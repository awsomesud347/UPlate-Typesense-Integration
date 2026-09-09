from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    typesense_admin_api_key: str = "uplate-dev-key"
    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    allowed_origins: str = "http://localhost:5173"
    campus_id: str = "purdue"


@lru_cache
def get_settings() -> Settings:
    return Settings()
