import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderMode(StrEnum):
    DETERMINISTIC_DEMO = "deterministic_demo"
    LOCAL_FASTER_WHISPER = "local_faster_whisper"
    LOCAL_MALAYALAM_HYBRID = "local_malayalam_hybrid"


_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$")
_WHISPER_DEVICES = {"cpu", "cuda", "auto"}
_WHISPER_COMPUTE_TYPES = {"int8", "int8_float16", "int16", "float16", "float32"}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHRAVYA_", env_file=".env", extra="ignore", enable_decoding=False
    )

    environment: str = "development"
    provider_mode: ProviderMode = ProviderMode.DETERMINISTIC_DEMO
    database_url: str = "sqlite:///./shravya.db"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    media_root: Path = Path(__file__).resolve().parents[3] / ".runtime" / "audio"
    demo_minimum_timestamp_coverage: float = 0.90
    max_wav_upload_bytes: int = 10 * 1024 * 1024
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "ml"
    whisper_multilingual: bool = True
    whisper_beam_size: int = Field(default=5, ge=1, le=20)
    whisper_vad: bool = True
    whisper_word_timestamps: bool = True
    hybrid_python_executable: Path = _REPOSITORY_ROOT / ".venv-indic-asr/Scripts/python.exe"
    hybrid_runner_script: Path = _REPOSITORY_ROOT / "backend/scripts/indicconformer_runner.py"
    hybrid_model_path: Path = _REPOSITORY_ROOT / (
        ".runtime/models/indic-conformer-600m-multilingual/e9b71b369c048e2c6b634d4c131061c34e441179"
    )
    hybrid_timeout_seconds: int = Field(default=90, ge=10, le=600)

    @field_validator("provider_mode", mode="before")
    @classmethod
    def normalize_provider_mode(cls, value: str | ProviderMode) -> str | ProviderMode:
        if isinstance(value, ProviderMode):
            return value
        normalized = value.strip().casefold()
        if normalized == "demo":
            return ProviderMode.DETERMINISTIC_DEMO
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("whisper_model")
    @classmethod
    def validate_whisper_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("Whisper model name or local path must be non-empty.")
        return normalized

    @field_validator("whisper_device")
    @classmethod
    def validate_whisper_device(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in _WHISPER_DEVICES:
            raise ValueError("Whisper device must be cpu, cuda, or auto.")
        return normalized

    @field_validator("whisper_compute_type")
    @classmethod
    def validate_whisper_compute_type(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in _WHISPER_COMPUTE_TYPES:
            raise ValueError("Unsupported Whisper compute type.")
        return normalized

    @field_validator("whisper_language")
    @classmethod
    def validate_whisper_language(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _LANGUAGE_PATTERN.fullmatch(normalized):
            raise ValueError("Whisper language must be a lowercase language code.")
        return normalized

    @field_validator(
        "hybrid_python_executable", "hybrid_runner_script", "hybrid_model_path", mode="before"
    )
    @classmethod
    def resolve_hybrid_path(cls, value: str | Path) -> Path:
        raw = str(value)
        if not raw.strip() or "\x00" in raw:
            raise ValueError("Hybrid runtime path must be non-empty and contain no NUL characters.")
        path = Path(raw)
        return path if path.is_absolute() else _REPOSITORY_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
