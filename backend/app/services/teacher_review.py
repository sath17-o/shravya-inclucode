from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.enums import ArtifactStatus, ContextReviewEventType, TeacherReviewStatus
from app.contracts.teacher_review import ContextCompletenessResult, DomainError
from app.models.foundation import ContextReviewEvent, CourseContextVersion
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import ContextCompletenessService


def assert_context_mutable(context: CourseContextVersion) -> None:
    if context.teacher_review_status is TeacherReviewStatus.APPROVED:
        raise DomainError("approved_context_immutable", "context.approved_immutable", "forbidden")
    if context.teacher_review_status is not TeacherReviewStatus.DRAFT:
        raise DomainError("context_not_draft", "context.not_draft", "forbidden")


class TeacherReviewService:
    def __init__(
        self,
        session: Session,
        repository: CurriculumRepository,
        completeness: ContextCompletenessService,
        now: Callable[[], datetime],
    ) -> None:
        self._session = session
        self._repository = repository
        self._completeness = completeness
        self._now = now

    def submit_for_review(
        self, context_version_id: str, actor_role: str = "teacher", reviewer_note: str | None = None
    ) -> CourseContextVersion:
        try:
            context = self._context(context_version_id)
            assert_context_mutable(context)
            self._require_complete(self._completeness.evaluate(context_version_id))
            context.teacher_review_status = TeacherReviewStatus.NEEDS_REVIEW
            context.submitted_at = self._now()
            if reviewer_note is not None:
                context.reviewer_note = reviewer_note
            self._repository.add_review_event(
                ContextReviewEvent(
                    context_version_id=context.id,
                    event_type=ContextReviewEventType.SUBMITTED_FOR_REVIEW,
                    actor_role=actor_role,
                    note=reviewer_note,
                )
            )
            return self._commit(context)
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def return_to_draft(
        self, context_version_id: str, actor_role: str = "teacher", reviewer_note: str | None = None
    ) -> CourseContextVersion:
        try:
            context = self._context(context_version_id)
            if context.teacher_review_status is TeacherReviewStatus.APPROVED:
                raise DomainError(
                    "approved_context_immutable", "context.approved_immutable", "forbidden"
                )
            if context.teacher_review_status is not TeacherReviewStatus.NEEDS_REVIEW:
                raise DomainError(
                    "invalid_review_transition", "review.transition_invalid", "conflict"
                )
            context.teacher_review_status = TeacherReviewStatus.DRAFT
            if reviewer_note is not None:
                context.reviewer_note = reviewer_note
            self._repository.add_review_event(
                ContextReviewEvent(
                    context_version_id=context.id,
                    event_type=ContextReviewEventType.RETURNED_TO_DRAFT,
                    actor_role=actor_role,
                    note=reviewer_note,
                )
            )
            return self._commit(context)
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def approve(self, context_version_id: str, actor_role: str = "teacher") -> CourseContextVersion:
        try:
            context = self._context(context_version_id)
            if context.teacher_review_status is TeacherReviewStatus.APPROVED:
                raise DomainError(
                    "approved_context_immutable", "context.approved_immutable", "forbidden"
                )
            if context.teacher_review_status is not TeacherReviewStatus.NEEDS_REVIEW:
                raise DomainError(
                    "invalid_review_transition", "review.transition_invalid", "conflict"
                )
            self._require_complete(self._completeness.evaluate(context_version_id))
            approved_at = self._now()
            context.teacher_review_status = TeacherReviewStatus.APPROVED
            context.approved_at = approved_at
            for artifact in self._repository.find_non_stale_artifacts_from_older_approved_contexts(
                context.course_id, context.version_number
            ):
                artifact.generation_status = ArtifactStatus.STALE
                artifact.stale_at = approved_at
                artifact.stale_reason = "course_context_superseded"
            self._repository.add_review_event(
                ContextReviewEvent(
                    context_version_id=context.id,
                    event_type=ContextReviewEventType.APPROVED,
                    actor_role=actor_role,
                )
            )
            return self._commit(context)
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def _context(self, context_version_id: str) -> CourseContextVersion:
        context = self._repository.get_context_version(context_version_id)
        if context is None:
            raise DomainError("context_not_found", "context.not_found", "not_found")
        return context

    @staticmethod
    def _require_complete(result: ContextCompletenessResult) -> None:
        if not result.is_complete:
            raise DomainError(
                "context_incomplete",
                "context.incomplete",
                "validation",
                {"issue_count": str(len(result.issues))},
            )

    def _commit(self, context: CourseContextVersion) -> CourseContextVersion:
        self._session.commit()
        return context
