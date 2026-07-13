import type { AnalysisResponse, ClaimEvidence, Verdict } from "@/lib/types";
import { deriveDashboardStats } from "@/lib/deriveStats";

const VERDICT_LABEL: Record<Verdict, string> = {
  backed: "Backed by GitHub",
  not_shown: "Not shown yet",
  not_verifiable: "Not verifiable from public code",
};

function claimsSection(title: string, evidences: ClaimEvidence[]): string {
  if (evidences.length === 0) return `### ${title}\n\n_None._\n`;
  const lines = evidences.map((e) => `- **${e.claim.text}** — ${e.rationale}`);
  return `### ${title}\n\n${lines.join("\n")}\n`;
}

/** Builds a self-contained Markdown report from an analysis result, for local download. */
export function buildReportMarkdown(result: AnalysisResponse): string {
  const { report, plan } = result;
  const stats = deriveDashboardStats(result);

  const header = `# GitHub Resume Analysis — ${report.profile_login}\n`;

  if (report.github_is_empty) {
    return (
      `${header}\n` +
      `Your public GitHub doesn't back any resume claims yet — that's the common ` +
      `case when real work lives in private repos.\n\n` +
      buildPlanSection(plan.suggestions)
    );
  }

  const stats_section =
    `## Summary\n\n` +
    `- Overall score: ${stats.overallScore}/10\n` +
    `- Skills match: ${stats.skillsMatchPct}%\n` +
    `- Experience level (claimed breadth): ${stats.experienceLevel.level} (${stats.experienceLevel.skillCount} distinct skills)\n` +
    `- Top proven strength: ${stats.topStrength}\n`;

  const claims_section =
    `## Claims\n\n` +
    claimsSection(VERDICT_LABEL.backed, report.backed) +
    "\n" +
    claimsSection(VERDICT_LABEL.not_shown, report.not_shown) +
    "\n" +
    claimsSection(VERDICT_LABEL.not_verifiable, report.not_verifiable);

  return `${header}\n${stats_section}\n${claims_section}\n${buildPlanSection(plan.suggestions)}`;
}

function buildPlanSection(suggestions: AnalysisResponse["plan"]["suggestions"]): string {
  if (suggestions.length === 0) {
    return (
      `## Build Plan\n\n` +
      `No concrete, verifiable claims were found to ground suggestions on.\n`
    );
  }
  const items = suggestions.map(
    (s, i) =>
      `${i + 1}. **${s.title}** (${s.size}) — ${s.what_to_build}\n   Proves: ${
        s.proves_claim || "a claimed skill"
      }`
  );
  return `## Build Plan\n\n${items.join("\n")}\n`;
}

/** Builds a short plain-text summary of an analysis result, for clipboard sharing. */
export function buildShareSummary(result: AnalysisResponse): string {
  const { report, plan } = result;
  const stats = deriveDashboardStats(result);

  if (report.github_is_empty) {
    const topSuggestion = plan.suggestions[0];
    return (
      `My GitHub resume analysis (${report.profile_login}): public GitHub doesn't ` +
      `back any resume claims yet.` +
      (topSuggestion ? ` Next build: ${topSuggestion.title}.` : "")
    );
  }

  const topSuggestion = plan.suggestions[0];
  return (
    `My GitHub resume analysis (${report.profile_login}): ${stats.overallScore}/10 ` +
    `overall, ${stats.skillsMatchPct}% of claims backed by GitHub evidence. ` +
    `Top proven strength: ${stats.topStrength}.` +
    (topSuggestion ? ` Next build: ${topSuggestion.title}.` : "")
  );
}
