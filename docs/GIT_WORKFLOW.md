# Git Workflow: GitHub Resume Assistant

> How we branch, commit, push, and review. The `/commit-push`, `/open-pr`, and
> `/review-pr` skills enforce this. Note: "MR" (merge request) and "PR" (pull
> request) mean the same thing here; GitHub calls it a PR.

## Branching

- `main` is always shippable. Never commit directly to `main`.
- One branch per unit of work, named by type + short slug:
  - `feat/fetch-github-repos`
  - `fix/rate-limit-retry`
  - `chore/setup-ci`
  - `docs/readme-setup`
  - `test/analysis-edge-cases`

## Commits — Conventional Commits

Format: `type(scope): summary`

```
feat(server): add fetch_github_repos MCP tool
fix(github): handle pagination past 100 repos
test(core): cover empty-GitHub suggestion path
docs(readme): add Claude Desktop setup steps
chore(ci): add pytest GitHub Action
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`.

Rules:
- One logical change per commit. Don't mix a feature and a refactor.
- Summary in imperative mood, lowercase, no trailing period, ≤ 72 chars.
- Body (optional) explains *why*, not *what* — the diff shows what.
- **Never commit secrets.** `.env` stays git-ignored. Verify before every commit.

## The safe local sequence (what /commit-push does)

1. Confirm you're **not on `main`** (create a branch if you are).
2. `git status` + `git diff` — review what's actually staged.
3. Scan the diff for secrets / debug prints / leftover TODOs.
4. Stage intentionally — **never `git add -A` blindly**; add the files you meant to.
5. Commit with a Conventional Commit message.
6. `git push -u origin <branch>`.

## Opening a PR (what /open-pr does)

- Push the branch, then `gh pr create`.
- PR title = the main Conventional Commit summary.
- PR body uses this template:

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

- Keep PRs small — one ROADMAP item or less. Small PRs get reviewed well.

## Reviewing a PR (what /review-pr does)

Review against these, in order:
1. **Correctness** — does it do what the PR says? Any bug or missed edge case?
   (Especially: the empty-GitHub path.)
2. **Scope** — does it stay within one ROADMAP item? Any scope creep?
3. **Practices** — matches CODING_PRACTICES.md? Types, error handling, no secrets,
   `core/` free of MCP imports?
4. **Tests** — adequate per TESTING.md? External calls mocked?
5. **Clarity** — could someone else maintain this?

Leave specific, actionable comments (`file:line` + suggested fix). Approve only
when correctness and tests pass. Be direct and kind.

## Since this is a solo public repo (for now)

Even reviewing your own PRs is worth it — it catches bugs and it's the exact
habit that reads well to the engineers you're trying to impress. Open the PR,
run `/review-pr` on it, address findings, then merge. Squash-merge to keep
`main` history clean.
