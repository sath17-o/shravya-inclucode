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
  aliases: { id: string; alias: string; normalized_alias: string }[];
  misrecognitions: { id: string; detected_text: string; normalized_text: string; source_note?: string | null }[];
};
export type Concept = {
  id: string;
  concept_key: string;
  title: string;
  malayalam_title: string | null;
  definition: string;
  malayalam_definition: string | null;
  sequence: number;
};
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
  concept_relationships: { id: string; source_concept_id: string; target_concept_id: string; relationship_type: string; sequence: number }[];
  questions: Question[];
};
export type Chapter = { id: string; title: string; sequence: number; lessons: Lesson[] };
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
  chapters: Chapter[];
};
