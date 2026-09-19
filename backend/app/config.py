from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, loaded from environment / .env.

    No secrets are hardcoded here; every value has an env var behind it.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "http://localhost:5173"

    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str = ""

    # Voice provider
    voice_provider: str = "mock"  # "mock" | "vapi"
    vapi_api_key: str = ""
    vapi_phone_number_id: str = ""
    vapi_assistant_id: str = ""

    # Where a live call is warm-transferred to on escalation (phone number or
    # SIP URI, per Vapi's transfer destination format). Required for a real
    # transfer to work; the mock provider ignores this entirely.
    human_transfer_destination: str = ""

    # Public webhook base URL (ngrok in dev, real host at demo time)
    public_base_url: str = "http://localhost:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
