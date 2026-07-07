# Coding Practices: GitHub Resume Assistant

> The standards Claude Code and you follow when writing code here.
> The `/implement` skill enforces these.

## Language & tooling

- **Python 3.11+**.
- **Type hints everywhere.** Every function signature is fully typed.
- **`ruff`** for lint + format. **`mypy`** for type checking. Both must pass before commit.
- Prefer **dataclasses** (or Pydantic if validation is needed) over loose dicts.

## Style

- Functions do one thing. If a function needs a comment to explain a second
  responsibility, split it.
- Names say what, not how: `find_unsupported_claims()` not `process_data2()`.
- Match the style of surrounding code. Consistency beats personal preference.
- No dead code, no commented-out blocks left behind. Delete it — git remembers.

## Error handling

- **Never swallow exceptions silently.** No bare `except:`.
- Wrap external calls (GitHub, Anthropic) in specific error handling that returns
  a useful message. A user should never see a raw stack trace through an MCP tool.
- Fail loud in `core/` (raise typed errors); translate to friendly messages only at
  the `server/` boundary.
- Add **retry with backoff** for transient network/API errors (see `clients/`).

## Secrets & config (critical — this is a public repo)

- **Never hardcode** `GITHUB_TOKEN` or `ANTHROPIC_API_KEY`. Ever.
- All secrets load from env vars via `config.py`.
- `.env` is git-ignored. `.env.example` (with placeholder values) is committed.
- Before every commit, the `/self-review` skill checks the diff for leaked secrets.

## MCP-specific patterns

- Each tool has a **clear, descriptive schema**: name, description, typed params.
  Claude uses these to decide when to call the tool — write them for a reader.
- Tool descriptions state **what the tool does and when to use it**, in plain English.
- Keep tool functions thin: validate input → call `core/` → format output. No logic.
- Return structured, readable output (not raw API JSON dumps).

## API clients

- GitHub: handle **pagination** and **rate limits** (check `X-RateLimit-Remaining`).
- Anthropic: assemble prompts in one place per tool; keep model id in `config.py`.
- Both clients return typed models from `models.py`, never raw responses.
- Cache expensive results (SQLite) so re-runs during dev don't burn API quota.

## Comments & docs

- Docstring every public function: one line on what, note non-obvious behavior.
- Comment the *why*, not the *what*. `# GitHub caps at 100 per page` is useful;
  `# loop over repos` is noise.

## Definition of "good code" here

Before code is considered done:
- [ ] Fully type-hinted
- [ ] `ruff` and `mypy` clean
- [ ] No secrets, no bare excepts, no dead code
- [ ] `core/` has no MCP imports
- [ ] Has tests (see TESTING.md)
- [ ] External calls have error handling + retries
