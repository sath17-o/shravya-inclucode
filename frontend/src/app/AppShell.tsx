import { type ReactNode, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button, Link } from "../components/primitives";

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const isTeacherRoute = location.pathname === "/teacher";
  useEffect(() => {
    document.documentElement.lang = "en";
    document.title = "Shravya";
  }, []);

  const selectRole = (nextRole: "teacher" | "student") => {
    navigate(nextRole === "teacher" ? "/teacher" : "/student");
  };

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={() => document.getElementById("main-content")?.focus()}
      >
        Skip to lesson content
      </a>
      <header className="site-header">
        <div className="brand-block">
          <p className="eyebrow"><span lang="ml">മലയാളം</span>-first classroom learning</p>
          <p className="brand-name">Shravya</p>
          <p className="tagline">Every class, made clear.</p>
        </div>
        <div className="header-controls">
          <div aria-label="Demo role switcher" className="segmented-control" role="group">
            <Button aria-pressed={isTeacherRoute} onClick={() => selectRole("teacher")} type="button">
              Teacher
            </Button>
            <Button aria-pressed={!isTeacherRoute} onClick={() => selectRole("student")} type="button">
              Student
            </Button>
          </div>
          <p className="role-note">Demo navigation only — no sign-in required.</p>
        </div>
      </header>
      <nav aria-label="Primary" className="primary-nav">
        <Link to="/teacher">Teacher review</Link>
        <Link end to="/student">Student lesson</Link>
        <Link to="/student/revisions">Revision</Link>
      </nav>
      <main id="main-content" tabIndex={-1}>{children}</main>
    </div>
  );
}
