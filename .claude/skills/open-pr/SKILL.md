---
name: open-pr
description: Open a pull request (a.k.a. MR) for a pushed branch using the project PR template, following docs/GIT_WORKFLOW.md. Use AFTER /commit-push. Keeps PRs small and well-described.
---

# open-pr

Open a pull request for the pushed branch. Follow `docs/GIT_WORKFLOW.md`.

## Steps

1. Confirm the branch is pushed (`git push` done in `/commit-push`).
2. Create the PR with the GitHub CLI:
   ```bash
   gh pr create --title "<Conventional Commit summary>" --body "<template below>"
   ```
3. Fill the PR body with the project template:

```markdown
## What
<one paragraph: what this PR does>

## Why
<link to the ROADMAP item or the reason>

## How
<key implementation choices a reviewer should know>

## Testing
<what tests were added; how you verified it works>

## Checklist
- [ ] Tests pass locally (`pytest`)
- [ ] `ruff` + `mypy` clean
- [ ] No secrets in the diff
- [ ] Docs updated if behavior changed
- [ ] ROADMAP.md item checked off if completed
```

## Guardrails

- Keep PRs small — one ROADMAP item or less. If the branch does more, say so and
  consider splitting.
- Title = the main Conventional Commit summary.
- If this completes a ROADMAP.md item, update the checkbox in `docs/ROADMAP.md`
  in the same PR.

## Handoff

Once the PR is open → hand off to **`/review-pr`** to review it before merging
(yes, review your own PR — see GIT_WORKFLOW.md).
