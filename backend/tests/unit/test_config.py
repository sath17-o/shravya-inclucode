from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_load_all_supported_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("SHRAVYA_ENVIRONMENT", "test")
    monkeypatch.setenv("SHRAVYA_PROVIDER_MODE", "demo")
    monkeypatch.setenv("SHRAVYA_DATABASE_URL", "sqlite:///./configured.db")
    monkeypatch.setenv("SHRAVYA_CORS_ORIGINS", "http://one.test,http://two.test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.environment == "test"
    assert settings.provider_mode.value == "deterministic_demo"
    assert settings.database_url == "sqlite:///./configured.db"
    assert settings.cors_origins == ["http://one.test", "http://two.test"]


def test_invalid_provider_mode_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SHRAVYA_PROVIDER_MODE", "unapproved")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_env_example_uses_the_valid_environment_variable_name() -> None:
    example = Path(__file__).resolve().parents[3] / ".env.example"
    content = example.read_text(encoding="utf-8")

    assert "SHRAVYA_ENVIRONMENT=development" in content
    assert "SHRAVYA_ENV=development" not in content


def test_settings_model_can_be_constructed_after_cache_clear(monkeypatch) -> None:
    monkeypatch.setenv("SHRAVYA_ENVIRONMENT", "development")
    get_settings.cache_clear()
    assert Settings().environment == "development"
