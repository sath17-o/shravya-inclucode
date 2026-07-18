import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { type InterfaceLanguage } from "../i18n/strings";

type AppContextValue = {
  language: InterfaceLanguage;
  curriculumRevision: number;
  setLanguage: (language: InterfaceLanguage) => void;
  refreshCurriculum: () => void;
};

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<InterfaceLanguage>("bilingual");
  const [curriculumRevision, setCurriculumRevision] = useState(0);
  const value = useMemo(
    () => ({
      language,
      curriculumRevision,
      setLanguage,
      refreshCurriculum: () => setCurriculumRevision((revision) => revision + 1),
    }),
    [curriculumRevision, language],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useAppContext must be used within AppProvider");
  }
  return context;
}
