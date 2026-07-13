import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import type { AnalysisResponse, GapReport } from "@/lib/types";
import AnalysisDashboard from "./AnalysisDashboard";

const normalResult: AnalysisResponse = {
  report: {
    profile_login: "octocat",
    backed: [
      {
        claim: { text: "Built a distributed cache in Go", skills: ["go"], category: "project" },
        verdict: "backed",
        matching_repos: ["go-cache"],
        cited_files: ["go-cache/src/cache.go"],
        rationale: "LRU cache in cache.go.",
      },
    ],
    not_shown: [
      {
        claim: { text: "Proficient in React", skills: ["react"], category: "skill" },
        verdict: "not_shown",
        matching_repos: [],
        cited_files: [],
        rationale: "No public repo shows React.",
      },
    ],
    not_verifiable: [],
    github_is_empty: false,
  },
  plan: {
    profile_login: "octocat",
    suggestions: [
      {
        title: "react-dashboard",
        what_to_build: "A live dashboard proving React skills.",
        proves_claim: "Proficient in React",
        skills: ["react"],
        size: "a weekend",
        skip: "auth",
      },
    ],
    github_is_empty: false,
  },
};

const emptyResult: AnalysisResponse = {
  report: {
    profile_login: "octocat",
    backed: [],
    not_shown: [],
    not_verifiable: [],
    github_is_empty: true,
  },
  plan: {
    profile_login: "octocat",
    suggestions: [],
    github_is_empty: true,
  },
};

describe("AnalysisDashboard", () => {
  it("renders stat cards, tabs, and the recommendation banner for a normal report", () => {
    render(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);

    expect(screen.getByText("Analysis Complete! 🎉")).toBeInTheDocument();
    expect(screen.getByText("Overall Score")).toBeInTheDocument();
    expect(screen.getByText("Skills Match")).toBeInTheDocument();
    expect(screen.getByText("Experience Level")).toBeInTheDocument();
    expect(screen.getByText("Top Strength")).toBeInTheDocument();

    for (const tab of ["Overview", "Skills", "Experience", "Projects", "Recommendations"]) {
      expect(screen.getByRole("tab", { name: new RegExp(tab) })).toBeInTheDocument();
    }

    expect(screen.getByText("✦ AI Recommendation")).toBeInTheDocument();
    expect(screen.getByText("A live dashboard proving React skills.")).toBeInTheDocument();
  });

  it("does not crash on the empty-GitHub case and shows honest empty-state copy", () => {
    render(<AnalysisDashboard result={emptyResult} onBackToHome={vi.fn()} />);

    expect(screen.getByText("Analysis Complete! 🎉")).toBeInTheDocument();
    expect(screen.getByText(/doesn.t back any resume claims yet/i)).toBeInTheDocument();
    expect(screen.getByText("Not enough evidence yet")).toBeInTheDocument();
    // No suggestions -> no recommendation banner.
    expect(screen.queryByText("✦ AI Recommendation")).not.toBeInTheDocument();
  });

  it("shows an EmptyState in the Skills tab instead of a blank panel when there are no claims", async () => {
    const user = userEvent.setup();
    render(<AnalysisDashboard result={emptyResult} onBackToHome={vi.fn()} />);

    await user.click(screen.getByRole("tab", { name: /Skills/ }));
    expect(screen.getByText("No claims to show yet")).toBeInTheDocument();
    expect(screen.queryByText("Backed by GitHub")).not.toBeInTheDocument();
  });

  it("switches tab content on click", async () => {
    const user = userEvent.setup();
    render(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);

    expect(screen.getByText("Profile Summary")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Skills/ }));
    expect(screen.getByText(/Backed by GitHub/)).toBeInTheDocument();
    expect(screen.getByText("Built a distributed cache in Go")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Projects/ }));
    expect(screen.getByText("react-dashboard")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Recommendations/ }));
    const suggestion = screen.getByText("react-dashboard").closest(".dsuggestion");
    expect(suggestion).not.toBeNull();
    expect(within(suggestion as HTMLElement).getByText(/Proves:/)).toBeInTheDocument();
  });

  it("calls onBackToHome when Back to Home is clicked", async () => {
    const user = userEvent.setup();
    const onBackToHome = vi.fn();
    render(<AnalysisDashboard result={normalResult} onBackToHome={onBackToHome} />);

    await user.click(screen.getByText("← Back to Home"));
    expect(onBackToHome).toHaveBeenCalledOnce();
  });

  it("downloads a Markdown report when Download Report is clicked", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Download Report/ }));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");

    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("copies a share summary to the clipboard and shows 'Copied!' when Share Report is clicked", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });

    render(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Share Report/ }));

    expect(writeText).toHaveBeenCalledOnce();
    expect(writeText.mock.calls[0][0]).toContain("octocat");
    expect(await screen.findByText("✓ Copied!")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  describe("with plan still generating (report arrived first)", () => {
    const pendingReport: GapReport = normalResult.report;

    it("shows a generating state in Projects/Recommendations and disables report actions", async () => {
      const user = userEvent.setup();
      render(
        <AnalysisDashboard result={{ report: pendingReport, plan: null }} onBackToHome={vi.fn()} />,
      );

      // Overview renders fine from the report alone, with no recommendation banner yet.
      expect(screen.getByText("Analysis Complete! 🎉")).toBeInTheDocument();
      expect(screen.queryByText("✦ AI Recommendation")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Download Report/ })).toBeDisabled();
      expect(screen.getByRole("button", { name: /Share Report/ })).toBeDisabled();

      await user.click(screen.getByRole("tab", { name: /Projects/ }));
      expect(screen.getByText("Generating your build plan…")).toBeInTheDocument();

      await user.click(screen.getByRole("tab", { name: /Recommendations/ }));
      expect(screen.getByText("Generating your build plan…")).toBeInTheDocument();
    });

    it("fills in the suggestions once the plan arrives (rerender with a populated plan)", async () => {
      const user = userEvent.setup();
      const { rerender } = render(
        <AnalysisDashboard result={{ report: pendingReport, plan: null }} onBackToHome={vi.fn()} />,
      );

      rerender(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);

      expect(screen.getByRole("button", { name: /Download Report/ })).toBeEnabled();
      await user.click(screen.getByRole("tab", { name: /Projects/ }));
      expect(screen.getByText("react-dashboard")).toBeInTheDocument();
      expect(screen.queryByText("Generating your build plan…")).not.toBeInTheDocument();
    });
  });

  it("has no axe violations for a normal report", async () => {
    const { container } = render(<AnalysisDashboard result={normalResult} onBackToHome={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no axe violations for the empty-GitHub case", async () => {
    const { container } = render(<AnalysisDashboard result={emptyResult} onBackToHome={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
