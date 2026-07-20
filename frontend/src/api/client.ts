import type {
  ApiErrorEnvelope,
  ApiSuccess,
  ApprovalResponse,
  Completeness,
  ContextDetail,
  ContextSummary,
  ReviewEvent,
  StudentOverview,
  SubmitResponse,
  Recording,
  RecordingRemoval,
  ProcessingJob,
  TranscriptSegmentInput,
  TranscriptRevision,
  AudioWorkflowSummary,
} from "./contracts";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(readonly envelope: ApiErrorEnvelope | null, readonly recoverable: boolean) {
    super("The classroom information could not be loaded.");
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(null, true);
  }

  let body: ApiSuccess<T> | ApiErrorEnvelope | null = null;
  try {
    body = (await response.json()) as ApiSuccess<T> | ApiErrorEnvelope;
  } catch {
    throw new ApiError(null, response.status < 500);
  }
  if (response.ok && body.status === "success") return body.data;
  throw new ApiError(body.status === "error" ? body : null, body.status === "error" ? body.recoverable : response.status < 500);
}

export const curriculumApi = {
  listContexts: (courseId: string, signal?: AbortSignal) => request<ContextSummary[]>(`/teacher/courses/${courseId}/contexts`, { signal }),
  contextDetail: (contextId: string, signal?: AbortSignal) => request<ContextDetail>(`/teacher/contexts/${contextId}`, { signal }),
  completeness: (contextId: string, signal?: AbortSignal) => request<Completeness>(`/teacher/contexts/${contextId}/completeness`, { signal }),
  reviewEvents: (contextId: string, signal?: AbortSignal) => request<ReviewEvent[]>(`/teacher/contexts/${contextId}/review-events`, { signal }),
  audioWorkflow: (contextId: string, signal?: AbortSignal) => request<AudioWorkflowSummary>(`/curriculum/context-versions/${contextId}/audio-workflow`, { signal }),
  submit: (contextId: string) => request<SubmitResponse>(`/teacher/contexts/${contextId}/submit-for-review`, { method: "POST" }),
  approve: (contextId: string) => request<ApprovalResponse>(`/teacher/contexts/${contextId}/approve`, { method: "POST" }),
  studentOverview: (courseId: string, signal?: AbortSignal) => request<StudentOverview>(`/student/courses/${courseId}/lesson-overview`, { signal }),
  uploadRecording: (lessonId: string, file: File) => request<Recording>(`/teacher/lessons/${lessonId}/recordings`, { method: "POST", headers: { "Content-Type": file.type || "audio/wav", "X-Filename": file.name }, body: file }),
  removeRecording: (contextVersionId: string, recordingId: string) => request<RecordingRemoval>(`/curriculum/context-versions/${contextVersionId}/recordings/${recordingId}`, { method: "DELETE" }),
  requestTranscription: (recordingId: string) => request<ProcessingJob>(`/teacher/recordings/${recordingId}/transcriptions`, { method: "POST" }),
  job: (jobId: string) => request<ProcessingJob>(`/teacher/processing-jobs/${jobId}`),
  runJob: (jobId: string) => request<ProcessingJob>(`/teacher/processing-jobs/${jobId}/run`, { method: "POST" }),
  transcript: (revisionId: string) => request<TranscriptRevision>(`/teacher/transcript-revisions/${revisionId}`),
  decideTerm: (suggestionId: string, decision: string) => request<TranscriptRevision>(`/teacher/term-suggestions/${suggestionId}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) }),
  manualRevision: (revisionId: string, segments: TranscriptSegmentInput[]) => request<TranscriptRevision>(`/teacher/transcript-revisions/${revisionId}/manual-revision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments }) }),
  recordingManualRevision: (recordingId: string, segments: TranscriptSegmentInput[]) => request<TranscriptRevision>(`/teacher/recordings/${recordingId}/manual-revision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments }) }),
  assessTranscript: (revisionId: string) => request<TranscriptRevision>(`/teacher/transcript-revisions/${revisionId}/quality-assessment`, { method: "POST" }),
  approveTranscript: (revisionId: string) => request<TranscriptRevision>(`/teacher/transcript-revisions/${revisionId}/approve`, { method: "POST" }),
};
