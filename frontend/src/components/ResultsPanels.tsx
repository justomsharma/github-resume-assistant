import type { GapReport, ProjectPlan } from "@/lib/types";
import { totalClaims } from "@/lib/types";
import ContributionGraph from "./ContributionGraph";

/** Port of results.html's 3-panel overview (Score / Diagnosis / Prescription). */
export default function ResultsPanels({ report, plan }: { report: GapReport; plan: ProjectPlan }) {
  const backed = report.backed.length;
  const gaps = report.not_shown.length;
  const nverif = report.not_verifiable.length;
  const total = totalClaims(report);
  const pct = total ? Math.floor((backed * 100) / total) : 0;
  const empty = report.github_is_empty;

  return (
    <div className="panels">
      {/* ---- Score panel ---- */}
      <details className="panel panel-score" data-empty={empty ? "true" : "false"} open>
        <summary className="phead">
          <span className="pn">℞</span>
          <span className="pt">
            <span className="plabel">Score</span>
            <span className="pgist">{empty ? "Clean slate" : `${backed} of ${total} backed`}</span>
          </span>
          <span className="chev" aria-hidden="true" />
        </summary>
        <div className="pbody">
          <section className="hero" data-empty={empty ? "true" : "false"}>
            {empty ? (
              <>
                <span className="kicker" data-role="">
                  Your next 30 days
                </span>
                <h1>
                  Empty GitHub? <em>Good — a clean slate.</em>
                </h1>
                <p className="hlede">
                  Nothing public backs your resume yet. That&rsquo;s the common case when your
                  real work lives in private repos. Here&rsquo;s the plan that fills this in.
                </p>
              </>
            ) : (
              <>
                <span className="kicker" data-role="">
                  You&rsquo;ve got public work — let&rsquo;s aim it
                </span>
                <h1>
                  {backed} of {total} claims are already <em>backed</em> by your GitHub.
                </h1>
                <p className="hlede">
                  Your public repos prove {backed >= gaps ? "most" : "some"} of your resume. {gaps}{" "}
                  claim{gaps !== 1 ? "s" : ""} still {gaps !== 1 ? "have" : "has"} no public
                  evidence — closing those is where the leverage is.
                </p>
              </>
            )}

            {!(empty || total === 0) && (
              <div className="summary">
                <div className="meter" style={{ "--pct": pct } as React.CSSProperties}>
                  <span className="val">
                    <b>{pct}%</b>
                    <span>backed</span>
                  </span>
                </div>
                <div className="callout">
                  <div className="big">
                    {backed} of {total} claims backed by public code.
                  </div>
                  <div className="small">
                    Each verdict is graded against your real repo code — dependencies, file tree,
                    and README — and backed claims cite the specific files that prove them.
                  </div>
                </div>
              </div>
            )}

            <ContributionGraph empty={empty} />
            <div className="glegend">
              <span>
                {empty
                  ? "0 public contributions today → a plan to change that this month"
                  : "Active public history — this is your credibility engine"}
              </span>
              <span className="scale">
                less <i style={{ background: "var(--g0)" }} />
                <i style={{ background: "var(--g1)" }} />
                <i style={{ background: "var(--g2)" }} />
                <i style={{ background: "var(--g3)" }} />
                <i style={{ background: "var(--g4)" }} /> more
              </span>
            </div>
          </section>
        </div>
      </details>

      {/* ---- Gaps panel (Diagnosis) ---- */}
      <details className="panel panel-gaps">
        <summary className="phead">
          <span className="pn">℞</span>
          <span className="pt">
            <span className="plabel">Diagnosis</span>
            <span className="pgist">
              {backed} backed · {gaps} not shown{nverif ? ` · ${nverif} not verifiable` : ""}
            </span>
          </span>
          <span className="chev" aria-hidden="true" />
        </summary>
        <div className="pbody">
          <p className="subtle">
            What your public code does and doesn&rsquo;t yet prove. Each claim is graded against
            your real repos and backed claims cite specific files — so &ldquo;not shown yet&rdquo;
            is a gap to close, not a mark against you, and &ldquo;not verifiable from public
            code&rdquo; just means public code can&rsquo;t prove that kind of claim.
          </p>

          {total === 0 ? (
            <div className="dx">
              <div className="r">
                <span className="claim">
                  No concrete, verifiable claims were found in the resume text.
                  <span className="why">
                    Add specific projects, technologies, and outcomes, then run this again.
                  </span>
                </span>
              </div>
            </div>
          ) : (
            <div className="dx">
              {report.backed.map((evidence, i) => (
                <div className="r" key={`backed-${i}`}>
                  <span className="st st-ok">backed</span>
                  <span className="claim">
                    {evidence.claim.text}
                    <span className="why">
                      {evidence.rationale}
                      {evidence.cited_files.length > 0 && (
                        <span className="cites"> Cites: {evidence.cited_files.join(", ")}</span>
                      )}
                    </span>
                  </span>
                </div>
              ))}
              {report.not_shown.map((evidence, i) => (
                <div className="r" key={`not-shown-${i}`}>
                  <span className="st st-gap">not shown yet</span>
                  <span className="claim">
                    {evidence.claim.text}
                    <span className="why">{evidence.rationale}</span>
                  </span>
                </div>
              ))}
              {report.not_verifiable.map((evidence, i) => (
                <div className="r" key={`not-verifiable-${i}`}>
                  <span className="st st-na">not verifiable from public code</span>
                  <span className="claim">
                    {evidence.claim.text}
                    <span className="why">{evidence.rationale}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </details>

      {/* ---- Plan panel (Prescription) ---- */}
      <details className="panel panel-plan" open>
        <summary className="phead">
          <span className="pn">℞</span>
          <span className="pt">
            <span className="plabel">Prescription</span>
            <span className="pgist">
              {plan.suggestions.length > 0
                ? `${plan.suggestions.length} project${plan.suggestions.length !== 1 ? "s" : ""} · gaps first`
                : "add specifics to unlock"}
            </span>
          </span>
          <span className="chev" aria-hidden="true" />
        </summary>
        <div className="pbody">
          {plan.suggestions.length > 0 ? (
            <>
              <p className="subtle">
                {empty
                  ? "Projects ranked so each turns one resume claim into public proof."
                  : "Fewer, sharper projects — you need the missing pieces, not volume."}
              </p>
              <div className="track">
                {plan.suggestions.map((s, i) => (
                  <div className="step" key={s.title}>
                    <div className="rail">
                      <div className="num">{i + 1}</div>
                      <div className="line" />
                    </div>
                    <div className="card2">
                      <div className="t">
                        <span className="title">{s.title}</span>
                        <span className="size">{s.size}</span>
                      </div>
                      <p className="build">{s.what_to_build}</p>
                      <div className="foot">
                        <span>
                          Proves: <b>{s.proves_claim || "a claimed skill"}</b>
                        </span>
                        <span className="skip">
                          Skip: <b>{s.skip || "anything not core to the demo"}</b>
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="subtle">
              No concrete, verifiable claims were found to ground suggestions on. Add specific
              projects, technologies, and outcomes to your resume, then run this again.
            </p>
          )}
        </div>
      </details>
    </div>
  );
}
