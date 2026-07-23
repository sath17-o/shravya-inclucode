import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { FocusJourneyPage, StudentLessonPage, TeacherReviewPage } from "../features/pages";
import { StudentReadingPreferencesProvider } from "../features/readingPreferences";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route element={<TeacherReviewPage />} path="/teacher" />
        <Route element={<StudentReadingPreferencesProvider><FocusJourneyPage /></StudentReadingPreferencesProvider>} path="/student/focus" />
        <Route element={<StudentReadingPreferencesProvider><StudentLessonPage /></StudentReadingPreferencesProvider>} path="/student" />
        <Route element={<Navigate replace to="/student" />} path="*" />
      </Routes>
    </AppShell>
  );
}
