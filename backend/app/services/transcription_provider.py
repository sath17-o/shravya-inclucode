from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from app.contracts.teacher_review import DomainError
from app.core.config import ProviderMode, Settings

DETERMINISTIC_DEMO_PROVIDER = "shravya-deterministic-demo"
LOCAL_FASTER_WHISPER_PROVIDER = "local-faster-whisper"
LOCAL_FASTER_WHISPER_PROVENANCE = (
    "Local speech recognition processed on this device; teacher review required."
)


@dataclass(frozen=True, slots=True)
class TranscriptionInput:
    source_sha256: str
    source_duration_ms: int
    audio_path: Path


@dataclass(frozen=True, slots=True)
class ProviderWord:
    start_ms: int
    end_ms: int
    text: str
    probability: float | None


@dataclass(frozen=True, slots=True)
class ProviderSegment:
    start_ms: int
    end_ms: int
    text: str
    sequence: int | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None
    temperature: float | None = None
    words: tuple[ProviderWord, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderTranscription:
    segments: tuple[ProviderSegment, ...]
    provider_mode: str
    provider_implementation: str
    provider_version: str | None
    ctranslate2_version: str | None
    model_identifier: str
    device: str
    compute_type: str
    language_requested: str
    language_detected: str | None
    language_probability: float | None
    multilingual: bool
    beam_size: int
    vad_filter: bool
    word_timestamps: bool
    transcription_started_at: datetime
    transcription_completed_at: datetime
    model_load_seconds: float | None
    inference_seconds: float

    def raw_output(self) -> dict[str, object]:
        return {
            "segments": [
                {
                    "sequence": index,
                    "start_ms": item.start_ms,
                    "end_ms": item.end_ms,
                    "text": item.text,
                    "avg_logprob": item.avg_logprob,
                    "no_speech_prob": item.no_speech_prob,
                    "compression_ratio": item.compression_ratio,
                    "temperature": item.temperature,
                    "words": [
                        {
                            "start_ms": word.start_ms,
                            "end_ms": word.end_ms,
                            "text": word.text,
                            "probability": word.probability,
                        }
                        for word in item.words
                    ],
                }
                for index, item in enumerate(self.segments, 1)
            ],
            "detected_language": self.language_detected,
            "detected_language_probability": self.language_probability,
        }


class TranscriptionProvider(Protocol):
    def transcribe(self, source: TranscriptionInput) -> ProviderTranscription | None: ...


class DeterministicDemoTranscriptionProvider:
    """Maps only the committed fixture; unknown audio is deliberately not transcribed."""

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path

    def transcribe(
        self, source: TranscriptionInput | str
    ) -> ProviderTranscription | tuple[ProviderSegment, ...] | None:
        manifest = self._manifest()
        source_sha256 = source if isinstance(source, str) else source.source_sha256
        if source_sha256 != manifest["sha256"]:
            return None
        now = datetime.now().astimezone()
        segments = tuple(
            ProviderSegment(
                start_ms=int(item["start_ms"]),
                end_ms=int(item["end_ms"]),
                text=str(item["text"]),
                sequence=int(item["sequence"]),
            )
            for item in manifest["transcript_segments"]
        )
        if isinstance(source, str):
            return segments
        return ProviderTranscription(
            segments=segments,
            provider_mode=ProviderMode.DETERMINISTIC_DEMO.value,
            provider_implementation=DETERMINISTIC_DEMO_PROVIDER,
            provider_version=str(manifest["provider_version"]),
            ctranslate2_version=None,
            model_identifier="bundled-fixture-map",
            device="offline",
            compute_type="not-applicable",
            language_requested="ml",
            language_detected="ml",
            language_probability=None,
            multilingual=True,
            beam_size=0,
            vad_filter=False,
            word_timestamps=False,
            transcription_started_at=now,
            transcription_completed_at=now,
            model_load_seconds=None,
            inference_seconds=0.0,
        )

    def matches_fixture_sha(self, sha256: str) -> bool:
        return sha256 == self._manifest()["sha256"]

    def _manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class LocalWhisperConfiguration:
    model: str
    device: str
    compute_type: str
    language: str
    multilingual: bool
    beam_size: int
    vad_filter: bool
    word_timestamps: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> LocalWhisperConfiguration:
        return cls(
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            language=settings.whisper_language,
            multilingual=settings.whisper_multilingual,
            beam_size=settings.whisper_beam_size,
            vad_filter=settings.whisper_vad,
            word_timestamps=settings.whisper_word_timestamps,
        )


class LocalFasterWhisperTranscriptionProvider:
    """Lazy, locally executed faster-whisper adapter with injectable model loading."""

    def __init__(
        self,
        configuration: LocalWhisperConfiguration,
        *,
        model_loader: Callable[[LocalWhisperConfiguration], Any] | None = None,
        version_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        self._configuration = configuration
        self._model_loader = model_loader or self._load_model
        self._version_lookup = version_lookup or self._package_version
        self._lock = Lock()
        self._model: Any | None = None

    def transcribe(self, source: TranscriptionInput) -> ProviderTranscription:
        model, model_load_seconds = self._model_instance()
        started_at = datetime.now().astimezone()
        inference_started = time.perf_counter()
        try:
            generated_segments, info = model.transcribe(
                str(source.audio_path),
                task="transcribe",
                language=self._configuration.language,
                beam_size=self._configuration.beam_size,
                temperature=0,
                word_timestamps=self._configuration.word_timestamps,
                vad_filter=self._configuration.vad_filter,
                condition_on_previous_text=False,
            )
            segments = tuple(self._segment(item) for item in generated_segments)
        except DomainError:
            raise
        except (KeyboardInterrupt, InterruptedError) as error:
            raise DomainError(
                "local_stt_interrupted", "audio.local_stt_interrupted", "conflict"
            ) from error
        except Exception as error:
            raise DomainError(
                "local_stt_inference_failed", "audio.local_stt_inference_failed", "validation"
            ) from error
        inference_seconds = time.perf_counter() - inference_started
        completed_at = datetime.now().astimezone()
        if not segments or not " ".join(item.text for item in segments).strip():
            raise DomainError(
                "local_stt_empty_transcript", "audio.local_stt_empty_transcript", "validation"
            )
        language_probability = getattr(info, "language_probability", None)
        if language_probability is not None:
            language_probability = self._probability(language_probability, "language")
        return ProviderTranscription(
            segments=segments,
            provider_mode=ProviderMode.LOCAL_FASTER_WHISPER.value,
            provider_implementation=LOCAL_FASTER_WHISPER_PROVIDER,
            provider_version=self._version_lookup("faster-whisper"),
            ctranslate2_version=self._version_lookup("ctranslate2"),
            model_identifier=self._configuration.model,
            device=self._configuration.device,
            compute_type=self._configuration.compute_type,
            language_requested=self._configuration.language,
            language_detected=self._optional_string(getattr(info, "language", None)),
            language_probability=language_probability,
            multilingual=self._configuration.multilingual,
            beam_size=self._configuration.beam_size,
            vad_filter=self._configuration.vad_filter,
            word_timestamps=self._configuration.word_timestamps,
            transcription_started_at=started_at,
            transcription_completed_at=completed_at,
            model_load_seconds=model_load_seconds,
            inference_seconds=inference_seconds,
        )

    def _model_instance(self) -> tuple[Any, float | None]:
        if self._model is not None:
            return self._model, 0.0
        with self._lock:
            if self._model is not None:
                return self._model, 0.0
            started = time.perf_counter()
            try:
                model = self._model_loader(self._configuration)
            except DomainError:
                raise
            except Exception as error:
                raise DomainError(
                    "local_stt_model_load_failed", "audio.local_stt_model_load_failed", "validation"
                ) from error
            if model is None or not callable(getattr(model, "transcribe", None)):
                raise DomainError(
                    "local_stt_malformed_model", "audio.local_stt_malformed_model", "validation"
                )
            self._model = model
            return model, time.perf_counter() - started

    @staticmethod
    def _load_model(configuration: LocalWhisperConfiguration) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise DomainError(
                "local_stt_dependency_unavailable",
                "audio.local_stt_dependency_unavailable",
                "validation",
            ) from error
        return WhisperModel(
            configuration.model,
            device=configuration.device,
            compute_type=configuration.compute_type,
        )

    @staticmethod
    def _package_version(package: str) -> str | None:
        try:
            return version(package)
        except PackageNotFoundError:
            return None

    @classmethod
    def _segment(cls, item: Any) -> ProviderSegment:
        try:
            start_ms = cls._milliseconds(getattr(item, "start"))
            end_ms = cls._milliseconds(getattr(item, "end"))
            text = cls._optional_string(getattr(item, "text"))
        except (TypeError, ValueError) as error:
            raise DomainError(
                "local_stt_malformed_result", "audio.local_stt_malformed_result", "validation"
            ) from error
        if start_ms < 0 or end_ms <= start_ms or not text:
            raise DomainError(
                "local_stt_malformed_result", "audio.local_stt_malformed_result", "validation"
            )
        words = tuple(cls._word(word) for word in (getattr(item, "words", None) or ()))
        return ProviderSegment(
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            avg_logprob=cls._optional_float(getattr(item, "avg_logprob", None)),
            no_speech_prob=cls._optional_float(getattr(item, "no_speech_prob", None)),
            compression_ratio=cls._optional_float(getattr(item, "compression_ratio", None)),
            temperature=cls._optional_float(getattr(item, "temperature", None)),
            words=words,
        )

    @classmethod
    def _word(cls, item: Any) -> ProviderWord:
        try:
            start_ms = cls._milliseconds(getattr(item, "start"))
            end_ms = cls._milliseconds(getattr(item, "end"))
            text = cls._optional_string(getattr(item, "word"))
        except (TypeError, ValueError) as error:
            raise DomainError(
                "local_stt_malformed_result", "audio.local_stt_malformed_result", "validation"
            ) from error
        if start_ms < 0 or end_ms < start_ms or not text:
            raise DomainError(
                "local_stt_malformed_result", "audio.local_stt_malformed_result", "validation"
            )
        probability = getattr(item, "probability", None)
        return ProviderWord(
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            probability=cls._probability(probability, "word") if probability is not None else None,
        )

    @staticmethod
    def _milliseconds(value: Any) -> int:
        return round(float(value) * 1000)

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _probability(value: Any, field: str) -> float:
        probability = float(value)
        if not 0 <= probability <= 1:
            raise DomainError(
                "local_stt_malformed_result", f"audio.local_stt_malformed_{field}", "validation"
            )
        return probability


_shared_provider_lock = Lock()
_shared_local_providers: dict[
    LocalWhisperConfiguration, LocalFasterWhisperTranscriptionProvider
] = {}


def local_provider_for_settings(settings: Settings) -> LocalFasterWhisperTranscriptionProvider:
    configuration = LocalWhisperConfiguration.from_settings(settings)
    with _shared_provider_lock:
        provider = _shared_local_providers.get(configuration)
        if provider is None:
            provider = LocalFasterWhisperTranscriptionProvider(configuration)
            _shared_local_providers[configuration] = provider
        return provider


def provider_for_settings(settings: Settings, manifest_path: Path) -> TranscriptionProvider:
    if settings.provider_mode is ProviderMode.DETERMINISTIC_DEMO:
        return DeterministicDemoTranscriptionProvider(manifest_path)
    if settings.provider_mode is ProviderMode.LOCAL_FASTER_WHISPER:
        return local_provider_for_settings(settings)
    raise DomainError("provider_mode_invalid", "audio.provider_mode_invalid", "validation")


def clear_local_provider_cache_for_tests() -> None:
    """A narrow test hook; application callers only use the configuration factory."""

    with _shared_provider_lock:
        _shared_local_providers.clear()


def raw_output_json(result: ProviderTranscription) -> str:
    return json.dumps(
        result.raw_output(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
