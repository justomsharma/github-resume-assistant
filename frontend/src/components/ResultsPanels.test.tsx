import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GapReport, ProjectPlan } from "@/lib/types";
import ResultsPanels from "./ResultsPanels";

const report: GapReport = {
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
};

const plan: ProjectPlan = {
  profile_login: "octocat",
  suggestions: [
    {
      title: "react-dashboard",
      what_to_build: "A live dashboard.",
      proves_claim: "Proficient in React",
      skills: ["react"],
      size: "a weekend",
      skip: "auth",
    },
  ],
  github_is_empty: false,
};

describe("ResultsPanels", () => {
  it("renders the Score, Diagnosis, and Prescription panels", () => {
    render(<ResultsPanels report={report} plan={plan} />);

    expect(screen.getByText("Score")).toBeInTheDocument();
    expect(screen.getByText("Diagnosis")).toBeInTheDocument();
    expect(screen.getByText("Prescription")).toBeInTheDocument();

    expect(screen.getByText("1 of 2 backed")).toBeInTheDocument();
    expect(screen.getByText("react-dashboard")).toBeInTheDocument();
    expect(screen.getByText(/go-cache\/src\/cache\.go/)).toBeInTheDocument();
  });

  it("frames an empty GitHub as a clean slate, not zero results", () => {
    const emptyReport: GapReport = {
      ...report,
      backed: [],
      github_is_empty: true,
    };
    render(<ResultsPanels report={emptyReport} plan={{ ...plan, github_is_empty: true }} />);

    expect(screen.getByText("Clean slate")).toBeInTheDocument();
    expect(screen.getByText(/Empty GitHub\?/)).toBeInTheDocument();
  });
});
