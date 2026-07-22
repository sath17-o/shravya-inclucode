from __future__ import annotations

import csv
import json
import os
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class EditCounts:
    substitutions: int
    deletions: int
    insertions: int

    @property
    def distance(self) -> int:
        return self.substitutions + self.deletions + self.insertions


def normalize_metric_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(without_punctuation.split())


def edit_counts(reference: list[T], hypothesis: list[T]) -> EditCounts:
    rows = len(reference) + 1
    columns = len(hypothesis) + 1
    table: list[list[tuple[int, EditCounts]]] = [
        [(0, EditCounts(0, 0, 0)) for _ in range(columns)] for _ in range(rows)
    ]
    for row in range(1, rows):
        table[row][0] = (row, EditCounts(0, row, 0))
    for column in range(1, columns):
        table[0][column] = (column, EditCounts(0, 0, column))
    for row in range(1, rows):
        for column in range(1, columns):
            if reference[row - 1] == hypothesis[column - 1]:
                table[row][column] = table[row - 1][column - 1]
                continue
            candidates = (
                _add(table[row - 1][column - 1], substitutions=1),
                _add(table[row - 1][column], deletions=1),
                _add(table[row][column - 1], insertions=1),
            )
            table[row][column] = min(candidates, key=lambda item: item[0])
    return table[-1][-1][1]


def word_error_rate(reference: str, hypothesis: str) -> tuple[EditCounts, float | None]:
    reference_words = normalize_metric_text(reference).split()
    hypothesis_words = normalize_metric_text(hypothesis).split()
    counts = edit_counts(reference_words, hypothesis_words)
    return counts, counts.distance / len(reference_words) if reference_words else None


def character_error_rate(reference: str, hypothesis: str) -> tuple[EditCounts, float | None]:
    normalized_reference = normalize_metric_text(reference)
    normalized_hypothesis = normalize_metric_text(hypothesis)
    counts = edit_counts(list(normalized_reference), list(normalized_hypothesis))
    return counts, counts.distance / len(normalized_reference) if normalized_reference else None


def academic_term_score(hypothesis: str, terms: list[str]) -> dict[str, object]:
    normalized_hypothesis = f" {normalize_metric_text(hypothesis)} "
    expected = [normalize_metric_text(term) for term in terms if normalize_metric_text(term)]
    hits = [term for term in expected if f" {term} " in normalized_hypothesis]
    misses = [term for term in expected if term not in hits]
    return {
        "exact_hits": hits,
        "misses": misses,
        "exact_recall": len(hits) / len(expected) if expected else None,
    }


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def atomic_write_csv(path: Path, payload: dict[str, object]) -> None:
    flattened = _flatten(payload)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["field", "value"])
            writer.writerows(sorted(flattened.items()))
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def counts_payload(counts: EditCounts) -> dict[str, int]:
    return asdict(counts)


def _add(
    entry: tuple[int, EditCounts],
    *,
    substitutions: int = 0,
    deletions: int = 0,
    insertions: int = 0,
) -> tuple[int, EditCounts]:
    _, counts = entry
    next_counts = EditCounts(
        substitutions=counts.substitutions + substitutions,
        deletions=counts.deletions + deletions,
        insertions=counts.insertions + insertions,
    )
    return next_counts.distance, next_counts


def _flatten(value: object, prefix: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        result: dict[str, str] = {}
        for key, item in value.items():
            result.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return result
    if isinstance(value, list):
        return {prefix: json.dumps(value, ensure_ascii=False)}
    return {prefix: "" if value is None else str(value)}
