from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.foundation import utcnow
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import ContextCompletenessService
from app.services.context_versioning import ContextVersioningService
from app.services.health import HealthService
from app.services.student_curriculum import StudentCurriculumService
from app.services.teacher_review import TeacherReviewService


def get_health_service(settings: Annotated[Settings, Depends(get_settings)]) -> HealthService:
    return HealthService(settings)


def get_repository(session: Annotated[Session, Depends(get_session)]) -> CurriculumRepository:
    return CurriculumRepository(session)


def get_completeness(
    repository: Annotated[CurriculumRepository, Depends(get_repository)],
) -> ContextCompletenessService:
    return ContextCompletenessService(repository)


def get_review(
    session: Annotated[Session, Depends(get_session)],
    repository: Annotated[CurriculumRepository, Depends(get_repository)],
    completeness: Annotated[ContextCompletenessService, Depends(get_completeness)],
) -> TeacherReviewService:
    return TeacherReviewService(session, repository, completeness, utcnow)


def get_versioning(
    session: Annotated[Session, Depends(get_session)],
    repository: Annotated[CurriculumRepository, Depends(get_repository)],
) -> ContextVersioningService:
    return ContextVersioningService(session, repository)


def get_student(
    repository: Annotated[CurriculumRepository, Depends(get_repository)],
) -> StudentCurriculumService:
    return StudentCurriculumService(repository)
