from __future__ import annotations

import json
import wave
from datetime import UTC, datetime
from pathlib import Path

from app.services.transcription_provider import ProviderSegment, ProviderTranscription
from scripts.benchmark_local_stt import main


class FakeLocalProvider:
    def transcribe(self, _source):
        return ProviderTranscription(
            segments=(
                ProviderSegment(
                    start_ms=0,
                    end_ms=1000,
                    text="ജലവും chlorophyll ഉം",
                ),
            ),
            provider_mode="local_faster_whisper",
            provider_implementation="local-faster-whisper",
            provider_version="1.2.1",
            ctranslate2_version="test",
            model_identifier="small",
            device="cpu",
            compute_type="int8",
            language_requested="ml",
            language_detected="ml",
            language_probability=0.8,
            multilingual=True,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            transcription_started_at=datetime.now(UTC),
            transcription_completed_at=datetime.now(UTC),
            model_load_seconds=0.1,
            inference_seconds=0.2,
        )


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * 16000)


def test_benchmark_runner_uses_injected_local_provider_and_writes_truthful_evidence(
    tmp_path,
) -> None:
    audio = tmp_path / "private-classroom.wav"
    reference = tmp_path / "reference.txt"
    terms = tmp_path / "terms.txt"
    output = tmp_path / "benchmark"
    _wav(audio)
    reference.write_text("ജലവും chlorophyll ഉം", encoding="utf-8")
    terms.write_text("chlorophyll\nwater\n", encoding="utf-8")

    exit_code = main(
        [
            "--audio",
            str(audio),
            "--reference-text-file",
            str(reference),
            "--terms-file",
            str(terms),
            "--output-dir",
            str(output),
        ],
        provider=FakeLocalProvider(),
    )

    assert exit_code == 0
    assert {
        "raw-transcript.txt",
        "raw-provider-output.json",
        "benchmark.json",
        "benchmark.csv",
    } == {path.name for path in output.iterdir()}
    benchmark = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
    assert benchmark["source_filename"] == "private-classroom.wav"
    assert str(audio) not in json.dumps(benchmark, ensure_ascii=False)
    assert benchmark["provider"]["implementation"] == "local-faster-whisper"
    assert benchmark["metrics"]["academic_terms"]["exact_hits"] == ["chlorophyll"]
    assert benchmark["timing"]["real_time_factor"] == 0.2
