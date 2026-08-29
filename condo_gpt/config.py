"""Central configuration loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PROMPT_VERSION = "p1-v1"
DEFAULT_SQL_ROW_LIMIT = 100
MAX_SQL_ROW_LIMIT = 500
MAX_CONVERSATION_TURNS = 3
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MODEL_HARD = "gpt-4o"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_MODEL_FALLBACK = "gemini-3.5-flash-lite"
DEFAULT_MAX_SESSION_COST_USD = 0.50
DEFAULT_CACHE_TTL_SECONDS = 3600
DEFAULT_CACHE_SIMILARITY = 0.95
DEFAULT_RATE_LIMIT = "30 per minute"
DEFAULT_MAPS_CALL_CAP = 20

_PLACEHOLDER_KEYS = {
    "your_openai_api_key_here",
    "your_google_api_key_here",
    "your_gemini_api_key_here",
    "your_shared_api_key_here",
}


def _env_secret(*names: str) -> str | None:
    """First non-empty, non-placeholder env value among *names."""
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        value = raw.strip()
        if value and value.lower() not in _PLACEHOLDER_KEYS:
            return value
    return None


def resolve_llm_provider(
    *,
    openai_api_key: str | None,
    google_api_key: str | None,
    explicit: str | None = None,
) -> str:
    """Pick openai, gemini, or none. Explicit LLM_PROVIDER wins when set."""
    provider = (explicit or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider in {"google", "gemini"}:
        return "gemini"
    if provider == "openai":
        return "openai"
    has_openai = bool(openai_api_key)
    has_gemini = bool(google_api_key)
    if has_gemini and not has_openai:
        return "gemini"
    if has_openai:
        return "openai"
    return "none"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    google_api_key: str | None
    llm_provider: str
    openai_model: str
    openai_model_hard: str
    gemini_model: str
    gemini_model_fallback: str
    gplaces_api_key: str | None
    flask_secret: str | None
    api_key: str | None
    pg_user: str | None
    pg_password: str | None
    pg_port: str
    pg_db: str | None
    pg_host: str
    prompt_version: str
    langchain_tracing: bool
    langchain_project: str
    flask_debug: bool
    cors_origins: list[str]
    sql_row_limit: int
    sql_statement_timeout_ms: int
    max_session_cost_usd: float
    cache_ttl_seconds: int
    cache_similarity_threshold: float
    rate_limit: str
    maps_call_cap: int
    audit_log_path: str

    @property
    def database_uri(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def api_auth_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def model(self) -> str:
        if self.llm_provider == "gemini":
            return self.gemini_model
        return self.openai_model

    @property
    def model_hard(self) -> str:
        if self.llm_provider == "gemini":
            return self.gemini_model
        return self.openai_model_hard


def get_settings() -> Settings:
    cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000")
    openai_api_key = _env_secret("OPENAI_API_KEY")
    google_api_key = _env_secret("GOOGLE_API_KEY", "GEMINI_API_KEY")
    llm_provider = resolve_llm_provider(
        openai_api_key=openai_api_key,
        google_api_key=google_api_key,
    )
    return Settings(
        openai_api_key=openai_api_key,
        google_api_key=google_api_key,
        llm_provider=llm_provider,
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        openai_model_hard=os.getenv("OPENAI_MODEL_HARD", DEFAULT_MODEL_HARD),
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        gemini_model_fallback=os.getenv(
            "GEMINI_MODEL_FALLBACK", DEFAULT_GEMINI_MODEL_FALLBACK
        ),
        gplaces_api_key=os.getenv("GPLACES_API_KEY"),
        flask_secret=os.getenv("FLASK_SECRET"),
        api_key=_env_secret("API_KEY"),
        pg_user=os.getenv("PG_USER"),
        pg_password=os.getenv("PG_PASSWORD"),
        pg_port=os.getenv("PG_PORT", "5432"),
        pg_db=os.getenv("PG_DB"),
        pg_host=os.getenv("PG_HOST", "localhost"),
        prompt_version=os.getenv("PROMPT_VERSION", PROMPT_VERSION),
        langchain_tracing=os.getenv("LANGCHAIN_TRACING_V2", "false").lower()
        in {"1", "true", "yes"},
        langchain_project=os.getenv("LANGCHAIN_PROJECT", "miami-condo-gpt"),
        flask_debug=os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"},
        cors_origins=[o.strip() for o in cors_raw.split(",") if o.strip()],
        sql_row_limit=int(os.getenv("SQL_ROW_LIMIT", str(DEFAULT_SQL_ROW_LIMIT))),
        sql_statement_timeout_ms=int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "15000")),
        max_session_cost_usd=float(
            os.getenv("MAX_SESSION_COST_USD", str(DEFAULT_MAX_SESSION_COST_USD))
        ),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))),
        cache_similarity_threshold=float(
            os.getenv("CACHE_SIMILARITY_THRESHOLD", str(DEFAULT_CACHE_SIMILARITY))
        ),
        rate_limit=os.getenv("RATE_LIMIT", DEFAULT_RATE_LIMIT),
        maps_call_cap=int(os.getenv("MAPS_CALL_CAP", str(DEFAULT_MAPS_CALL_CAP))),
        audit_log_path=os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl"),
    )
