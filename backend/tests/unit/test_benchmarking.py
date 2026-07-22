from __future__ import annotations

import json

from app.services.benchmarking import (
    academic_term_score,
    atomic_write_csv,
    atomic_write_json,
    character_error_rate,
    normalize_metric_text,
    word_error_rate,
)


def test_metric_normalization_preserves_malayalam_and_normalizes_latin_punctuation() -> None:
    assert normalize_metric_text("  Chlorophyll,  സസ്യങ്ങൾ! ") == "chlorophyll സസ്യങ്ങൾ"
    assert normalize_metric_text("ക്ലോറോഫിൽ") == "ക്ലോറോഫിൽ"


def test_word_and_character_error_counts_are_explicit() -> None:
    word_counts, wer = word_error_rate("water carbon", "water glucose")
    character_counts, cer = character_error_rate("abc", "adc")

    assert (word_counts.substitutions, word_counts.deletions, word_counts.insertions) == (1, 0, 0)
    assert wer == 1 / 2
    assert (
        character_counts.substitutions,
        character_counts.deletions,
        character_counts.insertions,
    ) == (
        1,
        0,
        0,
    )
    assert cer == 1 / 3


def test_academic_terms_are_scored_as_exact_raw_hypothesis_terms() -> None:
    score = academic_term_score(
        "Water and carbon dioxide make glucose; oxygen leaves the plant.",
        ["chlorophyll", "water", "carbon dioxide", "glucose", "oxygen", "photosynthesis"],
    )

    assert score["exact_hits"] == ["water", "carbon dioxide", "glucose", "oxygen"]
    assert score["misses"] == ["chlorophyll", "photosynthesis"]
    assert score["exact_recall"] == 4 / 6


def test_benchmark_evidence_outputs_are_atomic_and_parseable(tmp_path) -> None:
    payload = {"native": {"text": "ക്ലോറോഫിൽ", "probability": 0.9}, "terms": ["water"]}
    json_path = tmp_path / "benchmark.json"
    csv_path = tmp_path / "benchmark.csv"

    atomic_write_json(json_path, payload)
    atomic_write_csv(csv_path, payload)

    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    assert csv_path.read_text(encoding="utf-8").startswith("field,value\n")
    assert not list(tmp_path.glob(".*"))
