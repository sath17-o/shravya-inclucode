from __future__ import annotations

from dataclasses import dataclass

from app.contracts.enums import SourceStatus
from app.models.foundation import TranscriptRevision
from app.services.malayalam_hybrid_provider import (
    LOCAL_MALAYALAM_HYBRID_PROVENANCE,
    LOCAL_MALAYALAM_HYBRID_PROVIDER,
    LOCAL_MALAYALAM_HYBRID_VERSION,
)
from app.services.transcription_provider import (
    LOCAL_FASTER_WHISPER_PROVENANCE,
    LOCAL_FASTER_WHISPER_PROVIDER,
)

PHASE_3B_PROVIDER_VERSION = "phase-3b"
DETERMINISTIC_DEMO_PROVIDER = "shravya-deterministic-demo"
DETERMINISTIC_DEMO_PROVENANCE = (
    "Deterministic offline demo transcript mapped to a team-recorded "
    "Malayalam/code-mixed lesson — not live STT."
)
TEACHER_ENTERED_PROVIDER = "teacher-entered"
TEACHER_ENTERED_PROVENANCE = "Teacher-entered transcript for a local classroom recording"
TEACHER_ENTERED_DEMO_PROVENANCE = "Teacher-entered transcript for the bundled demo recording"
TEACHER_CORRECTED_PROVIDER = "teacher-corrected"
TEACHER_CORRECTED_DEMO_PROVENANCE = (
    "Teacher-corrected transcript based on deterministic offline demo transcription"
)


@dataclass(frozen=True, slots=True)
class ProvenancePolicyResult:
    supported: bool
    code: str | None = None


def recognised_provenance(revision: TranscriptRevision) -> ProvenancePolicyResult:
    """Allow only explicit Phase 3B transcript origins; future providers register here."""

    provider = revision.provider_name.strip()
    version = (revision.provider_version or "").strip()
    label = revision.provenance_label.strip()

    if (
        revision.source_status is SourceStatus.LOCAL_TEACHER
        and provider == LOCAL_MALAYALAM_HYBRID_PROVIDER
        and version == LOCAL_MALAYALAM_HYBRID_VERSION
        and label == LOCAL_MALAYALAM_HYBRID_PROVENANCE
        and revision.copied_from_transcript_revision_id is None
    ):
        return ProvenancePolicyResult(True)
    if (
        revision.source_status is SourceStatus.LOCAL_TEACHER
        and provider == LOCAL_FASTER_WHISPER_PROVIDER
        and bool(version)
        and label == LOCAL_FASTER_WHISPER_PROVENANCE
        and revision.copied_from_transcript_revision_id is None
    ):
        return ProvenancePolicyResult(True)
    if (
        revision.source_status is SourceStatus.DEMO
        and provider == DETERMINISTIC_DEMO_PROVIDER
        and version == PHASE_3B_PROVIDER_VERSION
        and label == DETERMINISTIC_DEMO_PROVENANCE
        and revision.copied_from_transcript_revision_id is None
    ):
        return ProvenancePolicyResult(True)
    if (
        revision.source_status is SourceStatus.DEMO
        and provider == TEACHER_ENTERED_PROVIDER
        and version == PHASE_3B_PROVIDER_VERSION
        and label == TEACHER_ENTERED_DEMO_PROVENANCE
        and revision.copied_from_transcript_revision_id is None
    ):
        return ProvenancePolicyResult(True)
    if (
        revision.source_status is SourceStatus.LOCAL_TEACHER
        and provider == TEACHER_ENTERED_PROVIDER
        and version == PHASE_3B_PROVIDER_VERSION
        and label == TEACHER_ENTERED_PROVENANCE
    ):
        return ProvenancePolicyResult(True)
    if (
        revision.source_status is SourceStatus.DEMO
        and provider == TEACHER_CORRECTED_PROVIDER
        and version == PHASE_3B_PROVIDER_VERSION
        and label == TEACHER_CORRECTED_DEMO_PROVENANCE
        and is_recognised_deterministic_demo_parent(revision.copied_from_transcript_revision)
    ):
        return ProvenancePolicyResult(True)
    if not provider or not label or not version:
        return ProvenancePolicyResult(False, "provenance_missing")
    return ProvenancePolicyResult(False, "provenance_unrecognised")


def is_recognised_deterministic_demo_parent(revision: TranscriptRevision | None) -> bool:
    """Accept only the exact, original deterministic fixture provenance as a correction parent."""

    return bool(
        revision is not None
        and revision.source_status is SourceStatus.DEMO
        and revision.provider_name.strip() == DETERMINISTIC_DEMO_PROVIDER
        and (revision.provider_version or "").strip() == PHASE_3B_PROVIDER_VERSION
        and revision.provenance_label.strip() == DETERMINISTIC_DEMO_PROVENANCE
        and revision.copied_from_transcript_revision_id is None
    )
