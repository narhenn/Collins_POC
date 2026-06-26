"""Application settings (env-overridable)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOALCERT_", env_file=".env", extra="ignore")

    # SQLite by default so the POC runs with zero infra. docker-compose sets a Postgres URL.
    database_url: str = "sqlite+pysqlite:///./goalcert.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Default pacing: sim-seconds advanced per real second when streaming a run.
    default_stream_speed: float = 30.0
    seed_on_startup: bool = True


settings = Settings()
