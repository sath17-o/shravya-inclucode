import json
from pathlib import Path

from app.main import create_app


def test_committed_openapi_snapshot_matches_the_fastapi_source_of_truth() -> None:
    snapshot_path = Path(__file__).resolve().parents[3] / "shared" / "contracts" / "openapi.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert create_app().openapi() == expected


def test_curriculum_endpoints_reference_the_standard_error_schema() -> None:
    schema = create_app().openapi()
    error_properties = schema["components"]["schemas"]["ErrorResponse"]["properties"]
    assert {"code", "message_key", "details"} <= set(error_properties)
    assert [name for name in schema["components"]["schemas"] if "Error" in name] == [
        "ErrorResponse"
    ]

    curriculum_path = schema["paths"]["/api/v1/teacher/contexts/{context_id}"]["get"]
    for status_code in ("403", "404", "409", "422", "500"):
        response_schema = curriculum_path["responses"][status_code]["content"]["application/json"][
            "schema"
        ]
        assert response_schema == {"$ref": "#/components/schemas/ErrorResponse"}
