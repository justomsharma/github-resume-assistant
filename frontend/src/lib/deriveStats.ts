import type { AnalysisResponse, ClaimEvidence, GapReport } from "@/lib/types";
import { totalClaims } from "@/lib/types";

export type ExperienceLevel = "Entry Level" | "Mid Level" | "Senior Level";

export interface SkillCount {
  skill: string;
  count: number;
  pct: number;
}

export interface CategoryShare {
  category: string;
  pct: number;
}

/** All claim evidence across the three verdict buckets, in a flat list. */
function allEvidence(report: GapReport): ClaimEvidence[] {
  return [...report.backed, ...report.not_shown, ...report.not_verifiable];
}

/** Counts occurrences of each skill string across a list of evidence, case-insensitive. */
function countSkills(evidence: ClaimEvidence[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const e of evidence) {
    for (const skill of e.claim.skills) {
      const key = skill.trim();
      if (!key) continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return counts;
}

/** Overall score out of 10, one decimal: the fraction of claims backed by public evidence. */
export function overallScore(report: GapReport): number {
  const total = totalClaims(report);
  if (total === 0) return 0;
  return Math.round((report.backed.length / total) * 100) / 10;
}

/** Percentage of resume claims backed by public GitHub evidence. */
export function skillsMatchPct(report: GapReport): number {
  const total = totalClaims(report);
  if (total === 0) return 0;
  return Math.round((report.backed.length / total) * 100);
}

/**
 * Bucketed from the breadth of distinct skills named across all resume claims
 * (not GitHub data — there's no seniority signal to ground this in). The real
 * count is surfaced alongside the label so the bucket isn't presented as more
 * precise than it is.
 */
export function experienceLevel(report: GapReport): { level: ExperienceLevel; skillCount: number } {
  const distinctSkills = countSkills(allEvidence(report)).size;
  const level: ExperienceLevel =
    distinctSkills < 4 ? "Entry Level" : distinctSkills < 10 ? "Mid Level" : "Senior Level";
  return { level, skillCount: distinctSkills };
}

/** The most-frequent skill among claims GitHub actually backs, or a fallback when there's none. */
export function topStrength(report: GapReport): string {
  const counts = countSkills(report.backed);
  if (counts.size === 0) return "Not enough evidence yet";
  let best = "";
  let bestCount = -1;
  for (const [skill, count] of counts) {
    if (count > bestCount) {
      best = skill;
      bestCount = count;
    }
  }
  return best;
}

/** Share of all resume claims per category, as whole percentages that sum to ~100. */
export function skillsDistribution(report: GapReport): CategoryShare[] {
  const evidence = allEvidence(report);
  const total = evidence.length;
  if (total === 0) return [];

  const counts = new Map<string, number>();
  for (const e of evidence) {
    const key = e.claim.category || "other";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([category, count]) => ({ category, pct: Math.round((count / total) * 100) }))
    .sort((a, b) => b.pct - a.pct);
}

/** Top skills by mention frequency across all resume claims, most-mentioned first. */
export function topSkills(report: GapReport, limit = 5): SkillCount[] {
  const evidence = allEvidence(report);
  const counts = countSkills(evidence);
  const totalMentions = Array.from(counts.values()).reduce((sum, n) => sum + n, 0);
  if (totalMentions === 0) return [];

  return Array.from(counts.entries())
    .map(([skill, count]) => ({ skill, count, pct: Math.round((count / totalMentions) * 100) }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

export interface DashboardStats {
  overallScore: number;
  skillsMatchPct: number;
  experienceLevel: { level: ExperienceLevel; skillCount: number };
  topStrength: string;
  skillsDistribution: CategoryShare[];
  topSkills: SkillCount[];
  totalSkills: number;
}

export function deriveDashboardStats({ report }: AnalysisResponse): DashboardStats {
  return {
    overallScore: overallScore(report),
    skillsMatchPct: skillsMatchPct(report),
    experienceLevel: experienceLevel(report),
    topStrength: topStrength(report),
    skillsDistribution: skillsDistribution(report),
    topSkills: topSkills(report),
    totalSkills: countSkills(allEvidence(report)).size,
  };
}
