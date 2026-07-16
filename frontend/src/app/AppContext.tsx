import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { type InterfaceLanguage } from "../i18n/strings";

export type LocalRole = "teacher" | "student";

type AppContextValue = {
  language: InterfaceLanguage;
  role: LocalRole;
  setLanguage: (language: InterfaceLanguage) => void;
  setRole: (role: LocalRole) => void;
};

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<InterfaceLanguage>("bilingual");
  const [role, setRole] = useState<LocalRole>("student");
  const value = useMemo(
    () => ({ language, role, setLanguage, setRole }),
    [language, role],
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
