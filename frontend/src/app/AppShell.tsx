import { type ReactNode, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAppContext } from "./AppContext";
import { Button, Link, RadioGroup } from "../components/primitives";
import { LocalizedText, accessibleLocalizedText } from "../i18n/LocalizedText";
import { localizedString, type InterfaceLanguage, type TranslationKey } from "../i18n/strings";

const languageOptions: InterfaceLanguage[] = ["english", "malayalam", "bilingual"];

export function AppShell({ children }: { children: ReactNode }) {
  const { language, role, setLanguage, setRole } = useAppContext();
  const location = useLocation();
  const navigate = useNavigate();
  const L = (key: TranslationKey) => <LocalizedText language={language} textKey={key} />;

  useEffect(() => {
    document.documentElement.lang = language === "english" ? "en" : "ml";
    document.title = localizedString("appName", language);
  }, [language]);

  const selectRole = (nextRole: "teacher" | "student") => {
    setRole(nextRole);
    if (nextRole === "teacher") {
      navigate("/teacher-setup");
    } else if (location.pathname === "/teacher-setup") {
      navigate("/learning-home");
    }
  };

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={() => document.getElementById("main-content")?.focus()}
      >
        {L("skipToContent")}
      </a>
      <header className="site-header">
        <div className="brand-block">
          <p className="eyebrow">{L("appDescription")}</p>
          <p className="brand-name">{L("appName")}</p>
        </div>
        <div className="header-controls">
          <div aria-label={accessibleLocalizedText("roleLabel", language)} className="segmented-control" role="group">
            <Button aria-pressed={role === "teacher"} onClick={() => selectRole("teacher")} type="button">
              {L("teacherSetup")}
            </Button>
            <Button aria-pressed={role === "student"} onClick={() => selectRole("student")} type="button">
              {L("studentLearning")}
            </Button>
          </div>
          <RadioGroup
            label={L("languageLabel")}
            name="interface-language"
            onChange={(value) => setLanguage(value as InterfaceLanguage)}
            options={languageOptions.map((option) => ({ value: option, label: L(option) }))}
            value={language}
          />
        </div>
      </header>
      <nav aria-label="Primary" className="primary-nav">
        {role === "teacher" ? <Link to="/teacher-setup">{L("teacherSetup")}</Link> : null}
        <Link to="/learning-home">{L("learningHome")}</Link>
        <Link to="/lesson-overview">{L("lessonOverview")}</Link>
        <Link to="/trust">{L("trustInformation")}</Link>
        <Link to="/learning-preferences">{L("learningPreferences")}</Link>
      </nav>
      <main id="main-content" tabIndex={-1}>{children}</main>
    </div>
  );
}
