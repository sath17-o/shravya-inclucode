export type ReviewStatus = "DRAFT" | "NEEDS_REVIEW" | "APPROVED";

export type ApiErrorEnvelope = {
  status: "error";
  code: string;
  message: string;
  message_key: string;
  details: Record<string, unknown>;
  recoverable: boolean;
  next_actions: string[];
  job_id: string | null;
};

export type ApiSuccess<T> = { status: "success"; data: T };

export type Course = {
  id: string;
  title: string;
  subject: string;
  class_level: number;
  grade_band: string;
};

export type ContextSummary = {
  id: string;
  course_id: string;
  version_number: number;
  teacher_review_status: ReviewStatus;
  copied_from_context_version_id: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  reviewer_note: string | null;
};

export type CompletenessIssue = {
  code: string;
  section: string;
  field: string | null;
  message_key: string;
  recovery_action: string;
};

export type Completeness = {
  context_version_id: string;
  is_complete: boolean;
  issues: CompletenessIssue[];
  completed_sections: string[];
  incomplete_sections: string[];
};

export type LearningObjective = { id: string; objective_text: string; malayalam_text: string | null; sequence: number };
export type ApprovedMaterial = {
  id: string;
  title: string;
  material_type: string;
  source_label: string;
  content: string;
  language: string;
  sequence: number;
  teacher_review_status?: ReviewStatus;
};
export type GlossaryTerm = {
  id: string;
  canonical_term: string;
  malayalam_support_label: string | null;
  definition: string;
  malayalam_explanation: string | null;
  sequence: number;
  concept_ids: string[];
  aliases: { id: string; alias: string; normalized_alias: string }[];
  misrecognitions?: { id: string; detected_text: string; normalized_text: string; source_note?: string | null }[];
};
export type StudentGlossaryTerm = Omit<GlossaryTerm, "misrecognitions">;
export type Concept = {
  id: string;
  concept_key: string;
  title: string;
  malayalam_title: string | null;
  definition: string;
  malayalam_definition: string | null;
  sequence: number;
};
export type RecoveryPack = { id: string; context_version_id: string; concept_id: string; cue_en: string; cue_ml: string; example_en: string; example_ml: string; alternate_explanation_en: string; alternate_explanation_ml: string; teacher_review_status: ReviewStatus; approved_at: string | null };
export type StudentRecoverySupport = { concept_id: string; cue: { english: string; malayalam: string }; example: { english: string; malayalam: string }; alternate_explanation: { english: string; malayalam: string } };
export type Question = {
  id: string;
  related_concept_id: string | null;
  source_type: string;
  source_label: string;
  question_text: string;
  malayalam_question_text: string | null;
  sequence: number;
  year: number | null;
  marks: number | null;
  teacher_review_status?: ReviewStatus;
};
export type Lesson = {
  id: string;
  title: string;
  sequence: number;
  primary_language: string;
  description: string | null;
  objectives: LearningObjective[];
  approved_materials: ApprovedMaterial[];
  glossary_terms: GlossaryTerm[];
  concepts: Concept[];
  recovery_packs?: RecoveryPack[];
  concept_relationships: { id: string; source_concept_id: string; target_concept_id: string; relationship_type: string; sequence: number }[];
  questions: Question[];
  approved_transcript: StudentTranscript | null;
};
export type StudentLesson = Omit<Lesson, "glossary_terms" | "recovery_packs"> & { glossary_terms: StudentGlossaryTerm[]; recovery_support: StudentRecoverySupport[] };
export type Recording = { id: string; lesson_id: string; original_filename: string; mime_type: string; byte_size: number; sha256: string; duration_ms: number; source_status: string; workflow_status: string };
export type RecordingRemoval = { recording_id: string; removed: boolean };
export type ProcessingJob = { id: string; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED"; stage: string; recoverable: boolean | null; recording_id: string; resulting_transcript_revision_id: string | null; error_code: string | null };
export type TranscriptSegment = { id: string; sequence: number; start_ms: number; end_ms: number; text: string };
export type TranscriptSegmentInput = { sequence?: number; start_ms: number; end_ms: number; text: string };
export type TranscriptSuggestion = { id: string; transcript_segment_id: string; glossary_term_id: string | null; detected_text: string; canonical_term: string | null; malayalam_support_label: string | null; latest_decision: "CONFIRMED" | "REJECTED" | "UNSURE" | null };
export type TranscriptQuality = { quality_status: "VERIFIED" | "NEEDS_REVIEW" | "FAILED"; measured_coverage?: number | null; reasons: { reason_code: string; severity: string; message_key: string; measured_value: number | null; threshold: number | null; recovery_action: string | null }[] };
export type TranscriptRevision = { id: string; recording_id: string; revision_number: number; copied_from_transcript_revision_id: string | null; source_status: string; provider_name: string; provider_version: string | null; provenance_label: string; teacher_review_status: ReviewStatus; approved_at: string | null; segments: TranscriptSegment[]; suggestions: TranscriptSuggestion[]; quality: TranscriptQuality | null };
export type AudioWorkflowState = "NO_RECORDING" | "UPLOADED" | "PROCESSING" | "PROCESSING_FAILED" | "MANUAL_TRANSCRIPT_REQUIRED" | "NEEDS_REVIEW" | "QUALITY_BLOCKED" | "QUALITY_VERIFIED" | "TRANSCRIPT_APPROVED" | "REMOVAL_PENDING" | "RECOVERY_CONFLICT";
export type AudioWorkflowSummary = {
  context_version_id: string;
  state: AudioWorkflowState;
  recording: { id: string; original_filename: string; mime_type: string; duration_ms: number; source_status: string; created_at: string; content_url: string } | null;
  latest_job: { id: string; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED"; stage: string; recoverable: boolean | null; error_code: string | null; message: string | null } | null;
  latest_revision: TranscriptRevision | null;
  deletion: { status: string; recoverable: boolean; message: string } | null;
  capabilities: { can_start_processing: boolean; can_retry_processing: boolean; can_enter_manual_transcript: boolean; can_edit_transcript: boolean; can_assess_quality: boolean; can_approve_transcript: boolean; can_remove_recording: boolean };
};
export type StudentTranscript = { id: string; recording_id: string; provenance_label: string; source_status: string; trusted_context_version: number; segments: Array<TranscriptSegment & { corrected_glossary_term_id: string | null }> };
export type Chapter = { id: string; title: string; sequence: number; lessons: Lesson[] };
export type StudentChapter = Omit<Chapter, "lessons"> & { lessons: StudentLesson[] };
export type ReviewEvent = { id: string; event_type: string; actor_role: string; note: string | null; created_at: string };
export type ContextDetail = ContextSummary & { chapters: Chapter[]; completeness: Completeness; review_events: ReviewEvent[] };
export type SubmitResponse = { context: ContextSummary; completeness: Completeness };
export type ApprovalResponse = { context: ContextSummary; newly_staled_artifact_count: number };
export type StudentOverview = {
  course: Course;
  is_ready: boolean;
  selected_context_id: string | null;
  version_number: number | null;
  approved_at: string | null;
  chapters: StudentChapter[];
};
