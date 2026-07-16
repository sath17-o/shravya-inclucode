from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.contracts.enums import (
    ArtifactStatus,
    ConceptRelationshipType,
    ConceptState,
    ContentLanguage,
    ContextReviewEventType,
    JobStatus,
    MaterialType,
    ProcessingJobType,
    QualityStatus,
    QuestionSourceType,
    SourceStatus,
    TeacherReviewStatus,
    TermDecisionValue,
    UncertaintyStatus,
)
from app.db.base import Base


def uuid4_string() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def sqlite_enum(enum_type: type, name: str, length: int) -> Enum:
    """Use named SQLite CHECK constraints rather than database-native enums."""
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum_class: [member.value for member in enum_class],
        length=length,
    )


class IdTimestampMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_string)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class LocalLearnerProfile(IdTimestampMixin, Base):
    __tablename__ = "local_learner_profiles"

    local_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    profile_schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        CheckConstraint("profile_schema_version >= 1", name="ck_profile_schema_version"),
    )

    preferences: Mapped[LearningPreferenceProfile | None] = relationship(
        back_populates="learner_profile",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list[LearningSession]] = relationship(
        back_populates="learner_profile", cascade="all, delete-orphan", passive_deletes=True
    )
    concept_states: Mapped[list[LearnerConceptState]] = relationship(
        back_populates="learner_profile", cascade="all, delete-orphan", passive_deletes=True
    )


class Course(IdTimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("class_level BETWEEN 5 AND 10", name="ck_courses_class_level"),
        CheckConstraint(
            "((class_level BETWEEN 5 AND 7 AND grade_band = '5-7') "
            "OR (class_level BETWEEN 8 AND 10 AND grade_band = '8-10'))",
            name="ck_courses_grade_band",
        ),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    class_level: Mapped[int] = mapped_column(Integer, nullable=False)
    grade_band: Mapped[str] = mapped_column(String(20), nullable=False)
    board_source: Mapped[str | None] = mapped_column(String(200))
    context_versions: Mapped[list[CourseContextVersion]] = relationship(
        back_populates="course", cascade="all, delete-orphan", passive_deletes=True
    )


class CourseContextVersion(IdTimestampMixin, Base):
    __tablename__ = "course_context_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version_number", name="uq_course_context_version"),
        CheckConstraint("version_number >= 1", name="ck_course_context_version_number"),
    )

    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_review_status: Mapped[TeacherReviewStatus] = mapped_column(
        sqlite_enum(TeacherReviewStatus, "teacher_review_status", 20),
        default=TeacherReviewStatus.DRAFT,
        nullable=False,
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    copied_from_context_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("course_context_versions.id", ondelete="SET NULL")
    )
    course: Mapped[Course] = relationship(back_populates="context_versions")
    copied_from_context_version: Mapped[CourseContextVersion | None] = relationship(
        remote_side="CourseContextVersion.id", foreign_keys=[copied_from_context_version_id]
    )
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="context_version", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[GeneratedArtifact]] = relationship(
        back_populates="course_context_version", cascade="all, delete-orphan", passive_deletes=True
    )


class Chapter(IdTimestampMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("context_version_id", "sequence", name="uq_chapter_context_sequence"),
        CheckConstraint("sequence >= 1", name="ck_chapters_sequence"),
    )

    context_version_id: Mapped[str] = mapped_column(
        ForeignKey("course_context_versions.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    context_version: Mapped[CourseContextVersion] = relationship(back_populates="chapters")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", passive_deletes=True
    )


class Lesson(IdTimestampMixin, Base):
    """A lesson belongs only to Chapter; context is derived through the chapter."""

    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sequence", name="uq_lesson_chapter_sequence"),
        UniqueConstraint("chapter_id", "title", name="uq_lesson_chapter_title"),
        CheckConstraint("sequence >= 1", name="ck_lessons_sequence"),
    )

    chapter_id: Mapped[str] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_language: Mapped[str] = mapped_column(String(20), default="ml", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[Chapter] = relationship(back_populates="lessons")
    objectives: Mapped[list[LearningObjective]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    glossary_terms: Mapped[list[GlossaryTerm]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    audio_assets: Mapped[list[LectureAudio]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    concepts: Mapped[list[Concept]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[GeneratedArtifact]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    questions: Mapped[list[QuestionItem]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    approved_materials: Mapped[list[ApprovedMaterial]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    concept_relationships: Mapped[list[ConceptRelationship]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )
    learning_sessions: Mapped[list[LearningSession]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )


class LearningObjective(IdTimestampMixin, Base):
    __tablename__ = "learning_objectives"
    __table_args__ = (
        UniqueConstraint("lesson_id", "sequence", name="uq_objective_lesson_sequence"),
        CheckConstraint("sequence >= 1", name="ck_learning_objectives_sequence"),
    )

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    objective_text: Mapped[str] = mapped_column(Text, nullable=False)
    malayalam_text: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson: Mapped[Lesson] = relationship(back_populates="objectives")


class GlossaryTerm(IdTimestampMixin, Base):
    __tablename__ = "glossary_terms"
    __table_args__ = (
        UniqueConstraint("lesson_id", "canonical_term", name="uq_glossary_lesson_term"),
        UniqueConstraint("lesson_id", "sequence", name="uq_glossary_lesson_sequence"),
        CheckConstraint("sequence >= 1", name="ck_glossary_terms_sequence"),
    )

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    canonical_term: Mapped[str] = mapped_column(String(200), nullable=False)
    malayalam_support_label: Mapped[str | None] = mapped_column(String(200))
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    malayalam_explanation: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson: Mapped[Lesson] = relationship(back_populates="glossary_terms")
    aliases: Mapped[list[TermAlias]] = relationship(
        back_populates="glossary_term", cascade="all, delete-orphan", passive_deletes=True
    )
    misrecognitions: Mapped[list[ASRMisrecognition]] = relationship(
        back_populates="glossary_term", cascade="all, delete-orphan", passive_deletes=True
    )


class TermAlias(IdTimestampMixin, Base):
    __tablename__ = "term_aliases"
    __table_args__ = (
        UniqueConstraint("glossary_term_id", "normalized_alias", name="uq_term_alias"),
    )

    glossary_term_id: Mapped[str] = mapped_column(
        ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False)
    glossary_term: Mapped[GlossaryTerm] = relationship(back_populates="aliases")


class ASRMisrecognition(IdTimestampMixin, Base):
    __tablename__ = "asr_misrecognitions"
    __table_args__ = (
        UniqueConstraint("glossary_term_id", "normalized_text", name="uq_asr_misrecognition"),
    )

    glossary_term_id: Mapped[str] = mapped_column(
        ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False
    )
    detected_text: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(200), nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text)
    glossary_term: Mapped[GlossaryTerm] = relationship(back_populates="misrecognitions")


class LectureAudio(IdTimestampMixin, Base):
    __tablename__ = "lecture_audio"

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_status: Mapped[SourceStatus] = mapped_column(
        sqlite_enum(SourceStatus, "lecture_audio_source_status", 20), nullable=False
    )
    lesson: Mapped[Lesson] = relationship(back_populates="audio_assets")
    transcript_revisions: Mapped[list[TranscriptRevision]] = relationship(
        back_populates="lecture_audio", cascade="all, delete-orphan", passive_deletes=True
    )


class TranscriptRevision(IdTimestampMixin, Base):
    __tablename__ = "transcript_revisions"
    __table_args__ = (
        UniqueConstraint(
            "lecture_audio_id", "revision_number", name="uq_audio_transcript_revision"
        ),
        CheckConstraint("revision_number >= 1", name="ck_transcript_revisions_number"),
    )

    lecture_audio_id: Mapped[str] = mapped_column(
        ForeignKey("lecture_audio.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_status: Mapped[SourceStatus] = mapped_column(
        sqlite_enum(SourceStatus, "transcript_revision_source_status", 20), nullable=False
    )
    language: Mapped[str] = mapped_column(String(20), default="ml", nullable=False)
    lecture_audio: Mapped[LectureAudio] = relationship(back_populates="transcript_revisions")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript_revision", cascade="all, delete-orphan", passive_deletes=True
    )
    quality_assessments: Mapped[list[TranscriptQualityAssessment]] = relationship(
        back_populates="transcript_revision", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[GeneratedArtifact]] = relationship(
        back_populates="source_transcript_revision"
    )


class TranscriptSegment(IdTimestampMixin, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint(
            "transcript_revision_id", "sequence", name="uq_transcript_segment_sequence"
        ),
        CheckConstraint("sequence >= 1", name="ck_transcript_segments_sequence"),
        CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start"),
        CheckConstraint("end_ms > start_ms", name="ck_transcript_segments_end"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_transcript_segments_confidence",
        ),
    )

    transcript_revision_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_revisions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    transcript_revision: Mapped[TranscriptRevision] = relationship(back_populates="segments")
    concept_evidence: Mapped[list[ConceptEvidence]] = relationship(
        back_populates="transcript_segment", cascade="all, delete-orphan", passive_deletes=True
    )
    term_suggestions: Mapped[list[TermSuggestion]] = relationship(
        back_populates="transcript_segment"
    )


class TermSuggestion(IdTimestampMixin, Base):
    __tablename__ = "term_suggestions"
    __table_args__ = (
        CheckConstraint("character_start >= 0", name="ck_term_suggestions_character_start"),
        CheckConstraint(
            "character_end > character_start", name="ck_term_suggestions_character_end"
        ),
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 1)",
            name="ck_term_suggestions_match_score",
        ),
    )

    transcript_segment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False
    )
    glossary_term_id: Mapped[str | None] = mapped_column(
        ForeignKey("glossary_terms.id", ondelete="SET NULL")
    )
    detected_text: Mapped[str] = mapped_column(String(200), nullable=False)
    character_start: Mapped[int] = mapped_column(Integer, nullable=False)
    character_end: Mapped[int] = mapped_column(Integer, nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    context_snapshot: Mapped[str | None] = mapped_column(Text)
    transcript_segment: Mapped[TranscriptSegment] = relationship(back_populates="term_suggestions")
    decisions: Mapped[list[TermDecision]] = relationship(
        back_populates="term_suggestion", cascade="all, delete-orphan", passive_deletes=True
    )


class TermDecision(IdTimestampMixin, Base):
    """Append-only decision history; later services resolve the most recent decision."""

    __tablename__ = "term_decisions"

    term_suggestion_id: Mapped[str] = mapped_column(
        ForeignKey("term_suggestions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[TermDecisionValue] = mapped_column(
        sqlite_enum(TermDecisionValue, "term_decision_value", 20), nullable=False
    )
    decided_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    term_suggestion: Mapped[TermSuggestion] = relationship(back_populates="decisions")


class TranscriptQualityAssessment(IdTimestampMixin, Base):
    __tablename__ = "transcript_quality_assessments"
    __table_args__ = (
        UniqueConstraint("transcript_revision_id", name="uq_quality_assessment_revision"),
    )

    transcript_revision_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_revisions.id", ondelete="CASCADE"), nullable=False
    )
    quality_status: Mapped[QualityStatus] = mapped_column(
        sqlite_enum(QualityStatus, "quality_status", 20), nullable=False
    )
    transcript_revision: Mapped[TranscriptRevision] = relationship(
        back_populates="quality_assessments"
    )
    reasons: Mapped[list[TranscriptQualityReason]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )


class TranscriptQualityReason(IdTimestampMixin, Base):
    __tablename__ = "transcript_quality_reasons"
    __table_args__ = (
        UniqueConstraint("assessment_id", "reason_code", name="uq_quality_reason_code"),
        CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'BLOCKING')", name="ck_quality_reason_severity"
        ),
    )

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_quality_assessments.id", ondelete="CASCADE"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message_key: Mapped[str] = mapped_column(String(200), nullable=False)
    measured_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    recovery_action: Mapped[str | None] = mapped_column(String(200))
    assessment: Mapped[TranscriptQualityAssessment] = relationship(back_populates="reasons")


class ProcessingJob(IdTimestampMixin, Base):
    """entity_id is intentionally generic; it identifies the job's typed domain entity."""

    __tablename__ = "processing_jobs"
    __table_args__ = (CheckConstraint("retry_count >= 0", name="ck_processing_jobs_retry_count"),)

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[ProcessingJobType] = mapped_column(
        sqlite_enum(ProcessingJobType, "processing_job_type", 40), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sqlite_enum(JobStatus, "job_status", 20), default=JobStatus.QUEUED, nullable=False
    )
    progress_message: Mapped[str] = mapped_column(String(500), default="Queued", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    recoverable: Mapped[bool | None] = mapped_column(Boolean)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lesson: Mapped[Lesson] = relationship(back_populates="processing_jobs")


class Concept(IdTimestampMixin, Base):
    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("lesson_id", "sequence", name="uq_concept_lesson_sequence"),
        UniqueConstraint("lesson_id", "concept_key", name="uq_concept_lesson_key"),
        CheckConstraint("sequence >= 1", name="ck_concepts_sequence"),
    )

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    concept_key: Mapped[str] = mapped_column(String(100), nullable=False)
    malayalam_title: Mapped[str | None] = mapped_column(String(250))
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    malayalam_definition: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson: Mapped[Lesson] = relationship(back_populates="concepts")
    evidence: Mapped[list[ConceptEvidence]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", passive_deletes=True
    )
    learner_states: Mapped[list[LearnerConceptState]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", passive_deletes=True
    )
    source_artifacts: Mapped[list[ArtifactSourceConcept]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", passive_deletes=True
    )


class ConceptEvidence(IdTimestampMixin, Base):
    __tablename__ = "concept_evidence"
    __table_args__ = (
        UniqueConstraint("concept_id", "transcript_segment_id", name="uq_concept_evidence"),
    )

    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    transcript_segment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False
    )
    concept: Mapped[Concept] = relationship(back_populates="evidence")
    transcript_segment: Mapped[TranscriptSegment] = relationship(back_populates="concept_evidence")


class GeneratedArtifact(IdTimestampMixin, Base):
    __tablename__ = "generated_artifacts"

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    source_transcript_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("transcript_revisions.id", ondelete="SET NULL")
    )
    course_context_version_id: Mapped[str] = mapped_column(
        ForeignKey("course_context_versions.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(150))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    source_status: Mapped[SourceStatus] = mapped_column(
        sqlite_enum(SourceStatus, "artifact_source_status", 20), nullable=False
    )
    quality_status: Mapped[QualityStatus] = mapped_column(
        sqlite_enum(QualityStatus, "artifact_quality_status", 20), nullable=False
    )
    uncertainty_status: Mapped[UncertaintyStatus] = mapped_column(
        sqlite_enum(UncertaintyStatus, "uncertainty_status", 20), nullable=False
    )
    uncertainty_note: Mapped[str | None] = mapped_column(Text)
    teacher_review_status: Mapped[TeacherReviewStatus] = mapped_column(
        sqlite_enum(TeacherReviewStatus, "artifact_teacher_review_status", 20),
        default=TeacherReviewStatus.DRAFT,
        nullable=False,
    )
    generation_status: Mapped[ArtifactStatus] = mapped_column(
        sqlite_enum(ArtifactStatus, "artifact_status", 30),
        default=ArtifactStatus.BLOCKED_BY_QUALITY,
        nullable=False,
    )
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_reason: Mapped[str | None] = mapped_column(Text)
    lesson: Mapped[Lesson] = relationship(back_populates="artifacts")
    source_transcript_revision: Mapped[TranscriptRevision | None] = relationship(
        back_populates="artifacts"
    )
    course_context_version: Mapped[CourseContextVersion] = relationship(back_populates="artifacts")
    source_concepts: Mapped[list[ArtifactSourceConcept]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan", passive_deletes=True
    )
    source_references: Mapped[list[ArtifactSourceReference]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan", passive_deletes=True
    )


class ArtifactSourceConcept(IdTimestampMixin, Base):
    __tablename__ = "artifact_source_concepts"
    __table_args__ = (
        UniqueConstraint("artifact_id", "concept_id", name="uq_artifact_source_concept"),
    )

    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("generated_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    artifact: Mapped[GeneratedArtifact] = relationship(back_populates="source_concepts")
    concept: Mapped[Concept] = relationship(back_populates="source_artifacts")


class ArtifactSourceReference(IdTimestampMixin, Base):
    __tablename__ = "artifact_source_references"

    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("generated_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False)
    display_text: Mapped[str] = mapped_column(Text, nullable=False)
    artifact: Mapped[GeneratedArtifact] = relationship(back_populates="source_references")


class LearningPreferenceProfile(IdTimestampMixin, Base):
    __tablename__ = "learning_preference_profiles"

    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("local_learner_profiles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    interface_language: Mapped[str] = mapped_column(String(20), default="bilingual", nullable=False)
    text_size: Mapped[str] = mapped_column(String(30), default="default", nullable=False)
    line_spacing: Mapped[str] = mapped_column(String(30), default="default", nullable=False)
    learner_profile: Mapped[LocalLearnerProfile] = relationship(back_populates="preferences")


class LearningSession(IdTimestampMixin, Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        UniqueConstraint(
            "learner_profile_id", "lesson_id", name="uq_learning_session_profile_lesson"
        ),
        CheckConstraint("resume_payload_version >= 1", name="ck_learning_sessions_payload_version"),
    )

    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("local_learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    current_route: Mapped[str] = mapped_column(String(250), nullable=False)
    resume_payload_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resume_payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    learner_profile: Mapped[LocalLearnerProfile] = relationship(back_populates="sessions")
    lesson: Mapped[Lesson] = relationship(back_populates="learning_sessions")


class LearnerConceptState(IdTimestampMixin, Base):
    __tablename__ = "learner_concept_states"
    __table_args__ = (
        UniqueConstraint("learner_profile_id", "concept_id", name="uq_learner_concept_state"),
    )

    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("local_learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[ConceptState] = mapped_column(
        sqlite_enum(ConceptState, "concept_state", 40),
        default=ConceptState.NOT_STARTED,
        nullable=False,
    )
    learner_profile: Mapped[LocalLearnerProfile] = relationship(back_populates="concept_states")
    concept: Mapped[Concept] = relationship(back_populates="learner_states")


class QuestionItem(IdTimestampMixin, Base):
    __tablename__ = "question_items"
    __table_args__ = (
        CheckConstraint("year IS NULL OR year > 0", name="ck_question_items_year"),
        CheckConstraint("marks IS NULL OR marks > 0", name="ck_question_items_marks"),
        CheckConstraint("sequence >= 1", name="ck_question_items_sequence"),
        UniqueConstraint("lesson_id", "sequence", name="uq_question_lesson_sequence"),
    )

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    related_concept_id: Mapped[str | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL")
    )
    source_type: Mapped[QuestionSourceType] = mapped_column(
        sqlite_enum(QuestionSourceType, "question_source_type", 30), nullable=False
    )
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    malayalam_question_text: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    marks: Mapped[int | None] = mapped_column(Integer)
    teacher_review_status: Mapped[TeacherReviewStatus] = mapped_column(
        sqlite_enum(TeacherReviewStatus, "question_teacher_review_status", 20),
        default=TeacherReviewStatus.DRAFT,
        nullable=False,
    )
    lesson: Mapped[Lesson] = relationship(back_populates="questions")


class ApprovedMaterial(IdTimestampMixin, Base):
    __tablename__ = "approved_materials"
    __table_args__ = (
        UniqueConstraint("lesson_id", "sequence", name="uq_material_lesson_sequence"),
        CheckConstraint("sequence >= 1", name="ck_materials_sequence"),
    )

    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    material_type: Mapped[MaterialType] = mapped_column(
        sqlite_enum(MaterialType, "material_type", 20), nullable=False
    )
    source_label: Mapped[str] = mapped_column(String(250), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[ContentLanguage] = mapped_column(
        sqlite_enum(ContentLanguage, "material_language", 20), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_review_status: Mapped[TeacherReviewStatus] = mapped_column(
        sqlite_enum(TeacherReviewStatus, "material_teacher_review_status", 20),
        default=TeacherReviewStatus.DRAFT,
        nullable=False,
    )
    lesson: Mapped[Lesson] = relationship(back_populates="approved_materials")


class ConceptRelationship(IdTimestampMixin, Base):
    __tablename__ = "concept_relationships"
    __table_args__ = (
        CheckConstraint("source_concept_id != target_concept_id", name="ck_relationship_not_self"),
        CheckConstraint("sequence >= 1", name="ck_relationship_sequence"),
        UniqueConstraint(
            "source_concept_id",
            "target_concept_id",
            "relationship_type",
            name="uq_relationship_tuple",
        ),
        UniqueConstraint("lesson_id", "sequence", name="uq_relationship_lesson_sequence"),
    )
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    source_concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    target_concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[ConceptRelationshipType] = mapped_column(
        sqlite_enum(ConceptRelationshipType, "concept_relationship_type", 20), nullable=False
    )
    teacher_note: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson: Mapped[Lesson] = relationship(back_populates="concept_relationships")
    source_concept: Mapped[Concept] = relationship(foreign_keys=[source_concept_id])
    target_concept: Mapped[Concept] = relationship(foreign_keys=[target_concept_id])


class ContextReviewEvent(Base):
    __tablename__ = "context_review_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_string)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    context_version_id: Mapped[str] = mapped_column(
        ForeignKey("course_context_versions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[ContextReviewEventType] = mapped_column(
        sqlite_enum(ContextReviewEventType, "context_review_event_type", 30), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


# These names are part of the immutable initial migration and must remain in
# metadata so Alembic autogenerate reports no spurious index removals.
Index("ix_context_versions_course", CourseContextVersion.course_id)
Index("ix_chapters_context", Chapter.context_version_id)
Index("ix_lessons_chapter", Lesson.chapter_id)
Index("ix_objectives_lesson", LearningObjective.lesson_id)
Index("ix_glossary_lesson", GlossaryTerm.lesson_id)
Index("ix_audio_lesson", LectureAudio.lesson_id)
Index("ix_revisions_audio", TranscriptRevision.lecture_audio_id)
Index("ix_segments_revision", TranscriptSegment.transcript_revision_id)
Index("ix_suggestions_segment", TermSuggestion.transcript_segment_id)
Index("ix_assessments_revision", TranscriptQualityAssessment.transcript_revision_id)
Index("ix_reasons_assessment", TranscriptQualityReason.assessment_id)
Index("ix_jobs_lesson", ProcessingJob.lesson_id)
Index("ix_concepts_lesson", Concept.lesson_id)
Index("ix_artifacts_lesson", GeneratedArtifact.lesson_id)
Index("ix_artifact_concepts_artifact", ArtifactSourceConcept.artifact_id)
Index("ix_artifact_references_artifact", ArtifactSourceReference.artifact_id)
Index("ix_sessions_profile", LearningSession.learner_profile_id)
Index("ix_states_profile", LearnerConceptState.learner_profile_id)
Index("ix_questions_lesson", QuestionItem.lesson_id)
Index("ix_context_copied_from", CourseContextVersion.copied_from_context_version_id)
Index("ix_materials_lesson_sequence", ApprovedMaterial.lesson_id, ApprovedMaterial.sequence)
Index("ix_glossary_lesson_sequence", GlossaryTerm.lesson_id, GlossaryTerm.sequence)
Index("ix_aliases_glossary", TermAlias.glossary_term_id)
Index("ix_misrecognitions_glossary", ASRMisrecognition.glossary_term_id)
Index("ix_concept_relationships_lesson", ConceptRelationship.lesson_id)
Index("ix_concept_relationships_source", ConceptRelationship.source_concept_id)
Index("ix_concept_relationships_target", ConceptRelationship.target_concept_id)
Index(
    "ix_review_events_context_created",
    ContextReviewEvent.context_version_id,
    ContextReviewEvent.created_at,
)
Index("ix_artifacts_context", GeneratedArtifact.course_context_version_id)
Index("ix_objectives_lesson_sequence", LearningObjective.lesson_id, LearningObjective.sequence)
Index("ix_concepts_lesson_sequence", Concept.lesson_id, Concept.sequence)
Index("ix_questions_lesson_sequence", QuestionItem.lesson_id, QuestionItem.sequence)
