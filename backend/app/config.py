from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app_rw:app_rw_dev@localhost:5432/lostfound"
    migration_database_url: str = "postgresql+psycopg://lostfound:lostfound_dev@localhost:5432/lostfound"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "lostfound"
    qdrant_url: str = "http://localhost:6333"        # or "local:/path" for embedded mode (tests/dev)
    redis_url: str = "redis://localhost:6379/0"

    match_backend: Literal["pg", "qdrant"] = "pg"
    match_top_n: int = 10
    match_min_text: float = 0.60                      # cosine floor for MiniLM text similarity (see docs/matching.md)
    match_min_image: float = 0.90                     # cosine floor for CLIP image similarity
    match_pool: int = 100
    rrf_k: int = 60

    jwt_secret: str = "change-me-in-real-deployments"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cors_origins: str = "http://localhost:3000"

    upload_dir: str = "./uploads"
    max_upload_mb: int = 8
    analytics_refresh_seconds: int = 300
    cache_ttl_seconds: int = 60
    rate_limit_scale: float = 1.0                     # multiply every rate limit (raise for e2e runs, keep 1 in production)


@lru_cache
def get_settings() -> Settings:
    return Settings()
