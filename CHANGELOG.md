# Changelog

All notable changes to this project, grouped by the version they belong to in
[`docs/ROADMAP.md`](docs/ROADMAP.md). Reconstructed retroactively from merged
PRs — dates are PR merge dates.

## [Unreleased] — v2.4 / v2.5 in progress

Frontend maturity pass and perceived-performance work, interleaved across PRs
#18–27. Not tagged yet: ROADMAP.md still lists open items under v2.4 (a
settings/history view, a real state-management story).

- #27 `feat(frontend)`: axe a11y regression tests and Lighthouse audit
- #26 `feat(frontend,backend)`: progressive results, empty/error states, streaming reliability
- #25 `chore(backend)`: CI coverage gate, API rate limiting, perf notes
- #24 `feat(frontend)`: wire up Download Report and Share Report buttons
- #23 `feat(frontend)`: redesign analysis progress screen with real 5-stage steps
- #22 `feat(frontend)`: redesign results page as a violet sidebar dashboard
- #21 `chore(skills)`: gate commit/push/MR/merge behind explicit user go-ahead
- #20 `fix(clients)`: salvage truncated claims and suggestions responses
- #19 `fix(clients)`: salvage truncated verdict responses instead of crashing
- #18 `feat(web,frontend)`: stream real per-stage analysis progress

## [v2.3] — 2026-07-09

Next.js frontend + JSON API split.

- #17 `fix(deploy)`: raise gunicorn's request timeout for `/api/analyze`
- #16 `feat(web,frontend)`: migrate to Next.js + TypeScript frontend over a Flask JSON API

## [v2.2] — 2026-07-09

Web upload + premium landing.

- #14 `feat(web)`: premium landing redesign + PDF/DOCX resume upload

(#13 and #15 covered the same ground and were closed unmerged in favor of #14.)

## [v2.1] — 2026-07-07

Grounded match fidelity — replaces the token matcher with an LLM-graded,
evidence-citing verdict (`backed` / `not_shown` / `not_verifiable`).

- #12 `feat(analysis)`: ground the backed verdict in real repo code

## [v2.0] — 2026-07-07

Two faces on one engine: a no-install web app over the same `core/`.

- #11 `style(web)`: apply ruff format to satisfy CI format check
- #10 `docs(readme)`: add module fallback for running the web app
- #9 `feat(web)`: add v2.0 no-install web app over the same core engine

## [v1.0] — 2026-07-07

Production polish — the first shippable, public version.

- #8 `docs`: polish README and add write-up for the v1.0 release
- #7 `chore(docker)`: add Dockerfile and verify the build in CI
- #6 `feat(github)`: respect rate-limit signals with backoff and retry
- #5 `chore(ci)`: add GitHub Actions running ruff, mypy, and pytest
- #4 `fix(anthropic)`: stop truncating `suggest_projects` JSON responses

## [v0.3] — 2026-07-07

The prescription — `suggest_projects()`, the star tool.

- #3 `feat(server)`: add `suggest_projects` 30-day build plan (v0.3)

## [v0.2] — 2026-07-07

The gap finder — `analyze_resume()`.

- #2 `feat(server)`: add `analyze_resume` gap finder (v0.2)

## [v0.1] — 2026-07-07

Walking skeleton — MCP plumbing works end-to-end with one real tool.

- #1 `feat(server)`: v0.1 walking skeleton with `fetch_github_repos`
