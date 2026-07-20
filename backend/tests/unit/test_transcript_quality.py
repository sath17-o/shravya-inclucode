from types import SimpleNamespace

import pytest

from app.contracts.enums import SourceStatus
from app.services.transcript_provenance import (
    DETERMINISTIC_DEMO_PROVENANCE,
    DETERMINISTIC_DEMO_PROVIDER,
    PHASE_3B_PROVIDER_VERSION,
    TEACHER_ENTERED_PROVENANCE,
    TEACHER_ENTERED_PROVIDER,
)
from app.services.transcript_quality import evaluate_transcript_quality


def _revision(
    intervals: list[tuple[int, int]],
    *,
    duration_ms: int = 1000,
    sequences: list[int] | None = None,
    text: str = "Plants need sunlight.",
):
    segments = [
        SimpleNamespace(
            id=f"segment-{index}",
            sequence=(sequences or list(range(1, len(intervals) + 1)))[index - 1],
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            term_suggestions=[],
        )
        for index, (start_ms, end_ms) in enumerate(intervals, 1)
    ]
    recording = SimpleNamespace(duration_ms=duration_ms, transcript_revisions=[])
    revision = SimpleNamespace(
        id="revision-1",
        revision_number=1,
        lecture_audio=recording,
        segments=segments,
        source_status=SourceStatus.LOCAL_TEACHER,
        provider_name=TEACHER_ENTERED_PROVIDER,
        provider_version=PHASE_3B_PROVIDER_VERSION,
        provenance_label=TEACHER_ENTERED_PROVENANCE,
        copied_from_transcript_revision_id=None,
    )
    recording.transcript_revisions = [revision]
    return revision


def _codes(revision) -> set[str]:
    return {item.code for item in evaluate_transcript_quality(revision, 0.9)}


def test_union_coverage_accepts_complete_overlapping_and_touching_intervals() -> None:
    complete = _revision([(0, 500), (500, 1000)])
    overlapping = _revision([(0, 700), (400, 1000)])

    assert "timestamp_coverage" not in _codes(complete)
    assert "timestamp_coverage" not in _codes(overlapping)


@pytest.mark.parametrize(
    ("intervals", "expected"),
    [
        ([(0, 400), (600, 900)], "timestamp_coverage"),
        ([(0, 899)], "timestamp_coverage"),
        ([(0, 900)], None),
        ([(-1, 100)], "timestamp_validity"),
        ([(500, 500)], "timestamp_validity"),
        ([(0, 1001)], "timestamp_validity"),
    ],
)
def test_timestamp_quality_rejects_invalid_or_insufficient_intervals(
    intervals: list[tuple[int, int]], expected: str | None
) -> None:
    codes = _codes(_revision(intervals))

    if expected is None:
        assert "timestamp_coverage" not in codes
    else:
        assert expected in codes


def test_timestamp_quality_rejects_blank_duplicate_or_zero_duration_inputs() -> None:
    assert "nonempty_segments" in _codes(_revision([(0, 1000)], text=" "))
    assert "segment_sequence" in _codes(_revision([(0, 500), (500, 1000)], sequences=[1, 1]))
    assert "recording_duration" in _codes(_revision([(0, 1)], duration_ms=0))


@pytest.mark.parametrize(
    ("source_status", "provider_name", "provider_version", "provenance_label", "expected"),
    [
        (
            SourceStatus.DEMO,
            "legacy-migrated",
            PHASE_3B_PROVIDER_VERSION,
            "Legacy transcript record — provenance unavailable",
            "provenance_unrecognised",
        ),
        (
            SourceStatus.LOCAL_TEACHER,
            "unknown-provider",
            PHASE_3B_PROVIDER_VERSION,
            TEACHER_ENTERED_PROVENANCE,
            "provenance_unrecognised",
        ),
        (
            SourceStatus.DEMO,
            DETERMINISTIC_DEMO_PROVIDER,
            None,
            DETERMINISTIC_DEMO_PROVENANCE,
            "provenance_missing",
        ),
    ],
)
def test_quality_fails_closed_for_unrecognised_provenance(
    source_status, provider_name, provider_version, provenance_label, expected
) -> None:
    revision = _revision([(0, 1000)])
    revision.source_status = source_status
    revision.provider_name = provider_name
    revision.provider_version = provider_version
    revision.provenance_label = provenance_label

    assert expected in _codes(revision)
