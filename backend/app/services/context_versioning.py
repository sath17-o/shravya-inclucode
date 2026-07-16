from __future__ import annotations

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.enums import ContextReviewEventType, TeacherReviewStatus
from app.contracts.teacher_review import DomainError
from app.models.foundation import (
    ApprovedMaterial,
    ASRMisrecognition,
    Chapter,
    Concept,
    ConceptRelationship,
    ContextReviewEvent,
    CourseContextVersion,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
    TermAlias,
)
from app.repositories.curriculum import CurriculumRepository


class ContextVersioningService:
    def __init__(self, session: Session, repository: CurriculumRepository) -> None:
        self._session = session
        self._repository = repository

    def create_draft_from_approved(
        self, source_context_id: str, actor_role: str = "teacher", note: str | None = None
    ) -> CourseContextVersion:
        source = self._repository.get_context_with_graph(source_context_id)
        if source is None:
            raise DomainError("context_not_found", "context.not_found", "not_found")
        if source.teacher_review_status is not TeacherReviewStatus.APPROVED:
            raise DomainError(
                "source_context_not_approved", "context.source_not_approved", "validation"
            )
        self._validate_source_remaps(source)
        copy = CourseContextVersion(
            course_id=source.course_id,
            version_number=self._repository.get_highest_version_number(source.course_id) + 1,
            teacher_review_status=TeacherReviewStatus.DRAFT,
            copied_from_context_version_id=source.id,
            submitted_at=None,
            approved_at=None,
            reviewer_note=None,
        )
        self._repository.add_context(copy)
        try:
            self._repository.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise DomainError("version_conflict", "context.version_conflict", "conflict") from error
        except SQLAlchemyError:
            self._session.rollback()
            raise
        try:
            lesson_ids = self._copy_chapters(source, copy)
            concept_ids = self._copy_lesson_children(source, lesson_ids)
            self._copy_relationships_and_questions(source, lesson_ids, concept_ids)
            event_note = (
                f"copied_from:{source.id}" if note is None else f"copied_from:{source.id}; {note}"
            )
            self._repository.add_review_event(
                ContextReviewEvent(
                    context_version_id=copy.id,
                    event_type=ContextReviewEventType.COPIED_TO_NEW_DRAFT,
                    actor_role=actor_role,
                    note=event_note,
                )
            )
            self._session.commit()
            return copy
        except SQLAlchemyError:
            self._session.rollback()
            raise

    @staticmethod
    def _validate_source_remaps(source: CourseContextVersion) -> None:
        concept_ids = {
            concept.id
            for chapter in source.chapters
            for lesson in chapter.lessons
            for concept in lesson.concepts
        }
        for chapter in source.chapters:
            for lesson in chapter.lessons:
                for relationship in lesson.concept_relationships:
                    if (
                        relationship.source_concept_id not in concept_ids
                        or relationship.target_concept_id not in concept_ids
                    ):
                        raise DomainError(
                            "context_incomplete",
                            "context.invalid_concept_reference",
                            "validation",
                            {"relationship_id": relationship.id},
                        )
                for question in lesson.questions:
                    if (
                        question.related_concept_id is not None
                        and question.related_concept_id not in concept_ids
                    ):
                        raise DomainError(
                            "context_incomplete",
                            "context.invalid_question_reference",
                            "validation",
                            {"question_id": question.id},
                        )

    def _copy_chapters(
        self, source: CourseContextVersion, copy: CourseContextVersion
    ) -> dict[str, str]:
        lesson_ids: dict[str, str] = {}
        for chapter in source.chapters:
            new_chapter = Chapter(
                context_version_id=copy.id, title=chapter.title, sequence=chapter.sequence
            )
            self._session.add(new_chapter)
            self._session.flush()
            for lesson in chapter.lessons:
                new_lesson = Lesson(
                    chapter_id=new_chapter.id,
                    title=lesson.title,
                    sequence=lesson.sequence,
                    primary_language=lesson.primary_language,
                    description=lesson.description,
                )
                self._session.add(new_lesson)
                self._session.flush()
                lesson_ids[lesson.id] = new_lesson.id
        return lesson_ids

    def _copy_lesson_children(
        self, source: CourseContextVersion, lesson_ids: dict[str, str]
    ) -> dict[str, str]:
        concept_ids: dict[str, str] = {}
        for chapter in source.chapters:
            for lesson in chapter.lessons:
                new_lesson_id = lesson_ids[lesson.id]
                for objective in lesson.objectives:
                    self._session.add(
                        LearningObjective(
                            lesson_id=new_lesson_id,
                            objective_text=objective.objective_text,
                            malayalam_text=objective.malayalam_text,
                            sequence=objective.sequence,
                        )
                    )
                for material in lesson.approved_materials:
                    self._session.add(
                        ApprovedMaterial(
                            lesson_id=new_lesson_id,
                            title=material.title,
                            material_type=material.material_type,
                            source_label=material.source_label,
                            content=material.content,
                            reference=material.reference,
                            language=material.language,
                            sequence=material.sequence,
                            teacher_review_status=material.teacher_review_status,
                        )
                    )
                for glossary in lesson.glossary_terms:
                    new_glossary = GlossaryTerm(
                        lesson_id=new_lesson_id,
                        canonical_term=glossary.canonical_term,
                        malayalam_support_label=glossary.malayalam_support_label,
                        definition=glossary.definition,
                        malayalam_explanation=glossary.malayalam_explanation,
                        sequence=glossary.sequence,
                    )
                    self._session.add(new_glossary)
                    self._session.flush()
                    for alias in glossary.aliases:
                        self._session.add(
                            TermAlias(
                                glossary_term_id=new_glossary.id,
                                alias=alias.alias,
                                normalized_alias=alias.normalized_alias,
                            )
                        )
                    for misrecognition in glossary.misrecognitions:
                        self._session.add(
                            ASRMisrecognition(
                                glossary_term_id=new_glossary.id,
                                detected_text=misrecognition.detected_text,
                                normalized_text=misrecognition.normalized_text,
                                source_note=misrecognition.source_note,
                            )
                        )
                for concept in lesson.concepts:
                    new_concept = Concept(
                        lesson_id=new_lesson_id,
                        concept_key=concept.concept_key,
                        title=concept.title,
                        malayalam_title=concept.malayalam_title,
                        definition=concept.definition,
                        malayalam_definition=concept.malayalam_definition,
                        sequence=concept.sequence,
                    )
                    self._session.add(new_concept)
                    self._session.flush()
                    concept_ids[concept.id] = new_concept.id
        return concept_ids

    def _copy_relationships_and_questions(
        self,
        source: CourseContextVersion,
        lesson_ids: dict[str, str],
        concept_ids: dict[str, str],
    ) -> None:
        for chapter in source.chapters:
            for lesson in chapter.lessons:
                for relationship in lesson.concept_relationships:
                    self._session.add(
                        ConceptRelationship(
                            lesson_id=lesson_ids[lesson.id],
                            source_concept_id=concept_ids[relationship.source_concept_id],
                            target_concept_id=concept_ids[relationship.target_concept_id],
                            relationship_type=relationship.relationship_type,
                            teacher_note=relationship.teacher_note,
                            sequence=relationship.sequence,
                        )
                    )
                for question in lesson.questions:
                    self._session.add(
                        QuestionItem(
                            lesson_id=lesson_ids[lesson.id],
                            related_concept_id=(
                                concept_ids[question.related_concept_id]
                                if question.related_concept_id is not None
                                else None
                            ),
                            source_type=question.source_type,
                            source_label=question.source_label,
                            question_text=question.question_text,
                            malayalam_question_text=question.malayalam_question_text,
                            sequence=question.sequence,
                            year=question.year,
                            marks=question.marks,
                            teacher_review_status=question.teacher_review_status,
                        )
                    )
