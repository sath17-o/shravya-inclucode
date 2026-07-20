import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProvider } from "../app/AppContext";
import {
  buildFocusJourneySteps,
  newFocusJourneyProgress,
  readFocusJourneyProgress,
} from "../features/focusJourney";
import { course, createCurriculumFetch, focusLessonFixture, v1 } from "./curriculumFixtures";

const nativeLocalStorage = window.localStorage;

function renderApp(path: "/student" | "/student/focus" | "/teacher", fetchMock = createCurriculumFetch()) {
  vi.stubGlobal("fetch", fetchMock);
  return render(<MemoryRouter initialEntries={[path]}><AppProvider><App /></AppProvider></MemoryRouter>);
}

async function openJourney() {
  const user = userEvent.setup();
  renderApp("/student");
  await user.click(await screen.findByRole("button", { name: "Start Focus Journey" }));
  await screen.findByRole("heading", { name: "What plants need" });
  return user;
}

async function answerAndContinue(user: ReturnType<typeof userEvent.setup>, answer: string) {
  await user.click(screen.getByLabelText(answer));
  await user.click(screen.getByRole("button", { name: "Continue" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "localStorage", { configurable: true, value: nativeLocalStorage });
  nativeLocalStorage.clear();
});

describe("Phase 4A Focus Journey", () => {
  it("shows Start Focus Journey on the approved student lesson", async () => {
    renderApp("/student");
    expect(await screen.findByRole("heading", { name: "Help me focus" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start Focus Journey" })).toBeInTheDocument();
  });

  it("renders trusted concepts in their approved order", async () => {
    const user = await openJourney();
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    await answerAndContinue(user, "Photosynthesis");
    expect(await screen.findByRole("heading", { name: "How inputs reach the leaf" })).toBeInTheDocument();
    await answerAndContinue(user, "Stomata");
    expect(await screen.findByRole("heading", { name: "Sunlight and chlorophyll" })).toBeInTheDocument();
    await answerAndContinue(user, "Chlorophyll");
    expect(await screen.findByRole("heading", { name: "Making glucose" })).toBeInTheDocument();
    await answerAndContinue(user, "Glucose");
    expect(await screen.findByRole("heading", { name: "Releasing oxygen" })).toBeInTheDocument();
  });

  it("uses mutated approved concepts and explicit glossary relationships without a fixed Photosynthesis mapping", async () => {
    renderApp("/student/focus", createCurriculumFetch({
      transformStudentLesson: (lesson) => ({
        ...lesson,
        concepts: lesson.concepts.map((concept) => ({ ...concept, title: `Trusted concept ${concept.sequence}`, definition: `Approved explanation ${concept.sequence}.` })),
        glossary_terms: lesson.glossary_terms.map((term) => ({ ...term, canonical_term: `Approved term ${term.sequence}` })),
      }),
    }));
    expect(await screen.findByRole("heading", { name: "Trusted concept 1" })).toBeInTheDocument();
    expect(screen.getByText("Approved explanation 1.")).toBeInTheDocument();
    expect(screen.getByLabelText("Approved term 1")).toBeInTheDocument();
    expect(screen.queryByText("Photosynthesis")).not.toBeInTheDocument();
  });

  it("fails closed when an approved concept has no explicit glossary relationship", async () => {
    renderApp("/student/focus", createCurriculumFetch({
      transformStudentLesson: (lesson) => ({
        ...lesson,
        glossary_terms: lesson.glossary_terms.map((term) => ({
          ...term,
          concept_ids: term.concept_ids?.filter((conceptId) => conceptId !== "concept-5") ?? [],
        })),
      }),
    }));
    expect(await screen.findByRole("heading", { name: "Focus Journey unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to full lesson" })).toBeInTheDocument();
  });

  it("shows only one concept step at a time", async () => {
    await openJourney();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "How inputs reach the leaf" })).not.toBeInTheDocument();
  });

  it("gives supportive feedback and blocks Continue after an incorrect answer", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Chlorophyll"));
    expect(screen.getByRole("status")).toHaveTextContent("Not quite. Look at the explanation once more and try again.");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("enables Continue after the correct answer", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    expect(screen.getByRole("status")).toHaveTextContent("That’s right. You can continue when you’re ready.");
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("removes completion when the current answer changes from correct to incorrect and restores it when corrected", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    await user.click(screen.getByLabelText("Chlorophyll"));
    expect(screen.getByRole("status")).toHaveTextContent("Not quite. Look at the explanation once more and try again.");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const persisted = readFocusJourneyProgress(`shravya:focus:${course.id}:${v1}:v1`, steps).progress;
    expect(persisted.selectedAnswers[steps[0].id]).toBe("Chlorophyll");
    expect(persisted.completedStepIds).not.toContain(steps[0].id);
    expect(persisted.correctAnswers[steps[0].id]).toBeUndefined();
    await user.click(screen.getByLabelText("Photosynthesis"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("continues to the next trusted concept", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    expect(await screen.findByText("Step 2 of 5")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How inputs reach the leaf" })).toHaveFocus();
  });

  it("returns to the previous concept with Back", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("heading", { name: "What plants need" })).toBeInTheDocument();
  });

  it("pauses and resumes the same step", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    await user.click(screen.getByRole("button", { name: "Pause journey" }));
    expect(await screen.findByRole("heading", { name: "Journey paused" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume journey" }));
    expect(await screen.findByRole("heading", { name: "How inputs reach the leaf" })).toBeInTheDocument();
  });

  it("restores saved progress after remounting the route", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    cleanup();
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "How inputs reach the leaf" })).toBeInTheDocument();
  });

  it("changes the entry action to Resume only after valid saved progress exists", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: "Exit to full lesson" }));
    expect(await screen.findByRole("button", { name: "Resume Focus Journey" })).toBeInTheDocument();
  });

  it("starts a separate journey when the approved context version changes", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    cleanup();
    renderApp("/student/focus", createCurriculumFetch({ initialStudentVersion: 2, initialV2Status: "APPROVED" }));
    expect(await screen.findByRole("heading", { name: "What plants need" })).toBeInTheDocument();
  });

  it("safely restarts when stored progress is corrupted", async () => {
    window.localStorage.setItem(`shravya:focus:${course.id}:${v1}:v1`, "not-json");
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("rejects impossible persisted progress and accepts a fully valid completed journey", () => {
    const journeyKey = `shravya:focus:${course.id}:${v1}:v1`;
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const base = newFocusJourneyProgress(journeyKey);
    const invalidStates = [
      { ...base, isComplete: true },
      { ...base, completedStepIds: ["unknown-step"], correctAnswers: { "unknown-step": "Answer" }, selectedAnswers: { "unknown-step": "Answer" } },
      { ...base, completedStepIds: [steps[0].id, steps[0].id], correctAnswers: { [steps[0].id]: steps[0].check.correctAnswer }, selectedAnswers: { [steps[0].id]: steps[0].check.correctAnswer } },
      { ...base, selectedAnswers: { [steps[0].id]: "invalid option" } },
      { ...base, completedStepIds: [steps[0].id], correctAnswers: { [steps[0].id]: "incorrect" }, selectedAnswers: { [steps[0].id]: "incorrect" } },
      { ...base, currentStepIndex: steps.length },
      { ...base, lastUpdated: "not-a-date" },
      { ...base, journeyKey: "shravya:focus:another-course:another-context:v2" },
    ];
    for (const invalid of invalidStates) {
      window.localStorage.setItem(journeyKey, JSON.stringify(invalid));
      const result = readFocusJourneyProgress(journeyKey, steps);
      expect(result.hasValidProgress).toBe(false);
      expect(result.progress.isComplete).toBe(false);
      expect(result.progress.currentStepIndex).toBe(0);
    }

    const answers = Object.fromEntries(steps.map((step) => [step.id, step.check.correctAnswer]));
    const complete = { ...base, currentStepIndex: steps.length - 1, completedStepIds: steps.map((step) => step.id), selectedAnswers: answers, correctAnswers: answers, isComplete: true };
    window.localStorage.setItem(journeyKey, JSON.stringify(complete));
    expect(readFocusJourneyProgress(journeyKey, steps)).toMatchObject({ hasValidProgress: true, progress: complete });
  });

  it("restarts only the current journey after confirmation", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    window.localStorage.setItem("shravya:focus:another-course:context:v1", "preserve-me");
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    expect(screen.getByRole("dialog", { name: "Restart journey?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm restart" }));
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(window.localStorage.getItem("shravya:focus:another-course:context:v1")).toBe("preserve-me");
  });

  it("keeps the journey usable when reading storage fails or localStorage is unavailable", async () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: () => { throw new Error("denied"); }, setItem: () => undefined, removeItem: () => undefined } as unknown as Storage,
    });
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    expect(screen.getByText("Progress is being kept for this visit only because device storage is unavailable.")).toBeInTheDocument();
    cleanup();
    Object.defineProperty(window, "localStorage", { configurable: true, get: () => { throw new Error("unavailable"); } });
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "What plants need" })).toBeInTheDocument();
  });

  it("keeps in-memory progress when saving or removing storage fails", async () => {
    const values = new Map<string, string>([["shravya:focus:another-course:context:v1", "preserve-me"]]);
    let saveAttempts = 0;
    let removeAttempts = 0;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: () => { saveAttempts += 1; throw new Error("quota denied"); },
        removeItem: () => { removeAttempts += 1; throw new Error("remove denied"); },
      } as unknown as Storage,
    });
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    expect(screen.getByText("Progress is being kept for this visit only because device storage is unavailable.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    await user.click(screen.getByRole("button", { name: "Confirm restart" }));
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(saveAttempts).toBeGreaterThan(0);
    expect(removeAttempts).toBe(1);
    expect(values.get("shravya:focus:another-course:context:v1")).toBe("preserve-me");
  });

  it("shows completion after the fifth correct check", async () => {
    const user = await openJourney();
    for (const answer of ["Photosynthesis", "Stomata", "Chlorophyll", "Glucose", "Oxygen"]) {
      await user.click(screen.getByLabelText(answer));
      if (answer !== "Oxygen") await user.click(screen.getByRole("button", { name: "Continue" }));
    }
    expect(await screen.findByRole("heading", { name: "Journey complete" })).toBeInTheDocument();
    expect(screen.getByText("You explored the lesson one step at a time.")).toBeInTheDocument();
  });

  it("does not show the pathway on the teacher page", async () => {
    renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    expect(screen.queryByText("Help me focus")).not.toBeInTheDocument();
  });

  it("provides labelled progress, a semantic answer group, and keyboard controls", async () => {
    const user = await openJourney();
    expect(screen.getByRole("progressbar", { name: "Focus Journey progress: Step 1 of 5" })).toHaveAttribute("aria-valuenow", "1");
    const check = screen.getByRole("group", { name: /Which key term is listed first/ });
    expect(within(check).getAllByRole("radio")).toHaveLength(3);
    screen.getByLabelText("Photosynthesis").focus();
    await user.keyboard("{ArrowDown}");
    expect(within(check).getAllByRole("radio").some((radio) => radio === document.activeElement)).toBe(true);
  });
});
