from enum import StrEnum


class QualityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class TeacherReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"


class SourceStatus(StrEnum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    DEMO = "DEMO"


class ArtifactStatus(StrEnum):
    READY = "READY"
    BLOCKED_BY_QUALITY = "BLOCKED_BY_QUALITY"
    STALE = "STALE"
    FAILED = "FAILED"


class UncertaintyStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    TENTATIVE = "TENTATIVE"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJobType(StrEnum):
    TRANSCRIPTION = "TRANSCRIPTION"
    CONCEPT_EXTRACTION = "CONCEPT_EXTRACTION"
    LAYERED_CONTENT_GENERATION = "LAYERED_CONTENT_GENERATION"
    EXPLAIN_DIFFERENTLY = "EXPLAIN_DIFFERENTLY"
    VISUAL_STORY_PREPARATION = "VISUAL_STORY_PREPARATION"
    TTS_GENERATION = "TTS_GENERATION"
    PRACTICE_GENERATION = "PRACTICE_GENERATION"


class TermDecisionValue(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNSURE = "UNSURE"


class ConceptState(StrEnum):
    NOT_STARTED = "not_started"
    VIEWED = "viewed"
    UNDERSTOOD = "understood"
    UNSURE = "unsure"
    NEEDS_ANOTHER_EXPLANATION = "needs_another_explanation"
    READY_FOR_PRACTICE = "ready_for_practice"


STUDENT_CONCEPT_STATE_LABELS: dict[ConceptState, str] = {
    ConceptState.NOT_STARTED: "New",
    ConceptState.VIEWED: "Learning",
    ConceptState.UNDERSTOOD: "I got it",
    ConceptState.UNSURE: "Not sure yet",
    ConceptState.NEEDS_ANOTHER_EXPLANATION: "Show me another way",
    ConceptState.READY_FOR_PRACTICE: "Ready to practise",
}
