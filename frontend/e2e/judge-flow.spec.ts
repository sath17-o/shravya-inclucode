import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const courseId = "7262085f-4395-55d0-83fe-16981a90283b";
const v1 = "context-v1";
const v2 = "context-v2";
const course = { id: courseId, title: "Class 7 Science", subject: "Science", class_level: 7, grade_band: "5-7" };
const complete = { context_version_id: v2, is_complete: true, issues: [], completed_sections: ["approved_materials", "glossary", "concepts", "questions", "required_text"], incomplete_sections: [] };

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
  ].map(([canonical_term, malayalam_support_label], index) => ({ id: `term-${index}`, canonical_term, malayalam_support_label, definition: `${canonical_term} lesson definition.`, malayalam_explanation: null, sequence: index + 1, aliases: [], misrecognitions: canonical_term === "Chlorophyll" ? [{ id: "asr", detected_text: "chlorophil", normalized_text: "chlorophil" }] : [] }));
  return {
    id: `lesson-${version}`, title: "Photosynthesis in Plants", sequence: 1, primary_language: "ml", description: "Plants use sunlight, water and carbon dioxide to make glucose and release oxygen.",
    objectives: [{ id: "o1", objective_text: "Identify the inputs required for photosynthesis.", malayalam_text: "പ്രകാശസംശ്ലേഷണത്തിന് ആവശ്യമായ ഘടകങ്ങളെ തിരിച്ചറിയുക.", sequence: 1 }],
    approved_materials: [{ id: "m1", title: improved ? "Improved teacher explanation" : "Trusted teacher explanation", material_type: "teacher_note", source_label: "Teacher-approved classroom note", content: improved ? "Improved teacher explanation" : "Plants use chlorophyll to capture sunlight.", language: "bilingual", sequence: 1 }],
    glossary_terms: glossary,
    concepts: [["What plants need", "സസ്യങ്ങൾക്ക് വേണ്ട ഘടകങ്ങൾ"], ["How inputs reach the leaf", "ഘടകങ്ങൾ ഇലയിലെത്തുന്നത്"], ["Sunlight and chlorophyll", "സൂര്യപ്രകാശവും ക്ലോറോഫിലും"], ["Making glucose", "ഗ്ലൂക്കോസ് നിർമ്മാണം"], ["Releasing oxygen", "ഓക്സിജൻ പുറന്തള്ളൽ"]].map(([title, malayalam_title], index) => ({ id: `c${index}`, concept_key: `c${index}`, title, malayalam_title, definition: title, malayalam_definition: malayalam_title, sequence: index + 1 })),
    concept_relationships: [],
    questions: [{ id: "q1", related_concept_id: "c0", source_type: "teacher_question", source_label: "Teacher question", question_text: "What inputs do plants need?", malayalam_question_text: "സസ്യങ്ങൾക്ക് എന്ത് വേണം?", sequence: 1, year: null, marks: null }, ...(improved ? [{ id: "q2", related_concept_id: "c4", source_type: "teacher_question", source_label: "Improved classroom question", question_text: "Put the five concepts in a learning flow.", malayalam_question_text: "അഞ്ച് ആശയങ്ങളെ ക്രമീകരിക്കുക.", sequence: 2, year: null, marks: 3 }] : [])],
  };
}

async function mockJudgeApi(page: Page) {
  let v2Status: "DRAFT" | "NEEDS_REVIEW" | "APPROVED" = "DRAFT";
  let studentVersion = 1;
  const events = { [v1]: [], [v2]: [{ id: "copy", event_type: "copied_to_new_draft", actor_role: "teacher", note: null, created_at: "2026-07-16T09:05:00Z" }] } as Record<string, object[]>;
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith(`/teacher/courses/${courseId}/contexts`)) return route.fulfill(json({ status: "success", data: [context(1, "APPROVED"), context(2, v2Status)] }));
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
