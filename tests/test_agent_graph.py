"""Offline agent graph smoke tests."""

from condo_gpt.agent.graph import build_graph
from condo_gpt.agent.nodes.execute import execute_node
from condo_gpt.agent.nodes.synthesize import synthesize_node
from condo_gpt.sinks import get_artifact_sink, get_sql_citation_sink, reset_sinks


class FakeDB:
    def __init__(self, rows="[('Faena House', 3), ('Continuum', 2)]"):
        self.calls = []
        self.rows = rows

    def run(self, sql):
        self.calls.append(sql)
        return self.rows


def test_graph_refuse_route():
    reset_sinks()
    graph = build_graph(db=None, llm=None, llm_hard=None)
    state = graph.invoke({"run_id": "test-refuse", "question": "DROP TABLE core_condobuilding"})
    assert state.get("route") == "refuse"
    assert state.get("refused")
    cites = get_sql_citation_sink("test-refuse")
    assert cites and cites[0]["blocked"]


def test_graph_doc_route():
    graph = build_graph(db=None, llm=None, llm_hard=None)
    state = graph.invoke(
        {
            "run_id": "test-doc",
            "question": "What is the Shore Club pet policy in the HOA documents?",
        }
    )
    assert state.get("route") == "doc"
    assert state.get("doc_citations") is not None
    assert state.get("final_text")


def test_graph_chitchat_route():
    graph = build_graph(db=None, llm=None, llm_hard=None)
    state = graph.invoke({"run_id": "test-hi", "question": "Hello"})
    assert state.get("route") == "chitchat"
    assert "CondoGPT" in (state.get("final_text") or "")


def test_graph_sql_execute_records_citations():
    reset_sinks()
    db = FakeDB(rows="[('Faena House', '3201 Collins')]")
    graph = build_graph(db=db, llm=None, llm_hard=None)
    state = graph.invoke(
        {"run_id": "test-sql-cite", "question": "List 3 approved buildings with addresses", "approved": True}
    )
    assert state.get("route") == "sql_qa"
    cites = get_sql_citation_sink("test-sql-cite")
    assert cites, "execute_node must record SQL citations on the live sink"
    assert cites[0]["blocked"] is False
    assert "SELECT" in (cites[0]["query"] or "").upper()
    assert db.calls, "validated SQL should hit the fake DB"


def test_graph_viz_emits_chart_artifact():
    reset_sinks()
    db = FakeDB()
    graph = build_graph(db=db, llm=None, llm_hard=None)
    state = graph.invoke(
        {"run_id": "test-viz", "question": "bar chart of approved buildings", "approved": True}
    )
    assert state.get("route") == "viz"
    artifacts = get_artifact_sink("test-viz")
    assert artifacts, "synthesize_node must persist chart artifacts"
    assert getattr(artifacts[0], "type", None) == "chart"
    assert artifacts[0].labels


def test_execute_node_citation_wiring():
    reset_sinks()
    db = FakeDB(rows="[(1,)]")
    execute_node(
        {"run_id": "ex", "planned_sql": "SELECT 1", "sql_blocked": False},
        db=db,
    )
    cites = get_sql_citation_sink("ex")
    assert cites[0]["blocked"] is False
    assert "LIMIT" in cites[0]["query"].upper()


def test_execute_node_blocked_sql_not_run():
    reset_sinks()
    db = FakeDB()
    execute_node(
        {
            "run_id": "ex-block",
            "planned_sql": "DELETE FROM core_condosale",
            "sql_blocked": False,
        },
        db=db,
    )
    cites = get_sql_citation_sink("ex-block")
    assert cites and cites[0]["blocked"] is True
    assert db.calls == []


def test_synthesize_chart_plan_appends_artifact():
    reset_sinks()
    synthesize_node(
        {
            "run_id": "syn",
            "question": "chart",
            "route": "viz",
            "execution_output": "[('a', 1)]",
            "artifacts_plan": {
                "kind": "chart",
                "title": "T",
                "chart_type": "bar",
                "labels": ["a"],
                "data": [1.0],
            },
        }
    )
    arts = get_artifact_sink("syn")
    assert len(arts) == 1
    assert arts[0].type == "chart"
