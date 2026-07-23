import { vi } from "vitest";

import type { AudioWorkflowSummary, Chapter, Completeness, ContextDetail, ContextSummary, Lesson, StudentChapter, StudentLesson, StudentOverview } from "../api/contracts";
import { PHOTOSYNTHESIS_DEMO_COURSE_ID } from "../demo/config";

export const course = { id: PHOTOSYNTHESIS_DEMO_COURSE_ID, title: "Class 7 Science", subject: "Science", class_level: 7, grade_band: "5-7" };
export const v1 = "context-v1";
export const v2 = "context-v2";

const glossary = [
  ["Photosynthesis", "പ്രകാശസംശ്ലേഷണം"], ["Chlorophyll", "ക്ലോറോഫിൽ"], ["Chloroplast", "ഹരിതകണം"], ["Stomata", "ഇലരന്ധ്രങ്ങൾ"], ["Carbon dioxide", "കാർബൺ ഡൈ ഓക്സൈഡ്"], ["Water", "ജലം"], ["Sunlight", "സൂര്യപ്രകാശം"], ["Glucose", "ഗ്ലൂക്കോസ്"], ["Oxygen", "ഓക്സിജൻ"], ["Leaf", "ഇല"],
].map(([canonical_term, malayalam_support_label], index) => ({
  id: `term-${index + 1}`,
  canonical_term,
  malayalam_support_label,
  definition: `${canonical_term} is part of the photosynthesis lesson.`,
  malayalam_explanation: `${malayalam_support_label}: പാഠത്തിലെ പ്രധാന പദം.`,
  sequence: index + 1,
  concept_ids: [
    ["concept-1"], ["concept-3"], ["concept-3"], ["concept-2"], ["concept-1", "concept-2"],
    ["concept-1", "concept-2"], ["concept-1", "concept-3"], ["concept-4"], ["concept-5"], ["concept-2"],
  ][index],
  aliases: [],
  misrecognitions: canonical_term === "Chlorophyll" ? [{ id: "asr-1", detected_text: "chlorophil", normalized_text: "chlorophil" }] : [],
}));

const concepts = [
  ["What plants need", "സസ്യങ്ങൾക്ക് വേണ്ട ഘടകങ്ങൾ"],
  ["How inputs reach the leaf", "ഘടകങ്ങൾ ഇലയിലെത്തുന്നത്"],
  ["Sunlight and chlorophyll", "സൂര്യപ്രകാശവും ക്ലോറോഫിലും"],
  ["Making glucose", "ഗ്ലൂക്കോസ് നിർമ്മാണം"],
  ["Releasing oxygen", "ഓക്സിജൻ പുറന്തള്ളൽ"],
].map(([title, malayalam_title], index) => ({ id: `concept-${index + 1}`, concept_key: `concept-${index + 1}`, title, malayalam_title, definition: `${title} definition`, malayalam_definition: `${malayalam_title} വിശദീകരണം`, sequence: index + 1 }));

function lesson(version: number, approvedTranscript = false): Lesson {
  const improved = version === 2;
  return {
    id: `lesson-${version}`, title: "Photosynthesis in Plants", sequence: 1, primary_language: "ml",
    description: "Green plants use sunlight, water and carbon dioxide to make glucose and release oxygen. പച്ച സസ്യങ്ങൾ ഭക്ഷണം നിർമ്മിക്കുന്നു.",
    objectives: [
      { id: `objective-${version}-1`, objective_text: "Identify the inputs required for photosynthesis.", malayalam_text: "പ്രകാശസംശ്ലേഷണത്തിന് ആവശ്യമായ ഘടകങ്ങളെ തിരിച്ചറിയുക.", sequence: 1 },
      { id: `objective-${version}-2`, objective_text: "Explain how sunlight and chlorophyll help plants.", malayalam_text: "സൂര്യപ്രകാശവും ക്ലോറോഫിലും സസ്യങ്ങളെ എങ്ങനെ സഹായിക്കുന്നു എന്ന് വിശദീകരിക്കുക.", sequence: 2 },
    ],
    approved_materials: [
      { id: `material-${version}-1`, title: improved ? "Improved teacher explanation" : "Trusted teacher explanation", material_type: "teacher_note", source_label: "Teacher-approved classroom note", content: improved ? "Improved teacher explanation\n\nസസ്യങ്ങൾ ഇലയിൽ ഭക്ഷണം നിർമ്മിക്കുന്നു." : "Plants use chlorophyll to capture sunlight.\n\nക്ലോറോഫിൽ സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.", language: "bilingual", sequence: 1 },
      { id: `material-${version}-2`, title: "Reference support", material_type: "reference_text", source_label: "Classroom reference support", content: "A leaf brings together water, carbon dioxide, sunlight and chlorophyll.", language: "bilingual", sequence: 2 },
    ],
    glossary_terms: glossary,
    concepts,
    concept_relationships: [],
  questions: [
      { id: `question-${version}-1`, related_concept_id: "concept-1", source_type: "teacher_question", source_label: "Teacher question", question_text: "What inputs do plants need for photosynthesis?", malayalam_question_text: "സസ്യങ്ങൾക്ക് എന്തെല്ലാം ഘടകങ്ങൾ ആവശ്യമാണ്?", sequence: 1, year: null, marks: null },
      { id: `question-${version}-2`, related_concept_id: "concept-3", source_type: "textbook_exercise", source_label: "Classroom exercise", question_text: "Why is chlorophyll important?", malayalam_question_text: "ക്ലോറോഫിൽ എന്തുകൊണ്ട് പ്രധാനമാണ്?", sequence: 2, year: null, marks: 2 },
      { id: `question-${version}-3`, related_concept_id: "concept-4", source_type: "board_style_question", source_label: "School-style practice question", question_text: "Explain how a leaf produces glucose.", malayalam_question_text: "ഒരു ഇല എങ്ങനെ ഗ്ലൂക്കോസ് നിർമ്മിക്കുന്നു?", sequence: 3, year: null, marks: 3 },
      ...(improved ? [{ id: "question-2-4", related_concept_id: "concept-5", source_type: "teacher_question", source_label: "Improved classroom question", question_text: "Put the five concepts in a learning flow.", malayalam_question_text: "അഞ്ച് ആശയങ്ങളെ പഠന ഒഴുക്കിൽ ക്രമീകരിക്കുക.", sequence: 4, year: null, marks: 3 }] : []),
  ],
  approved_transcript: approvedTranscript ? {
    id: "transcript-1", recording_id: "recording-1", provenance_label: "Deterministic offline demo transcript mapped to a team-recorded Malayalam/code-mixed lesson — not live STT.", source_status: "DEMO", trusted_context_version: version,
    segments: [
      { id: "segment-1", sequence: 1, start_ms: 0, end_ms: 7654, text: "സസ്യങ്ങൾക്ക് ജലം, carbon dioxide, sunlight എന്നിവ ആവശ്യമാണ്.", corrected_glossary_term_id: null },
      { id: "segment-2", sequence: 2, start_ms: 7654, end_ms: 12988, text: "ഇലയിലെ Chlorophyll സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.", corrected_glossary_term_id: "term-2" },
      { id: "segment-3", sequence: 3, start_ms: 12988, end_ms: 19400, text: "Plants glucose നിർമ്മിക്കുകയും oxygen പുറത്തുവിടുകയും ചെയ്യുന്നു.", corrected_glossary_term_id: null },
    ],
  } : null,
};
}

function studentLesson(version: number, approvedTranscript = false): StudentLesson {
  const trustedLesson = lesson(version, approvedTranscript);
  return {
    ...trustedLesson,
    glossary_terms: trustedLesson.glossary_terms.map(({ misrecognitions: _misrecognitions, ...term }) => term),
    recovery_support: [],
  };
}

export function focusLessonFixture(): StudentLesson {
  return studentLesson(1);
}

export const complete: Completeness = { context_version_id: v2, is_complete: true, issues: [], completed_sections: ["chapters", "lessons", "learning_objectives", "approved_materials", "glossary", "concepts", "questions", "required_text", "relationships"], incomplete_sections: [] };

function context(version: number, status: ContextSummary["teacher_review_status"]): ContextSummary {
  return { id: version === 1 ? v1 : v2, course_id: course.id, version_number: version, teacher_review_status: status, copied_from_context_version_id: version === 2 ? v1 : null, submitted_at: status === "DRAFT" ? null : "2026-07-16T09:00:00Z", approved_at: status === "APPROVED" ? "2026-07-16T09:05:00Z" : null, reviewer_note: null };
}

function detail(version: number, status: ContextSummary["teacher_review_status"]): ContextDetail {
  const summary = context(version, status);
  return { ...summary, chapters: [{ id: `chapter-${version}`, title: "Nutrition in Plants", sequence: 1, lessons: [lesson(version)] }], completeness: { ...complete, context_version_id: summary.id }, review_events: [] };
}

function overview(version: number, approvedTranscript = false, transformStudentLesson?: (lesson: StudentLesson) => StudentLesson, selectedContextId?: string): StudentOverview {
  const selected = context(version, "APPROVED");
  const trustedLesson = studentLesson(version, approvedTranscript);
  const chapters: StudentChapter[] = [{ id: `chapter-${version}`, title: "Nutrition in Plants", sequence: 1, lessons: [transformStudentLesson ? transformStudentLesson(trustedLesson) : trustedLesson] }];
  return { course, is_ready: true, selected_context_id: selectedContextId ?? selected.id, version_number: version, approved_at: selected.approved_at, chapters };
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function emptyAudioWorkflow(contextVersionId: string): AudioWorkflowSummary {
  return {
    context_version_id: contextVersionId,
    state: "NO_RECORDING",
    recording: null,
    latest_job: null,
    latest_revision: null,
    deletion: null,
    capabilities: {
      can_start_processing: false,
      can_retry_processing: false,
      can_enter_manual_transcript: false,
      can_edit_transcript: false,
      can_assess_quality: false,
      can_approve_transcript: false,
      can_remove_recording: false,
    },
  };
}

export function createCurriculumFetch(
  options: { notReady?: boolean; fail?: boolean; failSubmitOnce?: boolean; initialV2Status?: ContextSummary["teacher_review_status"]; initialStudentVersion?: 1 | 2; approvedTranscript?: boolean; transformStudentLesson?: (lesson: StudentLesson) => StudentLesson; studentContextId?: string; audioWorkflow?: AudioWorkflowSummary | ((contextVersionId: string) => AudioWorkflowSummary) } = {},
) {
  let v2Status: ContextSummary["teacher_review_status"] = options.initialV2Status ?? "DRAFT";
  let failSubmitOnce = options.failSubmitOnce ?? false;
  let studentVersion: 1 | 2 = options.initialStudentVersion ?? 1;
  const events: Record<string, { id: string; event_type: string; actor_role: string; note: string | null; created_at: string }[]> = {
    [v1]: [{ id: "event-v1-submitted", event_type: "submitted_for_review", actor_role: "teacher", note: null, created_at: "2026-07-16T09:00:00Z" }, { id: "event-v1-approved", event_type: "approved", actor_role: "teacher", note: null, created_at: "2026-07-16T09:05:00Z" }],
    [v2]: [{ id: "event-v2-copy", event_type: "copied_to_new_draft", actor_role: "teacher", note: "copied_from:f069db92-d848-5546-b3ad-3b10ee301600; improved classroom edition", created_at: "2026-07-16T09:05:00Z" }],
  };
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (options.fail) return response({ status: "error", code: "INTERNAL_ERROR", message: "SELECT * FROM private C:\\secrets", message_key: "error.internal", details: {}, recoverable: false, next_actions: [], job_id: null }, 500);
    if (url.endsWith(`/teacher/courses/${course.id}/contexts`)) return response({ status: "success", data: [context(1, "APPROVED"), context(2, v2Status)] });
    if (url.endsWith(`/student/courses/${course.id}/lesson-overview`)) return response({ status: "success", data: options.notReady ? { course, is_ready: false, selected_context_id: null, version_number: null, approved_at: null, chapters: [] } : overview(studentVersion, options.approvedTranscript, options.transformStudentLesson, options.studentContextId) });
    const contextId = url.match(/\/teacher\/contexts\/([^/]+)/)?.[1];
    const audioContextId = url.match(/\/curriculum\/context-versions\/([^/]+)\/audio-workflow/)?.[1];
    if (contextId && method === "POST" && url.endsWith("/submit-for-review")) {
      if (failSubmitOnce) {
        failSubmitOnce = false;
        return response({ status: "error", code: "TEMPORARY_FAILURE", message: "Try again", message_key: "error.retry", details: {}, recoverable: true, next_actions: [], job_id: null }, 503);
      }
      v2Status = "NEEDS_REVIEW";
      events[v2].push({ id: "event-v2-submit", event_type: "submitted_for_review", actor_role: "teacher", note: null, created_at: "2026-07-16T09:10:00Z" });
      return response({ status: "success", data: { context: context(2, v2Status), completeness: complete } });
    }
    if (contextId && method === "POST" && url.endsWith("/approve")) {
      v2Status = "APPROVED";
      studentVersion = 2;
      events[v2].push({ id: "event-v2-approved", event_type: "approved", actor_role: "teacher", note: null, created_at: "2026-07-16T09:12:00Z" });
      return response({ status: "success", data: { context: context(2, v2Status), newly_staled_artifact_count: 1 } });
    }
    if (audioContextId) {
      const configured = typeof options.audioWorkflow === "function"
        ? options.audioWorkflow(audioContextId)
        : options.audioWorkflow;
      return response({ status: "success", data: configured ?? emptyAudioWorkflow(audioContextId) });
    }
    if (contextId && url.endsWith("/completeness")) return response({ status: "success", data: { ...complete, context_version_id: contextId } });
    if (contextId && url.endsWith("/review-events")) return response({ status: "success", data: events[contextId] ?? [] });
    if (contextId && method === "GET") return response({ status: "success", data: { ...detail(contextId === v1 ? 1 : 2, contextId === v1 ? "APPROVED" : v2Status), review_events: events[contextId] ?? [] } });
    return response({ status: "error", code: "NOT_FOUND", message: "not found", message_key: "not_found", details: {}, recoverable: true, next_actions: [], job_id: null }, 404);
  });
}
