export type InterfaceLanguage = "english" | "malayalam" | "bilingual";
export type Locale = Exclude<InterfaceLanguage, "bilingual">;
export type LocalizedFragment = { language: "en" | "ml"; value: string };
export type LocalizedText = {
  english: string;
  malayalam: string;
  malayalamFragments?: LocalizedFragment[];
};

export const text = {
  appName: { english: "Shravya", malayalam: "ശ്രവ്യ" },
  appDescription: { english: "Malayalam-first inclusive learning", malayalam: "മലയാളം-ആദ്യം ഉൾക്കൊള്ളുന്ന പഠനം" },
  skipToContent: { english: "Skip to main content", malayalam: "പ്രധാന ഉള്ളടക്കത്തിലേക്ക് പോകുക" },
  roleLabel: { english: "Current space", malayalam: "നിലവിലെ സ്ഥലം" },
  teacherSetup: { english: "Teacher Setup", malayalam: "അധ്യാപക സജ്ജീകരണം" },
  studentLearning: { english: "Student Learning", malayalam: "വിദ്യാർത്ഥി പഠനം" },
  languageLabel: { english: "Interface language", malayalam: "ഇന്റർഫേസ് ഭാഷ" },
  english: { english: "English", malayalam: "ഇംഗ്ലീഷ്" },
  malayalam: { english: "Malayalam", malayalam: "മലയാളം" },
  bilingual: { english: "Bilingual", malayalam: "ദ്വിഭാഷ" },
  learningHome: { english: "Learning Home", malayalam: "പഠന ഹോം" },
  lessonOverview: { english: "Lesson Overview", malayalam: "പാഠ അവലോകനം" },
  trustInformation: { english: "Trust and Source Information", malayalam: "വിശ്വാസവും ഉറവിട വിവരങ്ങളും" },
  learningPreferences: { english: "Learning Preferences", malayalam: "പഠന മുൻഗണനകൾ" },
  phaseOneNotice: {
    english: "Phase 1 foundation: learning activities will be added in later approved phases.",
    malayalam: "ഘട്ടം 1 അടിസ്ഥാനം: പഠന പ്രവർത്തനങ്ങൾ അംഗീകരിച്ച അടുത്ത ഘട്ടങ്ങളിൽ ചേർക്കും.",
  },
  foundationState: {
    english: "Foundation ready for the next approved module.",
    malayalam: "അടുത്ത അംഗീകരിച്ച ഘടകത്തിനായി അടിസ്ഥാനം തയ്യാറാണ്.",
  },
  classSevenScience: { english: "Class 7 Science", malayalam: "ക്ലാസ് 7 ശാസ്ത്രം" },
  photosynthesis: { english: "Photosynthesis in Plants", malayalam: "സസ്യങ്ങളിലെ പ്രകാശസംശ്ലേഷണം" },
  lessonSummary: {
    english: "A Malayalam-English science lesson fixture for the Phase 1 application shell.",
    malayalam: "ഘട്ടം 1 ആപ്ലിക്കേഷൻ ഷെല്ലിനുള്ള മലയാളം-ഇംഗ്ലീഷ് ശാസ്ത്ര പാഠ മാതൃക.",
  },
  approved: { english: "Approved", malayalam: "അംഗീകരിച്ചത്" },
  needsReview: { english: "Needs review", malayalam: "പരിശോധന ആവശ്യമാണ്" },
  outdated: { english: "Outdated", malayalam: "കാലഹരണപ്പെട്ടത്" },
  source: { english: "Source", malayalam: "ഉറവിടം" },
  demo: { english: "Demo", malayalam: "ഡെമോ" },
  live: { english: "Live", malayalam: "തത്സമയം" },
  cached: { english: "Cached", malayalam: "സംരക്ഷിച്ച പകർപ്പ്" },
  whyTrust: { english: "Why can I trust this?", malayalam: "എനിക്ക് ഇത് എങ്ങനെ വിശ്വസിക്കാം?" },
  trustDetail: {
    english: "This Phase 1 screen uses a deterministic demo fixture. It is not live-generated content.",
    malayalam: "ഈ ഘട്ടം 1 സ്ക്രീൻ നിർണായക ഡെമോ മാതൃകയാണ് ഉപയോഗിക്കുന്നത്. ഇത് തത്സമയം സൃഷ്ടിച്ച ഉള്ളടക്കമല്ല.",
  },
  preferencePreview: {
    english: "Malayalam and English scientific terms should wrap clearly at larger text sizes and line spacing.",
    malayalam: "വലുതായ അക്ഷര വലിപ്പത്തിലും വരിയിടവേളയിലും മലയാളവും ഇംഗ്ലീഷ് ശാസ്ത്രീയ പദങ്ങളും വ്യക്തമായി വരിമാറ്റി കാണണം.",
  },
  chooseDensity: { english: "Choose page density", malayalam: "പേജ് സാന്ദ്രത തിരഞ്ഞെടുക്കുക" },
  comfortable: { english: "Comfortable", malayalam: "സുഖകരം" },
  compact: { english: "Compact", malayalam: "ഒതുക്കമുള്ളത്" },
  longMalayalamExample: {
    english: "Photosynthesis uses Sunlight, Water, Carbon dioxide and Chlorophyll to make Glucose and release Oxygen.",
    malayalam: "പ്രകാശസംശ്ലേഷണത്തിൽ Sunlight, Water, Carbon dioxide, Chlorophyll എന്നിവ ഉപയോഗിച്ച് Glucose ഉണ്ടാക്കി Oxygen പുറത്തുവിടുന്നു.",
    malayalamFragments: [
      { language: "ml", value: "പ്രകാശസംശ്ലേഷണത്തിൽ " },
      { language: "en", value: "Sunlight, Water, Carbon dioxide, Chlorophyll" },
      { language: "ml", value: " എന്നിവ ഉപയോഗിച്ച് " },
      { language: "en", value: "Glucose" },
      { language: "ml", value: " ഉണ്ടാക്കി " },
      { language: "en", value: "Oxygen" },
      { language: "ml", value: " പുറത്തുവിടുന്നു." },
    ],
  },
} satisfies Record<string, LocalizedText>;

export type TranslationKey = keyof typeof text;

export function localizedString(key: TranslationKey, language: InterfaceLanguage): string {
  const value = text[key];
  if (language === "bilingual") {
    return `${value.malayalam}/${value.english}`;
  }
  return value[language];
}
