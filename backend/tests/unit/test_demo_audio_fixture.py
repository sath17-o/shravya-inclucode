import hashlib
import json
import wave
from pathlib import Path

from app.services.audio_workflow import DeterministicDemoTranscriptionProvider
from app.services.transcript_provenance import (
    DETERMINISTIC_DEMO_PROVENANCE,
    DETERMINISTIC_DEMO_PROVIDER,
    PHASE_3B_PROVIDER_VERSION,
)

_ASSET_DIRECTORY = Path(__file__).resolve().parents[2] / "app" / "demo" / "assets"
_AUDIO_PATH = _ASSET_DIRECTORY / "photosynthesis-demo.wav"
_MANIFEST_PATH = _ASSET_DIRECTORY / "photosynthesis-demo.wav.json"


def _manifest() -> dict[str, object]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_spoken_fixture_manifest_matches_parsed_wav_properties() -> None:
    manifest = _manifest()

    assert hashlib.sha256(_AUDIO_PATH.read_bytes()).hexdigest() == manifest["sha256"]
    assert manifest["sha256"] == "f431fd3931ed5c8e0f53a0ae4bce1a3d9ae0cf656efc0234cd8f3e742cb9ead7"
    assert manifest["mime_type"] == "audio/wav"
    with wave.open(str(_AUDIO_PATH), "rb") as fixture:
        assert fixture.getcomptype() == "NONE"
        assert fixture.getnchannels() == manifest["channels"] == 1
        assert fixture.getframerate() == manifest["sample_rate_hz"] == 16000
        assert fixture.getsampwidth() == manifest["sample_width_bytes"] == 2
        assert (
            round(fixture.getnframes() / fixture.getframerate() * 1000)
            == manifest["duration_ms"]
            == 19400
        )


def test_spoken_fixture_replaces_legacy_short_tone_asset_without_claiming_stt_accuracy() -> None:
    manifest = _manifest()
    with wave.open(str(_AUDIO_PATH), "rb") as fixture:
        pcm = fixture.readframes(fixture.getnframes())
        one_second = fixture.getframerate() * fixture.getnchannels() * fixture.getsampwidth()

    full_second_blocks = [
        pcm[start : start + one_second] for start in range(0, 19 * one_second, one_second)
    ]
    assert manifest["duration_ms"] > 9000
    assert len(full_second_blocks) == 19
    assert any(block != full_second_blocks[0] for block in full_second_blocks[1:])


def test_manifest_segments_are_valid_and_provider_preserves_raw_misrecognition() -> None:
    manifest = _manifest()
    segments = manifest["transcript_segments"]
    assert isinstance(segments, list)
    assert [item["sequence"] for item in segments] == [1, 2, 3]
    assert segments[0]["start_ms"] == 0
    assert segments[-1]["end_ms"] == manifest["duration_ms"]
    assert all(
        current["start_ms"] < current["end_ms"] <= manifest["duration_ms"] for current in segments
    )
    assert all(
        previous["end_ms"] == current["start_ms"]
        for previous, current in zip(segments, segments[1:])
    )

    provider = DeterministicDemoTranscriptionProvider(_MANIFEST_PATH)
    raw = provider.transcribe(manifest["sha256"])
    assert raw is not None
    assert [segment.sequence for segment in raw] == [1, 2, 3]
    assert raw[1].text == "ഇലയിലെ chlorophil സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു."
    assert "chlorophil" in " ".join(segment.text for segment in raw)
    assert provider.transcribe("0" * 64) is None


def test_manifest_provenance_is_explicitly_deterministic_and_not_live_stt() -> None:
    manifest = _manifest()

    assert manifest["provider_id"] == DETERMINISTIC_DEMO_PROVIDER
    assert manifest["provider_version"] == PHASE_3B_PROVIDER_VERSION
    assert manifest["provenance"] == DETERMINISTIC_DEMO_PROVENANCE
    assert "deterministic offline" in manifest["provenance"].casefold()
    assert "not live stt" in manifest["provenance"].casefold()
