"""Offline, standalone IndicConformer subprocess runner for Shravya."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any
from uuid import UUID

REQUEST_SCHEMA_VERSION = 1
RESPONSE_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
MODEL_ID = "ai4bharat/indic-conformer-600m-multilingual"
MODEL_REVISION = "e9b71b369c048e2c6b634d4c131061c34e441179"
LANGUAGE = "ml"
DECODER = "ctc"
MANIFEST_NAME = "shravya-model-manifest.json"
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "DO_NOT_TRACK": "1",
}


class RunnerError(ValueError):
    """Controlled contract failure; stdout is never a transcript-data channel."""


def _exact_keys(value: object, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise RunnerError(f"invalid_{name}")
    return value


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunnerError(f"invalid_{name}")
    if minimum is not None and value < minimum:
        raise RunnerError(f"invalid_{name}")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunnerError(f"invalid_{name}")
    return value.strip()


def validate_manifest(model_path: Path) -> None:
    manifest_path = model_path / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RunnerError("local_hybrid_model_manifest_missing")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunnerError("local_hybrid_model_mismatch") from error
    try:
        manifest = _exact_keys(
            payload,
            {"schema_version", "model_id", "revision", "language", "decoder"},
            "manifest",
        )
    except RunnerError as error:
        raise RunnerError("local_hybrid_model_mismatch") from error
    if (
        manifest["schema_version"] != MANIFEST_SCHEMA_VERSION
        or manifest["model_id"] != MODEL_ID
        or manifest["revision"] != MODEL_REVISION
        or manifest["language"] != LANGUAGE
        or manifest["decoder"] != DECODER
    ):
        raise RunnerError("local_hybrid_model_mismatch")


def validate_request(payload: object) -> dict[str, Any]:
    request = _exact_keys(
        payload, {"schema_version", "request_id", "audio", "model", "segments"}, "request"
    )
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise RunnerError("unsupported_request_schema")
    request_id = _string(request["request_id"], "request_id")
    try:
        UUID(request_id)
    except (ValueError, AttributeError) as error:
        raise RunnerError("invalid_request_id") from error
    audio = _exact_keys(request["audio"], {"path", "sha256", "duration_ms"}, "audio")
    audio["path"] = _string(audio["path"], "audio_path")
    if not Path(audio["path"]).is_absolute():
        raise RunnerError("invalid_audio_path")
    sha256 = _string(audio["sha256"], "audio_sha256")
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise RunnerError("invalid_audio_sha256")
    audio["sha256"] = sha256
    audio["duration_ms"] = _integer(audio["duration_ms"], "audio_duration", minimum=1)
    model = _exact_keys(
        request["model"],
        {
            "local_path",
            "expected_model_id",
            "expected_revision",
            "language",
            "decoder",
            "offline_only",
        },
        "model",
    )
    model["local_path"] = _string(model["local_path"], "model_path")
    if not Path(model["local_path"]).is_absolute():
        raise RunnerError("local_hybrid_model_mismatch")
    if (
        model["expected_model_id"] != MODEL_ID
        or model["expected_revision"] != MODEL_REVISION
        or model["language"] != LANGUAGE
        or model["decoder"] != DECODER
        or model["offline_only"] is not True
    ):
        raise RunnerError("local_hybrid_model_mismatch")
    if not isinstance(request["segments"], list) or not request["segments"]:
        raise RunnerError("invalid_segments")
    segments: list[dict[str, int]] = []
    previous_start = -1
    for position, item in enumerate(request["segments"], 1):
        segment = _exact_keys(item, {"sequence", "start_ms", "end_ms"}, "segment")
        sequence = _integer(segment["sequence"], "segment_sequence", minimum=1)
        start_ms = _integer(segment["start_ms"], "segment_start", minimum=0)
        end_ms = _integer(segment["end_ms"], "segment_end", minimum=1)
        if (
            sequence != position
            or end_ms <= start_ms
            or start_ms < previous_start
            or end_ms > audio["duration_ms"]
        ):
            raise RunnerError("invalid_segments")
        previous_start = start_ms
        segments.append({"sequence": sequence, "start_ms": start_ms, "end_ms": end_ms})
    return {"request_id": request_id, "audio": audio, "model": model, "segments": segments}


def validate_wav(audio: dict[str, Any], segments: list[dict[str, int]]) -> tuple[bytes, int]:
    path = Path(audio["path"])
    if not path.is_file():
        raise RunnerError("invalid_audio_path")
    if hashlib.sha256(path.read_bytes()).hexdigest() != audio["sha256"]:
        raise RunnerError("audio_sha_mismatch")
    try:
        with wave.open(str(path), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != 16000
                or source.getcomptype() != "NONE"
                or source.getnframes() <= 0
            ):
                raise RunnerError("unsupported_wav")
            frame_count = source.getnframes()
            frames = source.readframes(frame_count)
    except (wave.Error, OSError) as error:
        raise RunnerError("unsupported_wav") from error
    duration_ms = round(frame_count * 1000 / 16000)
    if abs(duration_ms - audio["duration_ms"]) > 1 or any(
        item["end_ms"] > duration_ms for item in segments
    ):
        raise RunnerError("audio_duration_mismatch")
    return frames, frame_count


def _lazy_model(model_path: Path):
    try:
        import torch
        from transformers import AutoConfig, AutoModel
    except ImportError as error:
        raise RunnerError("hybrid_runtime_dependency_unavailable") from error
    started = time.perf_counter()
    config = AutoConfig.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        local_files_only=True,
    )
    config.ts_folder = str(model_path)
    model = AutoModel.from_config(
        config,
        trust_remote_code=True,
    )
    if callable(getattr(model, "eval", None)):
        model.eval()
    return torch, model, time.perf_counter() - started


def _model_text(
    model: Any,
    torch: Any,
    frames: bytes,
    frame_count: int,
    start_ms: int,
    end_ms: int,
) -> str:
    start_sample = start_ms * 16
    requested_end_sample = end_ms * 16
    if start_sample >= frame_count:
        raise RunnerError("segment_out_of_range")
    if requested_end_sample > frame_count:
        # Millisecond timestamps are rounded, while the physical PCM frame count is exact.
        # Clamp only the final rounding overrun; no samples are invented.
        if requested_end_sample - frame_count > 16:
            raise RunnerError("segment_out_of_range")
        end_sample = frame_count
    else:
        end_sample = requested_end_sample
    if end_sample <= start_sample:
        raise RunnerError("segment_out_of_range")
    try:
        samples = struct.unpack(
            f"<{end_sample - start_sample}h", frames[start_sample * 2 : end_sample * 2]
        )
    except (struct.error, ValueError) as error:
        raise RunnerError("segment_audio_invalid") from error
    waveform = torch.tensor(samples, dtype=torch.float32).unsqueeze(0) / 32768.0
    if not callable(model):
        raise RunnerError("hybrid_model_contract_invalid")
    with torch.no_grad():
        result = model(waveform, LANGUAGE, DECODER)
    if isinstance(result, (list, tuple)):
        result = result[0] if result else ""
    text = _string(result, "segment_text")
    if "\ufffd" in text:
        raise RunnerError("unsafe_segment_text")
    return text


def run(request: dict[str, Any]) -> dict[str, Any]:
    frames, frame_count = validate_wav(request["audio"], request["segments"])
    model_path = Path(request["model"]["local_path"])
    if not model_path.is_dir():
        raise RunnerError("local_hybrid_model_missing")
    validate_manifest(model_path)
    torch, model, model_load_seconds = _lazy_model(model_path)
    inference_started = time.perf_counter()
    segments = [
        {
            **item,
            "text": _model_text(
                model, torch, frames, frame_count, item["start_ms"], item["end_ms"]
            ),
        }
        for item in request["segments"]
    ]
    inference_seconds = time.perf_counter() - inference_started
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "request_id": request["request_id"],
        "status": "ok",
        "model": {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "language": LANGUAGE,
            "decoder": DECODER,
            "offline": True,
        },
        "runtime": {
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "torch_version": str(torch.__version__),
            "transformers_version": __import__("transformers").__version__,
            "model_load_seconds": model_load_seconds,
            "inference_seconds": inference_seconds,
            "total_seconds": model_load_seconds + inference_seconds,
        },
        "segments": segments,
    }


def write_response(path: Path, response: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(response, temporary, ensure_ascii=False, separators=(",", ":"))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args(argv)
    os.environ.update(OFFLINE_ENV)
    os.environ.pop("HF_TOKEN", None)
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
    try:
        request = validate_request(json.loads(arguments.input.read_text(encoding="utf-8")))
        write_response(arguments.output, run(request))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RunnerError):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
