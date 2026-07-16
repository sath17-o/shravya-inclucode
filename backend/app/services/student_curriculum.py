from __future__ import annotations

from app.contracts.teacher_review import DomainError
from app.models.foundation import CourseContextVersion, Lesson
from app.repositories.curriculum import CurriculumRepository


class StudentCurriculumService:
    def __init__(self, repository: CurriculumRepository) -> None:
        self._repository = repository

    def get_current_context(self, course_id: str) -> CourseContextVersion | None:
        if self._repository.get_course(course_id) is None:
            raise DomainError("course_not_found", "course.not_found", "not_found")
        return self._repository.get_highest_approved_context(course_id)

    def list_current_lessons(self, course_id: str) -> list[Lesson]:
        if self._repository.get_course(course_id) is None:
            raise DomainError("course_not_found", "course.not_found", "not_found")
        return self._repository.list_student_visible_approved_lessons(course_id)
