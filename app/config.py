from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    database_url: str = (
        "postgresql+asyncpg://payment:payment@localhost:5432/payment_db"
    )
    redis_url: str = "redis://localhost:6379/0"
    HTTP_PORT: int = 8000
    GRPC_PORT: int = 50051
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "STRIPE_PUBLISHABLE_KEY", "STRIPE_PUBLISABLE_KEY"
        ),
    )
    STRIPE_WEBHOOK_SECRET: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Get cached Settings instance."""
    return Settings()
