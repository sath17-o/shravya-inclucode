from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.contracts.enums import (
    ArtifactStatus,
    ConceptRelationshipType,
    ContentLanguage,
    ContextReviewEventType,
    MaterialType,
    QualityStatus,
    QuestionSourceType,
    SourceStatus,
    TeacherReviewStatus,
    UncertaintyStatus,
)
from app.models.foundation import (
    ApprovedMaterial,
    ASRMisrecognition,
    Chapter,
    Concept,
    ConceptRelationship,
    ContextReviewEvent,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
    TermAlias,
)

T = TypeVar("T")


def _build(model: type[T], defaults: dict[str, Any], overrides: dict[str, Any]) -> T:
    return model(**(defaults | overrides))


def course(**overrides: Any) -> Course:
    return _build(
        Course,
        {
            "title": "Class 7 Science demonstration lesson",
            "subject": "Science",
            "class_level": 7,
            "grade_band": "5-7",
        },
        overrides,
    )


def context_version(**overrides: Any) -> CourseContextVersion:
    return _build(
        CourseContextVersion,
        {"version_number": 1, "teacher_review_status": TeacherReviewStatus.DRAFT},
        overrides,
    )


def chapter(**overrides: Any) -> Chapter:
    return _build(Chapter, {"title": "Photosynthesis in Plants", "sequence": 1}, overrides)


def lesson(**overrides: Any) -> Lesson:
    return _build(
        Lesson,
        {"title": "Plants make food", "sequence": 1, "primary_language": "ml"},
        overrides,
    )


def learning_objective(**overrides: Any) -> LearningObjective:
    return _build(
        LearningObjective,
        {
            "objective_text": "Explain how plants make food.",
            "malayalam_text": "സസ്യങ്ങൾ എങ്ങനെ ആഹാരം നിർമ്മിക്കുന്നു എന്ന് വിശദീകരിക്കുക.",
            "sequence": 1,
        },
        overrides,
    )


def approved_material(**overrides: Any) -> ApprovedMaterial:
    return _build(
        ApprovedMaterial,
        {
            "title": "Teacher-approved source",
            "material_type": MaterialType.TEACHER_NOTE,
            "source_label": "Teacher",
            "content": "Plants make glucose using light, water, and carbon dioxide.",
            "language": ContentLanguage.BILINGUAL,
            "sequence": 1,
            "teacher_review_status": TeacherReviewStatus.APPROVED,
        },
        overrides,
    )


def glossary_term(**overrides: Any) -> GlossaryTerm:
    return _build(
        GlossaryTerm,
        {
            "canonical_term": "Photosynthesis",
            "malayalam_support_label": "പ്രകാശസംശ്ലേഷണം",
            "definition": "The process by which plants make glucose.",
            "malayalam_explanation": "സസ്യങ്ങൾ പ്രകാശം ഉപയോഗിച്ച് ഗ്ലൂക്കോസ് നിർമ്മിക്കുന്ന പ്രക്രിയ.",
            "sequence": 1,
        },
        overrides,
    )


def term_alias(**overrides: Any) -> TermAlias:
    return _build(
        TermAlias,
        {"alias": "plant food process", "normalized_alias": "plant food process"},
        overrides,
    )


def asr_misrecognition(**overrides: Any) -> ASRMisrecognition:
    return _build(
        ASRMisrecognition,
        {
            "detected_text": "chlorophil",
            "normalized_text": "chlorophil",
            "source_note": "Common ASR variant.",
        },
        overrides,
    )


def concept(**overrides: Any) -> Concept:
    return _build(
        Concept,
        {
            "concept_key": "plant-inputs",
            "title": "What plants need",
            "malayalam_title": "സസ്യങ്ങൾക്ക് വേണ്ടത്",
            "definition": "Plants need water, carbon dioxide, sunlight, and chlorophyll.",
            "malayalam_definition": "സസ്യങ്ങൾക്ക് ജലം, കാർബൺ ഡൈ ഓക്സൈഡ്, സൂര്യപ്രകാശം, ക്ലോറോഫിൽ എന്നിവ ആവശ്യമാണ്.",
            "sequence": 1,
        },
        overrides,
    )


def concept_relationship(**overrides: Any) -> ConceptRelationship:
    return _build(
        ConceptRelationship,
        {"relationship_type": ConceptRelationshipType.PREREQUISITE_OF, "sequence": 1},
        overrides,
    )


def question_item(**overrides: Any) -> QuestionItem:
    return _build(
        QuestionItem,
        {
            "source_type": QuestionSourceType.TEACHER_QUESTION,
            "source_label": "Teacher",
            "question_text": "What do plants need for photosynthesis?",
            "malayalam_question_text": "പ്രകാശസംശ്ലേഷണത്തിന് സസ്യങ്ങൾക്ക് എന്താണ് വേണ്ടത്?",
            "sequence": 1,
            "teacher_review_status": TeacherReviewStatus.APPROVED,
        },
        overrides,
    )


def review_event(**overrides: Any) -> ContextReviewEvent:
    return _build(
        ContextReviewEvent,
        {"event_type": ContextReviewEventType.DRAFT_CREATED, "actor_role": "teacher", "note": None},
        overrides,
    )


def generated_artifact(**overrides: Any) -> GeneratedArtifact:
    return _build(
        GeneratedArtifact,
        {
            "artifact_type": "layered_notes",
            "provider_name": "offline-test",
            "source_status": SourceStatus.DEMO,
            "quality_status": QualityStatus.VERIFIED,
            "uncertainty_status": UncertaintyStatus.CONFIRMED,
            "teacher_review_status": TeacherReviewStatus.APPROVED,
            "generation_status": ArtifactStatus.READY,
        },
        overrides,
    )


@dataclass(frozen=True)
class CompleteContext:
    course: Course
    context: CourseContextVersion
    chapter: Chapter
    lesson: Lesson
    glossary_terms: list[GlossaryTerm]
    concepts: list[Concept]


def complete_photosynthesis_context(
    session: Session,
    *,
    course_model: Course | None = None,
    version_number: int = 1,
    status: TeacherReviewStatus = TeacherReviewStatus.DRAFT,
) -> CompleteContext:
    """Build the locked-policy context without committing; callers own setup commits."""

    course_model = course_model or course()
    context = context_version(
        course=course_model,
        version_number=version_number,
        teacher_review_status=status,
    )
    chapter_model = chapter(context_version=context)
    lesson_model = lesson(chapter=chapter_model)
    session.add_all([course_model, context, chapter_model, lesson_model])
    session.flush()
    session.add_all(
        [learning_objective(lesson=lesson_model), approved_material(lesson=lesson_model)]
    )
    labels = {"photosynthesis": "പ്രകാശസംശ്ലേഷണം", "chlorophyll": "ക്ലോറോഫിൽ"}
    terms = (
        "Photosynthesis",
        "Chlorophyll",
        "Chloroplast",
        "Stomata",
        "Carbon dioxide",
        "Water",
        "Sunlight",
        "Glucose",
        "Oxygen",
        "Leaf",
    )
    glossary_terms = [
        glossary_term(
            lesson=lesson_model,
            canonical_term=term,
            malayalam_support_label=labels.get(term.casefold()),
            sequence=index,
        )
        for index, term in enumerate(terms, 1)
    ]
    session.add_all(glossary_terms)
    concepts = [
        concept(lesson=lesson_model, concept_key=key, title=title, sequence=index)
        for index, (key, title) in enumerate(
            (
                ("plant-inputs", "What plants need for photosynthesis"),
                ("inputs-reach-leaf", "How water and carbon dioxide reach the leaf"),
                ("sunlight-chlorophyll", "Role of sunlight and chlorophyll"),
                ("glucose-production", "Production of glucose"),
                ("oxygen-release", "Release of oxygen"),
            ),
            1,
        )
    ]
    session.add_all(concepts)
    session.flush()
    session.add_all(
        [
            term_alias(glossary_term=glossary_terms[0]),
            asr_misrecognition(glossary_term=glossary_terms[1]),
            concept_relationship(
                lesson=lesson_model,
                source_concept_id=concepts[0].id,
                target_concept_id=concepts[1].id,
            ),
            question_item(lesson=lesson_model, related_concept_id=concepts[0].id),
        ]
    )
    session.flush()
    return CompleteContext(
        course_model, context, chapter_model, lesson_model, glossary_terms, concepts
    )
