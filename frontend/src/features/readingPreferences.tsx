import { createContext, type ReactNode, useContext, useState } from "react";

export const READING_PREFERENCES_SCHEMA = 1;
export const READING_PREFERENCES_STORAGE_KEY = "shravya:student:reading-preferences";

export type ReadingPreferences = {
  schemaVersion: number;
  font: "default" | "hyperlegible";
  textSize: "small" | "default" | "large" | "extra-large";
  spacing: "compact" | "default" | "wide";
  contrast: "default" | "high" | "dark";
  reduceMotion: boolean;
};

export const DEFAULT_READING_PREFERENCES: ReadingPreferences = {
  schemaVersion: READING_PREFERENCES_SCHEMA,
  font: "default",
  textSize: "default",
  spacing: "default",
  contrast: "default",
  reduceMotion: false,
};

type ReadingPreferencesStore = {
  preferences: ReadingPreferences;
  updatePreferences: (update: Partial<Omit<ReadingPreferences, "schemaVersion">>) => void;
  resetReadingPreferences: () => void;
};

const ReadingPreferencesContext = createContext<ReadingPreferencesStore | null>(null);

function safeStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function isOneOf<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === "string" && values.includes(value as T);
}

export function normalizeReadingPreferences(value: unknown): ReadingPreferences {
  const candidate = value && typeof value === "object" && !Array.isArray(value)
    ? value as Partial<ReadingPreferences>
    : {};
  if (candidate.schemaVersion !== undefined && candidate.schemaVersion !== READING_PREFERENCES_SCHEMA) {
    return DEFAULT_READING_PREFERENCES;
  }
  return {
    schemaVersion: READING_PREFERENCES_SCHEMA,
    font: isOneOf(candidate.font, ["default", "hyperlegible"] as const) ? candidate.font : "default",
    textSize: isOneOf(candidate.textSize, ["small", "default", "large", "extra-large"] as const) ? candidate.textSize : "default",
    spacing: isOneOf(candidate.spacing, ["compact", "default", "wide"] as const) ? candidate.spacing : "default",
    contrast: isOneOf(candidate.contrast, ["default", "high", "dark"] as const) ? candidate.contrast : "default",
    reduceMotion: typeof candidate.reduceMotion === "boolean" ? candidate.reduceMotion : false,
  };
}

export function readReadingPreferences(): { preferences: ReadingPreferences; persistenceAvailable: boolean } {
  const storage = safeStorage();
  if (!storage) return { preferences: DEFAULT_READING_PREFERENCES, persistenceAvailable: false };
  try {
    const raw = storage.getItem(READING_PREFERENCES_STORAGE_KEY);
    if (!raw) return { preferences: DEFAULT_READING_PREFERENCES, persistenceAvailable: true };
    const parsed: unknown = JSON.parse(raw);
    const preferences = normalizeReadingPreferences(parsed);
    if (JSON.stringify(parsed) !== JSON.stringify(preferences)) {
      storage.setItem(READING_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
    }
    return { preferences, persistenceAvailable: true };
  } catch {
    return { preferences: DEFAULT_READING_PREFERENCES, persistenceAvailable: false };
  }
}

export function saveReadingPreferences(preferences: ReadingPreferences): boolean {
  const storage = safeStorage();
  if (!storage) return false;
  try {
    storage.setItem(READING_PREFERENCES_STORAGE_KEY, JSON.stringify(normalizeReadingPreferences(preferences)));
    return true;
  } catch {
    return false;
  }
}

export function StudentReadingPreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(() => readReadingPreferences().preferences);
  const updatePreferences = (update: Partial<Omit<ReadingPreferences, "schemaVersion">>) => {
    setPreferences((current) => {
      const next = normalizeReadingPreferences({ ...current, ...update });
      saveReadingPreferences(next);
      return next;
    });
  };
  const resetReadingPreferences = () => {
    saveReadingPreferences(DEFAULT_READING_PREFERENCES);
    setPreferences(DEFAULT_READING_PREFERENCES);
  };

  return (
    <ReadingPreferencesContext.Provider value={{ preferences, updatePreferences, resetReadingPreferences }}>
      <div
        className="student-reading-boundary"
        data-student-reading-preferences
        data-reading-contrast={preferences.contrast}
        data-reading-font={preferences.font}
        data-reading-size={preferences.textSize}
        data-reading-spacing={preferences.spacing}
        data-reduce-motion={preferences.reduceMotion}
      >
        {children}
      </div>
    </ReadingPreferencesContext.Provider>
  );
}

export function useReadingPreferences(): ReadingPreferencesStore {
  const store = useContext(ReadingPreferencesContext);
  if (!store) throw new Error("Reading preferences are available only in student views.");
  return store;
}

function RadioGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="reading-settings-group">
      <legend>{label}</legend>
      <div className="reading-settings-options">
        {options.map((option) => (
          <label key={option.value}>
            <input checked={value === option.value} name={label} onChange={() => onChange(option.value)} type="radio" value={option.value} />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function ReadingSettingsPanel() {
  const { preferences, updatePreferences, resetReadingPreferences } = useReadingPreferences();
  return (
    <section aria-labelledby="reading-settings-title" className="reading-settings-panel">
      <div>
        <h2 id="reading-settings-title">Reading settings</h2>
        <p>Changes apply now and stay on this browser.</p>
      </div>
      <RadioGroup
        label="Letters"
        onChange={(font) => updatePreferences({ font })}
        options={[{ value: "default", label: "Standard letters" }, { value: "hyperlegible", label: "Easier-to-distinguish letters" }]}
        value={preferences.font}
      />
      <RadioGroup
        label="Text size"
        onChange={(textSize) => updatePreferences({ textSize })}
        options={[{ value: "small", label: "Small" }, { value: "default", label: "Default" }, { value: "large", label: "Large" }, { value: "extra-large", label: "Extra large" }]}
        value={preferences.textSize}
      />
      <RadioGroup
        label="Text spacing"
        onChange={(spacing) => updatePreferences({ spacing })}
        options={[{ value: "compact", label: "Compact" }, { value: "default", label: "Default" }, { value: "wide", label: "Wide" }]}
        value={preferences.spacing}
      />
      <RadioGroup
        label="Display"
        onChange={(contrast) => updatePreferences({ contrast })}
        options={[{ value: "default", label: "Default" }, { value: "high", label: "High contrast" }, { value: "dark", label: "Dark" }]}
        value={preferences.contrast}
      />
      <label className="reading-settings-toggle">
        <input checked={preferences.reduceMotion} onChange={(event) => updatePreferences({ reduceMotion: event.target.checked })} type="checkbox" />
        <span>Reduce motion</span>
      </label>
      <div className="reading-settings-reset">
        <p>Restores text, spacing, contrast and motion settings. Your lesson progress will not change.</p>
        <button className="button reading-settings-reset-action" onClick={resetReadingPreferences} type="button">Reset reading settings</button>
      </div>
    </section>
  );
}
