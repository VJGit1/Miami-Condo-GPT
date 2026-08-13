# Miami Condo GPT

Natural-language assistant for Miami condo sales and buildings, powered by a **LangGraph StateGraph** agent and PostgreSQL.

Condo GPT lets real estate agents and investors ask questions in plain English and get answers about condo buildings, units, sales, and market trends. It generates **validated SQL**, charts, maps, PDF reports, and **document citations** via **structured artifacts** (the model never executes arbitrary Python).

Sample data is from [Condo Cube](https://condo-cube.com/) and covers:

- South Beach
- Miami Beach
- South of Fifth

## Architecture

```mermaid
flowchart TB
  subgraph clients [Clients]
    UI[Flask UI]
    API["/api/chat · /api/chat/approve"]
    Eval[evals.runner]
  end

  Runtime[condo_gpt.runtime.run_agent]
  Cache[semantic_cache]
  Audit[security + audit JSONL]

  subgraph graph [LangGraph StateGraph]
    Route[route]
    Retrieve[retrieve]
    Plan[plan_sql]
    Validate[validate]
    HITL[hitl_check / pause]
    Execute[execute]
    Critique[critique]
    Render[render_plan]
    Doc[doc_search]
    Synth[synthesize]
  end

  RetrSvc[retrieval hybrid context]
  Gateway[sql gateway]
  PG[(PostgreSQL readonly)]
  Docs[docs/corpus FAISS]
  Renderers[renderers chart/map/pdf/table]
  Obs[observability · LangSmith]

  UI --> Runtime
  API --> Runtime
  Eval --> Runtime
  Runtime --> Cache
  Runtime --> Audit
  Runtime --> graph
  Cache -.->|hit| Runtime

  Route -->|sql / viz / geo| Retrieve
  Route -->|doc| Doc
  Route -->|refuse / chitchat| Synth
  Retrieve --> Plan
  RetrSvc --> Retrieve
  Docs --> Doc
  Plan --> Validate
  Validate --> HITL
  HITL -->|approved| Execute
  HITL -->|pending| Synth
  Execute --> Critique
  Critique -->|retry| Plan
  Critique -->|ok| Render
  Render --> Synth
  Doc --> Synth

  Validate --> Gateway
  Execute --> Gateway
  Gateway --> PG
  Render --> Renderers
  graph --> Obs
```

| Layer | Role |
|-------|------|
| `condo_gpt/agent/graph.py` | Explicit LangGraph pipeline: route → retrieve → plan → validate → HITL → execute → critique → synthesize |
| `condo_gpt/retrieval/` | Hybrid context: schema cards, glossary, 32 SQL examples, doc corpus search |
| `condo_gpt.runtime.run_agent` | Single entrypoint for UI, `/api/chat`, and evals (+ cache) |
| `condo_gpt/sql/gateway.py` | SELECT/WITH allowlist, LIMIT cap, statement timeout in a transaction, citations |
| `condo_gpt.schemas.AgentResponse` | Typed text + artifacts + HITL/cost/confidence fields |
| `condo_gpt/cache/semantic_cache.py` | Lexical/demo cache (exact-norm match, then hash-embedding cosine) |
| `condo_gpt/security/` | API key auth, audit JSONL, per-session Maps call cap |
| `condo_gpt/renderers/` | Deterministic Chart.js / Maps / ReportLab / doc citation rendering |
| `evals/` | Smoke (15) + full (30) gold sets + offline/live runner |
| `condo_gpt/observability.py` | LangSmith hooks + token/cost estimates + `metrics.jsonl` |

See [docs/DEMO.md](docs/DEMO.md) for the 7-minute demo script.

## Features

- Natural language interface for querying condo data
- **LangGraph StateGraph** with named nodes (replaces opaque ReAct)
- **Hybrid retrieval** instead of mega-prompt schema dump
- **HITL approve-SQL** for high-stakes aggregates and investment language
- **Semantic cache** and per-session cost budget
- **Doc RAG** from local `docs/corpus/` fixture (HOA / offering-plan snippets)
- Structured `emit_chart` / `emit_map` / `emit_table` / `emit_pdf` tools (no `exec`)
- Google Maps integration with per-session call cap
- JSON API: `POST /api/chat`, `POST /api/chat/approve`
- API key auth (`X-API-Key`) + rate limiting on `/api/chat`
- Eval harness: smoke offline (no keys) + live agent runs

## Technologies

- Python 3.11
- Flask + Flask-Limiter
- PostgreSQL
- LangChain & LangGraph
- OpenAI GPT-4o-mini (+ optional `OPENAI_MODEL_HARD` for complex SQL) **or** Gemini 3.5 Flash (+ Flash-Lite fallback)
- Google Maps / Places API
- Chart.js, ReportLab, FAISS (entity index)
- pytest

## Setup (Linux / macOS)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
python -m condo_gpt.retrieval.ingest_docs   # optional: build doc index
```

Create DB / readonly user (see below), import `sample_db.sql`, then:

```bash
python server.py
```

Open [http://localhost:5000](http://localhost:5000).

### Required environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (chat LLM; optional if using Gemini) |
| `GOOGLE_API_KEY` | Google AI Studio / Gemini API key (optional if using OpenAI). `GEMINI_API_KEY` also works |
| `LLM_PROVIDER` | `openai` or `gemini`. Required only if **both** keys are set (defaults to openai) |
| `GEMINI_MODEL` | Gemini primary model (default `gemini-3.5-flash`) |
| `GEMINI_MODEL_FALLBACK` | Used on Gemini rate-limit / quota errors (default `gemini-3.5-flash-lite`) |
| `GPLACES_API_KEY` | Google Places API key |
| `FLASK_SECRET` | Flask session secret |
| `PG_USER` / `PG_PASSWORD` / `PG_PORT` / `PG_DB` | PostgreSQL |
| `PG_HOST` | optional, default `localhost` |
| `API_KEY` | Shared key for `/api/*` (optional; when set, required on API routes) |
| `MAX_SESSION_COST_USD` | Session spend soft cap (default `0.50`) |
| `OPENAI_MODEL_HARD` | Model for complex SQL planning (default `gpt-4o`) |
| `CACHE_TTL_SECONDS` / `CACHE_SIMILARITY_THRESHOLD` | Semantic cache tuning |
| `RATE_LIMIT` | Flask-Limiter spec (default `30 per minute`) |
| `MAPS_CALL_CAP` | Max Maps tool calls per session (default `20`) |
| `AUDIT_LOG_PATH` | JSONL audit log (default `logs/audit.jsonl`) |
| `LANGCHAIN_TRACING_V2` | `true` to enable LangSmith |
| `LANGCHAIN_API_KEY` | LangSmith API key |
| `LANGCHAIN_PROJECT` | default `miami-condo-gpt` |
| `PROMPT_VERSION` | default `p1-v1` |

### Database

```sql
CREATE DATABASE condo_gpt;
CREATE USER readonly_user WITH PASSWORD 'your_password';
GRANT CONNECT ON DATABASE condo_gpt TO readonly_user;
\c condo_gpt
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
```

```bash
psql -U postgres -d condo_gpt -f sample_db.sql
```

## Tests & evals

```bash
# Unit tests (routing, HITL, cache, retrieval, graph, gateway) — no API keys
pytest tests/ -q

# Offline smoke (gateway refusal checks)
python -m evals.runner --split smoke --offline-only

# Full agent smoke (needs DB + OpenAI)
python -m evals.runner --split smoke

# Expanded nightly suite
python -m evals.runner --split full
```

## API

```bash
curl -s localhost:5000/api/health
curl -s -X POST localhost:5000/api/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_shared_api_key_here' \
  -d '{"question":"List 3 approved buildings with addresses"}'
```

## Security notes

- `/api/*` requires `X-API-Key` when `API_KEY` is set (header only — not query string). The web UI form at `/` is exempt.
- HITL approve is bound to the session `user_id` that created the pending run.
- Owner/principal names are sensitive — default answers aggregate unless explicitly requested.
- All SQL goes through the readonly gateway. `SET LOCAL statement_timeout` runs inside a transaction. The allowlist blocks DML/DDL keywords (INSERT/UPDATE/DELETE/DROP/…); it does not treat words like `COMMENT` or `SECURITY` as forbidden, to avoid false positives on SELECT text.
- Repeat-question cache is lexical/demo-grade (exact normalized match, then hash embeddings), not an OpenAI vector index.

## Project structure

```text
app/                      Flask UI + templates/static
  server.py
condo_gpt/
  agent/                  LangGraph state, nodes, HITL, graph
  runtime.py              run_agent() / approve_agent()
  retrieval/              hybrid retrieval + doc search + ingest
  cache/                  lexical/demo cache
  security/               audit log, Maps budget, API key helper
  sql/gateway.py          SQL allowlist / limits / timeout
  schemas.py              AgentResponse, artifacts, DocCitation
  renderers/              chart/map/pdf/table/doc rendering
  tools.py                Maps + SafeSQL helpers
  sinks.py                run_id-keyed artifact/citation collectors
server.py                 launcher (`python server.py`)
evals/                    gold cases + runner
tests/                    unit + optional Postgres integration
docs/corpus/              fixture HOA/offering-plan text corpus
docs/DEMO.md              demo script
docs/Code_Review_Plan.md  remediation plan
```

## Setup (Windows)

```powershell
cd condo_gpt
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```
