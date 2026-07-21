from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    ArtifactStatus,
    ConceptRelationshipType,
    ContentLanguage,
    ContextReviewEventType,
    MaterialType,
    QualityStatus,
    QuestionSourceType,
    SourceStatus,
    TeacherReviewStatus,
    UncertaintyStatus,
)
from app.models.foundation import (
    ApprovedMaterial,
    ASRMisrecognition,
    Chapter,
    Concept,
    ConceptGlossaryTermLink,
    ConceptRecoveryPack,
    ConceptRelationship,
    ContextReviewEvent,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
    TermAlias,
)
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import ContextCompletenessService


def _stable_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"shravya-photosynthesis-demo:{name}"))


COURSE_ID = _stable_id("course")
CONTEXT_V1_ID = _stable_id("context-v1")
CONTEXT_V2_ID = _stable_id("context-v2")
CHAPTER_V1_ID = _stable_id("chapter-v1")
CHAPTER_V2_ID = _stable_id("chapter-v2")
LESSON_V1_ID = _stable_id("lesson-v1")
LESSON_V2_ID = _stable_id("lesson-v2")
V1_ARTIFACT_ID = _stable_id("artifact-v1")
V1_SUBMITTED_EVENT_ID = _stable_id("v1-submitted-event")
V1_APPROVED_EVENT_ID = _stable_id("v1-approved-event")
V2_COPIED_EVENT_ID = _stable_id("v2-copied-event")

FIXED_SUBMITTED_AT = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)
FIXED_APPROVED_AT = datetime(2026, 7, 16, 9, 5, tzinfo=UTC)

GLOSSARY = (
    ("Photosynthesis", "പ്രകാശസംശ്ലേഷണം", "Plants use light to make glucose."),
    ("Chlorophyll", "ക്ലോറോഫിൽ", "The green pigment that captures light."),
    ("Chloroplast", "ക്ലോറോപ്ലാസ്റ്റ്", "The cell part where photosynthesis happens."),
    ("Stomata", "രന്ധ്രങ്ങൾ", "Tiny leaf openings for gas exchange."),
    ("Carbon dioxide", "കാർബൺ ഡൈ ഓക്സൈഡ്", "A gas plants use to make food."),
    ("Water", "ജലം", "Water reaches leaves from the roots."),
    ("Sunlight", "സൂര്യപ്രകാശം", "Energy from the Sun used by plants."),
    ("Glucose", "ഗ്ലൂക്കോസ്", "A sugar made by plants as food."),
    ("Oxygen", "ഓക്സിജൻ", "A gas released during photosynthesis."),
    ("Leaf", "ഇല", "The main plant part that makes food."),
)

CONCEPTS = (
    ("plant-inputs", "What plants need", "സസ്യങ്ങൾക്ക് വേണ്ട ഘടകങ്ങൾ"),
    ("inputs-reach-leaf", "How inputs reach the leaf", "ജലവും വാതകവും ഇലയിലെത്തുന്നത്"),
    ("sunlight-chlorophyll", "Sunlight and chlorophyll", "സൂര്യപ്രകാശത്തിന്റെയും ക്ലോറോഫിലിന്റെയും പങ്ക്"),
    ("glucose-production", "Making glucose", "ഗ്ലൂക്കോസ് നിർമ്മാണം"),
    ("oxygen-release", "Releasing oxygen", "ഓക്സിജൻ പുറത്തുവിടൽ"),
)

_EXPECTED_CONTEXT_CHILD_COUNTS = {
    CONTEXT_V1_ID: {
        "chapters": 1,
        "lessons": 1,
        "objectives": 2,
        "materials": 2,
        "glossary_terms": 10,
        "aliases": 3,
        "misrecognitions": 1,
        "concepts": 5,
        "relationships": 4,
        "questions": 3,
        "concept_glossary_term_links": 10,
        "recovery_packs": 5,
    },
    CONTEXT_V2_ID: {
        "chapters": 1,
        "lessons": 1,
        "objectives": 3,
        "materials": 2,
        "glossary_terms": 10,
        "aliases": 3,
        "misrecognitions": 1,
        "concepts": 5,
        "relationships": 4,
        "questions": 4,
        "concept_glossary_term_links": 10,
        "recovery_packs": 5,
    },
}


@dataclass(frozen=True)
class DemoSeedResult:
    course_id: str
    context_v1_id: str
    context_v2_id: str
    artifact_v1_id: str
    created: bool


class DemoFixtureConflictError(RuntimeError):
    """Raised when a stable fixture record exists but is not the locked baseline."""


def seed_photosynthesis_demo(session: Session, reset: bool = False) -> DemoSeedResult:
    """Create, reuse, or reset the deterministic Photosynthesis judge demonstration."""

    try:
        existing = session.get(Course, COURSE_ID)
        if existing is not None and not reset:
            if not _is_complete_baseline(session):
                raise DemoFixtureConflictError(
                    "Photosynthesis demo data is incomplete or conflicting. Re-run with --reset."
                )
            session.commit()
            return _result(created=False)
        if existing is not None:
            session.delete(existing)
            session.flush()
            session.expunge_all()
        _create_baseline(session)
        session.flush()
        _require_complete(session, CONTEXT_V1_ID)
        _require_complete(session, CONTEXT_V2_ID)
        session.commit()
        return _result(created=True)
    except Exception:
        session.rollback()
        raise


def _result(created: bool) -> DemoSeedResult:
    return DemoSeedResult(
        course_id=COURSE_ID,
        context_v1_id=CONTEXT_V1_ID,
        context_v2_id=CONTEXT_V2_ID,
        artifact_v1_id=V1_ARTIFACT_ID,
        created=created,
    )


def _is_complete_baseline(session: Session) -> bool:
    course = session.get(Course, COURSE_ID)
    context_v1 = session.get(CourseContextVersion, CONTEXT_V1_ID)
    context_v2 = session.get(CourseContextVersion, CONTEXT_V2_ID)
    artifact = session.get(GeneratedArtifact, V1_ARTIFACT_ID)
    if (
        course is None
        or course.title != "Class 7 Science"
        or course.subject != "Science"
        or course.class_level != 7
        or course.grade_band != "5-7"
        or context_v1 is None
        or context_v2 is None
        or artifact is None
        or context_v1.course_id != COURSE_ID
        or context_v2.course_id != COURSE_ID
        or context_v1.version_number != 1
        or context_v1.teacher_review_status is not TeacherReviewStatus.APPROVED
        or context_v1.copied_from_context_version_id is not None
        or not _timestamps_match(context_v1.submitted_at, FIXED_SUBMITTED_AT)
        or not _timestamps_match(context_v1.approved_at, FIXED_APPROVED_AT)
        or context_v1.reviewer_note is not None
        or context_v2.version_number != 2
        or context_v2.teacher_review_status is not TeacherReviewStatus.DRAFT
        or context_v2.copied_from_context_version_id != CONTEXT_V1_ID
        or context_v2.submitted_at is not None
        or context_v2.approved_at is not None
        or context_v2.reviewer_note is not None
        or artifact.course_context_version_id != CONTEXT_V1_ID
        or artifact.lesson_id != LESSON_V1_ID
        or artifact.generation_status is not ArtifactStatus.READY
        or artifact.stale_at is not None
        or artifact.stale_reason is not None
    ):
        return False

    contexts = CurriculumRepository(session).list_context_versions(COURSE_ID)
    if [context.id for context in contexts] != [CONTEXT_V1_ID, CONTEXT_V2_ID]:
        return False
    artifacts = list(
        session.scalars(
            select(GeneratedArtifact)
            .where(GeneratedArtifact.course_context_version_id.in_([CONTEXT_V1_ID, CONTEXT_V2_ID]))
            .order_by(GeneratedArtifact.id)
        )
    )
    if [candidate.id for candidate in artifacts] != [V1_ARTIFACT_ID]:
        return False

    repository = CurriculumRepository(session)
    graph_v1 = repository.get_context_with_graph(CONTEXT_V1_ID)
    graph_v2 = repository.get_context_with_graph(CONTEXT_V2_ID)
    if (
        graph_v1 is None
        or graph_v2 is None
        or not _has_expected_context_graph(
            graph_v1, CHAPTER_V1_ID, LESSON_V1_ID, _EXPECTED_CONTEXT_CHILD_COUNTS[CONTEXT_V1_ID]
        )
        or not _has_expected_context_graph(
            graph_v2, CHAPTER_V2_ID, LESSON_V2_ID, _EXPECTED_CONTEXT_CHILD_COUNTS[CONTEXT_V2_ID]
        )
        or not _has_expected_events(repository.list_review_events(CONTEXT_V1_ID), _V1_EVENTS)
        or not _has_expected_events(repository.list_review_events(CONTEXT_V2_ID), _V2_EVENTS)
    ):
        return False
    try:
        _require_complete(session, CONTEXT_V1_ID)
        _require_complete(session, CONTEXT_V2_ID)
    except DemoFixtureConflictError:
        return False
    return True


_V1_EVENTS = (
    (V1_SUBMITTED_EVENT_ID, ContextReviewEventType.SUBMITTED_FOR_REVIEW, FIXED_SUBMITTED_AT),
    (V1_APPROVED_EVENT_ID, ContextReviewEventType.APPROVED, FIXED_APPROVED_AT),
)
_V2_EVENTS = ((V2_COPIED_EVENT_ID, ContextReviewEventType.COPIED_TO_NEW_DRAFT, FIXED_APPROVED_AT),)


def _timestamps_match(value: datetime | None, expected: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC) == expected


def _has_expected_context_graph(
    context: CourseContextVersion,
    chapter_id: str,
    lesson_id: str,
    expected_counts: dict[str, int],
) -> bool:
    chapters = context.chapters
    lessons = [lesson for chapter in chapters for lesson in chapter.lessons]
    if len(chapters) != 1 or len(lessons) != 1:
        return False
    chapter, lesson = chapters[0], lessons[0]
    if chapter.id != chapter_id or chapter.context_version_id != context.id:
        return False
    if lesson.id != lesson_id or lesson.chapter_id != chapter_id:
        return False
    counts = {
        "chapters": len(chapters),
        "lessons": len(lessons),
        "objectives": len(lesson.objectives),
        "materials": len(lesson.approved_materials),
        "glossary_terms": len(lesson.glossary_terms),
        "aliases": sum(len(term.aliases) for term in lesson.glossary_terms),
        "misrecognitions": sum(len(term.misrecognitions) for term in lesson.glossary_terms),
        "concepts": len(lesson.concepts),
        "relationships": len(lesson.concept_relationships),
        "questions": len(lesson.questions),
        "concept_glossary_term_links": len(context.concept_glossary_term_links),
        "recovery_packs": len(context.recovery_packs),
    }
    expected_pack_status = (
        TeacherReviewStatus.APPROVED if context.id == CONTEXT_V1_ID else TeacherReviewStatus.DRAFT
    )
    return counts == expected_counts and all(
        pack.teacher_review_status is expected_pack_status
        and (pack.approved_at is not None) == (expected_pack_status is TeacherReviewStatus.APPROVED)
        for pack in context.recovery_packs
    )


def _has_expected_events(
    events: list[ContextReviewEvent],
    expected: tuple[tuple[str, ContextReviewEventType, datetime], ...],
) -> bool:
    return len(events) == len(expected) and all(
        event.id == event_id
        and event.event_type is event_type
        and _timestamps_match(event.created_at, created_at)
        for event, (event_id, event_type, created_at) in zip(events, expected, strict=True)
    )


def _require_complete(session: Session, context_id: str) -> None:
    result = ContextCompletenessService(CurriculumRepository(session)).evaluate(context_id)
    if not result.is_complete:
        raise DemoFixtureConflictError(
            f"Photosynthesis demo context {context_id} is incomplete; use --reset."
        )


def _create_baseline(session: Session) -> None:
    session.add(
        Course(
            id=COURSE_ID,
            title="Class 7 Science",
            subject="Science",
            class_level=7,
            grade_band="5-7",
        )
    )
    session.flush()
    session.add(
        CourseContextVersion(
            id=CONTEXT_V1_ID,
            course_id=COURSE_ID,
            version_number=1,
            teacher_review_status=TeacherReviewStatus.APPROVED,
            submitted_at=FIXED_SUBMITTED_AT,
            approved_at=FIXED_APPROVED_AT,
        )
    )
    session.flush()
    session.add(
        CourseContextVersion(
            id=CONTEXT_V2_ID,
            course_id=COURSE_ID,
            version_number=2,
            teacher_review_status=TeacherReviewStatus.DRAFT,
            copied_from_context_version_id=CONTEXT_V1_ID,
        )
    )
    session.flush()
    _add_context(session, "v1", CONTEXT_V1_ID, CHAPTER_V1_ID, LESSON_V1_ID, improved=False)
    _add_context(session, "v2", CONTEXT_V2_ID, CHAPTER_V2_ID, LESSON_V2_ID, improved=True)
    session.flush()
    session.add_all(
        [
            ContextReviewEvent(
                id=V1_SUBMITTED_EVENT_ID,
                context_version_id=CONTEXT_V1_ID,
                event_type=ContextReviewEventType.SUBMITTED_FOR_REVIEW,
                actor_role="teacher",
                note="Historical classroom review submission.",
                created_at=FIXED_SUBMITTED_AT,
            ),
            ContextReviewEvent(
                id=V1_APPROVED_EVENT_ID,
                context_version_id=CONTEXT_V1_ID,
                event_type=ContextReviewEventType.APPROVED,
                actor_role="teacher",
                note="Historical teacher approval.",
                created_at=FIXED_APPROVED_AT,
            ),
            ContextReviewEvent(
                id=V2_COPIED_EVENT_ID,
                context_version_id=CONTEXT_V2_ID,
                event_type=ContextReviewEventType.COPIED_TO_NEW_DRAFT,
                actor_role="teacher",
                note=f"copied_from:{CONTEXT_V1_ID}; improved classroom edition",
                created_at=FIXED_APPROVED_AT,
            ),
            GeneratedArtifact(
                id=V1_ARTIFACT_ID,
                lesson_id=LESSON_V1_ID,
                course_context_version_id=CONTEXT_V1_ID,
                artifact_type="layered_notes",
                provider_name="offline-demo",
                model_name=None,
                prompt_version="demo-v1",
                generated_at=FIXED_APPROVED_AT,
                source_status=SourceStatus.DEMO,
                quality_status=QualityStatus.VERIFIED,
                uncertainty_status=UncertaintyStatus.CONFIRMED,
                uncertainty_note=None,
                teacher_review_status=TeacherReviewStatus.APPROVED,
                generation_status=ArtifactStatus.READY,
                stale_at=None,
                stale_reason=None,
            ),
        ]
    )


def _add_context(
    session: Session,
    label: str,
    context_id: str,
    chapter_id: str,
    lesson_id: str,
    *,
    improved: bool,
) -> None:
    session.add_all(
        [
            Chapter(
                id=chapter_id,
                context_version_id=context_id,
                title="Nutrition in Plants",
                sequence=1,
            ),
            Lesson(
                id=lesson_id,
                chapter_id=chapter_id,
                title="Photosynthesis in Plants",
                sequence=1,
                primary_language="ml",
                description=(
                    "Green plants use sunlight, water and carbon dioxide to make glucose and "
                    "release oxygen. പച്ച സസ്യങ്ങൾ സൂര്യപ്രകാശം, ജലം, കാർബൺ ഡൈ ഓക്സൈഡ് "
                    "എന്നിവ ഉപയോഗിച്ച് ഗ്ലൂക്കോസ് നിർമ്മിച്ച് ഓക്സിജൻ പുറത്തുവിടുന്നു."
                ),
            ),
        ]
    )
    objectives = [
        (
            "Identify the inputs required for photosynthesis.",
            "പ്രകാശസംശ്ലേഷണത്തിന് ആവശ്യമായ ഘടകങ്ങളെ തിരിച്ചറിയുക.",
        ),
        (
            "Explain how sunlight and chlorophyll help plants produce glucose and release oxygen.",
            "സൂര്യപ്രകാശവും ക്ലോറോഫിലും സസ്യങ്ങളെ ഗ്ലൂക്കോസ് നിർമ്മിക്കാനും ഓക്സിജൻ "
            "പുറത്തുവിടാനും എങ്ങനെ സഹായിക്കുന്നു എന്ന് വിശദീകരിക്കുക.",
        ),
    ]
    if improved:
        objectives.append(
            (
                "Describe the photosynthesis flow from leaf inputs to oxygen release.",
                "ഇലയിലെത്തുന്ന ഘടകങ്ങളിൽ നിന്ന് ഓക്സിജൻ പുറത്തുവിടുന്നതുവരെ പ്രകാശസംശ്ലേഷണത്തിന്റെ ഒഴുക്ക് വിവരിക്കുക.",
            )
        )
    session.add_all(
        [
            LearningObjective(
                id=_stable_id(f"{label}-objective-{sequence}"),
                lesson_id=lesson_id,
                objective_text=english,
                malayalam_text=malayalam,
                sequence=sequence,
            )
            for sequence, (english, malayalam) in enumerate(objectives, 1)
        ]
    )
    materials = [
        (
            "Trusted teacher explanation" if not improved else "Improved teacher explanation",
            MaterialType.TEACHER_NOTE,
            "Teacher-approved classroom note",
            "Plants use chlorophyll to capture sunlight. Water and carbon dioxide are changed "
            "into glucose, and oxygen is released.",
            "ക്ലോറോഫിൽ സൂര്യപ്രകാശം പിടിച്ചെടുക്കാൻ സഹായിക്കുന്നു. ജലവും കാർബൺ ഡൈ "
            "ഓക്സൈഡും ഗ്ലൂക്കോസായി മാറുമ്പോൾ ഓക്സിജൻ പുറത്തുവരുന്നു.",
        ),
        (
            "Reference support",
            MaterialType.REFERENCE_TEXT,
            "Classroom reference support",
            "A leaf brings together water, carbon dioxide, sunlight and chlorophyll for "
            "photosynthesis.",
            "ഇലയിൽ ജലം, കാർബൺ ഡൈ ഓക്സൈഡ്, സൂര്യപ്രകാശം, ക്ലോറോഫിൽ എന്നിവ ചേർന്നാണ് പ്രകാശസംശ്ലേഷണം നടക്കുന്നത്.",
        ),
    ]
    session.add_all(
        [
            ApprovedMaterial(
                id=_stable_id(f"{label}-material-{sequence}"),
                lesson_id=lesson_id,
                title=title,
                material_type=material_type,
                source_label=source_label,
                content=f"{english}\n\n{malayalam}",
                language=ContentLanguage.BILINGUAL,
                sequence=sequence,
                teacher_review_status=TeacherReviewStatus.APPROVED,
            )
            for sequence, (title, material_type, source_label, english, malayalam) in enumerate(
                materials, 1
            )
        ]
    )
    glossary_ids: dict[str, str] = {}
    for sequence, (term, support_label, definition) in enumerate(GLOSSARY, 1):
        glossary_id = _stable_id(f"{label}-glossary-{sequence}")
        glossary_ids[term] = glossary_id
        session.add(
            GlossaryTerm(
                id=glossary_id,
                lesson_id=lesson_id,
                canonical_term=term,
                malayalam_support_label=support_label,
                definition=definition,
                malayalam_explanation=f"{support_label}: {definition}",
                sequence=sequence,
            )
        )
        if term in {"Photosynthesis", "Chlorophyll", "Carbon dioxide"}:
            alias = term.casefold().replace(" ", "-")
            session.add(
                TermAlias(
                    id=_stable_id(f"{label}-alias-{sequence}"),
                    glossary_term_id=glossary_id,
                    alias=alias,
                    normalized_alias=alias,
                )
            )
        if term == "Chlorophyll":
            session.add(
                ASRMisrecognition(
                    id=_stable_id(f"{label}-chlorophil"),
                    glossary_term_id=glossary_id,
                    detected_text="chlorophil",
                    normalized_text="chlorophil",
                    source_note="Classroom ASR correction.",
                )
            )
    concept_ids: list[str] = []
    for sequence, (key, title, malayalam_title) in enumerate(CONCEPTS, 1):
        concept_id = _stable_id(f"{label}-concept-{sequence}")
        concept_ids.append(concept_id)
        wording = "Improved classroom flow: " if improved else ""
        session.add(
            Concept(
                id=concept_id,
                lesson_id=lesson_id,
                context_version_id=context_id,
                concept_key=key,
                title=title,
                malayalam_title=malayalam_title,
                definition=f"{wording}{title} in photosynthesis.",
                malayalam_definition=f"{malayalam_title} എന്നത് പ്രകാശസംശ്ലേഷണത്തിലെ ഒരു പ്രധാന ഘട്ടമാണ്.",
                sequence=sequence,
            )
        )
    recovery_text = (
        (
            "Notice the words water, carbon dioxide and sunlight.",
            "ജലം, കാർബൺ ഡൈ ഓക്സൈഡ്, സൂര്യപ്രകാശം എന്നീ വാക്കുകൾ ശ്രദ്ധിക്കുക.",
            "Think of the leaf collecting what the plant needs.",
            "ചെടിക്ക് വേണ്ട ഘടകങ്ങൾ ഇലയിൽ ഒന്നിക്കുന്നതായി ചിന്തിക്കുക.",
            "Plants need water, carbon dioxide and sunlight before making food.",
            "ഭക്ഷണം നിർമ്മിക്കുന്നതിന് മുമ്പ് സസ്യങ്ങൾക്ക് ജലം, കാർബൺ ഡൈ ഓക്സൈഡ്, സൂര്യപ്രകാശം എന്നിവ വേണം.",
        ),
        (
            "Follow water travelling from the roots and carbon dioxide entering "
            "through the stomata.",
            "വേരുകളിൽ നിന്ന് ഇലയിലേക്കെത്തുന്ന ജലവും സ്റ്റോമാറ്റയിലൂടെ ഇലയിലേക്ക് കടക്കുന്ന കാർബൺ ഡൈ ഓക്സൈഡും ശ്രദ്ധിക്കുക.",
            "Water travels up from roots while carbon dioxide enters through stomata.",
            "ജലം വേരുകളിൽ നിന്ന് മുകളിലേക്ക് എത്തുന്നു; കാർബൺ ഡൈ ഓക്സൈഡ് സ്റ്റോമാറ്റയിലൂടെ അകത്ത് കടക്കുന്നു.",
            "Photosynthesis uses the water and carbon dioxide that reach the leaf.",
            "ഇലയിലെത്തുന്ന ജലവും കാർബൺ ഡൈ ഓക്സൈഡും പ്രകാശസംശ്ലേഷണത്തിൽ ഉപയോഗിക്കുന്നു.",
        ),
        (
            "Notice how chlorophyll and sunlight work together.",
            "ക്ലോറോഫിലും സൂര്യപ്രകാശവും ഒരുമിച്ച് പ്രവർത്തിക്കുന്നതു ശ്രദ്ധിക്കുക.",
            "Chlorophyll in the leaf captures energy from sunlight.",
            "ഇലയിലെ ക്ലോറോഫിൽ സൂര്യപ്രകാശത്തിൽ നിന്നുള്ള ഊർജം പിടിച്ചെടുക്കുന്നു.",
            "Sunlight provides energy, and chlorophyll in the leaf captures that energy.",
            "സൂര്യപ്രകാശം ഊർജം നൽകുന്നു; ഇലയിലെ ക്ലോറോഫിൽ ആ ഊർജം പിടിച്ചെടുക്കുന്നു.",
        ),
        (
            "Look for the food made by the plant.",
            "സസ്യം നിർമ്മിക്കുന്ന ഭക്ഷണം കണ്ടെത്തുക.",
            "The plant uses water and carbon dioxide to make glucose, a sugar it uses as food.",
            "സസ്യം ജലവും കാർബൺ ഡൈ ഓക്സൈഡും ഉപയോഗിച്ച് ഗ്ലൂക്കോസ് എന്ന പഞ്ചസാര നിർമ്മിക്കുന്നു; "
            "അത് സസ്യം ഭക്ഷണമായി ഉപയോഗിക്കുന്നു.",
            "Glucose is a sugar made during photosynthesis and used by the plant as food.",
            "പ്രകാശസംശ്ലേഷണത്തിൽ നിർമ്മിക്കുന്ന ഗ്ലൂക്കോസ് സസ്യം ഭക്ഷണമായി ഉപയോഗിക്കുന്ന ഒരു പഞ്ചസാരയാണ്.",
        ),
        (
            "Notice oxygen leaving the leaf during photosynthesis.",
            "പ്രകാശസംശ്ലേഷണത്തിനിടെ ഇലയിൽ നിന്ന് പുറത്തുവരുന്ന ഓക്സിജൻ ശ്രദ്ധിക്കുക.",
            "During photosynthesis, the leaf releases oxygen into the air.",
            "പ്രകാശസംശ്ലേഷണത്തിനിടെ ഇല ഓക്സിജൻ വായുവിലേക്ക് പുറത്തുവിടുന്നു.",
            "Oxygen is released from the leaf while the plant makes food through photosynthesis.",
            "പ്രകാശസംശ്ലേഷണത്തിലൂടെ സസ്യം ഭക്ഷണം നിർമ്മിക്കുമ്പോൾ ഇലയിൽ നിന്ന് ഓക്സിജൻ പുറത്തുവിടുന്നു.",
        ),
    )
    session.add_all(
        [
            ConceptRecoveryPack(
                id=_stable_id(f"{label}-recovery-{sequence}"),
                context_version_id=context_id,
                concept_id=concept_ids[sequence - 1],
                cue_en=cue_en,
                cue_ml=cue_ml,
                example_en=example_en,
                example_ml=example_ml,
                alternate_explanation_en=alternate_en,
                alternate_explanation_ml=alternate_ml,
                teacher_review_status=(
                    TeacherReviewStatus.DRAFT if improved else TeacherReviewStatus.APPROVED
                ),
                approved_at=(None if improved else FIXED_APPROVED_AT),
            )
            for sequence, (
                cue_en,
                cue_ml,
                example_en,
                example_ml,
                alternate_en,
                alternate_ml,
            ) in enumerate(recovery_text, 1)
        ]
    )
    concept_glossary_terms = {
        "plant-inputs": ("Carbon dioxide", "Water", "Sunlight"),
        "inputs-reach-leaf": ("Carbon dioxide", "Water", "Leaf"),
        "sunlight-chlorophyll": ("Chlorophyll", "Sunlight"),
        "glucose-production": ("Glucose",),
        "oxygen-release": ("Oxygen",),
    }
    session.add_all(
        [
            ConceptGlossaryTermLink(
                id=_stable_id(f"{label}-concept-glossary-{concept_sequence}-{term_sequence}"),
                context_version_id=context_id,
                concept_id=concept_ids[concept_sequence - 1],
                glossary_term_id=glossary_ids[term],
                sequence=term_sequence,
            )
            for concept_sequence, (concept_key, _, _) in enumerate(CONCEPTS, 1)
            for term_sequence, term in enumerate(concept_glossary_terms[concept_key], 1)
        ]
    )
    session.add_all(
        [
            ConceptRelationship(
                id=_stable_id(f"{label}-relationship-{sequence}"),
                lesson_id=lesson_id,
                source_concept_id=concept_ids[sequence - 1],
                target_concept_id=concept_ids[sequence],
                relationship_type=ConceptRelationshipType.PRECEDES,
                sequence=sequence,
            )
            for sequence in range(1, len(concept_ids))
        ]
    )
    questions = [
        (
            QuestionSourceType.TEACHER_QUESTION,
            "Teacher question",
            "What inputs do plants need for photosynthesis?",
            "പ്രകാശസംശ്ലേഷണത്തിന് സസ്യങ്ങൾക്ക് എന്തെല്ലാം ഘടകങ്ങൾ ആവശ്യമാണ്?",
            0,
            None,
            None,
        ),
        (
            QuestionSourceType.TEXTBOOK_EXERCISE,
            "Classroom exercise",
            "Why is chlorophyll important in photosynthesis?",
            "പ്രകാശസംശ്ലേഷണത്തിൽ ക്ലോറോഫിൽ എന്തുകൊണ്ട് പ്രധാനമാണ്?",
            2,
            None,
            2,
        ),
        (
            QuestionSourceType.BOARD_STYLE_QUESTION,
            "School-style practice question",
            "Explain how a leaf produces glucose and releases oxygen.",
            "ഒരു ഇല എങ്ങനെ ഗ്ലൂക്കോസ് നിർമ്മിക്കുകയും ഓക്സിജൻ പുറത്തുവിടുകയും ചെയ്യുന്നു എന്ന് വിശദീകരിക്കുക.",
            3,
            None,
            3,
        ),
    ]
    if improved:
        questions.append(
            (
                QuestionSourceType.TEACHER_QUESTION,
                "Improved classroom question",
                "Put the five photosynthesis concepts in a learning flow.",
                "പ്രകാശസംശ്ലേഷണത്തിലെ അഞ്ച് ആശയങ്ങളെ പഠന ഒഴുക്കിൽ ക്രമീകരിക്കുക.",
                4,
                None,
                3,
            )
        )
    session.add_all(
        [
            QuestionItem(
                id=_stable_id(f"{label}-question-{sequence}"),
                lesson_id=lesson_id,
                related_concept_id=concept_ids[concept_index],
                source_type=source_type,
                source_label=source_label,
                question_text=question_text,
                malayalam_question_text=malayalam_question,
                sequence=sequence,
                year=year,
                marks=marks,
                teacher_review_status=TeacherReviewStatus.APPROVED,
            )
            for sequence, (
                source_type,
                source_label,
                question_text,
                malayalam_question,
                concept_index,
                year,
                marks,
            ) in enumerate(questions, 1)
        ]
    )
