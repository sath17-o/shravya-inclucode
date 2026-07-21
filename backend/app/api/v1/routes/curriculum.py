# ruff: noqa: F403, F405
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse

from app.api.dependencies import (
    get_audio_workflow,
    get_completeness,
    get_repository,
    get_review,
    get_student,
    get_versioning,
)
from app.contracts.common import ErrorResponse, SuccessResponse
from app.contracts.curriculum_api import *
from app.repositories.curriculum import CurriculumRepository
from app.services.audio_workflow import AudioWorkflowService, DemoSegment, WavUpload
from app.services.context_completeness import ContextCompletenessService
from app.services.context_versioning import ContextVersioningService
from app.services.student_curriculum import StudentCurriculumService
from app.services.teacher_review import TeacherReviewService

router = APIRouter(
    responses={
        403: {"model": ErrorResponse, "description": "The requested action is not permitted."},
        404: {
            "model": ErrorResponse,
            "description": "The requested curriculum record was not found.",
        },
        409: {
            "model": ErrorResponse,
            "description": "The curriculum context is in a conflicting state.",
        },
        422: {
            "model": ErrorResponse,
            "description": "The curriculum request could not be completed.",
        },
        500: {"model": ErrorResponse, "description": "An unexpected error occurred."},
    }
)


def summary(c):
    return ContextSummaryResponse.model_validate(c, from_attributes=True)


def completeness(r):
    return CompletenessResponse.model_validate(r, from_attributes=True)


def event(e):
    return ReviewEventResponse.model_validate(e, from_attributes=True)


def lesson(lesson_model):
    return LessonResponse(
        id=lesson_model.id,
        title=lesson_model.title,
        sequence=lesson_model.sequence,
        primary_language=lesson_model.primary_language,
        description=lesson_model.description,
        objectives=[
            LearningObjectiveResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.objectives, key=lambda x: (x.sequence, x.id))
        ],
        approved_materials=[
            ApprovedMaterialResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.approved_materials, key=lambda x: (x.sequence, x.id))
        ],
        glossary_terms=[
            GlossaryTermResponse(
                id=x.id,
                canonical_term=x.canonical_term,
                malayalam_support_label=x.malayalam_support_label,
                definition=x.definition,
                malayalam_explanation=x.malayalam_explanation,
                sequence=x.sequence,
                aliases=[
                    TermAliasResponse.model_validate(a, from_attributes=True)
                    for a in sorted(x.aliases, key=lambda a: (a.normalized_alias, a.id))
                ],
                misrecognitions=[
                    ASRMisrecognitionResponse.model_validate(a, from_attributes=True)
                    for a in sorted(x.misrecognitions, key=lambda a: (a.normalized_text, a.id))
                ],
            )
            for x in sorted(lesson_model.glossary_terms, key=lambda x: (x.sequence, x.id))
        ],
        concepts=[
            ConceptResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.concepts, key=lambda x: (x.sequence, x.id))
        ],
        recovery_packs=[
            RecoveryPackResponse.model_validate(x, from_attributes=True)
            for x in sorted(
                (
                    pack
                    for pack in lesson_model.chapter.context_version.recovery_packs
                    if pack.concept_id in {concept.id for concept in lesson_model.concepts}
                ),
                key=lambda x: (x.concept.sequence, x.id),
            )
        ],
        concept_relationships=[
            ConceptRelationshipResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.concept_relationships, key=lambda x: (x.sequence, x.id))
        ],
        questions=[
            QuestionResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.questions, key=lambda x: (x.sequence, x.id))
        ],
    )


def chapters(c):
    return [
        ChapterResponse(
            id=x.id,
            title=x.title,
            sequence=x.sequence,
            lessons=[lesson(y) for y in sorted(x.lessons, key=lambda y: (y.sequence, y.id))],
        )
        for x in sorted(c.chapters, key=lambda x: (x.sequence, x.id))
    ]


def student_lesson(projection):
    return StudentLessonResponse(
        id=projection.id,
        title=projection.title,
        sequence=projection.sequence,
        primary_language=projection.primary_language,
        description=projection.description,
        objectives=[
            LearningObjectiveResponse.model_validate(item, from_attributes=True)
            for item in projection.objectives
        ],
        approved_materials=[
            StudentApprovedMaterialResponse.model_validate(item, from_attributes=True)
            for item in projection.approved_materials
        ],
        glossary_terms=[
            StudentGlossaryTermResponse(
                id=item.id,
                canonical_term=item.canonical_term,
                malayalam_support_label=item.malayalam_support_label,
                definition=item.definition,
                malayalam_explanation=item.malayalam_explanation,
                sequence=item.sequence,
                concept_ids=list(item.concept_ids),
                aliases=[
                    StudentTermAliasResponse.model_validate(alias, from_attributes=True)
                    for alias in item.aliases
                ],
            )
            for item in projection.glossary_terms
        ],
        concepts=[
            ConceptResponse.model_validate(item, from_attributes=True)
            for item in projection.concepts
        ],
        concept_relationships=[
            StudentConceptRelationshipResponse.model_validate(item, from_attributes=True)
            for item in projection.concept_relationships
        ],
        questions=[
            StudentQuestionResponse.model_validate(item, from_attributes=True)
            for item in projection.questions
        ],
        recovery_support=[
            StudentRecoverySupportResponse(
                concept_id=item.concept_id,
                cue=StudentBilingualRecoveryTextResponse(
                    english=item.cue.english, malayalam=item.cue.malayalam
                ),
                example=StudentBilingualRecoveryTextResponse(
                    english=item.example.english, malayalam=item.example.malayalam
                ),
                alternate_explanation=StudentBilingualRecoveryTextResponse(
                    english=item.alternate_explanation.english,
                    malayalam=item.alternate_explanation.malayalam,
                ),
            )
            for item in projection.recovery_support
        ],
        approved_transcript=(
            StudentTranscriptResponse(
                id=projection.approved_transcript.id,
                recording_id=projection.approved_transcript.recording_id,
                provenance_label=projection.approved_transcript.provenance_label,
                source_status=projection.approved_transcript.source_status,
                trusted_context_version=projection.approved_transcript.trusted_context_version,
                segments=[
                    StudentTranscriptSegmentResponse.model_validate(item, from_attributes=True)
                    for item in projection.approved_transcript.segments
                ],
            )
            if projection.approved_transcript
            else None
        ),
    )


def student_chapters(projections):
    return [
        StudentChapterResponse(
            id=chapter_projection.id,
            title=chapter_projection.title,
            sequence=chapter_projection.sequence,
            lessons=[
                student_lesson(lesson_projection)
                for lesson_projection in chapter_projection.lessons
            ],
        )
        for chapter_projection in projections
    ]


def recording_response(recording):
    return RecordingResponse(
        id=recording.id,
        lesson_id=recording.lesson_id,
        original_filename=recording.original_filename,
        mime_type=recording.mime_type,
        byte_size=recording.byte_size,
        sha256=recording.sha256,
        duration_ms=recording.duration_ms,
        source_status=recording.source_status,
        workflow_status=recording.workflow_status,
    )


def job_response(job):
    return ProcessingJobResponse(
        id=job.id,
        status=job.status,
        stage=job.progress_message,
        recoverable=job.recoverable,
        recording_id=job.entity_id,
        resulting_transcript_revision_id=job.result_transcript_revision_id,
        error_code=job.error_code,
    )


def transcript_response(revision):
    assessment = max(
        revision.quality_assessments, key=lambda item: (item.created_at, item.id), default=None
    )
    suggestions = [
        suggestion for segment in revision.segments for suggestion in segment.term_suggestions
    ]
    glossary_by_id = {item.id: item for item in revision.lecture_audio.lesson.glossary_terms}
    return TranscriptRevisionResponse(
        id=revision.id,
        recording_id=revision.lecture_audio_id,
        revision_number=revision.revision_number,
        copied_from_transcript_revision_id=revision.copied_from_transcript_revision_id,
        source_status=revision.source_status,
        provider_name=revision.provider_name,
        provider_version=revision.provider_version,
        provenance_label=revision.provenance_label,
        teacher_review_status=revision.teacher_review_status,
        approved_at=revision.approved_at,
        segments=[
            TranscriptSegmentResponse(
                id=item.id,
                sequence=item.sequence,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                text=item.text,
            )
            for item in sorted(revision.segments, key=lambda item: (item.sequence, item.id))
        ],
        suggestions=[
            TermSuggestionResponse(
                id=item.id,
                transcript_segment_id=item.transcript_segment_id,
                glossary_term_id=item.glossary_term_id,
                detected_text=item.detected_text,
                canonical_term=(
                    glossary_by_id.get(item.glossary_term_id).canonical_term
                    if item.glossary_term_id in glossary_by_id
                    else None
                ),
                malayalam_support_label=(
                    glossary_by_id.get(item.glossary_term_id).malayalam_support_label
                    if item.glossary_term_id in glossary_by_id
                    else None
                ),
                latest_decision=max(
                    item.decisions,
                    key=lambda decision: (decision.created_at, decision.id),
                    default=None,
                ).decision
                if item.decisions
                else None,
            )
            for item in suggestions
        ],
        quality=TranscriptQualityResponse(
            quality_status=assessment.quality_status,
            reasons=[
                QualityReasonResponse.model_validate(reason, from_attributes=True)
                for reason in assessment.reasons
            ],
        )
        if assessment
        else None,
    )


def audio_workflow_summary_response(snapshot):
    revision = transcript_response(snapshot.revision) if snapshot.revision is not None else None
    if revision is not None and snapshot.findings:
        revision = revision.model_copy(
            update={
                "quality": TranscriptQualityResponse(
                    quality_status=QualityStatus.FAILED,
                    measured_coverage=snapshot.measured_coverage,
                    reasons=[
                        QualityReasonResponse(
                            reason_code=finding.code,
                            severity=finding.severity,
                            message_key=f"quality.{finding.code}",
                            measured_value=finding.measured,
                            threshold=finding.threshold,
                            recovery_action=finding.action,
                        )
                        for finding in snapshot.findings
                    ],
                )
            }
        )
    elif revision is not None and revision.quality is not None:
        revision = revision.model_copy(
            update={
                "quality": revision.quality.model_copy(
                    update={"measured_coverage": snapshot.measured_coverage}
                )
            }
        )

    return AudioWorkflowSummaryResponse(
        context_version_id=snapshot.context_version_id,
        state=snapshot.state,
        recording=(
            AudioWorkflowRecordingResponse(
                id=snapshot.recording.id,
                original_filename=snapshot.recording.original_filename,
                mime_type=snapshot.recording.mime_type,
                duration_ms=snapshot.recording.duration_ms,
                source_status=snapshot.recording.source_status,
                created_at=snapshot.recording.created_at,
                content_url=f"/api/v1/teacher/recordings/{snapshot.recording.id}/content",
            )
            if snapshot.recording is not None
            else None
        ),
        latest_job=(
            AudioWorkflowJobResponse(
                id=snapshot.job.id,
                status=snapshot.job.status,
                stage=snapshot.job.progress_message,
                recoverable=snapshot.job.recoverable,
                error_code=snapshot.job.error_code,
                message=(
                    "No offline demo transcript is available for this recording."
                    if snapshot.job.error_code == "demo_audio_unrecognized"
                    else "Transcription needs teacher attention."
                    if snapshot.job.status in {JobStatus.FAILED, JobStatus.CANCELLED}
                    else None
                ),
            )
            if snapshot.job is not None
            else None
        ),
        latest_revision=revision,
        deletion=(
            AudioWorkflowDeletionResponse(
                status=snapshot.tombstone.status.value,
                recoverable=True,
                message=(
                    "Recording cleanup needs attention before another recording can be used."
                    if snapshot.tombstone.status.value == "RECOVERY_CONFLICT"
                    else "Recording removal is still being completed."
                ),
            )
            if snapshot.tombstone is not None
            else None
        ),
        capabilities=AudioWorkflowCapabilitiesResponse(
            can_start_processing=snapshot.capabilities.can_start_processing,
            can_retry_processing=snapshot.capabilities.can_retry_processing,
            can_enter_manual_transcript=snapshot.capabilities.can_enter_manual_transcript,
            can_edit_transcript=snapshot.capabilities.can_edit_transcript,
            can_assess_quality=snapshot.capabilities.can_assess_quality,
            can_approve_transcript=snapshot.capabilities.can_approve_transcript,
            can_remove_recording=snapshot.capabilities.can_remove_recording,
        ),
    )


@router.get(
    "/teacher/courses/{course_id}/contexts",
    response_model=SuccessResponse[list[ContextSummaryResponse]],
    operation_id="list_teacher_contexts",
)
def list_contexts(course_id: str, repo: Annotated[CurriculumRepository, Depends(get_repository)]):
    if repo.get_course(course_id) is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("course_not_found", "course.not_found", "not_found")
    return SuccessResponse(data=[summary(x) for x in repo.list_context_versions(course_id)])


@router.get(
    "/teacher/contexts/{context_id}/completeness",
    response_model=SuccessResponse[CompletenessResponse],
    operation_id="get_context_completeness",
)
def get_completeness_route(
    context_id: str, service: Annotated[ContextCompletenessService, Depends(get_completeness)]
):
    return SuccessResponse(data=completeness(service.evaluate(context_id)))


@router.get(
    "/teacher/contexts/{context_id}/review-events",
    response_model=SuccessResponse[list[ReviewEventResponse]],
    operation_id="get_review_events",
)
def history(context_id: str, repo: Annotated[CurriculumRepository, Depends(get_repository)]):
    if repo.get_context_version(context_id) is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("context_not_found", "context.not_found", "not_found")
    return SuccessResponse(data=[event(x) for x in repo.list_review_events(context_id)])


@router.get(
    "/teacher/contexts/{context_id}",
    response_model=SuccessResponse[ContextDetailResponse],
    operation_id="get_teacher_context",
)
def detail(
    context_id: str,
    repo: Annotated[CurriculumRepository, Depends(get_repository)],
    service: Annotated[ContextCompletenessService, Depends(get_completeness)],
):
    c = repo.get_context_with_graph(context_id)
    if c is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("context_not_found", "context.not_found", "not_found")
    return SuccessResponse(
        data=ContextDetailResponse(
            **summary(c).model_dump(),
            chapters=chapters(c),
            completeness=completeness(service.evaluate(c.id)),
            review_events=[event(x) for x in repo.list_review_events(c.id)],
        )
    )


@router.get(
    "/curriculum/context-versions/{context_version_id}/audio-workflow",
    response_model=SuccessResponse[AudioWorkflowSummaryResponse],
    operation_id="get_teacher_audio_workflow",
)
def audio_workflow_summary(
    context_version_id: str,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    return SuccessResponse(
        data=audio_workflow_summary_response(service.get_workflow_summary(context_version_id))
    )


@router.post(
    "/teacher/contexts/{context_id}/submit-for-review",
    response_model=SuccessResponse[SubmitResponse],
    operation_id="submit_context_review",
)
def submit(
    context_id: str,
    body: ReviewNoteRequest | None = None,
    svc: Annotated[TeacherReviewService, Depends(get_review)] = None,
    complete: Annotated[ContextCompletenessService, Depends(get_completeness)] = None,
):
    c = svc.submit_for_review(context_id, reviewer_note=body.reviewer_note if body else None)
    return SuccessResponse(
        data=SubmitResponse(context=summary(c), completeness=completeness(complete.evaluate(c.id)))
    )


@router.post(
    "/teacher/contexts/{context_id}/return-to-draft",
    response_model=SuccessResponse[ContextSummaryResponse],
    operation_id="return_context_draft",
)
def return_draft(
    context_id: str,
    body: ReviewNoteRequest | None = None,
    svc: Annotated[TeacherReviewService, Depends(get_review)] = None,
):
    return SuccessResponse(
        data=summary(
            svc.return_to_draft(context_id, reviewer_note=body.reviewer_note if body else None)
        )
    )


@router.post(
    "/teacher/contexts/{context_id}/approve",
    response_model=SuccessResponse[ApprovalResponse],
    operation_id="approve_context",
)
def approve(context_id: str, svc: Annotated[TeacherReviewService, Depends(get_review)]):
    result = svc.approve_with_result(context_id)
    return SuccessResponse(
        data=ApprovalResponse(
            context=summary(result.context),
            newly_staled_artifact_count=result.newly_staled_artifact_count,
        )
    )


@router.post(
    "/teacher/recovery-packs/{recovery_pack_id}/approve",
    response_model=SuccessResponse[RecoveryPackResponse],
    operation_id="approve_recovery_pack",
)
def approve_recovery_pack(
    recovery_pack_id: str, svc: Annotated[TeacherReviewService, Depends(get_review)]
):
    return SuccessResponse(
        data=RecoveryPackResponse.model_validate(
            svc.approve_recovery_pack(recovery_pack_id), from_attributes=True
        )
    )


@router.post(
    "/teacher/contexts/{context_id}/copy-to-new-draft",
    response_model=SuccessResponse[ContextSummaryResponse],
    operation_id="copy_context_draft",
)
def copy(
    context_id: str,
    body: CopyRequest | None = None,
    svc: Annotated[ContextVersioningService, Depends(get_versioning)] = None,
):
    return SuccessResponse(
        data=summary(svc.create_draft_from_approved(context_id, note=body.note if body else None))
    )


@router.post(
    "/teacher/lessons/{lesson_id}/recordings",
    response_model=SuccessResponse[RecordingResponse],
    operation_id="upload_classroom_wav",
)
async def upload_recording(
    lesson_id: str,
    request: Request,
    x_filename: Annotated[str, Header(alias="X-Filename")],
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    recording = service.upload(
        lesson_id,
        WavUpload(
            filename=x_filename,
            declared_mime_type=request.headers.get("content-type", ""),
            data=await request.body(),
        ),
    )
    return SuccessResponse(data=recording_response(recording))


@router.post(
    "/teacher/recordings/{recording_id}/transcriptions",
    response_model=SuccessResponse[ProcessingJobResponse],
    operation_id="request_recording_transcription",
)
def request_transcription(
    recording_id: str,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    return SuccessResponse(data=job_response(service.request_transcription(recording_id)))


@router.get(
    "/teacher/recordings/{recording_id}/content",
    operation_id="get_recording_content",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Root-contained classroom WAV bytes.",
            "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def recording_content(
    recording_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]
):
    recording = service.get_recording(recording_id)
    return FileResponse(service.recording_path(recording_id), media_type=recording.mime_type)


@router.delete(
    "/curriculum/context-versions/{context_version_id}/recordings/{recording_id}",
    response_model=SuccessResponse[RecordingRemovalResponse],
    operation_id="remove_classroom_recording",
)
def remove_recording(
    context_version_id: str,
    recording_id: str,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    return SuccessResponse(
        data=RecordingRemovalResponse(
            recording_id=recording_id,
            removed=service.delete_recording(
                recording_id, expected_context_version_id=context_version_id
            ),
        )
    )


@router.get(
    "/teacher/processing-jobs/{job_id}",
    response_model=SuccessResponse[ProcessingJobResponse],
    operation_id="get_processing_job",
)
def get_job(job_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]):
    return SuccessResponse(data=job_response(service.get_job(job_id)))


@router.post(
    "/teacher/processing-jobs/{job_id}/run",
    response_model=SuccessResponse[ProcessingJobResponse],
    operation_id="run_processing_job",
)
def run_job(job_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]):
    return SuccessResponse(data=job_response(service.run_job(job_id)))


@router.get(
    "/teacher/transcript-revisions/{revision_id}",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="get_transcript_revision",
)
def get_revision(
    revision_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]
):
    return SuccessResponse(data=transcript_response(service.get_revision(revision_id)))


@router.post(
    "/teacher/term-suggestions/{suggestion_id}/decision",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="decide_transcript_term",
)
def decide_term(
    suggestion_id: str,
    body: TermDecisionRequest,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    return SuccessResponse(
        data=transcript_response(service.record_decision(suggestion_id, body.decision))
    )


@router.post(
    "/teacher/transcript-revisions/{revision_id}/manual-revision",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="create_manual_transcript_revision",
)
def manual_revision(
    revision_id: str,
    body: TranscriptManualRevisionRequest,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    segments = tuple(DemoSegment(**segment.model_dump()) for segment in body.segments)
    return SuccessResponse(
        data=transcript_response(service.create_manual_revision(revision_id, segments))
    )


@router.post(
    "/teacher/recordings/{recording_id}/manual-revision",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="create_recording_manual_transcript_revision",
)
def recording_manual_revision(
    recording_id: str,
    body: TranscriptManualRevisionRequest,
    service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)],
):
    segments = tuple(DemoSegment(**segment.model_dump()) for segment in body.segments)
    return SuccessResponse(
        data=transcript_response(
            service.create_manual_revision_for_recording(recording_id, segments)
        )
    )


@router.post(
    "/teacher/transcript-revisions/{revision_id}/quality-assessment",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="assess_transcript_quality",
)
def assess_transcript(
    revision_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]
):
    service.assess_quality(revision_id)
    return SuccessResponse(data=transcript_response(service.get_revision(revision_id)))


@router.post(
    "/teacher/transcript-revisions/{revision_id}/approve",
    response_model=SuccessResponse[TranscriptRevisionResponse],
    operation_id="approve_transcript_revision",
)
def approve_transcript(
    revision_id: str, service: Annotated[AudioWorkflowService, Depends(get_audio_workflow)]
):
    return SuccessResponse(data=transcript_response(service.approve_transcript(revision_id)))


@router.get(
    "/student/courses/{course_id}/lesson-overview",
    response_model=SuccessResponse[StudentLessonOverviewResponse],
    operation_id="student_lesson_overview",
)
def overview(
    course_id: str,
    svc: Annotated[StudentCurriculumService, Depends(get_student)],
):
    projection = svc.get_curriculum_projection(course_id)
    base = CourseResponse.model_validate(projection.course, from_attributes=True)
    return SuccessResponse(
        data=StudentLessonOverviewResponse(
            course=base,
            is_ready=projection.context is not None,
            selected_context_id=projection.context.id if projection.context else None,
            version_number=projection.context.version_number if projection.context else None,
            approved_at=projection.context.approved_at if projection.context else None,
            chapters=student_chapters(projection.chapters),
        )
    )
