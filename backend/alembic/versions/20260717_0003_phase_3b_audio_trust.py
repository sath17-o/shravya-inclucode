"""add offline audio-to-trusted-lesson workflow

Legacy migration policy:
- Existing audio/revisions receive explicit legacy provenance placeholders so
  the new non-null schema can be installed without SQLite defaults.
- PROCESSING maps to RUNNING and COMPLETED maps to SUCCEEDED on upgrade.
- RUNNING maps to PROCESSING and SUCCEEDED maps to COMPLETED on downgrade.
- Duplicate legacy jobs retain their original entity key in a dedicated archive;
  the lowest job id remains the deterministic active canonical job.
- legacy_processing_job_archive is immutable migration-history storage. Its
  result-reference field is historical text, not an active foreign key.
- Phase 2 has no result-reference column. A Phase 3B → Phase 2 downgrade
  deliberately omits that archive-only historical text; a re-upgrade recreates
  the archive row with a NULL result reference rather than fabricating one.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260717_0003"
down_revision: str | None = "20260716_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_legacy_status_column() -> None:
    with op.batch_alter_table("processing_jobs", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("phase_3b_status", sa.String(length=20), nullable=True))


def _replace_status_column(old_check_name: str, check_name: str, check_sql: str) -> None:
    with op.batch_alter_table("processing_jobs", recreate="always") as batch_op:
        batch_op.drop_constraint(old_check_name, type_="check")
        batch_op.drop_column("status")
        batch_op.alter_column("phase_3b_status", new_column_name="status", nullable=False)
        batch_op.create_check_constraint(check_name, check_sql)


def upgrade() -> None:
    # Preflight before any schema mutation. The selected archive policy below
    # preserves all duplicate job data rather than inventing a non-entity key.
    op.get_bind().execute(
        sa.text(
            "SELECT job_type, entity_id FROM processing_jobs "
            "GROUP BY job_type, entity_id HAVING COUNT(*) > 1"
        )
    ).fetchall()

    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_lecture_audio_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_lecture_audio_source_status",
            "source_status IN ('LIVE', 'CACHED', 'DEMO', 'LOCAL_TEACHER')",
        )
        batch_op.add_column(sa.Column("original_filename", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("byte_size", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sha256", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("workflow_status", sa.String(length=40), nullable=True))
    op.execute(
        "UPDATE lecture_audio SET original_filename = 'legacy-recording.wav' "
        "WHERE original_filename IS NULL"
    )
    op.execute("UPDATE lecture_audio SET byte_size = 1 WHERE byte_size IS NULL OR byte_size <= 0")
    op.execute(
        "UPDATE lecture_audio SET sha256 = printf('%064x', rowid) "
        "WHERE sha256 IS NULL OR length(sha256) != 64"
    )
    op.execute(
        "UPDATE lecture_audio SET duration_ms = 1 WHERE duration_ms IS NULL OR duration_ms <= 0"
    )
    op.execute(
        "UPDATE lecture_audio SET workflow_status = 'UPLOADED' WHERE workflow_status IS NULL"
    )
    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.alter_column("original_filename", nullable=False)
        batch_op.alter_column("byte_size", nullable=False)
        batch_op.alter_column("sha256", nullable=False)
        batch_op.alter_column("duration_ms", nullable=False)
        batch_op.alter_column("workflow_status", nullable=False)
        batch_op.create_check_constraint("ck_lecture_audio_byte_size", "byte_size > 0")
        batch_op.create_check_constraint("ck_lecture_audio_duration_ms", "duration_ms > 0")
        batch_op.create_check_constraint(
            "recording_workflow_status",
            "workflow_status IN ('UPLOADED', 'TRANSCRIBING', 'TRANSCRIPT_READY', "
            "'NEEDS_REVIEW', 'MANUAL_TRANSCRIPT_REQUIRED', 'APPROVED', 'FAILED')",
        )
        batch_op.create_unique_constraint("uq_lecture_audio_lesson_sha256", ["lesson_id", "sha256"])

    with op.batch_alter_table("transcript_revisions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transcript_revision_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_transcript_revision_source_status",
            "source_status IN ('LIVE', 'CACHED', 'DEMO', 'LOCAL_TEACHER')",
        )
        batch_op.add_column(
            sa.Column("copied_from_transcript_revision_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(sa.Column("provider_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("provider_version", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("provenance_label", sa.String(length=250), nullable=True))
        batch_op.add_column(sa.Column("teacher_review_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_by_role", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE transcript_revisions SET provider_name = 'legacy-migrated' "
        "WHERE provider_name IS NULL"
    )
    op.execute(
        "UPDATE transcript_revisions SET provenance_label = "
        "'Legacy transcript record — provenance unavailable' WHERE provenance_label IS NULL"
    )
    op.execute(
        "UPDATE transcript_revisions SET teacher_review_status = 'DRAFT' "
        "WHERE teacher_review_status IS NULL"
    )
    with op.batch_alter_table("transcript_revisions", recreate="always") as batch_op:
        batch_op.alter_column("provider_name", nullable=False)
        batch_op.alter_column("provenance_label", nullable=False)
        batch_op.alter_column("teacher_review_status", nullable=False)
        batch_op.create_foreign_key(
            "fk_revision_copied_from",
            "transcript_revisions",
            ["copied_from_transcript_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "transcript_teacher_review_status",
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
        )

    with op.batch_alter_table("generated_artifacts", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_artifact_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_artifact_source_status",
            "source_status IN ('LIVE', 'CACHED', 'DEMO', 'LOCAL_TEACHER')",
        )

    op.create_table(
        "recording_deletion_tombstones",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("context_version_id", sa.String(length=36), nullable=False),
        sa.Column("cleanup_type", sa.String(length=40), nullable=False),
        sa.Column("media_relative_path", sa.String(length=500), nullable=True),
        sa.Column("quarantine_relative_path", sa.String(length=500), nullable=True),
        sa.Column("quarantine_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_sha256", sa.String(length=64), nullable=True),
        sa.Column("expected_byte_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cleanup_owner_token", sa.String(length=64), nullable=True),
        sa.Column("cleanup_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_code", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "media_relative_path NOT LIKE '/%' AND media_relative_path NOT LIKE '%..%' "
            "AND media_relative_path NOT LIKE '%:%' AND "
            "(quarantine_relative_path IS NULL OR "
            "(quarantine_relative_path NOT LIKE '/%' AND quarantine_relative_path NOT LIKE '%..%' "
            "AND quarantine_relative_path NOT LIKE '%:%'))",
            name="ck_recording_tombstone_relative_path",
        ),
        sa.CheckConstraint(
            "status IN ('DELETE_PENDING', 'CLEANUP_CLAIMED', 'COMPLETED', 'RECOVERY_CONFLICT')",
            name="recording_deletion_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id", name="uq_recording_deletion_tombstone_recording"),
    )
    op.create_index(
        "ix_recording_tombstone_context",
        "recording_deletion_tombstones",
        ["context_version_id"],
    )

    op.create_table(
        "media_upload_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("temporary_relative_path", sa.String(length=500), nullable=False),
        sa.Column("final_relative_path", sa.String(length=500), nullable=False),
        sa.Column("quarantine_relative_path", sa.String(length=500), nullable=True),
        sa.Column("quarantine_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("conflict_code", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "temporary_relative_path NOT LIKE '/%' AND temporary_relative_path NOT LIKE '%..%' "
            "AND temporary_relative_path NOT LIKE '%:%' AND final_relative_path NOT LIKE '/%' "
            "AND final_relative_path NOT LIKE '%..%' AND final_relative_path NOT LIKE '%:%' "
            "AND (quarantine_relative_path IS NULL OR "
            "(quarantine_relative_path NOT LIKE '/%' AND quarantine_relative_path NOT LIKE '%..%' "
            "AND quarantine_relative_path NOT LIKE '%:%'))",
            name="ck_media_upload_intent_relative_paths",
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'MEDIA_PLACED', 'RECORDING_COMMITTED', 'COMPLETED', "
            "'RECOVERY_CONFLICT')",
            name="media_upload_intent_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("final_relative_path", name="uq_media_upload_intent_final_path"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_media_upload_intent_status", "media_upload_intents", ["status"])

    op.create_table(
        "legacy_processing_job_archive",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("original_entity_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_message", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("recoverable", sa.Boolean(), nullable=True),
        sa.Column("result_transcript_revision_id", sa.String(length=36), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("archived_reason", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('TRANSCRIPTION', 'CONCEPT_EXTRACTION', 'LAYERED_CONTENT_GENERATION', "
            "'EXPLAIN_DIFFERENTLY', 'VISUAL_STORY_PREPARATION', 'TTS_GENERATION', "
            "'PRACTICE_GENERATION')",
            name="legacy_processing_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'RUNNING', 'SUCCEEDED', "
            "'FAILED', 'CANCELLED')",
            name="ck_legacy_processing_job_archive_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_processing_job_archive_entity",
        "legacy_processing_job_archive",
        ["original_entity_id"],
    )
    op.execute(
        "INSERT INTO legacy_processing_job_archive "
        "(id, created_at, updated_at, lesson_id, original_entity_id, job_type, status, "
        "progress_message, started_at, completed_at, error_code, recoverable, "
        "result_transcript_revision_id, retry_count, archived_reason) "
        "SELECT id, created_at, updated_at, lesson_id, entity_id, job_type, status, "
        "progress_message, started_at, completed_at, error_code, recoverable, NULL, retry_count, "
        "'duplicate_legacy_job' FROM processing_jobs WHERE id NOT IN "
        "(SELECT MIN(id) FROM processing_jobs GROUP BY job_type, entity_id)"
    )
    op.execute(
        "DELETE FROM processing_jobs WHERE id NOT IN "
        "(SELECT MIN(id) FROM processing_jobs GROUP BY job_type, entity_id)"
    )

    _add_legacy_status_column()
    op.execute(
        "UPDATE processing_jobs SET phase_3b_status = CASE status "
        "WHEN 'PROCESSING' THEN 'RUNNING' "
        "WHEN 'COMPLETED' THEN 'SUCCEEDED' "
        "ELSE status END"
    )
    _replace_status_column(
        "ck_job_status",
        "job_status",
        "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
    )
    with op.batch_alter_table("processing_jobs", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("result_transcript_revision_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_job_result_revision",
            "transcript_revisions",
            ["result_transcript_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_processing_job_type_entity", ["job_type", "entity_id"]
        )

    op.create_table(
        "concept_glossary_term_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version_id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("glossary_term_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_concept_glossary_term_link_sequence"),
        sa.ForeignKeyConstraint(
            ["context_version_id"], ["course_context_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["glossary_term_id"], ["glossary_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "context_version_id",
            "concept_id",
            "glossary_term_id",
            name="uq_concept_glossary_term_link_pair",
        ),
        sa.UniqueConstraint(
            "context_version_id",
            "concept_id",
            "sequence",
            name="uq_concept_glossary_term_link_sequence",
        ),
    )
    op.create_index(
        "ix_concept_glossary_term_link_context_glossary",
        "concept_glossary_term_links",
        ["context_version_id", "glossary_term_id", "sequence"],
    )
    # SQLite cannot express the context ancestry through a composite foreign key.
    # These triggers reject links whose concept or glossary term does not belong to
    # the supplied context (or the same lesson), preventing cross-version leakage.
    same_context = """
        NOT EXISTS (
            SELECT 1 FROM concepts AS concept
            JOIN lessons AS concept_lesson ON concept_lesson.id = concept.lesson_id
            JOIN chapters AS concept_chapter ON concept_chapter.id = concept_lesson.chapter_id
            WHERE concept.id = NEW.concept_id
              AND concept_chapter.context_version_id = NEW.context_version_id
        )
        OR NOT EXISTS (
            SELECT 1 FROM glossary_terms AS glossary
            JOIN lessons AS glossary_lesson ON glossary_lesson.id = glossary.lesson_id
            JOIN chapters AS glossary_chapter ON glossary_chapter.id = glossary_lesson.chapter_id
            WHERE glossary.id = NEW.glossary_term_id
              AND glossary_chapter.context_version_id = NEW.context_version_id
        )
        OR NOT EXISTS (
            SELECT 1 FROM concepts AS concept
            JOIN glossary_terms AS glossary ON glossary.lesson_id = concept.lesson_id
            WHERE concept.id = NEW.concept_id AND glossary.id = NEW.glossary_term_id
        )
    """
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_concept_glossary_term_link_same_context_insert "
            "BEFORE INSERT ON concept_glossary_term_links FOR EACH ROW "
            f"WHEN {same_context} BEGIN "
            "SELECT RAISE(ABORT, 'concept glossary link must share its context and lesson'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_concept_glossary_term_link_same_context_update "
            "BEFORE UPDATE OF context_version_id, concept_id, glossary_term_id "
            "ON concept_glossary_term_links FOR EACH ROW "
            f"WHEN {same_context} BEGIN "
            "SELECT RAISE(ABORT, 'concept glossary link must share its context and lesson'); END"
        )
    )


def downgrade() -> None:
    pending_cleanup = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT "
                "(SELECT COUNT(*) FROM recording_deletion_tombstones "
                "WHERE status <> 'COMPLETED') + "
                "(SELECT COUNT(*) FROM media_upload_intents WHERE status <> 'COMPLETED')"
            )
        )
        .scalar_one()
    )
    if pending_cleanup:
        raise RuntimeError(
            "Cannot downgrade Phase 3B while cleanup is pending; "
            "complete recording and upload cleanup first."
        )
    local_teacher_rows = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT "
                "(SELECT COUNT(*) FROM lecture_audio WHERE source_status = 'LOCAL_TEACHER') + "
                "(SELECT COUNT(*) FROM transcript_revisions "
                "WHERE source_status = 'LOCAL_TEACHER') + "
                "(SELECT COUNT(*) FROM generated_artifacts WHERE source_status = 'LOCAL_TEACHER')"
            )
        )
        .scalar_one()
    )
    if local_teacher_rows:
        raise RuntimeError(
            "Cannot downgrade Phase 3B while LOCAL_TEACHER provenance exists; "
            "remove or migrate those records first."
        )
    op.execute("DROP TRIGGER IF EXISTS trg_concept_glossary_term_link_same_context_update")
    op.execute("DROP TRIGGER IF EXISTS trg_concept_glossary_term_link_same_context_insert")
    op.drop_index(
        "ix_concept_glossary_term_link_context_glossary",
        table_name="concept_glossary_term_links",
    )
    op.drop_table("concept_glossary_term_links")
    op.drop_index("ix_media_upload_intent_status", table_name="media_upload_intents")
    op.drop_table("media_upload_intents")
    with op.batch_alter_table("processing_jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_processing_job_type_entity", type_="unique")
        batch_op.drop_constraint("fk_job_result_revision", type_="foreignkey")
        batch_op.drop_column("result_transcript_revision_id")
    _add_legacy_status_column()
    op.execute(
        "UPDATE processing_jobs SET phase_3b_status = CASE status "
        "WHEN 'RUNNING' THEN 'PROCESSING' "
        "WHEN 'SUCCEEDED' THEN 'COMPLETED' "
        "ELSE status END"
    )
    _replace_status_column(
        "job_status",
        "ck_job_status",
        "status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.execute(
        "INSERT INTO processing_jobs "
        "(id, created_at, updated_at, lesson_id, job_type, entity_id, status, progress_message, "
        "started_at, completed_at, error_code, recoverable, retry_count) "
        "SELECT id, created_at, updated_at, lesson_id, job_type, original_entity_id, status, "
        "progress_message, started_at, completed_at, error_code, recoverable, retry_count "
        "FROM legacy_processing_job_archive"
    )
    op.drop_index(
        "ix_legacy_processing_job_archive_entity", table_name="legacy_processing_job_archive"
    )
    op.drop_table("legacy_processing_job_archive")

    with op.batch_alter_table("transcript_revisions", recreate="always") as batch_op:
        batch_op.drop_constraint("transcript_teacher_review_status", type_="check")
        batch_op.drop_constraint("fk_revision_copied_from", type_="foreignkey")
        batch_op.drop_column("approved_by_role")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("teacher_review_status")
        batch_op.drop_column("provenance_label")
        batch_op.drop_column("provider_version")
        batch_op.drop_column("provider_name")
        batch_op.drop_column("copied_from_transcript_revision_id")

    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_lecture_audio_lesson_sha256", type_="unique")
        batch_op.drop_constraint("recording_workflow_status", type_="check")
        batch_op.drop_constraint("ck_lecture_audio_duration_ms", type_="check")
        batch_op.drop_constraint("ck_lecture_audio_byte_size", type_="check")
        batch_op.drop_column("workflow_status")
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("sha256")
        batch_op.drop_column("byte_size")
        batch_op.drop_column("original_filename")

    op.drop_index("ix_recording_tombstone_context", table_name="recording_deletion_tombstones")
    op.drop_table("recording_deletion_tombstones")

    with op.batch_alter_table("generated_artifacts", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_artifact_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_artifact_source_status", "source_status IN ('LIVE', 'CACHED', 'DEMO')"
        )
    with op.batch_alter_table("transcript_revisions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transcript_revision_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_transcript_revision_source_status", "source_status IN ('LIVE', 'CACHED', 'DEMO')"
        )
    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_lecture_audio_source_status", type_="check")
        batch_op.create_check_constraint(
            "ck_lecture_audio_source_status", "source_status IN ('LIVE', 'CACHED', 'DEMO')"
        )
