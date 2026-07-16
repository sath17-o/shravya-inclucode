from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.contracts.enums import ArtifactStatus, ContextReviewEventType, TeacherReviewStatus
from app.models.foundation import CourseContextVersion, GeneratedArtifact
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import SECTION_ORDER, ContextCompletenessService
from app.services.teacher_review import TeacherReviewService
from tests.integration.factories import (
    approved_material,
    asr_misrecognition,
    chapter,
    complete_photosynthesis_context,
    concept,
    context_version,
    course,
    generated_artifact,
    glossary_term,
    learning_objective,
    lesson,
    question_item,
    review_event,
    term_alias,
)


def assert_no_internal_fields(value: object) -> None:
    if isinstance(value, dict):
        assert "_sa_instance_state" not in value
        for child in value.values():
            assert_no_internal_fields(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_internal_fields(child)


def assert_error(response, status: int, code: str, message_key: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == code
    assert body["message_key"] == message_key
    assert isinstance(body["details"], dict)
    assert {"message", "recoverable", "next_actions", "job_id"} <= set(body)
    assert_no_internal_fields(body)
    return body


def complete_context_setup(migrated_api, **kwargs):
    with migrated_api.session_factory() as session:
        result = complete_photosynthesis_context(session, **kwargs)
        session.commit()
        return result.course.id, result.context.id, result.lesson.id


def test_teacher_context_list_is_ordered_typed_and_safe(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        course_model = course()
        first = context_version(course=course_model, version_number=1)
        second = context_version(
            course=course_model,
            version_number=2,
            teacher_review_status=TeacherReviewStatus.NEEDS_REVIEW,
            submitted_at=datetime(2026, 7, 16, tzinfo=UTC),
            reviewer_note="Ready for review.",
        )
        third = context_version(
            course=course_model,
            version_number=3,
            teacher_review_status=TeacherReviewStatus.APPROVED,
            copied_from_context_version=first,
            submitted_at=datetime(2026, 7, 16, tzinfo=UTC),
            approved_at=datetime(2026, 7, 17, tzinfo=UTC),
        )
        session.add_all([course_model, third, second, first])
        session.commit()
        course_id, first_id = course_model.id, first.id
        context_ids = [first.id, second.id, third.id]

    response = migrated_api.client.get(f"/api/v1/teacher/courses/{course_id}/contexts")

    assert response.status_code == 200
    contexts = response.json()["data"]
    assert [item["version_number"] for item in contexts] == [1, 2, 3]
    assert [item["id"] for item in contexts] == context_ids
    assert contexts[0]["teacher_review_status"] == TeacherReviewStatus.DRAFT.value
    assert contexts[2]["copied_from_context_version_id"] == first_id
    assert contexts[0]["submitted_at"] is None and contexts[0]["approved_at"] is None
    assert contexts[1]["reviewer_note"] == "Ready for review."
    assert_no_internal_fields(response.json())
    assert_error(
        migrated_api.client.get("/api/v1/teacher/courses/missing/contexts"),
        404,
        "course_not_found",
        "course.not_found",
    )


def test_teacher_detail_serializes_deterministic_complete_curriculum(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        result = complete_photosynthesis_context(session)
        second_chapter = chapter(context_version=result.context, title="Second chapter", sequence=2)
        second_lesson = lesson(chapter=second_chapter, title="Second lesson", sequence=1)
        session.add_all([second_chapter, second_lesson])
        session.flush()
        session.add_all(
            [
                learning_objective(
                    lesson=result.lesson, objective_text="Second objective", sequence=2
                ),
                approved_material(lesson=result.lesson, title="Second material", sequence=2),
                glossary_term(lesson=result.lesson, canonical_term="Extra term", sequence=11),
                concept(
                    lesson=result.lesson,
                    concept_key="extra-concept",
                    title="Extra concept",
                    sequence=6,
                ),
                question_item(lesson=result.lesson, question_text="Second question", sequence=2),
                term_alias(
                    glossary_term=result.glossary_terms[0],
                    alias="A alias",
                    normalized_alias="a alias",
                ),
                asr_misrecognition(
                    glossary_term=result.glossary_terms[1],
                    detected_text="a chlorophyll",
                    normalized_text="a chlorophyll",
                ),
                review_event(
                    id="event-b",
                    context_version_id=result.context.id,
                    event_type=ContextReviewEventType.SUBMITTED_FOR_REVIEW,
                    note="Submitted.",
                    created_at=datetime(2026, 7, 16, tzinfo=UTC),
                ),
                review_event(
                    id="event-a",
                    context_version_id=result.context.id,
                    event_type=ContextReviewEventType.DRAFT_CREATED,
                    note=None,
                    created_at=datetime(2026, 7, 16, tzinfo=UTC),
                ),
            ]
        )
        session.commit()
        context_id = result.context.id

    response = migrated_api.client.get(f"/api/v1/teacher/contexts/{context_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert {"chapters", "completeness", "review_events"} <= set(data)
    assert [item["sequence"] for item in data["chapters"]] == [1, 2]
    lesson_data = data["chapters"][0]["lessons"][0]
    assert [item["sequence"] for item in lesson_data["objectives"]] == [1, 2]
    assert [item["sequence"] for item in lesson_data["approved_materials"]] == [1, 2]
    assert [item["sequence"] for item in lesson_data["glossary_terms"]] == list(range(1, 12))
    assert [item["sequence"] for item in lesson_data["concepts"]] == list(range(1, 7))
    assert [item["sequence"] for item in lesson_data["questions"]] == [1, 2]
    assert [item["normalized_alias"] for item in lesson_data["glossary_terms"][0]["aliases"]] == [
        "a alias",
        "plant food process",
    ]
    assert [
        item["normalized_text"] for item in lesson_data["glossary_terms"][1]["misrecognitions"]
    ] == [
        "a chlorophyll",
        "chlorophil",
    ]
    assert [item["id"] for item in data["review_events"]] == ["event-a", "event-b"]
    assert data["review_events"][0]["event_type"] == "draft_created"
    assert data["review_events"][0]["actor_role"] == "teacher"
    assert lesson_data["glossary_terms"][0]["malayalam_support_label"] == "പ്രകാശസംശ്ലേഷണം"
    assert lesson_data["glossary_terms"][1]["malayalam_support_label"] == "ക്ലോറോഫിൽ"
    assert (
        lesson_data["objectives"][0]["malayalam_text"]
        == "സസ്യങ്ങൾ എങ്ങനെ ആഹാരം നിർമ്മിക്കുന്നു എന്ന് വിശദീകരിക്കുക."
    )
    assert lesson_data["questions"][0]["malayalam_question_text"] == (
        "പ്രകാശസംശ്ലേഷണത്തിന് സസ്യങ്ങൾക്ക് എന്താണ് വേണ്ടത്?"
    )
    assert_no_internal_fields(data)
    assert_error(
        migrated_api.client.get("/api/v1/teacher/contexts/missing"),
        404,
        "context_not_found",
        "context.not_found",
    )


def test_completeness_endpoint_matches_service_and_is_deterministic(migrated_api) -> None:
    complete_course_id, complete_id, _ = complete_context_setup(migrated_api)
    with migrated_api.session_factory() as session:
        incomplete_course = course(title="Incomplete Science")
        incomplete = context_version(course=incomplete_course)
        session.add_all([incomplete_course, incomplete])
        session.commit()
        expected = ContextCompletenessService(CurriculumRepository(session)).evaluate(incomplete.id)
        incomplete_id = incomplete.id

    complete_response = migrated_api.client.get(
        f"/api/v1/teacher/contexts/{complete_id}/completeness"
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["data"] == {
        "context_version_id": complete_id,
        "is_complete": True,
        "issues": [],
        "completed_sections": [
            "chapters",
            "lessons",
            "learning_objectives",
            "approved_materials",
            "glossary",
            "concepts",
            "questions",
            "required_text",
            "relationships",
        ],
        "incomplete_sections": [],
    }
    incomplete_response = migrated_api.client.get(
        f"/api/v1/teacher/contexts/{incomplete_id}/completeness"
    )
    assert incomplete_response.status_code == 200
    assert incomplete_response.json()["data"] == expected.model_dump(mode="json")
    issues = incomplete_response.json()["data"]["issues"]
    assert [(item["section"], item["code"], item["field"] or "") for item in issues] == sorted(
        [(item["section"], item["code"], item["field"] or "") for item in issues],
        key=lambda item: (SECTION_ORDER.index(item[0]), item[1], item[2]),
    )
    assert {"code", "section", "field", "message_key", "recovery_action"} <= set(issues[0])
    assert_error(
        migrated_api.client.get("/api/v1/teacher/contexts/missing/completeness"),
        404,
        "context_not_found",
        "context.not_found",
    )


def test_review_history_is_chronological_and_handles_nullable_notes(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        result = complete_photosynthesis_context(session)
        session.add_all(
            [
                review_event(
                    id="event-z",
                    context_version_id=result.context.id,
                    created_at=datetime(2026, 7, 17, tzinfo=UTC),
                    note=None,
                ),
                review_event(
                    id="event-a",
                    context_version_id=result.context.id,
                    created_at=datetime(2026, 7, 16, tzinfo=UTC),
                    event_type=ContextReviewEventType.APPROVED,
                    note="Approved.",
                ),
            ]
        )
        session.commit()
        context_id = result.context.id

    response = migrated_api.client.get(f"/api/v1/teacher/contexts/{context_id}/review-events")

    assert response.status_code == 200
    events = response.json()["data"]
    assert [item["id"] for item in events] == ["event-a", "event-z"]
    assert events[0]["event_type"] == "approved"
    assert events[1]["note"] is None
    assert all("created_at" in item and item["actor_role"] == "teacher" for item in events)
    assert_error(
        migrated_api.client.get("/api/v1/teacher/contexts/missing/review-events"),
        404,
        "context_not_found",
        "context.not_found",
    )


def test_submit_and_return_to_draft_transitions_are_atomic_over_http(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        incomplete_course = course(title="Incomplete")
        incomplete = context_version(course=incomplete_course)
        session.add_all([incomplete_course, incomplete])
        session.commit()
        incomplete_id = incomplete.id
        incomplete_issue_count = len(
            ContextCompletenessService(CurriculumRepository(session)).evaluate(incomplete_id).issues
        )
    incomplete_response = migrated_api.client.post(
        f"/api/v1/teacher/contexts/{incomplete_id}/submit-for-review",
        json={"reviewer_note": "Ready for review."},
    )
    body = assert_error(incomplete_response, 422, "context_incomplete", "context.incomplete")
    assert body["details"] == {"issue_count": str(incomplete_issue_count)}
    with migrated_api.session_factory() as session:
        stored = session.get(CourseContextVersion, incomplete_id)
        assert stored.teacher_review_status is TeacherReviewStatus.DRAFT
        assert stored.submitted_at is None
        assert CurriculumRepository(session).list_review_events(incomplete_id) == []

    _, context_id, _ = complete_context_setup(migrated_api)
    submit_response = migrated_api.client.post(
        f"/api/v1/teacher/contexts/{context_id}/submit-for-review",
        json={"reviewer_note": "Ready for review."},
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()["data"]
    assert submitted["context"]["teacher_review_status"] == TeacherReviewStatus.NEEDS_REVIEW.value
    assert submitted["context"]["reviewer_note"] == "Ready for review."
    assert submitted["context"]["submitted_at"] is not None
    assert submitted["completeness"]["is_complete"] is True
    assert_error(
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/submit-for-review"),
        403,
        "context_not_draft",
        "context.not_draft",
    )
    returned = migrated_api.client.post(
        f"/api/v1/teacher/contexts/{context_id}/return-to-draft",
        json={"reviewer_note": "Correct the Malayalam explanation."},
    )
    assert returned.status_code == 200
    assert returned.json()["data"]["teacher_review_status"] == TeacherReviewStatus.DRAFT.value
    assert returned.json()["data"]["reviewer_note"] == "Correct the Malayalam explanation."
    with migrated_api.session_factory() as session:
        stored = session.get(CourseContextVersion, context_id)
        events = CurriculumRepository(session).list_review_events(context_id)
        assert stored.submitted_at is not None and stored.approved_at is None
        assert [event.event_type.value for event in events] == [
            "submitted_for_review",
            "returned_to_draft",
        ]
    assert_error(
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/return-to-draft"),
        409,
        "invalid_review_transition",
        "review.transition_invalid",
    )


@pytest.mark.parametrize(
    ("endpoint", "status", "code", "message_key"),
    [
        ("submit-for-review", 403, "approved_context_immutable", "context.approved_immutable"),
        ("return-to-draft", 403, "approved_context_immutable", "context.approved_immutable"),
        ("approve", 403, "approved_context_immutable", "context.approved_immutable"),
    ],
)
def test_approved_context_rejects_all_mutating_review_actions(
    migrated_api, endpoint: str, status: int, code: str, message_key: str
) -> None:
    _, context_id, _ = complete_context_setup(migrated_api, status=TeacherReviewStatus.APPROVED)
    response = migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/{endpoint}")
    assert_error(response, status, code, message_key)
    with migrated_api.session_factory() as session:
        assert CurriculumRepository(session).list_review_events(context_id) == []


def test_approval_stales_exactly_one_older_artifact_over_http(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        old = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        old.context.approved_at = datetime(2026, 7, 15, tzinfo=UTC)
        new = complete_photosynthesis_context(session, course_model=old.course, version_number=2)
        other = complete_photosynthesis_context(
            session,
            course_model=course(title="Another course"),
            version_number=1,
            status=TeacherReviewStatus.APPROVED,
        )
        eligible = generated_artifact(
            lesson_id=old.lesson.id, course_context_version_id=old.context.id
        )
        already_stale = generated_artifact(
            lesson_id=old.lesson.id,
            course_context_version_id=old.context.id,
            generation_status=ArtifactStatus.STALE,
            stale_at=datetime(2026, 7, 15, tzinfo=UTC),
            stale_reason="already_stale",
        )
        current = generated_artifact(
            lesson_id=new.lesson.id, course_context_version_id=new.context.id
        )
        other_artifact = generated_artifact(
            lesson_id=other.lesson.id, course_context_version_id=other.context.id
        )
        session.add_all([eligible, already_stale, current, other_artifact])
        session.commit()
        new_id = new.context.id
        artifact_ids = (eligible.id, already_stale.id, current.id, other_artifact.id)

    assert (
        migrated_api.client.post(f"/api/v1/teacher/contexts/{new_id}/submit-for-review").status_code
        == 200
    )
    response = migrated_api.client.post(f"/api/v1/teacher/contexts/{new_id}/approve")
    assert response.status_code == 200
    assert response.json()["data"]["newly_staled_artifact_count"] == 1
    assert (
        response.json()["data"]["context"]["teacher_review_status"]
        == TeacherReviewStatus.APPROVED.value
    )
    with migrated_api.session_factory() as session:
        eligible, already_stale, current, other_artifact = [
            session.get(GeneratedArtifact, artifact_id) for artifact_id in artifact_ids
        ]
        assert eligible.generation_status is ArtifactStatus.STALE
        assert (
            eligible.stale_reason == "course_context_superseded" and eligible.stale_at is not None
        )
        assert already_stale.stale_reason == "already_stale"
        assert current.generation_status is ArtifactStatus.READY
        assert other_artifact.generation_status is ArtifactStatus.READY
        assert [
            event.event_type.value
            for event in CurriculumRepository(session).list_review_events(new_id)
        ] == [
            "submitted_for_review",
            "approved",
        ]


def test_draft_cannot_be_approved_directly(migrated_api) -> None:
    _, context_id, _ = complete_context_setup(migrated_api)

    assert_error(
        migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/approve"),
        409,
        "invalid_review_transition",
        "review.transition_invalid",
    )
    with migrated_api.session_factory() as session:
        assert CurriculumRepository(session).list_review_events(context_id) == []


def test_approval_failure_rolls_back_and_returns_safe_500(migrated_api, monkeypatch) -> None:
    _, context_id, lesson_id = complete_context_setup(migrated_api)
    with migrated_api.session_factory() as session:
        artifact = generated_artifact(lesson_id=lesson_id, course_context_version_id=context_id)
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{context_id}/submit-for-review"
        ).status_code
        == 200
    )

    def fail_stale_lookup(*_args, **_kwargs):
        raise SQLAlchemyError("SELECT sensitive test failure")

    monkeypatch.setattr(
        CurriculumRepository,
        "find_non_stale_artifacts_from_older_approved_contexts",
        fail_stale_lookup,
    )
    response = migrated_api.client.post(f"/api/v1/teacher/contexts/{context_id}/approve")
    body = assert_error(response, 500, "INTERNAL_ERROR", "error.internal")
    assert body["details"] == {} and "sensitive test failure" not in response.text
    with migrated_api.session_factory() as session:
        context = session.get(CourseContextVersion, context_id)
        artifact = session.get(GeneratedArtifact, artifact_id)
        assert context.teacher_review_status is TeacherReviewStatus.NEEDS_REVIEW
        assert context.approved_at is None and artifact.generation_status is ArtifactStatus.READY
        assert [
            event.event_type.value
            for event in CurriculumRepository(session).list_review_events(context_id)
        ] == ["submitted_for_review"]


def test_copy_to_new_draft_and_copy_error_responses(migrated_api) -> None:
    _, source_id, _ = complete_context_setup(migrated_api, status=TeacherReviewStatus.APPROVED)
    response = migrated_api.client.post(
        f"/api/v1/teacher/contexts/{source_id}/copy-to-new-draft",
        json={"note": "Prepare revised classroom version."},
    )
    assert response.status_code == 200
    copy_data = response.json()["data"]
    assert copy_data["teacher_review_status"] == TeacherReviewStatus.DRAFT.value
    assert copy_data["version_number"] == 2
    assert copy_data["copied_from_context_version_id"] == source_id
    assert copy_data["submitted_at"] is None and copy_data["approved_at"] is None
    assert copy_data["reviewer_note"] is None
    with migrated_api.session_factory() as session:
        assert (
            session.get(CourseContextVersion, source_id).teacher_review_status
            is TeacherReviewStatus.APPROVED
        )
        events = CurriculumRepository(session).list_review_events(copy_data["id"])
        assert len(events) == 1 and events[0].event_type.value == "copied_to_new_draft"
        assert "Prepare revised classroom version." in events[0].note

    _, draft_id, _ = complete_context_setup(migrated_api)
    assert_error(
        migrated_api.client.post(f"/api/v1/teacher/contexts/{draft_id}/copy-to-new-draft"),
        422,
        "source_context_not_approved",
        "context.source_not_approved",
    )
    assert_error(
        migrated_api.client.post("/api/v1/teacher/contexts/missing/copy-to-new-draft"),
        404,
        "context_not_found",
        "context.not_found",
    )


def test_post_mutation_approval_failure_rolls_back_over_http(migrated_api, monkeypatch) -> None:
    with migrated_api.session_factory() as session:
        old = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        old.context.approved_at = datetime(2026, 7, 15, tzinfo=UTC)
        new = complete_photosynthesis_context(session, course_model=old.course, version_number=2)
        eligible = generated_artifact(
            lesson_id=old.lesson.id,
            course_context_version_id=old.context.id,
        )
        session.add(eligible)
        session.commit()
        new_context_id = new.context.id
        eligible_id = eligible.id

    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{new_context_id}/submit-for-review"
        ).status_code
        == 200
    )
    reached_post_mutation_commit = False

    def fail_after_approval_mutations(service, context):
        nonlocal reached_post_mutation_commit
        reached_post_mutation_commit = True
        artifact = service._session.get(GeneratedArtifact, eligible_id)
        assert context.teacher_review_status is TeacherReviewStatus.APPROVED
        assert context.approved_at is not None
        assert artifact.generation_status is ArtifactStatus.STALE
        assert artifact.stale_at is not None
        assert artifact.stale_reason == "course_context_superseded"
        assert any(
            event.event_type is ContextReviewEventType.APPROVED for event in service._session.new
        )
        raise SQLAlchemyError("post-mutation SELECT failure at C:\\private\\path")

    monkeypatch.setattr(TeacherReviewService, "_commit", fail_after_approval_mutations)
    response = migrated_api.client.post(f"/api/v1/teacher/contexts/{new_context_id}/approve")

    assert reached_post_mutation_commit is True
    body = assert_error(response, 500, "INTERNAL_ERROR", "error.internal")
    assert body["details"] == {}
    assert all(token not in response.text for token in ("SELECT", "private", "C:\\", "Traceback"))
    with migrated_api.session_factory() as session:
        context = session.get(CourseContextVersion, new_context_id)
        artifact = session.get(GeneratedArtifact, eligible_id)
        events = CurriculumRepository(session).list_review_events(new_context_id)
        assert context.teacher_review_status is TeacherReviewStatus.NEEDS_REVIEW
        assert context.approved_at is None
        assert artifact.generation_status is ArtifactStatus.READY
        assert artifact.stale_at is None and artifact.stale_reason is None
        assert [event.event_type.value for event in events] == ["submitted_for_review"]
