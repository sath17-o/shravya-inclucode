# ruff: noqa: F403, F405
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_completeness,
    get_repository,
    get_review,
    get_student,
    get_versioning,
)
from app.contracts.common import ErrorResponse, SuccessResponse
from app.contracts.curriculum_api import *
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import ContextCompletenessService
from app.services.context_versioning import ContextVersioningService
from app.services.student_curriculum import StudentCurriculumService
from app.services.teacher_review import TeacherReviewService

router = APIRouter(
    responses={
        403: {"model": ErrorResponse, "description": "The requested action is not permitted."},
        404: {
            "model": ErrorResponse,
            "description": "The requested curriculum record was not found.",
        },
        409: {
            "model": ErrorResponse,
            "description": "The curriculum context is in a conflicting state.",
        },
        422: {
            "model": ErrorResponse,
            "description": "The curriculum request could not be completed.",
        },
        500: {"model": ErrorResponse, "description": "An unexpected error occurred."},
    }
)


def summary(c):
    return ContextSummaryResponse.model_validate(c, from_attributes=True)


def completeness(r):
    return CompletenessResponse.model_validate(r, from_attributes=True)


def event(e):
    return ReviewEventResponse.model_validate(e, from_attributes=True)


def lesson(lesson_model):
    return LessonResponse(
        id=lesson_model.id,
        title=lesson_model.title,
        sequence=lesson_model.sequence,
        primary_language=lesson_model.primary_language,
        description=lesson_model.description,
        objectives=[
            LearningObjectiveResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.objectives, key=lambda x: (x.sequence, x.id))
        ],
        approved_materials=[
            ApprovedMaterialResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.approved_materials, key=lambda x: (x.sequence, x.id))
        ],
        glossary_terms=[
            GlossaryTermResponse(
                id=x.id,
                canonical_term=x.canonical_term,
                malayalam_support_label=x.malayalam_support_label,
                definition=x.definition,
                malayalam_explanation=x.malayalam_explanation,
                sequence=x.sequence,
                aliases=[
                    TermAliasResponse.model_validate(a, from_attributes=True)
                    for a in sorted(x.aliases, key=lambda a: (a.normalized_alias, a.id))
                ],
                misrecognitions=[
                    ASRMisrecognitionResponse.model_validate(a, from_attributes=True)
                    for a in sorted(x.misrecognitions, key=lambda a: (a.normalized_text, a.id))
                ],
            )
            for x in sorted(lesson_model.glossary_terms, key=lambda x: (x.sequence, x.id))
        ],
        concepts=[
            ConceptResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.concepts, key=lambda x: (x.sequence, x.id))
        ],
        concept_relationships=[
            ConceptRelationshipResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.concept_relationships, key=lambda x: (x.sequence, x.id))
        ],
        questions=[
            QuestionResponse.model_validate(x, from_attributes=True)
            for x in sorted(lesson_model.questions, key=lambda x: (x.sequence, x.id))
        ],
    )


def chapters(c):
    return [
        ChapterResponse(
            id=x.id,
            title=x.title,
            sequence=x.sequence,
            lessons=[lesson(y) for y in sorted(x.lessons, key=lambda y: (y.sequence, y.id))],
        )
        for x in sorted(c.chapters, key=lambda x: (x.sequence, x.id))
    ]


def student_lesson(projection):
    return StudentLessonResponse(
        id=projection.id,
        title=projection.title,
        sequence=projection.sequence,
        primary_language=projection.primary_language,
        description=projection.description,
        objectives=[
            LearningObjectiveResponse.model_validate(item, from_attributes=True)
            for item in projection.objectives
        ],
        approved_materials=[
            StudentApprovedMaterialResponse.model_validate(item, from_attributes=True)
            for item in projection.approved_materials
        ],
        glossary_terms=[
            StudentGlossaryTermResponse(
                id=item.id,
                canonical_term=item.canonical_term,
                malayalam_support_label=item.malayalam_support_label,
                definition=item.definition,
                malayalam_explanation=item.malayalam_explanation,
                sequence=item.sequence,
                aliases=[
                    StudentTermAliasResponse.model_validate(alias, from_attributes=True)
                    for alias in item.aliases
                ],
                misrecognitions=[
                    StudentASRMisrecognitionResponse.model_validate(variant, from_attributes=True)
                    for variant in item.misrecognitions
                ],
            )
            for item in projection.glossary_terms
        ],
        concepts=[
            ConceptResponse.model_validate(item, from_attributes=True)
            for item in projection.concepts
        ],
        concept_relationships=[
            StudentConceptRelationshipResponse.model_validate(item, from_attributes=True)
            for item in projection.concept_relationships
        ],
        questions=[
            StudentQuestionResponse.model_validate(item, from_attributes=True)
            for item in projection.questions
        ],
    )


def student_chapters(projections):
    return [
        StudentChapterResponse(
            id=chapter_projection.id,
            title=chapter_projection.title,
            sequence=chapter_projection.sequence,
            lessons=[
                student_lesson(lesson_projection)
                for lesson_projection in chapter_projection.lessons
            ],
        )
        for chapter_projection in projections
    ]


@router.get(
    "/teacher/courses/{course_id}/contexts",
    response_model=SuccessResponse[list[ContextSummaryResponse]],
    operation_id="list_teacher_contexts",
)
def list_contexts(course_id: str, repo: Annotated[CurriculumRepository, Depends(get_repository)]):
    if repo.get_course(course_id) is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("course_not_found", "course.not_found", "not_found")
    return SuccessResponse(data=[summary(x) for x in repo.list_context_versions(course_id)])


@router.get(
    "/teacher/contexts/{context_id}/completeness",
    response_model=SuccessResponse[CompletenessResponse],
    operation_id="get_context_completeness",
)
def get_completeness_route(
    context_id: str, service: Annotated[ContextCompletenessService, Depends(get_completeness)]
):
    return SuccessResponse(data=completeness(service.evaluate(context_id)))


@router.get(
    "/teacher/contexts/{context_id}/review-events",
    response_model=SuccessResponse[list[ReviewEventResponse]],
    operation_id="get_review_events",
)
def history(context_id: str, repo: Annotated[CurriculumRepository, Depends(get_repository)]):
    if repo.get_context_version(context_id) is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("context_not_found", "context.not_found", "not_found")
    return SuccessResponse(data=[event(x) for x in repo.list_review_events(context_id)])


@router.get(
    "/teacher/contexts/{context_id}",
    response_model=SuccessResponse[ContextDetailResponse],
    operation_id="get_teacher_context",
)
def detail(
    context_id: str,
    repo: Annotated[CurriculumRepository, Depends(get_repository)],
    service: Annotated[ContextCompletenessService, Depends(get_completeness)],
):
    c = repo.get_context_with_graph(context_id)
    if c is None:
        from app.contracts.teacher_review import DomainError

        raise DomainError("context_not_found", "context.not_found", "not_found")
    return SuccessResponse(
        data=ContextDetailResponse(
            **summary(c).model_dump(),
            chapters=chapters(c),
            completeness=completeness(service.evaluate(c.id)),
            review_events=[event(x) for x in repo.list_review_events(c.id)],
        )
    )


@router.post(
    "/teacher/contexts/{context_id}/submit-for-review",
    response_model=SuccessResponse[SubmitResponse],
    operation_id="submit_context_review",
)
def submit(
    context_id: str,
    body: ReviewNoteRequest | None = None,
    svc: Annotated[TeacherReviewService, Depends(get_review)] = None,
    complete: Annotated[ContextCompletenessService, Depends(get_completeness)] = None,
):
    c = svc.submit_for_review(context_id, reviewer_note=body.reviewer_note if body else None)
    return SuccessResponse(
        data=SubmitResponse(context=summary(c), completeness=completeness(complete.evaluate(c.id)))
    )


@router.post(
    "/teacher/contexts/{context_id}/return-to-draft",
    response_model=SuccessResponse[ContextSummaryResponse],
    operation_id="return_context_draft",
)
def return_draft(
    context_id: str,
    body: ReviewNoteRequest | None = None,
    svc: Annotated[TeacherReviewService, Depends(get_review)] = None,
):
    return SuccessResponse(
        data=summary(
            svc.return_to_draft(context_id, reviewer_note=body.reviewer_note if body else None)
        )
    )


@router.post(
    "/teacher/contexts/{context_id}/approve",
    response_model=SuccessResponse[ApprovalResponse],
    operation_id="approve_context",
)
def approve(context_id: str, svc: Annotated[TeacherReviewService, Depends(get_review)]):
    result = svc.approve_with_result(context_id)
    return SuccessResponse(
        data=ApprovalResponse(
            context=summary(result.context),
            newly_staled_artifact_count=result.newly_staled_artifact_count,
        )
    )


@router.post(
    "/teacher/contexts/{context_id}/copy-to-new-draft",
    response_model=SuccessResponse[ContextSummaryResponse],
    operation_id="copy_context_draft",
)
def copy(
    context_id: str,
    body: CopyRequest | None = None,
    svc: Annotated[ContextVersioningService, Depends(get_versioning)] = None,
):
    return SuccessResponse(
        data=summary(svc.create_draft_from_approved(context_id, note=body.note if body else None))
    )


@router.get(
    "/student/courses/{course_id}/lesson-overview",
    response_model=SuccessResponse[StudentLessonOverviewResponse],
    operation_id="student_lesson_overview",
)
def overview(
    course_id: str,
    svc: Annotated[StudentCurriculumService, Depends(get_student)],
):
    projection = svc.get_curriculum_projection(course_id)
    base = CourseResponse.model_validate(projection.course, from_attributes=True)
    return SuccessResponse(
        data=StudentLessonOverviewResponse(
            course=base,
            is_ready=projection.context is not None,
            selected_context_id=projection.context.id if projection.context else None,
            version_number=projection.context.version_number if projection.context else None,
            approved_at=projection.context.approved_at if projection.context else None,
            chapters=student_chapters(projection.chapters),
        )
    )
