# Phase 1 data model

The foundation uses SQLite, UUID string identifiers, UTC timestamps, explicit enums, and foreign-key relationships. Course-context versions and learner session payloads include schema/version fields where future migrations need them.

```text
Course → CourseContextVersion → Chapter → Lesson
Lesson → LearningObjective / GlossaryTerm / LectureAudio / Concept / QuestionItem
GlossaryTerm → TermAlias / ASRMisrecognition
LectureAudio → TranscriptRevision → TranscriptSegment / TermSuggestion / TranscriptQualityAssessment
TermSuggestion → TermDecision
Concept → ConceptEvidence / LearnerConceptState
GeneratedArtifact → ArtifactSourceConcept → Concept
GeneratedArtifact → ArtifactSourceReference
LocalLearnerProfile → LearningPreferenceProfile / LearningSession / LearnerConceptState
```

`GeneratedArtifact` records transcript revision, course-context version, provider/model/prompt identifiers where relevant, generation time, quality, teacher review, artifact status, and stale metadata. Source concepts and source references are normalized association records, not comma-separated fields.

The Phase 1 schema intentionally excludes feature-specific production behaviour.
