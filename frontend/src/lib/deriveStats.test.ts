import { describe, expect, it } from "vitest";
import type { ClaimEvidence, GapReport } from "@/lib/types";
import {
  deriveDashboardStats,
  experienceLevel,
  overallScore,
  skillsDistribution,
  skillsMatchPct,
  topSkills,
  topStrength,
} from "./deriveStats";

function evidence(overrides: Partial<ClaimEvidence>): ClaimEvidence {
  return {
    claim: { text: "claim", skills: [], category: "project" },
    verdict: "not_shown",
    matching_repos: [],
    cited_files: [],
    rationale: "",
    ...overrides,
  };
}

const normalReport: GapReport = {
  profile_login: "octocat",
  backed: [
    evidence({
      claim: { text: "Built a distributed cache in Go", skills: ["go", "redis"], category: "project" },
      verdict: "backed",
    }),
    evidence({
      claim: { text: "Wrote a Go CLI tool", skills: ["go"], category: "project" },
      verdict: "backed",
    }),
  ],
  not_shown: [
    evidence({
      claim: { text: "Proficient in React", skills: ["react"], category: "skill" },
      verdict: "not_shown",
    }),
  ],
  not_verifiable: [
    evidence({
      claim: { text: "Reduced latency by 30%", skills: ["go"], category: "impact" },
      verdict: "not_verifiable",
    }),
  ],
  github_is_empty: false,
};

const emptyReport: GapReport = {
  profile_login: "octocat",
  backed: [],
  not_shown: [
    evidence({
      claim: { text: "Proficient in React", skills: ["react", "typescript"], category: "skill" },
      verdict: "not_shown",
    }),
  ],
  not_verifiable: [],
  github_is_empty: true,
};

const singleClaimReport: GapReport = {
  profile_login: "octocat",
  backed: [
    evidence({
      claim: { text: "Built a distributed cache in Go", skills: ["go"], category: "project" },
      verdict: "backed",
    }),
  ],
  not_shown: [],
  not_verifiable: [],
  github_is_empty: false,
};

const zeroClaimsReport: GapReport = {
  profile_login: "octocat",
  backed: [],
  not_shown: [],
  not_verifiable: [],
  github_is_empty: false,
};

describe("deriveStats", () => {
  describe("normal report (backed + gaps + not-verifiable)", () => {
    it("computes overallScore and skillsMatchPct from the backed fraction", () => {
      expect(overallScore(normalReport)).toBeCloseTo(5, 1); // 2 of 4 backed -> 5.0/10
      expect(skillsMatchPct(normalReport)).toBe(50);
    });

    it("buckets experienceLevel from distinct skill breadth", () => {
      // go, redis, react -> 3 distinct skills -> Entry Level bucket
      const result = experienceLevel(normalReport);
      expect(result.level).toBe("Entry Level");
      expect(result.skillCount).toBe(3);
    });

    it("picks the most-frequent skill among backed claims as topStrength", () => {
      expect(topStrength(normalReport)).toBe("go");
    });

    it("computes skillsDistribution across all claims, sorted by share", () => {
      const dist = skillsDistribution(normalReport);
      const total = dist.reduce((sum, c) => sum + c.pct, 0);
      expect(total).toBe(100);
      expect(dist[0].category).toBe("project"); // 2 of 4 claims
    });

    it("computes topSkills by mention frequency", () => {
      const skills = topSkills(normalReport);
      expect(skills[0].skill).toBe("go"); // mentioned in 3 of 4 claims
      expect(skills[0].count).toBe(3);
    });
  });

  describe("empty-GitHub case", () => {
    it("has zero overallScore and skillsMatchPct with no backed claims", () => {
      expect(overallScore(emptyReport)).toBe(0);
      expect(skillsMatchPct(emptyReport)).toBe(0);
    });

    it("falls back topStrength to a message instead of crashing", () => {
      expect(topStrength(emptyReport)).toBe("Not enough evidence yet");
    });

    it("still computes experienceLevel from resume-claimed skills, not GitHub", () => {
      const result = experienceLevel(emptyReport);
      expect(result.skillCount).toBe(2); // react, typescript
      expect(result.level).toBe("Entry Level");
    });
  });

  describe("single-claim edge case", () => {
    it("scores 10/10 and 100% when the only claim is backed", () => {
      expect(overallScore(singleClaimReport)).toBe(10);
      expect(skillsMatchPct(singleClaimReport)).toBe(100);
      expect(topStrength(singleClaimReport)).toBe("go");
    });
  });

  describe("zero-claims case", () => {
    it("never divides by zero — everything reads 0, not NaN", () => {
      expect(overallScore(zeroClaimsReport)).toBe(0);
      expect(skillsMatchPct(zeroClaimsReport)).toBe(0);
      expect(skillsDistribution(zeroClaimsReport)).toEqual([]);
      expect(topSkills(zeroClaimsReport)).toEqual([]);
      expect(topStrength(zeroClaimsReport)).toBe("Not enough evidence yet");
    });
  });

  describe("deriveDashboardStats", () => {
    it("assembles all stats from an AnalysisResponse", () => {
      const stats = deriveDashboardStats({
        report: normalReport,
        plan: { profile_login: "octocat", suggestions: [], github_is_empty: false },
      });
      expect(stats.overallScore).toBeCloseTo(5, 1);
      expect(stats.skillsMatchPct).toBe(50);
      expect(stats.topStrength).toBe("go");
      expect(stats.totalSkills).toBe(3);
    });
  });
});
