# Roadmap: GitHub Resume Assistant

> Clear view of what each version includes. Build strictly in order.
> Do NOT pull work forward from a later version to "get ahead" — each version
> must earn the next by proving its value.

Legend: ✅ done · 🔨 in progress · ⬜ not started

---

## v0.1 — Walking skeleton (start here)

**Goal:** prove the MCP plumbing works end-to-end with one real tool.

- ⬜ Python project initialized with the `mcp` library
- ⬜ MCP server runs locally over stdio
- ⬜ `fetch_github_repos(username)` implemented against the real GitHub API
- ⬜ Registered and callable from **Claude Desktop**
- ⬜ Returns: profile summary, repo list, stars, primary languages, last-push dates

**Deliverable:** In Claude Desktop, "show me my GitHub repos" returns your real data.

**Definition of done:** you can see your own repos through Claude via the server.

---

## v0.2 — The gap finder

**Goal:** turn raw GitHub data into insight about the resume.

- ⬜ `analyze_resume(resume_text)` implemented
- ⬜ Extracts the strongest *claims* from the resume
- ⬜ Cross-references claims against `fetch_github_repos` output
- ⬜ Produces a **gap report**: which claims have public evidence, which don't
- ⬜ Uses the Anthropic API *inside the server* for the analysis
- ⬜ SQLite caching so repeated calls don't re-hit APIs

**Deliverable:** Claude can tell you which resume claims your GitHub does/doesn't back up.

---

## v0.3 — The prescription (the star tool)

**Goal:** the reason the product exists.

- ⬜ `suggest_projects()` implemented
- ⬜ Input: the gap report + GitHub reality + resume claims
- ⬜ Output: a **ranked 30-day plan** of specific, shippable projects
- ⬜ Each suggestion tied to a concrete resume claim it would prove
- ⬜ Each suggestion sized ("a weekend", "a week") and scoped (what to skip)

**Deliverable:** "Here are 3 things to build this month to make your resume credible."

**This is the v1 milestone. Ship it. Use it on yourself. Get feedback.**

---

## v1.0 — Production polish (shippable, public)

**Goal:** something you'd link in a job application.

- ⬜ Error handling + retry/backoff on GitHub and Anthropic calls
- ⬜ Rate-limit handling for the GitHub API
- ⬜ Config via env vars (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`)
- ⬜ Full README with setup + Claude Desktop config instructions
- ⬜ Test suite passing in CI (GitHub Actions)
- ⬜ Docker image builds
- ⬜ Public GitHub repo with docs and a short write-up

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
- ⬜ Add a **simple web app** over the same `core/` (for job-seekers, no install)
- ⬜ Web app: paste resume + enter GitHub username → gap report + build plan
- ⬜ Deploy (Railway / Render free tier)

**Deliverable:** same engine, two front doors — MCP for builders, web for everyone.

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
