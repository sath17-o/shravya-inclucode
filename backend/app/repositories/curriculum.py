from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.contracts.enums import ArtifactStatus, TeacherReviewStatus
from app.models.foundation import (
    Chapter,
    ConceptGlossaryTermLink,
    ConceptRecoveryPack,
    ContextReviewEvent,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    GlossaryTerm,
    LectureAudio,
    Lesson,
    TermSuggestion,
    TranscriptRevision,
    TranscriptSegment,
)


class CurriculumRepository:
    """Persistence queries for versioned curriculum aggregates; never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_course(self, course_id: str) -> Course | None:
        return self._session.get(Course, course_id)

    def get_context_version(self, context_version_id: str) -> CourseContextVersion | None:
        return self._session.get(CourseContextVersion, context_version_id)

    def get_context_with_graph(self, context_version_id: str) -> CourseContextVersion | None:
        lesson_options = (
            selectinload(CourseContextVersion.chapters)
            .selectinload(Chapter.lessons)
            .options(
                selectinload(Lesson.objectives),
                selectinload(Lesson.approved_materials),
                selectinload(Lesson.glossary_terms).selectinload(GlossaryTerm.aliases),
                selectinload(Lesson.glossary_terms).selectinload(GlossaryTerm.misrecognitions),
                selectinload(Lesson.concepts),
                selectinload(Lesson.concept_relationships),
                selectinload(Lesson.questions),
                selectinload(Lesson.audio_assets)
                .selectinload(LectureAudio.transcript_revisions)
                .selectinload(TranscriptRevision.segments)
                .selectinload(TranscriptSegment.term_suggestions)
                .selectinload(TermSuggestion.decisions),
                selectinload(Lesson.audio_assets)
                .selectinload(LectureAudio.transcript_revisions)
                .selectinload(TranscriptRevision.quality_assessments),
            )
        )
        statement = (
            select(CourseContextVersion)
            .where(CourseContextVersion.id == context_version_id)
            .options(
                lesson_options,
                selectinload(CourseContextVersion.concept_glossary_term_links),
                selectinload(CourseContextVersion.recovery_packs).selectinload(
                    ConceptRecoveryPack.concept
                ),
            )
        )
        return self._session.scalar(statement)

    def list_context_versions(self, course_id: str) -> list[CourseContextVersion]:
        statement = (
            select(CourseContextVersion)
            .where(CourseContextVersion.course_id == course_id)
            .order_by(CourseContextVersion.version_number, CourseContextVersion.id)
        )
        return list(self._session.scalars(statement))

    def get_highest_version_number(self, course_id: str) -> int:
        statement = select(func.max(CourseContextVersion.version_number)).where(
            CourseContextVersion.course_id == course_id
        )
        return self._session.scalar(statement) or 0

    def get_highest_approved_context(self, course_id: str) -> CourseContextVersion | None:
        statement = (
            select(CourseContextVersion)
            .where(
                CourseContextVersion.course_id == course_id,
                CourseContextVersion.teacher_review_status == TeacherReviewStatus.APPROVED,
            )
            .order_by(CourseContextVersion.version_number.desc(), CourseContextVersion.id.desc())
            .limit(1)
        )
        context = self._session.scalar(statement)
        return self.get_context_with_graph(context.id) if context is not None else None

    def list_student_visible_approved_lessons(self, course_id: str) -> list[Lesson]:
        context = self.get_highest_approved_context(course_id)
        if context is None:
            return []
        return [lesson for chapter in context.chapters for lesson in chapter.lessons]

    def find_non_stale_artifacts_from_older_approved_contexts(
        self, course_id: str, version_number: int
    ) -> list[GeneratedArtifact]:
        statement = (
            select(GeneratedArtifact)
            .join(CourseContextVersion)
            .where(
                CourseContextVersion.course_id == course_id,
                CourseContextVersion.version_number < version_number,
                CourseContextVersion.teacher_review_status == TeacherReviewStatus.APPROVED,
                GeneratedArtifact.generation_status != ArtifactStatus.STALE,
            )
        )
        return list(self._session.scalars(statement))

    def add_review_event(self, event: ContextReviewEvent) -> None:
        self._session.add(event)

    def list_review_events(self, context_version_id: str) -> list[ContextReviewEvent]:
        statement = (
            select(ContextReviewEvent)
            .where(ContextReviewEvent.context_version_id == context_version_id)
            .order_by(ContextReviewEvent.created_at, ContextReviewEvent.id)
        )
        return list(self._session.scalars(statement))

    def add_context(self, context: CourseContextVersion) -> None:
        self._session.add(context)

    def add_concept_glossary_term_link(self, link: ConceptGlossaryTermLink) -> None:
        self._session.add(link)

    def flush(self) -> None:
        self._session.flush()
