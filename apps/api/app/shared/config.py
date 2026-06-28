from functools import lru_cache

from pydantic import model_validator
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
    whisper_device: str = "cpu"
    stt_provider: str = "whisper_stream"
    live_voice_v2: bool = True
    mem0_enabled: bool = True
    cors_origins: str = "*"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "aipal://spotify-callback"

    @model_validator(mode="after")
    def validate_runtime_environment(self) -> "Settings":
        env = (self.aipal_env or "").strip().lower()
        production_like = env in {"production", "prod", "staging", "stage"}
        if not production_like:
            return self

        if not self.jwt_secret or self.jwt_secret == "dev-secret-change-in-production":
            raise ValueError("JWT_SECRET must be set to a non-default value in production-like environments")
        if self.magic_link_dev_return_token:
            raise ValueError("MAGIC_LINK_DEV_RETURN_TOKEN must be disabled in production-like environments")
        if self.llm_provider.lower() == "deepseek" and not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY must be set when DeepSeek is selected in production-like environments")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
