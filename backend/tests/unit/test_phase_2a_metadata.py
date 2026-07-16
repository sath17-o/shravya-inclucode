from app.db.base import Base
from app.models.foundation import (
    ApprovedMaterial,
    Concept,
    ConceptRelationship,
    ContextReviewEvent,
    CourseContextVersion,
    GlossaryTerm,
    LearningObjective,
    QuestionItem,
)


def test_phase_2a_tables_are_registered() -> None:
    assert {"approved_materials", "concept_relationships", "context_review_events"} <= set(
        Base.metadata.tables
    )


def test_phase_2a_metadata_contract() -> None:
    context = CourseContextVersion.__table__
    copied_from = context.c.copied_from_context_version_id
    assert copied_from.nullable
    assert next(iter(copied_from.foreign_keys)).ondelete == "SET NULL"
    assert "ix_context_copied_from" in {index.name for index in context.indexes}
    assert "updated_at" not in ContextReviewEvent.__table__.c
    assert not Concept.__table__.c.concept_key.unique
    assert "teacher_review_status" not in LearningObjective.__table__.c
    assert "teacher_review_status" not in GlossaryTerm.__table__.c
    assert "teacher_review_status" in ApprovedMaterial.__table__.c
    assert "teacher_review_status" in QuestionItem.__table__.c


def test_phase_2a_constraints_and_indexes_are_scoped() -> None:
    objective_constraints = {
        constraint.name for constraint in LearningObjective.__table__.constraints
    }
    glossary_constraints = {constraint.name for constraint in GlossaryTerm.__table__.constraints}
    relationship_constraints = {
        constraint.name for constraint in ConceptRelationship.__table__.constraints
    }
    assert "uq_objective_lesson_sequence" in objective_constraints
    assert {"uq_glossary_lesson_term", "uq_glossary_lesson_sequence"} <= glossary_constraints
    assert {
        "ck_relationship_not_self",
        "uq_relationship_tuple",
        "uq_relationship_lesson_sequence",
    } <= relationship_constraints
    assert {
        "ix_objectives_lesson_sequence",
        "ix_glossary_lesson_sequence",
        "ix_concepts_lesson_sequence",
        "ix_questions_lesson_sequence",
    } <= {
        index.name
        for table in (
            LearningObjective.__table__,
            GlossaryTerm.__table__,
            Concept.__table__,
            QuestionItem.__table__,
        )
        for index in table.indexes
    }
