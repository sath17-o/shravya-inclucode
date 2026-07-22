from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import ProviderMode, Settings
from app.services.audio_workflow import parse_wav_metadata
from app.services.benchmarking import (
    academic_term_score,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    character_error_rate,
    counts_payload,
    normalize_metric_text,
    word_error_rate,
)
from app.services.transcription_provider import (
    LocalFasterWhisperTranscriptionProvider,
    LocalWhisperConfiguration,
    TranscriptionInput,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Run local faster-whisper evidence and metrics.")
    command.add_argument("--audio", required=True, type=Path)
    command.add_argument("--reference-text-file", type=Path)
    command.add_argument("--terms-file", type=Path)
    command.add_argument("--model", default="small")
    command.add_argument("--device", default="cpu")
    command.add_argument("--compute-type", default="int8")
    command.add_argument("--language", default="ml")
    command.add_argument("--multilingual", action=argparse.BooleanOptionalAction, default=True)
    command.add_argument("--beam-size", type=int, default=5)
    command.add_argument("--vad", action=argparse.BooleanOptionalAction, default=True)
    command.add_argument("--word-timestamps", action=argparse.BooleanOptionalAction, default=True)
    command.add_argument("--output-dir", required=True, type=Path)
    return command


def main(
    argv: list[str] | None = None,
    *,
    provider: LocalFasterWhisperTranscriptionProvider | None = None,
) -> int:
    args = parser().parse_args(argv)
    audio = args.audio.resolve()
    if not audio.is_file():
        print("The audio file could not be read.", file=sys.stderr)
        return 2
    data = audio.read_bytes()
    try:
        metadata = parse_wav_metadata(data)
        settings = Settings(
            provider_mode=ProviderMode.LOCAL_FASTER_WHISPER,
            whisper_model=args.model,
            whisper_device=args.device,
            whisper_compute_type=args.compute_type,
            whisper_language=args.language,
            whisper_multilingual=args.multilingual,
            whisper_beam_size=args.beam_size,
            whisper_vad=args.vad,
            whisper_word_timestamps=args.word_timestamps,
        )
        active_provider = provider or LocalFasterWhisperTranscriptionProvider(
            LocalWhisperConfiguration.from_settings(settings)
        )
        result = active_provider.transcribe(
            TranscriptionInput(
                source_sha256=hashlib.sha256(data).hexdigest(),
                source_duration_ms=metadata.duration_ms,
                audio_path=audio,
            )
        )
    except Exception:
        print("Local benchmark transcription could not be completed.", file=sys.stderr)
        return 1

    reference = (
        args.reference_text_file.read_text(encoding="utf-8")
        if args.reference_text_file is not None
        else None
    )
    terms = (
        [
            line.strip()
            for line in args.terms_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if args.terms_file is not None
        else []
    )
    hypothesis = " ".join(segment.text for segment in result.segments).strip()
    benchmark: dict[str, object] = {
        "run_timestamp_utc": datetime.now(UTC).isoformat(),
        "source_filename": audio.name,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "audio": {
            "format": metadata.audio_format,
            "sample_rate_hz": metadata.sample_rate_hz,
            "channel_count": metadata.channel_count,
            "sample_width_bits": metadata.sample_width_bits,
            "frame_count": metadata.frame_count,
            "duration_ms": metadata.duration_ms,
        },
        "provider": {
            "mode": result.provider_mode,
            "implementation": result.provider_implementation,
            "version": result.provider_version,
            "ctranslate2_version": result.ctranslate2_version,
            "model": result.model_identifier,
            "device": result.device,
            "compute_type": result.compute_type,
            "language_requested": result.language_requested,
            "language_detected": result.language_detected,
            "language_probability": result.language_probability,
            "multilingual": result.multilingual,
            "beam_size": result.beam_size,
            "vad_filter": result.vad_filter,
            "word_timestamps": result.word_timestamps,
        },
        "reference_text": reference,
        "raw_hypothesis_text": hypothesis,
        "normalized_reference": normalize_metric_text(reference) if reference is not None else None,
        "normalized_hypothesis": normalize_metric_text(hypothesis),
        "timing": {
            "model_load_seconds": result.model_load_seconds,
            "inference_seconds": result.inference_seconds,
            "total_seconds": (result.model_load_seconds or 0) + result.inference_seconds,
            "audio_duration_seconds": metadata.duration_ms / 1000,
            "real_time_factor": result.inference_seconds / (metadata.duration_ms / 1000),
        },
        "detected_language": {
            "value": result.language_detected,
            "probability": result.language_probability,
        },
        "timestamp_coverage": _timestamp_coverage(result, metadata.duration_ms),
        "native_provider_output": result.raw_output(),
    }
    if reference is not None:
        word_counts, wer = word_error_rate(reference, hypothesis)
        character_counts, cer = character_error_rate(reference, hypothesis)
        benchmark["metrics"] = {
            "reference_word_count": len(normalize_metric_text(reference).split()),
            "hypothesis_word_count": len(normalize_metric_text(hypothesis).split()),
            "word_errors": counts_payload(word_counts),
            "word_error_rate": wer,
            "reference_character_count": len(normalize_metric_text(reference)),
            "character_errors": counts_payload(character_counts),
            "character_error_rate": cer,
            "academic_terms": academic_term_score(hypothesis, terms),
        }
    else:
        benchmark["metrics"] = None

    output_dir = args.output_dir.resolve()
    atomic_write_text(output_dir / "raw-transcript.txt", hypothesis + "\n")
    atomic_write_json(output_dir / "raw-provider-output.json", result.raw_output())
    atomic_write_json(output_dir / "benchmark.json", benchmark)
    atomic_write_csv(output_dir / "benchmark.csv", benchmark)
    print("Local STT benchmark evidence written.")
    return 0


def _timestamp_coverage(result, duration_ms: int) -> float:
    intervals = sorted((segment.start_ms, segment.end_ms) for segment in result.segments)
    if not intervals or duration_ms <= 0:
        return 0.0
    covered = 0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            covered += end - start
            start, end = next_start, next_end
    return (covered + end - start) / duration_ms


if __name__ == "__main__":
    raise SystemExit(main())
