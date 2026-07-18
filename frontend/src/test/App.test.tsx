import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppProvider } from "../app/AppContext";
import { createCurriculumFetch } from "./curriculumFixtures";

function renderApp(initialEntry: "/teacher" | "/student", fetchMock = createCurriculumFetch()) {
  vi.stubGlobal("fetch", fetchMock);
  return render(<MemoryRouter initialEntries={[initialEntry]}><AppProvider><App /></AppProvider></MemoryRouter>);
}

afterEach(() => vi.unstubAllGlobals());

describe("Phase 3A curriculum experience", () => {
  it("derives the Student controls from the student route", async () => {
    renderApp("/student");
    await screen.findByRole("heading", { name: "Photosynthesis in Plants" });
    const roleSwitcher = screen.getByRole("group", { name: "Demo role switcher" });
    expect(within(roleSwitcher).getByRole("button", { name: "Student" })).toHaveAttribute("aria-pressed", "true");
    expect(within(roleSwitcher).getByRole("button", { name: "Teacher" })).toHaveAttribute("aria-pressed", "false");
    expect(within(roleSwitcher).getAllByRole("button", { pressed: true })).toHaveLength(1);
    const navigation = screen.getByRole("navigation", { name: "Primary" });
    expect(within(navigation).getByRole("link", { name: "Student lesson" })).toHaveClass("active");
    expect(within(navigation).getByRole("link", { name: "Teacher review" })).not.toHaveClass("active");
  });

  it("derives the Teacher controls from the teacher route", async () => {
    renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    const roleSwitcher = screen.getByRole("group", { name: "Demo role switcher" });
    expect(within(roleSwitcher).getByRole("button", { name: "Teacher" })).toHaveAttribute("aria-pressed", "true");
    expect(within(roleSwitcher).getByRole("button", { name: "Student" })).toHaveAttribute("aria-pressed", "false");
    expect(within(roleSwitcher).getAllByRole("button", { pressed: true })).toHaveLength(1);
    const navigation = screen.getByRole("navigation", { name: "Primary" });
    expect(within(navigation).getByRole("link", { name: "Teacher review" })).toHaveClass("active");
    expect(within(navigation).getByRole("link", { name: "Student lesson" })).not.toHaveClass("active");
  });

  it("keeps the skip link keyboard reachable", async () => {
    const user = userEvent.setup();
    renderApp("/student");
    const skipLink = screen.getByRole("link", { name: "Skip to lesson content" });
    expect(skipLink).toHaveClass("skip-link");
    await user.tab();
    expect(skipLink).toHaveFocus();
  });

  it("renders the teacher baseline with approved v1, hidden Draft v2, and review readiness", async () => {
    renderApp("/teacher");
    expect(await screen.findByRole("heading", { name: "Teacher Review Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Version 1/ })).toHaveTextContent("Approved");
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Draft");
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Hidden from students until submitted and approved");
    expect(await screen.findByText("Ready for teacher review")).toBeInTheDocument();
  });

  it("keeps Needs Review hidden without calling it an earlier approved version", async () => {
    renderApp("/teacher", createCurriculumFetch({ initialV2Status: "NEEDS_REVIEW" }));
    const versionTwo = await screen.findByRole("button", { name: /Version 2/ });
    expect(versionTwo).toHaveTextContent("Needs review");
    expect(versionTwo).toHaveTextContent("Awaiting teacher approval · hidden from students");
    expect(versionTwo).not.toHaveTextContent("Earlier approved version");
    expect(versionTwo).not.toHaveTextContent("Currently visible to students");
  });

  it("never renders internal copied-from review metadata in the timeline", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    expect(await screen.findByRole("heading", { name: "Review history" })).toBeInTheDocument();
    expect(screen.queryByText(/copied_from:/)).not.toBeInTheDocument();
    expect(screen.queryByText("f069db92-d848-5546-b3ad-3b10ee301600")).not.toBeInTheDocument();
  });

  it("submits Draft v2 and then reports the returned stale-artifact count on approval", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await screen.findByRole("button", { name: "Submit for review" });
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    expect(await screen.findByText("Context submitted for teacher review.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Approve trusted version" }));
    expect(await screen.findByText("New trusted version approved. 1 older learning artifact marked stale.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Version 2/ })).toHaveTextContent("Currently visible to students");
  });

  it("offers a guarded retry action when submitting a context fails recoverably", async () => {
    const user = userEvent.setup();
    const fetchMock = createCurriculumFetch({ failSubmitOnce: true });
    renderApp("/teacher", fetchMock);
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    const retryButton = await screen.findByRole("button", { name: "Try submitting again" });
    expect(retryButton).toBeEnabled();
    await user.click(retryButton);
    expect(await screen.findByText("Context submitted for teacher review.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").length).toBe(2);
  });

  it("shows the approved-only student baseline and exact Malayalam support", async () => {
    renderApp("/student");
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
    expect(screen.getByText("Trusted version 1")).toBeInTheDocument();
    expect(screen.getAllByText("പ്രകാശസംശ്ലേഷണം").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ക്ലോറോഫിൽ").length).toBeGreaterThan(0);
    expect(screen.getByText("Heard as:")).toHaveTextContent("chlorophil");
    expect(screen.queryByText("Improved teacher explanation")).not.toBeInTheDocument();
    expect(screen.getByText("Follow the lesson from what plants need to the oxygen they release.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Question Explorer" })).toBeInTheDocument();
    expect(screen.queryByText(/Visual Story later|Question Explorer preview|Phase 3/)).not.toBeInTheDocument();
  });



  it("keeps Question Explorer as a semantic list with separated source labels", async () => {
    renderApp("/student");
    const heading = await screen.findByRole("heading", { name: "Question Explorer" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    const list = within(section!).getByRole("list");
    const [question] = within(list).getAllByRole("listitem");
    const sourceLabel = within(question).getByText("Teacher question");
    expect(sourceLabel).toHaveClass("question-source-label");
    expect(sourceLabel.nextElementSibling).toHaveClass("question-copy");
    expect(within(question).getByText("What inputs do plants need for photosynthesis?")).toBeInTheDocument();
  });

  it("fetches fresh student content after the teacher approves v2", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    await user.click(await screen.findByRole("button", { name: /Version 2/ }));
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    await user.click(await screen.findByRole("button", { name: "Approve trusted version" }));
    await user.click(screen.getByRole("button", { name: "Student" }));
    expect(await screen.findByText("Trusted version 2")).toBeInTheDocument();
    expect(screen.getByText("Improved teacher explanation")).toBeInTheDocument();
    expect(screen.getByText("Improved classroom question")).toBeInTheDocument();
  });

  it("renders the explicit student not-ready state", async () => {
    renderApp("/student", createCurriculumFetch({ notReady: true }));
    expect(await screen.findByRole("heading", { name: "This lesson is being prepared by your teacher." })).toBeInTheDocument();
    expect(screen.getByText("Only reviewed classroom content will appear here.")).toBeInTheDocument();
  });

  it("uses safe error copy without API internals", async () => {
    renderApp("/student", createCurriculumFetch({ fail: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The classroom information is unavailable right now.");
    expect(screen.queryByText(/SELECT \* FROM private/)).not.toBeInTheDocument();
    expect(screen.queryByText(/C:\\secrets/)).not.toBeInTheDocument();
  });

  it("supports keyboard selection of a version and keyboard role navigation", async () => {
    const user = userEvent.setup();
    renderApp("/teacher");
    const versionTwo = await screen.findByRole("button", { name: /Version 2/ });
    versionTwo.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("button", { name: /Version 2/ })).toHaveAttribute("aria-pressed", "true"));
    const student = screen.getByRole("button", { name: /^Student$/ });
    student.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
  });

  it("keeps one main heading and named landmarks on both primary routes", async () => {
    const { rerender } = renderApp("/teacher");
    await screen.findByRole("heading", { name: "Teacher Review Workspace" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
    rerender(<MemoryRouter initialEntries={["/student"]}><AppProvider><App /></AppProvider></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Photosynthesis in Plants" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
