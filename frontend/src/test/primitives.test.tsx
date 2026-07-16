import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorAlert, Notice, StatusMessage } from "../components/primitives";

describe("message semantics", () => {
  it("keeps a static notice out of live regions", () => {
    render(<Notice>Foundation information</Notice>);
    expect(screen.getByText("Foundation information")).not.toHaveAttribute("role");
  });

  it("marks dynamic status and blocking errors explicitly", () => {
    render(
      <>
        <StatusMessage>Saved</StatusMessage>
        <ErrorAlert>Cannot continue</ErrorAlert>
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot continue");
  });
});
