from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.contracts.enums import (
    ArtifactStatus,
    QualityStatus,
    SourceStatus,
    TeacherReviewStatus,
    UncertaintyStatus,
)
from app.models.foundation import (
    ArtifactSourceConcept,
    Chapter,
    Concept,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    LearningSession,
    LectureAudio,
    LocalLearnerProfile,
    TermSuggestion,
    TranscriptRevision,
    TranscriptSegment,
)


def create_lesson_graph(database_session):
    course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    database_session.add(course)
    database_session.flush()
    context = CourseContextVersion(course_id=course.id, version_number=1)
    database_session.add(context)
    database_session.flush()
    chapter = Chapter(context_version_id=context.id, title="Plants", sequence=1)
    database_session.add(chapter)
    database_session.flush()
    from app.models.foundation import Lesson

    lesson = Lesson(chapter_id=chapter.id, title="Photosynthesis in Plants", sequence=1)
    database_session.add(lesson)
    database_session.commit()
    return course, context, chapter, lesson


def test_uuid_identifiers_are_created_by_default(database_session) -> None:
    course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    database_session.add(course)
    database_session.commit()

    assert len(course.id) == 36


def test_database_checks_and_unique_constraints_reject_invalid_values(database_session) -> None:
    database_session.add(
        Course(title="Invalid", subject="Science", class_level=4, grade_band="5-7")
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Expected class-level check constraint to reject Class 4")

    for class_level, grade_band in ((7, "8-10"), (9, "5-7"), (7, "unknown")):
        database_session.add(
            Course(
                title=f"Invalid {class_level} {grade_band}",
                subject="Science",
                class_level=class_level,
                grade_band=grade_band,
            )
        )
        try:
            database_session.commit()
        except IntegrityError:
            database_session.rollback()
        else:
            raise AssertionError(
                "Expected course grade-band consistency constraint to reject mismatch"
            )

    database_session.add(
        Course(title="Valid senior", subject="Science", class_level=8, grade_band="8-10")
    )
    database_session.commit()

    course, context, _, lesson = create_lesson_graph(database_session)
    database_session.add(Chapter(context_version_id=context.id, title="Duplicate", sequence=1))
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Expected chapter sequence uniqueness to reject a duplicate")

    audio = LectureAudio(
        lesson_id=lesson.id,
        storage_path="demo.mp3",
        mime_type="audio/mpeg",
        source_status=SourceStatus.DEMO,
    )
    database_session.add(audio)
    database_session.flush()
    revision = TranscriptRevision(
        lecture_audio_id=audio.id,
        revision_number=1,
        source_status=SourceStatus.DEMO,
    )
    database_session.add(revision)
    database_session.flush()
    database_session.add(
        TranscriptSegment(
            transcript_revision_id=revision.id,
            sequence=1,
            start_ms=10,
            end_ms=10,
            text="invalid range",
            confidence=1.2,
        )
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Expected transcript range/confidence checks to reject invalid data")


def test_foreign_key_constraints_and_cascade_deletion_are_enforced(database_session) -> None:
    database_session.add(CourseContextVersion(course_id="missing-course", version_number=1))
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError(
            "Expected SQLite foreign-key enforcement to reject an orphan context version"
        )

    course, _, _, lesson = create_lesson_graph(database_session)
    audio = LectureAudio(
        lesson_id=lesson.id,
        storage_path="owned.mp3",
        mime_type="audio/mpeg",
        source_status=SourceStatus.DEMO,
    )
    database_session.add(audio)
    database_session.flush()
    revision = TranscriptRevision(
        lecture_audio_id=audio.id,
        revision_number=1,
        source_status=SourceStatus.DEMO,
    )
    database_session.add(revision)
    database_session.flush()
    segment = TranscriptSegment(
        transcript_revision_id=revision.id,
        sequence=1,
        start_ms=0,
        end_ms=1000,
        text="Plants use sunlight.",
        confidence=0.9,
    )
    database_session.add(segment)
    profile = LocalLearnerProfile(local_key="local-demo")
    database_session.add(profile)
    database_session.flush()
    database_session.add(
        LearningSession(
            learner_profile_id=profile.id, lesson_id=lesson.id, current_route="/learning-home"
        )
    )
    database_session.commit()
    revision_id = revision.id
    segment_id = segment.id

    database_session.delete(audio)
    database_session.commit()
    assert (
        database_session.scalar(
            select(TranscriptRevision).where(TranscriptRevision.id == revision_id)
        )
        is None
    )
    assert (
        database_session.scalar(select(TranscriptSegment).where(TranscriptSegment.id == segment_id))
        is None
    )
    assert database_session.scalar(select(Course).where(Course.id == course.id)) is not None
    assert (
        database_session.scalar(
            select(LearningSession).where(LearningSession.lesson_id == lesson.id)
        )
        is not None
    )

    database_session.delete(profile)
    database_session.commit()
    assert (
        database_session.scalar(
            select(LearningSession).where(LearningSession.lesson_id == lesson.id)
        )
        is None
    )
    assert database_session.scalar(select(Course).where(Course.id == course.id)) is not None


def test_generated_artifact_requires_explicit_trust_state_and_uses_safe_defaults(
    database_session,
) -> None:
    _, context, _, lesson = create_lesson_graph(database_session)
    database_session.add(
        LectureAudio(lesson_id=lesson.id, storage_path="missing.mp3", mime_type="audio/mpeg")
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Lecture audio must require an explicit source status")

    artifact = GeneratedArtifact(
        lesson_id=lesson.id,
        course_context_version_id=context.id,
        artifact_type="layered-content",
        provider_name="demo-fixture",
        source_status=SourceStatus.DEMO,
        quality_status=QualityStatus.VERIFIED,
        uncertainty_status=UncertaintyStatus.CONFIRMED,
    )
    database_session.add(artifact)
    database_session.commit()

    assert artifact.teacher_review_status is TeacherReviewStatus.DRAFT
    assert artifact.generation_status is ArtifactStatus.BLOCKED_BY_QUALITY

    database_session.add(
        GeneratedArtifact(
            lesson_id=lesson.id,
            course_context_version_id=context.id,
            artifact_type="missing-trust",
            provider_name="demo-fixture",
            quality_status=QualityStatus.VERIFIED,
        )
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Generated artifacts must require source and uncertainty status")


def test_sqlite_rejects_invalid_enum_values_and_duplicate_provenance(database_session) -> None:
    _, context, _, lesson = create_lesson_graph(database_session)
    try:
        database_session.execute(
            text(
                "INSERT INTO lecture_audio ("
                "id, created_at, updated_at, lesson_id, storage_path, mime_type, source_status"
                ") VALUES ("
                "'invalid-enum', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :lesson_id, "
                "'demo.mp3', 'audio/mpeg', 'UNKNOWN'"
                ")"
            ),
            {"lesson_id": lesson.id},
        )
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Expected the SQLite source-status CHECK constraint to reject UNKNOWN")

    concept = Concept(
        lesson_id=lesson.id,
        title="Plant inputs",
        concept_key="plant-inputs",
        definition="Plants need inputs to make food.",
        sequence=1,
    )
    artifact = GeneratedArtifact(
        lesson_id=lesson.id,
        course_context_version_id=context.id,
        artifact_type="layered-content",
        provider_name="demo-fixture",
        source_status=SourceStatus.DEMO,
        quality_status=QualityStatus.VERIFIED,
        uncertainty_status=UncertaintyStatus.CONFIRMED,
    )
    database_session.add_all([concept, artifact])
    database_session.flush()
    database_session.add_all(
        [
            ArtifactSourceConcept(artifact_id=artifact.id, concept_id=concept.id),
            ArtifactSourceConcept(artifact_id=artifact.id, concept_id=concept.id),
        ]
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Expected provenance association uniqueness to reject duplicates")


def test_term_suggestion_offsets_and_context_consistency(database_session) -> None:
    _, context, chapter, lesson = create_lesson_graph(database_session)
    assert not hasattr(lesson, "context_version_id")
    assert lesson.chapter_id == chapter.id
    assert chapter.context_version_id == context.id

    audio = LectureAudio(
        lesson_id=lesson.id,
        storage_path="demo.mp3",
        mime_type="audio/mpeg",
        source_status=SourceStatus.DEMO,
    )
    database_session.add(audio)
    database_session.flush()
    revision = TranscriptRevision(
        lecture_audio_id=audio.id,
        revision_number=1,
        source_status=SourceStatus.DEMO,
    )
    database_session.add(revision)
    database_session.flush()
    segment = TranscriptSegment(
        transcript_revision_id=revision.id,
        sequence=1,
        start_ms=0,
        end_ms=100,
        text="chlorophil",
        confidence=0.8,
    )
    database_session.add(segment)
    database_session.flush()
    database_session.add(
        TermSuggestion(
            transcript_segment_id=segment.id,
            detected_text="chlorophil",
            character_start=8,
            character_end=4,
            match_score=0.8,
        )
    )
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
    else:
        raise AssertionError("Term suggestion offsets must be ordered and non-negative")

    concept = Concept(
        lesson_id=lesson.id,
        title="Plant inputs",
        concept_key="plant-inputs",
        definition="Plants need inputs to make food.",
        sequence=1,
    )
    database_session.add(concept)
    database_session.commit()
    assert concept.lesson.chapter.context_version_id == context.id
