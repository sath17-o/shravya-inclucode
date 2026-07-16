import { type ReactNode } from "react";

import { type InterfaceLanguage, type LocalizedText as LocalizedTextValue, localizedString, text, type TranslationKey } from "./strings";

function MalayalamContent({ textKey }: { textKey: TranslationKey }) {
  const value: LocalizedTextValue = text[textKey];
  if (!value.malayalamFragments) {
    return <span lang="ml">{value.malayalam}</span>;
  }
  return (
    <span lang="ml">
      {value.malayalamFragments.map((fragment, index) => (
        <span key={`${fragment.language}-${index}`} lang={fragment.language}>{fragment.value}</span>
      ))}
    </span>
  );
}

export function LocalizedText({
  textKey,
  language,
  className,
}: {
  textKey: TranslationKey;
  language: InterfaceLanguage;
  className?: string;
}): ReactNode {
  const content = (() => {
    if (language === "english") {
      return <span lang="en">{text[textKey].english}</span>;
    }
    if (language === "malayalam") {
      return <MalayalamContent textKey={textKey} />;
    }
    return (
      <>
        <MalayalamContent textKey={textKey} />
        <span aria-hidden="true" className="language-separator"> / </span>
        <span className="sr-only" lang="en"> / </span>
        <span lang="en">{text[textKey].english}</span>
      </>
    );
  })();

  return <span className={className} data-localized-key={textKey}>{content}</span>;
}

export function accessibleLocalizedText(textKey: TranslationKey, language: InterfaceLanguage): string {
  return localizedString(textKey, language);
}
