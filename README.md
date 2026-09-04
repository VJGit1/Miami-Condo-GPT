# Miami Condo GPT

Natural-language assistant for Miami condo sales and buildings, powered by a LangChain ReAct agent and PostgreSQL.


Condo GPT lets real estate agents and investors ask questions in plain English and get answers about condo buildings, units, sales, and market trends. It can generate SQL queries, charts, maps, and PDF reports.

Sample data is from [Condo Cube](https://condo-cube.com/) and covers these markets:

- South Beach
- Miami Beach
- South of Fifth

## Features

- Natural language interface for querying condo data
- Dynamic SQL generation via a LangGraph ReAct agent
- Google Maps integration for schools, geocoding, and driving distances
- Interactive maps and Chart.js graphs in the browser
- PDF report generation with ReportLab

## Technologies

- Python 3.11
- Flask
- PostgreSQL
- LangChain & LangGraph
- OpenAI GPT-4o-mini
- Google Maps / Places API
- Chart.js, ReportLab, FAISS

## Setup (Windows)

### 1. Clone and create a virtual environment

```powershell
cd condo_gpt
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

### 3. Configure environment variables

Required variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `GPLACES_API_KEY` | Google Places API key |
| `FLASK_SECRET` | Any random string for Flask sessions |
| `PG_USER` | PostgreSQL user (e.g. `readonly_user`) |
| `PG_PASSWORD` | PostgreSQL password |
| `PG_PORT` | PostgreSQL port (default `5432`) |
| `PG_DB` | Database name (e.g. `condo_gpt`) |

Load `.env` into your PowerShell session before starting the app:

```

### 4. Create the database

```
psql -U postgres
```

```sql
CREATE DATABASE condo_gpt;
CREATE USER readonly_user WITH PASSWORD 'your_password';
GRANT CONNECT ON DATABASE condo_gpt TO readonly_user;
\c condo_gpt
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
\q
```

### 5. Import sample data

```
psql -U postgres -d condo_gpt -f sample_db.sql
```

### 6. Run the application

```
python server.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser.

## Setup (Linux / macOS)

## Usage

- Enter natural language questions about Miami condos in the input field.
- The agent queries PostgreSQL and returns text, tables, charts, or maps.
- **Maps and charts** render directly in the browser.
- **PDF reports** are saved to the project folder; the UI displays "PDF Generated!" when complete.
- Use **Clear Memory** to reset conversation history (last 3 exchanges).

## Example Prompt Sequence

- What buildings on collins had the most sales in 2023?
- Generate a graph of this data
- Put the data in an html table
- Add a third column with the total sales volume of each building
- Add a fourth column with the median sales price for each building
- Replace the third column with the closest school to the building, and the fourth column with the driving distance to that school from the building

## Architecture: The 3 Core Pillars

1. **Robust SQL Gateway (`sql_gateway.py`)**:
   - AST validation via `sqlparse` ensuring only `SELECT` and `WITH ... SELECT` queries execute.
   - Comprehensive blacklist blocking DML (`INSERT`, `UPDATE`, `DELETE`), DDL (`DROP`, `ALTER`, `TRUNCATE`), and unsafe functions (`PG_SLEEP`, `DBLINK`).
   - Enforced `LIMIT` capping to prevent database memory exhaustion.
   - Query isolation with `SET LOCAL statement_timeout` inside transactional connections.

2. **Safe Artifact Generation (`renderers.py`)**:
   - Zero `exec()` arbitrary code execution.
   - Deterministic ReportLab PDF generation via the `generate_pdf_report` tool.
   - Clean HTML sanitization for Chart.js and Google Maps widgets.

3. **Multi-Tool ReAct Agent (`main.py` + `tools.py`)**:
   - Powered by LangGraph's ReAct execution engine with OpenAI `gpt-4o-mini`.
   - Real FAISS vector index (`search_proper_nouns`) for fuzzy entity resolution and address matching.
   - Live Google Places, Geocoding, and Directions API tools for geospatial intelligence.

## Project Structure

- `server.py` — Flask web server and session memory
- `main.py` — LangGraph ReAct agent orchestration and stream processing
- `tools.py` — The 6 active agent tools (Safe SQL, FAISS, Places, Geocoding, Directions, Safe PDF)
- `sql_gateway.py` — AST-based SQL security gateway and statement timeout manager
- `renderers.py` — Deterministic PDF builder and HTML sanitizer
- `prefix.py` — System prompt and domain rules
- `boilerplate.py` — Few-shot SQL holding period templates
- `tests/` — Automated test suite covering SQL Gateway, tool schemas, and PDF generation
- `sample_db.sql` — PostgreSQL sample dataset

## Running Automated Tests

Run the test suite using Python's built-in test runner:

```powershell
python -m unittest discover -s tests -v
```

