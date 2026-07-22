"""add local STT evidence and truthful WAV metadata

Phase 4C stores native local-provider evidence separately from transcript text.
The evidence is owned by its revision and therefore disappears only when that
entire teacher-side revision is deleted with its recording.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260723_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("audio_format", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("sample_rate_hz", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("channel_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sample_width_bits", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("frame_count", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_lecture_audio_sample_rate_hz", "sample_rate_hz IS NULL OR sample_rate_hz > 0"
        )
        batch_op.create_check_constraint(
            "ck_lecture_audio_channel_count", "channel_count IS NULL OR channel_count > 0"
        )
        batch_op.create_check_constraint(
            "ck_lecture_audio_sample_width_bits",
            "sample_width_bits IS NULL OR sample_width_bits > 0",
        )
        batch_op.create_check_constraint(
            "ck_lecture_audio_frame_count", "frame_count IS NULL OR frame_count > 0"
        )

    op.create_table(
        "transcription_run_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_lecture_audio_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider_mode", sa.String(length=40), nullable=False),
        sa.Column("provider_implementation", sa.String(length=100), nullable=False),
        sa.Column("provider_version", sa.String(length=100), nullable=True),
        sa.Column("ctranslate2_version", sa.String(length=100), nullable=True),
        sa.Column("model_identifier", sa.String(length=500), nullable=False),
        sa.Column("device", sa.String(length=40), nullable=False),
        sa.Column("compute_type", sa.String(length=40), nullable=False),
        sa.Column("language_requested", sa.String(length=20), nullable=False),
        sa.Column("language_detected", sa.String(length=20), nullable=True),
        sa.Column("language_probability", sa.Float(), nullable=True),
        sa.Column("multilingual", sa.Boolean(), nullable=False),
        sa.Column("beam_size", sa.Integer(), nullable=False),
        sa.Column("vad_filter", sa.Boolean(), nullable=False),
        sa.Column("word_timestamps", sa.Boolean(), nullable=False),
        sa.Column("transcription_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcription_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_load_seconds", sa.Float(), nullable=True),
        sa.Column("inference_seconds", sa.Float(), nullable=False),
        sa.Column("raw_provider_output_json", sa.Text(), nullable=False),
        sa.CheckConstraint("source_duration_ms > 0", name="ck_evidence_source_duration"),
        sa.CheckConstraint("beam_size > 0", name="ck_evidence_beam_size"),
        sa.CheckConstraint(
            "model_load_seconds IS NULL OR model_load_seconds >= 0",
            name="ck_evidence_model_load_seconds",
        ),
        sa.CheckConstraint("inference_seconds >= 0", name="ck_evidence_inference_seconds"),
        sa.CheckConstraint(
            "language_probability IS NULL OR "
            "(language_probability >= 0 AND language_probability <= 1)",
            name="ck_evidence_language_probability",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_revision_id"], ["transcript_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_lecture_audio_id"], ["lecture_audio.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcript_revision_id", name="uq_transcription_evidence_revision"),
    )
    op.create_index(
        "ix_transcription_evidence_source_sha256",
        "transcription_run_evidence",
        ["source_sha256"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcription_evidence_source_sha256", table_name="transcription_run_evidence"
    )
    op.drop_table("transcription_run_evidence")
    with op.batch_alter_table("lecture_audio", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_lecture_audio_frame_count", type_="check")
        batch_op.drop_constraint("ck_lecture_audio_sample_width_bits", type_="check")
        batch_op.drop_constraint("ck_lecture_audio_channel_count", type_="check")
        batch_op.drop_constraint("ck_lecture_audio_sample_rate_hz", type_="check")
        batch_op.drop_column("frame_count")
        batch_op.drop_column("sample_width_bits")
        batch_op.drop_column("channel_count")
        batch_op.drop_column("sample_rate_hz")
        batch_op.drop_column("audio_format")
