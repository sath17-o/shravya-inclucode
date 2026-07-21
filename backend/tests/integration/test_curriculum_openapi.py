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
    "/api/v1/curriculum/context-versions/{context_version_id}/audio-workflow": "get",
    "/api/v1/teacher/lessons/{lesson_id}/recordings": "post",
    "/api/v1/curriculum/context-versions/{context_version_id}/recordings/{recording_id}": "delete",
    "/api/v1/teacher/recordings/{recording_id}/transcriptions": "post",
    "/api/v1/teacher/processing-jobs/{job_id}": "get",
    "/api/v1/teacher/processing-jobs/{job_id}/run": "post",
    "/api/v1/teacher/transcript-revisions/{revision_id}": "get",
    "/api/v1/teacher/term-suggestions/{suggestion_id}/decision": "post",
    "/api/v1/teacher/transcript-revisions/{revision_id}/manual-revision": "post",
    "/api/v1/teacher/recordings/{recording_id}/manual-revision": "post",
    "/api/v1/teacher/transcript-revisions/{revision_id}/quality-assessment": "post",
    "/api/v1/teacher/transcript-revisions/{revision_id}/approve": "post",
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
    assert "misrecognitions" not in components["StudentGlossaryTermResponse"]["properties"]
    assert "misrecognitions" in components["GlossaryTermResponse"]["properties"]
    assert "teacher_review_status" not in components["StudentTranscriptResponse"]["properties"]
    assert "teacher_review_status" in components["TranscriptRevisionResponse"]["properties"]
    assert len(components) == len(set(components))
    assert not {"Course", "Lesson", "GeneratedArtifact", "ContextReviewEvent"} & set(components)
    assert not any(
        token in path.casefold()
        for path in schema["paths"]
        for token in (
            "seed",
            "reset",
            "debug",
            "practice",
            "focus-journey",
        )
    )


def test_recording_content_is_documented_as_binary_wav_with_json_errors() -> None:
    operation = create_app().openapi()["paths"][
        "/api/v1/teacher/recordings/{recording_id}/content"
    ]["get"]
    assert operation["responses"]["200"]["content"] == {
        "audio/wav": {"schema": {"type": "string", "format": "binary"}}
    }
    for status_code in ("403", "404", "409", "422", "500"):
        assert operation["responses"][status_code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
