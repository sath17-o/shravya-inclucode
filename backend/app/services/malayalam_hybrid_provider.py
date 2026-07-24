"""Offline Malayalam-script drafting over locally timed faster-whisper evidence."""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from app.contracts.teacher_review import DomainError
from app.core.config import ProviderMode, Settings
from app.services.transcription_provider import (
    LocalFasterWhisperTranscriptionProvider,
    LocalWhisperConfiguration,
    ProviderSegment,
    ProviderTranscription,
    TranscriptionInput,
    local_provider_for_configuration,
)

LOCAL_MALAYALAM_HYBRID_PROVIDER = "local-malayalam-hybrid"
LOCAL_MALAYALAM_HYBRID_VERSION = "phase-4c5"
INDICCONFORMER_IMPLEMENTATION = "ai4bharat-indicconformer"
INDICCONFORMER_MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
INDICCONFORMER_REVISION = "e9b71b369c048e2c6b634d4c131061c34e441179"
INDICCONFORMER_LANGUAGE = "ml"
INDICCONFORMER_DECODER = "ctc"
MANIFEST_NAME = "shravya-model-manifest.json"
LOCAL_MALAYALAM_HYBRID_PROVENANCE = (
    "Local hybrid speech recognition: faster-whisper supplied speech boundaries and "
    "timestamp evidence; AI4Bharat IndicConformer supplied Malayalam-script draft text. "
    "Teacher review required."
)
_REQUEST_SCHEMA_VERSION = 1
_RESPONSE_SCHEMA_VERSION = 1
_MANIFEST = {
    "schema_version": 1,
    "model_id": INDICCONFORMER_MODEL_ID,
    "revision": INDICCONFORMER_REVISION,
    "language": INDICCONFORMER_LANGUAGE,
    "decoder": INDICCONFORMER_DECODER,
}
_RUNNER_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "DO_NOT_TRACK": "1",
}
_TOKEN_ENVIRONMENT_KEYS = {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}


@dataclass(frozen=True, slots=True)
class HybridConfiguration:
    python_executable: Path
    runner_script: Path
    model_path: Path
    timeout_seconds: int
    whisper: LocalWhisperConfiguration

    @classmethod
    def from_settings(cls, settings: Settings) -> HybridConfiguration:
        return cls(
            python_executable=settings.hybrid_python_executable,
            runner_script=settings.hybrid_runner_script,
            model_path=settings.hybrid_model_path,
            timeout_seconds=settings.hybrid_timeout_seconds,
            whisper=replace(
                LocalWhisperConfiguration.from_settings(settings), local_files_only=True
            ),
        )


class LocalMalayalamHybridTranscriptionProvider:
    """Runs only local processes and preserves both source evidence streams."""

    def __init__(
        self,
        configuration: HybridConfiguration,
        whisper_provider: LocalFasterWhisperTranscriptionProvider,
        *,
        process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        request_id_factory: Callable[[], str] = lambda: str(uuid4()),
        perf_counter: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._configuration = configuration
        self._whisper_provider = whisper_provider
        self._process_runner = process_runner
        self._request_id_factory = request_id_factory
        self._perf_counter = perf_counter

    def transcribe(self, source: TranscriptionInput) -> ProviderTranscription:
        wall_started = self._perf_counter()
        started_at = datetime.now().astimezone()
        self._validate_runtime_files()
        whisper = self._whisper(source)
        request_id = self._request_id_factory()
        request = self._request(source, whisper, request_id)
        response, process_seconds = self._run_runner(request)
        drafted_segments, runtime = self._validate_response(response, request, source, whisper)
        completed_at = datetime.now().astimezone()
        hybrid_wall_seconds = self._perf_counter() - wall_started
        hybrid_segments = tuple(
            ProviderSegment(
                sequence=index,
                start_ms=timing.start_ms,
                end_ms=timing.end_ms,
                text=text,
                avg_logprob=None,
                no_speech_prob=None,
                compression_ratio=None,
                temperature=None,
                words=(),
            )
            for index, (timing, text) in enumerate(zip(whisper.segments, drafted_segments), 1)
        )
        return ProviderTranscription(
            segments=hybrid_segments,
            provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID.value,
            provider_implementation=LOCAL_MALAYALAM_HYBRID_PROVIDER,
            provider_version=LOCAL_MALAYALAM_HYBRID_VERSION,
            ctranslate2_version=whisper.ctranslate2_version,
            model_identifier=(
                f"faster-whisper:{whisper.model_identifier}|"
                f"indic-conformer:{INDICCONFORMER_REVISION}"
            ),
            device=f"whisper:{whisper.device}|indic:cpu",
            compute_type=f"whisper:{whisper.compute_type}|indic:float32",
            language_requested=INDICCONFORMER_LANGUAGE,
            language_detected=whisper.language_detected,
            language_probability=whisper.language_probability,
            multilingual=whisper.multilingual,
            beam_size=whisper.beam_size,
            vad_filter=whisper.vad_filter,
            word_timestamps=whisper.word_timestamps,
            transcription_started_at=started_at,
            transcription_completed_at=completed_at,
            model_load_seconds=self._combined_seconds(
                whisper.model_load_seconds, runtime["model_load_seconds"]
            ),
            inference_seconds=hybrid_wall_seconds,
            raw_evidence_payload={
                "schema_version": 2,
                "pipeline": "local_malayalam_hybrid",
                "source": {
                    "sha256": source.source_sha256,
                    "duration_ms": source.source_duration_ms,
                },
                "faster_whisper": self._whisper_evidence(whisper),
                "indicconformer": {
                    "provider_implementation": INDICCONFORMER_IMPLEMENTATION,
                    **_MANIFEST,
                    "offline": True,
                    "runtime": runtime,
                    "raw_segments": response["segments"],
                },
                "subprocess": {
                    "exit_code": 0,
                    "timeout_seconds": self._configuration.timeout_seconds,
                    "wall_seconds": process_seconds,
                },
                "hybrid": {"wall_seconds": hybrid_wall_seconds},
                "hybrid_review_segments": [
                    {
                        "sequence": segment.sequence,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "text": segment.text,
                    }
                    for segment in hybrid_segments
                ],
            },
        )

    def _validate_runtime_files(self) -> None:
        if not self._configuration.python_executable.is_file():
            self._error("local_hybrid_python_missing")
        if not self._configuration.runner_script.is_file():
            self._error("local_hybrid_runner_missing")
        if not self._configuration.model_path.is_dir():
            self._error("local_hybrid_model_missing")
        manifest_path = self._configuration.model_path / MANIFEST_NAME
        if not manifest_path.is_file():
            self._error("local_hybrid_model_manifest_missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._error("local_hybrid_model_mismatch")
        if manifest != _MANIFEST:
            self._error("local_hybrid_model_mismatch")

    def _whisper(self, source: TranscriptionInput) -> ProviderTranscription:
        try:
            result = self._whisper_provider.transcribe(source)
        except DomainError as error:
            raise DomainError(
                "local_hybrid_whisper_failed",
                "audio.local_hybrid_whisper_failed",
                "validation",
            ) from error
        if not result.segments:
            self._error("local_hybrid_whisper_empty")
        previous_start = -1
        for position, item in enumerate(result.segments, 1):
            if (
                not item.text.strip()
                or item.start_ms < 0
                or item.end_ms <= item.start_ms
                or item.end_ms > source.source_duration_ms
                or item.start_ms < previous_start
                or (item.sequence is not None and item.sequence != position)
            ):
                self._error("local_hybrid_invalid_whisper_segments")
            previous_start = item.start_ms
        return result

    def _request(
        self, source: TranscriptionInput, whisper: ProviderTranscription, request_id: str
    ) -> dict[str, object]:
        if not request_id.strip():
            self._error("local_hybrid_output_invalid")
        return {
            "schema_version": _REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "audio": {
                "path": str(source.audio_path.resolve()),
                "sha256": source.source_sha256,
                "duration_ms": source.source_duration_ms,
            },
            "model": {
                "local_path": str(self._configuration.model_path.resolve()),
                "expected_model_id": INDICCONFORMER_MODEL_ID,
                "expected_revision": INDICCONFORMER_REVISION,
                "language": INDICCONFORMER_LANGUAGE,
                "decoder": INDICCONFORMER_DECODER,
                "offline_only": True,
            },
            "segments": [
                {"sequence": index, "start_ms": item.start_ms, "end_ms": item.end_ms}
                for index, item in enumerate(whisper.segments, 1)
            ],
        }

    def _run_runner(self, request: dict[str, object]) -> tuple[dict[str, Any], float]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() not in _TOKEN_ENVIRONMENT_KEYS
        }
        environment.update(_RUNNER_ENV)
        with tempfile.TemporaryDirectory(prefix="shravya-hybrid-") as directory:
            directory_path = Path(directory)
            request_path = directory_path / "request.json"
            response_path = directory_path / "response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            process_started = self._perf_counter()
            try:
                completed = self._process_runner(
                    [
                        str(self._configuration.python_executable),
                        str(self._configuration.runner_script),
                        "--input",
                        str(request_path),
                        "--output",
                        str(response_path),
                    ],
                    shell=False,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self._configuration.timeout_seconds,
                    env=environment,
                )
            except subprocess.TimeoutExpired as error:
                raise DomainError(
                    "local_hybrid_timeout", "audio.local_hybrid_timeout", "validation"
                ) from error
            except OSError as error:
                raise DomainError(
                    "local_hybrid_process_start_failed",
                    "audio.local_hybrid_process_start_failed",
                    "validation",
                ) from error
            process_seconds = self._perf_counter() - process_started
            if completed.returncode != 0:
                self._error("local_hybrid_process_failed")
            if not response_path.is_file():
                self._error("local_hybrid_output_missing")
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DomainError(
                    "local_hybrid_output_invalid", "audio.local_hybrid_output_invalid", "validation"
                ) from error
        return response, process_seconds

    def _validate_response(
        self,
        response: object,
        request: dict[str, object],
        source: TranscriptionInput,
        whisper: ProviderTranscription,
    ) -> tuple[tuple[str, ...], dict[str, float | str]]:
        expected = {"schema_version", "request_id", "status", "model", "runtime", "segments"}
        if not isinstance(response, dict) or set(response) != expected:
            self._error("local_hybrid_output_invalid")
        if response["schema_version"] != _RESPONSE_SCHEMA_VERSION or response["status"] != "ok":
            self._error("local_hybrid_output_invalid")
        if response["request_id"] != request["request_id"]:
            self._error("local_hybrid_request_mismatch")
        if response["model"] != {
            "model_id": INDICCONFORMER_MODEL_ID,
            "revision": INDICCONFORMER_REVISION,
            "language": INDICCONFORMER_LANGUAGE,
            "decoder": INDICCONFORMER_DECODER,
            "offline": True,
        }:
            self._error("local_hybrid_model_response_mismatch")
        runtime = self._runtime(response["runtime"])
        raw_segments = response["segments"]
        if not isinstance(raw_segments, list):
            self._error("local_hybrid_output_invalid")
        if len(raw_segments) != len(whisper.segments):
            self._error("local_hybrid_segment_count_mismatch")
        text: list[str] = []
        for sequence, (item, timing) in enumerate(zip(raw_segments, whisper.segments), 1):
            if not isinstance(item, dict) or set(item) != {
                "sequence",
                "start_ms",
                "end_ms",
                "text",
            }:
                self._error("local_hybrid_output_invalid")
            if item["sequence"] != sequence:
                self._error("local_hybrid_sequence_mismatch")
            if item["start_ms"] != timing.start_ms or item["end_ms"] != timing.end_ms:
                self._error("local_hybrid_timestamp_mismatch")
            value = item["text"]
            if not isinstance(value, str) or not value.strip():
                self._error("local_hybrid_empty_segment")
            if "\ufffd" in value:
                self._error("local_hybrid_unsafe_text")
            if timing.end_ms > source.source_duration_ms:
                self._error("local_hybrid_timestamp_mismatch")
            text.append(value.strip())
        return tuple(text), runtime

    @staticmethod
    def _runtime(value: object) -> dict[str, float | str]:
        expected = {
            "python_version",
            "torch_version",
            "transformers_version",
            "model_load_seconds",
            "inference_seconds",
            "total_seconds",
        }
        if not isinstance(value, dict) or set(value) != expected:
            LocalMalayalamHybridTranscriptionProvider._error("local_hybrid_output_invalid")
        result: dict[str, float | str] = {}
        for key in ("python_version", "torch_version", "transformers_version"):
            item = value[key]
            if not isinstance(item, str) or not item.strip():
                LocalMalayalamHybridTranscriptionProvider._error("local_hybrid_output_invalid")
            result[key] = item
        for key in ("model_load_seconds", "inference_seconds", "total_seconds"):
            item = value[key]
            if (
                isinstance(item, bool)
                or not isinstance(item, (float, int))
                or not math.isfinite(item)
                or item < 0
            ):
                LocalMalayalamHybridTranscriptionProvider._error("local_hybrid_output_invalid")
            result[key] = float(item)
        return result

    @staticmethod
    def _combined_seconds(first: float | None, second: float | str) -> float | None:
        return None if first is None else first + float(second)

    @staticmethod
    def _whisper_evidence(whisper: ProviderTranscription) -> dict[str, object]:
        return {
            "provider_mode": whisper.provider_mode,
            "provider_implementation": whisper.provider_implementation,
            "provider_version": whisper.provider_version,
            "ctranslate2_version": whisper.ctranslate2_version,
            "model_identifier": whisper.model_identifier,
            "device": whisper.device,
            "compute_type": whisper.compute_type,
            "language_requested": whisper.language_requested,
            "language_detected": whisper.language_detected,
            "language_probability": whisper.language_probability,
            "multilingual": whisper.multilingual,
            "beam_size": whisper.beam_size,
            "vad_filter": whisper.vad_filter,
            "word_timestamps": whisper.word_timestamps,
            "transcription_started_at": whisper.transcription_started_at.isoformat(),
            "transcription_completed_at": whisper.transcription_completed_at.isoformat(),
            "model_load_seconds": whisper.model_load_seconds,
            "inference_seconds": whisper.inference_seconds,
            "raw_output": whisper.raw_output(),
        }

    @staticmethod
    def _error(code: str) -> None:
        raise DomainError(code, f"audio.{code}", "validation")


_shared_hybrid_lock = Lock()
_shared_hybrid_providers: dict[HybridConfiguration, LocalMalayalamHybridTranscriptionProvider] = {}


def hybrid_provider_for_settings(settings: Settings) -> LocalMalayalamHybridTranscriptionProvider:
    configuration = HybridConfiguration.from_settings(settings)
    with _shared_hybrid_lock:
        provider = _shared_hybrid_providers.get(configuration)
        if provider is None:
            whisper = local_provider_for_configuration(configuration.whisper)
            provider = LocalMalayalamHybridTranscriptionProvider(configuration, whisper)
            _shared_hybrid_providers[configuration] = provider
        return provider


def clear_hybrid_provider_cache_for_tests() -> None:
    with _shared_hybrid_lock:
        _shared_hybrid_providers.clear()
