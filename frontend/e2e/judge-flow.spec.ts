import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const courseId = "7262085f-4395-55d0-83fe-16981a90283b";
const v1 = "context-v1";
const v2 = "context-v2";
const course = { id: courseId, title: "Class 7 Science", subject: "Science", class_level: 7, grade_band: "5-7" };
const complete = { context_version_id: v2, is_complete: true, issues: [], completed_sections: ["approved_materials", "glossary", "concepts", "questions", "required_text"], incomplete_sections: [] };
const spokenFixturePath = fileURLToPath(new URL("../../backend/app/demo/assets/photosynthesis-demo.wav", import.meta.url));

function json(data: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(data) };
}

function context(version: number, status: "DRAFT" | "NEEDS_REVIEW" | "APPROVED") {
  return { id: version === 1 ? v1 : v2, course_id: courseId, version_number: version, teacher_review_status: status, copied_from_context_version_id: version === 2 ? v1 : null, submitted_at: status === "DRAFT" ? null : "2026-07-16T09:00:00Z", approved_at: status === "APPROVED" ? "2026-07-16T09:05:00Z" : null, reviewer_note: null };
}

function lesson(version: number) {
  const improved = version === 2;
  const glossary = [
    ["Photosynthesis", "പ്രകാശസംശ്ലേഷണം"], ["Chlorophyll", "ക്ലോറോഫിൽ"], ["Chloroplast", "ഹരിതകണം"], ["Stomata", "ഇലരന്ധ്രങ്ങൾ"], ["Carbon dioxide", "കാർബൺ ഡൈ ഓക്സൈഡ്"], ["Water", "ജലം"], ["Sunlight", "സൂര്യപ്രകാശം"], ["Glucose", "ഗ്ലൂക്കോസ്"], ["Oxygen", "ഓക്സിജൻ"], ["Leaf", "ഇല"],
  ].map(([canonical_term, malayalam_support_label], index) => ({ id: `term-${index}`, canonical_term, malayalam_support_label, definition: `${canonical_term} lesson definition.`, malayalam_explanation: null, sequence: index + 1, concept_ids: [["c0"], ["c2"], ["c2"], ["c1"], ["c0", "c1"], ["c0", "c1"], ["c0", "c2"], ["c3"], ["c4"], ["c1"]][index], aliases: [], misrecognitions: canonical_term === "Chlorophyll" ? [{ id: "asr", detected_text: "chlorophil", normalized_text: "chlorophil" }] : [] }));
  return {
    id: `lesson-${version}`, title: "Photosynthesis in Plants", sequence: 1, primary_language: "ml", description: "Plants use sunlight, water and carbon dioxide to make glucose and release oxygen.",
    objectives: [{ id: "o1", objective_text: "Identify the inputs required for photosynthesis.", malayalam_text: "പ്രകാശസംശ്ലേഷണത്തിന് ആവശ്യമായ ഘടകങ്ങളെ തിരിച്ചറിയുക.", sequence: 1 }],
    approved_materials: [{ id: "m1", title: improved ? "Improved teacher explanation" : "Trusted teacher explanation", material_type: "teacher_note", source_label: "Teacher-approved classroom note", content: improved ? "Improved teacher explanation" : "Plants use chlorophyll to capture sunlight.", language: "bilingual", sequence: 1 }],
    glossary_terms: glossary,
    concepts: [["What plants need", "സസ്യങ്ങൾക്ക് വേണ്ട ഘടകങ്ങൾ"], ["How inputs reach the leaf", "ഘടകങ്ങൾ ഇലയിലെത്തുന്നത്"], ["Sunlight and chlorophyll", "സൂര്യപ്രകാശവും ക്ലോറോഫിലും"], ["Making glucose", "ഗ്ലൂക്കോസ് നിർമ്മാണം"], ["Releasing oxygen", "ഓക്സിജൻ പുറന്തള്ളൽ"]].map(([title, malayalam_title], index) => ({ id: `c${index}`, concept_key: `c${index}`, title, malayalam_title, definition: title, malayalam_definition: malayalam_title, sequence: index + 1 })),
    recovery_support: [0, 1, 2, 3, 4].map((index) => ({ concept_id: `c${index}`, cue: { english: `Approved cue ${index + 1}.`, malayalam: `അംഗീകരിച്ച സൂചന ${index + 1}.` }, example: { english: `Approved example ${index + 1}.`, malayalam: `അംഗീകരിച്ച ഉദാഹരണം ${index + 1}.` }, alternate_explanation: { english: `Approved alternate explanation ${index + 1}.`, malayalam: `അംഗീകരിച്ച വിശദീകരണം ${index + 1}.` } })),
    concept_relationships: [],
    questions: [{ id: "q1", related_concept_id: "c0", source_type: "teacher_question", source_label: "Teacher question", question_text: "What inputs do plants need?", malayalam_question_text: "സസ്യങ്ങൾക്ക് എന്ത് വേണം?", sequence: 1, year: null, marks: null }, ...(improved ? [{ id: "q2", related_concept_id: "c4", source_type: "teacher_question", source_label: "Improved classroom question", question_text: "Put the five concepts in a learning flow.", malayalam_question_text: "അഞ്ച് ആശയങ്ങളെ ക്രമീകരിക്കുക.", sequence: 2, year: null, marks: 3 }] : [])],
  };
}

async function mockJudgeApi(page: Page) {
  let v2Status: "DRAFT" | "NEEDS_REVIEW" | "APPROVED" = "DRAFT";
  let studentVersion = 1;
  let audioStage: "NONE" | "UPLOADED" | "PROCESSING" | "READY" = "NONE";
  let termDecision: "CONFIRMED" | "REJECTED" | "UNSURE" | null = null;
  const events = { [v1]: [], [v2]: [{ id: "copy", event_type: "copied_to_new_draft", actor_role: "teacher", note: null, created_at: "2026-07-16T09:05:00Z" }] } as Record<string, object[]>;
  const audioSummary = (contextVersionId: string) => ({
    context_version_id: contextVersionId,
    state: audioStage === "NONE" ? "NO_RECORDING" : audioStage === "UPLOADED" ? "UPLOADED" : audioStage === "PROCESSING" ? "PROCESSING" : "NEEDS_REVIEW",
    recording: audioStage === "NONE" ? null : { id: "recording-1", original_filename: "photosynthesis-demo.wav", mime_type: "audio/wav", duration_ms: 19400, source_status: "DEMO", created_at: "2026-07-16T09:00:00Z", content_url: "/api/v1/teacher/recordings/recording-1/content" },
    latest_job: audioStage === "PROCESSING" ? { id: "job-1", status: "RUNNING", stage: "Transcribing", recoverable: false, error_code: null, message: null } : null,
    latest_revision: audioStage === "READY" ? {
      id: "revision-1", recording_id: "recording-1", revision_number: 1, copied_from_transcript_revision_id: null, source_status: "DEMO", provider_name: "shravya-deterministic-demo", provider_version: "phase-3b", provenance_label: "Deterministic offline demo transcript mapped to a team-recorded Malayalam/code-mixed lesson — not live STT.", teacher_review_status: "DRAFT", approved_at: null,
      segments: [{ id: "segment-2", sequence: 2, start_ms: 7654, end_ms: 12988, text: "ഇലയിലെ chlorophil സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു." }],
      suggestions: [{ id: "suggestion-1", transcript_segment_id: "segment-2", glossary_term_id: "term-1", detected_text: "chlorophil", canonical_term: "Chlorophyll", malayalam_support_label: "ക്ലോറോഫിൽ", latest_decision: termDecision }],
      quality: null,
    } : null,
    deletion: null,
    capabilities: { can_start_processing: audioStage === "UPLOADED", can_retry_processing: false, can_enter_manual_transcript: audioStage !== "NONE", can_edit_transcript: audioStage === "READY", can_assess_quality: audioStage === "READY", can_approve_transcript: false, can_remove_recording: audioStage !== "NONE" },
  });
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith(`/teacher/courses/${courseId}/contexts`)) return route.fulfill(json({ status: "success", data: [context(1, "APPROVED"), context(2, v2Status)] }));
    const audioContextId = url.match(/\/curriculum\/context-versions\/([^/]+)\/audio-workflow/)?.[1];
    if (audioContextId) return route.fulfill(json({ status: "success", data: audioSummary(audioContextId) }));
    if (url.endsWith("/teacher/lessons/lesson-2/recordings") && method === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 150));
      audioStage = "UPLOADED";
      return route.fulfill(json({ status: "success", data: { id: "recording-1", lesson_id: "lesson-2", original_filename: "photosynthesis-demo.wav", mime_type: "audio/wav", byte_size: 620878, sha256: "f431fd3931ed5c8e0f53a0ae4bce1a3d9ae0cf656efc0234cd8f3e742cb9ead7", duration_ms: 19400, source_status: "DEMO", workflow_status: "UPLOADED" } }));
    }
    if (url.endsWith("/teacher/recordings/recording-1/transcriptions") && method === "POST") {
      audioStage = "PROCESSING";
      return route.fulfill(json({ status: "success", data: { id: "job-1", status: "QUEUED", stage: "Queued", recoverable: null, recording_id: "recording-1", resulting_transcript_revision_id: null, error_code: null } }));
    }
    if (url.endsWith("/teacher/processing-jobs/job-1/run") && method === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 150));
      audioStage = "READY";
      return route.fulfill(json({ status: "success", data: { id: "job-1", status: "SUCCEEDED", stage: "Transcript ready", recoverable: null, recording_id: "recording-1", resulting_transcript_revision_id: "revision-1", error_code: null } }));
    }
    if (url.endsWith("/teacher/term-suggestions/suggestion-1/decision") && method === "POST") {
      termDecision = "CONFIRMED";
      return route.fulfill(json({ status: "success", data: audioSummary(v2).latest_revision }));
    }
    if (url.endsWith(`/student/courses/${courseId}/lesson-overview`)) return route.fulfill(json({ status: "success", data: { course, is_ready: true, selected_context_id: studentVersion === 1 ? v1 : v2, version_number: studentVersion, approved_at: "2026-07-16T09:05:00Z", chapters: [{ id: "chapter", title: "Nutrition in Plants", sequence: 1, lessons: [lesson(studentVersion)] }] } }));
    const contextId = url.match(/\/teacher\/contexts\/([^/]+)/)?.[1];
    if (contextId && method === "POST" && url.endsWith("/submit-for-review")) {
      v2Status = "NEEDS_REVIEW";
      events[v2].push({ id: "submitted", event_type: "submitted_for_review", actor_role: "teacher", note: null, created_at: "2026-07-16T09:10:00Z" });
      return route.fulfill(json({ status: "success", data: { context: context(2, v2Status), completeness: complete } }));
    }
    if (contextId && method === "POST" && url.endsWith("/approve")) {
      v2Status = "APPROVED";
      studentVersion = 2;
      events[v2].push({ id: "approved", event_type: "approved", actor_role: "teacher", note: null, created_at: "2026-07-16T09:12:00Z" });
      return route.fulfill(json({ status: "success", data: { context: context(2, v2Status), newly_staled_artifact_count: 1 } }));
    }
    if (contextId && url.endsWith("/completeness")) return route.fulfill(json({ status: "success", data: { ...complete, context_version_id: contextId } }));
    if (contextId && url.endsWith("/review-events")) return route.fulfill(json({ status: "success", data: events[contextId] }));
    if (contextId) {
      const version = contextId === v1 ? 1 : 2;
      return route.fulfill(json({ status: "success", data: { ...context(version, version === 1 ? "APPROVED" : v2Status), chapters: [{ id: `chapter-${version}`, title: "Nutrition in Plants", sequence: 1, lessons: [lesson(version)] }], completeness: { ...complete, context_version_id: contextId }, review_events: events[contextId] } }));
    }
    return route.fulfill(json({ status: "error", code: "NOT_FOUND", message: "not found", message_key: "not_found", details: {}, recoverable: true, next_actions: [], job_id: null }, 404));
  });
}

async function expectNoSeriousAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (color: string) => {
    const channels = color.match(/\d+/g)?.slice(0, 3).map(Number) ?? [];
    const [red, green, blue] = channels.map((channel) => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue);
  };
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((first, second) => second - first);
  return (lighter + 0.05) / (darker + 0.05);
}

test("route navigation exposes one matching active role and lesson link", async ({ page }) => {
  await mockJudgeApi(page);
  for (const route of [
    { path: "/student", activeRole: "Student", inactiveRole: "Teacher", activeLink: "Student lesson", inactiveLink: "Teacher review" },
    { path: "/teacher", activeRole: "Teacher", inactiveRole: "Student", activeLink: "Teacher review", inactiveLink: "Student lesson" },
  ]) {
    await page.goto(route.path);
    const roleSwitcher = page.getByRole("group", { name: "Demo role switcher" });
    const activeRole = roleSwitcher.getByRole("button", { name: route.activeRole, exact: true });
    const inactiveRole = roleSwitcher.getByRole("button", { name: route.inactiveRole, exact: true });
    const navigation = page.getByRole("navigation", { name: "Primary" });
    const activeLink = navigation.getByRole("link", { name: route.activeLink, exact: true });
    const inactiveLink = navigation.getByRole("link", { name: route.inactiveLink, exact: true });

    await expect(activeRole).toHaveAttribute("aria-pressed", "true");
    await expect(inactiveRole).toHaveAttribute("aria-pressed", "false");
    await expect(activeLink).toHaveClass(/active/);
    await expect(activeLink).toHaveAttribute("aria-current", "page");
    await expect(activeLink).toHaveCSS("text-decoration-line", "underline");
    await expect(inactiveLink).not.toHaveClass(/active/);
    await expect(inactiveLink).not.toHaveAttribute("aria-current");
    await expect(inactiveLink).toHaveCSS("text-decoration-line", "none");
  }
});

test("student reading settings persist across reload and apply in the lesson and Focus Journey", async ({ page }) => {
  await mockJudgeApi(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/student");

  await page.locator(".lesson-reading-settings summary").click();
  await page.getByRole("radio", { name: "Easier-to-distinguish letters", exact: true }).check();
  await page.getByRole("radio", { name: "Extra large", exact: true }).check();
  await page.getByRole("radio", { name: "Wide", exact: true }).check();
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  await page.getByRole("checkbox", { name: "Reduce motion", exact: true }).check();

  const boundary = page.locator("[data-student-reading-preferences]");
  await expect(boundary).toHaveAttribute("data-reading-font", "hyperlegible");
  await expect(boundary).toHaveAttribute("data-reading-size", "extra-large");
  await expect(boundary).toHaveAttribute("data-reading-spacing", "wide");
  await expect(boundary).toHaveAttribute("data-reading-contrast", "dark");
  await expect(boundary).toHaveAttribute("data-reduce-motion", "true");
  const darkSurface = "rgb(23, 53, 44)";
  const primaryText = "rgb(249, 255, 250)";
  const structuralText = "rgb(200, 222, 212)";
  const assertDarkContrast = async (locator: ReturnType<Page["locator"]>, expected: string) => {
    await expect(locator).toHaveCSS("color", expected);
    const foreground = await locator.evaluate((element) => getComputedStyle(element).color);
    expect(contrastRatio(foreground, darkSurface)).toBeGreaterThanOrEqual(4.5);
  };
  await assertDarkContrast(page.getByRole("heading", { name: "Lesson orientation", exact: true }), primaryText);
  await assertDarkContrast(page.getByRole("heading", { name: "Help me focus", exact: true }), primaryText);
  await assertDarkContrast(page.getByRole("heading", { name: "Reading settings", exact: true }), primaryText);
  await assertDarkContrast(page.getByText("Teacher explanation", { exact: true }), structuralText);
  await assertDarkContrast(page.getByText("Step-by-step support", { exact: true }), structuralText);
  await assertDarkContrast(page.locator(".lesson-reading-settings summary"), structuralText);

  await page.getByRole("radio", { name: "High contrast", exact: true }).check();
  await expect(page.getByRole("heading", { name: "Lesson orientation", exact: true })).toHaveCSS("color", "rgb(23, 51, 45)");
  await page.getByRole("radio", { name: "Default", exact: true }).last().check();
  await expect(page.getByRole("heading", { name: "Lesson orientation", exact: true })).toHaveCSS("color", "rgb(23, 51, 45)");
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  expect(await page.locator("body").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);

  await page.reload();
  await expect(boundary).toHaveAttribute("data-reading-font", "hyperlegible");
  await page.locator(".lesson-reading-settings summary").click();
  await expect(page.getByRole("radio", { name: "Extra large", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Start Focus Journey" }).click();
  await page.getByRole("radio").first().check();
  await page.getByRole("button", { name: "Continue with this support" }).click();
  await page.getByRole("button", { name: "Start with step 1" }).click();
  await page.getByRole("button", { name: "More" }).click();
  await expect(page.getByRole("heading", { name: "Reading settings" })).toBeVisible();
  await expect(boundary).toHaveAttribute("data-reading-contrast", "dark");
  await page.getByRole("button", { name: "Reset reading settings" }).click();
  await expect(boundary).toHaveAttribute("data-reading-font", "default");
  await expect(boundary).toHaveAttribute("data-reading-contrast", "default");
  await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
});

test("judge flow shows teacher control, stale protection, and the approved v1-to-v2 student switch", async ({ page }) => {
  await mockJudgeApi(page);
  await page.goto("/student");
  const skipLink = page.getByRole("link", { name: "Skip to lesson content" });
  await expect(skipLink).toHaveCSS("position", "absolute");
  await expect(skipLink).toHaveCSS("left", "-10000px");
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS("position", "static");
  const skipBox = await skipLink.boundingBox();
  const heroBox = await page.locator(".student-hero").boundingBox();
  expect(skipBox?.y).toBeLessThan(heroBox?.y ?? 0);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await expect(page.getByText("Trusted version 1")).toBeVisible();
  const heroBackground = await page.locator(".student-hero").evaluate((element) => getComputedStyle(element).backgroundColor);
  for (const selector of [".student-hero h1", ".hero-malayalam", ".trusted-version"]) {
    const foreground = await page.locator(selector).evaluate((element) => getComputedStyle(element).color);
    expect(contrastRatio(foreground, heroBackground)).toBeGreaterThanOrEqual(4.5);
  }
  await expect(page.getByText("Improved teacher explanation")).toHaveCount(0);
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("button", { name: "Teacher" }).click();
  await expect(page.getByRole("heading", { name: "Teacher Review Workspace" })).toBeVisible();
  await page.getByRole("button", { name: /Version 2/ }).click();
  await expect(page.getByText("Ready for teacher review")).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.getByRole("button", { name: "Approve trusted version" }).click();
  await expect(page.getByRole("status")).toContainText("1 older learning artifact marked stale");
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("button", { name: "Student", exact: true }).click();
  await expect(page.getByText("Trusted version 2")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Improved teacher explanation" })).toBeVisible();
  await expect(page.getByText("Improved classroom question")).toBeVisible();
});

test("teacher and student layouts remain usable at judge viewport widths", async ({ page }) => {
  await mockJudgeApi(page);
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/teacher");
    await expect(page.getByRole("heading", { name: "Teacher Review Workspace" })).toBeVisible();
    expect(await page.locator("body").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.goto("/student");
    await expect(page.getByRole("heading", { name: "Photosynthesis in Plants" })).toBeVisible();
    expect(await page.locator("body").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
});

test("teacher audio review restores the durable deterministic transcript after reload", async ({ page }) => {
  await mockJudgeApi(page);
  await page.goto("/teacher");
  await page.getByRole("button", { name: /Version 2/ }).click();
  const workflow = page.getByRole("region", { name: "Recording workflow" });
  const milestone = (name: string) => workflow.locator("li").filter({ hasText: name });
  await page.getByLabel("Choose WAV classroom recording").setInputFiles(spokenFixturePath);
  await expect(milestone("Selected")).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "Upload WAV" }).click();
  await expect(milestone("Uploading")).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("button", { name: "Start transcription" })).toBeVisible();
  await page.getByRole("button", { name: "Start transcription" }).click();
  await expect(milestone("Transcribing")).toHaveAttribute("aria-current", "step");
  await expect(page.getByText("photosynthesis-demo.wav")).toBeVisible();
  await expect(milestone("Transcript ready")).toContainText("Complete");
  await expect(milestone("Needs review")).toHaveAttribute("aria-current", "step");
  await expect(page.getByText(/Deterministic offline demo transcript mapped/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("photosynthesis-demo.wav")).toBeVisible();
  await expect(page.getByText(/Deterministic offline demo transcript mapped/)).toBeVisible();
  await expect(page.getByText(/chlorophil/).first()).toBeVisible();
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
});

test("Focus Journey restores recovery and a paused approved-lesson step after reload", async ({ page }) => {
  await mockJudgeApi(page);
  await page.goto("/student");
  await page.getByRole("button", { name: "Start Focus Journey" }).click();
  await expect(page.getByRole("heading", { name: "How should Shravya support you right now?" })).toBeVisible();
  await page.getByLabel(/One step at a time\s+Show one clear step and one support at a time\./).check();
  await page.getByRole("button", { name: "Continue with this support" }).click();
  await expect(page.getByText("Support: One step at a time")).toBeVisible();
  await page.getByRole("button", { name: "Start with step 1" }).click();
  await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
  await page.getByRole("button", { name: "I’m stuck" }).click();
  await expect(page.getByRole("heading", { name: "Let’s find a way through" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Let’s find a way through" })).toBeVisible();
  await page.getByRole("button", { name: "Show the important words" }).click();
  await expect(page.getByRole("heading", { name: "Important words" })).toBeVisible();
  await page.getByRole("button", { name: "Return to question" }).click();
  await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
  await page.getByLabel("Photosynthesis").check();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "How inputs reach the leaf" })).toBeVisible();
  await page.getByRole("button", { name: "More" }).click();
  await page.getByRole("button", { name: "Pause journey" }).click();
  await expect(page.getByRole("heading", { name: "Journey paused" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Journey paused" })).toBeVisible();
  await expect(page.getByText("Focus Journey · Step 2 of 5")).toBeVisible();
  await page.getByRole("button", { name: "Resume journey" }).click();
  await expect(page.getByRole("heading", { name: "How inputs reach the leaf" })).toBeVisible();
  await page.getByRole("button", { name: "More" }).click();
  await page.getByRole("button", { name: "Exit to full lesson" }).click();
  await expect(page.getByRole("heading", { name: "Photosynthesis in Plants" })).toBeVisible();
  await expectNoSeriousAxeViolations(page);
});

test("browser Back from Focus Journey returns to the approved student lesson", async ({ page }) => {
  await mockJudgeApi(page);
  await page.goto("/student");
  await page.getByRole("button", { name: "Start Focus Journey" }).click();
  await expect(page.getByRole("heading", { name: "How should Shravya support you right now?" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Photosynthesis in Plants" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Teacher Review Workspace" })).toHaveCount(0);
});
