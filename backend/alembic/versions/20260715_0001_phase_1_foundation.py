"""create explicit Phase 1 foundation schema

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260715_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_learner_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_key", sa.String(length=64), nullable=False),
        sa.Column("profile_schema_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("profile_schema_version >= 1", name="ck_profile_schema_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_key"),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("class_level", sa.Integer(), nullable=False),
        sa.Column("grade_band", sa.String(length=20), nullable=False),
        sa.Column("board_source", sa.String(length=200), nullable=True),
        sa.CheckConstraint("class_level BETWEEN 5 AND 10", name="ck_courses_class_level"),
        sa.CheckConstraint(
            "((class_level BETWEEN 5 AND 7 AND grade_band = '5-7') "
            "OR (class_level BETWEEN 8 AND 10 AND grade_band = '8-10'))",
            name="ck_courses_grade_band",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "course_context_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("teacher_review_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_course_context_version_number"),
        sa.CheckConstraint(
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
            name="ck_teacher_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name="fk_context_course", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "version_number", name="uq_course_context_version"),
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_version_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_chapters_sequence"),
        sa.ForeignKeyConstraint(
            ["context_version_id"],
            ["course_context_versions.id"],
            name="fk_chapter_context",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("context_version_id", "sequence", name="uq_chapter_context_sequence"),
    )
    op.create_table(
        "lessons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("primary_language", sa.String(length=20), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_lessons_sequence"),
        sa.ForeignKeyConstraint(
            ["chapter_id"], ["chapters.id"], name="fk_lesson_chapter", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "sequence", name="uq_lesson_chapter_sequence"),
        sa.UniqueConstraint("chapter_id", "title", name="uq_lesson_chapter_title"),
    )
    op.create_table(
        "learning_objectives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("objective_text", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_learning_objectives_sequence"),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_objective_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "sequence", name="uq_objective_lesson_sequence"),
    )
    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_term", sa.String(length=200), nullable=False),
        sa.Column("malayalam_support_label", sa.String(length=200), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_glossary_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "canonical_term", name="uq_glossary_lesson_term"),
    )
    op.create_table(
        "term_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("glossary_term_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["glossary_term_id"], ["glossary_terms.id"], name="fk_alias_term", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("glossary_term_id", "alias", name="uq_term_alias"),
    )
    op.create_table(
        "asr_misrecognitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("glossary_term_id", sa.String(length=36), nullable=False),
        sa.Column("detected_text", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["glossary_term_id"],
            ["glossary_terms.id"],
            name="fk_misrecognition_term",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("glossary_term_id", "detected_text", name="uq_asr_misrecognition"),
    )
    op.create_table(
        "lecture_audio",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("source_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "source_status IN ('LIVE', 'CACHED', 'DEMO')", name="ck_lecture_audio_source_status"
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_audio_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lecture_audio_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("source_status", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.CheckConstraint("revision_number >= 1", name="ck_transcript_revisions_number"),
        sa.CheckConstraint(
            "source_status IN ('LIVE', 'CACHED', 'DEMO')",
            name="ck_transcript_revision_source_status",
        ),
        sa.ForeignKeyConstraint(
            ["lecture_audio_id"], ["lecture_audio.id"], name="fk_revision_audio", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lecture_audio_id", "revision_number", name="uq_audio_transcript_revision"
        ),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript_revision_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.CheckConstraint("sequence >= 1", name="ck_transcript_segments_sequence"),
        sa.CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_transcript_segments_end"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_transcript_segments_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_revision_id"],
            ["transcript_revisions.id"],
            name="fk_segment_revision",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transcript_revision_id", "sequence", name="uq_transcript_segment_sequence"
        ),
    )
    op.create_table(
        "term_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript_segment_id", sa.String(length=36), nullable=False),
        sa.Column("glossary_term_id", sa.String(length=36), nullable=True),
        sa.Column("detected_text", sa.String(length=200), nullable=False),
        sa.Column("character_start", sa.Integer(), nullable=False),
        sa.Column("character_end", sa.Integer(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("context_snapshot", sa.Text(), nullable=True),
        sa.CheckConstraint("character_start >= 0", name="ck_term_suggestions_character_start"),
        sa.CheckConstraint(
            "character_end > character_start", name="ck_term_suggestions_character_end"
        ),
        sa.CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 1)",
            name="ck_term_suggestions_match_score",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_segment_id"],
            ["transcript_segments.id"],
            name="fk_suggestion_segment",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["glossary_term_id"],
            ["glossary_terms.id"],
            name="fk_suggestion_glossary",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "term_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("term_suggestion_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("decided_by_role", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "decision IN ('CONFIRMED', 'REJECTED', 'UNSURE')", name="ck_term_decision_value"
        ),
        sa.ForeignKeyConstraint(
            ["term_suggestion_id"],
            ["term_suggestions.id"],
            name="fk_decision_suggestion",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript_quality_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript_revision_id", sa.String(length=36), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "quality_status IN ('VERIFIED', 'NEEDS_REVIEW', 'FAILED')", name="ck_quality_status"
        ),
        sa.ForeignKeyConstraint(
            ["transcript_revision_id"],
            ["transcript_revisions.id"],
            name="fk_quality_revision",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcript_revision_id", name="uq_quality_assessment_revision"),
    )
    op.create_table(
        "transcript_quality_reasons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message_key", sa.String(length=200), nullable=False),
        sa.Column("measured_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("recovery_action", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'BLOCKING')", name="ck_quality_reason_severity"
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["transcript_quality_assessments.id"],
            name="fk_reason_assessment",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "reason_code", name="uq_quality_reason_code"),
    )
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_message", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("recoverable", sa.Boolean(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("retry_count >= 0", name="ck_processing_jobs_retry_count"),
        sa.CheckConstraint(
            "job_type IN ("
            "'TRANSCRIPTION', 'CONCEPT_EXTRACTION', 'LAYERED_CONTENT_GENERATION', "
            "'EXPLAIN_DIFFERENTLY', 'VISUAL_STORY_PREPARATION', 'TTS_GENERATION', "
            "'PRACTICE_GENERATION')",
            name="ck_processing_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_job_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "concepts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_concepts_sequence"),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_concept_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "sequence", name="uq_concept_lesson_sequence"),
    )
    op.create_table(
        "concept_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("transcript_segment_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["concepts.id"], name="fk_evidence_concept", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transcript_segment_id"],
            ["transcript_segments.id"],
            name="fk_evidence_segment",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "transcript_segment_id", name="uq_concept_evidence"),
    )
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("source_transcript_revision_id", sa.String(length=36), nullable=True),
        sa.Column("course_context_version_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=150), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_status", sa.String(length=20), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.Column("uncertainty_status", sa.String(length=20), nullable=False),
        sa.Column("uncertainty_note", sa.Text(), nullable=True),
        sa.Column("teacher_review_status", sa.String(length=20), nullable=False),
        sa.Column("generation_status", sa.String(length=30), nullable=False),
        sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source_status IN ('LIVE', 'CACHED', 'DEMO')", name="ck_artifact_source_status"
        ),
        sa.CheckConstraint(
            "quality_status IN ('VERIFIED', 'NEEDS_REVIEW', 'FAILED')",
            name="ck_artifact_quality_status",
        ),
        sa.CheckConstraint(
            "uncertainty_status IN ('CONFIRMED', 'TENTATIVE', 'UNRESOLVED', 'NOT_APPLICABLE')",
            name="ck_uncertainty_status",
        ),
        sa.CheckConstraint(
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
            name="ck_artifact_teacher_review_status",
        ),
        sa.CheckConstraint(
            "generation_status IN ('READY', 'BLOCKED_BY_QUALITY', 'STALE', 'FAILED')",
            name="ck_artifact_status",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_artifact_lesson", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_transcript_revision_id"],
            ["transcript_revisions.id"],
            name="fk_artifact_revision",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_context_version_id"],
            ["course_context_versions.id"],
            name="fk_artifact_context",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "artifact_source_concepts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["generated_artifacts.id"],
            name="fk_artifact_concept_artifact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["concepts.id"], name="fk_artifact_concept_concept", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "concept_id", name="uq_artifact_source_concept"),
    )
    op.create_table(
        "artifact_source_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("reference_type", sa.String(length=100), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=False),
        sa.Column("display_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["generated_artifacts.id"],
            name="fk_artifact_reference_artifact",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "learning_preference_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=36), nullable=False),
        sa.Column("interface_language", sa.String(length=20), nullable=False),
        sa.Column("text_size", sa.String(length=30), nullable=False),
        sa.Column("line_spacing", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"],
            ["local_learner_profiles.id"],
            name="fk_preferences_profile",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_profile_id"),
    )
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=36), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("current_route", sa.String(length=250), nullable=False),
        sa.Column("resume_payload_version", sa.Integer(), nullable=False),
        sa.Column("resume_payload", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "resume_payload_version >= 1", name="ck_learning_sessions_payload_version"
        ),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"],
            ["local_learner_profiles.id"],
            name="fk_session_profile",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_session_lesson", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "learner_profile_id", "lesson_id", name="uq_learning_session_profile_lesson"
        ),
    )
    op.create_table(
        "learner_concept_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "state IN ('not_started', 'viewed', 'understood', 'unsure', "
            "'needs_another_explanation', 'ready_for_practice')",
            name="ck_concept_state",
        ),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"],
            ["local_learner_profiles.id"],
            name="fk_state_profile",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["concepts.id"], name="fk_state_concept", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_profile_id", "concept_id", name="uq_learner_concept_state"),
    )
    op.create_table(
        "question_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("related_concept_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_label", sa.String(length=200), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("marks", sa.Integer(), nullable=True),
        sa.Column("teacher_review_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("year IS NULL OR year > 0", name="ck_question_items_year"),
        sa.CheckConstraint("marks IS NULL OR marks > 0", name="ck_question_items_marks"),
        sa.CheckConstraint(
            "teacher_review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED')",
            name="ck_question_teacher_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_question_lesson", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["related_concept_id"], ["concepts.id"], name="fk_question_concept", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_context_versions_course", "course_context_versions", ["course_id"])
    op.create_index("ix_chapters_context", "chapters", ["context_version_id"])
    op.create_index("ix_lessons_chapter", "lessons", ["chapter_id"])
    op.create_index("ix_objectives_lesson", "learning_objectives", ["lesson_id"])
    op.create_index("ix_glossary_lesson", "glossary_terms", ["lesson_id"])
    op.create_index("ix_audio_lesson", "lecture_audio", ["lesson_id"])
    op.create_index("ix_revisions_audio", "transcript_revisions", ["lecture_audio_id"])
    op.create_index("ix_segments_revision", "transcript_segments", ["transcript_revision_id"])
    op.create_index("ix_suggestions_segment", "term_suggestions", ["transcript_segment_id"])
    op.create_index(
        "ix_assessments_revision", "transcript_quality_assessments", ["transcript_revision_id"]
    )
    op.create_index("ix_reasons_assessment", "transcript_quality_reasons", ["assessment_id"])
    op.create_index("ix_jobs_lesson", "processing_jobs", ["lesson_id"])
    op.create_index("ix_concepts_lesson", "concepts", ["lesson_id"])
    op.create_index("ix_artifacts_lesson", "generated_artifacts", ["lesson_id"])
    op.create_index("ix_artifact_concepts_artifact", "artifact_source_concepts", ["artifact_id"])
    op.create_index(
        "ix_artifact_references_artifact", "artifact_source_references", ["artifact_id"]
    )
    op.create_index("ix_sessions_profile", "learning_sessions", ["learner_profile_id"])
    op.create_index("ix_states_profile", "learner_concept_states", ["learner_profile_id"])
    op.create_index("ix_questions_lesson", "question_items", ["lesson_id"])


def downgrade() -> None:
    op.drop_index("ix_questions_lesson", table_name="question_items")
    op.drop_index("ix_states_profile", table_name="learner_concept_states")
    op.drop_index("ix_sessions_profile", table_name="learning_sessions")
    op.drop_index("ix_artifact_references_artifact", table_name="artifact_source_references")
    op.drop_index("ix_artifact_concepts_artifact", table_name="artifact_source_concepts")
    op.drop_index("ix_artifacts_lesson", table_name="generated_artifacts")
    op.drop_index("ix_concepts_lesson", table_name="concepts")
    op.drop_index("ix_jobs_lesson", table_name="processing_jobs")
    op.drop_index("ix_reasons_assessment", table_name="transcript_quality_reasons")
    op.drop_index("ix_assessments_revision", table_name="transcript_quality_assessments")
    op.drop_index("ix_suggestions_segment", table_name="term_suggestions")
    op.drop_index("ix_segments_revision", table_name="transcript_segments")
    op.drop_index("ix_revisions_audio", table_name="transcript_revisions")
    op.drop_index("ix_audio_lesson", table_name="lecture_audio")
    op.drop_index("ix_glossary_lesson", table_name="glossary_terms")
    op.drop_index("ix_objectives_lesson", table_name="learning_objectives")
    op.drop_index("ix_lessons_chapter", table_name="lessons")
    op.drop_index("ix_chapters_context", table_name="chapters")
    op.drop_index("ix_context_versions_course", table_name="course_context_versions")

    op.drop_table("question_items")
    op.drop_table("learner_concept_states")
    op.drop_table("learning_sessions")
    op.drop_table("learning_preference_profiles")
    op.drop_table("artifact_source_references")
    op.drop_table("artifact_source_concepts")
    op.drop_table("generated_artifacts")
    op.drop_table("concept_evidence")
    op.drop_table("concepts")
    op.drop_table("processing_jobs")
    op.drop_table("transcript_quality_reasons")
    op.drop_table("transcript_quality_assessments")
    op.drop_table("term_decisions")
    op.drop_table("term_suggestions")
    op.drop_table("transcript_segments")
    op.drop_table("transcript_revisions")
    op.drop_table("lecture_audio")
    op.drop_table("asr_misrecognitions")
    op.drop_table("term_aliases")
    op.drop_table("glossary_terms")
    op.drop_table("learning_objectives")
    op.drop_table("lessons")
    op.drop_table("chapters")
    op.drop_table("course_context_versions")
    op.drop_table("courses")
    op.drop_table("local_learner_profiles")
