---
name: self-review
description: Review the current local diff for bugs, scope creep, leaked secrets, and practice violations before anything is committed. Use AFTER /test passes and BEFORE /commit-push. The last gate before code leaves your machine.
---

# self-review

Review the working diff like a skeptical reviewer who did NOT write it. This is the
last check before committing.

## Look at the actual diff

```bash
git status
git diff
```

## Review checklist (in order)

1. **Correctness** — Does it do what was intended? Trace the logic. Any off-by-one,
   null case, or missed branch? Especially: the empty-GitHub path.
2. **Secrets** — Scan every changed line. No `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`,
   or any key/credential. `.env` must not be staged.
3. **Scope** — Only the intended files changed? No stray edits, no scope creep
   beyond the approved `/plan-first` approach or the ROADMAP item?
4. **Practices** (CODING_PRACTICES.md) — Types present? Error handling on external
   calls? `core/` free of MCP imports? No bare `except`, no dead code, no debug prints?
5. **Tests** (TESTING.md) — Are the changes actually covered? External calls mocked?

## Outcome

- If issues found: fix them now (or return to `/implement` / `/plan-first` if the
  problem is deeper), then re-review.
- If clean: summarize what changed in 2–3 lines for the commit/PR.

## Handoff

Once the diff is clean → hand off to **`/commit-push`**.
