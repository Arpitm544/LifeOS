from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LifeOS API"
    environment: str = "development"
    allow_demo_auth: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lifeos"
    database_ssl: bool = True
    # The worker reads due reminders for every user, so it needs an administrative
    # connection. Defaults to DATABASE_URL for local development.
    worker_database_url: str = ""
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_audience: str = ""
    clerk_authorized_parties: str = ""
    # Comma-separated browser origins allowed to call the API (the Next.js app).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_insight_model: str = "claude-haiku-5-5"
    llm_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    chat_rate_limit: int = Field(default=30, gt=0)
    api_rate_limit: int = Field(default=300, gt=0)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    # Push services browsers use; subscriptions to any other host are refused.
    push_allowed_hosts: str = ("fcm.googleapis.com,updates.push.services.mozilla.com,push.services.mozilla.com,"
                               "notify.windows.com,push.apple.com")
    worker_poll_seconds: int = Field(default=30, ge=5, le=300)
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / '.env', extra="ignore")

    @property
    def push_allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.push_allowed_hosts.split(',') if host.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
