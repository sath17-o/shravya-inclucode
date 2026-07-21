"""add teacher-verified concept recovery packs"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0004"
down_revision: str | None = "20260717_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "concepts",
        sa.Column(
            "context_version_id",
            sa.String(length=36),
            nullable=False,
            server_default="",
        ),
    )

    op.execute(
        """
        UPDATE concepts
        SET context_version_id = (
            SELECT chapters.context_version_id
            FROM lessons
            JOIN chapters ON chapters.id = lessons.chapter_id
            WHERE lessons.id = concepts.lesson_id
        )
        """
    )
    op.create_index(
        "uq_concepts_context_id",
        "concepts",
        ["context_version_id", "id"],
        unique=True,
    )

    op.execute(
        """
        CREATE TRIGGER trg_concepts_context_version_insert
        BEFORE INSERT ON concepts
        FOR EACH ROW
        WHEN NEW.context_version_id IS NOT (
            SELECT chapters.context_version_id
            FROM lessons
            JOIN chapters ON chapters.id = lessons.chapter_id
            WHERE lessons.id = NEW.lesson_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'concept_context_version_mismatch');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_concepts_context_version_update
        BEFORE UPDATE OF context_version_id, lesson_id ON concepts
        FOR EACH ROW
        WHEN NEW.context_version_id IS NOT (
            SELECT chapters.context_version_id
            FROM lessons
            JOIN chapters ON chapters.id = lessons.chapter_id
            WHERE lessons.id = NEW.lesson_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'concept_context_version_mismatch');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_lessons_concept_context_version_update
        BEFORE UPDATE OF chapter_id ON lessons
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM concepts
            WHERE concepts.lesson_id = OLD.id
              AND concepts.context_version_id IS NOT (
                  SELECT context_version_id FROM chapters WHERE chapters.id = NEW.chapter_id
              )
        )
        BEGIN
            SELECT RAISE(ABORT, 'concept_context_version_mismatch');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chapters_concept_context_version_update
        BEFORE UPDATE OF context_version_id ON chapters
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM concepts
            JOIN lessons ON lessons.id = concepts.lesson_id
            WHERE lessons.chapter_id = OLD.id
              AND concepts.context_version_id IS NOT NEW.context_version_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'concept_context_version_mismatch');
        END
        """
    )

    op.create_table(
        "concept_recovery_packs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version_id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("cue_en", sa.Text(), nullable=False),
        sa.Column("cue_ml", sa.Text(), nullable=False),
        sa.Column("example_en", sa.Text(), nullable=False),
        sa.Column("example_ml", sa.Text(), nullable=False),
        sa.Column("alternate_explanation_en", sa.Text(), nullable=False),
        sa.Column("alternate_explanation_ml", sa.Text(), nullable=False),
        sa.Column("teacher_review_status", sa.String(length=20), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(cue_en)) > 0", name="ck_recovery_pack_cue_en"),
        sa.CheckConstraint("length(trim(cue_ml)) > 0", name="ck_recovery_pack_cue_ml"),
        sa.CheckConstraint("length(trim(example_en)) > 0", name="ck_recovery_pack_example_en"),
        sa.CheckConstraint("length(trim(example_ml)) > 0", name="ck_recovery_pack_example_ml"),
        sa.CheckConstraint(
            "length(trim(alternate_explanation_en)) > 0", name="ck_recovery_pack_alternate_en"
        ),
        sa.CheckConstraint(
            "length(trim(alternate_explanation_ml)) > 0", name="ck_recovery_pack_alternate_ml"
        ),
        sa.CheckConstraint(
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
            name="ck_recovery_pack_teacher_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["context_version_id"],
            ["course_context_versions.id"],
            name="fk_recovery_pack_context_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["context_version_id", "concept_id"],
            ["concepts.context_version_id", "concepts.id"],
            name="fk_recovery_pack_context_concept",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "context_version_id", "concept_id", name="uq_recovery_pack_context_concept"
        ),
    )
    op.create_index(
        "ix_recovery_pack_context_status",
        "concept_recovery_packs",
        ["context_version_id", "teacher_review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_recovery_pack_context_status", table_name="concept_recovery_packs")
    op.drop_table("concept_recovery_packs")
    op.execute("DROP TRIGGER IF EXISTS trg_chapters_concept_context_version_update")
    op.execute("DROP TRIGGER IF EXISTS trg_lessons_concept_context_version_update")
    op.execute("DROP TRIGGER IF EXISTS trg_concepts_context_version_update")
    op.execute("DROP TRIGGER IF EXISTS trg_concepts_context_version_insert")
    op.drop_index("uq_concepts_context_id", table_name="concepts")
    op.drop_column("concepts", "context_version_id")
