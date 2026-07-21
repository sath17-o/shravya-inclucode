import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProvider } from "../app/AppContext";
import type { AudioWorkflowSummary } from "../api/contracts";
import { createCurriculumFetch } from "./curriculumFixtures";

function renderApp(initialEntry: "/teacher" | "/student", fetchMock = createCurriculumFetch()) {
  vi.stubGlobal("fetch", fetchMock);
  return render(<MemoryRouter initialEntries={[initialEntry]}><AppProvider><App /></AppProvider></MemoryRouter>);
}

afterEach(() => vi.unstubAllGlobals());

function timelineSummary(state: AudioWorkflowSummary["state"]): AudioWorkflowSummary {
  const hasRecording = state !== "NO_RECORDING";
  const hasRevision = ["NEEDS_REVIEW", "QUALITY_BLOCKED", "QUALITY_VERIFIED", "TRANSCRIPT_APPROVED"].includes(state);
  return {
    context_version_id: "context-v2",
    state,
    recording: hasRecording ? { id: "recording-1", original_filename: "photosynthesis-demo.wav", mime_type: "audio/wav", duration_ms: 19400, source_status: "DEMO", created_at: "2026-07-16T09:00:00Z", content_url: "/api/v1/teacher/recordings/recording-1/content" } : null,
    latest_job: state === "PROCESSING_FAILED" ? { id: "job-1", status: "FAILED", stage: "Transcription", recoverable: true, error_code: "DEMO_FAILURE", message: "Transcription needs teacher attention." } : state === "PROCESSING" ? { id: "job-1", status: "RUNNING", stage: "Transcribing", recoverable: false, error_code: null, message: null } : null,
    latest_revision: hasRevision ? {
      id: "revision-1", recording_id: "recording-1", revision_number: 1, copied_from_transcript_revision_id: null, source_status: "DEMO", provider_name: "demo", provider_version: "phase-3b", provenance_label: "Deterministic offline demo transcription", teacher_review_status: state === "TRANSCRIPT_APPROVED" ? "APPROVED" : "DRAFT", approved_at: state === "TRANSCRIPT_APPROVED" ? "2026-07-16T09:05:00Z" : null,
      segments: [{ id: "segment-1", sequence: 1, start_ms: 0, end_ms: 7654, text: "Plants need water." }], suggestions: [], quality: null,
    } : null,
    deletion: state === "REMOVAL_PENDING" ? { status: "PENDING", recoverable: true, message: "Recording cleanup is in progress." } : null,
    capabilities: { can_start_processing: state === "UPLOADED", can_retry_processing: state === "PROCESSING_FAILED", can_enter_manual_transcript: hasRecording, can_edit_transcript: hasRevision, can_assess_quality: hasRevision, can_approve_transcript: state === "QUALITY_VERIFIED", can_remove_recording: hasRecording },
  };
}

async function openTeacherAudio(summary: AudioWorkflowSummary) {
  const view = renderApp("/teacher", createCurriculumFetch({ audioWorkflow: (contextId) => contextId === "context-v2" ? summary : { ...summary, context_version_id: contextId, state: "NO_RECORDING", recording: null, latest_job: null, latest_revision: null } }));
  await userEvent.setup().click(await screen.findByRole("button", { name: /Version 2/ }));
  return view;
}

describe("Phase 3A curriculum experience", () => {
  it("derives the Student controls from the student route", async () => {
    renderApp("/student");
    await screen.findByRole("heading", { name: "Photosynthesis in Plants" });
    const roleSwitcher = screen.getByRole("group", { name: "Demo role switcher" });
    expect(within(roleSwitcher).getByRole("button", { name: "Student" })).toHaveAttribute("aria-pressed", "true");
    expect(within(roleSwitcher).getByRole("button", { name: "Teacher" })).toHaveAttribute("aria-pressed", "false");
    expect(within(roleSwitcher).getAllByRole("button", { pressed: true })).toHaveLength(1);
    const navigation = screen.getByRole("navigation", { name: "Primary" });
    expect(within(navigation).getByRole("link", { name: "Student lesson" })).toHaveClass("active");
    expect(within(navigation).getByRole("link", { name: "Teacher review" })).not.toHaveClass("active");
  });

  it("derives the Teacher controls from the teacher route", async () => {
    renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    const roleSwitcher = screen.getByRole("group", { name: "Demo role switcher" });
    expect(within(roleSwitcher).getByRole("button", { name: "Teacher" })).toHaveAttribute("aria-pressed", "true");
    expect(within(roleSwitcher).getByRole("button", { name: "Student" })).toHaveAttribute("aria-pressed", "false");
    expect(within(roleSwitcher).getAllByRole("button", { pressed: true })).toHaveLength(1);
    const navigation = screen.getByRole("navigation", { name: "Primary" });
    expect(within(navigation).getByRole("link", { name: "Teacher review" })).toHaveClass("active");
    expect(within(navigation).getByRole("link", { name: "Student lesson" })).not.toHaveClass("active");
  });

  it("keeps the skip link keyboard reachable", async () => {
    const user = userEvent.setup();
    renderApp("/student");
    const skipLink = screen.getByRole("link", { name: "Skip to lesson content" });
    expect(skipLink).toHaveClass("skip-link");
    await user.tab();
    expect(skipLink).toHaveFocus();
  });

  it("renders the teacher baseline with approved v1, hidden Draft v2, and review readiness", async () => {
    renderApp("/teacher");
    expect(await screen.findByRole("heading", { name: "Teacher Review Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Version 1/ })).toHaveTextContent("Approved");
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Draft");
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Hidden from students until submitted and approved");
    expect(await screen.findByText("Ready for teacher review")).toBeInTheDocument();
  });

  it("keeps Needs Review hidden without calling it an earlier approved version", async () => {
    renderApp("/teacher", createCurriculumFetch({ initialV2Status: "NEEDS_REVIEW" }));
    const versionTwo = await screen.findByRole("button", { name: /Version 2/ });
    expect(versionTwo).toHaveTextContent("Needs review");
    expect(versionTwo).toHaveTextContent("Awaiting teacher approval · hidden from students");
    expect(versionTwo).not.toHaveTextContent("Earlier approved version");
    expect(versionTwo).not.toHaveTextContent("Currently visible to students");
  });

  it("never renders internal copied-from review metadata in the timeline", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    expect(await screen.findByRole("heading", { name: "Review history" })).toBeInTheDocument();
    expect(screen.queryByText(/copied_from:/)).not.toBeInTheDocument();
    expect(screen.queryByText("f069db92-d848-5546-b3ad-3b10ee301600")).not.toBeInTheDocument();
  });

  it("submits Draft v2 and then reports the returned stale-artifact count on approval", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await screen.findByRole("button", { name: "Submit for review" });
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    expect(await screen.findByText("Context submitted for teacher review.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Approve trusted version" }));
    expect(await screen.findByText("New trusted version approved. 1 older learning artifact marked stale.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Currently visible to students");
  });

  it("offers a guarded retry action when submitting a context fails recoverably", async () => {
    const user = userEvent.setup();
    const fetchMock = createCurriculumFetch({ failSubmitOnce: true });
    renderApp("/teacher", fetchMock);
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    const retryButton = await screen.findByRole("button", { name: "Try submitting again" });
    expect(retryButton).toBeEnabled();
    await user.click(retryButton);
    expect(await screen.findByText("Context submitted for teacher review.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").length).toBe(2);
  });

  it("shows the approved-only student baseline and exact Malayalam support", async () => {
    renderApp("/student");
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
    expect(screen.getByText("Trusted version 1")).toBeInTheDocument();
    expect(screen.getAllByText("പ്രകാശസംശ്ലേഷണം").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ക്ലോറോഫിൽ").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Confirmed classroom term" })).toBeInTheDocument();
    expect(screen.getAllByText("Chlorophyll")[0]).toBeInTheDocument();
    expect(screen.queryByText("chlorophil", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirm|Reject|Unsure/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Improved teacher explanation")).not.toBeInTheDocument();
    expect(screen.getByText("Follow the lesson from what plants need to the oxygen they release.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Question Explorer" })).toBeInTheDocument();
    expect(screen.queryByText(/Visual Story later|Question Explorer preview|Phase 3/)).not.toBeInTheDocument();
  });

  it("shows only a teacher-approved transcript and links corrected Chlorophyll to the glossary", async () => {
    renderApp("/student", createCurriculumFetch({ approvedTranscript: true }));
    expect(await screen.findByRole("heading", { name: "Approved classroom transcript" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Deterministic offline demo transcript mapped to a team-recorded Malayalam/code-mixed lesson — not live STT.",
      ),
    ).toBeInTheDocument();
    const corrected = screen.getByRole("link", { name: /Chlorophyll/ });
    expect(corrected).toHaveAttribute("href", "#glossary-chlorophyll");
    expect(screen.queryByText("chlorophil", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Teacher-reviewed status", { exact: false })).not.toBeInTheDocument();
    expect(screen.getByText("Trusted classroom record · version 1")).toBeInTheDocument();
  });

  it("reconstructs every durable recording milestone with text, markers, and ordered-list semantics", async () => {
    const cases: Array<[AudioWorkflowSummary["state"], string[]]> = [
      ["NO_RECORDING", ["Not started", "Not started", "Not started", "Not started", "Not started"]],
      ["UPLOADED", ["Complete", "Complete", "Not started", "Not started", "Not started"]],
      ["PROCESSING", ["Complete", "Complete", "Current", "Not started", "Not started"]],
      ["PROCESSING_FAILED", ["Complete", "Complete", "Failed", "Not started", "Not started"]],
      ["MANUAL_TRANSCRIPT_REQUIRED", ["Complete", "Complete", "Failed", "Not started", "Not started"]],
      ["NEEDS_REVIEW", ["Complete", "Complete", "Complete", "Complete", "Current"]],
      ["QUALITY_BLOCKED", ["Complete", "Complete", "Complete", "Complete", "Current"]],
      ["QUALITY_VERIFIED", ["Complete", "Complete", "Complete", "Complete", "Current"]],
      ["TRANSCRIPT_APPROVED", ["Complete", "Complete", "Complete", "Complete", "Complete"]],
    ];
    const milestoneNames = ["Selected", "Uploading", "Transcribing", "Transcript ready", "Needs review"];
    for (const [state, expectedStatuses] of cases) {
      const view = await openTeacherAudio(timelineSummary(state));
      const region = screen.getByRole("region", { name: "Recording workflow" });
      const list = within(region).getByRole("list");
      expect(within(list).getAllByRole("listitem")).toHaveLength(5);
      for (const [index, expectedStatus] of expectedStatuses.entries()) {
        const item = within(list).getByText(milestoneNames[index]).closest("li");
        await waitFor(() => expect(item).toHaveTextContent(expectedStatus));
        expect(within(item!).getByText(/[○→✓!]/)).toBeInTheDocument();
        if (expectedStatus === "Current") expect(item).toHaveAttribute("aria-current", "step");
      }
      view.unmount();
    }
  });

  it("shows Selected and Uploading only while their local action state is active", async () => {
    const user = userEvent.setup();
    const baseFetch = createCurriculumFetch();
    let completeUpload: (() => void) | undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/recordings") && init?.method === "POST") {
        return new Promise<Response>((resolve) => {
          completeUpload = () => resolve(new Response(JSON.stringify({ status: "success", data: { id: "recording-1", lesson_id: "lesson-2", original_filename: "demo.wav", mime_type: "audio/wav", byte_size: 12, sha256: "a".repeat(64), duration_ms: 9000, source_status: "DEMO", workflow_status: "UPLOADED" } }), { status: 200, headers: { "content-type": "application/json" } }));
        });
      }
      return baseFetch(input, init);
    });
    renderApp("/teacher", fetchMock);
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await user.upload(screen.getByLabelText("Choose WAV classroom recording"), new File(["wav"], "demo.wav", { type: "audio/wav" }));
    const timeline = screen.getByRole("region", { name: "Recording workflow" });
    expect(within(timeline).getByText("Selected").closest("li")).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: "Upload WAV" }));
    await waitFor(() => expect(within(timeline).getByText("Uploading").closest("li")).toHaveAttribute("aria-current", "step"));
    completeUpload?.();
    await waitFor(() => expect(within(timeline).getByText("Uploading").closest("li")).not.toHaveAttribute("aria-current", "step"));
  });

  it("does not expose ordering controls on the immutable approved transcript display", async () => {
    const view = await openTeacherAudio(timelineSummary("TRANSCRIPT_APPROVED"));
    expect((await screen.findAllByText("Transcript review complete.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toHaveTextContent("Transcript review complete.");
    expect(screen.queryByRole("button", { name: /Move segment/ })).not.toBeInTheDocument();
    view.unmount();
  });

  it("edits the actual chlorophil segment when creating a manual transcript revision", async () => {
    const user = userEvent.setup();
    const baseFetch = createCurriculumFetch();
    const revision = {
      id: "revision-1", recording_id: "recording-1", revision_number: 1,
      copied_from_transcript_revision_id: null as string | null, source_status: "DEMO", provider_name: "demo", provider_version: "phase-3b",
      provenance_label: "Deterministic demo transcription", teacher_review_status: "DRAFT", approved_at: null,
      segments: [
        { id: "segment-1", sequence: 1, start_ms: 0, end_ms: 3000, text: "Plants need water." },
        { id: "segment-2", sequence: 2, start_ms: 3000, end_ms: 6000, text: "Leaf chlorophil captures light." },
      ],
      suggestions: [{ id: "suggestion-1", transcript_segment_id: "segment-2", glossary_term_id: "term-2", detected_text: "chlorophil", canonical_term: "Chlorophyll", malayalam_support_label: "ക്ലോറോഫിൽ", latest_decision: null }], quality: null,
    };
    let workflowStage: "NONE" | "UPLOADED" | "READY" = "NONE";
    let activeRevision = revision;
    const workflowSummary = (contextVersionId: string) => ({
      context_version_id: contextVersionId,
      state: workflowStage === "NONE" ? "NO_RECORDING" : workflowStage === "UPLOADED" ? "UPLOADED" : "NEEDS_REVIEW",
      recording: workflowStage === "NONE" ? null : { id: "recording-1", original_filename: "demo.wav", mime_type: "audio/wav", duration_ms: 9000, source_status: "DEMO", created_at: "2026-07-16T09:00:00Z", content_url: "/api/v1/teacher/recordings/recording-1/content" },
      latest_job: null,
      latest_revision: workflowStage === "READY" ? activeRevision : null,
      deletion: null,
      capabilities: { can_start_processing: workflowStage === "UPLOADED", can_retry_processing: false, can_enter_manual_transcript: workflowStage !== "NONE", can_edit_transcript: workflowStage === "READY", can_assess_quality: workflowStage === "READY", can_approve_transcript: false, can_remove_recording: workflowStage !== "NONE" },
    });
    const audioFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const json = (data: unknown) => new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.endsWith("/recordings") && init?.method === "POST") { workflowStage = "UPLOADED"; return json({ id: "recording-1", lesson_id: "lesson-2", original_filename: "demo.wav", mime_type: "audio/wav", byte_size: 12, sha256: "a".repeat(64), duration_ms: 9000, workflow_status: "UPLOADED" }); }
      if (url.endsWith("/transcriptions")) return json({ id: "job-1", status: "QUEUED", stage: "Queued", recoverable: null, recording_id: "recording-1", resulting_transcript_revision_id: null, error_code: null });
      if (url.endsWith("/processing-jobs/job-1/run")) { workflowStage = "READY"; return json({ id: "job-1", status: "SUCCEEDED", stage: "Ready", recoverable: null, recording_id: "recording-1", resulting_transcript_revision_id: "revision-1", error_code: null }); }
      if (url.endsWith("/transcript-revisions/revision-1")) return json(revision);
      if (url.endsWith("/transcript-revisions/revision-1/manual-revision")) {
        const requestBody = JSON.parse(String(init?.body));
        activeRevision = { ...revision, id: "revision-2", revision_number: 2, copied_from_transcript_revision_id: "revision-1", segments: requestBody.segments.map((segment: { sequence: number; start_ms: number; end_ms: number; text: string }, index: number) => ({ ...segment, id: `new-${index}` })) };
        return json(activeRevision);
      }
      const audioContextId = url.match(/\/curriculum\/context-versions\/([^/]+)\/audio-workflow/)?.[1];
      if (audioContextId) return json(workflowSummary(audioContextId));
      return baseFetch(input, init);
    });
    renderApp("/teacher", audioFetch);
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    const fileInput = await screen.findByLabelText("Choose WAV classroom recording");
    await user.upload(fileInput, new File(["wav"], "demo.wav", { type: "audio/wav" }));
    await user.click(screen.getByRole("button", { name: "Upload WAV" }));
    await user.click(await screen.findByRole("button", { name: "Start transcription" }));
    await user.click(await screen.findByRole("button", { name: "Manual transcript correction" }));
    expect(screen.getByRole("button", { name: "Move segment 1 up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move segment 2 down" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move segment 2 up" }));
    expect(screen.getByText("Segment moved to position 1 of 2.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move segment 1 down" })).toHaveFocus();
    expect(screen.getByLabelText("Segment 1 transcript text")).toHaveValue("Leaf chlorophil captures light.");
    expect(screen.getByLabelText("Segment 1 start milliseconds")).toHaveValue(3000);
    expect(screen.getByLabelText("Segment 1 end milliseconds")).toHaveValue(6000);
    await user.click(screen.getByRole("button", { name: "Save new transcript revision" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Segment timestamps must follow the displayed order.");
    expect(audioFetch.mock.calls.filter(([input]) => String(input).endsWith("/manual-revision"))).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Move segment 1 down" }));
    expect(screen.getByLabelText("Segment 1 transcript text")).toHaveValue("Plants need water.");
    const segmentTwo = screen.getByLabelText("Segment 2 transcript text");
    await user.clear(segmentTwo);
    await user.type(segmentTwo, "Leaf Chlorophyll captures light.");
    await user.click(screen.getByRole("button", { name: "Save new transcript revision" }));
    expect(await screen.findByText(/Revision 2/)).toBeInTheDocument();
    expect(screen.getByText("Leaf Chlorophyll captures light.")).toBeInTheDocument();
    expect(audioFetch.mock.calls.some(([, init]) => String(init?.body).includes("Chlorophyll"))).toBe(true);
  });

  it("restores a durable transcript review after reopening the teacher context", async () => {
    const resumeSummary = {
      context_version_id: "context-v2",
      state: "QUALITY_BLOCKED" as const,
      recording: { id: "recording-1", original_filename: "photosynthesis-demo.wav", mime_type: "audio/wav", duration_ms: 19400, source_status: "DEMO", created_at: "2026-07-16T09:00:00Z", content_url: "/api/v1/teacher/recordings/recording-1/content" },
      latest_job: { id: "job-1", status: "SUCCEEDED" as const, stage: "Transcript ready for teacher review", recoverable: false, error_code: null, message: null },
      latest_revision: {
        id: "revision-1", recording_id: "recording-1", revision_number: 1, copied_from_transcript_revision_id: null,
        source_status: "DEMO", provider_name: "shravya-deterministic-demo", provider_version: "phase-3b",
        provenance_label: "Deterministic offline demo transcript mapped to a team-recorded Malayalam/code-mixed lesson — not live STT.", teacher_review_status: "DRAFT" as const, approved_at: null,
        segments: [{ id: "segment-2", sequence: 2, start_ms: 7654, end_ms: 12988, text: "ഇലയിലെ chlorophil സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു." }],
        suggestions: [{ id: "suggestion-1", transcript_segment_id: "segment-2", glossary_term_id: "term-2", detected_text: "chlorophil", canonical_term: "Chlorophyll", malayalam_support_label: "ക്ലോറോഫിൽ", latest_decision: "CONFIRMED" as const }],
        quality: { quality_status: "FAILED" as const, measured_coverage: 1, reasons: [{ reason_code: "unresolved_terms", severity: "BLOCKING", message_key: "quality.unresolved_terms", measured_value: 1, threshold: 0, recovery_action: "confirm_or_edit_term" }] },
      },
      deletion: null,
      capabilities: { can_start_processing: false, can_retry_processing: false, can_enter_manual_transcript: true, can_edit_transcript: true, can_assess_quality: true, can_approve_transcript: false, can_remove_recording: true },
    };
    const fetchMock = createCurriculumFetch({ audioWorkflow: (contextId) => contextId === "context-v2" ? resumeSummary : { ...resumeSummary, context_version_id: contextId, state: "NO_RECORDING", recording: null, latest_job: null, latest_revision: null, capabilities: { ...resumeSummary.capabilities, can_enter_manual_transcript: false, can_edit_transcript: false, can_assess_quality: false, can_remove_recording: false } } });
    const first = renderApp("/teacher", fetchMock);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    expect(await screen.findByText("photosynthesis-demo.wav")).toBeInTheDocument();
    expect(screen.getByText(/Deterministic offline demo transcript mapped/)).toBeInTheDocument();
    expect(screen.getAllByText(/chlorophil/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("Choose WAV classroom recording")).not.toBeInTheDocument();
    first.unmount();
    renderApp("/teacher", fetchMock);
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    expect(await screen.findByText("photosynthesis-demo.wav")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps Question Explorer as a semantic list with separated source labels", async () => {
    renderApp("/student");
    const heading = await screen.findByRole("heading", { name: "Question Explorer" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    const list = within(section!).getByRole("list");
    const [question] = within(list).getAllByRole("listitem");
    const sourceLabel = within(question).getByText("Teacher question");
    expect(sourceLabel).toHaveClass("question-source-label");
    expect(sourceLabel.nextElementSibling).toHaveClass("question-copy");
    expect(within(question).getByText("What inputs do plants need for photosynthesis?")).toBeInTheDocument();
  });

  it("fetches fresh student content after the teacher approves v2", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    await user.click(await screen.findByRole("button", { name: "Approve trusted version" }));
    await user.click(screen.getByRole("button", { name: "Student" }));
    expect(await screen.findByText("Trusted version 2")).toBeInTheDocument();
    expect(screen.getByText("Improved teacher explanation")).toBeInTheDocument();
    expect(screen.getByText("Improved classroom question")).toBeInTheDocument();
  });

  it("renders the explicit student not-ready state", async () => {
    renderApp("/student", createCurriculumFetch({ notReady: true }));
    expect(await screen.findByRole("heading", { name: "This lesson is being prepared by your teacher." })).toBeInTheDocument();
    expect(screen.getByText("Only reviewed classroom content will appear here.")).toBeInTheDocument();
  });

  it("uses safe error copy without API internals", async () => {
    renderApp("/student", createCurriculumFetch({ fail: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The classroom information is unavailable right now.");
    expect(screen.queryByText(/SELECT \* FROM private/)).not.toBeInTheDocument();
    expect(screen.queryByText(/C:\\secrets/)).not.toBeInTheDocument();
  });

  it("supports keyboard selection of a version and keyboard role navigation", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    const versionTwo = await screen.findByRole("button", { name: /Version 2/ });
    versionTwo.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("button", { name: /Version 2/ })).toHaveAttribute("aria-pressed", "true"));
    const student = screen.getByRole("button", { name: /^Student$/ });
    student.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
  });

  it("keeps one main heading and named landmarks on both primary routes", async () => {
    const { rerender } = renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
    rerender(<MemoryRouter initialEntries={["/student"]}><AppProvider><App /></AppProvider></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
