from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.teacher_review import DomainError
from app.core.config import ProviderMode, Settings
from app.services.malayalam_hybrid_provider import (
    INDICCONFORMER_DECODER,
    INDICCONFORMER_LANGUAGE,
    INDICCONFORMER_MODEL_ID,
    INDICCONFORMER_REVISION,
    HybridConfiguration,
    LocalMalayalamHybridTranscriptionProvider,
    clear_hybrid_provider_cache_for_tests,
    hybrid_provider_for_settings,
)
from app.services.transcription_provider import (
    LocalWhisperConfiguration,
    ProviderSegment,
    ProviderTranscription,
    TranscriptionInput,
    clear_local_provider_cache_for_tests,
    local_provider_for_settings,
)


class FakeWhisperProvider:
    def __init__(self, segments: tuple[ProviderSegment, ...] | None = None) -> None:
        self.calls = 0
        self.segments = (
            segments
            if segments is not None
            else (
                ProviderSegment(0, 500, "raw English timing", sequence=1),
                ProviderSegment(500, 1000, "raw timing two", sequence=2),
            )
        )

    def transcribe(self, _source: TranscriptionInput) -> ProviderTranscription:
        self.calls += 1
        now = datetime.now(UTC)
        return ProviderTranscription(
            segments=self.segments,
            provider_mode="local_faster_whisper",
            provider_implementation="local-faster-whisper",
            provider_version="test-whisper",
            ctranslate2_version="test-ctranslate2",
            model_identifier="small",
            device="cpu",
            compute_type="int8",
            language_requested="ml",
            language_detected="ml",
            language_probability=0.9,
            multilingual=False,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            transcription_started_at=now,
            transcription_completed_at=now,
            model_load_seconds=0.1,
            inference_seconds=0.2,
        )


class FailingWhisperProvider:
    def transcribe(self, _source: TranscriptionInput) -> ProviderTranscription:
        raise DomainError(
            "local_stt_model_load_failed", "audio.local_stt_model_load_failed", "validation"
        )


def _manifest(model: Path) -> None:
    (model / "shravya-model-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": INDICCONFORMER_MODEL_ID,
                "revision": INDICCONFORMER_REVISION,
                "language": INDICCONFORMER_LANGUAGE,
                "decoder": INDICCONFORMER_DECODER,
            }
        ),
        encoding="utf-8",
    )


def _configuration(tmp_path: Path, *, manifest: bool = True) -> HybridConfiguration:
    python = tmp_path / "python.exe"
    runner = tmp_path / "runner.py"
    model = tmp_path / "model"
    python.write_bytes(b"")
    runner.write_text("# runner", encoding="utf-8")
    model.mkdir()
    if manifest:
        _manifest(model)
    return HybridConfiguration(
        python,
        runner,
        model,
        90,
        LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True),
    )


def _source(tmp_path: Path) -> TranscriptionInput:
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"audio")
    return TranscriptionInput("a" * 64, 1000, audio)


def _response(request: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": request["request_id"],
        "status": "ok",
        "model": {
            "model_id": INDICCONFORMER_MODEL_ID,
            "revision": INDICCONFORMER_REVISION,
            "language": INDICCONFORMER_LANGUAGE,
            "decoder": INDICCONFORMER_DECODER,
            "offline": True,
        },
        "runtime": {
            "python_version": "3.11.0",
            "torch_version": "2.0.0",
            "transformers_version": "4.0.0",
            "model_load_seconds": 0.3,
            "inference_seconds": 0.4,
            "total_seconds": 0.7,
        },
        "segments": [
            {"sequence": 1, "start_ms": 0, "end_ms": 500, "text": "ഒന്നാം വരി"},
            {"sequence": 2, "start_ms": 500, "end_ms": 1000, "text": "രണ്ടാം വരി"},
        ],
    }


def _runner(response_mutator=None, captured: dict | None = None):
    def run(command, **kwargs):
        if captured is not None:
            captured.update(command=command, kwargs=kwargs, directory=Path(command[3]).parent)
        request = json.loads(Path(command[3]).read_text(encoding="utf-8"))
        response = _response(request)
        if response_mutator is not None:
            response_mutator(response)
        Path(command[5]).write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "ignored stdout", "")

    return run


def test_hybrid_preserves_complete_dual_evidence_and_honest_wall_time(tmp_path: Path) -> None:
    captured: dict = {}
    ticks = iter((10.0, 12.0, 15.0, 20.0))
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path),
        FakeWhisperProvider(),
        process_runner=_runner(captured=captured),
        request_id_factory=lambda: "00000000-0000-0000-0000-000000000001",
        perf_counter=lambda: next(ticks),
    )
    result = provider.transcribe(_source(tmp_path))

    assert [item.text for item in result.segments] == ["ഒന്നാം വരി", "രണ്ടാം വരി"]
    assert [(item.start_ms, item.end_ms) for item in result.segments] == [(0, 500), (500, 1000)]
    assert all(item.words == () and item.avg_logprob is None for item in result.segments)
    assert result.multilingual is False
    assert result.word_timestamps is True
    assert result.device == "whisper:cpu|indic:cpu"
    assert result.inference_seconds == 10.0
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["env"]["HF_HUB_OFFLINE"] == "1"
    assert not captured["directory"].exists()
    evidence = result.raw_output()
    whisper = evidence["faster_whisper"]
    assert whisper["provider_mode"] == "local_faster_whisper"
    assert whisper["word_timestamps"] is True
    assert whisper["raw_output"]["segments"][0]["text"] == "raw English timing"
    assert evidence["indicconformer"]["raw_segments"][0]["text"] == "ഒന്നാം വരി"
    assert evidence["subprocess"] == {"exit_code": 0, "timeout_seconds": 90, "wall_seconds": 3.0}
    assert evidence["hybrid"] == {"wall_seconds": 10.0}


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda payload: payload.update(request_id="wrong"), "local_hybrid_request_mismatch"),
        (lambda payload: payload["segments"].pop(), "local_hybrid_segment_count_mismatch"),
        (
            lambda payload: payload["segments"][0].update(sequence=9),
            "local_hybrid_sequence_mismatch",
        ),
        (
            lambda payload: payload["segments"][0].update(end_ms=499),
            "local_hybrid_timestamp_mismatch",
        ),
        (lambda payload: payload["segments"][0].update(text=""), "local_hybrid_empty_segment"),
        (lambda payload: payload["segments"][0].update(text="\ufffd"), "local_hybrid_unsafe_text"),
    ],
)
def test_hybrid_reports_precise_response_failure_codes(tmp_path: Path, mutate, code: str) -> None:
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path), FakeWhisperProvider(), process_runner=_runner(mutate)
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))
    assert error.value.code == code


def test_manifest_preflight_fails_before_whisper(tmp_path: Path) -> None:
    whisper = FakeWhisperProvider()
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path, manifest=False), whisper, process_runner=_runner()
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))
    assert error.value.code == "local_hybrid_model_manifest_missing"
    assert whisper.calls == 0


@pytest.mark.parametrize("payload", [{"wrong": True}, {"schema_version": 2}])
def test_manifest_mismatch_fails_before_whisper(tmp_path: Path, payload: dict) -> None:
    configuration = _configuration(tmp_path)
    (configuration.model_path / "shravya-model-manifest.json").write_text(json.dumps(payload))
    whisper = FakeWhisperProvider()
    provider = LocalMalayalamHybridTranscriptionProvider(
        configuration, whisper, process_runner=_runner()
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))
    assert error.value.code == "local_hybrid_model_mismatch"
    assert whisper.calls == 0


@pytest.mark.parametrize(
    ("segments", "code"),
    [
        ((), "local_hybrid_whisper_empty"),
        (
            (
                ProviderSegment(500, 1000, "one", sequence=1),
                ProviderSegment(400, 500, "two", sequence=2),
            ),
            "local_hybrid_invalid_whisper_segments",
        ),
        ((ProviderSegment(0, 500, "one", sequence=2),), "local_hybrid_invalid_whisper_segments"),
    ],
)
def test_hybrid_rejects_invalid_whisper_evidence(tmp_path: Path, segments, code: str) -> None:
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path), FakeWhisperProvider(segments), process_runner=_runner()
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))
    assert error.value.code == code


def test_hybrid_reclassifies_whisper_execution_failures_without_running_subprocess(
    tmp_path: Path,
) -> None:
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("subprocess runner must not be called")

    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path), FailingWhisperProvider(), process_runner=must_not_run
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))

    assert error.value.code == "local_hybrid_whisper_failed"
    assert error.value.message_key == "audio.local_hybrid_whisper_failed"
    assert isinstance(error.value.__cause__, DomainError)
    assert error.value.__cause__.code == "local_stt_model_load_failed"


@pytest.mark.parametrize(
    ("runner", "code"),
    [
        (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("not executable")),
            "local_hybrid_process_start_failed",
        ),
        (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("runner", 90)
            ),
            "local_hybrid_timeout",
        ),
        (
            lambda command, **_kwargs: subprocess.CompletedProcess(command, 2),
            "local_hybrid_process_failed",
        ),
    ],
)
def test_hybrid_reports_precise_process_failure_codes(tmp_path: Path, runner, code: str) -> None:
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path), FakeWhisperProvider(), process_runner=runner
    )
    with pytest.raises(DomainError) as error:
        provider.transcribe(_source(tmp_path))
    assert error.value.code == code


def test_child_environment_removes_token_keys_case_insensitively(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "one")
    monkeypatch.setenv("hf_token", "two")
    monkeypatch.setenv("Hugging_Face_Hub_Token", "three")
    parent_token = os.environ["HF_TOKEN"]
    captured: dict = {}
    provider = LocalMalayalamHybridTranscriptionProvider(
        _configuration(tmp_path), FakeWhisperProvider(), process_runner=_runner(captured=captured)
    )
    provider.transcribe(_source(tmp_path))
    environment = captured["kwargs"]["env"]
    assert not any(key.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"} for key in environment)
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_TOKEN"] == parent_token


def test_hybrid_and_local_whisper_caches_are_offline_distinct() -> None:
    clear_local_provider_cache_for_tests()
    clear_hybrid_provider_cache_for_tests()
    local = Settings(provider_mode=ProviderMode.LOCAL_FASTER_WHISPER)
    hybrid = Settings(provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID)
    first = hybrid_provider_for_settings(hybrid)
    second = hybrid_provider_for_settings(hybrid)
    local_provider = local_provider_for_settings(local)

    assert first is second
    assert first._configuration.whisper.local_files_only is True
    assert local_provider._configuration.local_files_only is False
    assert first._whisper_provider is not local_provider
