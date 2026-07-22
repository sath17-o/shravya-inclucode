import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { realBackendApiBaseUrl } from "../scripts/playwright-real-backend";
import { PHOTOSYNTHESIS_DEMO_COURSE_ID } from "../src/demo/config";

const spokenFixturePath = fileURLToPath(new URL("../../backend/app/demo/assets/photosynthesis-demo.wav", import.meta.url));

test.describe.serial("complete trusted lesson judge journey", () => {
  test("complete trusted lesson judge journey", async ({ page }) => {
    test.setTimeout(60_000);
    await page.route("**/teacher/lessons/*/recordings", async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 180));
      await route.fulfill({ response });
    });
    await page.route("**/teacher/processing-jobs/*/run", async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 180));
      await route.fulfill({ response });
    });

    await page.goto("/teacher");
    await page.getByRole("button", { name: /Version 2/ }).click();
    const navigation = page.getByRole("navigation", { name: "Primary" });
    await expect(navigation.getByRole("link", { name: "Teacher review" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("button", { name: "Teacher" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("heading", { name: "Recovery support for this lesson" })).toBeVisible();
    const recoveryPackCards = page.locator(".recovery-pack-card");
    for (let index = 0; index < await recoveryPackCards.count(); index += 1) {
      const card = recoveryPackCards.nth(index);
      const approval = card.getByRole("button", { name: "Approve recovery pack" });
      if (await approval.count() && await approval.isEnabled()) {
        await approval.click();
        await expect(card.getByRole("button", { name: "Recovery pack approved" })).toBeVisible();
      }
    }
    await expect(page.getByRole("button", { name: "Recovery pack approved" })).toHaveCount(5);

    const audioWorkflow = page.locator(".audio-workflow");
    const workflow = page.getByRole("region", { name: "Recording workflow" });
    const milestone = (name: string) => workflow.locator("li").filter({ hasText: name });
    await expect(page.getByLabel("Choose WAV classroom recording")).toBeVisible();
    await expect(workflow.getByRole("list").getByRole("listitem")).toHaveCount(5);
    await expect(milestone("Selected")).toContainText("Not started");
    await expect(audioWorkflow.locator(".transcript-review")).toHaveCount(0);

    await page.getByLabel("Choose WAV classroom recording").setInputFiles(spokenFixturePath);
    await expect(milestone("Selected")).toHaveAttribute("aria-current", "step");
    await expect(audioWorkflow).toContainText("photosynthesis-demo.wav");
    await expect(audioWorkflow.locator(".transcript-review")).toHaveCount(0);

    await page.getByRole("button", { name: "Upload WAV" }).click();
    await expect(milestone("Uploading")).toHaveAttribute("aria-current", "step");
    await expect(audioWorkflow.locator("audio")).toBeVisible();
    await expect(audioWorkflow).toContainText("audio/wav");
    await expect(page.getByRole("button", { name: "Start transcription" })).toBeVisible();
    const playbackSource = await audioWorkflow.locator("audio").getAttribute("src");
    expect(playbackSource).not.toBeNull();
    const playbackResponse = await page.request.get(playbackSource!);
    expect(playbackResponse.status()).toBe(200);
    expect(playbackResponse.headers()["content-type"]).toContain("audio/wav");

    await page.getByRole("button", { name: "Start transcription" }).click();
    await expect(milestone("Transcribing")).toHaveAttribute("aria-current", "step");
    await expect(audioWorkflow).not.toContainText(/\d+%/);
    await expect(audioWorkflow.locator(".transcript-review")).toBeVisible();
    await expect(audioWorkflow.locator(".transcript-segments li")).toHaveCount(3);
    await expect(milestone("Transcript ready")).toContainText("Complete");
    await expect(milestone("Needs review")).toHaveAttribute("aria-current", "step");
    await expect(audioWorkflow).toContainText("Deterministic offline demo transcript");
    await expect(audioWorkflow).toContainText("not live STT");
    await expect(audioWorkflow).toContainText("chlorophil");
    await expect(audioWorkflow.getByText("chlorophil", { exact: true })).toBeVisible();
    await expect(audioWorkflow).toContainText("Chlorophyll");
    await expect(audioWorkflow).toContainText("ക്ലോറോഫിൽ");
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByRole("button", { name: "Approve transcript" })).toBeDisabled();
    await expect(audioWorkflow.getByRole("heading", { name: "Transcript quality: FAILED" })).toBeVisible();
    await expect(audioWorkflow).toContainText("unresolved terms");
    await expect(page.getByRole("button", { name: "Submit for review" })).toBeDisabled();

    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    await page.getByRole("button", { name: /Version 2/ }).click();
    await expect(audioWorkflow).toContainText("photosynthesis-demo.wav");
    await expect(audioWorkflow).toContainText("Deterministic offline demo transcript");
    await expect(audioWorkflow).toContainText("chlorophil");
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveAttribute("aria-pressed", "true");
    await expect(milestone("Needs review")).toHaveAttribute("aria-current", "step");

    await page.getByRole("button", { name: "Run quality check" }).click();
    await expect(audioWorkflow.getByRole("heading", { name: "Transcript quality: VERIFIED" })).toBeVisible();
    await expect(audioWorkflow).toContainText("Measured timestamp coverage: 100%");
    await expect(audioWorkflow).not.toContainText("unresolved terms");
    await expect(page.getByRole("button", { name: "Approve transcript" })).toBeEnabled();

    await page.getByRole("button", { name: "Approve transcript" }).click();
    await page.reload();
    await page.getByRole("button", { name: /Version 2/ }).click();
    await expect(audioWorkflow.getByRole("status")).toContainText("Transcript review complete.");
    await expect(milestone("Needs review")).toContainText("Complete");
    await expect(milestone("Needs review")).not.toHaveAttribute("aria-current", "step");
    await expect(page.getByRole("button", { name: "Submit for review" })).toBeEnabled();

    await page.getByRole("button", { name: "Submit for review" }).click();
    await expect(page.getByRole("button", { name: "Approve trusted version" })).toBeVisible();
    await page.getByRole("button", { name: "Approve trusted version" }).click();
    await expect(page.getByText("New trusted version approved.", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: /Version 2/ })).toContainText("Currently visible to students");
    const projection = await page.request.get(`${realBackendApiBaseUrl}/student/courses/${PHOTOSYNTHESIS_DEMO_COURSE_ID}/lesson-overview`);
    expect(projection.status()).toBe(200);
    expect((await projection.json()).data.chapters[0].lessons[0].recovery_support).toHaveLength(5);

    await page.getByRole("button", { name: "Student", exact: true }).click();
    await expect(navigation.getByRole("link", { name: "Student lesson" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("button", { name: "Student", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Trusted version 2")).toBeVisible();
    const trustedTranscript = page.locator("section.approved-transcript");
    await expect(trustedTranscript).toContainText("Deterministic offline demo transcript");
    await expect(trustedTranscript).toContainText("Trusted classroom record · version 2");
    await expect(trustedTranscript).not.toContainText("Teacher-reviewed status");
    await expect(trustedTranscript).toContainText("Chlorophyll");
    await expect(trustedTranscript).not.toContainText(/\bchlorophil\b/);
    await expect(trustedTranscript.locator(".transcript-segments li")).toHaveCount(3);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Unsure" })).toHaveCount(0);
    await expect(page.getByText("Chlorophyll").first()).toBeVisible();
    await expect(page.getByText("ക്ലോറോഫിൽ").first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/\bchlorophil\b/);
    await expect(page.getByRole("heading", { name: "Lesson orientation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Concept flow" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Question Explorer" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/C:\\|owner token|cleanup state|INTERNAL_ERROR/);

    await expect(page.getByRole("button", { name: "Start Focus Journey" })).toBeVisible();
    await page.getByRole("button", { name: "Start Focus Journey" }).click();
    await expect(page).toHaveURL(/\/student\/focus$/);
    await page.setViewportSize({ width: 1536, height: 700 });
    await expect(page.locator(".site-header")).toBeHidden();
    await expect(page.getByRole("navigation", { name: "Primary" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Student", exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "How should Shravya support you right now?" })).toBeVisible();
    await expect(page.getByText("Shravya responds to what helps you learn today.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
    await expect(page.getByRole("radio")).toHaveCount(3);
    await page.getByLabel(/One step at a time\s+Show one clear step and one support at a time\./).check();
    await page.getByRole("button", { name: "Continue with this support" }).click();
    await expect(page.getByText("Support: One step at a time")).toBeVisible();
    await expect(page.getByText("Now")).toBeVisible();
    await expect(page.getByText("Next")).toBeVisible();
    await expect(page.getByText("Later", { exact: true })).toHaveCount(0);
    const laterSteps = page.getByRole("button", { name: "See 3 later steps" });
    await expect(laterSteps).toHaveAttribute("aria-expanded", "false");
    await laterSteps.click();
    const hideLaterSteps = page.getByRole("button", { name: "Hide later steps" });
    await expect(hideLaterSteps).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("Later", { exact: true })).toHaveCount(3);
    await hideLaterSteps.click();
    await expect(laterSteps).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("Later", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Start with step 1" }).click();
    await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
    await expect(page.getByText("Step 1 of 5")).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Focus Journey progress: Step 1 of 5" })).toBeVisible();
    await expect(page.locator(".focus-step-card h1")).toHaveCount(1);
    await expect(page.locator(".focus-journey")).not.toContainText(/score|streak|timer|autoplay|punish/i);
    await expect(page.getByRole("button", { name: "Pause journey" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "false");
    const assertNormalStepFitsViewport = async (width: number, height: number) => {
      await page.setViewportSize({ width, height });
      await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
      const requiredElements = [
        page.locator(".focus-progress-copy"),
        page.getByRole("progressbar", { name: "Focus Journey progress: Step 1 of 5" }),
        page.locator(".focus-step-card h1"),
        page.locator(".focus-malayalam"),
        page.locator(".focus-explanation"),
        page.locator(".focus-terms"),
        ...await page.locator(".focus-terms li").all(),
        page.locator(".focus-check"),
        ...await page.locator(".focus-answer-option").all(),
        page.getByRole("button", { name: "I’m stuck", exact: true }),
        page.getByRole("button", { name: "Back", exact: true }),
        page.getByRole("button", { name: "Continue", exact: true }),
        page.getByRole("button", { name: "More", exact: true }),
      ];
      for (const element of requiredElements) {
        const box = await element.boundingBox();
        expect(box?.y).toBeGreaterThanOrEqual(0);
        expect((box?.y ?? 0) + (box?.height ?? 0), `The normal Step 1 task remains fully visible at ${width}×${height}`).toBeLessThanOrEqual(height);
      }
    };
    await assertNormalStepFitsViewport(1536, 700);
    await assertNormalStepFitsViewport(1536, 732);
    await assertNormalStepFitsViewport(1280, 720);
    await page.getByRole("radio").first().check();
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "I’m stuck" }).click();
    await expect(page.getByRole("heading", { name: "Let’s find a way through" })).toBeVisible();
    await expect(page.locator(".focus-recovery")).not.toContainText(/Support step|Orient|Next:/);
    await expect(page.locator(".focus-recovery").getByRole("heading", { name: "What plants need" })).toHaveCount(0);
    await expect(page.getByRole("group", { name: /Which key term is listed first/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "More" })).toHaveCount(0);
    await page.getByRole("button", { name: "Show the important words" }).click();
    await expect(page.getByRole("heading", { name: "Important words" })).toBeVisible();
    await page.getByRole("button", { name: "Give me a small cue" }).click();
    await expect(page.getByRole("heading", { name: "Small cue" })).toBeVisible();
    await page.getByRole("button", { name: "Show a concrete example" }).click();
    await expect(page.getByRole("heading", { name: "Concrete example" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Concrete example" })).toBeVisible();
    await page.getByRole("button", { name: "Return to question" }).click();
    await expect(page.getByRole("radio").first()).toBeChecked();
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Continue support" }).click();
    await page.getByRole("button", { name: "Show another explanation" }).click();
    await page.getByRole("button", { name: "Show where this fits" }).click();
    await expect(page.getByRole("heading", { name: "Concept connection" })).toBeVisible();
    await page.getByRole("button", { name: "Let me try again" }).click();
    await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
    await expect(page.getByRole("radio").first()).toBeChecked();
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
    await expect(page.locator("body")).not.toContainText(/\bchlorophil\b/);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Unsure" })).toHaveCount(0);
    await page.getByRole("button", { name: "More" }).click();
    const utility = page.locator(".focus-utility-actions");
    await expect(utility.locator(".focus-utility-normal").getByRole("button", { name: "Pause journey" })).toBeVisible();
    await expect(utility.locator(".focus-utility-normal").getByRole("button", { name: "Change support" })).toBeVisible();
    await expect(utility.locator(".focus-utility-normal").getByRole("button", { name: "Exit to full lesson" })).toBeVisible();
    await expect(utility.locator(".focus-utility-restart").getByRole("button", { name: "Restart journey" })).toBeVisible();
    await utility.locator(".focus-utility-restart").getByRole("button", { name: "Restart journey" }).click();
    const restartConfirmation = page.getByRole("dialog", { name: "Restart this journey?" });
    await expect(restartConfirmation).toBeVisible();
    await expect(restartConfirmation.getByRole("button", { name: "Keep my progress" })).toHaveClass(/focus-primary-action/);
    await restartConfirmation.getByRole("button", { name: "Keep my progress" }).click();
    await expect(page.getByRole("radio").first()).toBeChecked();
    await utility.locator(".focus-utility-restart").getByRole("button", { name: "Restart journey" }).click();
    await page.getByRole("dialog", { name: "Restart this journey?" }).getByRole("button", { name: "Restart journey" }).click();
    await expect(page.getByText("Support: One step at a time")).toBeVisible();
    await expect(page.getByText("Later", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Start with step 1" }).click();
    await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "More" }).click();
    const exitToLesson = page.getByRole("button", { name: "Exit to full lesson" });
    await expect(exitToLesson).toBeVisible();
    await exitToLesson.click();
    await expect(page).toHaveURL(/\/student$/);
    await expect(page.getByRole("heading", { name: "Photosynthesis in Plants" })).toBeVisible();
  });
});
