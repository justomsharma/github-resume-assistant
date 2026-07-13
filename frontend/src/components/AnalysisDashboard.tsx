"use client";

import { useState } from "react";
import type { AnalysisResponse, GapReport, ProjectPlan } from "@/lib/types";
import { totalClaims } from "@/lib/types";
import { deriveDashboardStats } from "@/lib/deriveStats";
import { buildReportMarkdown, buildShareSummary } from "@/lib/reportText";
import DashboardSidebar from "./DashboardSidebar";
import EmptyState from "./EmptyState";

type Tab = "overview" | "skills" | "experience" | "projects" | "recommendations";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "▦" },
  { id: "skills", label: "Skills", icon: "◫" },
  { id: "experience", label: "Experience", icon: "▤" },
  { id: "projects", label: "Projects", icon: "◇" },
  { id: "recommendations", label: "Recommendations", icon: "✦" },
];

const CATEGORY_COLORS = ["#6d4aff", "#ff8a3d", "#22b07d", "#ff4d8d", "#3da5ff"];

interface StatCardProps {
  label: string;
  value: string;
  sub: string;
  pct?: number;
  subTone?: "good" | "muted";
}

/** A stat card with an optional SVG progress ring. */
function StatCard({ label, value, sub, pct, subTone = "good" }: StatCardProps) {
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const offset = pct === undefined ? circumference : circumference * (1 - pct / 100);

  return (
    <div className="dcard">
      <div className="dcard-label">{label}</div>
      <div className="dcard-row">
        <div className="dcard-value">{value}</div>
        {pct !== undefined && (
          <div className="dring-wrap">
            <svg className="dring" viewBox="0 0 76 76" aria-hidden="true">
              <circle className="dring-track" cx="38" cy="38" r={radius} />
              <circle
                className="dring-arc"
                cx="38"
                cy="38"
                r={radius}
                strokeDasharray={circumference}
                strokeDashoffset={offset}
              />
            </svg>
          </div>
        )}
      </div>
      <div className={`dcard-sub${subTone === "muted" ? " dcard-sub-muted" : ""}`}>{sub}</div>
    </div>
  );
}

function ProfileSummary({ report, stats }: { report: AnalysisResponse["report"]; stats: ReturnType<typeof deriveDashboardStats> }) {
  const total = totalClaims(report);
  const backed = report.backed.length;

  if (report.github_is_empty || total === 0) {
    return (
      <p>
        Your public GitHub doesn&rsquo;t back any resume claims yet &mdash; that&rsquo;s the
        common case when real work lives in private repos. Use the Projects tab for a ranked plan
        to close that gap.
      </p>
    );
  }

  return (
    <p>
      You have {stats.totalSkills} distinct skill{stats.totalSkills === 1 ? "" : "s"} named across
      your resume, and public GitHub evidence already backs {backed} of {total} claim
      {total === 1 ? "" : "s"}. {stats.topStrength !== "Not enough evidence yet" && (
        <>Your strongest proven skill is <b>{stats.topStrength}</b>.</>
      )}
    </p>
  );
}

export default function AnalysisDashboard({
  result,
  onBackToHome,
}: {
  result: { report: GapReport; plan: ProjectPlan | null };
  onBackToHome: () => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const [copied, setCopied] = useState(false);
  const { report, plan } = result;
  const stats = deriveDashboardStats(result);
  const total = totalClaims(report);
  const topSuggestion = plan?.suggestions[0];

  function handleDownload() {
    if (!plan) return;
    const markdown = buildReportMarkdown({ report, plan });
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "resume-analysis-report.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleShare() {
    if (!plan) return;
    await navigator.clipboard.writeText(buildShareSummary({ report, plan }));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="dash">
      <div className="dshell">
        <DashboardSidebar profileLogin={report.profile_login} onBackToHome={onBackToHome} />
        <main className="dmain">
          <button type="button" className="dback" onClick={onBackToHome}>
            ← Back to Home
          </button>

          <div className="dtop">
            <div>
              <h1 className="dtitle">Analysis Complete! 🎉</h1>
              <p className="dsub">Here&rsquo;s your personalized analysis report.</p>
            </div>
            <div className="dtop-actions">
              <button
                type="button"
                className="dbtn dbtn-ghost"
                onClick={handleDownload}
                disabled={!plan}
                title={plan ? undefined : "Still generating your build plan…"}
              >
                ⬇ Download Report
              </button>
              <button
                type="button"
                className="dbtn dbtn-primary"
                onClick={handleShare}
                disabled={!plan}
                title={plan ? undefined : "Still generating your build plan…"}
              >
                {copied ? "✓ Copied!" : "⇄ Share Report"}
              </button>
            </div>
          </div>

          <div className="dstats">
            <StatCard label="Overall Score" value={`${stats.overallScore}/10`} pct={stats.overallScore * 10} sub={stats.overallScore >= 7 ? "Excellent" : stats.overallScore >= 4 ? "Good" : "Needs work"} />
            <StatCard label="Skills Match" value={`${stats.skillsMatchPct}%`} pct={stats.skillsMatchPct} sub={stats.skillsMatchPct >= 70 ? "Great match" : "Room to grow"} />
            <StatCard label="Experience Level" value={stats.experienceLevel.level} sub={`${stats.experienceLevel.skillCount} skills claimed`} />
            <StatCard
              label="Top Strength"
              value={stats.topStrength}
              sub={stats.topStrength === "Not enough evidence yet" ? "No backed claims yet" : "GitHub-verified"}
              subTone={stats.topStrength === "Not enough evidence yet" ? "muted" : "good"}
            />
          </div>

          <div className="dtabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`dtab${tab === t.id ? " active" : ""}`}
                onClick={() => setTab(t.id)}
              >
                <span className="dtab-ic">{t.icon}</span> {t.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <>
              <div className="dgrid-2">
                <div className="dpanel">
                  <div className="dpanel-h">Profile Summary</div>
                  <ProfileSummary report={report} stats={stats} />
                </div>
                <div className="dpanel">
                  <div className="dpanel-h">Top Skills</div>
                  {stats.topSkills.length === 0 ? (
                    <p className="dmuted">No skills found in the resume text yet.</p>
                  ) : (
                    <ul className="dskilllist">
                      {stats.topSkills.map((s) => (
                        <li key={s.skill} className="dskillrow">
                          <span className="dskillname">{s.skill}</span>
                          <div className="dskillbar">
                            <div className="dskillbar-fill" style={{ width: `${s.pct}%` }} />
                          </div>
                          <span className="dskillpct">{s.pct}%</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <div className="dgrid-2">
                <div className="dpanel">
                  <div className="dpanel-h">Key Highlights</div>
                  <ul className="dhighlights">
                    <li>
                      ✓ {total} claim{total === 1 ? "" : "s"} extracted from your resume
                    </li>
                    <li>
                      ✓ {report.backed.length} claim{report.backed.length === 1 ? "" : "s"} backed
                      by public GitHub evidence
                    </li>
                    <li>✓ {stats.totalSkills} distinct skills named across your claims</li>
                    <li>
                      {plan
                        ? `✓ ${plan.suggestions.length} build-plan project${plan.suggestions.length === 1 ? "" : "s"} suggested`
                        : "⏳ Build-plan projects still generating…"}
                    </li>
                  </ul>
                </div>
                <div className="dpanel">
                  <div className="dpanel-h">Skills Distribution</div>
                  {stats.skillsDistribution.length === 0 ? (
                    <p className="dmuted">No categorized claims yet.</p>
                  ) : (
                    <div className="ddonut-row">
                      <div
                        className="ddonut"
                        style={{
                          background: `conic-gradient(${donutStops(stats.skillsDistribution)})`,
                        }}
                      >
                        <div className="ddonut-hole">
                          <b>{stats.skillsDistribution.length}</b>
                          <span>Categories</span>
                        </div>
                      </div>
                      <ul className="ddonut-legend">
                        {stats.skillsDistribution.map((c, i) => (
                          <li key={c.category}>
                            <i style={{ background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }} />
                            {c.category} <span>{c.pct}%</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>

              {topSuggestion && (
                <div className="drecommend">
                  <div>
                    <div className="drecommend-h">✦ AI Recommendation</div>
                    <p>{topSuggestion.what_to_build}</p>
                    <button type="button" className="dbtn dbtn-primary" onClick={() => setTab("recommendations")}>
                      View Recommendations →
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {tab === "skills" && (
            <div className="dpanel">
              <div className="dpanel-h">All Claims by Verdict</div>
              {total === 0 ? (
                <EmptyState
                  icon="◫"
                  title="No claims to show yet"
                  description="Add specific projects, technologies, and outcomes to your resume, then run this again."
                />
              ) : (
                <>
                  <ClaimList title="Backed by GitHub" evidences={report.backed} tone="ok" />
                  <ClaimList title="Not shown yet" evidences={report.not_shown} tone="gap" />
                  <ClaimList
                    title="Not verifiable from public code"
                    evidences={report.not_verifiable}
                    tone="na"
                  />
                </>
              )}
            </div>
          )}

          {tab === "experience" && (
            <div className="dpanel">
              <div className="dpanel-h">Claimed Skill Breadth</div>
              <p>
                Your resume names {stats.totalSkills} distinct skill{stats.totalSkills === 1 ? "" : "s"} across{" "}
                {stats.skillsDistribution.length} categor{stats.skillsDistribution.length === 1 ? "y" : "ies"}, which
                buckets to <b>{stats.experienceLevel.level}</b> by claimed breadth &mdash; this reflects what the
                resume states, not a verified years-of-experience figure.
              </p>
              <ul className="dhighlights">
                {stats.skillsDistribution.map((c) => (
                  <li key={c.category}>
                    {c.category}: {c.pct}% of claims
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tab === "projects" &&
            (plan ? (
              <SuggestionList suggestions={plan.suggestions} />
            ) : (
              <div className="dpanel">
                <EmptyState
                  icon="⏳"
                  title="Generating your build plan…"
                  description="We're still ranking project suggestions against your gap report. This tab fills in automatically once it's ready."
                />
              </div>
            ))}

          {tab === "recommendations" &&
            (plan ? (
              <SuggestionList suggestions={plan.suggestions} detailed />
            ) : (
              <div className="dpanel">
                <EmptyState
                  icon="⏳"
                  title="Generating your build plan…"
                  description="We're still ranking project suggestions against your gap report. This tab fills in automatically once it's ready."
                />
              </div>
            ))}
        </main>
      </div>
    </div>
  );
}

function donutStops(distribution: { category: string; pct: number }[]): string {
  let acc = 0;
  const parts: string[] = [];
  distribution.forEach((c, i) => {
    const start = acc;
    acc += c.pct;
    parts.push(`${CATEGORY_COLORS[i % CATEGORY_COLORS.length]} ${start}% ${acc}%`);
  });
  return parts.join(", ");
}

function ClaimList({
  title,
  evidences,
  tone,
}: {
  title: string;
  evidences: AnalysisResponse["report"]["backed"];
  tone: "ok" | "gap" | "na";
}) {
  if (evidences.length === 0) return null;
  return (
    <div className="dclaimgroup">
      <div className="dclaimgroup-h">
        {title} ({evidences.length})
      </div>
      {evidences.map((e, i) => (
        <div className="dclaim" key={`${tone}-${i}`}>
          <span className={`dst dst-${tone}`}>{tone === "ok" ? "backed" : tone === "gap" ? "not shown" : "n/a"}</span>
          <div>
            <div className="dclaim-text">{e.claim.text}</div>
            <div className="dclaim-why">{e.rationale}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SuggestionList({
  suggestions,
  detailed = false,
}: {
  suggestions: AnalysisResponse["plan"]["suggestions"];
  detailed?: boolean;
}) {
  if (suggestions.length === 0) {
    return (
      <div className="dpanel">
        <EmptyState
          icon="◇"
          title="No suggestions yet"
          description="No concrete, verifiable claims were found to ground suggestions on. Add specific projects, technologies, and outcomes to your resume, then run this again."
        />
      </div>
    );
  }

  return (
    <div className="dpanel">
      {suggestions.map((s, i) => (
        <div className="dsuggestion" key={s.title}>
          <div className="dsuggestion-h">
            <span className="dsuggestion-n">{i + 1}</span>
            <span className="dsuggestion-t">{s.title}</span>
            <span className="dsuggestion-size">{s.size}</span>
          </div>
          <p>{s.what_to_build}</p>
          {detailed && (
            <div className="dsuggestion-foot">
              <span>
                Proves: <b>{s.proves_claim || "a claimed skill"}</b>
              </span>
              <span>
                Skip: <b>{s.skip || "anything not core to the demo"}</b>
              </span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
