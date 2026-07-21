import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiBaseUrl, ApiError, curriculumApi } from "../api/client";
import type { AudioWorkflowSummary, Completeness, ContextDetail, ContextSummary, Lesson, Recording, StudentLesson, StudentOverview, TranscriptRevision, TranscriptSegmentInput } from "../api/contracts";
import { useAppContext } from "../app/AppContext";
import { Button, ErrorAlert, StatusMessage } from "../components/primitives";
import { PHOTOSYNTHESIS_DEMO_COURSE_ID } from "../demo/config";
import {
  buildFocusJourneySteps,
  clearFocusJourneyProgress,
  FOCUS_SUPPORT_OPTIONS,
  focusJourneyStorageKey,
  hasStoredFocusJourneyProgress,
  newFocusJourneyProgress,
  readFocusJourneyProgress,
  saveFocusJourneyProgress,
  type FocusSupportMode,
  type FocusJourneyProgress,
} from "./focusJourney";

type AsyncState<T> = { kind: "loading" } | { kind: "error"; error: ApiError } | { kind: "ready"; data: T };
type TeacherWorkspace = { detail: ContextDetail; completeness: Completeness; events: ContextDetail["review_events"] };

const statusLabel: Record<ContextSummary["teacher_review_status"], string> = {
  APPROVED: "Approved",
  DRAFT: "Draft",
  NEEDS_REVIEW: "Needs review",
};

const eventLabel: Record<string, string> = {
  approved: "Approved",
  copied_to_new_draft: "Copied to new draft",
  draft_created: "Draft created",
  returned_to_draft: "Returned to Draft",
  submitted_for_review: "Submitted for review",
};

const checklistLabels: Record<string, string> = {
  approved_materials: "Approved materials are available",
  concepts: "All five learning concepts are defined",
  glossary: "All required glossary terms are present",
  questions: "Approved questions are available",
  required_text: "Malayalam support labels are complete",
};

export function versionVisibilityMessage(
  context: ContextSummary,
  currentStudentVersion: number | null,
): string {
  if (context.teacher_review_status === "DRAFT") {
    return "Hidden from students until submitted and approved";
  }
  if (context.teacher_review_status === "NEEDS_REVIEW") {
    return "Awaiting teacher approval · hidden from students";
  }
  return context.version_number === currentStudentVersion
    ? "Currently visible to students"
    : "Earlier approved version";
}

function safeError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(null, true);
}

function formatDate(value: string | null) {
  if (!value) return "Not yet";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Recorded" : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function StatusPill({ status }: { status: ContextSummary["teacher_review_status"] }) {
  return <span className={`status-pill status-${status.toLowerCase().replaceAll("_", "-")}`}>{statusLabel[status]}</span>;
}

function LoadingState({ label }: { label: string }) {
  return <section aria-live="polite" aria-busy="true" className="loading-panel" role="status"><span className="loading-mark" />{label}</section>;
}

function ErrorState({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <ErrorAlert>
      <p>{error.recoverable ? "We could not load the classroom information. You can try again." : "The classroom information is unavailable right now."}</p>
      {error.recoverable ? <Button onClick={onRetry} type="button">Try again</Button> : null}
    </ErrorAlert>
  );
}

function Bilingual({ english, malayalam, className }: { english: string; malayalam?: string | null; className?: string }) {
  return (
    <span className={className}>
      {malayalam ? <><span lang="ml" className="malayalam-copy">{malayalam}</span><span aria-hidden="true"> · </span></> : null}
      <span lang="en">{english}</span>
    </span>
  );
}

function useTeacherWorkspace(selectedId: string | null, refreshToken: number) {
  const [contexts, setContexts] = useState<AsyncState<ContextSummary[]>>({ kind: "loading" });
  const [workspace, setWorkspace] = useState<AsyncState<TeacherWorkspace>>({ kind: "loading" });
  const activeId = selectedId ?? (contexts.kind === "ready" ? contexts.data[0]?.id ?? null : null);

  const reloadContexts = useCallback(async (signal?: AbortSignal, showLoading = true) => {
    if (showLoading) setContexts({ kind: "loading" });
    try {
      setContexts({ kind: "ready", data: await curriculumApi.listContexts(PHOTOSYNTHESIS_DEMO_COURSE_ID, signal) });
    } catch (error) {
      if (!signal?.aborted) setContexts({ kind: "error", error: safeError(error) });
    }
  }, []);

  const reloadWorkspace = useCallback(async (contextId: string, signal?: AbortSignal, showLoading = true) => {
    if (showLoading) setWorkspace({ kind: "loading" });
    try {
      const [detail, completeness, events] = await Promise.all([
        curriculumApi.contextDetail(contextId, signal),
        curriculumApi.completeness(contextId, signal),
        curriculumApi.reviewEvents(contextId, signal),
      ]);
      setWorkspace({ kind: "ready", data: { detail, completeness, events } });
    } catch (error) {
      if (!signal?.aborted) setWorkspace({ kind: "error", error: safeError(error) });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const data = await curriculumApi.listContexts(PHOTOSYNTHESIS_DEMO_COURSE_ID, controller.signal);
        if (!controller.signal.aborted) setContexts({ kind: "ready", data });
      } catch (error) {
        if (!controller.signal.aborted) setContexts({ kind: "error", error: safeError(error) });
      }
    };
    void load();
    return () => controller.abort();
  }, [refreshToken]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    const load = async () => {
      try {
        const [detail, completeness, events] = await Promise.all([
          curriculumApi.contextDetail(activeId, controller.signal),
          curriculumApi.completeness(activeId, controller.signal),
          curriculumApi.reviewEvents(activeId, controller.signal),
        ]);
        if (!controller.signal.aborted) setWorkspace({ kind: "ready", data: { detail, completeness, events } });
      } catch (error) {
        if (!controller.signal.aborted) setWorkspace({ kind: "error", error: safeError(error) });
      }
    };
    void load();
    return () => controller.abort();
  }, [activeId, refreshToken]);

  return { activeId, contexts, workspace, reloadContexts, reloadWorkspace };
}

export function TeacherReviewPage() {
  const { curriculumRevision, refreshCurriculum } = useAppContext();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState<"submit" | "approve" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mutationFailure, setMutationFailure] = useState<"submit" | "approve" | null>(null);
  const { activeId, contexts, workspace, reloadContexts, reloadWorkspace } = useTeacherWorkspace(selectedId, curriculumRevision);

  const currentStudentVersion = useMemo(() => {
    if (contexts.kind !== "ready") return null;
    return Math.max(...contexts.data.filter((context) => context.teacher_review_status === "APPROVED").map((context) => context.version_number), 0) || null;
  }, [contexts]);

  const retry = () => {
    void reloadContexts();
    if (activeId) void reloadWorkspace(activeId);
  };

  const submit = async () => {
    if (!activeId || pending !== null) return;
    setPending("submit");
    setNotice(null);
    setMutationFailure(null);
    try {
      await curriculumApi.submit(activeId);
      setNotice("Context submitted for teacher review.");
      await Promise.all([reloadContexts(undefined, false), reloadWorkspace(activeId, undefined, false)]);
    } catch (error) {
      const failure = safeError(error);
      if (failure.recoverable) {
        setMutationFailure("submit");
      } else {
        setNotice("Submission is unavailable right now.");
      }
    } finally {
      setPending(null);
    }
  };

  const approve = async () => {
    if (!activeId || pending !== null) return;
    setPending("approve");
    setNotice(null);
    setMutationFailure(null);
    try {
      const result = await curriculumApi.approve(activeId);
      setNotice(`New trusted version approved. ${result.newly_staled_artifact_count} older learning artifact${result.newly_staled_artifact_count === 1 ? "" : "s"} marked stale.`);
      refreshCurriculum();
      await Promise.all([reloadContexts(undefined, false), reloadWorkspace(activeId, undefined, false)]);
    } catch (error) {
      const failure = safeError(error);
      if (failure.recoverable) {
        setMutationFailure("approve");
      } else {
        setNotice("Approval is unavailable right now.");
      }
    } finally {
      setPending(null);
    }
  };

  return (
    <article className="teacher-page">
      <header className="page-intro">
        <p className="eyebrow">Class 7 Science · Nutrition in Plants</p>
        <h1>Teacher Review Workspace</h1>
        <p>Review the classroom context before students and learning tools can use it.</p>
      </header>
      {notice ? <StatusMessage>{notice}</StatusMessage> : null}
      {mutationFailure ? (
        <ErrorAlert>
          <p>{mutationFailure === "submit" ? "Submission could not be completed." : "Approval could not be completed."}</p>
          <Button disabled={pending !== null} onClick={mutationFailure === "submit" ? submit : approve} type="button">
            {mutationFailure === "submit" ? "Try submitting again" : "Try approving again"}
          </Button>
        </ErrorAlert>
      ) : null}
      {contexts.kind === "loading" ? <LoadingState label="Loading classroom versions…" /> : null}
      {contexts.kind === "error" ? <ErrorState error={contexts.error} onRetry={retry} /> : null}
      {contexts.kind === "ready" ? (
        <div className="teacher-layout">
          <aside aria-label="Lesson versions" className="version-rail">
            <h2>Classroom versions</h2>
            <p className="quiet-copy">Photosynthesis in Plants</p>
            <div className="version-list">
              {contexts.data.map((context) => (
                <button aria-pressed={activeId === context.id} className="version-card" key={context.id} onClick={() => { setSelectedId(context.id); setNotice(null); }} type="button">
                  <span className="version-topline"><strong>Version {context.version_number}</strong><StatusPill status={context.teacher_review_status} /></span>
                  <span>{versionVisibilityMessage(context, currentStudentVersion)}</span>
                  {context.copied_from_context_version_id ? <span>Copied from version {context.version_number - 1}</span> : null}
                  <span>Submitted: {formatDate(context.submitted_at)}</span>
                  <span>Approved: {formatDate(context.approved_at)}</span>
                </button>
              ))}
            </div>
          </aside>
          <section className="workspace-detail">
            {workspace.kind === "loading" ? <LoadingState label="Loading selected classroom context…" /> : null}
            {workspace.kind === "error" ? <ErrorState error={workspace.error} onRetry={retry} /> : null}
            {workspace.kind === "ready" ? <TeacherContextDetail completeness={workspace.data.completeness} detail={workspace.data.detail} events={workspace.data.events} onApprove={approve} onSubmit={submit} onWorkflowChanged={() => reloadWorkspace(workspace.data.detail.id, undefined, false)} pending={pending} /> : null}
          </section>
        </div>
      ) : null}
    </article>
  );
}

function TeacherContextDetail({ detail, completeness, events, pending, onSubmit, onApprove, onWorkflowChanged }: { detail: ContextDetail; completeness: Completeness; events: ContextDetail["review_events"]; pending: "submit" | "approve" | null; onSubmit: () => void; onApprove: () => void; onWorkflowChanged: () => Promise<void> }) {
  const lesson = detail.chapters[0]?.lessons[0];
  if (!lesson) return <section className="empty-state"><h2>No lesson content yet</h2><p>This version does not contain a lesson to review.</p></section>;
  const canSubmit = detail.teacher_review_status === "DRAFT" && completeness.is_complete;
  const canApprove = detail.teacher_review_status === "NEEDS_REVIEW" && completeness.is_complete;
  return (
    <>
      <section className="detail-heading">
        <p className="eyebrow">{detail.chapters[0]?.title ?? "Classroom context"}</p>
        <div className="title-row"><h2>{lesson.title}</h2><StatusPill status={detail.teacher_review_status} /></div>
        <p>Version {detail.version_number} is {detail.teacher_review_status === "DRAFT" ? "hidden from students until approved." : "a teacher-controlled classroom version."}</p>
      </section>
      <section className={`completeness-panel ${completeness.is_complete ? "complete" : "incomplete"}`}>
        <div><p className="eyebrow">Context completeness</p><h2>{completeness.is_complete ? "Ready for teacher review" : "Needs classroom information"}</h2></div>
        {completeness.is_complete ? <ul>{Object.entries(checklistLabels).filter(([section]) => completeness.completed_sections.includes(section)).map(([, label]) => <li key={label}>{label}</li>)}</ul> : <ul>{completeness.issues.map((issue) => <li key={`${issue.section}-${issue.code}`}>{issue.recovery_action}</li>)}</ul>}
        <div className="review-actions">
          {detail.teacher_review_status === "DRAFT" ? <Button disabled={!canSubmit || pending !== null} onClick={onSubmit} type="button">{pending === "submit" ? "Submitting…" : "Submit for review"}</Button> : null}
          {detail.teacher_review_status === "NEEDS_REVIEW" ? <Button disabled={!canApprove || pending !== null} onClick={onApprove} type="button">{pending === "approve" ? "Approving…" : "Approve trusted version"}</Button> : null}
        </div>
      </section>
      <ResumableTeacherAudioWorkflow contextVersionId={detail.id} key={detail.id} lesson={lesson} onWorkflowChanged={onWorkflowChanged} />
      <RecoveryPackTeacherSection lesson={lesson} onChanged={onWorkflowChanged} />
      <section className="content-section"><h2>Learning objectives</h2><ol className="stack-list">{lesson.objectives.map((objective) => <li key={objective.id}><Bilingual english={objective.objective_text} malayalam={objective.malayalam_text} /></li>)}</ol></section>
      <section className="content-section"><h2>Approved learning materials</h2><div className="material-grid">{lesson.approved_materials.map((material) => <article className="material-card" key={material.id}><h3>{material.title}</h3><p className="material-source">{material.source_label}</p><p className="pre-line">{material.content}</p></article>)}</div></section>
      <section className="content-section"><h2>Glossary</h2><div className="glossary-grid">{lesson.glossary_terms.map((term) => <article className="glossary-card" key={term.id}><h3><Bilingual english={term.canonical_term} malayalam={term.malayalam_support_label} /></h3><p>{term.definition}</p></article>)}</div></section>
      <section className="content-section"><h2>Concept flow</h2><ConceptFlow lesson={lesson} /></section>
      <section className="content-section"><h2>Practice questions</h2><QuestionList lesson={lesson} /></section>
      <section className="content-section review-history"><h2>Review history</h2><ol className="timeline">{events.map((event) => <li key={event.id}><strong>{eventLabel[event.event_type] ?? "Review activity"}</strong><span>{formatDate(event.created_at)}</span></li>)}</ol></section>
    </>
  );
}

function RecoveryPackTeacherSection({ lesson, onChanged }: { lesson: Lesson; onChanged: () => Promise<void> }) {
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const packs = lesson.recovery_packs ?? [];
  if (packs.length === 0) return null;
  const byConcept = new Map(packs.map((pack) => [pack.concept_id, pack]));
  const approve = async (packId: string) => {
    setApprovingId(packId);
    try { await curriculumApi.approveRecoveryPack(packId); await onChanged(); } finally { setApprovingId(null); }
  };
  return <section aria-labelledby="recovery-support-title" className="content-section recovery-pack-section">
    <p className="eyebrow">NEUROFLEX RECOVERY SUPPORT</p><h2 id="recovery-support-title">Recovery support for this lesson</h2>
    <p>Review the cues, examples and alternate explanations that students may use when they become stuck.</p>
    <div className="recovery-pack-list">{[...lesson.concepts].sort((a, b) => a.sequence - b.sequence).map((concept) => {
      const pack = byConcept.get(concept.id); if (!pack) return null;
      const approved = pack.teacher_review_status === "APPROVED";
      return <article className="recovery-pack-card" key={pack.id} aria-labelledby={`recovery-pack-${pack.id}`}>
        <p className="quiet-copy">Concept {concept.sequence}</p><h3 id={`recovery-pack-${pack.id}`}><Bilingual english={concept.title} malayalam={concept.malayalam_title} /></h3>
        <dl><div><dt>Cue</dt><dd><Bilingual english={pack.cue_en} malayalam={pack.cue_ml} /></dd></div><div><dt>Example</dt><dd><Bilingual english={pack.example_en} malayalam={pack.example_ml} /></dd></div><div><dt>Alternate explanation</dt><dd><Bilingual english={pack.alternate_explanation_en} malayalam={pack.alternate_explanation_ml} /></dd></div></dl>
        <p><strong>{approved ? "Approved for students" : "Needs teacher review"}</strong></p>
        <Button disabled={approved || approvingId === pack.id} onClick={() => void approve(pack.id)} type="button">{approved ? "Recovery pack approved" : "Approve recovery pack"}</Button>
      </article>;
    })}</div>
  </section>;
}

type TimelineStatus = "not-started" | "current" | "complete" | "failed";
type EditableSegment = TranscriptSegmentInput & { clientId: string };

const timelineLabels: Record<TimelineStatus, { marker: string; label: string }> = {
  "not-started": { marker: "○", label: "Not started" },
  current: { marker: "→", label: "Current" },
  complete: { marker: "✓", label: "Complete" },
  failed: { marker: "!", label: "Failed" },
};

function workflowTimeline(summary: AudioWorkflowSummary | null, hasSelectedFile: boolean, uploading: boolean) {
  const statuses: TimelineStatus[] = ["not-started", "not-started", "not-started", "not-started", "not-started"];
  if (hasSelectedFile) statuses[0] = "current";
  if (uploading) {
    statuses[0] = "complete";
    statuses[1] = "current";
  }
  if (!summary || hasSelectedFile || uploading) return statuses;

  switch (summary.state) {
    case "UPLOADED":
      statuses[0] = "complete";
      statuses[1] = "complete";
      break;
    case "PROCESSING":
      statuses[0] = "complete";
      statuses[1] = "complete";
      statuses[2] = "current";
      break;
    case "PROCESSING_FAILED":
    case "MANUAL_TRANSCRIPT_REQUIRED":
      statuses[0] = "complete";
      statuses[1] = "complete";
      statuses[2] = "failed";
      break;
    case "NEEDS_REVIEW":
    case "QUALITY_BLOCKED":
    case "QUALITY_VERIFIED":
      statuses[0] = "complete";
      statuses[1] = "complete";
      statuses[2] = "complete";
      statuses[3] = "complete";
      statuses[4] = "current";
      break;
    case "TRANSCRIPT_APPROVED":
      statuses.fill("complete");
      break;
    case "NO_RECORDING":
    case "REMOVAL_PENDING":
    case "RECOVERY_CONFLICT":
      break;
  }
  return statuses;
}

function ResumableTeacherAudioWorkflow({
  contextVersionId,
  lesson,
  onWorkflowChanged,
}: {
  contextVersionId: string;
  lesson: Lesson;
  onWorkflowChanged: () => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<AsyncState<AudioWorkflowSummary>>({ kind: "loading" });
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [segments, setSegments] = useState<EditableSegment[]>([]);
  const [removalPending, setRemovalPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [timestampOrderError, setTimestampOrderError] = useState(false);
  const [segmentAnnouncement, setSegmentAnnouncement] = useState("");
  const summaryRequest = useRef(0);
  const segmentId = useRef(0);
  const moveControlRefs = useRef(new Map<string, { up: HTMLButtonElement | null; down: HTMLButtonElement | null }>());
  const moveFocusTarget = useRef<{ clientId: string; control: "up" | "down" } | null>(null);

  const loadSummary = useCallback(async (signal?: AbortSignal, showLoading = true) => {
    const requestNumber = ++summaryRequest.current;
    if (showLoading) setSummary({ kind: "loading" });
    try {
      const next = await curriculumApi.audioWorkflow(contextVersionId, signal);
      if (!signal?.aborted && requestNumber === summaryRequest.current && next.context_version_id === contextVersionId) {
        setSummary({ kind: "ready", data: next });
      }
    } catch (cause) {
      if (!signal?.aborted) setSummary({ kind: "error", error: safeError(cause) });
    }
  }, [contextVersionId]);

  useEffect(() => {
    const controller = new AbortController();
    const requestNumber = ++summaryRequest.current;
    const restore = async () => {
      try {
        const next = await curriculumApi.audioWorkflow(contextVersionId, controller.signal);
        if (!controller.signal.aborted && requestNumber === summaryRequest.current && next.context_version_id === contextVersionId) {
          setSummary({ kind: "ready", data: next });
        }
      } catch (cause) {
        if (!controller.signal.aborted) setSummary({ kind: "error", error: safeError(cause) });
      }
    };
    void restore();
    return () => controller.abort();
  }, [contextVersionId]);

  useEffect(() => {
    if (summary.kind !== "ready" || summary.data.state !== "PROCESSING") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const interval = reducedMotion ? 1500 : 1000;
    const poll = async () => {
      if (cancelled) return;
      try {
        const requestNumber = ++summaryRequest.current;
        const next = await curriculumApi.audioWorkflow(contextVersionId);
        if (cancelled || requestNumber !== summaryRequest.current || next.context_version_id !== contextVersionId) return;
        setSummary({ kind: "ready", data: next });
        if (next.state === "PROCESSING" && attempts < 39) {
          attempts += 1;
          timer = setTimeout(() => void poll(), interval);
        } else if (next.state === "PROCESSING") {
          setError("Processing is taking longer than expected. You can retry safely.");
        }
      } catch {
        if (!cancelled) setError("Processing status could not be refreshed. Try again.");
      }
    };
    timer = setTimeout(() => void poll(), interval);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [contextVersionId, summary]);

  useEffect(() => {
    const target = moveFocusTarget.current;
    if (!target) return;
    moveControlRefs.current.get(target.clientId)?.[target.control]?.focus();
    moveFocusTarget.current = null;
  }, [segments]);

  const data = summary.kind === "ready" ? summary.data : null;
  const recording = data?.recording ?? null;
  const revision = data?.latest_revision ?? null;
  const capabilities = data?.capabilities;
  const audioUrl = recording ? `${apiBaseUrl.replace(/\/api\/v1$/, "")}${recording.content_url}` : null;
  const timeline = workflowTimeline(data, file !== null, uploading);
  const milestoneNames = ["Selected", "Uploading", "Transcribing", "Transcript ready", "Needs review"];

  const normalizeSegments = (items: EditableSegment[]) => items.map((item, index) => ({ ...item, sequence: index + 1 }));
  const newSegment = (segment: TranscriptSegmentInput): EditableSegment => ({ ...segment, clientId: `new-segment-${++segmentId.current}` });

  const beginManualEntry = () => {
    setTimestampOrderError(false);
    setSegmentAnnouncement("");
    setSegments(revision
      ? revision.segments.map(({ id, sequence, start_ms, end_ms, text }) => ({ clientId: id, sequence, start_ms, end_ms, text }))
      : [newSegment({ sequence: 1, start_ms: 0, end_ms: recording?.duration_ms ?? 1000, text: "" })]);
    setEditing(true);
  };

  const updateSegment = (index: number, field: keyof TranscriptSegmentInput, value: string) => {
    setTimestampOrderError(false);
    setSegments((current) => current.map((segment, itemIndex) => itemIndex === index
      ? { ...segment, [field]: field === "text" ? value : Number(value) }
      : segment));
  };

  const moveSegment = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= segments.length) return;
    const movedSegmentId = segments[index].clientId;
    setTimestampOrderError(false);
    setSegments((current) => {
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return normalizeSegments(next);
    });
    moveFocusTarget.current = { clientId: movedSegmentId, control: direction === -1 ? "down" : "up" };
    setSegmentAnnouncement(`Segment moved to position ${nextIndex + 1} of ${segments.length}.`);
  };

  const removeSegment = (index: number) => {
    setTimestampOrderError(false);
    setSegments((current) => normalizeSegments(current.filter((_, itemIndex) => itemIndex !== index)));
  };

  const timestampOrderIsValid = () => segments.every((segment, index) => index === 0 || segment.start_ms >= segments[index - 1].start_ms);

  const runAction = async (action: () => Promise<void>, failure: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      await loadSummary(undefined, false);
      await onWorkflowChanged();
    } catch {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (!file || !file.name.toLowerCase().endsWith(".wav")) {
      setError("Choose a WAV recording to continue.");
      return;
    }
    setUploading(true);
    await runAction(async () => {
      await curriculumApi.uploadRecording(lesson.id, file);
      setFile(null);
    }, "The WAV recording could not be uploaded. Check the file and try again.");
    setUploading(false);
  };

  const transcribe = () => {
    if (!recording) return;
    void runAction(async () => {
      const job = await curriculumApi.requestTranscription(recording.id);
      await loadSummary(undefined, false);
      await curriculumApi.runJob(job.id);
    }, "Transcription could not be completed. You can add a manual transcript.");
  };

  const decide = (suggestionId: string, decision: string) => {
    void runAction(
      async () => {
        await curriculumApi.decideTerm(suggestionId, decision);
      },
      "The term decision could not be saved.",
    );
  };

  const assess = () => {
    if (!revision) return;
    void runAction(
      async () => {
        await curriculumApi.assessTranscript(revision.id);
      },
      "Quality could not be assessed. Try again.",
    );
  };

  const saveManual = () => {
    if (!recording) return;
    if (!timestampOrderIsValid()) {
      setTimestampOrderError(true);
      return;
    }
    void runAction(async () => {
      const payload = segments.map(({ clientId: _clientId, ...segment }) => segment);
      if (revision) await curriculumApi.manualRevision(revision.id, payload);
      else await curriculumApi.recordingManualRevision(recording.id, payload);
      setEditing(false);
    }, "The corrected transcript could not be saved. Check every timestamp and try again.");
  };

  const approve = () => {
    if (!revision) return;
    void runAction(
      async () => {
        await curriculumApi.approveTranscript(revision.id);
      },
      "Transcript approval is blocked until the current quality checks pass.",
    );
  };

  const remove = () => {
    if (!recording) return;
    void runAction(async () => {
      await curriculumApi.removeRecording(contextVersionId, recording.id);
      setFile(null);
      setEditing(false);
      setRemovalPending(false);
    }, "The recording could not be removed. Try again.");
  };

  return <section className="content-section audio-workflow" aria-labelledby="audio-workflow-title">
    <div><p className="eyebrow">Classroom recording</p><h2 id="audio-workflow-title">Audio-to-trusted-lesson review</h2><p>Upload one local WAV recording. Deterministic demo transcription is clearly labelled and unknown recordings use manual correction.</p></div>
    <section aria-labelledby="audio-workflow-progress-title" className="workflow-progress">
      <h3 id="audio-workflow-progress-title">Recording workflow</h3>
      <ol className="workflow-timeline">
        {milestoneNames.map((name, index) => {
          const status = timeline[index];
          const statusInfo = timelineLabels[status];
          return <li aria-current={status === "current" ? "step" : undefined} className={`workflow-milestone ${status}`} key={name}>
            <span aria-hidden="true" className="workflow-marker">{statusInfo.marker}</span>
            <span className="workflow-name">{name}</span>
            <span className="workflow-status">{statusInfo.label}</span>
          </li>;
        })}
      </ol>
      <p aria-live="polite" className="sr-only">{timeline.some((status) => status === "current") ? `${milestoneNames[timeline.indexOf("current")]} is current.` : data?.state === "TRANSCRIPT_APPROVED" ? "Transcript review complete." : "Workflow has not started."}</p>
    </section>
    {summary.kind === "loading" ? <StatusMessage>Restoring saved classroom recording review…</StatusMessage> : null}
    {summary.kind === "error" ? <ErrorAlert><p>Audio review could not be restored.</p><Button disabled={busy} onClick={() => void loadSummary()} type="button">Retry audio review</Button></ErrorAlert> : null}
    {data?.deletion ? <ErrorAlert><p>{data.deletion.message}</p><Button disabled={busy} onClick={() => void loadSummary(undefined, false)} type="button">Retry status check</Button></ErrorAlert> : null}
    {!recording ? <label className="audio-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setFile(event.dataTransfer.files[0] ?? null); setError(null); }}><strong>{file ? file.name : "Drop a WAV recording here or choose one"}</strong><input accept="audio/wav,.wav" aria-label="Choose WAV classroom recording" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null); }} type="file" /></label> : <section aria-label="Restored recording"><h3>{recording.original_filename}</h3><p>{recording.mime_type} · {(recording.duration_ms / 1000).toFixed(1)} seconds · {recording.source_status}</p>{audioUrl ? <audio controls preload="metadata" src={audioUrl}>Your browser can play WAV recordings with its audio controls.</audio> : null}</section>}
    <div className="review-actions">{!recording ? <Button disabled={!file || busy} onClick={() => void upload()} type="button">Upload WAV</Button> : null}{recording && (capabilities?.can_start_processing || capabilities?.can_retry_processing) ? <Button disabled={busy} onClick={transcribe} type="button">{capabilities.can_retry_processing ? "Retry transcription" : "Start transcription"}</Button> : null}{recording && capabilities?.can_remove_recording ? <Button disabled={busy} onClick={() => setRemovalPending(true)} type="button">Remove recording</Button> : null}</div>
    {data?.state === "PROCESSING" ? <StatusMessage>Transcription is processing. This page will refresh its status safely.</StatusMessage> : null}
    {data?.latest_job?.status === "FAILED" ? <ErrorAlert><p>{data.latest_job.message ?? "Transcription needs teacher attention."}</p></ErrorAlert> : null}
    {data?.state === "MANUAL_TRANSCRIPT_REQUIRED" ? <StatusMessage>Transcription needs manual entry. Add a teacher-reviewed transcript to continue.</StatusMessage> : null}
    {data?.state === "TRANSCRIPT_APPROVED" ? <StatusMessage>Transcript review complete.</StatusMessage> : null}
    {error ? <ErrorAlert><p>{error}</p><Button disabled={busy} onClick={() => void loadSummary(undefined, false)} type="button">Retry audio review</Button></ErrorAlert> : null}
    {removalPending ? <aside className="manual-editor" aria-label="Confirm recording removal"><p>Remove this recording and all of its transcript work? This is available only before context approval.</p><div className="review-actions"><Button disabled={busy} onClick={remove} type="button">Confirm removal</Button><Button disabled={busy} onClick={() => setRemovalPending(false)} type="button">Cancel</Button></div></aside> : null}
    {revision ? <div className="transcript-review"><p className="provenance-label">{revision.provenance_label}</p><p>Revision {revision.revision_number}{revision.copied_from_transcript_revision_id ? " · New revision based on the previous transcript" : ""} · {revision.teacher_review_status === "APPROVED" ? "Teacher-reviewed and approved" : "Needs teacher review"}</p><ol className="transcript-segments">{revision.segments.map((segment) => <li key={segment.id}><time>{(segment.start_ms / 1000).toFixed(1)}–{(segment.end_ms / 1000).toFixed(1)}s</time><span lang="ml">{segment.text}</span></li>)}</ol>{revision.suggestions.map((suggestion) => <article className="term-suggestion" key={suggestion.id}><p><strong>{suggestion.detected_text}</strong> → {suggestion.canonical_term} {suggestion.malayalam_support_label ? <span lang="ml">/ {suggestion.malayalam_support_label}</span> : null}</p><div className="review-actions"><Button aria-pressed={suggestion.latest_decision === "CONFIRMED"} disabled={busy || !capabilities?.can_edit_transcript} onClick={() => decide(suggestion.id, "CONFIRMED")} type="button">Confirm</Button><Button aria-pressed={suggestion.latest_decision === "REJECTED"} disabled={busy || !capabilities?.can_edit_transcript} onClick={() => decide(suggestion.id, "REJECTED")} type="button">Reject</Button><Button aria-pressed={suggestion.latest_decision === "UNSURE"} disabled={busy || !capabilities?.can_edit_transcript} onClick={() => decide(suggestion.id, "UNSURE")} type="button">Unsure</Button></div></article>)}</div> : null}
    {revision?.quality ? <aside className={`quality-result quality-${revision.quality.quality_status.toLowerCase()}`}><h3>Transcript quality: {revision.quality.quality_status}</h3>{revision.quality.measured_coverage !== null && revision.quality.measured_coverage !== undefined ? <p>Measured timestamp coverage: {Math.round(revision.quality.measured_coverage * 100)}%</p> : null}{revision.quality.reasons.length ? <ul>{revision.quality.reasons.map((reason) => <li key={reason.reason_code}>{reason.reason_code.replaceAll("_", " ")} · {reason.measured_value ?? ""}{reason.threshold !== null ? ` / ${reason.threshold}` : ""}</li>)}</ul> : <p>Timestamp coverage, text, provenance, term review and latest revision checks passed.</p>}</aside> : null}
    {revision || recording ? <div className="review-actions">{revision ? <Button disabled={busy || !capabilities?.can_assess_quality} onClick={assess} type="button">Run quality check</Button> : null}{revision ? <Button disabled={busy || !capabilities?.can_approve_transcript} onClick={approve} type="button">Approve transcript</Button> : null}{capabilities?.can_enter_manual_transcript ? <Button disabled={busy} onClick={beginManualEntry} type="button">Manual transcript correction</Button> : null}</div> : null}
    {editing ? <div className="manual-editor"><h3>{revision ? "Create a corrected transcript revision" : "Add a manual transcript"}</h3><p aria-live="polite" className="sr-only">{segmentAnnouncement}</p>{timestampOrderError ? <ErrorAlert><p>Segment timestamps must follow the displayed order.</p></ErrorAlert> : null}{segments.map((segment, index) => <fieldset key={segment.clientId}><legend>Segment {index + 1}</legend><div className="segment-fields"><label>Start milliseconds<input aria-label={`Segment ${index + 1} start milliseconds`} min="0" onChange={(event) => updateSegment(index, "start_ms", event.target.value)} type="number" value={segment.start_ms} /></label><label>End milliseconds<input aria-label={`Segment ${index + 1} end milliseconds`} min="1" onChange={(event) => updateSegment(index, "end_ms", event.target.value)} type="number" value={segment.end_ms} /></label><label className="segment-text-field">Transcript text<textarea aria-label={`Segment ${index + 1} transcript text`} onChange={(event) => updateSegment(index, "text", event.target.value)} value={segment.text} /></label></div><div className="review-actions segment-actions"><button aria-label={`Move segment ${index + 1} up`} className="button" disabled={busy || index === 0} onClick={() => moveSegment(index, -1)} ref={(element) => { const controls = moveControlRefs.current.get(segment.clientId) ?? { up: null, down: null }; moveControlRefs.current.set(segment.clientId, { ...controls, up: element }); }} type="button">Move up</button><button aria-label={`Move segment ${index + 1} down`} className="button" disabled={busy || index === segments.length - 1} onClick={() => moveSegment(index, 1)} ref={(element) => { const controls = moveControlRefs.current.get(segment.clientId) ?? { up: null, down: null }; moveControlRefs.current.set(segment.clientId, { ...controls, down: element }); }} type="button">Move down</button>{segments.length > 1 ? <Button aria-label={`Remove segment ${index + 1}`} disabled={busy} onClick={() => removeSegment(index)} type="button">Remove</Button> : null}</div></fieldset>)}<div className="review-actions"><Button disabled={busy} onClick={() => { setTimestampOrderError(false); setSegments((current) => [...current, newSegment({ sequence: current.length + 1, start_ms: 0, end_ms: recording?.duration_ms ?? 1000, text: "" })]); }} type="button">Add segment</Button><Button disabled={busy} onClick={saveManual} type="button">Save new transcript revision</Button><Button disabled={busy} onClick={() => setEditing(false)} type="button">Cancel</Button></div></div> : null}
  </section>;
}

function TeacherAudioWorkflow({
  contextVersionId,
  lesson,
}: {
  contextVersionId: string;
  lesson: Lesson;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [jobState, setJobState] = useState<string | null>(null);
  const [revision, setRevision] = useState<TranscriptRevision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [segments, setSegments] = useState<TranscriptSegmentInput[]>([]);
  const [removalPending, setRemovalPending] = useState(false);
  const [busy, setBusy] = useState(false);

  const beginManualEntry = () => {
    const initialSegments = revision
      ? revision.segments.map(({ sequence, start_ms, end_ms, text }) => ({ sequence, start_ms, end_ms, text }))
      : [{ sequence: 1, start_ms: 0, end_ms: recording?.duration_ms ?? 1000, text: "" }];
    setSegments(initialSegments);
    setEditing(true);
  };

  const updateSegment = (index: number, field: keyof TranscriptSegmentInput, value: string) => {
    setSegments((current) => current.map((segment, itemIndex) => {
      if (itemIndex !== index) return segment;
      return { ...segment, [field]: field === "text" ? value : Number(value) };
    }));
  };

  const upload = async () => {
    if (!file || !file.name.toLowerCase().endsWith(".wav")) { setError("Choose a WAV recording to continue."); return; }
    setError(null); setBusy(true); setJobState("Uploading recording");
    try {
      const nextRecording = await curriculumApi.uploadRecording(lesson.id, file);
      setRecording(nextRecording); setJobState("Selected and uploaded");
    } catch { setError("The WAV recording could not be uploaded. Check the file and try again."); } finally { setBusy(false); }
  };
  const transcribe = async () => {
    if (!recording) return;
    setBusy(true); setError(null);
    try {
      const queued = await curriculumApi.requestTranscription(recording.id);
      setJobState(`Queued · ${queued.stage}`);
      setJobState("Transcribing");
      const job = await curriculumApi.runJob(queued.id);
      setJobState(job.status === "SUCCEEDED" ? "Transcript ready · needs review" : "Manual transcript correction needed");
      if (job.resulting_transcript_revision_id) setRevision(await curriculumApi.transcript(job.resulting_transcript_revision_id));
    } catch { setError("Transcription could not be completed. You can add a manual transcript."); } finally { setBusy(false); }
  };
  const decide = async (id: string, decision: string) => { try { setBusy(true); setRevision(await curriculumApi.decideTerm(id, decision)); } catch { setError("The term decision could not be saved."); } finally { setBusy(false); } };
  const assess = async (id = revision?.id) => { if (!id) return; try { setBusy(true); setRevision(await curriculumApi.assessTranscript(id)); } catch { setError("Quality could not be assessed. Try again."); } finally { setBusy(false); } };
  const createManual = async () => {
    if (!revision && !recording) return;
    try {
      setBusy(true);
      const next = revision
        ? await curriculumApi.manualRevision(revision.id, segments)
        : await curriculumApi.recordingManualRevision(recording!.id, segments);
      setRevision(next); setEditing(false); setJobState("New transcript revision needs review");
    } catch { setError("The corrected transcript could not be saved. Check every timestamp and try again."); } finally { setBusy(false); }
  };
  const approve = async () => { if (!revision) return; try { setBusy(true); setRevision(await curriculumApi.approveTranscript(revision.id)); } catch { setError("Transcript approval is blocked until the current quality checks pass."); } finally { setBusy(false); } };
  const remove = async () => {
    if (!recording) return;
    try {
      setBusy(true); await curriculumApi.removeRecording(contextVersionId, recording.id);
      setRecording(null); setRevision(null); setFile(null); setEditing(false); setJobState("Recording removed"); setRemovalPending(false);
    } catch { setError("The recording could not be removed. Try again."); } finally { setBusy(false); }
  };
  return <section className="content-section audio-workflow" aria-labelledby="audio-workflow-title">
    <div><p className="eyebrow">Classroom recording</p><h2 id="audio-workflow-title">Audio-to-trusted-lesson review</h2><p>Upload one local WAV recording. Deterministic demo transcription is clearly labelled and unknown recordings use manual correction.</p></div>
    <label className="audio-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setFile(event.dataTransfer.files[0] ?? null); }}>
      <strong>{file ? file.name : "Drop a WAV recording here or choose one"}</strong><input accept="audio/wav,.wav" aria-label="Choose WAV classroom recording" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" />
    </label>
    <div className="review-actions"><Button disabled={!file || busy} onClick={upload} type="button">Upload WAV</Button>{recording ? <Button disabled={busy} onClick={transcribe} type="button">Start transcription</Button> : null}{recording ? <Button disabled={busy} onClick={() => setRemovalPending(true)} type="button">Remove recording</Button> : null}</div>
    {jobState ? <StatusMessage>{jobState}</StatusMessage> : null}{error ? <ErrorAlert><p>{error}</p></ErrorAlert> : null}
    {removalPending ? <aside className="manual-editor" aria-label="Confirm recording removal"><p>Remove this recording and all of its transcript work? This is available only before context approval.</p><div className="review-actions"><Button disabled={busy} onClick={() => void remove()} type="button">Confirm removal</Button><Button disabled={busy} onClick={() => setRemovalPending(false)} type="button">Cancel</Button></div></aside> : null}
    {revision ? <div className="transcript-review"><p className="provenance-label">{revision.provenance_label}</p><p>Revision {revision.revision_number}{revision.copied_from_transcript_revision_id ? " · New revision based on the previous transcript" : ""} · {revision.teacher_review_status === "APPROVED" ? "Teacher-reviewed and approved" : "Needs teacher review"}</p><audio controls preload="metadata" src={`${apiBaseUrl}/teacher/recordings/${revision.recording_id}/content`}>Your browser can play WAV recordings with its audio controls.</audio><ol className="transcript-segments">{revision.segments.map((segment) => <li key={segment.id}><time>{(segment.start_ms / 1000).toFixed(1)}–{(segment.end_ms / 1000).toFixed(1)}s</time><span lang="ml">{segment.text}</span></li>)}</ol>{revision.suggestions.map((suggestion) => <article className="term-suggestion" key={suggestion.id}><p><strong>{suggestion.detected_text}</strong> → {suggestion.canonical_term} {suggestion.malayalam_support_label ? <span lang="ml">/ {suggestion.malayalam_support_label}</span> : null}</p><div className="review-actions"><Button disabled={busy} onClick={() => void decide(suggestion.id, "CONFIRMED")} type="button">Confirm</Button><Button disabled={busy} onClick={() => void decide(suggestion.id, "REJECTED")} type="button">Reject</Button><Button disabled={busy} onClick={() => void decide(suggestion.id, "UNSURE")} type="button">Unsure</Button></div></article>)}</div> : null}
    {revision?.quality ? <aside className={`quality-result quality-${revision.quality.quality_status.toLowerCase()}`}><h3>Transcript quality: {revision.quality.quality_status}</h3>{revision.quality.reasons.length ? <ul>{revision.quality.reasons.map((reason) => <li key={reason.reason_code}>{reason.reason_code.replaceAll("_", " ")} · {reason.measured_value ?? ""}{reason.threshold !== null ? ` / ${reason.threshold}` : ""}</li>)}</ul> : <p>Timestamp coverage, text, provenance, term review and latest revision checks passed.</p>}</aside> : null}
    {revision || recording ? <div className="review-actions">{revision ? <Button disabled={busy} onClick={() => void assess()} type="button">Run quality check</Button> : null}{revision ? <Button disabled={busy || revision.quality?.quality_status !== "VERIFIED"} onClick={approve} type="button">Approve transcript</Button> : null}<Button disabled={busy} onClick={beginManualEntry} type="button">Manual transcript correction</Button></div> : null}
    {editing ? <div className="manual-editor"><h3>{revision ? "Create a corrected transcript revision" : "Add a manual transcript"}</h3>{segments.map((segment, index) => <fieldset key={index}><legend>Segment {index + 1}</legend><label>Start milliseconds<input aria-label={`Segment ${index + 1} start milliseconds`} min="0" onChange={(event) => updateSegment(index, "start_ms", event.target.value)} type="number" value={segment.start_ms} /></label><label>End milliseconds<input aria-label={`Segment ${index + 1} end milliseconds`} min="1" onChange={(event) => updateSegment(index, "end_ms", event.target.value)} type="number" value={segment.end_ms} /></label><label>Transcript text<textarea aria-label={`Segment ${index + 1} transcript text`} onChange={(event) => updateSegment(index, "text", event.target.value)} value={segment.text} /></label>{segments.length > 1 ? <Button disabled={busy} onClick={() => setSegments((current) => current.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sequence: itemIndex + 1 })))} type="button">Remove segment</Button> : null}</fieldset>)}<div className="review-actions"><Button disabled={busy} onClick={() => setSegments((current) => [...current, { sequence: current.length + 1, start_ms: 0, end_ms: recording?.duration_ms ?? 1000, text: "" }])} type="button">Add segment</Button><Button disabled={busy} onClick={() => void createManual()} type="button">Save new transcript revision</Button><Button disabled={busy} onClick={() => setEditing(false)} type="button">Cancel</Button></div></div> : null}
  </section>;
}

function ConceptFlow({ lesson }: { lesson: Lesson | StudentLesson }) {
  return <ol className="concept-flow">{lesson.concepts.map((concept) => <li key={concept.id}><span className="concept-number">{concept.sequence}</span><Bilingual english={concept.title} malayalam={concept.malayalam_title} /></li>)}</ol>;
}

function QuestionList({ lesson }: { lesson: Lesson | StudentLesson }) {
  return (
    <ol className="question-list">
      {lesson.questions.map((question) => (
        <li key={question.id}>
          <span className="question-source-label">{question.source_label}</span>
          <Bilingual className="question-copy" english={question.question_text} malayalam={question.malayalam_question_text} />
        </li>
      ))}
    </ol>
  );
}

export function StudentLessonPage() {
  const navigate = useNavigate();
  const { curriculumRevision } = useAppContext();
  const [state, setState] = useState<AsyncState<StudentOverview>>({ kind: "loading" });
  const load = useCallback(async (signal?: AbortSignal) => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", data: await curriculumApi.studentOverview(PHOTOSYNTHESIS_DEMO_COURSE_ID, signal) });
    } catch (error) {
      if (!signal?.aborted) setState({ kind: "error", error: safeError(error) });
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const request = async () => {
      try {
        const data = await curriculumApi.studentOverview(PHOTOSYNTHESIS_DEMO_COURSE_ID, controller.signal);
        if (!controller.signal.aborted) setState({ kind: "ready", data });
      } catch (error) {
        if (!controller.signal.aborted) setState({ kind: "error", error: safeError(error) });
      }
    };
    void request();
    return () => controller.abort();
  }, [curriculumRevision]);

  if (state.kind === "loading") return <LoadingState label="Loading your teacher-approved lesson…" />;
  if (state.kind === "error") return <ErrorState error={state.error} onRetry={() => void load()} />;
  if (!state.data.is_ready) return <section className="not-ready-state"><h1>This lesson is being prepared by your teacher.</h1><p>Only reviewed classroom content will appear here.</p></section>;
  const lesson = state.data.chapters[0]?.lessons[0];
  if (!lesson) return <section className="empty-state"><h1>Lesson unavailable</h1><p>There is no approved lesson content to show yet.</p></section>;
  const photosynthesis = lesson.glossary_terms.find((term) => term.canonical_term === "Photosynthesis");
  const chlorophyll = lesson.glossary_terms.find((term) => term.canonical_term === "Chlorophyll");
  const focusKey = focusJourneyStorageKey(state.data);
  const focusSteps = buildFocusJourneySteps(lesson);
  const hasStartedFocusJourney = focusKey !== null && hasStoredFocusJourneyProgress(focusKey, focusSteps);
  return (
    <article className="student-page">
      <header className="student-hero">
        <p className="eyebrow">{state.data.course.title}</p>
        <span className="trust-badge">Teacher-approved lesson</span>
        <h1>{lesson.title}</h1>
        {photosynthesis?.malayalam_support_label ? <p className="hero-malayalam" lang="ml">{photosynthesis.malayalam_support_label}</p> : null}
        <p className="trusted-version">Trusted version {state.data.version_number}</p>
      </header>
      {lesson.approved_transcript ? <section className="student-section approved-transcript" aria-labelledby="approved-transcript-title"><div><p className="eyebrow">Trusted classroom record</p><h2 id="approved-transcript-title">Approved classroom transcript</h2><p>{lesson.approved_transcript.provenance_label}</p><p>Trusted classroom record · version {lesson.approved_transcript.trusted_context_version}</p></div><ol className="transcript-segments">{lesson.approved_transcript.segments.map((segment) => <li key={segment.id}><time>{(segment.start_ms / 1000).toFixed(1)}–{(segment.end_ms / 1000).toFixed(1)}s</time><span lang="ml">{segment.text.includes("Chlorophyll") ? <><a href="#glossary-chlorophyll" className="glossary-link">{segment.text}</a></> : segment.text}</span></li>)}</ol></section> : null}
      <section className="student-section orientation"><h2>Lesson orientation</h2><p className="pre-line">{lesson.description}</p><h3>What you will learn</h3><ol className="stack-list">{lesson.objectives.map((objective) => <li key={objective.id}><Bilingual english={objective.objective_text} malayalam={objective.malayalam_text} /></li>)}</ol></section>
      <section className="student-section focus-entry" aria-labelledby="focus-entry-title">
        <p className="eyebrow">Step-by-step support</p>
        <h2 id="focus-entry-title">Help me focus</h2>
        <p>Learn this lesson one small step at a time.</p>
        <p className="quiet-copy">Designed to reduce information load and support step-by-step learning.</p>
        <Button onClick={() => navigate("/student/focus")} type="button">{hasStartedFocusJourney ? "Resume Focus Journey" : "Start Focus Journey"}</Button>
      </section>
      <section className="student-section"><h2>Trusted explanation</h2><div className="material-grid">{lesson.approved_materials.map((material) => <article className="material-card" key={material.id}><p className="eyebrow">{material.material_type === "teacher_note" ? "Teacher explanation" : "Reference support"}</p><h3>{material.title}</h3><p className="pre-line">{material.content}</p></article>)}</div></section>
      <section className="student-section"><h2>Glossary</h2><div className="glossary-grid">{lesson.glossary_terms.map((term) => <article className="glossary-card" id={term.canonical_term === "Chlorophyll" ? "glossary-chlorophyll" : undefined} key={term.id}><h3><Bilingual english={term.canonical_term} malayalam={term.malayalam_support_label} /></h3><p>{term.definition}</p></article>)}</div>{chlorophyll ? <aside className="term-correction"><h3>Confirmed classroom term</h3><p><strong>{chlorophyll.canonical_term}</strong></p>{chlorophyll.malayalam_support_label ? <p>Malayalam: <strong lang="ml">{chlorophyll.malayalam_support_label}</strong></p> : null}</aside> : null}</section>
      <section className="student-section"><h2>Concept flow</h2><p>Follow the lesson from what plants need to the oxygen they release.</p><ConceptFlow lesson={lesson} /></section>
      <section className="student-section"><h2>Question Explorer</h2><p>Use these teacher-approved questions to notice what the lesson asks you to explain.</p><QuestionList lesson={lesson} /></section>
    </article>
  );
}

export function FocusJourneyPage() {
  const navigate = useNavigate();
  const { curriculumRevision } = useAppContext();
  const [state, setState] = useState<AsyncState<StudentOverview>>({ kind: "loading" });
  const [progress, setProgress] = useState<FocusJourneyProgress>(() => newFocusJourneyProgress());
  const [restartRequested, setRestartRequested] = useState(false);
  const [persistenceUnavailable, setPersistenceUnavailable] = useState(false);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const requestOverview = useCallback(async (signal?: AbortSignal) => {
    const data = await curriculumApi.studentOverview(PHOTOSYNTHESIS_DEMO_COURSE_ID, signal);
    const approvedLesson = data.chapters[0]?.lessons[0];
    const approvedSteps = approvedLesson ? buildFocusJourneySteps(approvedLesson) : [];
    const approvedKey = focusJourneyStorageKey(data);
    const stored = approvedKey && approvedSteps.length > 0 ? readFocusJourneyProgress(approvedKey, approvedSteps) : null;
    return {
      data,
      progress: stored?.progress ?? newFocusJourneyProgress(approvedKey ?? ""),
      persistenceAvailable: stored?.persistenceAvailable ?? true,
    };
  }, []);

  const load = async () => {
    setState({ kind: "loading" });
    try {
      const result = await requestOverview();
      setProgress(result.progress);
      setPersistenceUnavailable(!result.persistenceAvailable);
      setRestartRequested(false);
      setState({ kind: "ready", data: result.data });
    } catch (error) {
      setState({ kind: "error", error: safeError(error) });
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const request = async () => {
      try {
        const result = await requestOverview(controller.signal);
        if (!controller.signal.aborted) {
          setProgress(result.progress);
          setPersistenceUnavailable(!result.persistenceAvailable);
          setRestartRequested(false);
          setState({ kind: "ready", data: result.data });
        }
      } catch (error) {
        if (!controller.signal.aborted) setState({ kind: "error", error: safeError(error) });
      }
    };
    void request();
    return () => controller.abort();
  }, [curriculumRevision, requestOverview]);

  const lesson = state.kind === "ready" ? state.data.chapters[0]?.lessons[0] : undefined;
  const steps = useMemo(() => lesson ? buildFocusJourneySteps(lesson) : [], [lesson]);
  const storageKey = state.kind === "ready" ? focusJourneyStorageKey(state.data) : null;

  useEffect(() => {
    if (state.kind === "ready" && steps.length > 0 && progress.screen === "concept" && !progress.paused && !progress.isComplete) {
      stepHeadingRef.current?.focus();
    }
  }, [progress.currentStepIndex, progress.isComplete, progress.paused, progress.screen, state.kind, steps.length]);

  const updateProgress = (update: (current: FocusJourneyProgress) => FocusJourneyProgress) => {
    if (!storageKey) return;
    setProgress((current) => {
      const next = { ...update(current), lastUpdated: new Date().toISOString() };
      if (!saveFocusJourneyProgress(storageKey, next)) setPersistenceUnavailable(true);
      return next;
    });
  };

  if (state.kind === "loading") return <LoadingState label="Loading your Focus Journey…" />;
  if (state.kind === "error") return <ErrorState error={state.error} onRetry={() => void load()} />;
  if (!state.data.is_ready || !lesson || !storageKey || steps.length !== 5) {
    return <section className="empty-state focus-empty-state"><h1>Focus Journey unavailable</h1><p>Your teacher-approved lesson is not ready for this pathway yet.</p><Button onClick={() => navigate("/student")} type="button">Return to full lesson</Button></section>;
  }

  const chooseSupport = (supportMode: FocusSupportMode) => {
    updateProgress((current) => ({ ...current, supportMode, screen: "support-choice", paused: false }));
  };

  if (progress.screen === "support-choice") {
    return (
      <article className="focus-journey focus-support-choice" aria-labelledby="focus-support-title">
        <section className="focus-step-card">
          <p className="eyebrow">FOCUS JOURNEY</p>
          <h1 id="focus-support-title">How should Shravya support you right now?</h1>
          <p>Choose what would make this lesson easier to follow.<br />You can change this at any time.</p>
          <fieldset className="focus-support-options" aria-describedby="focus-support-reassurance">
            <legend className="sr-only">Choose one support option</legend>
            {FOCUS_SUPPORT_OPTIONS.map((option) => (
              <label className="focus-support-option" key={option.mode}>
                <input checked={progress.supportMode === option.mode} name="focus-support" onChange={() => chooseSupport(option.mode)} type="radio" value={option.mode} />
                <span><strong>{option.label}</strong>{" "}<small>{option.description}</small></span>
              </label>
            ))}
          </fieldset>
          <p className="focus-reassurance" id="focus-support-reassurance">Shravya responds to what helps you learn today.<br />It does not ask for or store a diagnosis.</p>
          <Button disabled={progress.supportMode === null} onClick={() => updateProgress((current) => ({ ...current, screen: "journey-preview" }))} type="button">Continue with this support</Button>
        </section>
      </article>
    );
  }

  const support = FOCUS_SUPPORT_OPTIONS.find((option) => option.mode === progress.supportMode);
  if (progress.screen === "journey-preview" && support) {
    return (
      <article className="focus-journey focus-journey-preview" aria-labelledby="focus-preview-title">
        <section className="focus-step-card">
          <p className="eyebrow">YOUR LEARNING PATH</p>
          <h1 id="focus-preview-title">{lesson.title}</h1>
          <p className="focus-selected-support">Support: {support.label}</p>
          <Button className="focus-secondary-action" onClick={() => updateProgress((current) => ({ ...current, screen: "support-choice" }))} type="button">Change support</Button>
          <section aria-labelledby="focus-preview-steps-title" className="focus-preview-steps">
            <h2 id="focus-preview-steps-title">5 small steps</h2>
            <ol>{steps.map((item, index) => <li key={item.id}><span>{index === 0 ? "Now" : index === 1 ? "Next" : "Later"}</span><strong>{item.concept.title}</strong>{item.concept.malayalam_title ? <small lang="ml">{item.concept.malayalam_title}</small> : null}</li>)}</ol>
          </section>
          <section aria-labelledby="focus-preview-what-title" className="focus-preview-what">
            <h2 id="focus-preview-what-title">In each step, you will:</h2>
            <ul><li>Learn one idea</li><li>Try one small question</li><li>Choose whether to continue, revisit or pause</li></ul>
          </section>
          <div className="focus-actions">
            <Button onClick={() => updateProgress((current) => ({ ...current, currentStepIndex: 0, isComplete: false, paused: false, screen: "concept" }))} type="button">Start with step 1</Button>
            <Button className="focus-secondary-action" onClick={() => navigate("/student")} type="button">Return to lesson</Button>
          </div>
        </section>
      </article>
    );
  }

  const step = steps[Math.min(progress.currentStepIndex, steps.length - 1)];
  const selectedAnswer = progress.selectedAnswers[step.id];
  const answerIsCorrect = selectedAnswer === step.check.correctAnswer;
  const selectAnswer = (answer: string) => {
    const isCorrect = answer === step.check.correctAnswer;
    updateProgress((current) => {
      const completedStepIds = isCorrect
        ? [...new Set([...current.completedStepIds, step.id])]
        : current.completedStepIds.filter((stepId) => stepId !== step.id);
      return {
        ...current,
        selectedAnswers: { ...current.selectedAnswers, [step.id]: answer },
        correctAnswers: isCorrect
          ? { ...current.correctAnswers, [step.id]: answer }
          : Object.fromEntries(Object.entries(current.correctAnswers).filter(([stepId]) => stepId !== step.id)),
        completedStepIds,
        isComplete: isCorrect && current.currentStepIndex === steps.length - 1 && completedStepIds.length === steps.length,
        screen: isCorrect && current.currentStepIndex === steps.length - 1 && completedStepIds.length === steps.length ? "complete" : current.screen,
      };
    });
  };

  const restartJourney = () => {
    const fresh = { ...newFocusJourneyProgress(storageKey), supportMode: progress.supportMode, screen: "journey-preview" as const };
    const cleared = clearFocusJourneyProgress(storageKey);
    const saved = saveFocusJourneyProgress(storageKey, fresh);
    if (!cleared || !saved) setPersistenceUnavailable(true);
    setProgress(fresh);
    setRestartRequested(false);
  };

  if (progress.screen === "complete" && progress.isComplete) {
    return (
      <article className="focus-journey" aria-labelledby="focus-complete-title">
        <section className="focus-step-card focus-completion">
          <p className="eyebrow">Focus Journey</p>
          <h1 id="focus-complete-title">Journey complete</h1>
          <p>You explored the lesson one step at a time.</p>
          <p className="quiet-copy">{persistenceUnavailable ? "Progress is being kept for this visit only because device storage is unavailable." : "Progress is saved on this device."}</p>
          <div className="focus-actions">
            <Button onClick={() => updateProgress((current) => ({ ...current, currentStepIndex: 0, isComplete: false, paused: false, screen: "concept" }))} type="button">Review this journey</Button>
            <Button className="focus-secondary-action" onClick={() => updateProgress((current) => ({ ...current, screen: "support-choice", paused: false }))} type="button">Change support</Button>
            <Button onClick={() => navigate("/student")} type="button">Return to full lesson</Button>
          </div>
        </section>
      </article>
    );
  }

  if (progress.paused) {
    return (
      <article className="focus-journey" aria-labelledby="focus-paused-title">
        <section className="focus-step-card focus-paused">
          <p className="eyebrow">Focus Journey · Step {progress.currentStepIndex + 1} of {steps.length}</p>
          <h1 id="focus-paused-title" tabIndex={-1}>Journey paused</h1>
          <p role="status">Your place is saved. Resume when you are ready.</p>
          <p className="quiet-copy">{persistenceUnavailable ? "Progress is being kept for this visit only because device storage is unavailable." : "Progress is saved on this device."}</p>
          <div className="focus-actions">
            <Button onClick={() => updateProgress((current) => ({ ...current, paused: false }))} type="button">Resume journey</Button>
            <Button className="focus-secondary-action" onClick={() => updateProgress((current) => ({ ...current, screen: "support-choice", paused: false }))} type="button">Change support</Button>
            <Button onClick={() => navigate("/student")} type="button">Exit to lesson</Button>
          </div>
        </section>
      </article>
    );
  }

  return (
    <article className="focus-journey" aria-labelledby="focus-step-title">
      <header className="focus-journey-header">
        <p className="eyebrow">Focus Journey</p>
        <p className="focus-progress-copy">Step {progress.currentStepIndex + 1} of {steps.length}</p>
        <div aria-label={`Focus Journey progress: Step ${progress.currentStepIndex + 1} of ${steps.length}`} aria-valuemax={steps.length} aria-valuemin={1} aria-valuenow={progress.currentStepIndex + 1} className="focus-progress" role="progressbar"><span style={{ width: `${((progress.currentStepIndex + 1) / steps.length) * 100}%` }} /></div>
        <p className="quiet-copy">{persistenceUnavailable ? "Progress is being kept for this visit only because device storage is unavailable." : "Progress is saved on this device."}</p>
      </header>
      <section className="focus-step-card">
        <h1 id="focus-step-title" ref={stepHeadingRef} tabIndex={-1}>{step.concept.title}</h1>
        {step.concept.malayalam_title ? <p className="focus-malayalam" lang="ml">{step.concept.malayalam_title}</p> : null}
        <p className="focus-explanation">{step.explanation}</p>
        <section aria-labelledby={`terms-${step.id}`} className="focus-terms">
          <h2 id={`terms-${step.id}`}>Key terms</h2>
          <ul>{step.terms.map((term) => <li key={term.id}><strong>{term.canonical_term}</strong>{term.malayalam_support_label ? <span lang="ml">{term.malayalam_support_label}</span> : null}</li>)}</ul>
        </section>
        <fieldset className="focus-check">
          <legend>{step.check.prompt}</legend>
          {step.check.options.map((option) => <label key={option} className="focus-answer-option"><input checked={selectedAnswer === option} name={`focus-check-${step.id}`} onChange={() => selectAnswer(option)} type="radio" value={option} /><span>{option}</span></label>)}
        </fieldset>
        {selectedAnswer ? <p aria-live="polite" className={`focus-feedback ${answerIsCorrect ? "correct" : "incorrect"}`} role="status">{answerIsCorrect ? "That’s right. You can continue when you’re ready." : "Not quite. Look at the explanation once more and try again."}</p> : null}
        <div className="focus-actions focus-step-actions">
          <Button disabled={progress.currentStepIndex === 0} onClick={() => updateProgress((current) => ({ ...current, currentStepIndex: Math.max(0, current.currentStepIndex - 1) }))} type="button">Back</Button>
          <Button disabled={!answerIsCorrect} onClick={() => updateProgress((current) => current.currentStepIndex === steps.length - 1 ? { ...current, isComplete: true, screen: "complete" } : { ...current, currentStepIndex: current.currentStepIndex + 1 })} type="button">Continue</Button>
          <Button onClick={() => updateProgress((current) => ({ ...current, paused: true }))} type="button">Pause journey</Button>
          <Button className="focus-secondary-action" onClick={() => updateProgress((current) => ({ ...current, screen: "support-choice", paused: false }))} type="button">Change support</Button>
          <Button onClick={() => navigate("/student")} type="button">Exit to full lesson</Button>
        </div>
        <div className="focus-restart">
          {restartRequested ? <section aria-labelledby="restart-confirm-title" className="focus-restart-confirm" role="dialog"><h2 id="restart-confirm-title">Restart journey?</h2><p>This clears only this lesson’s saved Focus Journey on this device.</p><div className="focus-actions"><Button onClick={restartJourney} type="button">Confirm restart</Button><Button onClick={() => setRestartRequested(false)} type="button">Keep my progress</Button></div></section> : <Button onClick={() => setRestartRequested(true)} type="button">Restart journey</Button>}
        </div>
      </section>
    </article>
  );
}
