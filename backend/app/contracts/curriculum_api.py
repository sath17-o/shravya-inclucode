from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.contracts.enums import (
    ContextReviewEventType,
    JobStatus,
    QualityStatus,
    RecordingWorkflowStatus,
    SourceStatus,
    TeacherReviewStatus,
    TermDecisionValue,
)


class ContextSummaryResponse(BaseModel):
    id: str
    course_id: str
    version_number: int
    teacher_review_status: TeacherReviewStatus
    copied_from_context_version_id: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    reviewer_note: str | None = None


class LearningObjectiveResponse(BaseModel):
    id: str
    objective_text: str
    malayalam_text: str | None
    sequence: int


class ApprovedMaterialResponse(BaseModel):
    id: str
    title: str
    material_type: str
    source_label: str
    content: str
    language: str
    sequence: int
    teacher_review_status: TeacherReviewStatus


class TermAliasResponse(BaseModel):
    id: str
    alias: str
    normalized_alias: str


class ASRMisrecognitionResponse(BaseModel):
    id: str
    detected_text: str
    normalized_text: str
    source_note: str | None


class GlossaryTermResponse(BaseModel):
    id: str
    canonical_term: str
    malayalam_support_label: str | None
    definition: str
    malayalam_explanation: str | None
    sequence: int
    aliases: list[TermAliasResponse] = Field(default_factory=list)
    misrecognitions: list[ASRMisrecognitionResponse] = Field(default_factory=list)


class ConceptResponse(BaseModel):
    id: str
    concept_key: str
    title: str
    malayalam_title: str | None
    definition: str
    malayalam_definition: str | None
    sequence: int


class ConceptRelationshipResponse(BaseModel):
    id: str
    source_concept_id: str
    target_concept_id: str
    relationship_type: str
    teacher_note: str | None
    sequence: int


class QuestionResponse(BaseModel):
    id: str
    related_concept_id: str | None
    source_type: str
    source_label: str
    question_text: str
    malayalam_question_text: str | None
    sequence: int
    year: int | None
    marks: int | None
    teacher_review_status: TeacherReviewStatus


class LessonResponse(BaseModel):
    id: str
    title: str
    sequence: int
    primary_language: str
    description: str | None
    objectives: list[LearningObjectiveResponse] = Field(default_factory=list)
    approved_materials: list[ApprovedMaterialResponse] = Field(default_factory=list)
    glossary_terms: list[GlossaryTermResponse] = Field(default_factory=list)
    concepts: list[ConceptResponse] = Field(default_factory=list)
    concept_relationships: list[ConceptRelationshipResponse] = Field(default_factory=list)
    questions: list[QuestionResponse] = Field(default_factory=list)


class ChapterResponse(BaseModel):
    id: str
    title: str
    sequence: int
    lessons: list[LessonResponse] = Field(default_factory=list)


class ReviewEventResponse(BaseModel):
    id: str
    event_type: ContextReviewEventType
    actor_role: str
    note: str | None
    created_at: datetime


class CompletenessIssueResponse(BaseModel):
    code: str
    section: str
    field: str | None
    message_key: str
    recovery_action: str


class CompletenessResponse(BaseModel):
    context_version_id: str
    is_complete: bool
    issues: list[CompletenessIssueResponse]
    completed_sections: list[str]
    incomplete_sections: list[str]


class ContextDetailResponse(ContextSummaryResponse):
    chapters: list[ChapterResponse]
    completeness: CompletenessResponse
    review_events: list[ReviewEventResponse]


class ReviewNoteRequest(BaseModel):
    reviewer_note: str | None = None


class CopyRequest(BaseModel):
    note: str | None = None


class SubmitResponse(BaseModel):
    context: ContextSummaryResponse
    completeness: CompletenessResponse


class ApprovalResponse(BaseModel):
    context: ContextSummaryResponse
    newly_staled_artifact_count: int


class CourseResponse(BaseModel):
    id: str
    title: str
    subject: str
    class_level: int
    grade_band: str


class StudentApprovedMaterialResponse(BaseModel):
    id: str
    title: str
    material_type: str
    source_label: str
    content: str
    language: str
    sequence: int


class StudentTermAliasResponse(BaseModel):
    id: str
    alias: str
    normalized_alias: str


class StudentGlossaryTermResponse(BaseModel):
    id: str
    canonical_term: str
    malayalam_support_label: str | None
    definition: str
    malayalam_explanation: str | None
    sequence: int
    concept_ids: list[str] = Field(default_factory=list)
    aliases: list[StudentTermAliasResponse] = Field(default_factory=list)


class StudentConceptRelationshipResponse(BaseModel):
    id: str
    source_concept_id: str
    target_concept_id: str
    relationship_type: str
    sequence: int


class StudentQuestionResponse(BaseModel):
    id: str
    related_concept_id: str | None
    source_type: str
    source_label: str
    question_text: str
    malayalam_question_text: str | None
    sequence: int
    year: int | None
    marks: int | None


class StudentLessonResponse(BaseModel):
    id: str
    title: str
    sequence: int
    primary_language: str
    description: str | None
    objectives: list[LearningObjectiveResponse] = Field(default_factory=list)
    approved_materials: list[StudentApprovedMaterialResponse] = Field(default_factory=list)
    glossary_terms: list[StudentGlossaryTermResponse] = Field(default_factory=list)
    concepts: list[ConceptResponse] = Field(default_factory=list)
    concept_relationships: list[StudentConceptRelationshipResponse] = Field(default_factory=list)
    questions: list[StudentQuestionResponse] = Field(default_factory=list)
    approved_transcript: "StudentTranscriptResponse | None" = None


class StudentChapterResponse(BaseModel):
    id: str
    title: str
    sequence: int
    lessons: list[StudentLessonResponse] = Field(default_factory=list)


class StudentLessonOverviewResponse(BaseModel):
    course: CourseResponse
    is_ready: bool
    selected_context_id: str | None = None
    version_number: int | None = None
    approved_at: datetime | None = None
    chapters: list[StudentChapterResponse] = Field(default_factory=list)


class RecordingResponse(BaseModel):
    id: str
    lesson_id: str
    original_filename: str
    mime_type: str
    byte_size: int
    sha256: str
    duration_ms: int
    source_status: SourceStatus
    workflow_status: RecordingWorkflowStatus


class ProcessingJobResponse(BaseModel):
    id: str
    status: JobStatus
    stage: str
    recoverable: bool | None
    recording_id: str
    resulting_transcript_revision_id: str | None
    error_code: str | None


class TranscriptSegmentInput(BaseModel):
    sequence: int | None = Field(default=None, ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)


class TranscriptSegmentResponse(TranscriptSegmentInput):
    id: str


class TermSuggestionResponse(BaseModel):
    id: str
    transcript_segment_id: str
    glossary_term_id: str | None
    detected_text: str
    canonical_term: str | None
    malayalam_support_label: str | None
    latest_decision: TermDecisionValue | None


class QualityReasonResponse(BaseModel):
    reason_code: str
    severity: str
    message_key: str
    measured_value: float | None
    threshold: float | None
    recovery_action: str | None


class TranscriptQualityResponse(BaseModel):
    quality_status: QualityStatus
    measured_coverage: float | None = None
    reasons: list[QualityReasonResponse] = Field(default_factory=list)


class TranscriptRevisionResponse(BaseModel):
    id: str
    recording_id: str
    revision_number: int
    copied_from_transcript_revision_id: str | None
    source_status: SourceStatus
    provider_name: str
    provider_version: str | None
    provenance_label: str
    teacher_review_status: TeacherReviewStatus
    approved_at: datetime | None
    segments: list[TranscriptSegmentResponse] = Field(default_factory=list)
    suggestions: list[TermSuggestionResponse] = Field(default_factory=list)
    quality: TranscriptQualityResponse | None = None


AudioWorkflowState = Literal[
    "NO_RECORDING",
    "UPLOADED",
    "PROCESSING",
    "PROCESSING_FAILED",
    "MANUAL_TRANSCRIPT_REQUIRED",
    "NEEDS_REVIEW",
    "QUALITY_BLOCKED",
    "QUALITY_VERIFIED",
    "TRANSCRIPT_APPROVED",
    "REMOVAL_PENDING",
    "RECOVERY_CONFLICT",
]


class AudioWorkflowRecordingResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    duration_ms: int
    source_status: SourceStatus
    created_at: datetime
    content_url: str


class AudioWorkflowJobResponse(BaseModel):
    id: str
    status: JobStatus
    stage: str
    recoverable: bool | None
    error_code: str | None
    message: str | None


class AudioWorkflowDeletionResponse(BaseModel):
    status: str
    recoverable: bool
    message: str


class AudioWorkflowCapabilitiesResponse(BaseModel):
    can_start_processing: bool
    can_retry_processing: bool
    can_enter_manual_transcript: bool
    can_edit_transcript: bool
    can_assess_quality: bool
    can_approve_transcript: bool
    can_remove_recording: bool


class AudioWorkflowSummaryResponse(BaseModel):
    context_version_id: str
    state: AudioWorkflowState
    recording: AudioWorkflowRecordingResponse | None = None
    latest_job: AudioWorkflowJobResponse | None = None
    latest_revision: TranscriptRevisionResponse | None = None
    deletion: AudioWorkflowDeletionResponse | None = None
    capabilities: AudioWorkflowCapabilitiesResponse


class TranscriptManualRevisionRequest(BaseModel):
    """Equal starts are allowed for overlapping segments; sequence-order starts never decrease."""

    segments: list[TranscriptSegmentInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segments(self) -> "TranscriptManualRevisionRequest":
        sequences = [
            item.sequence if item.sequence is not None else index
            for index, item in enumerate(self.segments, 1)
        ]
        if sequences != list(range(1, len(self.segments) + 1)):
            raise ValueError("Segments must use unique, ordered positive sequence values.")
        if any(item.end_ms <= item.start_ms for item in self.segments):
            raise ValueError("Each segment end timestamp must be after its start timestamp.")
        if any(
            next_item.start_ms < item.start_ms
            for item, next_item in zip(self.segments, self.segments[1:])
        ):
            raise ValueError("Segment start timestamps must not move backward in sequence order.")
        return self


class RecordingRemovalResponse(BaseModel):
    recording_id: str
    removed: bool


class TermDecisionRequest(BaseModel):
    decision: TermDecisionValue


class StudentTranscriptSegmentResponse(BaseModel):
    id: str
    sequence: int
    start_ms: int
    end_ms: int
    text: str
    corrected_glossary_term_id: str | None = None


class StudentTranscriptResponse(BaseModel):
    id: str
    recording_id: str
    provenance_label: str
    source_status: SourceStatus
    trusted_context_version: int
    segments: list[StudentTranscriptSegmentResponse] = Field(default_factory=list)
