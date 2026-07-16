import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../app/App";
import { AppProvider } from "../app/AppContext";
import { localizedString, text } from "../i18n/strings";

function renderApp(initialEntry = "/learning-home") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AppProvider>
        <App />
      </AppProvider>
    </MemoryRouter>,
  );
}

describe("Phase 1 application shell", () => {
  it("provides a keyboard path from the skip link to main content", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.tab();
    const skipLink = screen.getByRole("link", { name: /skip to main content/i });
    expect(skipLink).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("switches to Malayalam labels, language and document title", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("radio", { name: localizedString("malayalam", "bilingual") }));

    expect(screen.getByRole("heading", { name: text.learningHome.malayalam })).toBeInTheDocument();
    await waitFor(() => expect(document.documentElement).toHaveAttribute("lang", "ml"));
    expect(document.title).toBe(text.appName.malayalam);
  });

  it("uses separate Malayalam and English spans for bilingual labels", () => {
    renderApp();

    const heading = screen.getByRole("heading", { name: localizedString("learningHome", "bilingual") });
    expect(heading.querySelector('span[lang="ml"]')).toHaveTextContent(text.learningHome.malayalam);
    expect(heading.querySelector('span[lang="en"]:not(.sr-only)')).toHaveTextContent(text.learningHome.english);
  });

  it("enforces the teacher route boundary and role-switch navigation", async () => {
    const user = userEvent.setup();
    renderApp("/teacher-setup");

    expect(screen.getByRole("heading", { name: localizedString("learningHome", "bilingual") })).toBeInTheDocument();
    const teacher = screen.getByRole("button", { name: localizedString("teacherSetup", "bilingual") });
    await user.click(teacher);
    expect(teacher).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: localizedString("teacherSetup", "bilingual") })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: localizedString("studentLearning", "bilingual") }));
    expect(screen.getByRole("heading", { name: localizedString("learningHome", "bilingual") })).toBeInTheDocument();
  });

  it("uses static notices rather than a fake progress state", async () => {
    const user = userEvent.setup();
    renderApp();

    expect(document.querySelector(".notice")).not.toHaveAttribute("role");
    await user.click(screen.getByRole("link", { name: localizedString("lessonOverview", "bilingual") }));
    expect(document.querySelector(".notice")).not.toHaveAttribute("role");
  });

  it("expands the trust panel by keyboard", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: localizedString("trustInformation", "bilingual") }));
    const panelButton = screen.getByRole("button", { name: localizedString("whyTrust", "bilingual") });
    panelButton.focus();
    await user.keyboard("{Enter}");

    expect(panelButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(text.trustDetail.english)).toBeInTheDocument();
  });

  it("does not render icon-only buttons or actionable links", () => {
    const { container } = renderApp();

    container.querySelectorAll("button, a[href]").forEach((element) => {
      expect(element.textContent?.trim().length).toBeGreaterThan(0);
    });
  });
});
