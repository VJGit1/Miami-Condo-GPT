# v2 improvements over GitHub baseline

This document compares the **current local codebase (v2)** with what is published on [GitHub `main`](https://github.com/VJGit1/Miami-Condo-GPT) (v1). It focuses on *capability deltas*—what got stronger and why.

**Baseline (GitHub):** LangChain ReAct agent, Flask UI, PostgreSQL tools, Maps/charts/PDF via model-generated code paths.  
**v2 (local):** Explicit LangGraph pipeline under `condo_gpt/`, Flask UI under `app/`, hybrid retrieval, SQL gateway, structured artifacts, HITL, lexical cache/cost controls, doc RAG, security surface, and an eval harness.

For a live walkthrough, see [DEMO.md](DEMO.md). Layout details are in the [README](../README.md).

---

## Snapshot

| Dimension | GitHub (v1) | v2 |
|-----------|-------------|-----|
| Agent | Opaque `create_react_agent` loop | Named LangGraph nodes in `condo_gpt/agent/` (route → retrieve → plan → validate → HITL → execute → critique → synthesize) |
| Schema context | Mega-prompt dump in `prefix.py` | Hybrid retrieval in `condo_gpt/retrieval/` (schema cards, glossary, SQL examples) |
| SQL safety | Tool SQL + readonly DB user | `condo_gpt/sql/gateway.py` — SELECT/WITH allowlist, LIMIT, timeout **in a transaction**, citations, refusal |
| Charts / maps / PDF | Model emits HTML/Python; PDF path used `exec` | Graph `render_plan` → `append_artifact` → `condo_gpt/renderers/` (no `exec`) |
| Trust for high-stakes SQL | Execute immediately | `pending_approval` + Approve/Reject; pending runs bound to session `user_id` |
| Cost / repeats | None | Lexical/demo cache (exact-norm match, then hash embeddings), session budget, cost badges |
| Documents | SQL/market only | Local HOA / offering-plan corpus + `DocCitation` |
| API | Form POST only | `/api/chat`, header-only `X-API-Key`, rate limit, audit JSONL |
| Quality bar | Manual spot checks | 51 unit tests + smoke/full eval runner + optional Postgres integration test |
| Layout | Flat `main.py` / `server.py` / `tools.py` | `app/` (Flask) + `condo_gpt/` (agent runtime) |
| Observability | Prints | `run_id`, cost estimates, metrics JSONL, LangSmith-ready traces |

---

## Capability map — why v2 is stronger

### 1. Reliability (answers you can regress)

**v1:** Success depended on a ReAct loop and prompt luck. There was no gold set or automated gate.

**v2:**
- Gold cases in `evals/cases/` (`smoke` for PR-speed checks, `full` for deeper coverage)
- Offline smoke for adversarial SQL/gateway checks without API keys
- Unit tests for routing, HITL, cache, retrieval, graph, gateway citation wiring, security, and artifacts
- Optional skip-if-no-DB integration test in `tests/integration/`

**Why it’s better:** You can change a prompt or node and *measure* whether lookup, join, aggregation, refusal, viz, and doc routes still hold.

---

### 2. Safety (bounded tools, not hopeful prompts)

**v1:** The model could draft arbitrary SQL and, for PDFs, emit code that the server executed. Charts/maps relied on HTML/code extraction from the model’s text. Safety rested mainly on a readonly DB role and regex-ish habits in the prompt.

**v2:**
- `condo_gpt/sql/gateway.py` — SELECT/WITH only, multi-statement block, LIMIT cap, `SET LOCAL statement_timeout` inside a transaction, structured citations
- Artifacts planned in-graph and rendered deterministically — **no arbitrary code execution**
- API key on `/api/*` via `X-API-Key` header only (not query string); Flask-Limiter; per-session Maps cap; audit JSONL per run
- Prompt-injection / destructive SQL covered in eval cases

**Why it’s better:** The LLM is treated as an *untrusted planner*. Hard boundaries live in code, so demos of blocked `DROP`/`DELETE` are reproducible.

---

### 3. Architecture (inspectable control flow)

**v1:** One flat ReAct agent with a long system prefix. Hard to explain *where* a failure happened (routing vs SQL vs rendering).

**v2:**
- `condo_gpt/agent/graph.py` — explicit StateGraph with named nodes
- Shared entrypoint `condo_gpt.runtime.run_agent()` for UI, JSON API, and evals
- Typed `condo_gpt.schemas.AgentResponse` (status, artifacts, citations, confidence, cost, HITL fields)
- Domain knowledge in retrieval assets instead of one mega-prompt
- Flask isolated in `app/`; `server.py` at repo root is a launcher

**Why it’s better:** You can walk a run node-by-node (and in LangSmith), show a critique retry, and point to concrete packages for each responsibility.

---

### 4. Groundedness (citations and retrieval)

**v1:** SQL might appear in logs/UI depending on parsing; schema and business glossary lived mostly inside a giant prefix. No document store.

**v2:**
- Hybrid retrieval: schema cards, glossary, ~32 SQL few-shots
- SQL citations recorded on the live graph path (`run_id`-keyed sinks)
- Doc RAG over `docs/corpus/` with source · page · snippet citations

**Why it’s better:** Answers are *checkable*—market facts point at SQL; HOA/policy questions point at documents instead of inventing rules from the schema.

---

### 5. Trust UX (human in the loop)

**v1:** Aggregates and investment-flavored asks executed in one shot.

**v2:** High-stakes patterns (e.g. `SUM(sale_price)`, investment language) pause at `pending_approval` with proposed SQL; Approve resumes execution, Reject leaves the DB untouched. Pending runs are bound to the creating session’s `user_id`. Confidence surfaces on the response.

**Why it’s better:** When money-shaped numbers are involved, a human gate is a feature, not a workaround.

---

### 6. Unit economics (cost and latency awareness)

**v1:** No repeat-question cache or session spend controls.

**v2:** Lexical/demo cache in `condo_gpt/cache/` (exact normalized question first, then hash-embedding cosine — not an OpenAI vector index), `MAX_SESSION_COST_USD`, token/cost fields on responses, UI cache-hit / cost badges.

**Why it’s better:** You can demo the *same* question twice and show ~$0 on the second hit. The cache is honest about what it is.

---

### 7. Observability (debug what ran)

**v1:** Console prints and ad-hoc debugging.

**v2:** Stable `run_id`, estimated cost/latency, `evals/results/metrics.jsonl`, audit log, LangSmith env hooks for named-node traces.

**Why it’s better:** Failures become replayable; demos can open a trace and explain critique/retry instead of “the agent did something.”

---

## How the stack maps to modules

```text
GitHub v1                         v2
---------                         --
main.py (ReAct + HTML/exec)  →    condo_gpt/agent/graph.py + condo_gpt/runtime.py
prefix mega-prompt           →    condo_gpt/retrieval/ (+ shorter node prompts)
tools SQL + exec/HTML        →    condo_gpt/sql/gateway.py + render_plan + renderers/
server.py monolith           →    app/server.py (UI/API) + server.py launcher
(none)                       →    condo_gpt/cache/, security/, sinks.py
(none)                       →    evals/, tests/, docs/corpus/
```

Removed from v1 leftovers: `prefix.py`, `boilerplate.py`, `sandbox.py`, `examples.py`, ReAct `setup_tools()`.

---

## What unchanged vs still next

**Unchanged on purpose:** Same product surface (condo Q&A, Postgres sample markets, Maps/charts), same local-demo posture.

**Still deferred:** pgvector migration, SSO / multi-tenant deploy, forecasting models, larger gold set (~80+ cases), load tests, real embedding cache.

---

## Bottom line

v1 proved the **product idea**: natural language over Miami condo data with tools and a browser UI.

v2 proves the **system**: bounded planning, measurable quality, citable answers, human gates for stakes, cost control, and a security story you can execute live—without relying on the model to “be careful.”
