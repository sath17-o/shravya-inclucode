"""add Phase 2A curriculum preparation schema

Revision ID: 20260716_0002
Revises: 20260715_0001
Create Date: 2026-07-16

Phase 2A targets clean development databases. Curriculum-child tables are
expected to be empty when their required Phase 2A fields are introduced.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0002"
down_revision: str | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("course_context_versions", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("reviewer_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("copied_from_context_version_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_context_copied_from",
            "course_context_versions",
            ["copied_from_context_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_context_copied_from",
        "course_context_versions",
        ["copied_from_context_version_id"],
    )

    with op.batch_alter_table("lessons", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))

    with op.batch_alter_table("learning_objectives", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("malayalam_text", sa.Text(), nullable=True))
    op.create_index(
        "ix_objectives_lesson_sequence", "learning_objectives", ["lesson_id", "sequence"]
    )

    with op.batch_alter_table("glossary_terms", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("malayalam_explanation", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=False))
        batch_op.alter_column("definition", existing_type=sa.Text(), nullable=False)
        batch_op.create_unique_constraint("uq_glossary_lesson_sequence", ["lesson_id", "sequence"])
        batch_op.create_check_constraint("ck_glossary_terms_sequence", "sequence >= 1")
    op.create_index("ix_glossary_lesson_sequence", "glossary_terms", ["lesson_id", "sequence"])

    with op.batch_alter_table("term_aliases", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("normalized_alias", sa.String(length=200), nullable=False))
        batch_op.drop_constraint("uq_term_alias", type_="unique")
        batch_op.create_unique_constraint("uq_term_alias", ["glossary_term_id", "normalized_alias"])
    op.create_index("ix_aliases_glossary", "term_aliases", ["glossary_term_id"])

    with op.batch_alter_table("asr_misrecognitions", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("normalized_text", sa.String(length=200), nullable=False))
        batch_op.add_column(sa.Column("source_note", sa.Text(), nullable=True))
        batch_op.drop_constraint("uq_asr_misrecognition", type_="unique")
        batch_op.create_unique_constraint(
            "uq_asr_misrecognition", ["glossary_term_id", "normalized_text"]
        )
    op.create_index("ix_misrecognitions_glossary", "asr_misrecognitions", ["glossary_term_id"])

    with op.batch_alter_table("concepts", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("concept_key", sa.String(length=100), nullable=False))
        batch_op.add_column(sa.Column("malayalam_title", sa.String(length=250), nullable=True))
        batch_op.add_column(sa.Column("definition", sa.Text(), nullable=False))
        batch_op.add_column(sa.Column("malayalam_definition", sa.Text(), nullable=True))
        batch_op.create_unique_constraint("uq_concept_lesson_key", ["lesson_id", "concept_key"])
    op.create_index("ix_concepts_lesson_sequence", "concepts", ["lesson_id", "sequence"])

    with op.batch_alter_table("question_items", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("malayalam_question_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=False))
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=100),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "question_source_type",
            "source_type IN ('teacher_question', 'textbook_exercise', 'past_school_exam', "
            "'board_style_question', 'ai_generated_practice')",
        )
        batch_op.create_check_constraint("ck_question_items_sequence", "sequence >= 1")
        batch_op.create_unique_constraint("uq_question_lesson_sequence", ["lesson_id", "sequence"])
    op.create_index("ix_questions_lesson_sequence", "question_items", ["lesson_id", "sequence"])

    op.create_table(
        "approved_materials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("material_type", sa.String(length=20), nullable=False),
        sa.Column("source_label", sa.String(length=250), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("teacher_review_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_materials_sequence"),
        sa.CheckConstraint(
            "material_type IN ('teacher_note', 'textbook_excerpt', 'worksheet', "
            "'reference_text', 'other')",
            name="material_type",
        ),
        sa.CheckConstraint("language IN ('en', 'ml', 'bilingual')", name="material_language"),
        sa.CheckConstraint(
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
            name="material_teacher_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_material_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "sequence", name="uq_material_lesson_sequence"),
    )
    op.create_index("ix_materials_lesson_sequence", "approved_materials", ["lesson_id", "sequence"])

    op.create_table(
        "concept_relationships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("source_concept_id", sa.String(length=36), nullable=False),
        sa.Column("target_concept_id", sa.String(length=36), nullable=False),
        sa.Column("relationship_type", sa.String(length=20), nullable=False),
        sa.Column("teacher_note", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "source_concept_id != target_concept_id", name="ck_relationship_not_self"
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_relationship_sequence"),
        sa.CheckConstraint(
            "relationship_type IN ('prerequisite_of', 'input_to', 'enables', 'produces', "
            "'precedes', 'related_to')",
            name="concept_relationship_type",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_relationship_lesson", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_concept_id"],
            ["concepts.id"],
            name="fk_relationship_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_concept_id"],
            ["concepts.id"],
            name="fk_relationship_target",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_concept_id",
            "target_concept_id",
            "relationship_type",
            name="uq_relationship_tuple",
        ),
        sa.UniqueConstraint("lesson_id", "sequence", name="uq_relationship_lesson_sequence"),
    )
    op.create_index("ix_concept_relationships_lesson", "concept_relationships", ["lesson_id"])
    op.create_index(
        "ix_concept_relationships_source", "concept_relationships", ["source_concept_id"]
    )
    op.create_index(
        "ix_concept_relationships_target", "concept_relationships", ["target_concept_id"]
    )

    op.create_table(
        "context_review_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("actor_role", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('draft_created', 'submitted_for_review', 'returned_to_draft', "
            "'approved', 'copied_to_new_draft')",
            name="context_review_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["context_version_id"],
            ["course_context_versions.id"],
            name="fk_review_event_context",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_events_context_created",
        "context_review_events",
        ["context_version_id", "created_at"],
    )
    op.create_index("ix_artifacts_context", "generated_artifacts", ["course_context_version_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_context", table_name="generated_artifacts")
    op.drop_index("ix_review_events_context_created", table_name="context_review_events")
    op.drop_table("context_review_events")

    op.drop_index("ix_concept_relationships_target", table_name="concept_relationships")
    op.drop_index("ix_concept_relationships_source", table_name="concept_relationships")
    op.drop_index("ix_concept_relationships_lesson", table_name="concept_relationships")
    op.drop_table("concept_relationships")

    op.drop_index("ix_materials_lesson_sequence", table_name="approved_materials")
    op.drop_table("approved_materials")

    op.drop_index("ix_questions_lesson_sequence", table_name="question_items")
    with op.batch_alter_table("question_items", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_question_lesson_sequence", type_="unique")
        batch_op.drop_constraint("ck_question_items_sequence", type_="check")
        batch_op.drop_constraint("question_source_type", type_="check")
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=30),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
        batch_op.drop_column("sequence")
        batch_op.drop_column("malayalam_question_text")

    op.drop_index("ix_concepts_lesson_sequence", table_name="concepts")
    with op.batch_alter_table("concepts", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_concept_lesson_key", type_="unique")
        batch_op.drop_column("malayalam_definition")
        batch_op.drop_column("definition")
        batch_op.drop_column("malayalam_title")
        batch_op.drop_column("concept_key")

    op.drop_index("ix_misrecognitions_glossary", table_name="asr_misrecognitions")
    with op.batch_alter_table("asr_misrecognitions", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_asr_misrecognition", type_="unique")
        batch_op.create_unique_constraint(
            "uq_asr_misrecognition", ["glossary_term_id", "detected_text"]
        )
        batch_op.drop_column("source_note")
        batch_op.drop_column("normalized_text")

    op.drop_index("ix_aliases_glossary", table_name="term_aliases")
    with op.batch_alter_table("term_aliases", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_term_alias", type_="unique")
        batch_op.create_unique_constraint("uq_term_alias", ["glossary_term_id", "alias"])
        batch_op.drop_column("normalized_alias")

    op.drop_index("ix_glossary_lesson_sequence", table_name="glossary_terms")
    with op.batch_alter_table("glossary_terms", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_glossary_terms_sequence", type_="check")
        batch_op.drop_constraint("uq_glossary_lesson_sequence", type_="unique")
        batch_op.alter_column("definition", existing_type=sa.Text(), nullable=True)
        batch_op.drop_column("sequence")
        batch_op.drop_column("malayalam_explanation")

    op.drop_index("ix_objectives_lesson_sequence", table_name="learning_objectives")
    with op.batch_alter_table("learning_objectives", recreate="always") as batch_op:
        batch_op.drop_column("malayalam_text")

    with op.batch_alter_table("lessons", recreate="always") as batch_op:
        batch_op.drop_column("description")

    op.drop_index("ix_context_copied_from", table_name="course_context_versions")
    with op.batch_alter_table("course_context_versions", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_context_copied_from", type_="foreignkey")
        batch_op.drop_column("copied_from_context_version_id")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("reviewer_note")
