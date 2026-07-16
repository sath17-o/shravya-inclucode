import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { text } from "../src/i18n/strings";

const seriousOrCritical = (impact: string | null | undefined) => impact === "serious" || impact === "critical";

async function expectNoSeriousAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => seriousOrCritical(violation.impact))).toEqual([]);
}

test("direct student access to Teacher Setup redirects to Learning Home", async ({ page }) => {
  await page.goto("/teacher-setup");
  await expect(page).toHaveURL(/\/learning-home$/);
  await expect(page.getByRole("heading", { name: /Learning Home/ })).toBeVisible();
});

test("Phase 1 routes are keyboard-operable, multilingual, and accessible", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/learning-home");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /Skip to main content/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();

  await page.getByRole("button", { name: /Teacher Setup/ }).press("Enter");
  await expect(page).toHaveURL(/\/teacher-setup$/);
  await expect(page.getByRole("button", { name: /Teacher Setup/ })).toHaveAttribute("aria-pressed", "true");
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("button", { name: /Student Learning/ }).press("Enter");
  await expect(page).toHaveURL(/\/learning-home$/);
  await page.getByRole("radio", { name: /Malayalam/ }).check();
  await expect(page.locator("html")).toHaveAttribute("lang", "ml");
  await expect(page).toHaveTitle(text.appName.malayalam);
  await expect(page.getByRole("heading", { name: text.learningHome.malayalam })).toBeVisible();
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("link", { name: text.lessonOverview.malayalam }).press("Enter");
  await expect(page.getByRole("heading", { name: text.lessonOverview.malayalam })).toBeVisible();
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("link", { name: text.trustInformation.malayalam }).press("Enter");
  const trustButton = page.getByRole("button", { name: text.whyTrust.malayalam });
  await trustButton.focus();
  await page.keyboard.press("Enter");
  await expect(trustButton).toHaveAttribute("aria-expanded", "true");
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("link", { name: text.learningPreferences.malayalam }).press("Enter");
  await expect(page.getByRole("heading", { name: text.learningPreferences.malayalam })).toBeVisible();
  await page.getByRole("radio", { name: text.compact.malayalam }).check();
  await page.locator("html").evaluate((element) => {
    element.style.fontSize = "24px";
    element.style.lineHeight = "2";
  });
  const longLabel = page.getByTestId("long-label-preview");
  await expect(longLabel).toBeVisible();
  expect(await longLabel.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expectNoSeriousAxeViolations(page);
});
