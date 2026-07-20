from __future__ import annotations

from dataclasses import dataclass

from app.contracts.enums import QualityStatus, TeacherReviewStatus
from app.contracts.teacher_review import (
    ContextCompletenessIssue,
    ContextCompletenessResult,
    DomainError,
)
from app.core.config import get_settings
from app.models.foundation import CourseContextVersion, Lesson
from app.repositories.curriculum import CurriculumRepository
from app.services.transcript_quality import evaluate_transcript_quality


@dataclass(frozen=True)
class LockedPhotosynthesisCompletenessPolicy:
    required_glossary_terms: tuple[str, ...] = (
        "photosynthesis",
        "chlorophyll",
        "chloroplast",
        "stomata",
        "carbon dioxide",
        "water",
        "sunlight",
        "glucose",
        "oxygen",
        "leaf",
    )
    required_malayalam_labels: tuple[tuple[str, str], ...] = (
        ("photosynthesis", "പ്രകാശസംശ്ലേഷണം"),
        ("chlorophyll", "ക്ലോറോഫിൽ"),
    )
    required_concept_keys: tuple[str, ...] = (
        "plant-inputs",
        "inputs-reach-leaf",
        "sunlight-chlorophyll",
        "glucose-production",
        "oxygen-release",
    )


SECTION_ORDER = (
    "chapters",
    "lessons",
    "learning_objectives",
    "approved_materials",
    "glossary",
    "concepts",
    "questions",
    "required_text",
    "relationships",
)


def normalize(value: str) -> str:
    return value.strip().casefold()


class ContextCompletenessService:
    def __init__(
        self,
        repository: CurriculumRepository,
        policy: LockedPhotosynthesisCompletenessPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or LockedPhotosynthesisCompletenessPolicy()

    def evaluate(self, context_version_id: str) -> ContextCompletenessResult:
        context = self._repository.get_context_with_graph(context_version_id)
        if context is None:
            raise DomainError("context_not_found", "context.not_found", "not_found")

        issues: list[ContextCompletenessIssue] = []
        lessons = self._lessons(context)
        if not context.chapters:
            issues.append(self._issue("missing_chapter", "chapters", None))
        if not lessons:
            issues.append(self._issue("missing_lesson", "lessons", None))
        if not any(lesson.objectives for lesson in lessons):
            issues.append(self._issue("missing_learning_objective", "learning_objectives", None))
        if not any(
            material.teacher_review_status is TeacherReviewStatus.APPROVED
            for lesson in lessons
            for material in lesson.approved_materials
        ):
            issues.append(self._issue("missing_approved_material", "approved_materials", None))

        glossary = [term for lesson in lessons for term in lesson.glossary_terms]
        glossary_by_term: dict[str, list] = {}
        for glossary_term in glossary:
            glossary_by_term.setdefault(normalize(glossary_term.canonical_term), []).append(
                glossary_term
            )
        for required_term in self._policy.required_glossary_terms:
            if required_term not in glossary_by_term:
                issues.append(
                    self._issue("missing_required_glossary_term", "glossary", required_term)
                )
        for term, required_label in self._policy.required_malayalam_labels:
            matching_terms = glossary_by_term.get(term, [])
            if not any(item.malayalam_support_label == required_label for item in matching_terms):
                issues.append(self._issue("missing_required_malayalam_label", "glossary", term))

        concepts = [concept for lesson in lessons for concept in lesson.concepts]
        concept_keys = {normalize(concept.concept_key) for concept in concepts}
        for concept_key in self._policy.required_concept_keys:
            if concept_key not in concept_keys:
                issues.append(self._issue("missing_locked_concept", "concepts", concept_key))
        if not any(
            question.teacher_review_status is TeacherReviewStatus.APPROVED
            for lesson in lessons
            for question in lesson.questions
        ):
            issues.append(self._issue("missing_approved_question", "questions", None))

        issues.extend(self._empty_text_issues(context, lessons))
        issues.extend(self._relationship_issues(lessons))
        issues.extend(self._audio_transcript_issues(lessons))
        active_sections = SECTION_ORDER + (
            ("classroom_transcript",) if any(lesson.audio_assets for lesson in lessons) else ()
        )
        issues.sort(
            key=lambda issue: (active_sections.index(issue.section), issue.code, issue.field or "")
        )
        incomplete_sections = [
            section
            for section in active_sections
            if any(issue.section == section for issue in issues)
        ]
        return ContextCompletenessResult(
            context_version_id=context.id,
            is_complete=not issues,
            issues=issues,
            completed_sections=[
                section for section in active_sections if section not in incomplete_sections
            ],
            incomplete_sections=incomplete_sections,
        )

    @staticmethod
    def _lessons(context: CourseContextVersion) -> list[Lesson]:
        return [lesson for chapter in context.chapters for lesson in chapter.lessons]

    @staticmethod
    def _issue(code: str, section: str, field: str | None) -> ContextCompletenessIssue:
        return ContextCompletenessIssue(
            code=code,
            section=section,
            field=field,
            message_key=f"completeness.{code}",
            recovery_action=f"complete_{section}",
        )

    def _empty_text_issues(
        self, context: CourseContextVersion, lessons: list[Lesson]
    ) -> list[ContextCompletenessIssue]:
        values: list[tuple[str, str | None]] = []
        for chapter in context.chapters:
            values.append(("chapter.title", chapter.title))
        for lesson in lessons:
            values.append(("lesson.title", lesson.title))
            values.extend(
                ("learning_objective.objective_text", item.objective_text)
                for item in lesson.objectives
            )
            values.extend(
                ("approved_material.title", item.title) for item in lesson.approved_materials
            )
            values.extend(
                ("approved_material.source_label", item.source_label)
                for item in lesson.approved_materials
            )
            values.extend(
                ("approved_material.content", item.content) for item in lesson.approved_materials
            )
            values.extend(
                ("glossary.canonical_term", item.canonical_term) for item in lesson.glossary_terms
            )
            values.extend(
                ("glossary.definition", item.definition) for item in lesson.glossary_terms
            )
            values.extend(("concept.concept_key", item.concept_key) for item in lesson.concepts)
            values.extend(("concept.title", item.title) for item in lesson.concepts)
            values.extend(("concept.definition", item.definition) for item in lesson.concepts)
            values.extend(("question.source_label", item.source_label) for item in lesson.questions)
            values.extend(
                ("question.question_text", item.question_text) for item in lesson.questions
            )
        return [
            self._issue("empty_required_text", "required_text", field_name)
            for field_name, value in values
            if value is None or not value.strip()
        ]

    def _relationship_issues(self, lessons: list[Lesson]) -> list[ContextCompletenessIssue]:
        concepts = {concept.id: concept for lesson in lessons for concept in lesson.concepts}
        issues: list[ContextCompletenessIssue] = []
        for lesson in lessons:
            for relationship in lesson.concept_relationships:
                source = concepts.get(relationship.source_concept_id)
                target = concepts.get(relationship.target_concept_id)
                if (
                    source is None
                    or target is None
                    or source.lesson_id != lesson.id
                    or target.lesson_id != lesson.id
                ):
                    issues.append(
                        self._issue(
                            "concept_relationship_crosses_lesson",
                            "relationships",
                            relationship.id,
                        )
                    )
        return issues

    def _audio_transcript_issues(self, lessons: list[Lesson]) -> list[ContextCompletenessIssue]:
        """Audio is opt-in for legacy contexts, but trusted once added to a draft."""
        issues: list[ContextCompletenessIssue] = []
        for lesson in lessons:
            for recording in lesson.audio_assets:
                revisions = sorted(
                    recording.transcript_revisions,
                    key=lambda item: (item.revision_number, item.id),
                )
                latest = revisions[-1] if revisions else None
                if latest is None:
                    issues.append(
                        self._issue(
                            "recording_missing_transcript", "classroom_transcript", recording.id
                        )
                    )
                    continue
                findings = evaluate_transcript_quality(
                    latest,
                    get_settings().demo_minimum_timestamp_coverage,
                    latest_revision_id=latest.id,
                )
                assessment = max(
                    latest.quality_assessments,
                    key=lambda item: (item.created_at, item.id),
                    default=None,
                )
                if (
                    findings
                    or assessment is None
                    or assessment.quality_status is not QualityStatus.VERIFIED
                ):
                    issues.append(
                        self._issue(
                            "transcript_quality_not_verified", "classroom_transcript", latest.id
                        )
                    )
                if latest.teacher_review_status is not TeacherReviewStatus.APPROVED:
                    issues.append(
                        self._issue(
                            "transcript_not_teacher_approved", "classroom_transcript", latest.id
                        )
                    )
        return issues
