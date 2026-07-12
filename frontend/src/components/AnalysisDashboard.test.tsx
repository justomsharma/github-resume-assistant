import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisResponse } from "@/lib/types";
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
});
