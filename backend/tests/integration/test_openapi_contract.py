import json
from pathlib import Path

from app.main import create_app


def test_committed_openapi_snapshot_matches_the_fastapi_source_of_truth() -> None:
    snapshot_path = Path(__file__).resolve().parents[3] / "shared" / "contracts" / "openapi.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert create_app().openapi() == expected
