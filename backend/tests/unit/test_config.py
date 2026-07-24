from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ProviderMode, Settings, get_settings


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


def test_hybrid_settings_are_validated_and_resolved_from_the_repository_root(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID)

    assert settings.hybrid_timeout_seconds == 90
    assert settings.hybrid_python_executable.name == "python.exe"
    assert settings.hybrid_runner_script.name == "indicconformer_runner.py"
    assert settings.hybrid_model_path.name == "e9b71b369c048e2c6b634d4c131061c34e441179"
    assert settings.hybrid_python_executable.is_absolute()
    assert settings.hybrid_runner_script.is_absolute()
    assert settings.hybrid_model_path.is_absolute()


@pytest.mark.parametrize("timeout", [9, 601])
def test_hybrid_timeout_bounds_are_enforced(timeout: int) -> None:
    with pytest.raises(ValidationError):
        Settings(hybrid_timeout_seconds=timeout)


@pytest.mark.parametrize(
    "field",
    ["hybrid_python_executable", "hybrid_runner_script", "hybrid_model_path"],
)
@pytest.mark.parametrize("value", ["", "bad\x00path"])
def test_hybrid_paths_reject_empty_or_nul_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
