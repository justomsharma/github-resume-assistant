---
name: commit-push
description: Safely commit reviewed changes with a Conventional Commit message and push to a feature branch, following docs/GIT_WORKFLOW.md. Use AFTER /self-review. Never commits to main, never blind-adds, never commits secrets.
---

# commit-push

Commit and push the reviewed changes. Follow `docs/GIT_WORKFLOW.md`.

## Safe sequence

1. **Branch check** — confirm you are NOT on `main`. If you are, create a branch:
   `git checkout -b <type>/<slug>` (e.g. `feat/fetch-github-repos`).
2. `git status` and `git diff` — confirm what will be committed.
3. **Secret scan** — one more look; abort if any key/credential is present.
4. **Stage intentionally** — add the specific files you meant to change.
   NEVER `git add -A` blindly. `.env` must never be staged.
5. **Commit** with a Conventional Commit message:
   `type(scope): imperative summary` (≤72 chars, lowercase, no trailing period).
   Add a body explaining *why* only if non-obvious.
6. **Push**: `git push -u origin <branch>`.

## Guardrails

- One logical change per commit. Split unrelated changes.
- Only commit when tests are green (from `/test`) and the diff is reviewed
  (from `/self-review`).
- If this completes a ROADMAP.md item, note it — `/open-pr` will check it off.

## Handoff

Once pushed → hand off to **`/open-pr`** to open the pull request.
