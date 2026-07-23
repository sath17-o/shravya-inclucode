import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProvider } from "../app/AppContext";
import {
  DEFAULT_READING_PREFERENCES,
  READING_PREFERENCES_STORAGE_KEY,
  ReadingSettingsPanel,
  StudentReadingPreferencesProvider,
  normalizeReadingPreferences,
  readReadingPreferences,
} from "../features/readingPreferences";
import { createCurriculumFetch } from "./curriculumFixtures";

const focusKey = "shravya:focus:course:context:v5";

function renderSettings() {
  return render(
    <StudentReadingPreferencesProvider>
      <ReadingSettingsPanel />
    </StudentReadingPreferencesProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("browser-level reading preferences", () => {
  it("migrates partial legacy data to explicit schema v1 without touching v5 journey progress", () => {
    window.localStorage.setItem(READING_PREFERENCES_STORAGE_KEY, JSON.stringify({ font: "hyperlegible", spacing: "wide" }));
    window.localStorage.setItem(focusKey, "preserve-progress");

    expect(readReadingPreferences()).toEqual({
      preferences: { ...DEFAULT_READING_PREFERENCES, font: "hyperlegible", spacing: "wide" },
      persistenceAvailable: true,
    });
    expect(JSON.parse(window.localStorage.getItem(READING_PREFERENCES_STORAGE_KEY) ?? "null")).toEqual({
      ...DEFAULT_READING_PREFERENCES,
      font: "hyperlegible",
      spacing: "wide",
    });
    expect(window.localStorage.getItem(focusKey)).toBe("preserve-progress");
  });

  it("normalizes invalid persisted values safely and idempotently", () => {
    const invalid = { schemaVersion: 99, font: "unknown", textSize: "giant", spacing: 4, contrast: "sepia", reduceMotion: "yes" };
    expect(normalizeReadingPreferences(invalid)).toEqual(DEFAULT_READING_PREFERENCES);
    expect(normalizeReadingPreferences(normalizeReadingPreferences(invalid))).toEqual(DEFAULT_READING_PREFERENCES);
    expect(normalizeReadingPreferences({ schemaVersion: 99, font: "hyperlegible" })).toEqual(DEFAULT_READING_PREFERENCES);
  });

  it("applies semantic attributes immediately and resets only reading preferences", async () => {
    const user = userEvent.setup();
    const untouchedJourney = JSON.stringify({ supportMode: "one_step", answers: { concept: "answer" }, completedStepIds: ["concept"], recovery: { concept: { currentRecoveryStage: 2 } } });
    window.localStorage.setItem(focusKey, untouchedJourney);
    const view = renderSettings();
    const boundary = view.container.querySelector("[data-student-reading-preferences]");

    await user.click(screen.getByRole("radio", { name: "Easier-to-distinguish letters" }));
    await user.click(screen.getByRole("radio", { name: "Extra large" }));
    await user.click(screen.getByRole("radio", { name: "Wide" }));
    await user.click(screen.getByRole("radio", { name: "Dark" }));
    await user.click(screen.getByRole("checkbox", { name: "Reduce motion" }));
    expect(boundary).toHaveAttribute("data-reading-font", "hyperlegible");
    expect(boundary).toHaveAttribute("data-reading-size", "extra-large");
    expect(boundary).toHaveAttribute("data-reading-spacing", "wide");
    expect(boundary).toHaveAttribute("data-reading-contrast", "dark");
    expect(boundary).toHaveAttribute("data-reduce-motion", "true");

    await user.click(screen.getByRole("button", { name: "Reset reading settings" }));
    expect(readReadingPreferences().preferences).toEqual(DEFAULT_READING_PREFERENCES);
    expect(window.localStorage.getItem(focusKey)).toBe(untouchedJourney);
    expect(screen.getByText(/Your lesson progress will not change\./)).toBeInTheDocument();
  });

  it("uses native accessible controls with distinct reset wording", () => {
    renderSettings();
    expect(screen.getByRole("group", { name: "Letters" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Text size" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Text spacing" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Display" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset reading settings" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reset$/ })).not.toBeInTheDocument();
  });

  it("does not place reading attributes on the teacher view", async () => {
    vi.stubGlobal("fetch", createCurriculumFetch());
    const view = render(
      <MemoryRouter initialEntries={["/teacher"]}>
        <AppProvider><App /></AppProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Teacher Review Workspace" })).toBeInTheDocument();
    expect(view.container.querySelector("[data-student-reading-preferences]")).toBeNull();
  });
});
