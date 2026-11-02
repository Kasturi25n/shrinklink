from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration. Every value can be overridden with an env var or .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default so the app runs with zero setup.
    # Production: postgresql+psycopg2://user:pass@host:5432/shortener
    database_url: str = "sqlite:///./shortener.db"

    # Leave unset to use the in-process cache (fine for dev / single worker).
    # Production: redis://localhost:6379/0
    redis_url: Optional[str] = None

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60

    base_url: str = "http://localhost:8000"
    short_code_length: int = 7

    # How long a resolved short link stays in the cache.
    cache_ttl_seconds: int = 3600

    # Fixed-window rate limits: (max requests, window in seconds)
    redirect_rate_limit: int = 120
    create_rate_limit: int = 20
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
