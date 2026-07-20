import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { FocusJourneyPage, StudentLessonPage, TeacherReviewPage } from "../features/pages";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route element={<TeacherReviewPage />} path="/teacher" />
        <Route element={<FocusJourneyPage />} path="/student/focus" />
        <Route element={<StudentLessonPage />} path="/student" />
        <Route element={<Navigate replace to="/student" />} path="*" />
      </Routes>
    </AppShell>
  );
}
