from datetime import datetime

from pydantic import BaseModel, Field

from app.contracts.enums import ContextReviewEventType, TeacherReviewStatus


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


class StudentASRMisrecognitionResponse(BaseModel):
    id: str
    detected_text: str
    normalized_text: str


class StudentGlossaryTermResponse(BaseModel):
    id: str
    canonical_term: str
    malayalam_support_label: str | None
    definition: str
    malayalam_explanation: str | None
    sequence: int
    aliases: list[StudentTermAliasResponse] = Field(default_factory=list)
    misrecognitions: list[StudentASRMisrecognitionResponse] = Field(default_factory=list)


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
