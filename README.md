# GitHub Resume Assistant

[![CI](https://github.com/justomsharma/github-resume-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/justomsharma/github-resume-assistant/actions/workflows/ci.yml)

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

**v1.0 — shipped.** All three tools work end-to-end, and the repo is production-
polished: retry/backoff and rate-limit handling on the GitHub API, config via env
vars, a test suite passing in CI (ruff + mypy + pytest), and a Docker image that
builds. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what each version includes and
[`docs/WRITEUP.md`](docs/WRITEUP.md) for the short story of why it's built this way.

Shipped: **v0.1** walking skeleton (`fetch_github_repos`), **v0.2** the gap finder
(`analyze_resume`), **v0.3** the prescription (`suggest_projects`), and **v1.0**
production polish.

## What `analyze_resume` does (v0.2)

Given your resume text and a GitHub username, it:

1. Extracts the strongest, most concrete claims from the resume (via Claude).
2. Cross-references each claim against your real public repositories.
3. Returns a **gap report** — which claims have public GitHub evidence and which
   are gaps to close.

If your public GitHub is empty or thin — the common case when your real work
lives in private company repos — it degrades gracefully and frames every claim
as a gap to close, never "nothing found".

Results are cached in SQLite so re-analyzing the same resume doesn't re-hit the
Anthropic API. In Claude Desktop, ask: **"analyze my resume against my GitHub"**
and paste your resume + username.

## What `suggest_projects` does (v0.3 — the star tool)

Given your resume text and a GitHub username, it builds the same gap report as
`analyze_resume`, then **prescribes what to build next**:

1. Reuses the gap report (which claims your public GitHub does / doesn't back up).
2. Asks Claude for candidate shippable projects grounded in that report.
3. Ranks them in pure `core/` — **gaps first, quicker wins earlier** — into a
   **30-day plan**.

Each suggestion is tied to a concrete resume claim it would prove, sized
("a weekend" / "a week"), and scoped (what to deliberately skip so it ships). The
empty-GitHub case is the main case: instead of "nothing to show", it prescribes
starter projects that build public credibility from scratch. Candidates are cached
in SQLite so re-running the same gap report doesn't re-hit the Anthropic API.

In Claude Desktop, ask: **"what should I build to make my resume credible?"** and
paste your resume + username.

## Tech stack

- Python 3.11+ with the official `mcp` library
- GitHub REST API (`requests`)
- Anthropic API (latest Claude models — `claude-sonnet-5` / `claude-opus-4-8`)
- SQLite for caching (from v0.2)
- pytest for testing, ruff + mypy for quality

## Getting started (dev)

```bash
# 1. Create and activate a virtualenv
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)

# 2. Install the package with dev/test extras
pip install -e ".[dev]"

# 3. Configure secrets (see note below)
cp .env.example .env      # GITHUB_TOKEN optional; ANTHROPIC_API_KEY required for analyze_resume

# 4. Run tests
pytest
```

> **`GITHUB_TOKEN` is optional.** The GitHub REST API works unauthenticated, just
> with a lower rate limit. Set a token (a fine-grained token with public read
> access is enough) to avoid hitting that limit.
>
> **`ANTHROPIC_API_KEY` is required for `analyze_resume`.** `ANTHROPIC_MODEL`
> defaults to `claude-sonnet-5` (swappable). `CACHE_PATH` is optional — the SQLite
> cache defaults to `./.cache/resume_assistant.db`.

## Registering the server in Claude Desktop

The server speaks MCP over stdio. Add it to your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "github-resume-assistant": {
      "command": "/absolute/path/to/.venv/bin/resume-assistant",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "ANTHROPIC_API_KEY": "your_anthropic_key_here"
      }
    }
  }
}
```

`resume-assistant` is the console script installed by `pip install -e ".[dev]"`.
On Windows the path is `...\.venv\Scripts\resume-assistant.exe`. If you'd rather
not rely on the script, use your interpreter directly instead:

```jsonc
{
  "mcpServers": {
    "github-resume-assistant": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "resume_assistant.server.app"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "ANTHROPIC_API_KEY": "your_anthropic_key_here"
      }
    }
  }
}
```

Fully quit and reopen Claude Desktop, then ask: **"show me the GitHub repos for
octocat"** — Claude will call `fetch_github_repos` and return the real data.

## Run with Docker

Prefer not to manage a local Python environment? Build the image and run the
server in a container. Secrets are passed at runtime — never baked into the image.

```bash
# Build
docker build -t resume-assistant .

# Run (the server speaks MCP over stdio, so keep STDIN open with -i)
docker run -i --rm \
  -e GITHUB_TOKEN=your_github_token_here \
  -e ANTHROPIC_API_KEY=your_anthropic_key_here \
  resume-assistant
```

> The SQLite cache lives inside the container and is discarded when it exits
> (`--rm`). To persist it across runs, mount a volume and point `CACHE_PATH` at
> it, e.g. `-v resume-cache:/app/.cache -e CACHE_PATH=/app/.cache/resume.db`.

To use the container from Claude Desktop, set the command to `docker`:

```jsonc
{
  "mcpServers": {
    "github-resume-assistant": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_TOKEN",
        "-e", "ANTHROPIC_API_KEY",
        "resume-assistant"
      ],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "ANTHROPIC_API_KEY": "your_anthropic_key_here"
      }
    }
  }
}
```

Passing `-e GITHUB_TOKEN` (no `=value`) forwards the variable from the `env`
block above into the container, keeping the token out of the args list.

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

MIT — see [`LICENSE`](LICENSE).
