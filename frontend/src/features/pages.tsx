import { useState } from "react";

import { Card, ExpandableTrustPanel, Notice, RadioGroup, StatusBadge } from "../components/primitives";
import { useAppContext } from "../app/AppContext";
import { LocalizedText, accessibleLocalizedText } from "../i18n/LocalizedText";
import { type TranslationKey } from "../i18n/strings";

function useLocalized() {
  const { language } = useAppContext();
  return {
    L: (key: TranslationKey) => <LocalizedText language={language} textKey={key} />,
    accessible: (key: TranslationKey) => accessibleLocalizedText(key, language),
  };
}

function TrustStatus() {
  const { L, accessible } = useLocalized();
  return (
    <div className="status-row" aria-label={accessible("trustInformation")}>
      <StatusBadge kind="approved">{L("approved")}</StatusBadge>
      <StatusBadge kind="source">{L("source")}: {L("demo")}</StatusBadge>
    </div>
  );
}

export function TeacherSetupPage() {
  const { L } = useLocalized();
  return (
    <article className="page-grid">
      <div>
        <p className="eyebrow">{L("classSevenScience")}</p>
        <h1>{L("teacherSetup")}</h1>
        <p className="wrap-anywhere">{L("phaseOneNotice")}</p>
      </div>
      <Card>
        <h2>{L("photosynthesis")}</h2>
        <p className="wrap-anywhere">{L("lessonSummary")}</p>
        <TrustStatus />
      </Card>
    </article>
  );
}

export function LearningHomePage() {
  const { L } = useLocalized();
  return (
    <article className="page-grid">
      <div>
        <p className="eyebrow">{L("classSevenScience")}</p>
        <h1>{L("learningHome")}</h1>
        <p className="wrap-anywhere">{L("phaseOneNotice")}</p>
      </div>
      <Card>
        <h2>{L("photosynthesis")}</h2>
        <p className="wrap-anywhere">{L("longMalayalamExample")}</p>
        <Notice>{L("foundationState")}</Notice>
      </Card>
    </article>
  );
}

export function LessonOverviewPage() {
  const { L } = useLocalized();
  return (
    <article className="page-grid">
      <div>
        <p className="eyebrow">{L("classSevenScience")}</p>
        <h1>{L("lessonOverview")}</h1>
      </div>
      <Card>
        <h2>{L("photosynthesis")}</h2>
        <TrustStatus />
        <p className="wrap-anywhere">{L("lessonSummary")}</p>
        <Notice>{L("phaseOneNotice")}</Notice>
      </Card>
    </article>
  );
}

export function TrustPage() {
  const { L } = useLocalized();
  return (
    <article className="page-grid">
      <div>
        <h1>{L("trustInformation")}</h1>
        <p className="wrap-anywhere">{L("phaseOneNotice")}</p>
      </div>
      <Card>
        <TrustStatus />
        <ExpandableTrustPanel title={L("whyTrust")}>
          <p className="wrap-anywhere">{L("trustDetail")}</p>
        </ExpandableTrustPanel>
      </Card>
    </article>
  );
}

export function LearningPreferencesPage() {
  const { L } = useLocalized();
  const [density, setDensity] = useState("comfortable");
  return (
    <article className="page-grid">
      <div>
        <h1>{L("learningPreferences")}</h1>
        <p className="wrap-anywhere">{L("preferencePreview")}</p>
      </div>
      <Card>
        <RadioGroup
          label={L("chooseDensity")}
          name="density"
          onChange={setDensity}
          options={[
            { value: "comfortable", label: L("comfortable") },
            { value: "compact", label: L("compact") },
          ]}
          value={density}
        />
        <p className="wrap-anywhere" data-testid="long-label-preview">{L("longMalayalamExample")}</p>
      </Card>
    </article>
  );
}
