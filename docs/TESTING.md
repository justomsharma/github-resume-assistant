# Testing: GitHub Resume Assistant

> How we test. The `/test` skill enforces this. No feature ships without tests.

## Framework

- **`pytest`** for everything.
- **`pytest-mock`** / `unittest.mock` for mocking external APIs.
- **`responses`** or `respx` for mocking HTTP calls (GitHub/Anthropic) if useful.
- **`pytest-cov`** for coverage.

## Structure — mirror `src/`

```
tests/
├── conftest.py                 # shared fixtures (fake profile, fake repos, fake resume)
├── core/
│   ├── test_analysis.py
│   └── test_suggestions.py
├── clients/
│   ├── test_github.py
│   └── test_anthropic.py
└── server/
    └── test_app.py
```

## The golden rule: never hit real APIs in tests

- **Always mock** GitHub and Anthropic. Tests must run offline, fast, and free.
- No real `GITHUB_TOKEN` / `ANTHROPIC_API_KEY` needed to run the suite.
- Put realistic fake data in `conftest.py` fixtures (a fake profile, a few fake
  repos with varied languages/stars/dates, a sample resume with strong + weak claims).

## What to test per layer

| Layer | Test focus |
|-------|-----------|
| `core/analysis.py` | Given fixture repos + resume, does it find the right supported/unsupported claims? Edge cases: empty GitHub, resume with no claims, all claims supported. |
| `core/suggestions.py` | Given a gap report, are suggestions ranked, tied to claims, and scoped? Edge case: empty GitHub → still gives buildable ideas. |
| `clients/github.py` | Pagination handled? Rate-limit path? 404 for missing user? (all mocked) |
| `clients/anthropic.py` | Prompt assembled correctly? Retry on transient error? (mocked) |
| `server/app.py` | Tools registered with correct schemas? Errors from `core/` become friendly messages? |

## Edge cases we specifically care about (from the product)

- **Empty / near-empty GitHub** — this is our real user. The tool must degrade
  gracefully and still produce a useful build plan, not "nothing found."
- **Resume with inflated claims** — the gap finder should catch unsupported claims.
- **API failure** — GitHub down, Anthropic rate-limited: friendly error, no crash.

## Running

```bash
pytest                    # run all
pytest --cov=src          # with coverage
pytest tests/core -v      # one layer
```

## Bar before shipping a version

- [ ] Every `core/` function has happy-path + at least one edge-case test.
- [ ] All external calls are mocked; suite runs with no network and no keys.
- [ ] Coverage on `core/` is meaningful (aim high — it's pure logic, easy to test).
- [ ] The "empty GitHub" scenario is explicitly tested.
- [ ] `pytest` green locally and in CI before opening a PR.
