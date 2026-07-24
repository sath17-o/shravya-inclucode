from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.contracts.teacher_review import DomainError
from app.core.config import ProviderMode, Settings
from app.services.transcription_provider import (
    LocalFasterWhisperTranscriptionProvider,
    LocalWhisperConfiguration,
    TranscriptionInput,
    clear_local_provider_cache_for_tests,
    local_provider_for_settings,
    provider_for_settings,
)


class FakeWhisperModel:
    def __init__(self, segments):
        self._segments = segments
        self.calls = 0

    def transcribe(self, *_args, **_kwargs):
        self.calls += 1
        return iter(self._segments), SimpleNamespace(language="ml", language_probability=0.8)


def _source() -> TranscriptionInput:
    return TranscriptionInput("a" * 64, 1000, Path("local-proof.wav"))


def _segment(*, text: str = "സസ്യങ്ങൾക്ക് chlorophyll ആവശ്യമാണ്."):
    return SimpleNamespace(
        start=0.0,
        end=1.0,
        text=text,
        avg_logprob=-0.2,
        no_speech_prob=0.01,
        compression_ratio=1.1,
        temperature=0.0,
        words=[SimpleNamespace(start=0.0, end=0.5, word="സസ്യങ്ങൾക്ക്", probability=0.9)],
    )


def _configuration() -> LocalWhisperConfiguration:
    return LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True)


def test_local_provider_is_lazy_consumes_generators_and_preserves_native_output() -> None:
    calls = 0
    model = FakeWhisperModel([_segment()])

    def load(_configuration):
        nonlocal calls
        calls += 1
        return model

    provider = LocalFasterWhisperTranscriptionProvider(
        _configuration(), model_loader=load, version_lookup=lambda _package: "test-version"
    )
    assert calls == 0

    result = provider.transcribe(_source())
    second = provider.transcribe(_source())

    assert calls == 1
    assert model.calls == 2
    assert result.segments[0].text == "സസ്യങ്ങൾക്ക് chlorophyll ആവശ്യമാണ്."
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 1000
    assert result.segments[0].avg_logprob == -0.2
    assert result.segments[0].words[0].probability == 0.9
    assert result.raw_output()["segments"][0]["words"][0]["probability"] == 0.9
    assert second.model_load_seconds == 0.0


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (None, "local_stt_malformed_model"),
        (FakeWhisperModel([]), "local_stt_empty_transcript"),
    ],
)
def test_local_provider_fails_with_typed_errors(model, code: str) -> None:
    provider = LocalFasterWhisperTranscriptionProvider(
        _configuration(), model_loader=lambda _configuration: model
    )

    with pytest.raises(DomainError) as error:
        provider.transcribe(_source())

    assert error.value.code == code


def test_model_load_failure_is_typed() -> None:
    def fail(_configuration):
        raise OSError("model cache unavailable")

    provider = LocalFasterWhisperTranscriptionProvider(_configuration(), model_loader=fail)

    with pytest.raises(DomainError) as error:
        provider.transcribe(_source())

    assert error.value.code == "local_stt_model_load_failed"


def test_local_whisper_loader_receives_the_explicit_offline_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Loader:
        def __init__(self, model, **kwargs) -> None:
            captured["model"] = model
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Loader))
    LocalFasterWhisperTranscriptionProvider._load_model(_configuration())
    assert captured["local_files_only"] is False

    offline = LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True)
    LocalFasterWhisperTranscriptionProvider._load_model(offline)
    assert captured["local_files_only"] is True


def test_provider_selection_is_explicit_and_shared_only_for_matching_local_settings(
    tmp_path,
) -> None:
    clear_local_provider_cache_for_tests()
    local = Settings(provider_mode=ProviderMode.LOCAL_FASTER_WHISPER)
    hybrid = Settings(provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID)
    deterministic = Settings(provider_mode=ProviderMode.DETERMINISTIC_DEMO)
    first = local_provider_for_settings(local)
    second = local_provider_for_settings(local)

    assert first is second
    assert provider_for_settings(deterministic, tmp_path / "fixture.json").__class__.__name__ == (
        "DeterministicDemoTranscriptionProvider"
    )
    assert provider_for_settings(hybrid, tmp_path / "fixture.json").__class__.__name__ == (
        "LocalMalayalamHybridTranscriptionProvider"
    )


def test_unknown_provider_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(provider_mode="live")
