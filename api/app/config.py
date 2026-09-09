from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    typesense_admin_api_key: str = "uplate-dev-key"
    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"

    # Primary query understanding: Typesense NL Search Models, which orchestrate a
    # third-party LLM. Anthropic is not a supported provider there, hence the split.
    nl_llm_api_key: str = ""
    nl_llm_model_name: str = "google/gemini-3.1-flash-lite"
    nl_model_id: str = "uplate-nl"

    # Fallback only, used when the Typesense NL path fails. Blank = degrade to keyword.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    allowed_origins: str = "http://localhost:5173"
    campus_id: str = "purdue"

    # UPlate already queries dining courts and On the Gos natively. This search
    # product covers the retail/off-campus half, which is the part that doesn't
    # exist anywhere else. Applied as a QUERY-TIME filter, not by removing data:
    # set false to search dining courts too, no reindex needed.
    retail_only: bool = True

    # Dev-only escape hatch so frontend work doesn't require a running Typesense.
    # Opt-in and off by default: fixture data does NOT honor allergen exclusions,
    # so a silent fallback would violate the safety invariant. Responses served
    # this way are stamped in the reasoning trace.
    use_fixtures: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
