# Architecture: GitHub Resume Assistant

> How the code is structured and why. Read this before adding a file — put new
> code where the structure says it goes, not wherever is convenient.

## Guiding principle: keep the engine separate from the interface

Even though v1 only exposes an MCP server, we write the analysis logic so it does
**not** import anything MCP-specific. This costs almost nothing now and makes the
v2 web app a wrapper instead of a rewrite (see ROADMAP.md v2.0).

- **`core/`** = pure logic. Knows nothing about MCP. Testable without a server.
- **`server/`** = the MCP adapter. Thin. Translates tool calls into `core/` calls.
- **`clients/`** = talking to the outside world (GitHub API, Anthropic API).

## Folder layout (v1)

```
github-resume-assistant/
├── src/
│   └── resume_assistant/
│       ├── __init__.py
│       ├── server/
│       │   ├── __init__.py
│       │   └── app.py            # MCP server: registers the 3 tools, thin adapter
│       ├── core/
│       │   ├── __init__.py
│       │   ├── analysis.py       # analyze_resume logic (claims → gap report)
│       │   ├── suggestions.py    # suggest_projects logic (gap report → 30-day plan)
│       │   └── models.py         # dataclasses: Repo, Profile, Claim, Gap, Suggestion
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── github.py         # GitHub API client (fetch_github_repos data)
│       │   └── anthropic.py      # Anthropic API client (LLM calls)
│       ├── cache/
│       │   ├── __init__.py
│       │   └── store.py          # SQLite cache (added in v0.2)
│       └── config.py             # env var loading, settings
├── tests/                        # mirrors src/ structure (see TESTING.md)
├── docs/
├── .claude/skills/
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile                    # added in v1.0
└── README.md
```

## Module responsibilities (single responsibility per file)

| Module | Owns | Must NOT do |
|--------|------|-------------|
| `server/app.py` | Tool registration, schema definitions, calling `core/` | Business logic, API calls |
| `core/analysis.py` | Turning resume + repos into a gap report | Import MCP, hit network directly |
| `core/suggestions.py` | Turning a gap report into a ranked build plan | Import MCP, hit network directly |
| `clients/github.py` | GitHub HTTP calls, pagination, rate-limit handling | Business decisions |
| `clients/anthropic.py` | Anthropic HTTP calls, prompt assembly, retries | Business decisions |
| `cache/store.py` | Read/write cached results in SQLite | Business decisions |
| `config.py` | Load and validate env vars | Anything else |

## Data flow

```
Claude Desktop
   │  (MCP tool call)
   ▼
server/app.py  ──▶  clients/github.py  ──▶  GitHub API
   │                      │
   │                      ▼
   │              core/analysis.py  ──▶  clients/anthropic.py  ──▶  Anthropic API
   │                      │
   │                      ▼
   │              core/suggestions.py
   │                      │
   ▼                      ▼
 tool result  ◀──  cache/store.py (SQLite)
```

## Key rules

1. **`core/` imports only stdlib + `clients/` + `models`.** Never `mcp`.
2. **`clients/` return plain data** (dataclasses from `models.py`), never raw JSON dicts leaking upward.
3. **All secrets flow through `config.py`.** No `os.getenv` scattered in business logic.
4. **The MCP layer is dumb.** If `server/app.py` grows logic, that logic belongs in `core/`.
5. **One tool = one clear entry function in `core/`.** `fetch_github_repos` → `clients/github.py`; `analyze_resume` → `core/analysis.py`; `suggest_projects` → `core/suggestions.py`.

## Model / LLM choices

- Use the latest Claude models via the Anthropic API. Default to **`claude-sonnet-5`**
  for analysis; consider **`claude-opus-4-8`** for the nuanced `suggest_projects`
  reasoning if quality justifies the cost.
- Do NOT hardcode a model id in business logic — put it in `config.py` so it's swappable.
- (Note: there is no "Sonnet 4.6" — that was a typo in the original plan.)
