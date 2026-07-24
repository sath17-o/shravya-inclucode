from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.contracts.teacher_review import DomainError
from app.core.config import ProviderMode, Settings
from app.models.foundation import TranscriptionRunEvidence
from app.services.audio_workflow import AudioWorkflowService, DemoSegment, WavUpload
from app.services.malayalam_hybrid_provider import (
    INDICCONFORMER_DECODER,
    INDICCONFORMER_LANGUAGE,
    INDICCONFORMER_MODEL_ID,
    INDICCONFORMER_REVISION,
    HybridConfiguration,
    LocalMalayalamHybridTranscriptionProvider,
)
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


def test_hybrid_provider_persists_dual_local_evidence_and_safe_summary(
    migrated_api, tmp_path
) -> None:
    settings = Settings(
        provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID,
        media_root=tmp_path / "media",
    )
    whisper = LocalFasterWhisperTranscriptionProvider(
        LocalWhisperConfiguration.from_settings(settings),
        model_loader=lambda _configuration: FakeWhisperModel(),
        version_lookup=lambda package: {"faster-whisper": "1.2.1", "ctranslate2": "test"}.get(
            package
        ),
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    python = runtime / "python.exe"
    runner = runtime / "runner.py"
    model = runtime / "model"
    python.write_bytes(b"")
    runner.write_text("# fake", encoding="utf-8")
    model.mkdir()
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

    def run(command, **_kwargs):
        request = json.loads(Path(command[3]).read_text(encoding="utf-8"))
        response = {
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
                "model_load_seconds": 0.1,
                "inference_seconds": 0.1,
                "total_seconds": 0.2,
            },
            "segments": [
                {
                    "sequence": segment["sequence"],
                    "start_ms": segment["start_ms"],
                    "end_ms": segment["end_ms"],
                    "text": "ഇലയിലെ chlorophil സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.",
                }
                for segment in request["segments"]
            ],
        }
        Path(command[5]).write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    provider = LocalMalayalamHybridTranscriptionProvider(
        HybridConfiguration(
            python,
            runner,
            model,
            90,
            LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True),
        ),
        whisper,
        process_runner=run,
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
        completed = service.run_job(service.request_transcription(recording.id).id)
        revision = service.get_revision(completed.result_transcript_revision_id or "")
        evidence = revision.transcription_evidence
        assert completed.status.value == "SUCCEEDED"
        assert evidence is not None
        assert evidence.provider_mode == "local_malayalam_hybrid"
        assert '"pipeline":"local_malayalam_hybrid"' in evidence.raw_provider_output_json
        assert '"faster_whisper"' in evidence.raw_provider_output_json
        assert '"indicconformer"' in evidence.raw_provider_output_json
        assert '"provider_mode":"local_faster_whisper"' in evidence.raw_provider_output_json
        assert evidence.inference_seconds >= 0

    response = migrated_api.client.get(
        f"/api/v1/curriculum/context-versions/{context_id}/audio-workflow"
    )
    assert response.status_code == 200
    summary = response.json()["data"]["latest_revision"]["provenance_summary"]
    assert summary["mode"] == "local_malayalam_hybrid"
    assert summary["local_only"] is True
    assert "raw_provider_output_json" not in str(response.json())


def test_hybrid_manifest_failure_creates_no_revision_or_evidence(migrated_api, tmp_path) -> None:
    settings = Settings(
        provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID,
        media_root=tmp_path / "media",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    python = runtime / "python.exe"
    runner = runtime / "runner.py"
    model = runtime / "model"
    python.write_bytes(b"")
    runner.write_text("# fake", encoding="utf-8")
    model.mkdir()
    provider = LocalMalayalamHybridTranscriptionProvider(
        HybridConfiguration(
            python,
            runner,
            model,
            90,
            LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True),
        ),
        LocalFasterWhisperTranscriptionProvider(
            LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True),
            model_loader=lambda _configuration: FakeWhisperModel(),
        ),
    )
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        service = AudioWorkflowService(
            session,
            settings,
            session_factory=migrated_api.session_factory,
            provider=provider,
        )
        recording = service.upload(context.lesson.id, WavUpload("local.wav", "audio/wav", _asset()))
        job = service.run_job(service.request_transcription(recording.id).id)
        session.refresh(recording)
        assert job.error_code == "local_hybrid_model_manifest_missing"
        assert recording.transcript_revisions == []


def test_hybrid_whisper_failure_is_recoverable_without_revision_or_evidence(
    migrated_api, tmp_path
) -> None:
    settings = Settings(
        provider_mode=ProviderMode.LOCAL_MALAYALAM_HYBRID,
        media_root=tmp_path / "media",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    python = runtime / "python.exe"
    runner = runtime / "runner.py"
    model = runtime / "model"
    python.write_bytes(b"")
    runner.write_text("# must not execute", encoding="utf-8")
    model.mkdir()
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

    class FailingWhisper:
        def transcribe(self, _source):
            raise DomainError(
                "local_stt_model_load_failed", "audio.local_stt_model_load_failed", "validation"
            )

    provider = LocalMalayalamHybridTranscriptionProvider(
        HybridConfiguration(
            python,
            runner,
            model,
            90,
            LocalWhisperConfiguration("small", "cpu", "int8", "ml", True, 5, True, True, True),
        ),
        FailingWhisper(),
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
        recording = service.upload(context.lesson.id, WavUpload("local.wav", "audio/wav", _asset()))
        job = service.run_job(service.request_transcription(recording.id).id)
        session.refresh(recording)
        assert job.status.value == "FAILED"
        assert job.error_code == "local_hybrid_whisper_failed"
        assert job.recoverable is True
        assert recording.workflow_status.value == "MANUAL_TRANSCRIPT_REQUIRED"
        assert recording.transcript_revisions == []
        assert session.query(TranscriptionRunEvidence).count() == 0

    summary = migrated_api.client.get(
        f"/api/v1/curriculum/context-versions/{context_id}/audio-workflow"
    )
    assert summary.status_code == 200
    assert "local_stt_model_load_failed" not in str(summary.json())
