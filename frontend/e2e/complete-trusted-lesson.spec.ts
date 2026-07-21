import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { realBackendApiBaseUrl } from "../scripts/playwright-real-backend";
import { PHOTOSYNTHESIS_DEMO_COURSE_ID } from "../src/demo/config";

const spokenFixturePath = fileURLToPath(new URL("../../backend/app/demo/assets/photosynthesis-demo.wav", import.meta.url));

test.describe.serial("complete trusted lesson judge journey", () => {
  test("complete trusted lesson judge journey", async ({ page }) => {
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
    await expect(page.getByRole("button", { name: "Approve recovery pack" })).toHaveCount(5);
    await page.getByRole("button", { name: "Approve recovery pack" }).first().click();
    await expect(page.getByRole("button", { name: "Recovery pack approved" })).toHaveCount(1);

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
    expect((await projection.json()).data.chapters[0].lessons[0].recovery_support).toEqual([]);

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
    await expect(page.getByRole("heading", { name: "How should Shravya support you right now?" })).toBeVisible();
    await expect(page.getByText("Shravya responds to what helps you learn today.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
    await page.getByLabel(/Less at once\s+Show one short idea at a time\./).check();
    await page.getByRole("button", { name: "Continue with this support" }).click();
    await expect(page.getByText("Support: Less at once")).toBeVisible();
    await expect(page.getByText("Now")).toBeVisible();
    await expect(page.getByText("Next")).toBeVisible();
    await expect(page.getByText("Later")).toHaveCount(3);
    await page.getByRole("button", { name: "Start with step 1" }).click();
    await expect(page.getByRole("heading", { name: "What plants need" })).toBeVisible();
    await expect(page.getByText("Step 1 of 5")).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Focus Journey progress: Step 1 of 5" })).toBeVisible();
    await expect(page.getByText("Progress is saved on this device.")).toBeVisible();
    await expect(page.locator(".focus-step-card h1")).toHaveCount(1);
    await expect(page.locator(".focus-journey")).not.toContainText(/score|streak|timer|autoplay|punish/i);
    await page.getByRole("button", { name: "Exit to full lesson" }).click();
    await expect(page).toHaveURL(/\/student$/);
    await expect(page.getByRole("heading", { name: "Photosynthesis in Plants" })).toBeVisible();
  });
});
