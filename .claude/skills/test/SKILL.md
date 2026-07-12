---
name: test
description: Write and run pytest tests for code just implemented on this project, following docs/TESTING.md. Mocks all external APIs. Use AFTER /implement. Blocks the pipeline until tests pass.
---

# test

Add tests for the code from `/implement` and make the suite green. Follow
`docs/TESTING.md`.

## Write tests

- Mirror `src/` structure under `tests/`.
- **Mock all external APIs** (GitHub, Anthropic). Never hit the network. No real
  keys required to run the suite.
- Use / extend fixtures in `conftest.py` (fake profile, fake repos, sample resume).
- Cover, per TESTING.md:
  - Happy path for the new code.
  - At least one edge case.
  - The **empty / near-empty GitHub** case if this touches analysis or suggestions —
    this is our real user and must degrade gracefully.

## Run

```bash
pytest --cov=src
```

- If tests fail, fix the code or the test (whichever is wrong) and re-run.
- If a failure reveals the approach was flawed, STOP and return to `/plan-first`.

## Bar to pass

- [ ] New code has happy-path + edge-case tests
- [ ] All external calls mocked; suite runs offline with no keys
- [ ] Empty-GitHub path tested (if relevant)
- [ ] `pytest` green

## Handoff — STOP and wait for the user

Once tests pass, **STOP**. Do NOT automatically proceed to `/self-review`,
`/commit-push`, `/open-pr`, `/review-pr`, or merge.

- Report what changed and the local test results, then say the changes are ready
  to test locally and ask the user to verify.
- Only continue to commit, push, open the MR/PR, review it, or merge **when the
  user explicitly tells you to** (e.g. "commit and push", "raise the MR").
- Until that explicit go-ahead, keep all changes local and uncommitted.
