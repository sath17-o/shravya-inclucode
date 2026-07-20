import hashlib
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event, Lock, Thread, local

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.contracts.enums import (
    ProcessingJobType,
    RecordingDeletionStatus,
    TeacherReviewStatus,
    TermDecisionValue,
    UploadIntentStatus,
)
from app.contracts.teacher_review import DomainError
from app.core.config import get_settings
from app.main import create_app
from app.models.foundation import (
    CourseContextVersion,
    LectureAudio,
    MediaUploadIntent,
    ProcessingJob,
    RecordingDeletionTombstone,
    TermDecision,
    TermSuggestion,
    TranscriptQualityAssessment,
    TranscriptQualityReason,
    TranscriptRevision,
    TranscriptSegment,
    utcnow,
)
from app.repositories.curriculum import CurriculumRepository
from app.services.audio_workflow import AudioWorkflowService, WavUpload
from app.services.context_completeness import ContextCompletenessService
from tests.integration.factories import complete_photosynthesis_context


def _asset() -> bytes:
    return (
        Path(__file__).resolve().parents[2] / "app" / "demo" / "assets" / "photosynthesis-demo.wav"
    ).read_bytes()


def _media_path(migrated_api, recording_id: str) -> Path:
    with migrated_api.session_factory() as session:
        recording = session.get(LectureAudio, recording_id)
        assert recording is not None
        return Path(recording.storage_path)


def _upload_and_transcribe(migrated_api, lesson_id: str) -> tuple[dict, dict]:
    uploaded = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "photosynthesis-demo.wav"},
    ).json()["data"]
    job = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{uploaded['id']}/transcriptions"
    ).json()["data"]
    completed = migrated_api.client.post(f"/api/v1/teacher/processing-jobs/{job['id']}/run").json()[
        "data"
    ]
    revision = migrated_api.client.get(
        f"/api/v1/teacher/transcript-revisions/{completed['resulting_transcript_revision_id']}"
    ).json()["data"]
    return uploaded, revision


def _confirm_and_verify(migrated_api, revision: dict) -> dict:
    confirmed = migrated_api.client.post(
        f"/api/v1/teacher/term-suggestions/{revision['suggestions'][0]['id']}/decision",
        json={"decision": "CONFIRMED"},
    )
    assert confirmed.status_code == 200
    verified = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision['id']}/quality-assessment"
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["quality"]["quality_status"] == "VERIFIED"
    return verified.json()["data"]


def _workflow_summary(migrated_api, context_id: str) -> dict:
    response = migrated_api.client.get(
        f"/api/v1/curriculum/context-versions/{context_id}/audio-workflow"
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_audio_workflow_summary_reconstructs_durable_teacher_state(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id

    empty = _workflow_summary(migrated_api, context_id)
    assert empty["state"] == "NO_RECORDING"
    assert empty["recording"] is None
    assert not any(empty["capabilities"].values())

    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "photosynthesis-demo.wav"},
    ).json()["data"]
    uploaded = _workflow_summary(migrated_api, context_id)
    assert uploaded["state"] == "UPLOADED"
    assert uploaded["recording"]["id"] == recording["id"]
    assert uploaded["recording"]["content_url"].endswith(f"/{recording['id']}/content")
    assert uploaded["capabilities"]["can_start_processing"]

    job = migrated_api.client.post(f"/api/v1/teacher/recordings/{recording['id']}/transcriptions")
    assert job.status_code == 200
    processing = _workflow_summary(migrated_api, context_id)
    assert processing["state"] == "PROCESSING"
    assert processing["latest_job"]["status"] == "QUEUED"

    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/processing-jobs/{job.json()['data']['id']}/run"
        ).status_code
        == 200
    )
    ready = _workflow_summary(migrated_api, context_id)
    assert ready["state"] == "NEEDS_REVIEW"
    assert ready["latest_revision"]["provenance_label"].startswith("Deterministic offline")
    suggestion = ready["latest_revision"]["suggestions"][0]
    assert suggestion["detected_text"] == "chlorophil"
    assert suggestion["latest_decision"] is None

    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/term-suggestions/{suggestion['id']}/decision",
            json={"decision": "CONFIRMED"},
        ).status_code
        == 200
    )
    decided = _workflow_summary(migrated_api, context_id)
    assert decided["latest_revision"]["suggestions"][0]["latest_decision"] == "CONFIRMED"

    revision_id = decided["latest_revision"]["id"]
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{revision_id}/quality-assessment"
        ).status_code
        == 200
    )
    verified = _workflow_summary(migrated_api, context_id)
    assert verified["state"] == "QUALITY_VERIFIED"
    assert verified["latest_revision"]["quality"]["measured_coverage"] == 1.0
    assert verified["capabilities"]["can_approve_transcript"]

    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{revision_id}/approve"
        ).status_code
        == 200
    )
    approved = _workflow_summary(migrated_api, context_id)
    assert approved["state"] == "TRANSCRIPT_APPROVED"
    assert not approved["capabilities"]["can_edit_transcript"]
    assert str(get_settings().media_root.resolve()) not in str(approved)


def test_audio_workflow_summary_fails_closed_for_current_evidence_and_cleanup(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, revision = _upload_and_transcribe(migrated_api, lesson_id)
    _confirm_and_verify(migrated_api, revision)
    with migrated_api.session_factory() as session:
        suggestion = session.get(TermSuggestion, revision["suggestions"][0]["id"])
        assert suggestion is not None
        session.add(
            TermDecision(
                term_suggestion_id=suggestion.id,
                decision=TermDecisionValue.UNSURE,
                decided_by_role="teacher",
            )
        )
        session.commit()
    stale = _workflow_summary(migrated_api, context_id)
    assert stale["state"] == "QUALITY_BLOCKED"
    assert {item["reason_code"] for item in stale["latest_revision"]["quality"]["reasons"]} >= {
        "unresolved_terms"
    }

    with migrated_api.session_factory() as session:
        session.add(
            RecordingDeletionTombstone(
                recording_id=recording["id"],
                context_version_id=context_id,
                media_relative_path="safe/relative.wav",
                quarantine_relative_path=".quarantine/safe.media",
                status=RecordingDeletionStatus.RECOVERY_CONFLICT,
                conflict_code="media_identity_mismatch",
            )
        )
        session.commit()
    conflict = _workflow_summary(migrated_api, context_id)
    assert conflict["state"] == "RECOVERY_CONFLICT"
    assert conflict["deletion"] == {
        "status": "RECOVERY_CONFLICT",
        "recoverable": True,
        "message": "Recording cleanup needs attention before another recording can be used.",
    }
    assert "safe/relative.wav" not in str(conflict)


def test_migrated_wav_workflow_is_idempotent_and_student_safe(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.DRAFT)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
        course_id = context.course.id
        context_id = context.context.id

    uploaded = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "../../photosynthesis-demo.wav"},
    )
    assert uploaded.status_code == 200
    recording = uploaded.json()["data"]
    assert recording["original_filename"] == "photosynthesis-demo.wav"
    assert recording["duration_ms"] == 19400
    audio = migrated_api.client.get(f"/api/v1/teacher/recordings/{recording['id']}/content")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert str(get_settings().media_root.resolve()) not in audio.text

    first = migrated_api.client.post(f"/api/v1/teacher/recordings/{recording['id']}/transcriptions")
    repeat = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/transcriptions"
    )
    assert first.status_code == repeat.status_code == 200
    assert first.json()["data"]["id"] == repeat.json()["data"]["id"]
    assert first.json()["data"]["status"] == "QUEUED"

    job = migrated_api.client.post(
        f"/api/v1/teacher/processing-jobs/{first.json()['data']['id']}/run"
    ).json()["data"]
    assert job["status"] == "SUCCEEDED"
    revision_id = job["resulting_transcript_revision_id"]
    assert revision_id
    revision = migrated_api.client.get(
        f"/api/v1/teacher/transcript-revisions/{revision_id}"
    ).json()["data"]
    suggestion = revision["suggestions"][0]
    assert suggestion["detected_text"] == "chlorophil"
    assert suggestion["canonical_term"] == "Chlorophyll"
    assert suggestion["malayalam_support_label"] == "ക്ലോറോഫിൽ"
    assert revision["provenance_label"] == (
        "Deterministic offline demo transcript mapped to a team-recorded "
        "Malayalam/code-mixed lesson — not live STT."
    )

    unsure = migrated_api.client.post(
        f"/api/v1/teacher/term-suggestions/{suggestion['id']}/decision",
        json={"decision": "UNSURE"},
    )
    assert unsure.status_code == 200
    blocked = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision_id}/quality-assessment"
    ).json()["data"]
    assert blocked["quality"]["quality_status"] == "FAILED"
    assert {item["reason_code"] for item in blocked["quality"]["reasons"]} >= {"unresolved_terms"}

    manual = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision_id}/manual-revision",
        json={
            "segments": [
                {
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                    "text": item["text"].replace("chlorophil", "Chlorophyll"),
                }
                for item in revision["segments"]
            ]
        },
    )
    assert manual.status_code == 200
    corrected = manual.json()["data"]
    assert corrected["revision_number"] == 2
    assert corrected["copied_from_transcript_revision_id"] == revision_id
    verified = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{corrected['id']}/quality-assessment"
    ).json()["data"]
    assert verified["quality"]["quality_status"] == "VERIFIED"
    approved = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{corrected['id']}/approve"
    )
    assert approved.status_code == 200

    with migrated_api.session_factory() as session:
        assert (
            ContextCompletenessService(CurriculumRepository(session))
            .evaluate(context_id)
            .is_complete
        )
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{context_id}/submit-for-review"
        ).status_code
        == 200
    )
    assert (
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/approve").status_code
        == 200
    )
    student = migrated_api.client.get(f"/api/v1/student/courses/{course_id}/lesson-overview")
    assert student.status_code == 200
    transcript = student.json()["data"]["chapters"][0]["lessons"][0]["approved_transcript"]
    assert transcript["teacher_review_status"] == "APPROVED"
    assert "Chlorophyll" in transcript["segments"][1]["text"]


def test_unknown_wav_never_receives_demo_text(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    unknown = bytearray(_asset())
    unknown[-1] ^= 1
    uploaded = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown),
        headers={"Content-Type": "audio/wav", "X-Filename": "unknown.wav"},
    ).json()["data"]
    job = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{uploaded['id']}/transcriptions"
    ).json()["data"]
    failed = migrated_api.client.post(f"/api/v1/teacher/processing-jobs/{job['id']}/run").json()[
        "data"
    ]
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "demo_audio_unrecognized"
    assert failed["resulting_transcript_revision_id"] is None


def test_stale_term_decisions_and_assessments_cannot_approve_or_submit(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.DRAFT)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id

    _, revision = _upload_and_transcribe(migrated_api, lesson_id)
    verified = _confirm_and_verify(migrated_api, revision)
    unsure = migrated_api.client.post(
        f"/api/v1/teacher/term-suggestions/{revision['suggestions'][0]['id']}/decision",
        json={"decision": "UNSURE"},
    )
    assert unsure.status_code == 200
    blocked_approval = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision['id']}/approve"
    )
    assert blocked_approval.status_code == 422
    assert blocked_approval.json()["code"] == "transcript_quality_blocked"

    rejected = migrated_api.client.post(
        f"/api/v1/teacher/term-suggestions/{revision['suggestions'][0]['id']}/decision",
        json={"decision": "REJECTED"},
    )
    assert rejected.status_code == 200
    blocked_submit = migrated_api.client.post(
        f"/api/v1/teacher/contexts/{context_id}/submit-for-review"
    )
    assert blocked_submit.status_code == 422
    assert blocked_submit.json()["code"] == "context_incomplete"
    assert verified["quality"]["quality_status"] == "VERIFIED"


def test_manual_revisions_are_append_only_and_student_projects_confirmed_term(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.DRAFT)
        session.commit()
        lesson_id = context.lesson.id
        course_id = context.course.id
        context_id = context.context.id

    _, revision = _upload_and_transcribe(migrated_api, lesson_id)
    _confirm_and_verify(migrated_api, revision)
    manual = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision['id']}/manual-revision",
        json={
            "segments": [
                {
                    "sequence": item["sequence"],
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                    "text": item["text"].replace("chlorophil", "Chlorophyll"),
                }
                for item in revision["segments"]
            ]
        },
    )
    assert manual.status_code == 200
    replacement = manual.json()["data"]
    assert "Chlorophyll" in replacement["segments"][1]["text"]
    original = migrated_api.client.get(f"/api/v1/teacher/transcript-revisions/{revision['id']}")
    assert "chlorophil" in original.json()["data"]["segments"][1]["text"]
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{revision['id']}/approve"
        ).status_code
        == 422
    )

    verified = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{replacement['id']}/quality-assessment"
    ).json()["data"]
    assert verified["quality"]["quality_status"] == "VERIFIED"
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{replacement['id']}/approve"
        ).status_code
        == 200
    )
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{context_id}/submit-for-review"
        ).status_code
        == 200
    )
    assert (
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/approve").status_code
        == 200
    )
    transcript = migrated_api.client.get(
        f"/api/v1/student/courses/{course_id}/lesson-overview"
    ).json()["data"]["chapters"][0]["lessons"][0]["approved_transcript"]
    rendered = " ".join(item["text"] for item in transcript["segments"])
    assert "Chlorophyll" in rendered
    assert "chlorophil" not in rendered


def test_confirmed_term_is_projected_canonically_for_students(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.DRAFT)
        session.commit()
        lesson_id = context.lesson.id
        course_id = context.course.id
        context_id = context.context.id

    _, revision = _upload_and_transcribe(migrated_api, lesson_id)
    _confirm_and_verify(migrated_api, revision)
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{revision['id']}/approve"
        ).status_code
        == 200
    )
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{context_id}/submit-for-review"
        ).status_code
        == 200
    )
    assert (
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/approve").status_code
        == 200
    )
    transcript = migrated_api.client.get(
        f"/api/v1/student/courses/{course_id}/lesson-overview"
    ).json()["data"]["chapters"][0]["lessons"][0]["approved_transcript"]
    rendered = " ".join(item["text"] for item in transcript["segments"])
    assert "Chlorophyll" in rendered
    assert "chlorophil" not in rendered


def test_unknown_wav_has_manual_entry_and_invalid_timestamps_are_typed(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    unknown = bytearray(_asset())
    unknown[-1] ^= 1
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown),
        headers={"Content-Type": "audio/wav", "X-Filename": "unknown.wav"},
    ).json()["data"]
    invalid = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/manual-revision",
        json={"segments": [{"sequence": 1, "start_ms": 500, "end_ms": 100, "text": "Manual text"}]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "REQUEST_VALIDATION_ERROR"
    manual = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/manual-revision",
        json={"segments": [{"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Manual text"}]},
    )
    assert manual.status_code == 200
    quality = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{manual.json()['data']['id']}/quality-assessment"
    )
    assert quality.json()["data"]["quality"]["quality_status"] == "VERIFIED"


def test_removing_a_mutable_recording_cleans_media_jobs_and_transcript_descendants(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, revision = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    removed = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["data"] == {"recording_id": recording["id"], "removed": True}
    assert not media_path.exists()
    with migrated_api.session_factory() as session:
        assert session.get(LectureAudio, recording["id"]) is None
        assert (
            session.scalar(select(ProcessingJob).where(ProcessingJob.entity_id == recording["id"]))
            is None
        )
        assert session.get(TranscriptRevision, revision["id"]) is None
        assert (
            session.scalar(
                select(TranscriptSegment).where(
                    TranscriptSegment.transcript_revision_id == revision["id"]
                )
            )
            is None
        )
        assert session.scalar(select(TermSuggestion)) is None
        assert session.scalar(select(TermDecision)) is None
    retry = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert retry.status_code == 200
    assert retry.json()["data"]["removed"] is True


def test_removal_after_failed_processing_and_from_approved_context(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    unknown = bytearray(_asset())
    unknown[-1] ^= 1
    uploaded = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown),
        headers={"Content-Type": "audio/wav", "X-Filename": "unknown.wav"},
    ).json()["data"]
    job = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{uploaded['id']}/transcriptions"
    ).json()["data"]
    assert (
        migrated_api.client.post(f"/api/v1/teacher/processing-jobs/{job['id']}/run").status_code
        == 200
    )
    assert (
        migrated_api.client.delete(
            f"/api/v1/curriculum/context-versions/{context_id}/recordings/{uploaded['id']}"
        ).status_code
        == 200
    )

    second, _ = _upload_and_transcribe(migrated_api, lesson_id)
    with migrated_api.session_factory() as session:
        session.get(
            type(context.context), context_id
        ).teacher_review_status = TeacherReviewStatus.APPROVED
        session.commit()
    rejected = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{second['id']}"
    )
    assert rejected.status_code == 403


def test_recording_origins_and_manual_provenance_are_truthful(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id

    demo, demo_revision = _upload_and_transcribe(migrated_api, lesson_id)
    assert demo["source_status"] == "DEMO"
    corrected = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{demo_revision['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Corrected demo text"}
            ]
        },
    )
    assert corrected.json()["data"]["source_status"] == "DEMO"
    assert "Teacher-corrected" in corrected.json()["data"]["provenance_label"]

    unknown_bytes = bytearray(_asset())
    unknown_bytes[-1] ^= 1
    unknown = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown_bytes),
        headers={"Content-Type": "audio/wav", "X-Filename": "local.wav"},
    ).json()["data"]
    assert unknown["source_status"] == "LOCAL_TEACHER"
    manual = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{unknown['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Local teacher text"}
            ]
        },
    )
    assert manual.status_code == 200
    assert manual.json()["data"]["source_status"] == "LOCAL_TEACHER"
    assert manual.json()["data"]["provenance_label"] == (
        "Teacher-entered transcript for a local classroom recording"
    )


def test_invalid_provenance_blocks_quality_and_context_submission(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    _, revision = _upload_and_transcribe(migrated_api, lesson_id)
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/term-suggestions/{revision['suggestions'][0]['id']}/decision",
            json={"decision": "CONFIRMED"},
        ).status_code
        == 200
    )
    with migrated_api.session_factory() as session:
        persisted = session.get(TranscriptRevision, revision["id"])
        persisted.provider_name = "legacy-migrated"
        persisted.provenance_label = "Legacy transcript record — provenance unavailable"
        session.commit()
    quality = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision['id']}/quality-assessment"
    )
    assert quality.json()["data"]["quality"]["quality_status"] == "FAILED"
    assert "provenance_unrecognised" in {
        reason["reason_code"] for reason in quality.json()["data"]["quality"]["reasons"]
    }
    submitted = migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/submit-for-review")
    assert submitted.status_code == 422
    assert submitted.json()["code"] == "context_incomplete"


def test_manual_revision_validation_is_atomic_and_typed(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    unknown_bytes = bytearray(_asset())
    unknown_bytes[-1] ^= 1
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown_bytes),
        headers={"Content-Type": "audio/wav", "X-Filename": "local.wav"},
    ).json()["data"]
    invalid_payloads = [
        {"segments": [{"sequence": 1, "start_ms": -1, "end_ms": 1, "text": "Text"}]},
        {"segments": [{"sequence": 1, "start_ms": 2, "end_ms": 1, "text": "Text"}]},
        {"segments": [{"sequence": 1, "start_ms": 1, "end_ms": 1, "text": "Text"}]},
        {"segments": [{"sequence": 1, "start_ms": 0, "end_ms": 19401, "text": "Text"}]},
        {
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 1, "text": "Text"},
                {"sequence": 1, "start_ms": 1, "end_ms": 2, "text": "Text"},
            ]
        },
        {"segments": [{"sequence": 0, "start_ms": 0, "end_ms": 1, "text": "Text"}]},
        {"segments": [{"sequence": 2, "start_ms": 0, "end_ms": 1, "text": "Text"}]},
        {"segments": [{"sequence": 1, "start_ms": 0, "end_ms": 1, "text": " "}]},
        {"segments": []},
    ]
    for payload in invalid_payloads:
        response = migrated_api.client.post(
            f"/api/v1/teacher/recordings/{recording['id']}/manual-revision", json=payload
        )
        assert response.status_code == 422
        assert response.json()["code"] != "INTERNAL_ERROR"
    with migrated_api.session_factory() as session:
        assert (
            session.scalar(
                select(TranscriptRevision).where(
                    TranscriptRevision.lecture_audio_id == recording["id"]
                )
            )
            is None
        )

    valid = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/manual-revision",
        json={"segments": [{"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Valid text"}]},
    )
    assert valid.status_code == 200
    with migrated_api.session_factory() as session:
        assert (
            session.query(TranscriptRevision).filter_by(lecture_audio_id=recording["id"]).count()
            == 1
        )


def test_rejected_manual_revision_does_not_mutate_existing_revision_state(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    _, revision = _upload_and_transcribe(migrated_api, lesson_id)
    _confirm_and_verify(migrated_api, revision)
    with migrated_api.session_factory() as session:
        original = session.get(TranscriptRevision, revision["id"])
        assert original is not None
        original_revision = (
            original.id,
            original.revision_number,
            original.source_status.value,
            original.provider_name,
            original.provider_version,
            original.provenance_label,
            original.teacher_review_status.value,
            original.approved_at,
            original.approved_by_role,
            original.copied_from_transcript_revision_id,
        )
        original_segments = tuple(
            (
                segment.id,
                segment.sequence,
                segment.start_ms,
                segment.end_ms,
                segment.text,
                segment.confidence,
            )
            for segment in session.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_revision_id == revision["id"])
                .order_by(TranscriptSegment.sequence)
            )
        )
        original_decisions = tuple(
            (
                decision.id,
                decision.term_suggestion_id,
                decision.decision.value,
                decision.decided_by_role,
            )
            for decision in session.scalars(select(TermDecision).order_by(TermDecision.id))
        )
        original_assessment = session.scalar(
            select(TranscriptQualityAssessment).where(
                TranscriptQualityAssessment.transcript_revision_id == revision["id"]
            )
        )
        assert original_assessment is not None
        original_assessment_values = (
            original_assessment.id,
            original_assessment.transcript_revision_id,
            original_assessment.quality_status.value,
        )
        original_reasons = tuple(
            (
                reason.id,
                reason.assessment_id,
                reason.reason_code,
                reason.severity,
                reason.message_key,
                reason.measured_value,
                reason.threshold,
                reason.recovery_action,
            )
            for reason in session.scalars(
                select(TranscriptQualityReason)
                .where(TranscriptQualityReason.assessment_id == original_assessment.id)
                .order_by(TranscriptQualityReason.reason_code)
            )
        )
        original_workflow_status = original.lecture_audio.workflow_status.value
        original_latest_revision_number = session.scalar(
            select(TranscriptRevision.revision_number)
            .where(TranscriptRevision.lecture_audio_id == revision["recording_id"])
            .order_by(TranscriptRevision.revision_number.desc())
            .limit(1)
        )

    rejected = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{revision['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 500, "end_ms": 1500, "text": "First"},
                {"sequence": 2, "start_ms": 0, "end_ms": 1000, "text": "Second"},
            ]
        },
    )
    assert rejected.status_code == 422
    with migrated_api.session_factory() as session:
        assert (
            session.query(TranscriptRevision)
            .filter_by(lecture_audio_id=revision["recording_id"])
            .count()
            == 1
        )
        assert session.query(TranscriptSegment).filter_by(
            transcript_revision_id=revision["id"]
        ).count() == len(original_segments)
        unchanged = session.get(TranscriptRevision, revision["id"])
        assert unchanged is not None
        assert (
            unchanged.id,
            unchanged.revision_number,
            unchanged.source_status.value,
            unchanged.provider_name,
            unchanged.provider_version,
            unchanged.provenance_label,
            unchanged.teacher_review_status.value,
            unchanged.approved_at,
            unchanged.approved_by_role,
            unchanged.copied_from_transcript_revision_id,
        ) == original_revision
        assert (
            tuple(
                (
                    segment.id,
                    segment.sequence,
                    segment.start_ms,
                    segment.end_ms,
                    segment.text,
                    segment.confidence,
                )
                for segment in session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_revision_id == revision["id"])
                    .order_by(TranscriptSegment.sequence)
                )
            )
            == original_segments
        )
        assert (
            tuple(
                (
                    decision.id,
                    decision.term_suggestion_id,
                    decision.decision.value,
                    decision.decided_by_role,
                )
                for decision in session.scalars(select(TermDecision).order_by(TermDecision.id))
            )
            == original_decisions
        )
        assessment = session.scalar(
            select(TranscriptQualityAssessment).where(
                TranscriptQualityAssessment.transcript_revision_id == revision["id"]
            )
        )
        assert assessment is not None
        assert (
            assessment.id,
            assessment.transcript_revision_id,
            assessment.quality_status.value,
        ) == original_assessment_values
        assert (
            tuple(
                (
                    reason.id,
                    reason.assessment_id,
                    reason.reason_code,
                    reason.severity,
                    reason.message_key,
                    reason.measured_value,
                    reason.threshold,
                    reason.recovery_action,
                )
                for reason in session.scalars(
                    select(TranscriptQualityReason)
                    .where(TranscriptQualityReason.assessment_id == assessment.id)
                    .order_by(TranscriptQualityReason.reason_code)
                )
            )
            == original_reasons
        )
        assert unchanged.lecture_audio.workflow_status.value == original_workflow_status
        assert (
            session.scalar(
                select(TranscriptRevision.revision_number)
                .where(TranscriptRevision.lecture_audio_id == revision["recording_id"])
                .order_by(TranscriptRevision.revision_number.desc())
                .limit(1)
            )
            == original_latest_revision_number
        )


def test_removal_tombstone_retries_after_media_unlink_failure(migrated_api, monkeypatch) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    original_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path.parent.name == ".quarantine":
            raise OSError("simulated media failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    failed = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert failed.status_code == 409
    assert str(media_path) not in failed.text
    with migrated_api.session_factory() as session:
        assert session.get(LectureAudio, recording["id"]) is None
        assert (
            session.scalar(
                select(RecordingDeletionTombstone).where(
                    RecordingDeletionTombstone.recording_id == recording["id"]
                )
            )
            is not None
        )
    monkeypatch.setattr(Path, "unlink", original_unlink)
    retried = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert retried.status_code == 200
    assert retried.json()["data"]["removed"] is True
    assert not media_path.exists()
    with migrated_api.session_factory() as session:
        receipt = session.scalar(select(RecordingDeletionTombstone))
        assert receipt is not None
        assert receipt.status.value == "COMPLETED"
        assert receipt.media_relative_path is None


def test_removal_handles_missing_media_and_all_job_types(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    with migrated_api.session_factory() as session:
        session.add(
            ProcessingJob(
                lesson_id=lesson_id,
                job_type=ProcessingJobType.CONCEPT_EXTRACTION,
                entity_id=recording["id"],
                progress_message="Additional job type",
                retry_count=0,
            )
        )
        session.commit()
    media_path.unlink()
    removed = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert removed.status_code == 200
    with migrated_api.session_factory() as session:
        assert (
            session.scalar(select(ProcessingJob).where(ProcessingJob.entity_id == recording["id"]))
            is None
        )


def test_removal_rolls_back_database_failure_before_tombstone_commit(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as setup_session:
        context = complete_photosynthesis_context(setup_session)
        setup_session.commit()
        lesson_id = context.lesson.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())

        def fail_commit():
            raise RuntimeError("simulated tombstone transition failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        try:
            service.delete_recording(recording["id"])
        except (RuntimeError, DomainError):
            pass
        else:
            raise AssertionError("expected simulated commit failure")
        assert session.get(LectureAudio, recording["id"]) is not None
        session.expire_all()
        assert session.scalar(select(RecordingDeletionTombstone)) is None
        assert media_path.exists()


def test_process_style_interruption_keeps_retryable_tombstone(migrated_api, monkeypatch) -> None:
    with migrated_api.session_factory() as setup_session:
        context = complete_photosynthesis_context(setup_session)
        setup_session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())

        def interrupt(*_args):
            raise RuntimeError("simulated interruption after durable transition")

        monkeypatch.setattr(service, "_finish_deletion", interrupt)
        try:
            service.delete_recording(recording["id"])
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected simulated interruption")
        assert session.get(LectureAudio, recording["id"]) is None
        assert session.scalar(select(RecordingDeletionTombstone)) is not None
    monkeypatch.undo()
    retried = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert retried.status_code == 200
    with migrated_api.session_factory() as session:
        receipt = session.scalar(select(RecordingDeletionTombstone))
        assert receipt is not None
        assert receipt.status.value == "COMPLETED"
        assert receipt.completed_at is not None
        assert receipt.media_relative_path is None


def test_concurrent_deletion_joins_one_durable_tombstone_and_cleans_once(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    original_unlink = Path.unlink
    unlink_calls = 0

    def count_media_unlink(path, *args, **kwargs):
        nonlocal unlink_calls
        if path.parent.name == ".quarantine":
            unlink_calls += 1
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", count_media_unlink)
    transition_barrier = Barrier(2)
    thread_state = local()
    original_transition = AudioWorkflowService._create_or_load_deletion_tombstone

    def synchronize_active_read_then_transition(service, *args, **kwargs):
        # delete_recording loads LectureAudio before this call. Each thread must
        # therefore observe the active row before either writes its tombstone.
        if not getattr(thread_state, "released", False):
            thread_state.released = True
            transition_barrier.wait(timeout=5)
        return original_transition(service, *args, **kwargs)

    monkeypatch.setattr(
        AudioWorkflowService,
        "_create_or_load_deletion_tombstone",
        synchronize_active_read_then_transition,
    )
    outcomes: list[tuple[str, str | None]] = []
    outcomes_lock = Lock()

    def delete_from_independent_session() -> None:
        with migrated_api.session_factory() as session:
            try:
                assert AudioWorkflowService(session, get_settings()).delete_recording(
                    recording["id"], expected_context_version_id=context_id
                )
            except DomainError as error:
                outcome = ("recoverable_conflict", error.code)
            except Exception as error:  # pragma: no cover - assertion below retains the error type
                outcome = ("untyped", type(error).__name__)
            else:
                outcome = ("success", None)
        with outcomes_lock:
            outcomes.append(outcome)

    first = Thread(target=delete_from_independent_session)
    second = Thread(target=delete_from_independent_session)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    assert len(outcomes) == 2
    assert all(kind in {"success", "recoverable_conflict"} for kind, _ in outcomes), outcomes
    assert all(code in {None, "RECORDING_DELETION_IN_PROGRESS"} for _, code in outcomes), outcomes
    assert unlink_calls == 1
    assert not media_path.exists()
    with migrated_api.session_factory() as session:
        receipts = list(
            session.scalars(
                select(RecordingDeletionTombstone).where(
                    RecordingDeletionTombstone.recording_id == recording["id"]
                )
            )
        )
        assert len(receipts) == 1
        assert receipts[0].status.value == "COMPLETED"
        assert session.get(LectureAudio, recording["id"]) is None
        assert (
            session.scalar(select(ProcessingJob).where(ProcessingJob.entity_id == recording["id"]))
            is None
        )


def test_pending_cleanup_remains_authorised_after_context_approval_and_rejects_wrong_context(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)
    media_path = _media_path(migrated_api, recording["id"])
    original_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))
    assert (
        migrated_api.client.delete(
            f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
        ).status_code
        == 409
    )
    with migrated_api.session_factory() as session:
        session.get(
            CourseContextVersion, context_id
        ).teacher_review_status = TeacherReviewStatus.APPROVED
        session.commit()
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        try:
            service.delete_recording(recording["id"], expected_context_version_id="wrong-context")
        except Exception as error:
            assert getattr(error, "code", None) == "recording_context_mismatch"
        else:
            raise AssertionError("a wrong context must not join a pending cleanup")
    monkeypatch.setattr(Path, "unlink", original_unlink)
    assert (
        migrated_api.client.delete(
            f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
        ).status_code
        == 200
    )
    assert not media_path.exists()


def test_demo_manual_first_and_corrected_parent_lineage_fail_closed(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    demo = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "photosynthesis-demo.wav"},
    ).json()["data"]
    manual_first = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{demo['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Manual demo text"}
            ]
        },
    )
    assert manual_first.status_code == 200
    assert manual_first.json()["data"]["source_status"] == "DEMO"
    assert manual_first.json()["data"]["provider_name"] == "teacher-entered"
    assert "bundled demo recording" in manual_first.json()["data"]["provenance_label"]

    with migrated_api.session_factory() as session:
        lineage_context = complete_photosynthesis_context(session)
        session.commit()
        lineage_lesson_id = lineage_context.lesson.id
    _, deterministic = _upload_and_transcribe(migrated_api, lineage_lesson_id)
    for field, value in (
        ("provider_version", "wrong"),
        ("provenance_label", "unknown origin"),
        ("provider_name", "legacy-migrated"),
    ):
        with migrated_api.session_factory() as session:
            parent = session.get(TranscriptRevision, deterministic["id"])
            setattr(parent, field, value)
            session.commit()
        rejected = migrated_api.client.post(
            f"/api/v1/teacher/transcript-revisions/{deterministic['id']}/manual-revision",
            json={
                "segments": [{"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "No child"}]
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "transcript_provenance_invalid"
        with migrated_api.session_factory() as session:
            assert (
                session.query(TranscriptRevision)
                .filter_by(lecture_audio_id=deterministic["recording_id"])
                .count()
                == 1
            )
            parent = session.get(TranscriptRevision, deterministic["id"])
            setattr(
                parent,
                field,
                {
                    "provider_version": "phase-3b",
                    "provenance_label": (
                        "Deterministic offline demo transcript mapped to a team-recorded "
                        "Malayalam/code-mixed lesson — not live STT."
                    ),
                    "provider_name": "shravya-deterministic-demo",
                }[field],
            )
            session.commit()
    accepted = migrated_api.client.post(
        f"/api/v1/teacher/transcript-revisions/{deterministic['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 19400, "text": "Corrected demo text"}
            ]
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["copied_from_transcript_revision_id"] == deterministic["id"]


def test_manual_segments_reject_backward_starts_and_allow_ordered_overlap(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    unknown = bytearray(_asset())
    unknown[-1] ^= 1
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=bytes(unknown),
        headers={"Content-Type": "audio/wav", "X-Filename": "local.wav"},
    ).json()["data"]
    backward = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 500, "end_ms": 1500, "text": "First"},
                {"sequence": 2, "start_ms": 0, "end_ms": 1000, "text": "Second"},
            ]
        },
    )
    assert backward.status_code == 422
    with migrated_api.session_factory() as session:
        assert (
            session.scalar(
                select(TranscriptRevision).where(
                    TranscriptRevision.lecture_audio_id == recording["id"]
                )
            )
            is None
        )
    overlap = migrated_api.client.post(
        f"/api/v1/teacher/recordings/{recording['id']}/manual-revision",
        json={
            "segments": [
                {"sequence": 1, "start_ms": 0, "end_ms": 7000, "text": "First"},
                {"sequence": 2, "start_ms": 0, "end_ms": 19400, "text": "Second"},
            ]
        },
    )
    assert overlap.status_code == 200


def test_upload_failures_compensate_media_without_path_disclosure(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    before = (
        set(get_settings().media_root.rglob("*.wav"))
        if get_settings().media_root.exists()
        else set()
    )
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        original_commit = session.commit
        calls = 0

        def fail_first_commit():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("simulated database commit failure")
            return original_commit()

        monkeypatch.setattr(session, "commit", fail_first_commit)
        try:
            service.upload(
                lesson_id,
                WavUpload(filename="one.wav", declared_mime_type="audio/wav", data=_asset()),
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected commit failure")
        assert (
            session.scalar(select(LectureAudio).where(LectureAudio.lesson_id == lesson_id)) is None
        )
        assert set(get_settings().media_root.rglob("*.wav")) == before
        assert session.scalar(select(MediaUploadIntent)) is None


def test_upload_write_and_flush_failures_leave_no_recording_or_media(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    before = set(get_settings().media_root.rglob("*.wav"))
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        original_write = Path.write_bytes

        def fail_write(path, data):
            if path.suffix == ".uploading":
                raise OSError("simulated media write failure")
            return original_write(path, data)

        monkeypatch.setattr(Path, "write_bytes", fail_write)
        try:
            service.upload(
                lesson_id,
                WavUpload(filename="write.wav", declared_mime_type="audio/wav", data=_asset()),
            )
        except OSError:
            pass
        else:
            raise AssertionError("expected write failure")
        assert (
            session.scalar(select(LectureAudio).where(LectureAudio.lesson_id == lesson_id)) is None
        )
        assert set(get_settings().media_root.rglob("*.wav")) == before
        monkeypatch.setattr(Path, "write_bytes", original_write)

        original_flush = session.flush
        failed = False

        def fail_first_flush(*args, **kwargs):
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("simulated database flush failure")
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", fail_first_flush)
        try:
            service.upload(
                lesson_id,
                WavUpload(filename="flush.wav", declared_mime_type="audio/wav", data=_asset()),
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected flush failure")
        assert (
            session.scalar(select(LectureAudio).where(LectureAudio.lesson_id == lesson_id)) is None
        )
        assert set(get_settings().media_root.rglob("*.wav")) == before


def test_failed_upload_unlink_creates_and_retries_durable_orphan_cleanup(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        original_commit = session.commit
        original_unlink = Path.unlink
        calls = 0

        def fail_first_commit():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("simulated commit failure")
            return original_commit()

        def fail_uploaded_unlink(path, *args, **kwargs):
            if path.parent.name == ".quarantine":
                raise OSError("simulated compensation failure")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(session, "commit", fail_first_commit)
        monkeypatch.setattr(Path, "unlink", fail_uploaded_unlink)
        try:
            service.upload(
                lesson_id,
                WavUpload(filename="orphan.wav", declared_mime_type="audio/wav", data=_asset()),
            )
        except (RuntimeError, DomainError):
            pass
        else:
            raise AssertionError("expected commit failure")
        tombstone = session.scalar(select(MediaUploadIntent))
        assert tombstone is not None
        orphan_path = get_settings().media_root / tombstone.quarantine_relative_path
        assert orphan_path.exists()
        monkeypatch.setattr(Path, "unlink", original_unlink)
        assert service.retry_pending_media_cleanup() == 1
        assert not orphan_path.exists()
        assert session.scalar(select(MediaUploadIntent)) is None


def test_wav_alias_is_stored_and_served_with_canonical_media_type(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    uploaded = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/x-wav", "X-Filename": "alias.wav"},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["data"]["mime_type"] == "audio/wav"
    content = migrated_api.client.get(
        f"/api/v1/teacher/recordings/{uploaded.json()['data']['id']}/content"
    )
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("audio/wav")
    assert str(get_settings().media_root.resolve()) not in str(content.headers)


def test_process_interruption_upload_recovery_uses_a_fresh_session(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id

    with migrated_api.session_factory() as interrupted_session:
        service = AudioWorkflowService(interrupted_session, get_settings())
        original_commit = interrupted_session.commit

        def interrupt_recording_commit():
            raise KeyboardInterrupt("simulated process interruption")

        monkeypatch.setattr(interrupted_session, "commit", interrupt_recording_commit)
        with pytest.raises(KeyboardInterrupt):
            service.upload(
                lesson_id,
                WavUpload(
                    filename="interrupted.wav", declared_mime_type="audio/wav", data=_asset()
                ),
            )
        monkeypatch.setattr(interrupted_session, "commit", original_commit)

    with migrated_api.session_factory() as recovery_session:
        recovery_service = AudioWorkflowService(recovery_session, get_settings())
        recovery_session.invalidate()
        # The recovery service has its own injected factory and does not reuse
        # the invalidated request session.
        assert recovery_service.recover_upload_intents() == 1
    with migrated_api.session_factory() as session:
        assert session.scalar(select(MediaUploadIntent)) is None
        assert (
            session.scalar(select(LectureAudio).where(LectureAudio.lesson_id == lesson_id)) is None
        )


def test_upload_recovery_uses_a_fresh_session_after_media_placement_failure(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id

    with migrated_api.session_factory() as interrupted_session:
        service = AudioWorkflowService(interrupted_session, get_settings())
        original_commit = interrupted_session.commit
        original_recovery = AudioWorkflowService.recover_upload_intents

        def invalidate_then_fail_recording_commit() -> None:
            interrupted_session.invalidate()
            raise RuntimeError("simulated post-placement persistence failure")

        monkeypatch.setattr(interrupted_session, "commit", invalidate_then_fail_recording_commit)
        # Keep the request's exception path from consuming the durable intent;
        # the separate recovery instance below must discover it.
        monkeypatch.setattr(AudioWorkflowService, "recover_upload_intents", lambda *_a, **_k: 0)
        with pytest.raises(RuntimeError):
            service.upload(
                lesson_id,
                WavUpload(filename="placed.wav", declared_mime_type="audio/wav", data=_asset()),
            )
        monkeypatch.setattr(interrupted_session, "commit", original_commit)
        monkeypatch.setattr(AudioWorkflowService, "recover_upload_intents", original_recovery)

    # The request session was invalidated. Recovery opens its own session and
    # removes the otherwise unreachable placement plus its durable intent.
    with migrated_api.session_factory() as recovery_session:
        assert AudioWorkflowService(recovery_session, get_settings()).recover_upload_intents() == 1
    with migrated_api.session_factory() as session:
        assert session.scalar(select(MediaUploadIntent)) is None
        assert (
            session.scalar(select(LectureAudio).where(LectureAudio.lesson_id == lesson_id)) is None
        )


def test_application_startup_recovers_a_durable_pre_commit_upload_intent(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        service = AudioWorkflowService(session, get_settings())
        sha256 = hashlib.sha256(_asset()).hexdigest()
        temporary, final = service._upload_paths(lesson_id, sha256)
        intent_id = service._prepare_upload_intent(
            lesson_id, sha256, len(_asset()), temporary, final
        )
        service._place_upload_media(temporary, final, _asset())
        service._set_upload_intent_status(intent_id, UploadIntentStatus.MEDIA_PLACED)
        assert final.exists()

    app = create_app()
    app.state.audio_session_factory = migrated_api.session_factory
    with TestClient(app, raise_server_exceptions=False):
        pass
    assert not final.exists()
    with migrated_api.session_factory() as session:
        assert session.scalar(select(MediaUploadIntent)) is None


def test_application_startup_recovers_safe_intents_and_retains_conflicts(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        other_context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        other_lesson_id = other_context.lesson.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "startup-owned.wav"},
    ).json()["data"]
    media_path = _media_path(migrated_api, recording["id"])
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        persisted = session.get(LectureAudio, recording["id"])
        assert persisted is not None
        safe_temporary, safe_final = service._upload_paths(
            other_lesson_id, hashlib.sha256(_asset()).hexdigest()
        )
        safe_id = service._prepare_upload_intent(
            other_lesson_id,
            hashlib.sha256(_asset()).hexdigest(),
            len(_asset()),
            safe_temporary,
            safe_final,
        )
        conflict = MediaUploadIntent(
            lesson_id=other_lesson_id,
            temporary_relative_path=f"{other_lesson_id}/startup-conflict.uploading",
            final_relative_path=media_path.relative_to(
                get_settings().media_root.resolve()
            ).as_posix(),
            sha256="f" * 64,
            byte_size=1,
            recording_id="wrong-recording",
            status=UploadIntentStatus.MEDIA_PLACED,
        )
        session.add(conflict)
        session.commit()
        conflict_id = conflict.id

    app = create_app()
    app.state.audio_session_factory = migrated_api.session_factory
    # A durable operator conflict is not a reason to make the whole service
    # unavailable; startup still cleans independent safe work.
    with TestClient(app, raise_server_exceptions=False):
        pass
    assert media_path.exists()
    with migrated_api.session_factory() as session:
        assert session.get(MediaUploadIntent, safe_id) is None
        retained = session.get(MediaUploadIntent, conflict_id)
        assert retained is not None
        assert retained.status is UploadIntentStatus.RECOVERY_CONFLICT
        assert str(get_settings().media_root.resolve()) not in (retained.conflict_code or "")


@pytest.mark.parametrize("mismatch", ["sha", "lesson", "recording", "byte_size"])
def test_upload_recovery_preserves_media_owned_by_mismatched_recording_intent(
    migrated_api, mismatch: str
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        other_context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        other_lesson_id = other_context.lesson.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "owned.wav"},
    ).json()["data"]
    original_media = _media_path(migrated_api, recording["id"]).read_bytes()
    with migrated_api.session_factory() as session:
        persisted = session.get(LectureAudio, recording["id"])
        assert persisted is not None
        final = Path(persisted.storage_path)
        intent = MediaUploadIntent(
            lesson_id=other_lesson_id if mismatch == "lesson" else lesson_id,
            temporary_relative_path=f"{lesson_id}/collision.uploading",
            final_relative_path=final.relative_to(get_settings().media_root.resolve()).as_posix(),
            sha256="f" * 64 if mismatch == "sha" else persisted.sha256,
            byte_size=1 if mismatch == "byte_size" else persisted.byte_size,
            recording_id="other-recording" if mismatch == "recording" else persisted.id,
            status=UploadIntentStatus.MEDIA_PLACED,
        )
        session.add(intent)
        session.commit()
        intent_id = intent.id
        service = AudioWorkflowService(session, get_settings())
        with pytest.raises(DomainError) as error:
            service.recover_upload_intents()
        assert error.value.code == "upload_recovery_conflict"
    with migrated_api.session_factory() as session:
        assert session.get(LectureAudio, recording["id"]) is not None
        conflict = session.get(MediaUploadIntent, intent_id)
        assert conflict is not None
        assert conflict.status is UploadIntentStatus.RECOVERY_CONFLICT
        assert conflict.conflict_code == "final_path_owned_by_other_recording"
    assert _media_path(migrated_api, recording["id"]).read_bytes() == original_media


def test_upload_recovery_reconciles_an_exact_committed_recording_without_unlink(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "exact.wav"},
    ).json()["data"]
    media_path = _media_path(migrated_api, recording["id"])
    original_unlink = Path.unlink
    unlinks = 0

    def count_unlink(path, *args, **kwargs):
        nonlocal unlinks
        if path == media_path:
            unlinks += 1
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", count_unlink)
    with migrated_api.session_factory() as session:
        persisted = session.get(LectureAudio, recording["id"])
        assert persisted is not None
        session.add(
            MediaUploadIntent(
                lesson_id=lesson_id,
                temporary_relative_path=f"{lesson_id}/exact.uploading",
                final_relative_path=media_path.relative_to(
                    get_settings().media_root.resolve()
                ).as_posix(),
                sha256=persisted.sha256,
                byte_size=persisted.byte_size,
                recording_id=persisted.id,
                status=UploadIntentStatus.RECORDING_COMMITTED,
            )
        )
        session.commit()
        assert AudioWorkflowService(session, get_settings()).recover_upload_intents() == 1
    assert media_path.exists()
    assert unlinks == 0


@pytest.mark.parametrize(
    ("status", "placed_file"),
    [
        (UploadIntentStatus.PREPARED, None),
        (UploadIntentStatus.PREPARED, "temporary"),
        # Covers a crash after atomic final placement and before the status
        # update from PREPARED to MEDIA_PLACED.
        (UploadIntentStatus.PREPARED, "final"),
        (UploadIntentStatus.MEDIA_PLACED, None),
        (UploadIntentStatus.RECORDING_COMMITTED, None),
        (UploadIntentStatus.COMPLETED, None),
    ],
)
def test_upload_recovery_cleans_safe_crash_states_idempotently(
    migrated_api, status: UploadIntentStatus, placed_file: str | None
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        service = AudioWorkflowService(session, get_settings())
        sha256 = hashlib.sha256(_asset()).hexdigest()
        temporary, final = service._upload_paths(lesson_id, sha256)
        intent_id = service._prepare_upload_intent(
            lesson_id, sha256, len(_asset()), temporary, final
        )
        if placed_file is not None:
            target = temporary if placed_file == "temporary" else final
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_asset())
        service._set_upload_intent_status(intent_id, status)
        assert service.recover_upload_intents() == 1
        assert service.recover_upload_intents() == 0
    assert not temporary.exists()
    assert not final.exists()
    with migrated_api.session_factory() as session:
        assert session.get(MediaUploadIntent, intent_id) is None


@pytest.mark.parametrize("placed_file", ["temporary", "final"])
def test_upload_recovery_preserves_replacement_crash_file_as_conflict(
    migrated_api, placed_file: str
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        service = AudioWorkflowService(session, get_settings())
        sha256 = hashlib.sha256(_asset()).hexdigest()
        temporary, final = service._upload_paths(lesson_id, sha256)
        intent_id = service._prepare_upload_intent(
            lesson_id, sha256, len(_asset()), temporary, final
        )
        target = temporary if placed_file == "temporary" else final
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"replacement, not the upload intent")
        with pytest.raises(DomainError) as error:
            service.recover_upload_intents()
        assert error.value.code == "upload_recovery_conflict"
    with migrated_api.session_factory() as session:
        intent = session.get(MediaUploadIntent, intent_id)
        assert intent is not None
        assert intent.status is UploadIntentStatus.RECOVERY_CONFLICT
        quarantine = get_settings().media_root / intent.quarantine_relative_path
        assert quarantine.read_bytes() == b"replacement, not the upload intent"
        assert str(get_settings().media_root.resolve()) not in (intent.conflict_code or "")
        assert (
            AudioWorkflowService(session, get_settings()).recover_upload_intents(
                raise_on_conflict=False
            )
            == 0
        )


def test_deletion_api_identity_rejects_unknown_and_wrong_context_and_retries_receipt(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        other_context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
        other_context_id = other_context.context.id
    unknown = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/unknown-recording"
    )
    assert unknown.status_code == 404
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "identity.wav"},
    ).json()["data"]
    wrong = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{other_context_id}/recordings/{recording['id']}"
    )
    assert wrong.status_code == 409
    removed = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
    )
    assert removed.status_code == 200
    assert (
        migrated_api.client.delete(
            f"/api/v1/curriculum/context-versions/{context_id}/recordings/{recording['id']}"
        ).status_code
        == 200
    )
    completed_wrong = migrated_api.client.delete(
        f"/api/v1/curriculum/context-versions/{other_context_id}/recordings/{recording['id']}"
    )
    assert completed_wrong.status_code == 409
    assert str(get_settings().media_root.resolve()) not in completed_wrong.text


def test_recording_deletion_retries_sqlite_busy_without_partial_mutation(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
        engine = session.get_bind()
    recording, _ = _upload_and_transcribe(migrated_api, lesson_id)

    with engine.connect() as lock_connection:
        lock_connection.exec_driver_sql("BEGIN IMMEDIATE")
        with migrated_api.session_factory() as blocked_session:
            blocked_session.execute(text("PRAGMA busy_timeout = 1"))
            rollback_count = 0
            original_rollback = blocked_session.rollback

            def count_rollback() -> None:
                nonlocal rollback_count
                rollback_count += 1
                original_rollback()

            blocked_session.rollback = count_rollback  # type: ignore[method-assign]
            with pytest.raises(DomainError) as error:
                AudioWorkflowService(blocked_session, get_settings()).delete_recording(
                    recording["id"], expected_context_version_id=context_id
                )
            assert error.value.code == "RECORDING_DELETION_IN_PROGRESS"
            assert rollback_count >= 3
        lock_connection.rollback()

    # No write made it through the held lock. Once it is released, the same
    # operation succeeds through the normal bounded retry/claim path.
    with migrated_api.session_factory() as session:
        assert session.get(LectureAudio, recording["id"]) is not None
        assert (
            session.scalar(
                select(RecordingDeletionTombstone).where(
                    RecordingDeletionTombstone.recording_id == recording["id"]
                )
            )
            is None
        )
        assert AudioWorkflowService(session, get_settings()).delete_recording(
            recording["id"], expected_context_version_id=context_id
        )


def test_deletion_lease_reclaim_and_replacement_file_protection(migrated_api, monkeypatch) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "lease.wav"},
    ).json()["data"]
    media_path = _media_path(migrated_api, recording["id"])

    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        active = session.get(LectureAudio, recording["id"])
        assert active is not None
        tombstone, created = service._create_or_load_deletion_tombstone(active, context_id)
        assert created
        session.delete(active)
        session.commit()
        first_owner = service._claim_deletion_cleanup(tombstone)
        assert first_owner is not None

    with migrated_api.session_factory() as session:
        tombstone = session.scalar(
            select(RecordingDeletionTombstone).where(
                RecordingDeletionTombstone.recording_id == recording["id"]
            )
        )
        assert tombstone is not None
        with pytest.raises(DomainError) as in_progress:
            AudioWorkflowService(session, get_settings())._claim_deletion_cleanup(tombstone)
        assert in_progress.value.code == "RECORDING_DELETION_IN_PROGRESS"
        # A non-owner cannot move a live claim to a terminal state.
        AudioWorkflowService(session, get_settings())._record_deletion_conflict(
            tombstone, "not-the-owner", "wrong_owner"
        )
        session.refresh(tombstone)
        assert tombstone.status.value == "CLEANUP_CLAIMED"
        tombstone.cleanup_lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    original_unlink = Path.unlink
    unlink_calls = 0

    def count_unlink(path, *args, **kwargs):
        nonlocal unlink_calls
        if path.parent.name == ".quarantine":
            unlink_calls += 1
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", count_unlink)
    replacement = b"replacement file must survive a reclaimed lease"
    media_path.write_bytes(replacement)
    with migrated_api.session_factory() as session:
        with pytest.raises(DomainError) as conflict:
            AudioWorkflowService(session, get_settings()).delete_recording(
                recording["id"], expected_context_version_id=context_id
            )
        assert conflict.value.code == "recording_cleanup_conflict"
    with migrated_api.session_factory() as session:
        tombstone = session.scalar(select(RecordingDeletionTombstone))
        assert tombstone is not None
        quarantine = get_settings().media_root / tombstone.quarantine_relative_path
        assert quarantine.read_bytes() == replacement
    assert unlink_calls == 0
    with migrated_api.session_factory() as session:
        tombstone = session.scalar(select(RecordingDeletionTombstone))
        assert tombstone is not None
        assert tombstone.status.value == "RECOVERY_CONFLICT"
        assert tombstone.conflict_code == "media_identity_mismatch"


def test_upload_quarantine_deletes_only_captured_media_and_preserves_replacement(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        service = AudioWorkflowService(session, get_settings())
        sha256 = hashlib.sha256(_asset()).hexdigest()
        temporary, final = service._upload_paths(lesson_id, sha256)
        intent_id = service._prepare_upload_intent(
            lesson_id, sha256, len(_asset()), temporary, final
        )
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(_asset())
        renames = 0
        original_rename = Path.rename

        def count_rename(path, target):
            nonlocal renames
            if path == final:
                renames += 1
            return original_rename(path, target)

        replacement = b"replacement created after quarantine capture"
        monkeypatch.setattr(Path, "rename", count_rename)
        monkeypatch.setattr(
            service,
            "_before_intent_quarantine_deletion",
            lambda _intent_id: final.write_bytes(replacement),
        )
        assert service.recover_upload_intents() == 1
        assert renames == 1
        assert final.read_bytes() == replacement
    with migrated_api.session_factory() as session:
        assert session.get(MediaUploadIntent, intent_id) is None


def test_media_placed_exact_owner_reconciles_only_when_current_bytes_match(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "placed-owner.wav"},
    ).json()["data"]
    media_path = _media_path(migrated_api, recording["id"])
    with migrated_api.session_factory() as session:
        persisted = session.get(LectureAudio, recording["id"])
        assert persisted is not None
        intent = MediaUploadIntent(
            lesson_id=lesson_id,
            temporary_relative_path=f"{lesson_id}/placed-owner.uploading",
            final_relative_path=media_path.relative_to(
                get_settings().media_root.resolve()
            ).as_posix(),
            quarantine_relative_path=".quarantine/placed-owner.media",
            sha256=persisted.sha256,
            byte_size=persisted.byte_size,
            recording_id=persisted.id,
            status=UploadIntentStatus.MEDIA_PLACED,
        )
        session.add(intent)
        session.commit()
        intent_id = intent.id
        assert AudioWorkflowService(session, get_settings()).recover_upload_intents() == 1
        session.expire_all()
        assert session.get(MediaUploadIntent, intent_id) is None

        replacement = b"current bytes no longer match the committed metadata"
        media_path.write_bytes(replacement)
        conflicting = MediaUploadIntent(
            lesson_id=lesson_id,
            temporary_relative_path=f"{lesson_id}/current-bytes.uploading",
            final_relative_path=media_path.relative_to(
                get_settings().media_root.resolve()
            ).as_posix(),
            quarantine_relative_path=".quarantine/current-bytes.media",
            sha256=persisted.sha256,
            byte_size=persisted.byte_size,
            recording_id=persisted.id,
            status=UploadIntentStatus.MEDIA_PLACED,
        )
        session.add(conflicting)
        session.commit()
        conflicting_id = conflicting.id
        with pytest.raises(DomainError) as error:
            AudioWorkflowService(session, get_settings()).recover_upload_intents()
        assert error.value.code == "upload_recovery_conflict"
    assert media_path.read_bytes() == replacement
    with migrated_api.session_factory() as session:
        assert session.get(LectureAudio, recording["id"]) is not None
        conflict = session.get(MediaUploadIntent, conflicting_id)
        assert conflict is not None
        assert conflict.status is UploadIntentStatus.RECOVERY_CONFLICT


def test_expired_lease_reuses_quarantine_and_never_touches_original_replacement(
    migrated_api, monkeypatch
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "expired-lease.wav"},
    ).json()["data"]
    original_path = _media_path(migrated_api, recording["id"])
    first_entered = Event()
    release_first = Event()
    hook_lock = Lock()
    hook_calls = 0
    first_outcome: list[str | None] = []
    original_unlink = Path.unlink
    original_rename = Path.rename
    quarantine_unlinks = 0
    quarantine_transfers = 0

    def count_quarantine_unlink(path, *args, **kwargs):
        nonlocal quarantine_unlinks
        if path.parent.name == ".quarantine":
            quarantine_unlinks += 1
        return original_unlink(path, *args, **kwargs)

    def count_quarantine_rename(path, target):
        nonlocal quarantine_transfers
        if path == original_path and Path(target).parent.name == ".quarantine":
            quarantine_transfers += 1
        return original_rename(path, target)

    def pause_first_cleanup(_tombstone_id: str, _owner_token: str) -> None:
        nonlocal hook_calls
        with hook_lock:
            hook_calls += 1
            is_first = hook_calls == 1
        if is_first:
            first_entered.set()
            assert release_first.wait(timeout=5)

    monkeypatch.setattr(
        AudioWorkflowService, "_before_quarantine_deletion", staticmethod(pause_first_cleanup)
    )
    monkeypatch.setattr(Path, "rename", count_quarantine_rename)
    monkeypatch.setattr(Path, "unlink", count_quarantine_unlink)

    def first_worker() -> None:
        with migrated_api.session_factory() as session:
            try:
                assert AudioWorkflowService(session, get_settings()).delete_recording(
                    recording["id"], expected_context_version_id=context_id
                )
            except DomainError as error:
                first_outcome.append(error.code)
            else:
                first_outcome.append(None)

    first = Thread(target=first_worker)
    first.start()
    assert first_entered.wait(timeout=5)
    with migrated_api.session_factory() as session:
        tombstone = session.scalar(select(RecordingDeletionTombstone))
        assert tombstone is not None
        tombstone.cleanup_lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    replacement = b"must remain at the original pathname"
    original_path.write_bytes(replacement)
    with migrated_api.session_factory() as session:
        assert AudioWorkflowService(session, get_settings()).delete_recording(
            recording["id"], expected_context_version_id=context_id
        )
    release_first.set()
    first.join(timeout=5)
    assert not first.is_alive()
    assert first_outcome == ["RECORDING_DELETION_IN_PROGRESS"]
    assert hook_calls == 2
    assert quarantine_transfers == 1
    assert quarantine_unlinks == 1
    assert original_path.read_bytes() == replacement
    with migrated_api.session_factory() as session:
        receipt = session.scalar(select(RecordingDeletionTombstone))
        assert receipt is not None
        assert receipt.status.value == "COMPLETED"


def test_missing_quarantine_after_worker_crash_completes_without_touching_replacement(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        context_id = context.context.id
    recording = migrated_api.client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/recordings",
        content=_asset(),
        headers={"Content-Type": "audio/wav", "X-Filename": "crash-after-delete.wav"},
    ).json()["data"]
    original_path = _media_path(migrated_api, recording["id"])
    with migrated_api.session_factory() as session:
        service = AudioWorkflowService(session, get_settings())
        active = session.get(LectureAudio, recording["id"])
        assert active is not None
        tombstone, _ = service._create_or_load_deletion_tombstone(active, context_id)
        session.delete(active)
        session.commit()
        owner = service._claim_deletion_cleanup(tombstone)
        assert owner is not None
        quarantine = service._quarantine_tombstone_media(tombstone, owner)
        assert quarantine is not None
        quarantine.unlink()  # Simulates crash after verified quarantine deletion.
    replacement = b"new file after the crashed cleanup"
    original_path.write_bytes(replacement)
    with migrated_api.session_factory() as session:
        tombstone = session.scalar(select(RecordingDeletionTombstone))
        assert tombstone is not None
        tombstone.cleanup_lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
        assert AudioWorkflowService(session, get_settings()).delete_recording(
            recording["id"], expected_context_version_id=context_id
        )
    assert original_path.read_bytes() == replacement
    with migrated_api.session_factory() as session:
        receipt = session.scalar(select(RecordingDeletionTombstone))
        assert receipt is not None
        assert receipt.status.value == "COMPLETED"


def test_startup_retains_root_escaping_intent_without_touching_external_path(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session)
        session.commit()
        lesson_id = context.lesson.id
        session.execute(text("PRAGMA ignore_check_constraints = ON"))
        session.execute(
            text(
                "INSERT INTO media_upload_intents "
                "(id, created_at, updated_at, lesson_id, temporary_relative_path, "
                "final_relative_path, sha256, byte_size, status) VALUES "
                "('root-escaping-intent', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :lesson_id, "
                "'../outside.uploading', '../outside.wav', :sha256, 1, 'PREPARED')"
            ),
            {"lesson_id": lesson_id, "sha256": "0" * 64},
        )
        session.execute(text("PRAGMA ignore_check_constraints = OFF"))
        session.commit()
    external_path = (get_settings().media_root / "../outside.wav").resolve()
    app = create_app()
    app.state.audio_session_factory = migrated_api.session_factory
    with TestClient(app, raise_server_exceptions=False) as client:
        health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert str(get_settings().media_root.resolve()) not in health.text
    assert not external_path.exists()
    with migrated_api.session_factory() as session:
        intent = session.get(MediaUploadIntent, "root-escaping-intent")
        assert intent is not None
        assert intent.status is UploadIntentStatus.RECOVERY_CONFLICT
        assert intent.conflict_code == "unsafe_relative_path"
