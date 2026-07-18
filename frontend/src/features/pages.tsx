import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, curriculumApi } from "../api/client";
import type { Completeness, ContextDetail, ContextSummary, Lesson, StudentOverview } from "../api/contracts";
import { useAppContext } from "../app/AppContext";
import { Button, ErrorAlert, StatusMessage } from "../components/primitives";
import { PHOTOSYNTHESIS_DEMO_COURSE_ID } from "../demo/config";

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
            {workspace.kind === "ready" ? <TeacherContextDetail completeness={workspace.data.completeness} detail={workspace.data.detail} events={workspace.data.events} onApprove={approve} onSubmit={submit} pending={pending} /> : null}
          </section>
        </div>
      ) : null}
    </article>
  );
}

function TeacherContextDetail({ detail, completeness, events, pending, onSubmit, onApprove }: { detail: ContextDetail; completeness: Completeness; events: ContextDetail["review_events"]; pending: "submit" | "approve" | null; onSubmit: () => void; onApprove: () => void }) {
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
      <section className="content-section"><h2>Learning objectives</h2><ol className="stack-list">{lesson.objectives.map((objective) => <li key={objective.id}><Bilingual english={objective.objective_text} malayalam={objective.malayalam_text} /></li>)}</ol></section>
      <section className="content-section"><h2>Approved learning materials</h2><div className="material-grid">{lesson.approved_materials.map((material) => <article className="material-card" key={material.id}><h3>{material.title}</h3><p className="material-source">{material.source_label}</p><p className="pre-line">{material.content}</p></article>)}</div></section>
      <section className="content-section"><h2>Glossary</h2><div className="glossary-grid">{lesson.glossary_terms.map((term) => <article className="glossary-card" key={term.id}><h3><Bilingual english={term.canonical_term} malayalam={term.malayalam_support_label} /></h3><p>{term.definition}</p></article>)}</div></section>
      <section className="content-section"><h2>Concept flow</h2><ConceptFlow lesson={lesson} /></section>
      <section className="content-section"><h2>Practice questions</h2><QuestionList lesson={lesson} /></section>
      <section className="content-section review-history"><h2>Review history</h2><ol className="timeline">{events.map((event) => <li key={event.id}><strong>{eventLabel[event.event_type] ?? "Review activity"}</strong><span>{formatDate(event.created_at)}</span></li>)}</ol></section>
    </>
  );
}

function ConceptFlow({ lesson }: { lesson: Lesson }) {
  return <ol className="concept-flow">{lesson.concepts.map((concept) => <li key={concept.id}><span className="concept-number">{concept.sequence}</span><Bilingual english={concept.title} malayalam={concept.malayalam_title} /></li>)}</ol>;
}

function QuestionList({ lesson }: { lesson: Lesson }) {
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
  const correction = lesson.glossary_terms.flatMap((term) => term.misrecognitions.map((item) => ({ term, item }))).find(({ item }) => item.detected_text.toLowerCase() === "chlorophil");
  return (
    <article className="student-page">
      <header className="student-hero">
        <p className="eyebrow">{state.data.course.title}</p>
        <span className="trust-badge">Teacher-approved lesson</span>
        <h1>{lesson.title}</h1>
        {photosynthesis?.malayalam_support_label ? <p className="hero-malayalam" lang="ml">{photosynthesis.malayalam_support_label}</p> : null}
        <p className="trusted-version">Trusted version {state.data.version_number}</p>
      </header>
      <section className="student-section orientation"><h2>Lesson orientation</h2><p className="pre-line">{lesson.description}</p><h3>What you will learn</h3><ol className="stack-list">{lesson.objectives.map((objective) => <li key={objective.id}><Bilingual english={objective.objective_text} malayalam={objective.malayalam_text} /></li>)}</ol></section>
      <section className="student-section"><h2>Trusted explanation</h2><div className="material-grid">{lesson.approved_materials.map((material) => <article className="material-card" key={material.id}><p className="eyebrow">{material.material_type === "teacher_note" ? "Teacher explanation" : "Reference support"}</p><h3>{material.title}</h3><p className="pre-line">{material.content}</p></article>)}</div></section>
      <section className="student-section"><h2>Glossary</h2><div className="glossary-grid">{lesson.glossary_terms.map((term) => <article className="glossary-card" key={term.id}><h3><Bilingual english={term.canonical_term} malayalam={term.malayalam_support_label} /></h3><p>{term.definition}</p></article>)}</div>{correction ? <aside className="term-correction"><h3>Classroom term check</h3><p>Heard as: <strong>{correction.item.detected_text}</strong></p><p>Confirmed term: <strong>{correction.term.canonical_term}</strong></p><p>Malayalam: <strong lang="ml">{correction.term.malayalam_support_label}</strong></p></aside> : null}{!correction && chlorophyll ? <aside className="term-correction"><h3>Classroom term check</h3><p>Confirmed term: <strong>{chlorophyll.canonical_term}</strong></p></aside> : null}</section>
      <section className="student-section"><h2>Concept flow</h2><p>Follow the lesson from what plants need to the oxygen they release.</p><ConceptFlow lesson={lesson} /></section>
      <section className="student-section"><h2>Question Explorer</h2><p>Use these teacher-approved questions to notice what the lesson asks you to explain.</p><QuestionList lesson={lesson} /></section>
    </article>
  );
}
