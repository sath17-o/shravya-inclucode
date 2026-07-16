from app.main import create_app

CURRICULUM_PATHS = {
    "/api/v1/teacher/courses/{course_id}/contexts": "get",
    "/api/v1/teacher/contexts/{context_id}/completeness": "get",
    "/api/v1/teacher/contexts/{context_id}/review-events": "get",
    "/api/v1/teacher/contexts/{context_id}": "get",
    "/api/v1/teacher/contexts/{context_id}/submit-for-review": "post",
    "/api/v1/teacher/contexts/{context_id}/return-to-draft": "post",
    "/api/v1/teacher/contexts/{context_id}/approve": "post",
    "/api/v1/teacher/contexts/{context_id}/copy-to-new-draft": "post",
    "/api/v1/student/courses/{course_id}/lesson-overview": "get",
}


def test_curriculum_openapi_contract_is_typed_and_has_no_out_of_scope_routes() -> None:
    schema = create_app().openapi()
    operations = [schema["paths"][path][method] for path, method in CURRICULUM_PATHS.items()]

    operation_ids = [operation["operationId"] for operation in operations]
    assert len(operation_ids) == len(set(operation_ids))
    for operation in operations:
        success = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in success
        for status_code in ("403", "404", "409", "422", "500"):
            error = operation["responses"][status_code]["content"]["application/json"]["schema"]
            assert error == {"$ref": "#/components/schemas/ErrorResponse"}

    for path in (
        "/api/v1/teacher/contexts/{context_id}/submit-for-review",
        "/api/v1/teacher/contexts/{context_id}/return-to-draft",
        "/api/v1/teacher/contexts/{context_id}/copy-to-new-draft",
    ):
        request_schema = schema["paths"][path]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert any("$ref" in item for item in request_schema["anyOf"])

    components = schema["components"]["schemas"]
    approval_properties = components["ApprovalResponse"]["properties"]
    assert "newly_staled_artifact_count" in approval_properties
    not_ready_properties = components["StudentLessonOverviewResponse"]["properties"]
    assert {"is_ready", "selected_context_id", "chapters"} <= set(not_ready_properties)
    assert len(components) == len(set(components))
    assert not {"Course", "Lesson", "GeneratedArtifact", "ContextReviewEvent"} & set(components)
    assert not any(
        token in path.casefold()
        for path in schema["paths"]
        for token in (
            "seed",
            "reset",
            "debug",
            "transcription",
            "audio",
            "practice",
            "focus-journey",
        )
    )
