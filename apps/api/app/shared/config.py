from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aipal:aipal_dev@localhost:5432/aipal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    aipal_env: str = "development"
    magic_link_dev_return_token: bool = True
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    whisper_model: str = "base"
    mem0_enabled: bool = True
    cors_origins: str = "*"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "aipal://spotify-callback"
    google_client_id: str = ""
    apple_team_id: str = ""
    apple_client_id: str = ""
    resend_api_key: str = ""
    aipal_internal_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
