import json
from pathlib import Path


def test_photosynthesis_fixture_is_utf8_and_contains_real_malayalam_labels() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[3] / "shared" / "fixtures" / "class-7-photosynthesis.json"
    )
    source = fixture_path.read_text(encoding="utf-8")
    fixture = json.loads(source)

    assert "മലയാളം" in fixture["primary_language"]
    assert "ക്ലോറോഫിൽ" in source
    assert "പ്രകാശസംശ്ലേഷണം" in source
    assert fixture["glossary"][1]["malayalam_support_label"] == "ക്ലോറോഫിൽ"
    assert "Î±â”¤" not in source
    assert "Î“Ã‡" not in source
    assert "�" not in source
