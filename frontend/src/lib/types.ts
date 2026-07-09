/**
 * Mirrors resume_assistant/core/models.py. Hand-written, not generated: the
 * backend's dataclasses are the source of truth (docs/ARCHITECTURE.md — core/
 * never imports anything web-specific), these types just describe the JSON
 * shape the Flask API returns via dataclasses.asdict().
 */

export type Verdict = "backed" | "not_shown" | "not_verifiable";

export interface Claim {
  text: string;
  skills: string[];
  category: string;
}

export interface ClaimEvidence {
  claim: Claim;
  verdict: Verdict;
  matching_repos: string[];
  cited_files: string[];
  rationale: string;
}

export interface GapReport {
  profile_login: string;
  backed: ClaimEvidence[];
  not_shown: ClaimEvidence[];
  not_verifiable: ClaimEvidence[];
  github_is_empty: boolean;
}

export interface Suggestion {
  title: string;
  what_to_build: string;
  proves_claim: string;
  skills: string[];
  size: string;
  skip: string;
}

export interface ProjectPlan {
  profile_login: string;
  suggestions: Suggestion[];
  github_is_empty: boolean;
}

export interface AnalysisResponse {
  report: GapReport;
  plan: ProjectPlan;
}

export interface ApiErrorResponse {
  error: string;
}

/** Derived counts the UI needs; not sent by the API, computed client-side. */
export function totalClaims(report: GapReport): number {
  return report.backed.length + report.not_shown.length + report.not_verifiable.length;
}
