from __future__ import annotations

from dataclasses import dataclass

from app.contracts.enums import TermDecisionValue
from app.models.foundation import LectureAudio, TranscriptRevision
from app.services.transcript_provenance import recognised_provenance


@dataclass(frozen=True, slots=True)
class TranscriptQualityFinding:
    code: str
    severity: str
    action: str
    measured: float
    threshold: float


def evaluate_transcript_quality(
    revision: TranscriptRevision, minimum_coverage: float, *, latest_revision_id: str | None = None
) -> tuple[TranscriptQualityFinding, ...]:
    """Evaluate current transcript evidence without trusting a persisted assessment."""

    findings: list[TranscriptQualityFinding] = []
    segments = sorted(revision.segments, key=lambda item: (item.sequence, item.id))
    duration_ms = revision.lecture_audio.duration_ms

    if duration_ms <= 0:
        findings.append(
            TranscriptQualityFinding(
                "recording_duration", "BLOCKING", "replace_recording", duration_ms, 1
            )
        )
    if not segments or any(not item.text.strip() for item in segments):
        findings.append(
            TranscriptQualityFinding("nonempty_segments", "BLOCKING", "manual_transcript", 0, 1)
        )

    expected_sequences = list(range(1, len(segments) + 1))
    actual_sequences = [item.sequence for item in segments]
    if actual_sequences != expected_sequences:
        findings.append(
            TranscriptQualityFinding("segment_sequence", "BLOCKING", "renumber_segments", 0, 1)
        )

    valid_intervals: list[tuple[int, int]] = []
    invalid_interval_count = 0
    previous_start: int | None = None
    out_of_order_count = 0
    for item in segments:
        if previous_start is not None and item.start_ms < previous_start:
            out_of_order_count += 1
        previous_start = item.start_ms
        if 0 <= item.start_ms < item.end_ms <= duration_ms:
            valid_intervals.append((item.start_ms, item.end_ms))
        else:
            invalid_interval_count += 1
    if invalid_interval_count:
        findings.append(
            TranscriptQualityFinding(
                "timestamp_validity", "BLOCKING", "correct_timestamps", invalid_interval_count, 0
            )
        )
    if out_of_order_count:
        findings.append(
            TranscriptQualityFinding(
                "timestamp_order", "BLOCKING", "reorder_segments", out_of_order_count, 0
            )
        )

    covered_ms = _merged_coverage(valid_intervals)
    coverage = covered_ms / duration_ms if duration_ms > 0 else 0
    if coverage < minimum_coverage:
        findings.append(
            TranscriptQualityFinding(
                "timestamp_coverage",
                "BLOCKING",
                "extend_timestamps",
                coverage,
                minimum_coverage,
            )
        )

    provenance = recognised_provenance(revision)
    if not provenance.supported:
        findings.append(
            TranscriptQualityFinding(
                provenance.code or "provenance_unrecognised",
                "BLOCKING",
                "correct_provenance",
                0,
                1,
            )
        )

    unresolved = unresolved_suggestion_count(revision)
    if unresolved:
        findings.append(
            TranscriptQualityFinding(
                "unresolved_terms", "BLOCKING", "confirm_or_edit_term", unresolved, 0
            )
        )

    latest = latest_transcript_revision(revision.lecture_audio)
    if latest_revision_id is None:
        latest_revision_id = latest.id if latest is not None else None
    if latest_revision_id != revision.id:
        findings.append(
            TranscriptQualityFinding("latest_revision", "BLOCKING", "review_latest_revision", 0, 1)
        )
    return tuple(findings)


def latest_transcript_revision(recording: LectureAudio) -> TranscriptRevision | None:
    return max(
        recording.transcript_revisions,
        key=lambda item: (item.revision_number, item.id),
        default=None,
    )


def unresolved_suggestion_count(revision: TranscriptRevision) -> int:
    unresolved = 0
    for segment in revision.segments:
        for suggestion in segment.term_suggestions:
            decision = max(
                suggestion.decisions, key=lambda item: (item.created_at, item.id), default=None
            )
            if decision is None or decision.decision is not TermDecisionValue.CONFIRMED:
                unresolved += 1
    return unresolved


def _merged_coverage(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    covered_ms = 0
    merged_start, merged_end = sorted(intervals)[0]
    for start_ms, end_ms in sorted(intervals)[1:]:
        if start_ms <= merged_end:
            merged_end = max(merged_end, end_ms)
        else:
            covered_ms += merged_end - merged_start
            merged_start, merged_end = start_ms, end_ms
    return covered_ms + merged_end - merged_start
