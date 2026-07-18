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
} from "./contracts";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

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
  submit: (contextId: string) => request<SubmitResponse>(`/teacher/contexts/${contextId}/submit-for-review`, { method: "POST" }),
  approve: (contextId: string) => request<ApprovalResponse>(`/teacher/contexts/${contextId}/approve`, { method: "POST" }),
  studentOverview: (courseId: string, signal?: AbortSignal) => request<StudentOverview>(`/student/courses/${courseId}/lesson-overview`, { signal })

};
