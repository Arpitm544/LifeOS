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
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_audience: str = ""
    clerk_authorized_parties: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    chat_rate_limit: int = Field(default=30, gt=0)
    api_rate_limit: int = Field(default=300, gt=0)
    transcription_rate_limit: int = Field(default=5, gt=0)
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / '.env', extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()

