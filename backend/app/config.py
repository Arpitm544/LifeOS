from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LifeOS API"
    environment: str = "development"
    allow_demo_auth: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lifeos"
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_audience: str = ""
    clerk_authorized_parties: str = ""
    anthropic_api_key: str = ""
    chat_rate_limit: int = 30
    api_rate_limit: int = 300
    transcription_rate_limit: int = 5
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / '.env', extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()

