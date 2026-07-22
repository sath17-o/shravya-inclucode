import type { Concept, GlossaryTerm, Lesson, StudentOverview } from "../api/contracts";

export const FOCUS_JOURNEY_PATHWAY = "focus";
export const FOCUS_JOURNEY_PROGRESS_SCHEMA = 4;

export type FocusSupportMode =
  | "less_at_once"
  | "clear_path"
  | "word_support"
  | "examples"
  | "choose_as_i_go";

export type FocusJourneyScreen = "support-choice" | "journey-preview" | "concept" | "complete";

export type FocusRecoveryStage = 1 | 2 | 3 | 4 | 5 | 6;

export type FocusRecoveryProgress = {
  recoveryOpened: boolean;
  currentRecoveryStage: FocusRecoveryStage;
  highestRecoveryStage: FocusRecoveryStage;
  returnedToTry: boolean;
};

export const FOCUS_SUPPORT_OPTIONS: ReadonlyArray<{
  mode: FocusSupportMode;
  label: string;
  description: string;
}> = [
  { mode: "less_at_once", label: "Less at once", description: "Show one short idea at a time." },
  { mode: "clear_path", label: "A clear path", description: "Show what I am doing now and what comes next." },
  { mode: "word_support", label: "Help with words", description: "Make difficult words clear in Malayalam and English." },
  { mode: "examples", label: "Examples when needed", description: "Show a concrete example when an idea feels unclear." },
  { mode: "choose_as_i_go", label: "Let me choose as I go", description: "Keep every kind of support available during the lesson." },
];

export type FocusJourneyProgress = {
  schemaVersion: number;
  journeyKey: string;
  trustedContextVersion: number | null;
  supportMode: FocusSupportMode | null;
  screen: FocusJourneyScreen;
  currentStepIndex: number;
  recoveryByConcept: Record<string, FocusRecoveryProgress>;
  completedStepIds: string[];
  selectedAnswers: Record<string, string>;
  correctAnswers: Record<string, string>;
  paused: boolean;
  isComplete: boolean;
  lastUpdated: string;
};

export type FocusJourneyStep = {
  id: string;
  concept: Concept;
  explanation: string;
  terms: GlossaryTerm[];
  check: {
    prompt: string;
    correctAnswer: string;
    options: string[];
  };
};

export type FocusJourneyStorageResult = {
  progress: FocusJourneyProgress;
  hasValidProgress: boolean;
  persistenceAvailable: boolean;
};

function conciseTrustedText(concept: Concept): string | null {
  const firstLine = concept.definition.trim().split(/\r?\n|(?<=[.!?])\s/)[0]?.trim();
  if (!firstLine) return null;
  return firstLine.length > 180 ? `${firstLine.slice(0, 177).trimEnd()}…` : firstLine;
}

function linkedTerms(concept: Concept, glossaryTerms: GlossaryTerm[]): GlossaryTerm[] {
  return glossaryTerms
    .filter((term) => Array.isArray(term.concept_ids) && term.concept_ids.includes(concept.id))
    .sort((first, second) => first.sequence - second.sequence);
}

function uniqueTerms(terms: GlossaryTerm[]): string[] {
  return [...new Set(terms.map((term) => term.canonical_term))];
}

export function buildFocusJourneySteps(lesson: Lesson): FocusJourneyStep[] {
  const concepts = [...lesson.concepts].sort((first, second) => first.sequence - second.sequence);
  if (concepts.length !== 5) return [];
  const explicitlyLinkedTerms = lesson.glossary_terms.filter((term) => Array.isArray(term.concept_ids) && term.concept_ids.length > 0);
  const allOptions = uniqueTerms(explicitlyLinkedTerms);
  const steps: FocusJourneyStep[] = [];

  for (const concept of concepts) {
    const explanation = conciseTrustedText(concept);
    const terms = linkedTerms(concept, lesson.glossary_terms);
    const correctAnswer = terms[0]?.canonical_term;
    const options = correctAnswer ? [correctAnswer, ...allOptions.filter((term) => term !== correctAnswer)].slice(0, 3) : [];
    if (!explanation || !correctAnswer || options.length < 2) return [];
    steps.push({
      id: concept.id,
      concept,
      explanation,
      terms,
      check: {
        prompt: `Which key term is listed first for “${concept.title}”?`,
        correctAnswer,
        options,
      },
    });
  }
  return steps;
}

export function focusJourneyStorageKey(overview: StudentOverview): string | null {
  if (!overview.selected_context_id || overview.version_number === null) return null;
  return `shravya:${FOCUS_JOURNEY_PATHWAY}:${overview.course.id}:${overview.selected_context_id}:v${overview.version_number}`;
}

function contextVersionFromJourneyKey(journeyKey: string): number | null {
  const match = /:v(\d+)$/.exec(journeyKey);
  return match ? Number(match[1]) : null;
}

export function newFocusJourneyProgress(journeyKey = ""): FocusJourneyProgress {
  return {
    schemaVersion: FOCUS_JOURNEY_PROGRESS_SCHEMA,
    journeyKey,
    trustedContextVersion: contextVersionFromJourneyKey(journeyKey),
    supportMode: null,
    screen: "support-choice",
    currentStepIndex: 0,
    recoveryByConcept: {},
    completedStepIds: [],
    selectedAnswers: {},
    correctAnswers: {},
    paused: false,
    isComplete: false,
    lastUpdated: new Date().toISOString(),
  };
}

function safeStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return Boolean(value && typeof value === "object") && Object.values(value as Record<string, unknown>).every((item) => typeof item === "string");
}

function isValidRecoveryRecord(value: unknown, steps: FocusJourneyStep[]): value is Record<string, FocusRecoveryProgress> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const stepIds = new Set(steps.map((step) => step.id));
  const fields = new Set(["recoveryOpened", "currentRecoveryStage", "highestRecoveryStage", "returnedToTry"]);
  return Object.entries(value as Record<string, unknown>).every(([conceptId, recovery]) => {
    if (!stepIds.has(conceptId) || !recovery || typeof recovery !== "object" || Array.isArray(recovery)) return false;
    const candidate = recovery as Partial<FocusRecoveryProgress>;
    return Object.keys(candidate).every((field) => fields.has(field))
      && typeof candidate.recoveryOpened === "boolean"
      && typeof candidate.returnedToTry === "boolean"
      && !(candidate.recoveryOpened && candidate.returnedToTry)
      && Number.isInteger(candidate.currentRecoveryStage)
      && Number.isInteger(candidate.highestRecoveryStage)
      && (candidate.currentRecoveryStage ?? 0) >= 1
      && (candidate.currentRecoveryStage ?? 7) <= 6
      && (candidate.highestRecoveryStage ?? 0) >= (candidate.currentRecoveryStage ?? 7)
      && (candidate.highestRecoveryStage ?? 7) <= 6;
  });
}

function isValidProgress(value: unknown, journeyKey: string, steps: FocusJourneyStep[]): value is FocusJourneyProgress {
  if (!value || typeof value !== "object" || steps.length === 0) return false;
  const progress = value as Partial<FocusJourneyProgress>;
  if (progress.schemaVersion !== FOCUS_JOURNEY_PROGRESS_SCHEMA || progress.journeyKey !== journeyKey) return false;
  if (progress.trustedContextVersion !== contextVersionFromJourneyKey(journeyKey)) return false;
  if (!FOCUS_SUPPORT_OPTIONS.some((option) => option.mode === progress.supportMode) && progress.supportMode !== null) return false;
  if (!["support-choice", "journey-preview", "concept", "complete"].includes(progress.screen ?? "")) return false;
  if (progress.screen !== "support-choice" && progress.supportMode === null) return false;
  if (!Number.isInteger(progress.currentStepIndex) || (progress.currentStepIndex ?? -1) < 0 || (progress.currentStepIndex ?? steps.length) >= steps.length) return false;
  if (!Array.isArray(progress.completedStepIds) || !progress.completedStepIds.every((id) => typeof id === "string")) return false;
  if (new Set(progress.completedStepIds).size !== progress.completedStepIds.length) return false;
  if (!isValidRecoveryRecord(progress.recoveryByConcept, steps)) return false;
  if (!isStringRecord(progress.selectedAnswers) || !isStringRecord(progress.correctAnswers)) return false;
  if (typeof progress.paused !== "boolean" || typeof progress.isComplete !== "boolean" || typeof progress.lastUpdated !== "string" || Number.isNaN(Date.parse(progress.lastUpdated))) return false;

  const stepsById = new Map(steps.map((step) => [step.id, step]));
  const completed = new Set(progress.completedStepIds);
  for (const [stepId, answer] of Object.entries(progress.selectedAnswers)) {
    const step = stepsById.get(stepId);
    if (!step || !step.check.options.includes(answer)) return false;
  }
  for (const [stepId, answer] of Object.entries(progress.correctAnswers)) {
    const step = stepsById.get(stepId);
    if (!step || answer !== step.check.correctAnswer || progress.selectedAnswers[stepId] !== answer) return false;
  }
  for (const stepId of completed) {
    const step = stepsById.get(stepId);
    if (!step || progress.correctAnswers[stepId] !== step.check.correctAnswer || progress.selectedAnswers[stepId] !== step.check.correctAnswer) return false;
  }
  if (completed.size !== Object.keys(progress.correctAnswers).length) return false;

  const allCompleted = steps.every((step) => completed.has(step.id));
  if (progress.isComplete !== allCompleted) return false;
  if (progress.isComplete && (progress.currentStepIndex !== steps.length - 1 || progress.screen !== "complete")) return false;
  if (!progress.isComplete && progress.screen === "complete") return false;
  if (progress.paused && progress.screen !== "concept") return false;
  const firstIncomplete = steps.findIndex((step) => !completed.has(step.id));
  return progress.isComplete || (progress.currentStepIndex ?? 0) <= firstIncomplete;
}

export function readFocusJourneyProgress(journeyKey: string, steps: FocusJourneyStep[]): FocusJourneyStorageResult {
  const fresh = newFocusJourneyProgress(journeyKey);
  const storage = safeStorage();
  if (!storage) return { progress: fresh, hasValidProgress: false, persistenceAvailable: false };
  try {
    const parsed: unknown = JSON.parse(storage.getItem(journeyKey) ?? "null");
    return isValidProgress(parsed, journeyKey, steps)
      ? { progress: parsed, hasValidProgress: true, persistenceAvailable: true }
      : { progress: fresh, hasValidProgress: false, persistenceAvailable: true };
  } catch {
    return { progress: fresh, hasValidProgress: false, persistenceAvailable: false };
  }
}

export function hasStoredFocusJourneyProgress(journeyKey: string, steps: FocusJourneyStep[]): boolean {
  return readFocusJourneyProgress(journeyKey, steps).hasValidProgress;
}

export function saveFocusJourneyProgress(journeyKey: string, progress: FocusJourneyProgress): boolean {
  const storage = safeStorage();
  if (!storage) return false;
  try {
    storage.setItem(journeyKey, JSON.stringify(progress));
    return true;
  } catch {
    return false;
  }
}

export function clearFocusJourneyProgress(journeyKey: string): boolean {
  const storage = safeStorage();
  if (!storage) return false;
  try {
    storage.removeItem(journeyKey);
    return true;
  } catch {
    return false;
  }
}
