from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.contracts.enums import TeacherReviewStatus
from app.contracts.teacher_review import DomainError
from app.models.foundation import Chapter, Lesson
from app.repositories.curriculum import CurriculumRepository


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
class StudentASRVariantProjection:
    id: str
    detected_text: str
    normalized_text: str


@dataclass(frozen=True, slots=True)
class StudentGlossaryTermProjection:
    id: str
    canonical_term: str
    malayalam_support_label: str | None
    definition: str
    malayalam_explanation: str | None
    sequence: int
    aliases: tuple[StudentTermAliasProjection, ...]
    misrecognitions: tuple[StudentASRVariantProjection, ...]


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
        course_projection = StudentCourseProjection(
            id=course.id,
            title=course.title,
            subject=course.subject,
            class_level=course.class_level,
            grade_band=course.grade_band,
        )
        context = self._repository.get_highest_approved_context(course_id)
        if context is None:
            return StudentCurriculumProjection(course=course_projection, context=None, chapters=())
        return StudentCurriculumProjection(
            course=course_projection,
            context=StudentContextProjection(
                id=context.id,
                version_number=context.version_number,
                approved_at=context.approved_at,
            ),
            chapters=tuple(
                self._chapter_projection(chapter)
                for chapter in sorted(context.chapters, key=lambda item: (item.sequence, item.id))
            ),
        )

    @staticmethod
    def _chapter_projection(chapter: Chapter) -> StudentChapterProjection:
        return StudentChapterProjection(
            id=chapter.id,
            title=chapter.title,
            sequence=chapter.sequence,
            lessons=tuple(
                StudentCurriculumService._lesson_projection(lesson)
                for lesson in sorted(chapter.lessons, key=lambda item: (item.sequence, item.id))
            ),
        )

    @staticmethod
    def _lesson_projection(lesson: Lesson) -> StudentLessonProjection:
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
                    misrecognitions=tuple(
                        StudentASRVariantProjection(
                            id=variant.id,
                            detected_text=variant.detected_text,
                            normalized_text=variant.normalized_text,
                        )
                        for variant in sorted(
                            item.misrecognitions,
                            key=lambda variant: (variant.normalized_text, variant.id),
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
        )
