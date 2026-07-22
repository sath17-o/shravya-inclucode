from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import ProviderMode, Settings
from app.models.foundation import TranscriptionRunEvidence
from app.services.audio_workflow import AudioWorkflowService, DemoSegment, WavUpload
from app.services.transcription_provider import (
    LocalFasterWhisperTranscriptionProvider,
    LocalWhisperConfiguration,
)
from tests.integration.factories import complete_photosynthesis_context


def _asset() -> bytes:
    return (
        Path(__file__).resolve().parents[2] / "app" / "demo" / "assets" / "photosynthesis-demo.wav"
    ).read_bytes()


class FakeWhisperModel:
    def transcribe(self, *_args, **_kwargs):
        segment = SimpleNamespace(
            start=0.0,
            end=19.4,
            text="ഇലയിലെ chlorophil സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.",
            avg_logprob=-0.25,
            no_speech_prob=0.02,
            compression_ratio=1.1,
            temperature=0.0,
            words=[SimpleNamespace(start=0.0, end=0.4, word="ഇലയിലെ", probability=0.91)],
        )
        return iter([segment]), SimpleNamespace(language="ml", language_probability=0.82)


def test_local_provider_preserves_immutable_teacher_evidence_without_student_leakage(
    migrated_api, tmp_path
) -> None:
    settings = Settings(
        provider_mode=ProviderMode.LOCAL_FASTER_WHISPER,
        media_root=tmp_path / "media",
    )
    provider = LocalFasterWhisperTranscriptionProvider(
        LocalWhisperConfiguration.from_settings(settings),
        model_loader=lambda _configuration: FakeWhisperModel(),
        version_lookup=lambda package: {"faster-whisper": "1.2.1", "ctranslate2": "test"}.get(
            package
        ),
    )
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        context_id = context.context.id
        service = AudioWorkflowService(
            session,
            settings,
            session_factory=migrated_api.session_factory,
            provider=provider,
        )
        recording = service.upload(
            context.lesson.id,
            WavUpload("local.wav", "audio/wav", _asset()),
        )
        job = service.request_transcription(recording.id)
        completed = service.run_job(job.id)
        assert completed.status.value == "SUCCEEDED"
        revision = service.get_revision(completed.result_transcript_revision_id or "")
        evidence = revision.transcription_evidence
        assert evidence is not None
        evidence_id = evidence.id
        raw_evidence = evidence.raw_provider_output_json
        assert evidence.provider_implementation == "local-faster-whisper"
        assert evidence.model_identifier == "small"
        assert evidence.source_sha256 == recording.sha256
        assert '"probability":0.91' in raw_evidence
        assert revision.segments[0].confidence is None

        summary = migrated_api.client.get(
            f"/api/v1/curriculum/context-versions/{context_id}/audio-workflow"
        )
        assert summary.status_code == 200

        corrected = service.create_manual_revision(
            revision.id,
            [
                DemoSegment(
                    start_ms=0,
                    end_ms=recording.duration_ms,
                    text="ഇലയിലെ Chlorophyll സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.",
                    sequence=1,
                )
            ],
        )
        assert corrected.transcription_evidence is None
        session.expire_all()
        retained = session.get(TranscriptionRunEvidence, evidence_id)
        assert retained is not None and retained.raw_provider_output_json == raw_evidence
        retained.inference_seconds = 99.0
        with pytest.raises(ValueError, match="transcription_run_evidence_is_immutable"):
            session.commit()
        session.rollback()

    revision_data = summary.json()["data"]["latest_revision"]
    assert revision_data["provenance_summary"] == {
        "mode": "local_faster_whisper",
        "provider_implementation": "local-faster-whisper",
        "model_identifier": "small",
        "device": "cpu",
        "language_detected": "ml",
        "inference_seconds": revision_data["provenance_summary"]["inference_seconds"],
        "local_only": True,
    }
    assert "raw_provider_output_json" not in str(revision_data)
