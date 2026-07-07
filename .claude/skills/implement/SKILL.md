---
name: implement
description: Write code for an already-validated approach on this project, following docs/CODING_PRACTICES.md and docs/ARCHITECTURE.md. Use only AFTER /plan-first has produced an approved approach. Do not use to design or decide — only to build what was agreed.
---

# implement

Build the code for the approach approved in `/plan-first`. If no approach has been
validated yet, STOP and run `/plan-first` first.

## Before writing

- Re-read the relevant parts of `docs/ARCHITECTURE.md` (where code goes) and
  `docs/CODING_PRACTICES.md` (how code is written).
- Confirm the target files match the approved plan.

## While writing

Follow CODING_PRACTICES.md strictly:
- Full type hints on every function.
- Keep `core/` free of MCP imports — pure logic only.
- Secrets only through `config.py`; never hardcode keys.
- Specific error handling on external calls; add retry/backoff in `clients/`.
- Reuse existing models in `core/models.py`; add to them rather than duplicating.
- Keep MCP tool functions thin: validate → call `core/` → format output.
- Match surrounding style. No dead code, no leftover debug prints.

## Scope discipline

- Build only what the approved approach covered. If you discover the plan was
  wrong or incomplete, STOP and go back to `/plan-first` — don't silently expand scope.

## Self-check before handing off

- [ ] Code matches the approved approach
- [ ] Fully typed; would pass `ruff` and `mypy`
- [ ] No secrets, no bare `except`, no dead code
- [ ] `core/` has no MCP imports
- [ ] New logic lives in the layer ARCHITECTURE.md assigns it to

## Handoff

Once the code is written → hand off to **`/test`** to add and run tests.
Do NOT commit yet.
