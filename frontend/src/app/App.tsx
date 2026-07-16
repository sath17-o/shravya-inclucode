import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { useAppContext } from "./AppContext";
import {
  LearningHomePage,
  LearningPreferencesPage,
  LessonOverviewPage,
  TeacherSetupPage,
  TrustPage,
} from "../features/pages";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route element={<LearningHomePage />} path="/learning-home" />
        <Route element={<LessonOverviewPage />} path="/lesson-overview" />
        <Route element={<TeacherRoute />} path="/teacher-setup" />
        <Route element={<TrustPage />} path="/trust" />
        <Route element={<LearningPreferencesPage />} path="/learning-preferences" />
        <Route element={<Navigate replace to="/learning-home" />} path="*" />
      </Routes>
    </AppShell>
  );
}

function TeacherRoute() {
  const { role } = useAppContext();
  return role === "teacher" ? <TeacherSetupPage /> : <Navigate replace to="/learning-home" />;
}
