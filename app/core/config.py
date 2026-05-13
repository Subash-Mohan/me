from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    jwt_secret: SecretStr
    jwt_expires_days: int = 30

    supermemory_api_key: SecretStr
    supermemory_base_url: str = "https://api.supermemory.ai"
    supermemory_timeout_ms: int = 2000

    openrouter_api_key: SecretStr
    openrouter_default_model: str

    chat_history_turns: int = 10

    @field_validator("supermemory_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # ty: ignore[missing-argument]
