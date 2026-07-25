from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.contracts.enums import QualityStatus, TeacherReviewStatus
from app.contracts.teacher_review import DomainError
from app.models.foundation import Chapter, Course, CourseContextVersion, Lesson
from app.repositories.curriculum import CurriculumRepository
from app.services.transcript_provenance import recognised_provenance
from app.services.transcript_quality import unresolved_suggestion_count


@dataclass(frozen=True, slots=True)
class StudentCourseProjection:
    id: str
    title: str
    subject: str
    class_level: int
    grade_band: str


@dataclass(frozen=True, slots=True)
class StudentContextProjection:
    id: str
    version_number: int
    approved_at: datetime | None


@dataclass(frozen=True, slots=True)
class StudentObjectiveProjection:
    id: str
    objective_text: str
    malayalam_text: str | None
    sequence: int


@dataclass(frozen=True, slots=True)
class StudentMaterialProjection:
    id: str
    title: str
    material_type: str
    source_label: str
    content: str
    language: str
    sequence: int


@dataclass(frozen=True, slots=True)
class StudentTermAliasProjection:
    id: str
    alias: str
    normalized_alias: str


@dataclass(frozen=True, slots=True)
class StudentGlossaryTermProjection:
    id: str
    canonical_term: str
    malayalam_support_label: str | None
    definition: str
    malayalam_explanation: str | None
    sequence: int
    concept_ids: tuple[str, ...]
    aliases: tuple[StudentTermAliasProjection, ...]


@dataclass(frozen=True, slots=True)
class StudentConceptProjection:
    id: str
    concept_key: str
    title: str
    malayalam_title: str | None
    definition: str
    malayalam_definition: str | None
    sequence: int


@dataclass(frozen=True, slots=True)
class StudentRelationshipProjection:
    id: str
    source_concept_id: str
    target_concept_id: str
    relationship_type: str
    sequence: int


@dataclass(frozen=True, slots=True)
class StudentQuestionProjection:
    id: str
    related_concept_id: str | None
    source_type: str
    source_label: str
    question_text: str
    malayalam_question_text: str | None
    sequence: int
    year: int | None
    marks: int | None


@dataclass(frozen=True, slots=True)
class StudentTranscriptSegmentProjection:
    id: str
    sequence: int
    start_ms: int
    end_ms: int
    text: str
    corrected_glossary_term_id: str | None


@dataclass(frozen=True, slots=True)
class StudentTranscriptProjection:
    id: str
    recording_id: str
    provenance_label: str
    source_status: str
    trusted_context_version: int
    segments: tuple[StudentTranscriptSegmentProjection, ...]


@dataclass(frozen=True, slots=True)
class StudentRecoveryTextProjection:
    english: str
    malayalam: str


@dataclass(frozen=True, slots=True)
class StudentRecoverySupportProjection:
    concept_id: str
    cue: StudentRecoveryTextProjection
    example: StudentRecoveryTextProjection
    alternate_explanation: StudentRecoveryTextProjection


@dataclass(frozen=True, slots=True)
class StudentLessonProjection:
    id: str
    title: str
    sequence: int
    primary_language: str
    description: str | None
    objectives: tuple[StudentObjectiveProjection, ...]
    approved_materials: tuple[StudentMaterialProjection, ...]
    glossary_terms: tuple[StudentGlossaryTermProjection, ...]
    concepts: tuple[StudentConceptProjection, ...]
    concept_relationships: tuple[StudentRelationshipProjection, ...]
    questions: tuple[StudentQuestionProjection, ...]
    approved_transcript: StudentTranscriptProjection | None
    recovery_support: tuple[StudentRecoverySupportProjection, ...]


@dataclass(frozen=True, slots=True)
class StudentChapterProjection:
    id: str
    title: str
    sequence: int
    lessons: tuple[StudentLessonProjection, ...]


@dataclass(frozen=True, slots=True)
class StudentCurriculumProjection:
    course: StudentCourseProjection
    context: StudentContextProjection | None
    chapters: tuple[StudentChapterProjection, ...]


@dataclass(frozen=True, slots=True)
class StudentRevisionSummaryProjection:
    context_id: str
    version_number: int
    approved_at: datetime
    chapter_title: str
    lesson_title: str
    is_current: bool


@dataclass(frozen=True, slots=True)
class StudentRevisionLibraryProjection:
    course: StudentCourseProjection
    revisions: tuple[StudentRevisionSummaryProjection, ...]


class StudentCurriculumService:
    def __init__(self, repository: CurriculumRepository) -> None:
        self._repository = repository

    def get_current_context(self, course_id: str) -> StudentContextProjection | None:
        return self.get_curriculum_projection(course_id).context

    def list_current_lessons(self, course_id: str) -> list[StudentLessonProjection]:
        return [
            lesson
            for chapter in self.get_curriculum_projection(course_id).chapters
            for lesson in chapter.lessons
        ]

    def get_curriculum_projection(self, course_id: str) -> StudentCurriculumProjection:
        course = self._repository.get_course(course_id)
        if course is None:
            raise DomainError("course_not_found", "course.not_found", "not_found")
        course_projection = self._course_projection(course)
        context = self._repository.get_highest_approved_context(course_id)
        if context is None:
            return StudentCurriculumProjection(course=course_projection, context=None, chapters=())
        return self._projection_for_context(course_projection, context)

    def get_revision_library(self, course_id: str) -> StudentRevisionLibraryProjection:
        course = self._repository.get_course(course_id)
        if course is None:
            raise DomainError("course_not_found", "course.not_found", "not_found")
        visible: list[
            tuple[CourseContextVersion, StudentChapterProjection, StudentLessonProjection]
        ] = []
        for context in self._repository.list_approved_contexts_with_graph(course_id):
            projection = self._projection_for_context(self._course_projection(course), context)
            first_lesson = self._first_projected_lesson(projection)
            if context.approved_at is not None and first_lesson is not None:
                visible.append((context, *first_lesson))
        current_context_id = (
            max(visible, key=lambda item: (item[0].version_number, item[0].id))[0].id
            if visible
            else None
        )
        return StudentRevisionLibraryProjection(
            course=self._course_projection(course),
            revisions=tuple(
                StudentRevisionSummaryProjection(
                    context_id=context.id,
                    version_number=context.version_number,
                    approved_at=context.approved_at,
                    chapter_title=chapter.title,
                    lesson_title=lesson.title,
                    is_current=context.id == current_context_id,
                )
                for context, chapter, lesson in visible
            ),
        )

    def get_approved_revision_projection(
        self, course_id: str, context_version_id: str
    ) -> StudentCurriculumProjection:
        course = self._repository.get_course(course_id)
        if course is None:
            raise DomainError("course_not_found", "course.not_found", "not_found")
        context = self._repository.get_approved_context_for_course_with_graph(
            course_id, context_version_id
        )
        if context is None:
            raise DomainError(
                "student_revision_not_found", "student.revision_not_found", "not_found"
            )
        projection = self._projection_for_context(self._course_projection(course), context)
        if self._first_projected_lesson(projection) is None:
            raise DomainError(
                "student_revision_not_found", "student.revision_not_found", "not_found"
            )
        return projection

    @staticmethod
    def _first_projected_lesson(
        projection: StudentCurriculumProjection,
    ) -> tuple[StudentChapterProjection, StudentLessonProjection] | None:
        for chapter in projection.chapters:
            if chapter.lessons:
                return chapter, chapter.lessons[0]
        return None

    @staticmethod
    def _course_projection(course: Course) -> StudentCourseProjection:
        return StudentCourseProjection(
            id=course.id,
            title=course.title,
            subject=course.subject,
            class_level=course.class_level,
            grade_band=course.grade_band,
        )

    @staticmethod
    def _projection_for_context(
        course_projection: StudentCourseProjection, context: CourseContextVersion
    ) -> StudentCurriculumProjection:
        return StudentCurriculumProjection(
            course=course_projection,
            context=StudentContextProjection(
                id=context.id,
                version_number=context.version_number,
                approved_at=context.approved_at,
            ),
            chapters=tuple(
                StudentCurriculumService._chapter_projection(chapter, context)
                for chapter in sorted(context.chapters, key=lambda item: (item.sequence, item.id))
            ),
        )

    @staticmethod
    def _chapter_projection(chapter: Chapter, context) -> StudentChapterProjection:
        return StudentChapterProjection(
            id=chapter.id,
            title=chapter.title,
            sequence=chapter.sequence,
            lessons=tuple(
                StudentCurriculumService._lesson_projection(lesson, context)
                for lesson in sorted(chapter.lessons, key=lambda item: (item.sequence, item.id))
            ),
        )

    @staticmethod
    def _lesson_projection(lesson: Lesson, context) -> StudentLessonProjection:
        linked_concept_ids: dict[str, list[str]] = {}
        lesson_concept_ids = {concept.id for concept in lesson.concepts}
        concept_sequences = {concept.id: concept.sequence for concept in lesson.concepts}
        for link in sorted(
            context.concept_glossary_term_links,
            key=lambda item: (
                item.glossary_term_id,
                concept_sequences.get(item.concept_id, 0),
                item.sequence,
                item.id,
            ),
        ):
            if link.concept_id in lesson_concept_ids:
                linked_concept_ids.setdefault(link.glossary_term_id, []).append(link.concept_id)
        return StudentLessonProjection(
            id=lesson.id,
            title=lesson.title,
            sequence=lesson.sequence,
            primary_language=lesson.primary_language,
            description=lesson.description,
            objectives=tuple(
                StudentObjectiveProjection(
                    id=item.id,
                    objective_text=item.objective_text,
                    malayalam_text=item.malayalam_text,
                    sequence=item.sequence,
                )
                for item in sorted(lesson.objectives, key=lambda item: (item.sequence, item.id))
            ),
            approved_materials=tuple(
                StudentMaterialProjection(
                    id=item.id,
                    title=item.title,
                    material_type=item.material_type.value,
                    source_label=item.source_label,
                    content=item.content,
                    language=item.language.value,
                    sequence=item.sequence,
                )
                for item in sorted(
                    (
                        item
                        for item in lesson.approved_materials
                        if item.teacher_review_status is TeacherReviewStatus.APPROVED
                    ),
                    key=lambda item: (item.sequence, item.id),
                )
            ),
            glossary_terms=tuple(
                StudentGlossaryTermProjection(
                    id=item.id,
                    canonical_term=item.canonical_term,
                    malayalam_support_label=item.malayalam_support_label,
                    definition=item.definition,
                    malayalam_explanation=item.malayalam_explanation,
                    sequence=item.sequence,
                    concept_ids=tuple(linked_concept_ids.get(item.id, ())),
                    aliases=tuple(
                        StudentTermAliasProjection(
                            id=alias.id,
                            alias=alias.alias,
                            normalized_alias=alias.normalized_alias,
                        )
                        for alias in sorted(
                            item.aliases, key=lambda alias: (alias.normalized_alias, alias.id)
                        )
                    ),
                )
                for item in sorted(lesson.glossary_terms, key=lambda item: (item.sequence, item.id))
            ),
            concepts=tuple(
                StudentConceptProjection(
                    id=item.id,
                    concept_key=item.concept_key,
                    title=item.title,
                    malayalam_title=item.malayalam_title,
                    definition=item.definition,
                    malayalam_definition=item.malayalam_definition,
                    sequence=item.sequence,
                )
                for item in sorted(lesson.concepts, key=lambda item: (item.sequence, item.id))
            ),
            concept_relationships=tuple(
                StudentRelationshipProjection(
                    id=item.id,
                    source_concept_id=item.source_concept_id,
                    target_concept_id=item.target_concept_id,
                    relationship_type=item.relationship_type.value,
                    sequence=item.sequence,
                )
                for item in sorted(
                    lesson.concept_relationships, key=lambda item: (item.sequence, item.id)
                )
            ),
            questions=tuple(
                StudentQuestionProjection(
                    id=item.id,
                    related_concept_id=item.related_concept_id,
                    source_type=item.source_type.value,
                    source_label=item.source_label,
                    question_text=item.question_text,
                    malayalam_question_text=item.malayalam_question_text,
                    sequence=item.sequence,
                    year=item.year,
                    marks=item.marks,
                )
                for item in sorted(
                    (
                        item
                        for item in lesson.questions
                        if item.teacher_review_status is TeacherReviewStatus.APPROVED
                    ),
                    key=lambda item: (item.sequence, item.id),
                )
            ),
            approved_transcript=StudentCurriculumService._approved_transcript(
                lesson, context.version_number
            ),
            recovery_support=StudentCurriculumService._recovery_support(lesson, context),
        )

    @staticmethod
    def _recovery_support(lesson: Lesson, context) -> tuple[StudentRecoverySupportProjection, ...]:
        concepts = sorted(lesson.concepts, key=lambda item: (item.sequence, item.id))
        concept_ids = {concept.id for concept in concepts}
        by_concept = {pack.concept_id: pack for pack in context.recovery_packs}
        # Packs are projected only as a complete, approved set for the selected context.
        if set(by_concept) != concept_ids:
            return ()
        ordered = [by_concept[concept.id] for concept in concepts]
        if any(
            pack.context_version_id != context.id
            or pack.teacher_review_status is not TeacherReviewStatus.APPROVED
            or pack.approved_at is None
            or not all(
                value.strip()
                for value in (
                    pack.cue_en,
                    pack.cue_ml,
                    pack.example_en,
                    pack.example_ml,
                    pack.alternate_explanation_en,
                    pack.alternate_explanation_ml,
                )
            )
            for pack in ordered
        ):
            return ()
        return tuple(
            StudentRecoverySupportProjection(
                concept_id=pack.concept_id,
                cue=StudentRecoveryTextProjection(pack.cue_en, pack.cue_ml),
                example=StudentRecoveryTextProjection(pack.example_en, pack.example_ml),
                alternate_explanation=StudentRecoveryTextProjection(
                    pack.alternate_explanation_en, pack.alternate_explanation_ml
                ),
            )
            for pack in ordered
        )

    @staticmethod
    def _approved_transcript(
        lesson: Lesson, context_version: int
    ) -> StudentTranscriptProjection | None:
        approved = []
        for recording in lesson.audio_assets:
            revision = max(
                recording.transcript_revisions,
                key=lambda item: (item.revision_number, item.id),
                default=None,
            )
            if revision is None:
                continue
            quality = max(
                revision.quality_assessments,
                key=lambda item: (item.created_at, item.id),
                default=None,
            )
            if (
                revision.teacher_review_status is TeacherReviewStatus.APPROVED
                and quality is not None
                and quality.quality_status is QualityStatus.VERIFIED
                and recognised_provenance(revision).supported
                and unresolved_suggestion_count(revision) == 0
            ):
                approved.append(revision)
        if not approved:
            return None
        revision = max(approved, key=lambda item: (item.created_at, item.revision_number, item.id))
        corrected_by_segment: dict[str, str] = {}
        display_text_by_segment: dict[str, str] = {
            segment.id: segment.text for segment in revision.segments
        }
        glossary_by_id = {term.id: term for term in lesson.glossary_terms}
        for segment in revision.segments:
            for suggestion in segment.term_suggestions:
                decision = max(
                    suggestion.decisions, key=lambda item: (item.created_at, item.id), default=None
                )
                if decision is not None and decision.decision.value == "CONFIRMED":
                    glossary = glossary_by_id.get(suggestion.glossary_term_id or "")
                    if glossary is not None:
                        corrected_by_segment[segment.id] = glossary.id
                        display_text_by_segment[segment.id] = display_text_by_segment[
                            segment.id
                        ].replace(suggestion.detected_text, glossary.canonical_term)
        return StudentTranscriptProjection(
            id=revision.id,
            recording_id=revision.lecture_audio_id,
            provenance_label=revision.provenance_label,
            source_status=revision.source_status.value,
            trusted_context_version=context_version,
            segments=tuple(
                StudentTranscriptSegmentProjection(
                    id=segment.id,
                    sequence=segment.sequence,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=display_text_by_segment[segment.id],
                    corrected_glossary_term_id=corrected_by_segment.get(segment.id),
                )
                for segment in sorted(revision.segments, key=lambda item: (item.sequence, item.id))
            ),
        )
