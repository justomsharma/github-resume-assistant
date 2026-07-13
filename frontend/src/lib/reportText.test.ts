import { describe, expect, it } from "vitest";
import type { AnalysisResponse } from "@/lib/types";
import { buildReportMarkdown, buildShareSummary } from "./reportText";

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
    not_verifiable: [
      {
        claim: { text: "Reduced latency by 30%", skills: ["go"], category: "impact" },
        verdict: "not_verifiable",
        matching_repos: [],
        cited_files: [],
        rationale: "Not verifiable from public code.",
      },
    ],
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

const zeroClaimsResult: AnalysisResponse = {
  report: {
    profile_login: "octocat",
    backed: [],
    not_shown: [],
    not_verifiable: [],
    github_is_empty: false,
  },
  plan: {
    profile_login: "octocat",
    suggestions: [],
    github_is_empty: false,
  },
};

describe("buildReportMarkdown", () => {
  it("includes the profile header, score, and all three verdict sections for a normal report", () => {
    const md = buildReportMarkdown(normalResult);

    expect(md).toContain("# GitHub Resume Analysis — octocat");
    expect(md).toContain("Overall score: 3.3/10");
    expect(md).toContain("### Backed by GitHub");
    expect(md).toContain("Built a distributed cache in Go");
    expect(md).toContain("### Not shown yet");
    expect(md).toContain("Proficient in React");
    expect(md).toContain("### Not verifiable from public code");
    expect(md).toContain("Reduced latency by 30%");
    expect(md).toContain("react-dashboard");
  });

  it("shows the empty-state message and skips claim sections for the empty-GitHub case", () => {
    const md = buildReportMarkdown(emptyResult);

    expect(md).toContain("doesn't back any resume claims yet");
    expect(md).not.toContain("### Backed by GitHub");
    expect(md).toContain("## Build Plan");
    expect(md).toContain("No concrete, verifiable claims were found");
  });

  it("does not crash on a zero-claims (non-empty) report and shows placeholders", () => {
    const md = buildReportMarkdown(zeroClaimsResult);

    expect(md).toContain("### Backed by GitHub");
    expect(md).toContain("_None._");
    expect(md).toContain("No concrete, verifiable claims were found");
  });

  it("renders numbered suggestions in the build plan when present", () => {
    const md = buildReportMarkdown(normalResult);
    expect(md).toContain("1. **react-dashboard** (a weekend)");
    expect(md).toContain("Proves: Proficient in React");
  });
});

describe("buildShareSummary", () => {
  it("includes profile login, score, top strength, and top suggestion for a normal report", () => {
    const summary = buildShareSummary(normalResult);

    expect(summary).toContain("octocat");
    expect(summary).toContain("3.3/10");
    expect(summary).toContain("go");
    expect(summary).toContain("react-dashboard");
  });

  it("uses empty-state phrasing instead of score text for the empty-GitHub case", () => {
    const summary = buildShareSummary(emptyResult);

    expect(summary).toContain("doesn't back any resume claims yet");
    expect(summary).not.toContain("/10");
  });
});
