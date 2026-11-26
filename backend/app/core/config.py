"""Application configuration. Every environment variable is prefixed with PLI_."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="PLI_",
        extra="ignore",
    )

    app_name: str = "Personal Learning Intelligence"
    environment: str = "development"
    debug: bool = True
    database_url: str = f"sqlite:///{DATA_DIR / 'pli.db'}"
    secret_key: str = "CHANGE-ME-IN-PRODUCTION-please-use-a-long-random-value"
    secret_key_previous: str | None = None
    session_ttl_hours: int = 12
    cookie_name: str = "pli_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_mb: int = 25
    demo_mode: bool = True

    # Fase 3 - Bayesian Knowledge Tracing defaults. Administrators can override
    # these at runtime through /api/v1/intelligence/bkt-params; every change is
    # recorded in engine_configs and in the audit log.
    bkt_p_init: float = 0.20
    bkt_p_transit: float = 0.25
    bkt_p_slip: float = 0.10
    bkt_p_guess: float = 0.20
    bkt_mastery_threshold: float = 0.80

    # Fase 4 - server-side AI defaults. API keys are NEVER read by the browser.
    # Runtime policy (budget, retries) lives in engine_configs; these are only
    # the initial values used before an administrator changes them.
    ai_request_timeout_sec: int = 30
    ai_max_tokens_per_request: int = 1024
    ai_daily_token_limit: int = 50000
    ai_monthly_cost_limit_usd: float = 0.0
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 150
    rag_top_k: int = 4
    tutor_max_history: int = 12

    # Fase 6 - production, encrypted backup, retention and monitoring.
    backup_encryption_key: str | None = None
    retention_days: int = 365
    ai_log_retention_days: int = 90
    audit_log_retention_days: int = 365
    metrics_enabled: bool = True

    @property
    def env_file_path(self) -> Path:
        return Path(self.model_config.get("env_file", str(PROJECT_ROOT / ".env")))

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
