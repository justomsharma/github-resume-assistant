# Write-up: GitHub Resume Assistant

A short account of what this is, why I built it this way, and what it taught me
about the Model Context Protocol (MCP).

## The problem

Engineers improving their resume paste it into ChatGPT and wing it. ChatGPT can
only critique the *words on the page* — it can't see what you've actually built,
so it can't tell whether a claim is true or what you should build next.

For the engineer I built this for — 2–4 years in, strong real work but most of it
locked in **private company repos** — the problem is sharper: their *public*
GitHub is too thin to back up their resume. A tool that merely "grades your resume
against GitHub" would just tell them their GitHub is empty. Demoralizing and
useless. The valuable move is to **prescribe what to build next.**

## The wedge

The one thing a copy-paste-into-ChatGPT workflow structurally cannot do is read
your real GitHub. So the whole product is built around that grounding:

1. Read the resume's strongest, most concrete claims.
2. Read the actual public GitHub reality (repos, languages, stars, recency).
3. Surface the **gap** — claims with no public evidence.
4. Prescribe a **ranked, shippable 30-day plan** to close the highest-value gaps.

The grounding in real repo data is the moat. Everything else serves it.

## The three tools

| Tool | Role | What it does |
|------|------|--------------|
| `fetch_github_repos()` | Foundation | Pulls profile, repos, stars, languages, recency from the real GitHub API. |
| `analyze_resume()` | Support | Extracts resume claims (via Claude) and cross-references them against real repos → a gap report. |
| `suggest_projects()` | **The star** | Turns the gap report into a ranked plan of specific, shippable projects, each tied to a claim it would prove. |

The **empty-GitHub case is the main case**, not an edge case: instead of "nothing
to show", the tools frame every claim as a gap and prescribe starter projects that
build public credibility from scratch.

## Architecture — engine separate from interface

The analysis logic never imports anything MCP-specific. That cost almost nothing
now and keeps a future web front-end a wrapper rather than a rewrite.

- **`core/`** — pure logic (gap analysis, suggestion ranking). No MCP, no network.
- **`clients/`** — the outside world: GitHub REST (pagination, retry/backoff,
  rate-limit handling) and Anthropic (prompt assembly, retries).
- **`server/`** — a thin MCP adapter: validate input → call `core/` → format output.
- **`cache/`** — SQLite so repeated analyses don't re-hit paid APIs.
- **`config.py`** — the single place secrets and settings load from env vars.

## What building it taught me about MCP

- **Tool descriptions are a prompt.** Claude decides *when* to call a tool from its
  name and description, so they're written for a reader, stating what the tool does
  and when to use it — not just typed signatures.
- **Keep the MCP layer dumb.** Every time logic tried to creep into `server/app.py`,
  it belonged in `core/`. The adapter only translates and formats.
- **Grounding beats fluency.** The LLM is prompted to use *only* the provided GitHub
  facts and never fabricate claims or projects — the value is in the real data, not
  the model's imagination.
- **Real APIs fail.** Rate limits, transient 5xx, and secondary limits are normal, so
  the clients retry with backoff and surface friendly, typed errors instead of stack
  traces through a tool call.

## Honest v1 scope and limits

- **v1's only user is me.** That's a feature: instant feedback, zero user-research
  overhead, and the fastest path to knowing if the advice is actually good.
- No accounts, no auth, no multi-user database — SQLite is enough.
- No web app yet. Job-seekers don't install MCP servers; engineers do. A no-install
  web surface is the v2 bet, and only earns its place once v1 proves the advice is
  worth installing anything for.
- Only public GitHub and pasted resume text — no private-repo or LinkedIn awareness.

See [`ROADMAP.md`](ROADMAP.md) for what each version includes and
[`PRODUCT.md`](PRODUCT.md) for the full rationale.
