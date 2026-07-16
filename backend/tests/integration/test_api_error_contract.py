import json

import pytest

from app.api.dependencies import get_repository, get_student
from app.contracts.teacher_review import DomainError


def assert_response_has_no_sensitive_content(body: dict[str, object]) -> None:
    serialized = json.dumps(body)
    for forbidden in (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "SQLAlchemy",
        "Traceback",
        "C:\\\\",
        "shravya-inclucode",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("category", "status_code"),
    [
        ("not_found", 404),
        ("validation", 422),
        ("conflict", 409),
        ("forbidden", 403),
    ],
)
def test_domain_errors_are_mapped_to_safe_http_responses(
    migrated_api, category: str, status_code: int
) -> None:
    def raise_domain_error() -> None:
        raise DomainError(
            code=f"test_{category}",
            message_key=f"test.{category}",
            category=category,
            details={"safe_identifier": "context-test"},
        )

    migrated_api.app.dependency_overrides[get_repository] = raise_domain_error

    response = migrated_api.client.get("/api/v1/teacher/courses/course-test/contexts")

    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == f"test_{category}"
    assert body["message_key"] == f"test.{category}"
    assert body["details"] == {"safe_identifier": "context-test"}
    assert_response_has_no_sensitive_content(body)


def test_unexpected_error_has_a_safe_generic_500_response(migrated_api) -> None:
    def raise_unexpected_error() -> None:
        raise RuntimeError(
            "SELECT * FROM private_records at C:\\Users\\saths\\Documents\\shravya-inclucode"
        )

    migrated_api.app.dependency_overrides[get_student] = raise_unexpected_error

    response = migrated_api.client.get("/api/v1/student/courses/course-test/lesson-overview")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message_key"] == "error.internal"
    assert body["details"] == {}
    assert "private_records" not in response.text
    assert_response_has_no_sensitive_content(body)
