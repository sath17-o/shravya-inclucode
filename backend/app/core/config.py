from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderMode(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    DEMO = "demo"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHRAVYA_", env_file=".env", extra="ignore", enable_decoding=False
    )

    environment: str = "development"
    provider_mode: ProviderMode = ProviderMode.DEMO
    database_url: str = "sqlite:///./shravya.db"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
