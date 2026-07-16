from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

import scripts.seed_photosynthesis_demo as seed_cli
from app.contracts.enums import ArtifactStatus, ContextReviewEventType, TeacherReviewStatus
from app.demo.photosynthesis_fixture import (
    CONTEXT_V1_ID,
    CONTEXT_V2_ID,
    COURSE_ID,
    FIXED_APPROVED_AT,
    LESSON_V1_ID,
    V1_APPROVED_EVENT_ID,
    V1_ARTIFACT_ID,
    V1_SUBMITTED_EVENT_ID,
    V2_COPIED_EVENT_ID,
    DemoFixtureConflictError,
    seed_photosynthesis_demo,
)
from app.models.foundation import (
    Chapter,
    ContextReviewEvent,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
)
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import ContextCompletenessService
from tests.integration.factories import complete_photosynthesis_context, generated_artifact


def _demo_counts(session) -> dict[str, int]:
    return {
        "contexts": session.scalar(
            select(func.count())
            .select_from(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "chapters": session.scalar(
            select(func.count())
            .select_from(Chapter)
            .join(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "lessons": session.scalar(
            select(func.count())
            .select_from(Lesson)
            .join(Chapter)
            .join(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "objectives": session.scalar(
            select(func.count())
            .select_from(LearningObjective)
            .join(Lesson)
            .join(Chapter)
            .join(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "glossary": session.scalar(
            select(func.count())
            .select_from(GlossaryTerm)
            .join(Lesson)
            .join(Chapter)
            .join(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "questions": session.scalar(
            select(func.count())
            .select_from(QuestionItem)
            .join(Lesson)
            .join(Chapter)
            .join(CourseContextVersion)
            .where(CourseContextVersion.course_id == COURSE_ID)
        ),
        "artifacts": session.scalar(
            select(func.count())
            .select_from(GeneratedArtifact)
            .where(GeneratedArtifact.course_context_version_id.in_([CONTEXT_V1_ID, CONTEXT_V2_ID]))
        ),
        "events": session.scalar(
            select(func.count())
            .select_from(ContextReviewEvent)
            .where(ContextReviewEvent.context_version_id.in_([CONTEXT_V1_ID, CONTEXT_V2_ID]))
        ),
    }


def _assert_conflict_then_reset(session) -> None:
    with pytest.raises(DemoFixtureConflictError, match="--reset"):
        seed_photosynthesis_demo(session)
    restored = seed_photosynthesis_demo(session, reset=True)
    assert restored.created is True
    assert _demo_counts(session) == {
        "contexts": 2,
        "chapters": 2,
        "lessons": 2,
        "objectives": 5,
        "glossary": 20,
        "questions": 7,
        "artifacts": 1,
        "events": 3,
    }


def test_photosynthesis_demo_seed_reuse_reset_and_unrelated_data(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        first = seed_photosynthesis_demo(session)
        counts = _demo_counts(session)
        assert first.created is True
        assert counts == {
            "contexts": 2,
            "chapters": 2,
            "lessons": 2,
            "objectives": 5,
            "glossary": 20,
            "questions": 7,
            "artifacts": 1,
            "events": 3,
        }
        school_style_question = session.scalar(
            select(QuestionItem).where(
                QuestionItem.lesson_id == LESSON_V1_ID,
                QuestionItem.source_label == "School-style practice question",
            )
        )
        assert school_style_question is not None
        assert school_style_question.year is None
        assert (
            ContextCompletenessService(CurriculumRepository(session))
            .evaluate(CONTEXT_V1_ID)
            .is_complete
        )
        assert (
            ContextCompletenessService(CurriculumRepository(session))
            .evaluate(CONTEXT_V2_ID)
            .is_complete
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ContextReviewEvent)
                .where(ContextReviewEvent.context_version_id == CONTEXT_V1_ID)
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ContextReviewEvent)
                .where(ContextReviewEvent.context_version_id == CONTEXT_V2_ID)
            )
            == 1
        )

        unrelated = complete_photosynthesis_context(session)
        unrelated_artifact = generated_artifact(
            lesson_id=unrelated.lesson.id,
            course_context_version_id=unrelated.context.id,
        )
        session.add(unrelated_artifact)
        session.commit()
        unrelated_course_id, unrelated_artifact_id = unrelated.course.id, unrelated_artifact.id

        reused = seed_photosynthesis_demo(session)
        assert reused.created is False
        assert _demo_counts(session) == counts

        reset = seed_photosynthesis_demo(session, reset=True)
        assert reset.created is True
        assert (
            reset.course_id,
            reset.context_v1_id,
            reset.context_v2_id,
            reset.artifact_v1_id,
        ) == (
            COURSE_ID,
            CONTEXT_V1_ID,
            CONTEXT_V2_ID,
            V1_ARTIFACT_ID,
        )
        assert session.get(Course, unrelated_course_id) is not None
        assert session.get(GeneratedArtifact, unrelated_artifact_id) is not None
        assert _demo_counts(session) == counts
        assert (
            session.get(CourseContextVersion, CONTEXT_V1_ID).teacher_review_status
            is TeacherReviewStatus.APPROVED
        )
        assert (
            session.get(CourseContextVersion, CONTEXT_V2_ID).teacher_review_status
            is TeacherReviewStatus.DRAFT
        )
        artifact = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
        assert artifact.generation_status is ArtifactStatus.READY
        assert artifact.stale_at is None and artifact.stale_reason is None
        assert (
            ContextCompletenessService(CurriculumRepository(session))
            .evaluate(CONTEXT_V1_ID)
            .is_complete
        )
        assert (
            ContextCompletenessService(CurriculumRepository(session))
            .evaluate(CONTEXT_V2_ID)
            .is_complete
        )


def test_photosynthesis_demo_judge_switch_smoke(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)

    baseline = migrated_api.client.get(f"/api/v1/student/courses/{COURSE_ID}/lesson-overview")
    assert baseline.status_code == 200
    assert baseline.json()["data"]["selected_context_id"] == CONTEXT_V1_ID
    assert baseline.json()["data"]["version_number"] == 1
    assert "Improved teacher explanation" not in baseline.text
    assert "പ്രകാശസംശ്ലേഷണം" in baseline.text and "ക്ലോറോഫിൽ" in baseline.text
    baseline_lesson = baseline.json()["data"]["chapters"][0]["lessons"][0]
    assert baseline_lesson["objectives"][0]["malayalam_text"] == (
        "പ്രകാശസംശ്ലേഷണത്തിന് ആവശ്യമായ ഘടകങ്ങളെ തിരിച്ചറിയുക."
    )
    assert baseline_lesson["concepts"][0]["malayalam_definition"] == (
        "സസ്യങ്ങൾക്ക് വേണ്ട ഘടകങ്ങൾ എന്നത് പ്രകാശസംശ്ലേഷണത്തിലെ ഒരു പ്രധാന ഘട്ടമാണ്."
    )
    assert baseline_lesson["questions"][0]["malayalam_question_text"] == (
        "പ്രകാശസംശ്ലേഷണത്തിന് സസ്യങ്ങൾക്ക് എന്തെല്ലാം ഘടകങ്ങൾ ആവശ്യമാണ്?"
    )

    detail = migrated_api.client.get(f"/api/v1/teacher/contexts/{CONTEXT_V2_ID}")
    assert detail.status_code == 200
    assert detail.json()["data"]["completeness"]["is_complete"] is True
    assert (
        migrated_api.client.post(
            f"/api/v1/teacher/contexts/{CONTEXT_V2_ID}/submit-for-review"
        ).status_code
        == 200
    )
    approval = migrated_api.client.post(f"/api/v1/teacher/contexts/{CONTEXT_V2_ID}/approve")
    assert approval.status_code == 200
    assert approval.json()["data"]["newly_staled_artifact_count"] == 1

    switched = migrated_api.client.get(f"/api/v1/student/courses/{COURSE_ID}/lesson-overview")
    assert switched.status_code == 200
    assert switched.json()["data"]["selected_context_id"] == CONTEXT_V2_ID
    assert switched.json()["data"]["version_number"] == 2
    assert "Improved teacher explanation" in switched.text
    with migrated_api.session_factory() as session:
        artifact = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
        assert artifact.generation_status is ArtifactStatus.STALE
        assert artifact.stale_reason == "course_context_superseded"
        seed_photosynthesis_demo(session, reset=True)
        restored = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
        assert restored.generation_status is ArtifactStatus.READY
        assert restored.stale_at is None and restored.stale_reason is None

    restored_response = migrated_api.client.get(
        f"/api/v1/student/courses/{COURSE_ID}/lesson-overview"
    )
    assert restored_response.status_code == 200
    assert restored_response.json()["data"]["selected_context_id"] == CONTEXT_V1_ID


def test_non_reset_seed_rejects_returned_draft_history_and_reset_restores(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        session.add_all(
            [
                ContextReviewEvent(
                    id="00000000-0000-0000-0000-000000000001",
                    context_version_id=CONTEXT_V2_ID,
                    event_type=ContextReviewEventType.SUBMITTED_FOR_REVIEW,
                    actor_role="teacher",
                    created_at=FIXED_APPROVED_AT,
                ),
                ContextReviewEvent(
                    id="00000000-0000-0000-0000-000000000002",
                    context_version_id=CONTEXT_V2_ID,
                    event_type=ContextReviewEventType.RETURNED_TO_DRAFT,
                    actor_role="teacher",
                    created_at=datetime(2026, 7, 16, 9, 6, tzinfo=UTC),
                ),
            ]
        )
        session.commit()
        _assert_conflict_then_reset(session)

        events = session.scalars(
            select(ContextReviewEvent)
            .where(ContextReviewEvent.context_version_id == CONTEXT_V2_ID)
            .order_by(ContextReviewEvent.created_at, ContextReviewEvent.id)
        ).all()
        assert [event.id for event in events] == [V2_COPIED_EVENT_ID]


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("missing_review_event", id="missing-review-event"),
        pytest.param("extra_review_event", id="extra-review-event"),
        pytest.param("artifact_not_ready", id="artifact-not-ready"),
        pytest.param("artifact_stale_fields", id="artifact-stale-fields"),
        pytest.param("course_metadata", id="course-metadata"),
    ],
)
def test_non_reset_seed_rejects_modified_baseline_and_reset_restores(
    migrated_api, mutation: str
) -> None:
    with migrated_api.session_factory() as session:
        seed_photosynthesis_demo(session, reset=True)
        if mutation == "missing_review_event":
            session.delete(session.get(ContextReviewEvent, V1_APPROVED_EVENT_ID))
        elif mutation == "extra_review_event":
            session.add(
                ContextReviewEvent(
                    id="00000000-0000-0000-0000-000000000003",
                    context_version_id=CONTEXT_V1_ID,
                    event_type=ContextReviewEventType.APPROVED,
                    actor_role="teacher",
                    created_at=datetime(2026, 7, 16, 9, 7, tzinfo=UTC),
                )
            )
        elif mutation == "artifact_not_ready":
            session.get(GeneratedArtifact, V1_ARTIFACT_ID).generation_status = ArtifactStatus.FAILED
        elif mutation == "artifact_stale_fields":
            artifact = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
            artifact.stale_at = FIXED_APPROVED_AT
            artifact.stale_reason = "tampered"
        else:
            session.get(Course, COURSE_ID).title = "Changed Class 7 Science"
        session.commit()
        _assert_conflict_then_reset(session)

        assert session.get(ContextReviewEvent, V1_SUBMITTED_EVENT_ID) is not None
        assert session.get(ContextReviewEvent, V1_APPROVED_EVENT_ID) is not None
        artifact = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
        assert artifact.generation_status is ArtifactStatus.READY
        assert artifact.stale_at is None and artifact.stale_reason is None
        assert session.get(Course, COURSE_ID).title == "Class 7 Science"


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _FakeSession:
    def close(self) -> None:
        pass


def _patch_cli_database(monkeypatch: pytest.MonkeyPatch) -> _FakeEngine:
    engine = _FakeEngine()
    monkeypatch.setattr(seed_cli, "create_db_engine", lambda _url: engine)
    monkeypatch.setattr(seed_cli, "_at_alembic_head", lambda _engine: True)
    monkeypatch.setattr(seed_cli, "sessionmaker", lambda **_kwargs: _FakeSession)
    return engine


def test_demo_cli_requires_database_at_alembic_head(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    engine = _FakeEngine()
    monkeypatch.setattr(seed_cli, "create_db_engine", lambda _url: engine)
    monkeypatch.setattr(seed_cli, "_at_alembic_head", lambda _engine: False)

    assert seed_cli.main([]) == 1
    captured = capsys.readouterr()
    assert "Database is not at Alembic head" in captured.err
    assert "python -m alembic upgrade head" in captured.err
    assert captured.out == ""
    assert engine.disposed is True


def test_demo_cli_reports_fixture_conflicts_without_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _patch_cli_database(monkeypatch)

    def raise_conflict(_session, *, reset: bool):
        raise DemoFixtureConflictError("SELECT password FROM C:\\private\\demo.db")

    monkeypatch.setattr(seed_cli, "seed_photosynthesis_demo", raise_conflict)
    assert seed_cli.main([]) == 1
    captured = capsys.readouterr()
    assert captured.err == "Demo baseline conflict. Re-run this command with --reset.\n"
    assert "SELECT" not in captured.err and "C:\\private" not in captured.err


def test_demo_cli_hides_unexpected_error_details(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _patch_cli_database(monkeypatch)

    def raise_unexpected(_session, *, reset: bool):
        raise RuntimeError("SELECT * FROM secrets at C:\\private\\demo.db password=hidden")

    monkeypatch.setattr(seed_cli, "seed_photosynthesis_demo", raise_unexpected)
    assert seed_cli.main([]) == 1
    captured = capsys.readouterr()
    assert captured.err == "Demo setup failed. Check database setup and try again.\n"
    assert "SELECT" not in captured.err
    assert "C:\\private" not in captured.err
    assert "password" not in captured.err


@pytest.mark.parametrize("created", [True, False])
def test_demo_cli_reports_created_and_reused_baselines(
    monkeypatch: pytest.MonkeyPatch, capsys, created: bool
) -> None:
    _patch_cli_database(monkeypatch)
    monkeypatch.setattr(
        seed_cli,
        "seed_photosynthesis_demo",
        lambda _session, *, reset: type(
            "SeedResult",
            (),
            {
                "course_id": COURSE_ID,
                "context_v1_id": CONTEXT_V1_ID,
                "context_v2_id": CONTEXT_V2_ID,
                "created": created,
            },
        )(),
    )

    assert seed_cli.main(["--reset"] if created else []) == 0
    captured = capsys.readouterr()
    assert "Shravya Photosynthesis demo ready" in captured.out
    assert f"Fixture: {'created' if created else 'reused'}" in captured.out
    assert captured.err == ""
