from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    # Database and Redis settings
    database_url: str = (
        "postgresql+asyncpg://payment:payment@localhost:5432/payment_db"
    )
    redis_url: str = "redis://localhost:6379/0"
    
    # Service ports
    HTTP_PORT: int = 8000
    GRPC_PORT: int = 50051
    
    # Stripe settings
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "STRIPE_PUBLISHABLE_KEY", "STRIPE_PUBLISABLE_KEY"
        ),
    )
    STRIPE_WEBHOOK_SECRET: str | None = None
    
    # Keycloak settings
    KEYCLOAK_ISSUER: str = "http://localhost:8080/realms/finstack"
    KEYCLOAK_AUDIENCE: str = "paymentservice"
    KEYCLOAK_JWKS_URL: str | None = None
    
    # Optional: Keycloak admin settings for advanced features
    KEYCLOAK_SERVER_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM_NAME: str = "finstack"
    KEYCLOAK_CLIENT_ID: str = "paymentservice"
    KEYCLOAK_CLIENT_SECRET: str | None = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Derive JWKS URL from issuer if not provided
        if not self.KEYCLOAK_JWKS_URL:
            self.KEYCLOAK_JWKS_URL = f"{self.KEYCLOAK_ISSUER}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    """Get cached Settings instance."""
    return Settings()
