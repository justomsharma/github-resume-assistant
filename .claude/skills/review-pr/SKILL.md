---
name: review-pr
description: Review a pull request (MR) against project standards before merge, following docs/GIT_WORKFLOW.md. Use AFTER /open-pr, or any time to review a teammate's or your own PR. The final gate before code reaches main.
---

# review-pr

Review a PR before it merges. Follow `docs/GIT_WORKFLOW.md`. Review as a skeptic,
even on your own PR — it catches bugs and builds the exact habit that impresses
senior engineers.

## Get the diff

```bash
gh pr view <number>
gh pr diff <number>
```

## Review dimensions (in order)

1. **Correctness** — Does it do what the PR says? Trace edge cases, especially the
   empty-GitHub path. Any bug, missed branch, or wrong assumption?
2. **Scope** — Stays within one ROADMAP item? Any creep or unrelated changes?
3. **Practices** (CODING_PRACTICES.md) — Types, error handling, no secrets,
   `core/` free of MCP imports, no dead code?
4. **Tests** (TESTING.md) — Adequate coverage? External calls mocked? Empty-GitHub
   case tested where relevant?
5. **Clarity** — Could someone else maintain this in six months?

## Leave findings

- Specific and actionable: `file:line` + the problem + a suggested fix.
- Be direct and kind. Distinguish must-fix (correctness, secrets, tests) from nits.

## Decision

- **Request changes** if correctness, secrets, or tests fail → send the author back
  to `/plan-first` or `/implement` as appropriate.
- **Approve** only when correctness holds and tests pass.

## Merge

- Squash-merge to keep `main` history clean (GIT_WORKFLOW.md).
- Confirm the ROADMAP.md checkbox is ticked if the item is complete.

## Handoff

This is the end of the chain. After merge, the next unit of work starts fresh at
**`/plan-first`**.
