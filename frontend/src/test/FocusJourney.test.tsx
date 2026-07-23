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
import { readReadingPreferences } from "../features/readingPreferences";
import type { StudentLesson } from "../api/contracts";
import { course, createCurriculumFetch, focusLessonFixture, v1 } from "./curriculumFixtures";

const nativeLocalStorage = window.localStorage;
const supportNames = {
  oneStep: /One step at a time\s+Show one clear step and one support at a time\./,
  helpWithWords: /Help with words\s+Make important Malayalam and English words clear\./,
  chooseSupport: /Let me choose support\s+Let me choose a cue, example or explanation when I need it\./,
};

function withApprovedRecoverySupport(lesson: StudentLesson): StudentLesson {
  return {
    ...lesson,
    recovery_support: lesson.concepts.map((concept) => ({
      concept_id: concept.id,
      cue: { english: `Approved cue for ${concept.title}.`, malayalam: `അംഗീകരിച്ച സൂചന ${concept.sequence}.` },
      example: { english: `Approved example for ${concept.title}.`, malayalam: `അംഗീകരിച്ച ഉദാഹരണം ${concept.sequence}.` },
      alternate_explanation: { english: `Approved alternate explanation for ${concept.title}.`, malayalam: `അംഗീകരിച്ച മറ്റൊരു വിശദീകരണം ${concept.sequence}.` },
    })),
  };
}

function recoveryFetch(transform?: (lesson: StudentLesson) => StudentLesson, options: { studentContextId?: string } = {}) {
  return createCurriculumFetch({
    studentContextId: options.studentContextId,
    transformStudentLesson: (lesson) => transform ? transform(withApprovedRecoverySupport(lesson)) : withApprovedRecoverySupport(lesson),
  });
}

function renderApp(path: "/student" | "/student/focus" | "/teacher", fetchMock = createCurriculumFetch()) {
  vi.stubGlobal("fetch", fetchMock);
  return render(<MemoryRouter initialEntries={[path]}><AppProvider><App /></AppProvider></MemoryRouter>);
}

async function selectSupport(user: ReturnType<typeof userEvent.setup>, label = supportNames.oneStep) {
  await user.click(await screen.findByRole("radio", { name: label }));
  await user.click(screen.getByRole("button", { name: "Continue with this support" }));
  await screen.findByRole("button", { name: "Start with step 1" });
}

async function openJourney(fetchMock = recoveryFetch(), firstConcept = "What plants need") {
  const user = userEvent.setup();
  renderApp("/student", fetchMock);
  await user.click(await screen.findByRole("button", { name: "Start Focus Journey" }));
  await selectSupport(user);
  await user.click(screen.getByRole("button", { name: "Start with step 1" }));
  await screen.findByRole("heading", { name: firstConcept });
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

describe("Phase 4 Focus Journey", () => {
  it("shows Start Focus Journey on the approved student lesson", async () => {
    renderApp("/student");
    expect(await screen.findByRole("heading", { name: "Help me focus" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start Focus Journey" })).toBeInTheDocument();
  });

  it("opens support choice first with three accessible single-select options", async () => {
    renderApp("/student/focus", recoveryFetch());
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    expect(screen.getByText("FOCUS JOURNEY")).toBeInTheDocument();
    expect(screen.getByText("Show one clear step and one support at a time.")).toBeInTheDocument();
    expect(screen.getByText("Make important Malayalam and English words clear.")).toBeInTheDocument();
    expect(screen.getByText("Let me choose a cue, example or explanation when I need it.")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    const radios = screen.getAllByRole("radio");
    expect(radios[0]).toHaveAccessibleName(supportNames.oneStep);
    expect(radios[1]).toHaveAccessibleName(supportNames.helpWithWords);
    expect(radios[2]).toHaveAccessibleName(supportNames.chooseSupport);
    expect(radios.every((radio) => !radio.hasAttribute("aria-label"))).toBe(true);
    expect(screen.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
    expect(screen.queryByText(/ADHD|autism|dyslexia|disability|medical profile/i)).not.toBeInTheDocument();
  });

  it("selects exactly one support and previews trusted Now and Next steps before later steps are requested", async () => {
    const user = userEvent.setup();
    renderApp("/student/focus");
    await user.click(await screen.findByRole("radio", { name: supportNames.oneStep }));
    expect(screen.getByRole("radio", { name: supportNames.oneStep })).toBeChecked();
    expect(screen.getByRole("radio", { name: supportNames.helpWithWords })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    expect(await screen.findByText("Support: One step at a time")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start with step 1" })).toHaveClass("focus-primary-action");
    expect(screen.getByRole("button", { name: "Change" })).toHaveClass("focus-text-action");
    expect(screen.getByRole("heading", { name: "5 small steps" })).toBeInTheDocument();
    expect(screen.getByText("Now")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "See 3 later steps" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Making glucose")).not.toBeInTheDocument();
    expect(screen.getByText("What plants need")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "See 3 later steps" }));
    expect(screen.getByRole("button", { name: "Hide later steps" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Later")).toHaveLength(3);
    expect(screen.getByText("Making glucose")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hide later steps" }));
    expect(screen.getByRole("button", { name: "See 3 later steps" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Making glucose")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Change" }));
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: supportNames.oneStep })).toBeChecked();
  });

  it("migrates every valid Phase 4B.2B support mode to a current canonical mode", () => {
    const journeyKey = `shravya:focus:${course.id}:${v1}:v1`;
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const mappings = {
      less_at_once: "one_step_at_a_time",
      clear_path: "one_step_at_a_time",
      word_support: "help_with_words",
      examples: "choose_support",
      choose_as_i_go: "choose_support",
    };
    for (const [legacyMode, expectedMode] of Object.entries(mappings)) {
      const legacy = { ...newFocusJourneyProgress(journeyKey), schemaVersion: 4, supportMode: legacyMode, screen: "journey-preview" };
      window.localStorage.setItem(journeyKey, JSON.stringify(legacy));
      expect(readFocusJourneyProgress(journeyKey, steps)).toMatchObject({ hasValidProgress: true, progress: { schemaVersion: 5, supportMode: expectedMode } });
      expect(JSON.parse(window.localStorage.getItem(journeyKey)!).supportMode).toBe(expectedMode);
    }
  });

  it("resets malformed legacy support state instead of preserving it", () => {
    const journeyKey = `shravya:focus:${course.id}:${v1}:v1`;
    const steps = buildFocusJourneySteps(focusLessonFixture());
    window.localStorage.setItem(journeyKey, JSON.stringify({ ...newFocusJourneyProgress(journeyKey), schemaVersion: 4, supportMode: "unknown_mode", screen: "journey-preview" }));
    expect(readFocusJourneyProgress(journeyKey, steps)).toMatchObject({ hasValidProgress: false, progress: { supportMode: null, screen: "support-choice" } });
  });

  it("derives preview names and ordering from the approved lesson", async () => {
    const user = userEvent.setup();
    renderApp("/student/focus", createCurriculumFetch({
      transformStudentLesson: (lesson) => ({
        ...lesson,
        concepts: lesson.concepts.map((concept) => ({
          ...concept,
          title: `Approved preview ${concept.sequence}`,
        })),
      }),
    }));
    await user.click(await screen.findByRole("radio", { name: supportNames.oneStep }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    const preview = screen.getByRole("heading", { name: "5 small steps" }).closest("section");
    expect(within(preview!).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("NowApproved preview 1"),
      expect.stringContaining("NextApproved preview 2"),
    ]);
    await user.click(screen.getByRole("button", { name: "See 3 later steps" }));
    expect(within(preview!).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("NowApproved preview 1"),
      expect.stringContaining("NextApproved preview 2"),
      expect.stringContaining("LaterApproved preview 3"),
      expect.stringContaining("LaterApproved preview 4"),
      expect.stringContaining("LaterApproved preview 5"),
    ]);
    expect(screen.getByRole("button", { name: "Hide later steps" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByText("What plants need")).not.toBeInTheDocument();
    expect(screen.queryByText(/revisit/i)).not.toBeInTheDocument();
  });

  it("restores the selected support and preview screen after a refresh", async () => {
    const user = userEvent.setup();
    renderApp("/student/focus");
    await user.click(await screen.findByRole("radio", { name: supportNames.helpWithWords }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    cleanup();
    renderApp("/student/focus");
    expect(await screen.findByText("Support: Help with words")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start with step 1" })).toBeInTheDocument();
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
    await openJourney(createCurriculumFetch({
      transformStudentLesson: (lesson) => ({
        ...lesson,
        concepts: lesson.concepts.map((concept) => ({ ...concept, title: `Trusted concept ${concept.sequence}`, definition: `Approved explanation ${concept.sequence}.` })),
        glossary_terms: lesson.glossary_terms.map((term) => ({ ...term, canonical_term: `Approved term ${term.sequence}` })),
      }),
    }), "Trusted concept 1");
    expect(screen.getByRole("heading", { name: "Trusted concept 1" })).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "More" }));
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
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Exit to full lesson" }));
    expect(await screen.findByRole("button", { name: "Resume Focus Journey" })).toBeInTheDocument();
  });

  it("starts a separate journey when the approved context version changes", async () => {
    const user = await openJourney();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("heading", { name: "Let’s find a way through" })).toBeInTheDocument();
    cleanup();
    renderApp("/student/focus", createCurriculumFetch({ initialStudentVersion: 2, initialV2Status: "APPROVED" }));
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
  });

  it("opens the approved recovery journey without completing or skipping the current concept", async () => {
    const user = await openJourney();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    const recovery = await screen.findByRole("heading", { name: "Let’s find a way through" });
    expect(recovery).toHaveFocus();
    const panel = recovery.closest("section");
    expect(within(panel!).getByText("Show the important words")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  });

  it("provides the recovery action on every approved concept screen", async () => {
    const user = await openJourney();
    for (const answer of ["Photosynthesis", "Stomata", "Chlorophyll", "Glucose"]) {
      expect(screen.getByRole("button", { name: "I’m stuck" })).toBeInTheDocument();
      await answerAndContinue(user, answer);
    }
    expect(await screen.findByRole("heading", { name: "Releasing oxygen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I’m stuck" })).toBeInTheDocument();
  });

  it("reveals only approved recovery support in six deliberate stages", async () => {
    const user = await openJourney();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    const words = await screen.findByRole("heading", { name: "Let’s find a way through" });
    expect(within(words.closest("section")!).getByText("Water")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Give me a small cue" }));
    expect(await screen.findByText("Approved cue for What plants need.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show a concrete example" }));
    expect(await screen.findByText("Approved example for What plants need.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show another explanation" }));
    expect(await screen.findByText("Approved alternate explanation for What plants need.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show where this fits" }));
    const flow = await screen.findByRole("heading", { name: "Let’s find a way through" });
    expect(within(flow.closest("section")!).getByText("Now")).toBeInTheDocument();
    expect(within(flow.closest("section")!).getByText("Next")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Let me try again" }));
    expect(screen.queryByRole("heading", { name: "Concept connection" })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /Which key term is listed first/ })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Continue support" }));
    expect(await screen.findByRole("heading", { name: "Concept connection" })).toBeInTheDocument();
  });

  it("activates the compact journey shell that hides demo chrome in the browser", async () => {
    await openJourney();
    expect(document.body).toHaveClass("focus-journey-active");
    expect(document.querySelector(".site-header")).toBeInTheDocument();
    expect(document.querySelector(".primary-nav")).toBeInTheDocument();
  });

  it("keeps normal controls focused on learning and reveals utility actions only through More", async () => {
    const user = await openJourney();
    expect(screen.getByRole("button", { name: "Continue" })).toHaveClass("focus-primary-action");
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I’m stuck" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause journey" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change support" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Exit to full lesson" })).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: "More" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    more.focus();
    await user.keyboard("{Enter}");
    expect(more).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Pause journey" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change support" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exit to full lesson" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart journey" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart journey" }).closest(".focus-utility-restart")).not.toBeNull();
    await user.keyboard("{Enter}");
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Pause journey" })).not.toBeInTheDocument();
  });

  it("keeps the selected answer while recovery is the only visible learning task", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("heading", { name: "Let’s find a way through" })).toHaveFocus();
    expect(screen.queryByText("What plants need definition")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Key terms" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /Which key term is listed first/ })).not.toBeInTheDocument();
    for (const label of ["Back", "Continue", "I’m stuck", "More", "Pause journey", "Change support", "Exit to full lesson", "Restart journey"]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/Support step|Next:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Orient" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Step 1 of 5")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { name: "What plants need" })).toHaveLength(1);
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const storedDuringRecovery = readFocusJourneyProgress(`shravya:focus:${course.id}:${v1}:v1`, steps).progress;
    expect(storedDuringRecovery.selectedAnswers[steps[0].id]).toBe("Photosynthesis");
    expect(storedDuringRecovery.completedStepIds).not.toContain(steps[0].id);
    await user.click(screen.getByRole("button", { name: "Return to question" }));
    expect(screen.getByLabelText("Photosynthesis")).toBeChecked();
    expect(screen.getByRole("group", { name: /Which key term is listed first/ })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("returns from Let me try again without completing the concept", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    for (const action of ["Show the important words", "Give me a small cue", "Show a concrete example", "Show another explanation", "Show where this fits"]) {
      await user.click(screen.getByRole("button", { name: action }));
    }
    await user.click(screen.getByRole("button", { name: "Let me try again" }));
    expect(screen.getByLabelText("Photosynthesis")).toBeChecked();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const recovered = readFocusJourneyProgress(`shravya:focus:${course.id}:${v1}:v1`, steps).progress;
    expect(recovered.completedStepIds).not.toContain(steps[0].id);
    expect(recovered.recoveryByConcept[steps[0].id]).toMatchObject({ recoveryOpened: false, returnedToTry: true, highestRecoveryStage: 6 });
  });

  it("derives the recovery flow from the approved concept sequence", async () => {
    const user = await openJourney(recoveryFetch((lesson) => ({
        ...lesson,
        concepts: lesson.concepts.map((concept) => ({ ...concept, title: `Approved recovery ${concept.sequence}` })),
      })), "Approved recovery 1");
    await answerAndContinue(user, "Photosynthesis");
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    await user.click(screen.getByRole("button", { name: "Give me a small cue" }));
    await user.click(screen.getByRole("button", { name: "Show a concrete example" }));
    await user.click(screen.getByRole("button", { name: "Show another explanation" }));
    await user.click(screen.getByRole("button", { name: "Show where this fits" }));
    const flow = await screen.findByRole("heading", { name: "Let’s find a way through" });
    const panel = within(flow.closest("section")!);
    expect(panel.getByText("Approved recovery 1")).toBeInTheDocument();
    expect(panel.getByText("Approved recovery 2")).toBeInTheDocument();
    expect(panel.getByText("Approved recovery 3")).toBeInTheDocument();
  });

  it("fails closed when the approved recovery support is missing", async () => {
    const user = await openJourney(createCurriculumFetch());
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByText("Support for this step is not available yet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to question" }));
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
  });

  it("fails closed for an incomplete matching recovery pack without rendering partial support", async () => {
    const user = await openJourney(recoveryFetch((lesson) => ({
      ...lesson,
      recovery_support: lesson.recovery_support.map((pack, index) => index === 0 ? {
        ...pack,
        cue: { ...pack.cue, english: "" },
      } : pack),
    })));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByText("Support for this step is not available yet.")).toBeInTheDocument();
    expect(screen.queryByText("Approved example for What plants need.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  });

  it("fails closed for duplicate matching packs instead of selecting either pack", async () => {
    const user = await openJourney(recoveryFetch((lesson) => ({
      ...lesson,
      recovery_support: [...lesson.recovery_support, {
        ...lesson.recovery_support[0],
        cue: { english: "Duplicate pack cue.", malayalam: "ആവര്‍ത്തിച്ച സൂചന." },
      }],
    })));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByText("Support for this step is not available yet.")).toBeInTheDocument();
    expect(screen.queryByText("Approved cue for What plants need.")).not.toBeInTheDocument();
    expect(screen.queryByText("Duplicate pack cue.")).not.toBeInTheDocument();
  });

  it("fails closed for a pack belonging to another concept", async () => {
    const user = await openJourney(recoveryFetch((lesson) => ({
      ...lesson,
      recovery_support: lesson.recovery_support.filter((pack) => pack.concept_id !== "concept-1"),
    })));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByText("Support for this step is not available yet.")).toBeInTheDocument();
    expect(screen.queryByText("Approved cue for How inputs reach the leaf.")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What plants need" })).toBeInTheDocument();
  });

  it("keeps recovery stage isolated for each approved concept", async () => {
    const user = await openJourney();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    await user.click(screen.getByRole("button", { name: "Give me a small cue" }));
    expect(await screen.findByText("Approved cue for What plants need.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to question" }));
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: /^Continue$/ }));
    expect(await screen.findByRole("heading", { name: "How inputs reach the leaf" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("heading", { name: "Let’s find a way through" })).toBeInTheDocument();
    expect(screen.queryByText("Approved cue for What plants need.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to question" }));
    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Continue support" }));
    expect(await screen.findByText("Approved cue for What plants need.")).toBeInTheDocument();
  });

  it("restores an open recovery stage after remounting and clears it on restart", async () => {
    const user = await openJourney();
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    cleanup();
    renderApp("/student/focus", recoveryFetch());
    expect(await screen.findByRole("heading", { name: "Let’s find a way through" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to question" }));
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    expect(await screen.findByText("Support: One step at a time")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("heading", { name: "Let’s find a way through" })).toBeInTheDocument();
  });

  it("uses each selected support mode only to present approved recovery support", async () => {
    const user = userEvent.setup();
    renderApp("/student/focus", recoveryFetch());
    await user.click(await screen.findByRole("radio", { name: supportNames.oneStep }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("button", { name: "Show the important words" })).toBeInTheDocument();
    expect(screen.queryByText(/Support step|Next:/)).not.toBeInTheDocument();
    cleanup();
    nativeLocalStorage.clear();
    renderApp("/student/focus", recoveryFetch());
    await user.click(await screen.findByRole("radio", { name: supportNames.helpWithWords }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    const wordSupportPanel = screen.getByRole("heading", { name: "Let’s find a way through" }).closest("section")!;
    expect(within(wordSupportPanel).getByText("Photosynthesis")).toBeInTheDocument();
    cleanup();
    nativeLocalStorage.clear();
    renderApp("/student/focus", recoveryFetch());
    await user.click(await screen.findByRole("radio", { name: supportNames.chooseSupport }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    await user.click(screen.getByRole("button", { name: "Give me a small cue" }));
    await user.click(screen.getByRole("button", { name: "Show a concrete example" }));
    expect(await screen.findByText("Approved example for What plants need.")).toBeInTheDocument();
    cleanup();
    nativeLocalStorage.clear();
    renderApp("/student/focus", recoveryFetch());
    await user.click(await screen.findByRole("radio", { name: supportNames.chooseSupport }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    expect(await screen.findByRole("button", { name: "Important words" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Another explanation" })).toBeInTheDocument();
  });

  it("keeps the recovery view canonical-only while Malayalam support remains available", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    await answerAndContinue(user, "Stomata");
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    const panel = await screen.findByRole("heading", { name: "Let’s find a way through" });
    expect(within(panel.closest("section")!).getByText("Chlorophyll")).toBeInTheDocument();
    const trustedTerm = within(panel.closest("section")!).getByRole("button", { name: "Show teacher-approved meaning for Chlorophyll" });
    await user.click(trustedTerm);
    expect(within(panel.closest("section")!).getByRole("region", { name: "Teacher-approved meaning for Chlorophyll" })).toHaveTextContent("✓ Teacher-approved term");
    expect(within(panel.closest("section")!).getByText("ക്ലോറോഫിൽ")).toBeInTheDocument();
    expect(within(panel.closest("section")!).queryByRole("link", { name: /View official ISLRTC resource/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bchlorophil\b/);
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unsure" })).not.toBeInTheDocument();
  });

  it("changes support without deleting completed concept progress", async () => {
    const user = await openJourney();
    await answerAndContinue(user, "Photosynthesis");
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Change support" }));
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: supportNames.chooseSupport }));
    await user.click(screen.getByRole("button", { name: "Continue with this support" }));
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const stored = readFocusJourneyProgress(`shravya:focus:${course.id}:${v1}:v1`, steps).progress;
    expect(stored.completedStepIds).toContain(steps[0].id);
    expect(stored.supportMode).toBe("choose_support");
    expect(stored.screen).toBe("journey-preview");
  });

  it("safely restarts when stored progress is corrupted", async () => {
    window.localStorage.setItem(`shravya:focus:${course.id}:${v1}:v1`, "not-json");
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
  });

  it("shows the exact official ISLRTC link only for the structured Chlorophyll term in the authorized context", async () => {
    const authorizedFetch = recoveryFetch((lesson) => ({
      ...lesson,
      glossary_terms: lesson.glossary_terms.map((term) => term.canonical_term === "Chlorophyll" ? {
        ...term,
        id: "a7287dbc-4022-5dbb-9395-1b77c953631c",
      } : term),
    }), { studentContextId: "f069db92-d848-5546-b3ad-3b10ee301600" });
    const user = await openJourney(authorizedFetch);
    await answerAndContinue(user, "Photosynthesis");
    await answerAndContinue(user, "Stomata");
    await user.click(screen.getByRole("button", { name: "I’m stuck" }));
    await user.click(screen.getByRole("button", { name: "Show the important words" }));
    const panel = screen.getByRole("heading", { name: "Let’s find a way through" }).closest("section")!;
    await user.click(within(panel).getByRole("button", { name: "Show teacher-approved meaning for Chlorophyll" }));
    const link = within(panel).getByRole("link", { name: "View official ISLRTC resource for Chlorophyll — opens in a new tab" });
    expect(link).toHaveAttribute("href", "https://www.youtube.com/watch?v=Oqrmn9kYESk");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(within(panel).getByText("External educational resource from the Indian Sign Language Research and Training Centre.")).toBeInTheDocument();
    expect(within(panel).getByText("Developed jointly by CIET, NCERT and ISLRTC.")).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Return to question" }));
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("resets contradictory persisted recovery without opening or completing the concept", async () => {
    const journeyKey = `shravya:focus:${course.id}:${v1}:v1`;
    const steps = buildFocusJourneySteps(focusLessonFixture());
    const contradictory = {
      ...newFocusJourneyProgress(journeyKey),
      supportMode: "one_step_at_a_time" as const,
      screen: "concept" as const,
      recoveryByConcept: {
        [steps[0].id]: {
          recoveryOpened: true,
          currentRecoveryStage: 3,
          highestRecoveryStage: 3,
          returnedToTry: true,
        },
      },
    };
    window.localStorage.setItem(journeyKey, JSON.stringify(contradictory));
    expect(readFocusJourneyProgress(journeyKey, steps).hasValidProgress).toBe(false);
    renderApp("/student/focus", recoveryFetch());
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Let’s find a way through" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with this support" })).toBeDisabled();
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
      { ...base, recoveryByConcept: { [steps[0].id]: { recoveryOpened: true, currentRecoveryStage: 2, highestRecoveryStage: 2, returnedToTry: true } } },
      { ...base, recoveryByConcept: { [steps[0].id]: { recoveryOpened: false, currentRecoveryStage: 0, highestRecoveryStage: 1, returnedToTry: false } } },
      { ...base, recoveryByConcept: { [steps[0].id]: { recoveryOpened: false, currentRecoveryStage: 4, highestRecoveryStage: 3, returnedToTry: false } } },
      { ...base, recoveryByConcept: { [steps[0].id]: { recoveryOpened: "yes", currentRecoveryStage: 2, highestRecoveryStage: 2, returnedToTry: false } } },
      { ...base, recoveryByConcept: { [steps[0].id]: { recoveryOpened: false, currentRecoveryStage: 2, highestRecoveryStage: 2, returnedToTry: false, rawPack: "untrusted" } } },
    ];
    for (const invalid of invalidStates) {
      window.localStorage.setItem(journeyKey, JSON.stringify(invalid));
      const result = readFocusJourneyProgress(journeyKey, steps);
      expect(result.hasValidProgress).toBe(false);
      expect(result.progress.isComplete).toBe(false);
      expect(result.progress.currentStepIndex).toBe(0);
    }

    const answers = Object.fromEntries(steps.map((step) => [step.id, step.check.correctAnswer]));
    const complete = { ...base, supportMode: "one_step_at_a_time" as const, screen: "complete" as const, currentStepIndex: steps.length - 1, completedStepIds: steps.map((step) => step.id), selectedAnswers: answers, correctAnswers: answers, isComplete: true };
    window.localStorage.setItem(journeyKey, JSON.stringify(complete));
    expect(readFocusJourneyProgress(journeyKey, steps)).toMatchObject({ hasValidProgress: true, progress: complete });
  });

  it("restarts only the current journey after confirmation", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    window.localStorage.setItem("shravya:focus:another-course:context:v1", "preserve-me");
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    const confirmation = screen.getByRole("dialog", { name: "Restart this journey?" });
    expect(confirmation).toHaveTextContent("Your learning and recovery progress for this journey will be cleared.");
    expect(within(confirmation).getAllByRole("button").map((button) => button.textContent)).toEqual(["Keep my progress", "Restart journey"]);
    expect(within(confirmation).getByRole("button", { name: "Keep my progress" })).toHaveClass("focus-primary-action");
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    expect(await screen.findByRole("heading", { name: "5 small steps" })).toBeInTheDocument();
    expect(screen.getByText("Support: One step at a time")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(window.localStorage.getItem("shravya:focus:another-course:context:v1")).toBe("preserve-me");
  });

  it("keeps reading preferences separate from the Focus Journey reset", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("radio", { name: "Easier-to-distinguish letters" }));
    expect(readReadingPreferences().preferences.font).toBe("hyperlegible");
    await user.click(screen.getByRole("button", { name: "Reset reading settings" }));
    expect(readReadingPreferences().preferences.font).toBe("default");
    expect(screen.getByLabelText("Photosynthesis")).toBeChecked();

    await user.click(screen.getByRole("radio", { name: "Easier-to-distinguish letters" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    expect(readReadingPreferences().preferences.font).toBe("hyperlegible");
  });

  it("keeps progress when restart confirmation is cancelled and returns focus to Restart journey", async () => {
    const user = await openJourney();
    await user.click(screen.getByLabelText("Photosynthesis"));
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    const confirmation = screen.getByRole("heading", { name: "Restart this journey?" });
    expect(confirmation).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Keep my progress" }));
    const restart = screen.getByRole("button", { name: "Restart journey" });
    expect(restart).toHaveFocus();
    expect(screen.getByLabelText("Photosynthesis")).toBeChecked();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("keeps the journey usable when reading storage fails or localStorage is unavailable", async () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: () => { throw new Error("denied"); }, setItem: () => undefined, removeItem: () => undefined } as unknown as Storage,
    });
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
    cleanup();
    Object.defineProperty(window, "localStorage", { configurable: true, get: () => { throw new Error("unavailable"); } });
    renderApp("/student/focus");
    expect(await screen.findByRole("heading", { name: "How should Shravya support you right now?" })).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    await user.click(screen.getByRole("button", { name: "Restart journey" }));
    expect(await screen.findByRole("heading", { name: "5 small steps" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start with step 1" }));
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
      await user.click(screen.getByRole("button", { name: "Continue" }));
    }
    expect(await screen.findByRole("heading", { name: "Journey complete" })).toBeInTheDocument();
    expect(screen.getByText("You explored the lesson one step at a time.")).toBeInTheDocument();
  });

  it("does not show the pathway on the teacher page", async () => {
    renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    expect(screen.queryByText("Help me focus")).not.toBeInTheDocument();
  });

  it("returns to the approved full lesson from the preview", async () => {
    const user = userEvent.setup();
    renderApp("/student/focus");
    await selectSupport(user);
    await user.click(screen.getByRole("button", { name: "Return to lesson" }));
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
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
