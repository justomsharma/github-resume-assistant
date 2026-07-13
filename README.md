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

## The web app (v2.0–v2.3 — no install)

The same engine, a second front door. Job-seekers don't install MCP servers, so
there's a **Next.js + TypeScript frontend** (`frontend/`) calling a **Flask JSON
API** (`resume_assistant/web/`) that's a thin adapter over the identical `core/`
logic (`build_gap_report` + `build_project_plan`) — upload your resume (PDF/DOCX),
type a GitHub username, and get the gap report + ranked 30-day plan. The
empty-GitHub case is the main case — it renders a build plan, not "nothing found".

As of v2.3 the UI and API are two separately-runnable, separately-deployable
processes; `core/` never imports Flask or knows the frontend exists.

Run both locally:

```bash
# Terminal 1 — the JSON API (after `pip install -e ".[dev]"` and setting
# ANTHROPIC_API_KEY, see below)
python -m resume_assistant.web.app
# serves http://127.0.0.1:5000/api/analyze

# Terminal 2 — the frontend
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL defaults to the API above
npm run dev
# open http://127.0.0.1:3000
```

`ANTHROPIC_API_KEY` is required; `GITHUB_TOKEN` is optional (a higher GitHub rate
limit); `FRONTEND_ORIGIN` (defaults to `http://127.0.0.1:3000`) scopes the API's
CORS to the frontend's origin — set it to your deployed frontend's URL in
production. Each claim is graded against your real repo code — parsed dependency
manifests, the recursive file tree, language breakdown, and README — and earns one
of three honest verdicts: **backed** (public code proves it, citing the specific
files), **not shown yet** (a gap to close), or **not verifiable from public code**
(claims like private/enterprise usage, traffic, or latency that public code
structurally can't prove).

> **Rate limits without a token.** Grounding reads each repo's code, so analysis
> makes several GitHub calls per repo. Unauthenticated, a profile with many repos
> can exhaust the rate limit — you'll get a friendly "set a `GITHUB_TOKEN`" message
> rather than a crash. Setting a token raises the limit dramatically.

### Deploying (free tiers)

Two services, deployed separately:

- **API** ([Render](https://render.com), free web service) — this repo includes
  `render.yaml`; connect the repo in the Render dashboard as a Blueprint, then set
  `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, and `FRONTEND_ORIGIN` (your Vercel URL) in
  its environment tab. Runs via `gunicorn`.
- **Frontend** ([Vercel](https://vercel.com), free tier) — import this repo, set
  the project's **Root Directory** to `frontend/`, and set `NEXT_PUBLIC_API_URL`
  to your Render URL. Vercel auto-detects Next.js; no extra config needed.

### Load & performance

- **Latency.** Grounding makes several sequential GitHub + Anthropic calls per
  repo (evidence fetch, then LLM-graded verdicts), so a full analysis can take
  tens of seconds — often longer on Render's free tier (0.1 CPU). Budget for
  it rather than expecting a snappy response.
- **Timeouts.** `render.yaml` runs gunicorn with `--timeout 120` because the
  default 30s is routinely exceeded under the free tier's CPU limits; without
  it gunicorn SIGKILLs the worker mid-request. `/api/analyze/stream` (SSE)
  exists so the frontend can show real progress instead of a blank spinner
  for that whole window.
- **Rate limits.** The API applies per-IP limits via `Flask-Limiter`: 10
  requests/hour on `/api/analyze` and `/api/analyze/stream` (the routes that
  burn GitHub + Anthropic quota), 60/hour by default elsewhere. Limits are
  tracked in-memory, which only holds because Render's free tier runs a
  single gunicorn worker — scaling to multiple workers would need a shared
  store (e.g. Redis) instead.

## Tech stack

- **Backend:** Python 3.11+ with the official `mcp` library; Flask (`flask-cors`)
  for the v2.3 JSON API
- **Frontend:** Next.js + TypeScript (App Router), plain CSS — no UI framework
- GitHub REST API (`requests`)
- Anthropic API (latest Claude models — `claude-sonnet-5` / `claude-opus-4-8`)
- SQLite for caching (from v0.2)
- pytest for backend testing, ruff + mypy for backend quality; ESLint + `tsc` for
  the frontend

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
