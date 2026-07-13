# Accessibility & Responsive Audit (v2.4)

> Point-in-time findings for the two closing v2.4 items: "Responsive design pass
> + Lighthouse score" and "Accessibility audit (axe/Lighthouse a11y pass)".
> Regenerate the Lighthouse numbers when the frontend changes materially: in
> `frontend/`, run `npm run build && npm run start` in one terminal, then
> `npm run audit:lighthouse` in another once it's serving on `:3000`. The axe
> checks below run on every `npm test`.

## Tooling

- **axe-core via `vitest-axe`** — runs inside the existing Vitest + jsdom
  component tests, one `"has no axe violations"` case per ARIA-bearing
  component. These are permanent regression tests (fail CI on a real
  violation), not a one-off report.
- **Lighthouse** (`npx lighthouse`) — run once, manually, against a production
  build (`next build && next start`) on `2026-07-14`. Not wired into CI; the
  project's CI gate today is backend-coverage only (see CLAUDE.md).

## Lighthouse scores — 2026-07-14

Audited `http://localhost:3000` (the landing page — the only statically
reachable route; the in-progress and dashboard views are client-rendered
state, covered instead by the axe component tests below).

| Category | Desktop | Mobile (simulated throttling) |
|---|---|---|
| Performance | 100 | 97 |
| Accessibility | 100 | 100 |
| Best Practices | 100 | 100 |
| SEO | 100 | 100 |

The mobile Performance score (97) is pulled down by Largest Contentful Paint
(2.6s under simulated mobile throttling, score 0.88/1) — inherent to the
Next.js JS bundle under 4x CPU/network throttling, not a regression from a
specific component. No action taken; not worth chasing for a 3-point synthetic
score on a project this size.

## Axe findings and fixes

One real violation was found and fixed:

- **`AnalysisProgress.tsx`** — the `role="progressbar"` step-list had no
  accessible name (`aria-progressbar-name`, a WCAG 4.1.2 failure). Fixed by
  adding `aria-label="Analysis progress"`.

No other violations were found across `ErrorBanner`, `EmptyState`,
`AnalysisDashboard` (both the normal and empty-GitHub report states), and
`LandingForm`. The existing `role="tablist"`/`role="tab"`/`aria-selected`
wiring in `AnalysisDashboard` and the `role="alert"` / decorative
`aria-hidden` usage elsewhere all passed axe clean.

## Responsive pass

`globals.css` breakpoints (860px / 900px / 720px / 520px) were reviewed
against the Lighthouse mobile run and manual inspection — no real layout
break was found at any of them, so the existing ad-hoc scale was left as-is
rather than rewritten speculatively.
