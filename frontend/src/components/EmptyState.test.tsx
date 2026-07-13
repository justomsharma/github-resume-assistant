import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("renders the icon, title, and description passed as props", () => {
    render(<EmptyState icon="◇" title="No suggestions yet" description="Try adding more claims." />);

    expect(screen.getByText("◇")).toBeInTheDocument();
    expect(screen.getByText("No suggestions yet")).toBeInTheDocument();
    expect(screen.getByText("Try adding more claims.")).toBeInTheDocument();
  });
});
