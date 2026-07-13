# Roadmap: GitHub Resume Assistant

> Clear view of what each version includes. Build strictly in order.
> Do NOT pull work forward from a later version to "get ahead" — each version
> must earn the next by proving its value.

Legend: ✅ done · 🔨 in progress · ⬜ not started

---

## v0.1 — Walking skeleton (start here)

**Goal:** prove the MCP plumbing works end-to-end with one real tool.

- ✅ Python project initialized with the `mcp` library
- ✅ MCP server runs locally over stdio
- ✅ `fetch_github_repos(username)` implemented against the real GitHub API
- ✅ Registered and callable from **Claude Desktop**
- ✅ Returns: profile summary, repo list, stars, primary languages, last-push dates

**Deliverable:** In Claude Desktop, "show me my GitHub repos" returns your real data.

**Definition of done:** you can see your own repos through Claude via the server.

---

## v0.2 — The gap finder

**Goal:** turn raw GitHub data into insight about the resume.

- ✅ `analyze_resume(resume_text)` implemented
- ✅ Extracts the strongest *claims* from the resume
- ✅ Cross-references claims against `fetch_github_repos` output
- ✅ Produces a **gap report**: which claims have public evidence, which don't
- ✅ Uses the Anthropic API *inside the server* for the analysis
- ✅ SQLite caching so repeated calls don't re-hit APIs

**Deliverable:** Claude can tell you which resume claims your GitHub does/doesn't back up.

---

## v0.3 — The prescription (the star tool)

**Goal:** the reason the product exists.

- ✅ `suggest_projects()` implemented
- ✅ Input: the gap report + GitHub reality + resume claims
- ✅ Output: a **ranked 30-day plan** of specific, shippable projects
- ✅ Each suggestion tied to a concrete resume claim it would prove
- ✅ Each suggestion sized ("a weekend", "a week") and scoped (what to skip)

**Deliverable:** "Here are 3 things to build this month to make your resume credible."

**This is the v1 milestone. Ship it. Use it on yourself. Get feedback.**

---

## v1.0 — Production polish (shippable, public)

**Goal:** something you'd link in a job application.

- ✅ Error handling + retry/backoff on GitHub and Anthropic calls
- ✅ Rate-limit handling for the GitHub API
- ⬜ Config via env vars (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`)
- ✅ Full README with setup + Claude Desktop config instructions
- ✅ Test suite passing in CI (GitHub Actions)
- ✅ Docker image builds
- ✅ Public GitHub repo with docs and a short write-up

**Deliverable:** shareable, documented, tested MCP server.

---

## v2.0 — Two faces on one engine (only if v1 proves useful)

> Gated: build this ONLY after v1 has proven the advice is genuinely good on you
> and ideally 2–3 other people. This is the "reach real users" bet from the
> office-hours session. Do not start it on speculation.

**Insight from office hours:** job-seekers don't install MCP servers; engineers do.
To reach real users you need a no-install surface.

- ⬜ Refactor analysis logic into a **plain Python library** (`core/`)
- ⬜ MCP server becomes a thin adapter over `core/` (for you + portfolio)
- ✅ Add a **simple web app** over the same `core/` (for job-seekers, no install)
- ✅ Web app: paste resume + enter GitHub username → gap report + build plan
- ⬜ Deploy (Railway / Render free tier) — unblocked by v2.1 (grounded verdicts
  now honest); the deploy itself is the last remaining step.

**Deliverable:** same engine, two front doors — MCP for builders, web for everyone.

---

## v2.1 — Grounded match fidelity (gates the v2.0 deploy)

**Goal:** make the "backed" verdict honest. The v2.0 matcher marked a claim
"backed" if a skill token merely appeared in a repo's name, description, or
primary language — so "built a distributed cache in Go" was "backed" by any repo
mentioning "go". That false positive undercuts the whole grounding moat
(PRODUCT.md). This is a quality item, not new surface — it gates the v2.0 deploy.

- ✅ Fetch real repo evidence for every non-fork repo: dependency manifests
  (parsed), recursive file tree, language breakdown, and README (bounded to a
  char budget) — reusing the existing retry/rate-limit client
- ✅ Replace the token matcher with an **LLM-graded verdict** that cites specific
  files and returns one of three honest verdicts per claim:
  `backed` / `not_shown` / `not_verifiable` (the last for claims public code
  structurally can't prove — enterprise usage, latency, "300+/day", cost %)
- ✅ Scale to "all repos" safely: per-repo char budget + batched verification
  under a token budget with merged verdicts; cache evidence per repo `pushed_at`
  and verdicts per model + claims + evidence fingerprint
- ✅ Three honest verdict labels across MCP + web; empty-GitHub stays the main
  case (every claim `not_shown`, verifier skipped)

**Deliverable:** on your real resume + GitHub, "backed" verdicts cite real files
and are true; unprovable claims read "not verifiable from public code"; genuine
gaps read "not shown yet". Then the v2.0 deploy is unblocked.

---

## v2.2 — Web upload + premium landing

**Goal:** meet job-seekers where they are — let them drop in a resume file
instead of pasting text, on a landing that looks like a product, not a form.

- ✅ Web landing redesigned to a premium "analyze your profile" layout
  (violet theme + sidebar shell, scoped to the landing so results is untouched)
- ✅ Resume **file upload** (PDF / DOCX) parsed to text in the web layer
  (`web/resume_upload.py`); `core/` stays pure and still receives text
- ✅ 10 MB cap + friendly errors for empty / oversized / unsupported / unreadable
  files; pasted-text path kept as a tolerant fallback

**Deliverable:** upload a PDF/DOCX + GitHub username on a polished page → same
grounded gap report and 30-day plan.

---

## v2.3 — Next.js frontend + JSON API split

**Goal:** give the UI room to grow. The v2.2 Jinja-rendered pages were fine for a
static two-page flow, but hand-rolled JS gets painful as interactivity grows —
move to a typed frontend without touching the proven `core/` engine.

- ✅ `web/app.py` becomes a pure JSON API (`POST /api/analyze`); the Jinja
  templates/static assets are retired, not kept in parallel
- ✅ `frontend/` — a new Next.js + TypeScript app (App Router) reproducing the
  v2.2 landing + v2.1 results UI as React components, calling the API directly
  from the browser (`NEXT_PUBLIC_API_URL`, no Next.js server proxy)
- ✅ CORS scoped to the frontend's origin (`FRONTEND_ORIGIN` config, never a
  wildcard — the API accepts file uploads)
- ✅ `core/`, `clients/`, `cache/` untouched — this is an interface-layer swap
- ✅ Deploy configs for two free-tier services: `render.yaml` (Flask API on
  Render) + Vercel (Next.js frontend, root directory `frontend/`)

**Deliverable:** the same grounded gap report + 30-day plan, served by a
TypeScript frontend and a JSON API, deployable as two free-tier services.

---

## v2.4 — Frontend maturity pass

**Goal:** the v2.3 frontend proved the API split works but is still a thin,
two-screen app. Grow it into something that reads as a real product surface
before scope grows further.

- ⬜ Grow past 6 components — add loading/error states, empty states, and a
  settings/history view
- ⬜ Real state management story (Zustand/Context, justified by what the new
  views actually need — not added speculatively)
- ⬜ Responsive design pass + Lighthouse score
- ⬜ Accessibility audit (axe/Lighthouse a11y pass)

**Deliverable:** the frontend holds up under real usage — handles slow/failed
requests and empty state gracefully, works on mobile, and passes an a11y audit.

---

## v2.5 — Perceived performance: granular progress + progressive results

**Goal:** analyzing a large GitHub account (many repos) can take well over a
minute, and today the loading screen looks frozen through most of it — the
5 stages are reported as evenly-weighted, but `evidence` (fetch code-level
facts per non-fork repo) and `report` (grade claims against evidence, already
batched under a char budget) dominate wall-clock time with zero visibility
into progress until each stage's blocking call returns everything at once.

- ⬜ Granular sub-progress: `clients/github.py`'s `fetch_repo_evidence` and
  `clients/anthropic.py`'s `verify_claims` accept an optional progress
  callback, firing per repo / per verification batch respectively
  (`core/analysis.py`'s `ClaimVerifier` protocol gains the optional param)
- ⬜ SSE carries the sub-progress detail (e.g. "Reading repo 14 of 52") so
  `AnalysisProgress.tsx` shows real, continuously-moving progress instead of
  sitting still on one of the two heavy stages
- ⬜ Progressive reveal: `run_analysis_events` yields the gap report as its
  own event as soon as it's ready, then the plan afterward, instead of one
  bundled terminal result — the frontend switches to `AnalysisDashboard` the
  moment the report lands (Overview/Skills populated), while
  Projects/Recommendations show a "Generating your build plan…" state until
  the plan event arrives
- ⬜ Explicitly out of scope for this version: claim-by-claim streaming inside
  the report itself — would require restructuring the caching layer
  (`cache/store.py` currently caches only complete result lists) for
  uncertain extra benefit on top of the two items above

**Deliverable:** on a large GitHub account, the loading screen shows real,
continuously-updating progress through the slow stages, and the gap report is
visible before the 30-day plan finishes generating.

---

## v3.0+ — Ideas parking lot (not committed)

Only promote these to a real version if a user actually asks for them:

- Auto-scaffold suggested starter repos ("build plan → real repo skeleton")
- LinkedIn import alongside resume text
- Track resume/GitHub changes over time and re-score
- Team/consulting mode for SIGNAL (multiple resumes)
- Private-repo awareness (with the user's explicit token + consent)

---

## Anti-goals (things we deliberately will NOT do)

- No user accounts / auth system in v1.
- No PostgreSQL in v1 — SQLite is enough until there are real concurrent users.
- No "grade everyone's resume" generic mode — stay on the wedge.
- No web app before v1 proves the advice is worth installing anything for.
