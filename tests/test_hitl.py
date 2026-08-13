"""HITL trigger tests — offline."""

from condo_gpt.agent.graph import build_graph, resume_after_approval
from condo_gpt.agent.hitl import requires_hitl
from condo_gpt.agent.pending import pop_pending, save_pending
from condo_gpt.sinks import get_sql_citation_sink, reset_sinks


class FakeDB:
    def __init__(self):
        self.calls = []

    def run(self, sql):
        self.calls.append(sql)
        return "[(1234567,)]"


def test_hitl_sum_aggregate():
    needs, reason = requires_hitl(
        "Total sales volume in 2023",
        "SELECT SUM(s.sale_price) FROM core_condosale s",
    )
    assert needs
    assert "SUM" in reason or "aggregate" in reason.lower()


def test_hitl_investment_language():
    needs, reason = requires_hitl(
        "Should I invest in Brickell condos?",
        "SELECT alt_name FROM core_condobuilding LIMIT 5",
    )
    assert needs
    assert "investment" in reason.lower() or "Investment" in reason


def test_hitl_simple_lookup_ok():
    needs, _ = requires_hitl(
        "List 3 approved buildings",
        "SELECT alt_name, address FROM core_condobuilding WHERE approved = TRUE LIMIT 3",
        retrieval_score=0.8,
    )
    assert not needs


def test_hitl_low_retrieval():
    needs, reason = requires_hitl(
        "Obscure query",
        "SELECT 1",
        retrieval_score=0.1,
    )
    assert needs
    assert "retrieval" in reason.lower()


def test_hitl_graph_pauses_before_execute():
    reset_sinks()
    db = FakeDB()
    graph = build_graph(db=db, llm=None, llm_hard=None)
    state = graph.invoke(
        {
            "run_id": "hitl-pause",
            "question": "Total sales volume for 2023 approved buildings",
        }
    )
    assert state.get("pending_approval")
    assert db.calls == []


def test_hitl_reject_leaves_db_untouched():
    reset_sinks()
    db = FakeDB()
    graph = build_graph(db=db, llm=None, llm_hard=None)
    state = graph.invoke(
        {
            "run_id": "hitl-reject",
            "question": "Total sales volume for 2023 approved buildings",
            "metadata": {"user_id": "u1"},
        }
    )
    assert state.get("pending_approval")
    pending = pop_pending("hitl-reject", owner_id="u1")
    assert pending is not None
    assert db.calls == []


def test_hitl_approve_retry_uses_hard_model():
    """Aggregation retries after HITL must keep llm_hard, matching the live graph."""
    import json
    from types import SimpleNamespace

    class RecordingLLM:
        def __init__(self, name):
            self.name = name
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            sql = (
                "SELECT SUM(s.sale_price) FROM core_condosale s "
                "JOIN core_condounit u ON s.condo_unit_id = u.id "
                "JOIN core_condobuilding b ON u.building_id = b.id "
                "WHERE b.approved = TRUE AND s.blacklist = FALSE LIMIT 100"
            )
            return SimpleNamespace(
                content=json.dumps({"sql": sql, "rationale": self.name}),
                response_metadata={},
            )

    class EmptyThenOkDB:
        def __init__(self):
            self.calls = 0

        def run(self, sql):
            self.calls += 1
            if self.calls == 1:
                return "[]"
            return "[(1234567,)]"

    reset_sinks()
    llm = RecordingLLM("soft")
    llm_hard = RecordingLLM("hard")
    db = EmptyThenOkDB()
    pending = {
        "run_id": "hitl-retry-hard",
        "question": "Total sales volume for 2023 approved buildings",
        "route": "sql_qa",
        "planned_sql": "SELECT SUM(s.sale_price) FROM core_condosale s LIMIT 100",
        "retry_count": 0,
    }
    final = resume_after_approval(pending, db=db, llm=llm, llm_hard=llm_hard)
    assert not final.get("pending_approval")
    assert llm_hard.calls == 1
    assert llm.calls == 0
    assert db.calls == 2


def test_hitl_approve_resumes_and_cites():
    reset_sinks()
    db = FakeDB()
    graph = build_graph(db=db, llm=None, llm_hard=None)
    state = graph.invoke(
        {
            "run_id": "hitl-approve",
            "question": "Total sales volume for 2023 approved buildings",
            "metadata": {"user_id": "u1"},
        }
    )
    assert state.get("pending_approval")
    pending = pop_pending("hitl-approve", owner_id="u1")
    reset_sinks("hitl-approve")
    final = resume_after_approval(pending, db=db, llm=None)
    assert not final.get("pending_approval")
    cites = get_sql_citation_sink("hitl-approve")
    assert cites and cites[0]["blocked"] is False
    assert db.calls


def test_pending_owner_isolation():
    save_pending(
        "owned-run",
        {"run_id": "owned-run", "question": "q", "metadata": {"user_id": "alice"}},
    )
    assert pop_pending("owned-run", owner_id="bob") is None
    assert pop_pending("owned-run", owner_id="alice") is not None
