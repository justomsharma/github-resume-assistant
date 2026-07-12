# CLAUDE.md — GitHub Resume Assistant

Read this at the start of every session. It tells you what we're building, the
rules to follow, and which skill to use when.

## What this project is

An MCP server that connects Claude to a user's real GitHub activity and prescribes
**what to build and ship publicly to make their resume credible**. The full spec is
in `docs/PRODUCT.md`. Read it before making product decisions.

Key facts to internalize:
- **v1's only user is the builder (you).** Not "everyone with a resume."
- **`suggest_projects` is the heart** of the product; `analyze_resume` supports it.
- **The competitor is free ChatGPT copy-paste.** We only win by grounding advice
  in real GitHub data.
- **The empty-GitHub case is the main case**, not an edge case — handle it everywhere.

## Documentation map (read the relevant one before acting)

| Doc | When to read |
|-----|--------------|
| `docs/PRODUCT.md` | Any product/scope decision |
| `docs/ROADMAP.md` | Deciding what to build next; check version order |
| `docs/ARCHITECTURE.md` | Before creating/moving any file |
| `docs/CODING_PRACTICES.md` | Before/while writing code |
| `docs/TESTING.md` | Before/while writing tests |
| `docs/GIT_WORKFLOW.md` | Committing, pushing, PRs |

## The golden rule

**Never write code before an approach is read, formed, and validated.** Every
coding request starts at `/plan-first`. No exceptions.

## Skill routing — which skill, when

When the user's request matches a skill below, invoke it via the Skill tool. When
in doubt on a coding task, start with `/plan-first`.

| Situation | Skill |
|-----------|-------|
| User asks to add / change / fix / build anything | `/plan-first` |
| An approach was just approved, time to write code | `/implement` |
| Code was written, needs tests | `/test` |
| Tests pass, review the diff before committing | `/self-review` |
| Diff is clean, commit and push | `/commit-push` |
| Branch pushed, open the PR/MR | `/open-pr` |
| Review a PR/MR before merge | `/review-pr` |

## How the skills connect (the chain)

Each skill hands off to the next. This is the standard path for any change:

```
/plan-first  →  /implement  →  /test  →  /self-review  →  /commit-push  →  /open-pr  →  /review-pr  →  (merge)
   read code      write code    pytest    review diff      commit +        create      review it
   + validate     to the docs   + mock    for bugs &       push to a       the PR       before
   approach                     APIs      secrets          branch          w/ template  merge
```

Rules for the chain:
- **Always enter at `/plan-first`** for anything that changes code.
- A skill may **send you backwards**: if `/test`, `/self-review`, or `/review-pr`
  finds the approach was wrong, return to `/plan-first` — don't patch forward blindly.
- Don't skip `/plan-first` or `/self-review`. Those two gates are the whole point.
- **STOP after `/test`.** When local changes are made and tests pass, report the
  results and let the user test locally. Do NOT auto-proceed to `/commit-push`,
  `/open-pr`, `/review-pr`, or merge — those run **only when the user explicitly
  says so** ("commit and push", "raise the MR").
- After a merge, the next unit of work starts fresh at `/plan-first`.

## Non-negotiables

- No secrets in code or commits. `.env` is git-ignored; use `config.py`.
- `core/` never imports MCP.
- Build roadmap versions in order; don't pull v2 work into v1.
- Every feature ships with tests; external APIs are always mocked in tests.
