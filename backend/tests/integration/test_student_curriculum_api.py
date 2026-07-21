import re
from datetime import UTC, datetime

import pytest

from app.contracts.enums import TeacherReviewStatus
from tests.integration.factories import (
    approved_material,
    complete_photosynthesis_context,
    context_version,
    course,
    question_item,
)


def assert_forbidden_keys_absent(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value)
        for child in value.values():
            assert_forbidden_keys_absent(child, forbidden)
    elif isinstance(value, list):
        for child in value:
            assert_forbidden_keys_absent(child, forbidden)


def setup_contexts_for_selection(migrated_api, second_status: TeacherReviewStatus):
    with migrated_api.session_factory() as session:
        first = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        first.context.created_at = datetime(2026, 7, 18, tzinfo=UTC)
        first.context.approved_at = datetime(2026, 7, 18, tzinfo=UTC)
        second = complete_photosynthesis_context(
            session,
            course_model=first.course,
            version_number=2,
            status=second_status,
        )
        second.context.created_at = datetime(2026, 7, 15, tzinfo=UTC)
        if second_status is TeacherReviewStatus.APPROVED:
            second.context.approved_at = datetime(2026, 7, 15, tzinfo=UTC)
        session.add_all(
            [
                approved_material(
                    lesson=second.lesson,
                    title="Draft material must not leak",
                    sequence=2,
                    teacher_review_status=TeacherReviewStatus.DRAFT,
                ),
                question_item(
                    lesson=second.lesson,
                    question_text="Draft question must not leak",
                    sequence=2,
                    teacher_review_status=TeacherReviewStatus.DRAFT,
                ),
            ]
        )
        other = complete_photosynthesis_context(
            session,
            course_model=course(title="Other course marker"),
            version_number=1,
            status=TeacherReviewStatus.APPROVED,
        )
        other.context.approved_at = datetime(2026, 7, 16, tzinfo=UTC)
        session.commit()
        return first.course.id, first.context.id, second.context.id, other.context.id


def test_student_unknown_course_has_a_safe_not_found_error(migrated_api) -> None:
    response = migrated_api.client.get("/api/v1/student/courses/missing/lesson-overview")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "course_not_found"
    assert body["message_key"] == "course.not_found"
    assert isinstance(body["details"], dict)


@pytest.mark.parametrize("status", [TeacherReviewStatus.DRAFT, TeacherReviewStatus.NEEDS_REVIEW])
def test_student_returns_the_typed_not_ready_shape_without_an_approved_context(
    migrated_api, status
) -> None:
    with migrated_api.session_factory() as session:
        course_model = course(title=f"{status.value} only")
        context = context_version(course=course_model, teacher_review_status=status)
        session.add_all([course_model, context])
        session.commit()
        course_id = course_model.id

    response = migrated_api.client.get(f"/api/v1/student/courses/{course_id}/lesson-overview")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "course": {
            "id": course_id,
            "title": f"{status.value} only",
            "subject": "Science",
            "class_level": 7,
            "grade_band": "5-7",
        },
        "is_ready": False,
        "selected_context_id": None,
        "version_number": None,
        "approved_at": None,
        "chapters": [],
    }


@pytest.mark.parametrize(
    ("second_status", "expected_version"),
    [
        (TeacherReviewStatus.DRAFT, 1),
        (TeacherReviewStatus.NEEDS_REVIEW, 1),
        (TeacherReviewStatus.APPROVED, 2),
    ],
)
def test_student_selects_by_highest_approved_version_not_timestamps(
    migrated_api, second_status: TeacherReviewStatus, expected_version: int
) -> None:
    course_id, first_id, second_id, _ = setup_contexts_for_selection(migrated_api, second_status)

    response = migrated_api.client.get(f"/api/v1/student/courses/{course_id}/lesson-overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version_number"] == expected_version
    assert data["selected_context_id"] == (second_id if expected_version == 2 else first_id)


def test_student_filters_unapproved_children_and_prevents_context_and_teacher_leakage(
    migrated_api,
) -> None:
    course_id, first_id, second_id, other_id = setup_contexts_for_selection(
        migrated_api, TeacherReviewStatus.APPROVED
    )

    response = migrated_api.client.get(f"/api/v1/student/courses/{course_id}/lesson-overview")

    assert response.status_code == 200
    data = response.json()["data"]
    lesson = data["chapters"][0]["lessons"][0]
    assert data["selected_context_id"] == second_id
    assert [item["title"] for item in lesson["approved_materials"]] == ["Teacher-approved source"]
    assert [item["question_text"] for item in lesson["questions"]] == [
        "What do plants need for photosynthesis?"
    ]
    assert lesson["glossary_terms"][0]["malayalam_support_label"] == "പ്രകാശസംശ്ലേഷണം"
    assert lesson["glossary_terms"][1]["malayalam_support_label"] == "ക്ലോറോഫിൽ"
    assert lesson["glossary_terms"][1]["canonical_term"] == "Chlorophyll"
    assert lesson["glossary_terms"][0]["aliases"]
    assert "misrecognitions" not in lesson["glossary_terms"][1]
    assert lesson["glossary_terms"][0]["concept_ids"] == [lesson["concepts"][0]["id"]]
    assert_forbidden_keys_absent(
        data,
        {
            "reviewer_note",
            "review_events",
            "submitted_at",
            "copied_from_context_version_id",
            "teacher_review_status",
            "stale_reason",
            "stale_at",
            "generated_artifacts",
            "teacher_note",
            "source_note",
        },
    )
    serialized = response.text
    assert first_id not in serialized
    assert other_id not in serialized
    assert "Other course marker" not in serialized
    assert re.search(r"\bchlorophil\b", serialized) is None
