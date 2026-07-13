import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnalysisProgress from "./AnalysisProgress";

/** Force the reduced-motion branch so the displayed value snaps to `progress`
 * on the next animation frame instead of easing toward it over many frames —
 * that keeps these assertions deterministic without faking rAF timing. */
function stubReducedMotion() {
  window.matchMedia = vi.fn((query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("AnalysisProgress", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all 5 real pipeline stages", () => {
    render(<AnalysisProgress handle="@octocat" progress={0} onCancel={vi.fn()} />);

    expect(screen.getByText("Parsing Resume")).toBeInTheDocument();
    expect(screen.getByText("Analyzing GitHub Profile")).toBeInTheDocument();
    expect(screen.getByText("Extracting Skills & Experience")).toBeInTheDocument();
    expect(screen.getByText("Evaluating Strengths")).toBeInTheDocument();
    expect(screen.getByText("Generating Report")).toBeInTheDocument();
  });

  it("marks earlier stages done and shows a live percent on the active stage", async () => {
    stubReducedMotion();
    // 0.5 of 5 stages -> stage index 2 ("Extracting Skills & Experience") active,
    // stages 0 and 1 done, stages 3 and 4 pending.
    render(<AnalysisProgress handle="@octocat" progress={0.5} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Parsing Resume").closest(".pstep")).toHaveClass("pstep-done");
    });
    expect(screen.getByText("Extracting Skills & Experience").closest(".pstep")).toHaveClass(
      "pstep-now",
    );
    const pending = screen.getByText("Generating Report").closest(".pstep");
    expect(pending).toHaveClass("pstep-pending");
    expect(pending).toHaveTextContent("Pending");
  });

  it("marks every stage done (no stuck spinner) once progress reaches 1", async () => {
    stubReducedMotion();
    render(<AnalysisProgress handle="@octocat" progress={1} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Generating Report").closest(".pstep")).toHaveClass("pstep-done");
    });
    expect(screen.queryByText("Generating Report")?.closest(".pstep")).not.toHaveClass(
      "pstep-now",
    );
  });

  it("calls onCancel when Cancel Analysis is clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<AnalysisProgress handle="@octocat" progress={0.2} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: /Cancel Analysis/ }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
