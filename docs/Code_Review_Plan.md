# Code review remediation plan

v2 packages (`agent/`, `retrieval/`, `security/`) are directionally right. The live LangGraph path has silent sink bugs, leftover v1 files at the repo root, and test gaps. This document is the remediation plan from the code review; it does **not** implement the fixes.

Findings are ordered by severity, then folder-layout refactor, then missing tests.

---

## The seven findings

### 1. SQL citations never recorded on the graph path (high)

[`get_sql_citation_sink()`](../sinks.py) returns `list(_SQL_CITATION_SINK)` — a **copy**. [`execute_node`](../agent/nodes/execute.py) appends to that copy, so [`agent_runtime._response_from_state`](../agent_runtime.py) always sees an empty sink.

Verified: after `execute_node`, the real sink is `[]`. Demo claim “SQL citations in UI” fails for normal graph runs. [`tools.SafeSQLQueryTool._run`](../tools.py) uses `append_sql_citation` correctly, but the graph does not use that tool path.

**Fix:** Call `append_sql_citation(...)` from `execute_node` (do not append to the list returned by `get_*_sink()`).

---

### 2. Charts / maps / tables / PDFs never persist (high)

Same copy-then-append in [`synthesize_node`](../agent/nodes/synthesize.py) via `get_artifact_sink()`. Artifacts are planned in [`render_plan_node`](../agent/nodes/render_plan.py) then discarded.

Verified: after synthesize with a chart plan, `get_artifact_sink()` is `[]`.

**Fix:** Call `append_artifact(...)` for chart / table / pdf / map plans.

---

### 3. Missing regression tests for citations and artifacts (high)

[`tests/test_agent_graph.py`](../tests/test_agent_graph.py) only covers refuse / doc / chitchat. Nothing asserts citations or artifacts after a SQL + viz graph run, so findings 1 and 2 shipped broken.

**Fix:** Add tests that a SQL execute path records citations and a viz plan yields artifacts on `AgentResponse` (fake DB, no API keys). See [Missing tests](#missing-tests) below.

---

### 4. Global process sinks + HITL store (medium)

Module globals in [`sinks.py`](../sinks.py) and [`agent/pending.py`](../agent/pending.py) mix concurrent Flask requests. Approve is keyed only by `run_id` with no user/session check — anyone who learns a `run_id` can approve via `/api/chat/approve`. Maps budget uses `_MAPS_SESSION_KEY = "default"` in [`tools.py`](../tools.py) — process-wide cap, not per session as the README says.

**Fix:** Use `contextvars` or `run_id`-keyed stores; bind pending + maps cap to session / `user_id`.

---

### 5. Semantic cache is hash-embedding, not real embeddings (medium)

[`cache/semantic_cache.py`](../cache/semantic_cache.py) uses MD5 bag-of-words vectors at cosine threshold `0.95`. Similar but different condo questions can collide and return the wrong cached answer. Fine as a demo stub; risky if presented as a real semantic cache.

**Fix:** Document as a lexical / demo cache, **or** switch to OpenAI embeddings with a stricter exact-norm fallback.

---

### 6. Security surface gaps (medium)

- API key accepted via query string (`?api_key=`) in [`server.py`](../server.py) — ends up in logs / history.
- Web UI `/` bypasses API key by design — OK for local demo; not a locked API.
- `SET LOCAL statement_timeout` in [`sql_gateway.safe_run`](../sql_gateway.py) is best-effort and often a no-op outside a transaction; timeout story is weaker than advertised.
- Keyword bans include broad tokens like `COMMENT` / `SECURITY` — possible false blocks on odd SELECTs.

**Fix:** Header-only API key; wrap timeout in a transaction; tighten allowlist comments in README.

---

### 7. Dead / parallel code paths (medium)

[`setup_tools()`](../tools.py) still builds a ReAct-style toolkit (`SQLDatabaseToolkit`, FAISS retriever tool, `emit_*`). The LangGraph path never calls it. Emit tools work; the graph’s `render_plan` → `synthesize` path is the broken one (finding 2). Confusing for readers (“which path is live?”).

v1 leftovers unused by the v2 graph:

- [`prefix.py`](../prefix.py) (~400 lines)
- [`boilerplate.py`](../boilerplate.py)
- [`sandbox.py`](../sandbox.py)
- root [`__init__.py`](../__init__.py)
- [`examples.py`](../examples.py) (loads `retrieval/examples.jsonl` for legacy prompts)

**Fix:** Delete or quarantine leftovers; keep one emit path (graph `render_plan` → `append_artifact`). Collapse dual entrypoints (`main.py` re-export vs `server.py` → `agent_runtime`).

---

## Folder-layout refactor

The layered packages are fine. The weirdness is a **half-migrated flat root**: v1 monolith left on disk, v2 packages bolted beside it.

| Smell | Detail |
|-------|--------|
| Dual entrypoints | `main.py` re-exports `agent_runtime`; `server.py` imports runtime directly |
| Orphan v1 files | `prefix.py`, `boilerplate.py`, `sandbox.py` — unused by v2 graph |
| Split brains for examples | Root `examples.py` loads `retrieval/examples.jsonl` |
| Flat root clutter | `config`, `schemas`, `memory`, `observability`, `sinks`, `sql_gateway`, `tools`, `agent_runtime` next to packages |
| Misleading package root | Empty `__init__.py` at repo root |
| Fat modules | `tools.py` = maps + SQL tool + emit + FAISS setup; `renderers/__init__.py` holds all renderers |
| Import side effects | `tools.py` constructs `GooglePlacesTool()` / `GoogleMaps(...)` at import time |

**Target layout:**

```text
app/                 # server.py, templates/, static/
condo_gpt/
  agent/             # graph, nodes, hitl, pending, state
  retrieval/
  cache/
  security/
  renderers/         # split out of renderers/__init__.py
  sql/               # sql_gateway.py
  runtime.py         # run_agent / approve_agent
  schemas.py
  config.py
  memory.py
  observability.py
  sinks.py
  tools.py           # maps + remaining live tools only
tests/
docs/
evals/
```

Delete or quarantine after the emit path is fixed: `prefix.py`, `boilerplate.py`, `sandbox.py`, root `__init__.py`, unused `setup_tools` ReAct leftovers. Update README project-structure and architecture diagram after the move.

---

## Missing tests

| Test | Covers |
|------|--------|
| Graph SQL execute → citations on `AgentResponse` (fake DB, no API keys) | Finding 1 |
| Viz route / chart plan → chart artifact on `AgentResponse` | Finding 2 |
| HITL approve resumes and produces citations; reject leaves DB untouched | Finding 4 + HITL demo path |
| Gateway execute → citation wiring (not only `validate_sql` allow/deny) | Findings 1 + 6 |
| Optional skip-if-no-DB integration: `run_agent` against seeded Postgres | End-to-end |

Also: [`.gitignore`](../.gitignore) ignores `sample_db.sql` while README still tells people to import it — onboarding footgun if the dump is not elsewhere. Either stop ignoring the dump or document where to get it.

---

## Suggested implementation order

1. Sink append fixes + regression tests (findings 1–3)
2. HITL / session / maps isolation (finding 4)
3. Cache honesty or real embeddings (finding 5)
4. Auth / timeout / allowlist (finding 6)
5. Delete dead paths, then package move (finding 7 + folder layout)

Do not move packages until citations and artifacts work on the live graph path; otherwise the refactor hides the same bugs in new import paths.
