from __future__ import annotations

import hashlib
import logging
import re
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.contracts.enums import (
    JobStatus,
    ProcessingJobType,
    QualityStatus,
    RecordingDeletionStatus,
    RecordingWorkflowStatus,
    SourceStatus,
    TeacherReviewStatus,
    TermDecisionValue,
    UploadIntentStatus,
)
from app.contracts.teacher_review import DomainError
from app.core.config import Settings
from app.models.foundation import (
    Chapter,
    CourseContextVersion,
    LectureAudio,
    Lesson,
    MediaUploadIntent,
    ProcessingJob,
    RecordingDeletionTombstone,
    TermDecision,
    TermSuggestion,
    TranscriptionRunEvidence,
    TranscriptQualityAssessment,
    TranscriptQualityReason,
    TranscriptRevision,
    TranscriptSegment,
    utcnow,
)
from app.services.teacher_review import assert_context_mutable
from app.services.transcript_provenance import (
    DETERMINISTIC_DEMO_PROVENANCE,
    PHASE_3B_PROVIDER_VERSION,
    TEACHER_CORRECTED_DEMO_PROVENANCE,
    TEACHER_CORRECTED_PROVIDER,
    TEACHER_ENTERED_DEMO_PROVENANCE,
    TEACHER_ENTERED_PROVENANCE,
    TEACHER_ENTERED_PROVIDER,
    is_recognised_deterministic_demo_parent,
    recognised_provenance,
)
from app.services.transcript_quality import TranscriptQualityFinding, evaluate_transcript_quality
from app.services.transcription_provider import (
    DETERMINISTIC_DEMO_PROVIDER,
    LOCAL_FASTER_WHISPER_PROVENANCE,
    DeterministicDemoTranscriptionProvider,
    ProviderTranscription,
    TranscriptionInput,
    TranscriptionProvider,
    provider_for_settings,
    raw_output_json,
)

_ALLOWED_MIME_TYPES = {"audio/wav", "audio/x-wav"}
_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_CLEANUP_LEASE_SECONDS = 15
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WavUpload:
    filename: str
    declared_mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class DemoSegment:
    start_ms: int
    end_ms: int
    text: str
    sequence: int | None = None


@dataclass(frozen=True, slots=True)
class WavMetadata:
    audio_format: str
    sample_rate_hz: int
    channel_count: int
    sample_width_bits: int
    frame_count: int
    duration_ms: int


def parse_wav_metadata(data: bytes) -> WavMetadata:
    """Parse only standard WAV container metadata; callers retain typed file validation."""

    try:
        with wave.open(BytesIO(data), "rb") as wav:
            frame_count = wav.getnframes()
            sample_rate_hz = wav.getframerate()
            metadata = WavMetadata(
                audio_format="PCM" if wav.getcomptype() == "NONE" else wav.getcomptype(),
                sample_rate_hz=sample_rate_hz,
                channel_count=wav.getnchannels(),
                sample_width_bits=wav.getsampwidth() * 8,
                frame_count=frame_count,
                duration_ms=round(frame_count / sample_rate_hz * 1000),
            )
    except (EOFError, wave.Error, ZeroDivisionError) as error:
        raise DomainError("wav_parse_invalid", "audio.wav_parse_invalid", "validation") from error
    if (
        metadata.duration_ms <= 0
        or metadata.sample_rate_hz <= 0
        or metadata.channel_count <= 0
        or metadata.sample_width_bits <= 0
        or metadata.frame_count <= 0
    ):
        raise DomainError("wav_metadata_invalid", "audio.wav_metadata_invalid", "validation")
    return metadata


@dataclass(frozen=True, slots=True)
class AudioWorkflowCapabilities:
    can_start_processing: bool
    can_retry_processing: bool
    can_enter_manual_transcript: bool
    can_edit_transcript: bool
    can_assess_quality: bool
    can_approve_transcript: bool
    can_remove_recording: bool


@dataclass(frozen=True, slots=True)
class AudioWorkflowSnapshot:
    context_version_id: str
    state: str
    recording: LectureAudio | None
    job: ProcessingJob | None
    revision: TranscriptRevision | None
    assessment: TranscriptQualityAssessment | None
    findings: tuple[TranscriptQualityFinding, ...]
    measured_coverage: float | None
    tombstone: RecordingDeletionTombstone | None
    capabilities: AudioWorkflowCapabilities


class AudioWorkflowService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        now: Callable[[], datetime] = utcnow,
        session_factory: sessionmaker[Session] | None = None,
        provider: TranscriptionProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._now = now
        self._session_factory = session_factory or sessionmaker(
            bind=session.get_bind(), autocommit=False, autoflush=False
        )
        self._provider = provider or provider_for_settings(settings, self._demo_manifest_path())

    @staticmethod
    def _demo_manifest_path() -> Path:
        return (
            Path(__file__).resolve().parents[1] / "demo" / "assets" / "photosynthesis-demo.wav.json"
        )

    def upload(self, lesson_id: str, upload: WavUpload) -> LectureAudio:
        self._assert_context_mutable_for_lesson(lesson_id)
        self.recover_upload_intents()
        filename = self._sanitize_filename(upload.filename)
        metadata = self._validate_wav(filename, upload.declared_mime_type, upload.data)
        sha256 = hashlib.sha256(upload.data).hexdigest()
        existing = self._session.scalar(
            select(LectureAudio).where(
                LectureAudio.lesson_id == lesson_id, LectureAudio.sha256 == sha256
            )
        )
        if existing is not None:
            return existing
        temporary_path, storage_path = self._upload_paths(lesson_id, sha256)
        intent_id = self._prepare_upload_intent(
            lesson_id, sha256, len(upload.data), temporary_path, storage_path
        )
        try:
            self._place_upload_media(temporary_path, storage_path, upload.data)
            self._set_upload_intent_status(intent_id, UploadIntentStatus.MEDIA_PLACED)
        except Exception:
            self.recover_upload_intents()
            raise
        recording = LectureAudio(
            lesson_id=lesson_id,
            storage_path=str(storage_path),
            original_filename=filename,
            mime_type="audio/wav",
            byte_size=len(upload.data),
            sha256=sha256,
            duration_ms=metadata.duration_ms,
            audio_format=metadata.audio_format,
            sample_rate_hz=metadata.sample_rate_hz,
            channel_count=metadata.channel_count,
            sample_width_bits=metadata.sample_width_bits,
            frame_count=metadata.frame_count,
            source_status=(
                SourceStatus.DEMO
                if isinstance(self._provider, DeterministicDemoTranscriptionProvider)
                and self._provider.matches_fixture_sha(sha256)
                else SourceStatus.LOCAL_TEACHER
            ),
            workflow_status=RecordingWorkflowStatus.UPLOADED,
        )
        self._session.add(recording)
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            self.recover_upload_intents()
            raise
        self._set_upload_intent_status(
            intent_id, UploadIntentStatus.RECORDING_COMMITTED, recording.id
        )
        self._complete_upload_intent(intent_id)
        return recording

    def recover_upload_intents(self, *, raise_on_conflict: bool = True) -> int:
        """Recover upload state through an independent session after crashes or failed requests."""

        with self._session_factory() as recovery:
            intents = list(recovery.scalars(select(MediaUploadIntent)))
            recovered = 0
            conflicts = 0
            for intent in intents:
                if intent.status is UploadIntentStatus.RECOVERY_CONFLICT:
                    conflicts += 1
                    continue
                try:
                    temporary = self._intent_path(intent.temporary_relative_path)
                    final = self._intent_path(intent.final_relative_path)
                except DomainError:
                    self._mark_upload_conflict(intent, "unsafe_relative_path")
                    conflicts += 1
                    continue
                occupant = recovery.scalar(
                    select(LectureAudio).where(LectureAudio.storage_path == str(final))
                )
                if occupant is not None:
                    if self._intent_matches_recording(
                        intent, occupant, final
                    ) and self._file_matches(final, occupant.sha256, occupant.byte_size):
                        recovery.delete(intent)
                        recovered += 1
                    else:
                        self._mark_upload_conflict(intent, "final_path_owned_by_other_recording")
                        conflicts += 1
                    continue
                try:
                    if not self._quarantine_and_remove_intent_file(temporary, intent):
                        self._mark_upload_conflict(intent, "temporary_file_identity_mismatch")
                        conflicts += 1
                        continue
                    if not self._quarantine_and_remove_intent_file(final, intent):
                        self._mark_upload_conflict(intent, "final_file_identity_mismatch")
                        conflicts += 1
                        continue
                except OSError as error:
                    recovery.rollback()
                    raise DomainError(
                        "upload_cleanup_pending", "audio.upload_cleanup_pending", "conflict"
                    ) from error
                recovery.delete(intent)
                recovered += 1
            if recovered or conflicts:
                recovery.commit()
            if conflicts:
                logger.warning(
                    "Audio upload recovery retained %d unresolved conflict intent(s); "
                    "operator action is required.",
                    conflicts,
                )
            if conflicts and raise_on_conflict:
                raise DomainError(
                    "upload_recovery_conflict", "audio.upload_recovery_conflict", "conflict"
                )
            return recovered

    # Kept as the operational recovery entry point for the CLI/startup hook and
    # for an operator retry after a transient filesystem failure.
    def retry_pending_media_cleanup(self) -> int:
        return self.recover_upload_intents()

    def get_recording(self, recording_id: str) -> LectureAudio:
        return self._recording(recording_id)

    def recording_path(self, recording_id: str) -> Path:
        return self._storage_path(self._recording(recording_id), require_file=True)

    def _storage_path(self, recording: LectureAudio, *, require_file: bool) -> Path:
        root = self._settings.media_root.resolve()
        path = Path(recording.storage_path).resolve()
        if root not in path.parents or (require_file and not path.is_file()):
            raise DomainError(
                "recording_file_unavailable", "audio.recording_file_unavailable", "not_found"
            )
        return path

    def get_revision(self, revision_id: str) -> TranscriptRevision:
        return self._revision(revision_id)

    def get_job(self, job_id: str) -> ProcessingJob:
        return self._job(job_id)

    def get_workflow_summary(self, context_version_id: str) -> AudioWorkflowSnapshot:
        """Return a fail-closed projection of durable teacher audio workflow evidence."""

        context = self._session.scalar(
            select(CourseContextVersion)
            .where(CourseContextVersion.id == context_version_id)
            .options(
                selectinload(CourseContextVersion.chapters)
                .selectinload(Chapter.lessons)
                .options(
                    selectinload(Lesson.glossary_terms),
                    selectinload(Lesson.audio_assets)
                    .selectinload(LectureAudio.transcript_revisions)
                    .selectinload(TranscriptRevision.segments)
                    .selectinload(TranscriptSegment.term_suggestions)
                    .selectinload(TermSuggestion.decisions),
                    selectinload(Lesson.audio_assets)
                    .selectinload(LectureAudio.transcript_revisions)
                    .selectinload(TranscriptRevision.quality_assessments)
                    .selectinload(TranscriptQualityAssessment.reasons),
                )
            )
        )
        if context is None:
            raise DomainError("context_not_found", "context.not_found", "not_found")

        recordings = [
            asset
            for chapter in context.chapters
            for lesson in chapter.lessons
            for asset in lesson.audio_assets
        ]
        recording = max(recordings, key=lambda item: (item.created_at, item.id), default=None)
        tombstone = self._session.scalar(
            select(RecordingDeletionTombstone)
            .where(RecordingDeletionTombstone.context_version_id == context.id)
            .order_by(
                RecordingDeletionTombstone.created_at.desc(), RecordingDeletionTombstone.id.desc()
            )
            .limit(1)
        )
        if tombstone is not None and tombstone.status is RecordingDeletionStatus.COMPLETED:
            tombstone = None

        job = (
            self._session.scalar(
                select(ProcessingJob)
                .where(
                    ProcessingJob.job_type == ProcessingJobType.TRANSCRIPTION,
                    ProcessingJob.entity_id == recording.id,
                )
                .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                .limit(1)
            )
            if recording is not None
            else None
        )
        revision = self._latest_revision(recording.id) if recording is not None else None
        assessment = (
            max(
                revision.quality_assessments,
                key=lambda item: (item.created_at, item.id),
                default=None,
            )
            if revision is not None
            else None
        )
        findings = (
            evaluate_transcript_quality(
                revision,
                self._settings.demo_minimum_timestamp_coverage,
                latest_revision_id=revision.id,
            )
            if revision is not None
            else ()
        )
        measured_coverage = self._timestamp_coverage(revision) if revision is not None else None
        state = self._derived_workflow_state(
            recording, job, revision, assessment, findings, tombstone
        )
        mutable = context.teacher_review_status is TeacherReviewStatus.DRAFT
        quality_verified = bool(
            revision is not None
            and assessment is not None
            and assessment.quality_status is QualityStatus.VERIFIED
            and not findings
        )
        capabilities = AudioWorkflowCapabilities(
            can_start_processing=bool(
                mutable
                and recording is not None
                and (job is None or job.status in {JobStatus.FAILED, JobStatus.CANCELLED})
                and tombstone is None
            ),
            can_retry_processing=bool(
                mutable
                and recording is not None
                and job is not None
                and job.status in {JobStatus.FAILED, JobStatus.CANCELLED}
                and tombstone is None
            ),
            can_enter_manual_transcript=bool(
                mutable
                and recording is not None
                and (
                    revision is None
                    or revision.teacher_review_status is not TeacherReviewStatus.APPROVED
                )
                and tombstone is None
            ),
            can_edit_transcript=bool(
                mutable
                and revision is not None
                and revision.teacher_review_status is not TeacherReviewStatus.APPROVED
                and tombstone is None
            ),
            can_assess_quality=bool(
                mutable
                and revision is not None
                and revision.teacher_review_status is not TeacherReviewStatus.APPROVED
                and tombstone is None
            ),
            can_approve_transcript=bool(
                mutable
                and revision is not None
                and revision.teacher_review_status is not TeacherReviewStatus.APPROVED
                and quality_verified
                and tombstone is None
            ),
            can_remove_recording=bool(mutable and recording is not None and tombstone is None),
        )
        return AudioWorkflowSnapshot(
            context_version_id=context.id,
            state=state,
            recording=recording,
            job=job,
            revision=revision,
            assessment=assessment,
            findings=findings,
            measured_coverage=measured_coverage,
            tombstone=tombstone,
            capabilities=capabilities,
        )

    def request_transcription(self, recording_id: str) -> ProcessingJob:
        recording = self._recording(recording_id)
        self._assert_context_mutable_for_lesson(recording.lesson_id)
        existing = self._session.scalar(
            select(ProcessingJob).where(
                ProcessingJob.job_type == ProcessingJobType.TRANSCRIPTION,
                ProcessingJob.entity_id == recording.id,
            )
        )
        if existing is not None:
            if existing.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                existing.status = JobStatus.QUEUED
                existing.started_at = None
                existing.completed_at = None
                existing.error_code = None
                existing.recoverable = None
                existing.result_transcript_revision_id = None
                existing.progress_message = self._queued_transcription_message()
                existing.retry_count += 1
                recording.workflow_status = RecordingWorkflowStatus.TRANSCRIBING
                self._session.commit()
            return existing
        job = ProcessingJob(
            lesson_id=recording.lesson_id,
            job_type=ProcessingJobType.TRANSCRIPTION,
            entity_id=recording.id,
            status=JobStatus.QUEUED,
            progress_message=self._queued_transcription_message(),
            retry_count=0,
        )
        recording.workflow_status = RecordingWorkflowStatus.TRANSCRIBING
        self._session.add(job)
        self._session.commit()
        return job

    def run_job(self, job_id: str) -> ProcessingJob:
        job = self._job(job_id)
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            return job
        if job.job_type is not ProcessingJobType.TRANSCRIPTION:
            raise DomainError("unsupported_job", "audio.job_unsupported", "validation")
        recording = self._recording(job.entity_id)
        self._assert_context_mutable_for_lesson(recording.lesson_id)
        job.status = JobStatus.RUNNING
        job.started_at = self._now()
        job.progress_message = self._running_transcription_message()
        self._session.flush()
        try:
            result = self._provider.transcribe(
                TranscriptionInput(
                    source_sha256=recording.sha256,
                    source_duration_ms=recording.duration_ms,
                    audio_path=self._storage_path(recording, require_file=True),
                )
            )
        except DomainError as error:
            return self._fail_transcription_job(job, recording, error.code)
        except Exception:
            return self._fail_transcription_job(job, recording, "local_stt_inference_failed")
        if result is None:
            job.status = JobStatus.FAILED
            job.completed_at = self._now()
            job.error_code = "demo_audio_unrecognized"
            job.recoverable = True
            job.progress_message = "No offline demo transcript is available for this recording"
            recording.workflow_status = RecordingWorkflowStatus.MANUAL_TRANSCRIPT_REQUIRED
            self._session.commit()
            return job
        try:
            revision = self._new_revision(
                recording,
                tuple(
                    DemoSegment(
                        start_ms=item.start_ms,
                        end_ms=item.end_ms,
                        text=item.text,
                        sequence=index,
                    )
                    for index, item in enumerate(result.segments, 1)
                ),
                source_status=(
                    SourceStatus.DEMO
                    if result.provider_implementation == DETERMINISTIC_DEMO_PROVIDER
                    else SourceStatus.LOCAL_TEACHER
                ),
                provider_name=result.provider_implementation,
                provider_version=result.provider_version,
                provenance=self._provider_provenance(result),
                evidence=(
                    None
                    if result.provider_implementation == DETERMINISTIC_DEMO_PROVIDER
                    else result
                ),
            )
        except Exception:
            self._session.rollback()
            return self._fail_transcription_job(job, recording, "local_stt_evidence_write_failed")
        job.status = JobStatus.SUCCEEDED
        job.completed_at = self._now()
        job.progress_message = "Transcript ready for teacher review"
        job.result_transcript_revision_id = revision.id
        recording.workflow_status = RecordingWorkflowStatus.NEEDS_REVIEW
        self._session.commit()
        return job

    def record_decision(
        self, suggestion_id: str, decision: TermDecisionValue
    ) -> TranscriptRevision:
        suggestion = self._session.get(TermSuggestion, suggestion_id)
        if suggestion is None:
            raise DomainError(
                "term_suggestion_not_found", "audio.suggestion_not_found", "not_found"
            )
        revision = suggestion.transcript_segment.transcript_revision
        self._assert_revision_mutable(revision)
        self._session.add(
            TermDecision(
                term_suggestion_id=suggestion.id, decision=decision, decided_by_role="teacher"
            )
        )
        self._invalidate_assessment(revision)
        revision.lecture_audio.workflow_status = RecordingWorkflowStatus.NEEDS_REVIEW
        self._session.commit()
        return revision

    def create_manual_revision(
        self, revision_id: str, segments: list[DemoSegment]
    ) -> TranscriptRevision:
        source = self._revision(revision_id)
        self._assert_revision_mutable(source)
        if not segments:
            raise DomainError(
                "manual_transcript_empty", "audio.manual_transcript_empty", "validation"
            )
        recording = source.lecture_audio
        self._validate_manual_segments(recording, segments)
        source_status, provider_name, provenance = self._manual_revision_provenance(source)
        revision = self._new_revision(
            recording,
            tuple(segments),
            source_status=source_status,
            provider_name=provider_name,
            provenance=provenance,
            copied_from_id=source.id,
        )
        self._invalidate_assessment(source)
        recording.workflow_status = RecordingWorkflowStatus.NEEDS_REVIEW
        self._session.commit()
        return revision

    def create_manual_revision_for_recording(
        self, recording_id: str, segments: list[DemoSegment]
    ) -> TranscriptRevision:
        recording = self._recording(recording_id)
        self._assert_context_mutable_for_lesson(recording.lesson_id)
        if self._latest_revision(recording.id) is not None:
            raise DomainError(
                "transcript_revision_exists",
                "audio.transcript_revision_exists",
                "validation",
            )
        if not segments:
            raise DomainError(
                "manual_transcript_empty", "audio.manual_transcript_empty", "validation"
            )
        self._validate_manual_segments(recording, segments)
        source_status, provider_name, provenance = self._manual_first_provenance(recording)
        revision = self._new_revision(
            recording,
            tuple(segments),
            source_status=source_status,
            provider_name=provider_name,
            provenance=provenance,
        )
        recording.workflow_status = RecordingWorkflowStatus.NEEDS_REVIEW
        self._session.commit()
        return revision

    def assess_quality(self, revision_id: str) -> TranscriptQualityAssessment:
        revision = self._revision(revision_id)
        self._assert_revision_mutable(revision)
        assessment = self._replace_assessment(revision)
        revision.lecture_audio.workflow_status = (
            RecordingWorkflowStatus.TRANSCRIPT_READY
            if assessment.quality_status is QualityStatus.VERIFIED
            else RecordingWorkflowStatus.NEEDS_REVIEW
        )
        self._session.commit()
        return assessment

    def approve_transcript(self, revision_id: str) -> TranscriptRevision:
        revision = self._revision(revision_id)
        self._assert_revision_mutable(revision)
        if self._latest_revision(revision.lecture_audio_id).id != revision.id:
            raise DomainError("transcript_not_latest", "audio.transcript_not_latest", "validation")
        assessment = self._replace_assessment(revision)
        if assessment.quality_status is not QualityStatus.VERIFIED:
            revision.lecture_audio.workflow_status = RecordingWorkflowStatus.NEEDS_REVIEW
            self._session.commit()
            raise DomainError(
                "transcript_quality_blocked", "audio.transcript_quality_blocked", "validation"
            )
        revision.teacher_review_status = TeacherReviewStatus.APPROVED
        revision.approved_at = self._now()
        revision.approved_by_role = "teacher"
        revision.lecture_audio.workflow_status = RecordingWorkflowStatus.APPROVED
        self._session.commit()
        return revision

    def delete_recording(
        self, recording_id: str, *, expected_context_version_id: str | None = None
    ) -> bool:
        for attempt in range(3):
            try:
                return self._delete_recording_once(recording_id, expected_context_version_id)
            except OperationalError as error:
                self._session.rollback()
                if not self._is_sqlite_busy(error):
                    raise
                if attempt == 2:
                    raise DomainError(
                        "RECORDING_DELETION_IN_PROGRESS",
                        "audio.recording_deletion_in_progress",
                        "conflict",
                    ) from error
                time.sleep(0.01 * (attempt + 1))
        raise AssertionError("bounded deletion retry must return or raise")

    def _delete_recording_once(
        self, recording_id: str, expected_context_version_id: str | None
    ) -> bool:
        recording = self._session.get(LectureAudio, recording_id)
        if recording is None:
            tombstone = self._session.scalar(
                select(RecordingDeletionTombstone).where(
                    RecordingDeletionTombstone.recording_id == recording_id
                )
            )
            if tombstone is None:
                raise DomainError("recording_not_found", "audio.recording_not_found", "not_found")
            if (
                expected_context_version_id is not None
                and tombstone.context_version_id != expected_context_version_id
            ):
                raise DomainError(
                    "recording_context_mismatch", "audio.recording_context_mismatch", "conflict"
                )
            if tombstone.status is RecordingDeletionStatus.COMPLETED:
                return True
            return self._finish_deletion(tombstone, expected_context_version_id)
        self._assert_context_mutable_for_lesson(recording.lesson_id)
        context_version_id = self._context_id_for_lesson(recording.lesson_id)
        if (
            expected_context_version_id is not None
            and expected_context_version_id != context_version_id
        ):
            raise DomainError(
                "recording_context_mismatch", "audio.recording_context_mismatch", "conflict"
            )
        tombstone, created = self._create_or_load_deletion_tombstone(recording, context_version_id)
        if tombstone.context_version_id != context_version_id:
            raise DomainError(
                "recording_context_mismatch", "audio.recording_context_mismatch", "conflict"
            )
        if not created:
            if tombstone.status is RecordingDeletionStatus.COMPLETED:
                return True
            return self._finish_deletion(tombstone, context_version_id)
        try:
            for job in self._session.scalars(
                select(ProcessingJob).where(ProcessingJob.entity_id == recording.id)
            ):
                self._session.delete(job)
            self._session.delete(recording)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._finish_deletion(tombstone, context_version_id)

    def _new_revision(
        self,
        recording: LectureAudio,
        segments: tuple[DemoSegment, ...],
        *,
        source_status: SourceStatus,
        provider_name: str,
        provenance: str,
        provider_version: str | None = PHASE_3B_PROVIDER_VERSION,
        copied_from_id: str | None = None,
        evidence: ProviderTranscription | None = None,
    ) -> TranscriptRevision:
        revision = TranscriptRevision(
            lecture_audio_id=recording.id,
            revision_number=(
                self._session.scalar(
                    select(TranscriptRevision.revision_number)
                    .where(TranscriptRevision.lecture_audio_id == recording.id)
                    .order_by(TranscriptRevision.revision_number.desc())
                    .limit(1)
                )
                or 0
            )
            + 1,
            source_status=source_status,
            language="ml",
            copied_from_transcript_revision_id=copied_from_id,
            provider_name=provider_name,
            provider_version=provider_version,
            provenance_label=provenance,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        )
        self._session.add(revision)
        self._session.flush()
        for position, segment in enumerate(segments, 1):
            item = TranscriptSegment(
                transcript_revision_id=revision.id,
                sequence=segment.sequence if segment.sequence is not None else position,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                confidence=None,
            )
            self._session.add(item)
            self._session.flush()
            self._suggest_terms(item)
        if evidence is not None:
            self._session.add(
                TranscriptionRunEvidence(
                    transcript_revision_id=revision.id,
                    source_lecture_audio_id=recording.id,
                    source_sha256=recording.sha256,
                    source_duration_ms=recording.duration_ms,
                    provider_mode=evidence.provider_mode,
                    provider_implementation=evidence.provider_implementation,
                    provider_version=evidence.provider_version,
                    ctranslate2_version=evidence.ctranslate2_version,
                    model_identifier=evidence.model_identifier,
                    device=evidence.device,
                    compute_type=evidence.compute_type,
                    language_requested=evidence.language_requested,
                    language_detected=evidence.language_detected,
                    language_probability=evidence.language_probability,
                    multilingual=evidence.multilingual,
                    beam_size=evidence.beam_size,
                    vad_filter=evidence.vad_filter,
                    word_timestamps=evidence.word_timestamps,
                    transcription_started_at=evidence.transcription_started_at,
                    transcription_completed_at=evidence.transcription_completed_at,
                    model_load_seconds=evidence.model_load_seconds,
                    inference_seconds=evidence.inference_seconds,
                    raw_provider_output_json=raw_output_json(evidence),
                )
            )
        return revision

    def _suggest_terms(self, segment: TranscriptSegment) -> None:
        lesson = segment.transcript_revision.lecture_audio.lesson
        for term in lesson.glossary_terms:
            for variant in term.misrecognitions:
                start = segment.text.casefold().find(variant.detected_text.casefold())
                if start >= 0:
                    self._session.add(
                        TermSuggestion(
                            transcript_segment_id=segment.id,
                            glossary_term_id=term.id,
                            detected_text=segment.text[start : start + len(variant.detected_text)],
                            character_start=start,
                            character_end=start + len(variant.detected_text),
                            match_score=1.0,
                            context_snapshot=segment.text,
                        )
                    )

    def _latest_revision(self, recording_id: str) -> TranscriptRevision | None:
        return self._session.scalar(
            select(TranscriptRevision)
            .where(TranscriptRevision.lecture_audio_id == recording_id)
            .order_by(TranscriptRevision.revision_number.desc(), TranscriptRevision.id.desc())
            .limit(1)
        )

    @staticmethod
    def _manual_revision_provenance(source: TranscriptRevision) -> tuple[SourceStatus, str, str]:
        if source.source_status is SourceStatus.DEMO:
            if not is_recognised_deterministic_demo_parent(source):
                raise DomainError(
                    "transcript_provenance_invalid",
                    "audio.transcript_provenance_invalid",
                    "validation",
                )
            return (
                SourceStatus.DEMO,
                TEACHER_CORRECTED_PROVIDER,
                TEACHER_CORRECTED_DEMO_PROVENANCE,
            )
        if not recognised_provenance(source).supported:
            raise DomainError(
                "transcript_provenance_invalid", "audio.transcript_provenance_invalid", "validation"
            )
        return (
            SourceStatus.LOCAL_TEACHER,
            TEACHER_ENTERED_PROVIDER,
            TEACHER_ENTERED_PROVENANCE,
        )

    @staticmethod
    def _manual_first_provenance(recording: LectureAudio) -> tuple[SourceStatus, str, str]:
        if recording.source_status is SourceStatus.DEMO:
            return (
                SourceStatus.DEMO,
                TEACHER_ENTERED_PROVIDER,
                TEACHER_ENTERED_DEMO_PROVENANCE,
            )
        if recording.source_status is SourceStatus.LOCAL_TEACHER:
            return (
                SourceStatus.LOCAL_TEACHER,
                TEACHER_ENTERED_PROVIDER,
                TEACHER_ENTERED_PROVENANCE,
            )
        raise DomainError(
            "transcript_provenance_invalid", "audio.transcript_provenance_invalid", "validation"
        )

    @staticmethod
    def _validate_manual_segments(recording: LectureAudio, segments: list[DemoSegment]) -> None:
        if recording.duration_ms <= 0 or not segments:
            raise DomainError(
                "manual_transcript_invalid", "audio.manual_transcript_invalid", "validation"
            )
        sequences = [
            segment.sequence if segment.sequence is not None else index
            for index, segment in enumerate(segments, 1)
        ]
        if sequences != list(range(1, len(segments) + 1)):
            raise DomainError(
                "manual_transcript_invalid", "audio.manual_transcript_invalid", "validation"
            )
        if any(
            not segment.text.strip()
            or segment.start_ms < 0
            or segment.end_ms <= segment.start_ms
            or segment.end_ms > recording.duration_ms
            for segment in segments
        ):
            raise DomainError(
                "manual_transcript_invalid", "audio.manual_transcript_invalid", "validation"
            )
        # Equal starts are permitted for overlapping speech; starts may never move backward.
        if any(
            next_item.start_ms < item.start_ms for item, next_item in zip(segments, segments[1:])
        ):
            raise DomainError(
                "manual_transcript_invalid", "audio.manual_transcript_invalid", "validation"
            )

    def _relative_media_path(self, recording: LectureAudio) -> str:
        path = self._storage_path(recording, require_file=False)
        return path.relative_to(self._settings.media_root.resolve()).as_posix()

    def _create_or_load_deletion_tombstone(
        self, recording: LectureAudio, context_version_id: str
    ) -> tuple[RecordingDeletionTombstone, bool]:
        # SQLite's INSERT .. ON CONFLICT is the equivalent bounded atomic boundary:
        # a collision leaves the outer deletion transaction usable and never leaks IntegrityError.
        tombstone_id = str(uuid4())
        now = self._now()
        result = self._session.execute(
            sqlite_insert(RecordingDeletionTombstone)
            .values(
                id=tombstone_id,
                created_at=now,
                updated_at=now,
                recording_id=recording.id,
                context_version_id=context_version_id,
                media_relative_path=self._relative_media_path(recording),
                quarantine_relative_path=f".quarantine/recording-{tombstone_id}.media",
                expected_sha256=recording.sha256,
                expected_byte_size=recording.byte_size,
                cleanup_type="RECORDING_DELETION",
                status=RecordingDeletionStatus.DELETE_PENDING,
            )
            .on_conflict_do_nothing(index_elements=["recording_id"])
        )
        if result.rowcount:
            created = self._session.get(RecordingDeletionTombstone, tombstone_id)
            assert created is not None
            return created, True
        existing = self._session.scalar(
            select(RecordingDeletionTombstone).where(
                RecordingDeletionTombstone.recording_id == recording.id
            )
        )
        if existing is None:
            raise DomainError(
                "recording_cleanup_pending", "audio.recording_cleanup_pending", "conflict"
            )
        return existing, False

    def _finish_deletion(
        self, tombstone: RecordingDeletionTombstone, expected_context_version_id: str | None = None
    ) -> bool:
        if (
            expected_context_version_id is not None
            and tombstone.context_version_id != expected_context_version_id
        ):
            raise DomainError(
                "recording_context_mismatch", "audio.recording_context_mismatch", "conflict"
            )
        self._assert_tombstone_context_exists(tombstone)
        owner_token = self._claim_deletion_cleanup(tombstone)
        if owner_token is None:
            return True
        try:
            quarantine = self._quarantine_tombstone_media(tombstone, owner_token)
            if quarantine is not None and quarantine.exists():
                if not self._file_matches(
                    quarantine, tombstone.expected_sha256 or "", tombstone.expected_byte_size or -1
                ):
                    self._record_deletion_conflict(
                        tombstone, owner_token, "media_identity_mismatch"
                    )
                    raise DomainError(
                        "recording_cleanup_conflict", "audio.recording_cleanup_conflict", "conflict"
                    )
                self._before_quarantine_deletion(tombstone.id, owner_token)
                self._assert_current_cleanup_owner(tombstone.id, owner_token)
                quarantine.unlink()
        except OSError as error:
            self._release_deletion_claim(tombstone, owner_token)
            raise DomainError(
                "recording_cleanup_pending", "audio.recording_cleanup_pending", "conflict"
            ) from error
        completed_at = self._now()
        result = self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone.id,
                RecordingDeletionTombstone.status == RecordingDeletionStatus.CLEANUP_CLAIMED,
                RecordingDeletionTombstone.cleanup_owner_token == owner_token,
            )
            .values(
                status=RecordingDeletionStatus.COMPLETED,
                completed_at=completed_at,
                media_relative_path=None,
                quarantine_relative_path=None,
                quarantine_captured_at=None,
                cleanup_owner_token=None,
                cleanup_claimed_at=None,
                cleanup_lease_expires_at=None,
                updated_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            self._session.commit()
            return True
        self._session.rollback()
        current = self._session.get(RecordingDeletionTombstone, tombstone.id)
        if current is not None and current.status is RecordingDeletionStatus.COMPLETED:
            return True
        raise DomainError(
            "RECORDING_DELETION_IN_PROGRESS",
            "audio.recording_deletion_in_progress",
            "conflict",
        )

    def _quarantine_tombstone_media(
        self, tombstone: RecordingDeletionTombstone, owner_token: str
    ) -> Path | None:
        quarantine = self._tombstone_quarantine_path(tombstone)
        if quarantine.exists():
            if tombstone.quarantine_captured_at is None:
                self._record_tombstone_quarantine_capture(tombstone.id, owner_token)
            return quarantine
        if tombstone.quarantine_captured_at is not None:
            # A previous claimant removed the quarantined object. The original
            # path is deliberately never revisited because it may be replaced.
            return None
        original = self._tombstone_path(tombstone)
        if not original.exists():
            return None
        self._assert_current_cleanup_owner(tombstone.id, owner_token)
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        try:
            original.rename(quarantine)
        except FileExistsError:
            if not quarantine.exists():
                raise
        self._record_tombstone_quarantine_capture(tombstone.id, owner_token)
        return quarantine

    def _assert_current_cleanup_owner(self, tombstone_id: str, owner_token: str) -> None:
        result = self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone_id,
                RecordingDeletionTombstone.status == RecordingDeletionStatus.CLEANUP_CLAIMED,
                RecordingDeletionTombstone.cleanup_owner_token == owner_token,
            )
            .values(updated_at=self._now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            self._session.commit()
            return
        self._session.rollback()
        raise DomainError(
            "RECORDING_DELETION_IN_PROGRESS",
            "audio.recording_deletion_in_progress",
            "conflict",
        )

    @staticmethod
    def _before_quarantine_deletion(_tombstone_id: str, _owner_token: str) -> None:
        """Deterministic seam for the lease-loss regression test."""

    def _record_tombstone_quarantine_capture(self, tombstone_id: str, owner_token: str) -> None:
        result = self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone_id,
                RecordingDeletionTombstone.status == RecordingDeletionStatus.CLEANUP_CLAIMED,
                RecordingDeletionTombstone.cleanup_owner_token == owner_token,
            )
            .values(quarantine_captured_at=self._now(), updated_at=self._now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            self._session.commit()
            return
        self._session.rollback()
        raise DomainError(
            "RECORDING_DELETION_IN_PROGRESS",
            "audio.recording_deletion_in_progress",
            "conflict",
        )

    def _claim_deletion_cleanup(self, tombstone: RecordingDeletionTombstone) -> str | None:
        now = self._now()
        owner_token = uuid4().hex
        claimed = self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone.id,
                (
                    (RecordingDeletionTombstone.status == RecordingDeletionStatus.DELETE_PENDING)
                    | (
                        (
                            RecordingDeletionTombstone.status
                            == RecordingDeletionStatus.CLEANUP_CLAIMED
                        )
                        & (RecordingDeletionTombstone.cleanup_lease_expires_at < now)
                    )
                ),
            )
            .values(
                status=RecordingDeletionStatus.CLEANUP_CLAIMED,
                cleanup_owner_token=owner_token,
                cleanup_claimed_at=now,
                cleanup_lease_expires_at=now + timedelta(seconds=_CLEANUP_LEASE_SECONDS),
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount:
            self._session.commit()
            self._session.refresh(tombstone)
            return owner_token
        self._session.rollback()
        current = self._session.get(RecordingDeletionTombstone, tombstone.id)
        if current is not None and current.status is RecordingDeletionStatus.COMPLETED:
            return None
        if current is not None and current.status is RecordingDeletionStatus.RECOVERY_CONFLICT:
            raise DomainError(
                "recording_cleanup_conflict", "audio.recording_cleanup_conflict", "conflict"
            )
        raise DomainError(
            "RECORDING_DELETION_IN_PROGRESS",
            "audio.recording_deletion_in_progress",
            "conflict",
        )

    def _release_deletion_claim(
        self, tombstone: RecordingDeletionTombstone, owner_token: str
    ) -> None:
        self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone.id,
                RecordingDeletionTombstone.cleanup_owner_token == owner_token,
            )
            .values(
                status=RecordingDeletionStatus.DELETE_PENDING,
                cleanup_owner_token=None,
                cleanup_claimed_at=None,
                cleanup_lease_expires_at=None,
                updated_at=self._now(),
            )
            .execution_options(synchronize_session=False)
        )
        self._session.commit()

    def _record_deletion_conflict(
        self, tombstone: RecordingDeletionTombstone, owner_token: str, code: str
    ) -> None:
        self._session.execute(
            update(RecordingDeletionTombstone)
            .where(
                RecordingDeletionTombstone.id == tombstone.id,
                RecordingDeletionTombstone.cleanup_owner_token == owner_token,
            )
            .values(
                status=RecordingDeletionStatus.RECOVERY_CONFLICT,
                conflict_code=code,
                cleanup_owner_token=None,
                cleanup_claimed_at=None,
                cleanup_lease_expires_at=None,
                updated_at=self._now(),
            )
            .execution_options(synchronize_session=False)
        )
        self._session.commit()

    def _tombstone_path(self, tombstone: RecordingDeletionTombstone) -> Path:
        root = self._settings.media_root.resolve()
        path = (root / tombstone.media_relative_path).resolve()
        if root not in path.parents:
            raise DomainError(
                "recording_cleanup_pending", "audio.recording_cleanup_pending", "conflict"
            )
        return path

    def _tombstone_quarantine_path(self, tombstone: RecordingDeletionTombstone) -> Path:
        relative = (
            tombstone.quarantine_relative_path or f".quarantine/recording-{tombstone.id}.media"
        )
        return self._intent_path(relative)

    def _upload_paths(self, lesson_id: str, sha256: str) -> tuple[Path, Path]:
        root = self._settings.media_root.resolve()
        final = (root / lesson_id / f"{sha256}-{uuid4().hex}.wav").resolve()
        temporary = final.with_suffix(".uploading")
        if root not in final.parents or root not in temporary.parents:
            raise DomainError("unsafe_storage_path", "audio.unsafe_storage_path", "validation")
        return temporary, final

    def _prepare_upload_intent(
        self, lesson_id: str, sha256: str, byte_size: int, temporary: Path, final: Path
    ) -> str:
        with self._session_factory() as recovery:
            intent = MediaUploadIntent(
                lesson_id=lesson_id,
                temporary_relative_path=temporary.relative_to(
                    self._settings.media_root.resolve()
                ).as_posix(),
                final_relative_path=final.relative_to(
                    self._settings.media_root.resolve()
                ).as_posix(),
                sha256=sha256,
                byte_size=byte_size,
                status=UploadIntentStatus.PREPARED,
            )
            recovery.add(intent)
            recovery.flush()
            intent.quarantine_relative_path = f".quarantine/upload-{intent.id}.media"
            recovery.commit()
            return intent.id

    def _set_upload_intent_status(
        self, intent_id: str, status: UploadIntentStatus, recording_id: str | None = None
    ) -> None:
        with self._session_factory() as recovery:
            intent = recovery.get(MediaUploadIntent, intent_id)
            if intent is None:
                return
            intent.status = status
            if recording_id is not None:
                intent.recording_id = recording_id
            recovery.commit()

    def _complete_upload_intent(self, intent_id: str) -> None:
        with self._session_factory() as recovery:
            intent = recovery.get(MediaUploadIntent, intent_id)
            if intent is not None:
                intent.status = UploadIntentStatus.COMPLETED
                recovery.commit()
                recovery.delete(intent)
                recovery.commit()

    def _intent_path(self, relative_path: str) -> Path:
        root = self._settings.media_root.resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents:
            raise DomainError("upload_cleanup_pending", "audio.upload_cleanup_pending", "conflict")
        return path

    @staticmethod
    def _intent_matches_recording(
        intent: MediaUploadIntent, recording: LectureAudio, final: Path
    ) -> bool:
        return (
            (intent.recording_id is None or intent.recording_id == recording.id)
            and recording.lesson_id == intent.lesson_id
            and recording.storage_path == str(final)
            and recording.sha256 == intent.sha256
            and recording.byte_size == intent.byte_size
            and recording.mime_type == "audio/wav"
        )

    @staticmethod
    def _file_identity(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest(), path.stat().st_size

    def _file_matches(self, path: Path, sha256: str, byte_size: int) -> bool:
        try:
            current_sha256, current_byte_size = self._file_identity(path)
        except OSError:
            return False
        return current_sha256 == sha256 and current_byte_size == byte_size

    def _quarantine_and_remove_intent_file(self, path: Path, intent: MediaUploadIntent) -> bool:
        """Delete only a verified object after it has left its original pathname."""

        quarantine = self._intent_quarantine_path(intent)
        if quarantine.exists():
            if intent.quarantine_captured_at is None:
                intent.quarantine_captured_at = self._now()
                self._session_factory_commit_intent(intent.id, intent.quarantine_captured_at)
            candidate = quarantine
        elif intent.quarantine_captured_at is not None:
            # A prior worker already quarantined then deleted the object. Never
            # revisit an original pathname: it may now be a replacement.
            return True
        elif not path.exists():
            return True
        else:
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.rename(quarantine)
            except FileExistsError:
                if not quarantine.exists():
                    raise
            candidate = quarantine
            captured_at = self._now()
            intent.quarantine_captured_at = captured_at
            self._session_factory_commit_intent(intent.id, captured_at)

        if not self._file_matches(candidate, intent.sha256, intent.byte_size):
            return False
        self._before_intent_quarantine_deletion(intent.id)
        candidate.unlink()
        return True

    @staticmethod
    def _before_intent_quarantine_deletion(_intent_id: str) -> None:
        """Deterministic seam for quarantine/replacement regression tests."""

    def _intent_quarantine_path(self, intent: MediaUploadIntent) -> Path:
        relative = intent.quarantine_relative_path or f".quarantine/upload-{intent.id}.media"
        return self._intent_path(relative)

    def _session_factory_commit_intent(self, intent_id: str, captured_at: datetime) -> None:
        with self._session_factory() as recovery:
            intent = recovery.get(MediaUploadIntent, intent_id)
            if intent is None:
                return
            intent.quarantine_relative_path = intent.quarantine_relative_path or (
                f".quarantine/upload-{intent.id}.media"
            )
            intent.quarantine_captured_at = captured_at
            recovery.commit()

    @staticmethod
    def _mark_upload_conflict(intent: MediaUploadIntent, code: str) -> None:
        intent.status = UploadIntentStatus.RECOVERY_CONFLICT
        intent.conflict_code = code

    @staticmethod
    def _is_sqlite_busy(error: OperationalError) -> bool:
        message = str(error).lower()
        return "database is locked" in message or "database is busy" in message

    def _assert_tombstone_context_exists(self, tombstone: RecordingDeletionTombstone) -> None:
        from app.models.foundation import CourseContextVersion

        if self._session.get(CourseContextVersion, tombstone.context_version_id) is None:
            raise DomainError(
                "recording_context_mismatch", "audio.recording_context_mismatch", "conflict"
            )

    def _invalidate_assessment(self, revision: TranscriptRevision) -> None:
        assessment = self._session.scalar(
            select(TranscriptQualityAssessment).where(
                TranscriptQualityAssessment.transcript_revision_id == revision.id
            )
        )
        if assessment is not None:
            self._session.delete(assessment)
            self._session.flush()

    def _queued_transcription_message(self) -> str:
        return (
            "Queued for deterministic demo transcription"
            if isinstance(self._provider, DeterministicDemoTranscriptionProvider)
            else "Queued for local speech recognition"
        )

    def _running_transcription_message(self) -> str:
        return (
            "Running deterministic demo transcription"
            if isinstance(self._provider, DeterministicDemoTranscriptionProvider)
            else "Running local speech recognition"
        )

    @staticmethod
    def _provider_provenance(result: ProviderTranscription) -> str:
        return (
            DETERMINISTIC_DEMO_PROVENANCE
            if result.provider_implementation == DETERMINISTIC_DEMO_PROVIDER
            else LOCAL_FASTER_WHISPER_PROVENANCE
        )

    def _fail_transcription_job(
        self, job: ProcessingJob, recording: LectureAudio, error_code: str
    ) -> ProcessingJob:
        current_job = self._session.get(ProcessingJob, job.id)
        current_recording = self._session.get(LectureAudio, recording.id)
        if current_job is None or current_recording is None:
            raise DomainError("job_not_found", "audio.job_not_found", "not_found")
        current_job.status = JobStatus.FAILED
        current_job.completed_at = self._now()
        current_job.error_code = error_code
        current_job.recoverable = True
        current_job.progress_message = (
            "Local transcription could not start; enter a transcript manually or try again."
        )
        current_recording.workflow_status = RecordingWorkflowStatus.MANUAL_TRANSCRIPT_REQUIRED
        self._session.commit()
        return current_job

    def _replace_assessment(self, revision: TranscriptRevision) -> TranscriptQualityAssessment:
        self._invalidate_assessment(revision)
        latest = self._latest_revision(revision.lecture_audio_id)
        findings = evaluate_transcript_quality(
            revision,
            self._settings.demo_minimum_timestamp_coverage,
            latest_revision_id=latest.id if latest is not None else None,
        )
        assessment = TranscriptQualityAssessment(
            transcript_revision_id=revision.id,
            quality_status=QualityStatus.VERIFIED if not findings else QualityStatus.FAILED,
            reasons=[
                self._reason(
                    finding.code,
                    finding.severity,
                    finding.action,
                    finding.measured,
                    finding.threshold,
                )
                for finding in findings
            ],
        )
        self._session.add(assessment)
        self._session.flush()
        return assessment

    @staticmethod
    def _reason(
        code: str, severity: str, action: str, measured: float, threshold: float
    ) -> TranscriptQualityReason:
        return TranscriptQualityReason(
            reason_code=code,
            severity=severity,
            message_key=f"quality.{code}",
            measured_value=measured,
            threshold=threshold,
            recovery_action=action,
        )

    def _recording(self, recording_id: str) -> LectureAudio:
        recording = self._session.get(LectureAudio, recording_id)
        if recording is None:
            raise DomainError("recording_not_found", "audio.recording_not_found", "not_found")
        return recording

    def _job(self, job_id: str) -> ProcessingJob:
        job = self._session.get(ProcessingJob, job_id)
        if job is None:
            raise DomainError("job_not_found", "audio.job_not_found", "not_found")
        return job

    def _revision(self, revision_id: str) -> TranscriptRevision:
        revision = self._session.scalar(
            select(TranscriptRevision)
            .where(TranscriptRevision.id == revision_id)
            .options(
                selectinload(TranscriptRevision.segments)
                .selectinload(TranscriptSegment.term_suggestions)
                .selectinload(TermSuggestion.decisions),
                selectinload(TranscriptRevision.lecture_audio).selectinload(
                    LectureAudio.transcript_revisions
                ),
                selectinload(TranscriptRevision.lecture_audio).selectinload(LectureAudio.lesson),
            )
        )
        if revision is None:
            raise DomainError("transcript_not_found", "audio.transcript_not_found", "not_found")
        return revision

    def _assert_revision_mutable(self, revision: TranscriptRevision) -> None:
        self._assert_context_mutable_for_lesson(revision.lecture_audio.lesson_id)
        if revision.teacher_review_status is TeacherReviewStatus.APPROVED:
            raise DomainError(
                "approved_transcript_immutable", "audio.approved_transcript_immutable", "forbidden"
            )

    def _assert_context_mutable_for_lesson(self, lesson_id: str) -> None:
        lesson = self._session.scalar(
            select(Lesson)
            .where(Lesson.id == lesson_id)
            .options(selectinload(Lesson.chapter).selectinload(Chapter.context_version))
        )
        if lesson is None:
            raise DomainError("lesson_not_found", "lesson.not_found", "not_found")
        assert_context_mutable(lesson.chapter.context_version)

    def _context_id_for_lesson(self, lesson_id: str) -> str:
        lesson = self._session.scalar(
            select(Lesson)
            .where(Lesson.id == lesson_id)
            .options(selectinload(Lesson.chapter).selectinload(Chapter.context_version))
        )
        if lesson is None:
            raise DomainError("lesson_not_found", "lesson.not_found", "not_found")
        return lesson.chapter.context_version_id

    @staticmethod
    def _derived_workflow_state(
        recording: LectureAudio | None,
        job: ProcessingJob | None,
        revision: TranscriptRevision | None,
        assessment: TranscriptQualityAssessment | None,
        findings: tuple[TranscriptQualityFinding, ...],
        tombstone: RecordingDeletionTombstone | None,
    ) -> str:
        if tombstone is not None:
            if tombstone.status is RecordingDeletionStatus.RECOVERY_CONFLICT:
                return "RECOVERY_CONFLICT"
            return "REMOVAL_PENDING"
        if recording is None:
            return "NO_RECORDING"
        if job is not None and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            return "PROCESSING"
        if revision is None:
            if recording.workflow_status is RecordingWorkflowStatus.MANUAL_TRANSCRIPT_REQUIRED:
                return "MANUAL_TRANSCRIPT_REQUIRED"
            if job is not None and job.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                return "PROCESSING_FAILED"
            return "UPLOADED"
        if assessment is not None and (
            findings or assessment.quality_status is QualityStatus.FAILED
        ):
            return "QUALITY_BLOCKED"
        if revision.teacher_review_status is TeacherReviewStatus.APPROVED:
            return "TRANSCRIPT_APPROVED"
        if assessment is not None and assessment.quality_status is QualityStatus.VERIFIED:
            return "QUALITY_VERIFIED"
        return "NEEDS_REVIEW"

    @staticmethod
    def _timestamp_coverage(revision: TranscriptRevision) -> float:
        duration_ms = revision.lecture_audio.duration_ms
        if duration_ms <= 0:
            return 0
        intervals = sorted(
            (segment.start_ms, segment.end_ms)
            for segment in revision.segments
            if 0 <= segment.start_ms < segment.end_ms <= duration_ms
        )
        if not intervals:
            return 0
        covered_ms = 0
        start_ms, end_ms = intervals[0]
        for next_start, next_end in intervals[1:]:
            if next_start <= end_ms:
                end_ms = max(end_ms, next_end)
            else:
                covered_ms += end_ms - start_ms
                start_ms, end_ms = next_start, next_end
        return (covered_ms + end_ms - start_ms) / duration_ms

    def _validate_wav(self, filename: str, mime_type: str, data: bytes) -> WavMetadata:
        if not filename.lower().endswith(".wav"):
            raise DomainError(
                "wav_extension_required", "audio.wav_extension_required", "validation"
            )
        if mime_type.lower() not in _ALLOWED_MIME_TYPES:
            raise DomainError("wav_mime_required", "audio.wav_mime_required", "validation")
        if len(data) == 0 or len(data) > self._settings.max_wav_upload_bytes:
            raise DomainError("wav_size_invalid", "audio.wav_size_invalid", "validation")
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise DomainError("wav_magic_invalid", "audio.wav_magic_invalid", "validation")
        return parse_wav_metadata(data)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        base = Path(filename or "recording.wav").name
        sanitized = _FILENAME_PATTERN.sub("-", base).strip(".-")
        if not sanitized:
            sanitized = "recording.wav"
        return sanitized[:255]

    def _place_upload_media(self, temporary: Path, destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary.write_bytes(data)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def recover_pending_audio_uploads(
    settings: Settings, session_factory: sessionmaker[Session], *, raise_on_conflict: bool = True
) -> int:
    """Run durable upload-intent recovery in a newly-created session."""

    with session_factory() as session:
        return AudioWorkflowService(
            session, settings, session_factory=session_factory
        ).recover_upload_intents(raise_on_conflict=raise_on_conflict)
