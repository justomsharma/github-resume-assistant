# GitHub Resume Assistant

An MCP server that connects Claude to your real GitHub activity and tells you
**what to build and ship publicly to make your resume credible** — grounded in
your actual contribution history, not generic advice.

> Most resume tools critique the words on the page. This one looks at what you've
> actually built (and haven't), finds the gap between your resume's claims and your
> public GitHub, and prescribes a ranked plan of shippable projects to close it.

## Why it exists

Engineers improving their resume today paste it into ChatGPT and wing it. ChatGPT
can't see your real work and can't tell you what to build. This tool can — by
bridging Claude to the GitHub API. Full rationale in [`docs/PRODUCT.md`](docs/PRODUCT.md).

## The three tools

| Tool | What it does |
|------|--------------|
| `fetch_github_repos()` | Pulls your GitHub profile, repos, stars, languages, recency. |
| `analyze_resume(text)` | Finds which resume claims your public GitHub does / doesn't back up. |
| `suggest_projects()` | Prescribes a ranked 30-day plan of projects to prove your strongest claims. |

## Status

Early development. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what each version
includes. Currently building **v0.1 — walking skeleton**.

## Tech stack

- Python 3.11+ with the official `mcp` library
- GitHub REST API (`requests` / `aiohttp`)
- Anthropic API (latest Claude models — `claude-sonnet-5` / `claude-opus-4-8`)
- SQLite for caching (from v0.2)
- pytest for testing, ruff + mypy for quality

## Getting started (dev)

> Setup instructions get fleshed out as v0.1 lands. Rough shape:

```bash
# 1. Create and activate a virtualenv
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env      # then fill in GITHUB_TOKEN and ANTHROPIC_API_KEY

# 4. Run tests
pytest
```

Claude Desktop MCP config instructions land with v0.1.

## For contributors (and future you)

This repo is built with a strict, self-enforcing workflow. If you use Claude Code
here, it reads [`CLAUDE.md`](CLAUDE.md) and follows a skill chain:

```
/plan-first → /implement → /test → /self-review → /commit-push → /open-pr → /review-pr
```

The rule: **no code before the approach is validated.** See the docs:

- [`docs/PRODUCT.md`](docs/PRODUCT.md) — what we're building and why
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — versions and scope
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — code structure
- [`docs/CODING_PRACTICES.md`](docs/CODING_PRACTICES.md) — how we write code
- [`docs/TESTING.md`](docs/TESTING.md) — how we test
- [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md) — branching, commits, PRs

## License

MIT (add a LICENSE file before going public).
