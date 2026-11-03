import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
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

    # BASE_URL wins if set; otherwise use the public URL Render injects; otherwise localhost.
    base_url: str = Field(
        default_factory=lambda: os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")
    )
    short_code_length: int = 7

    # How long a resolved short link stays in the cache.
    cache_ttl_seconds: int = 3600

    # Fixed-window rate limits: (max requests, window in seconds)
    redirect_rate_limit: int = 120
    create_rate_limit: int = 20
    rate_limit_window_seconds: int = 60

    # Client IP resolution behind proxies (see app/proxy.py).
    # Shared secret the Vercel front end sends in x-proxy-secret; unset = trust no edge headers.
    proxy_secret: Optional[str] = None
    # Proxies that append to X-Forwarded-For in front of the app (3 on Render); 0 = socket peer.
    trusted_proxy_hops: int = 0

    # Ops switch: log the forwarding headers each rate-limited request arrives with,
    # to see what a proxy chain (e.g. Vercel -> Render) actually sends. Off by default.
    log_proxy_headers: bool = False


    @field_validator("database_url")
    @classmethod
    def normalise_postgres_scheme(cls, v: str) -> str:
        # Hosts such as Render hand out "postgres://" or "postgresql://" URLs. Neither
        # names a driver: the first is rejected by SQLAlchemy 2.x and the second picks
        # a driver by library default, which changed between SQLAlchemy versions.
        # Always pin the driver we actually install (psycopg2).
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg2://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
