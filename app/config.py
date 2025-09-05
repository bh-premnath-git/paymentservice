from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = (
        "postgresql+asyncpg://payment:payment@localhost:5432/payment_db"
    )
    redis_url: str = "redis://localhost:6379/0"
    APP_REST_PORT: int = 8000
    APP_GRPC_PORT: int = 50051


@lru_cache
def get_settings() -> Settings:
    """Get cached Settings instance."""
    return Settings()
