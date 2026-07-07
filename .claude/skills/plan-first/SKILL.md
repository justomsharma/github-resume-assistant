---
name: plan-first
description: Entry point for ANY coding request on this project. Before writing a single line of code, read the existing code, form an approach, and validate it with the user. Use whenever the user asks to add, change, fix, or build something. Proactively invoke this instead of jumping straight to code.
---

# plan-first

**The rule this project lives by: never code before the approach is validated.**

When the user asks for anything that would change code, do NOT start editing.
Run this sequence first.

## Step 1 — Understand the request

Restate what the user is asking for in one sentence. If it's ambiguous, ask a
clarifying question before going further.

## Step 2 — Read the existing code FIRST

- Read `docs/PRODUCT.md`, `docs/ROADMAP.md`, and `docs/ARCHITECTURE.md` to ground
  yourself in what we're building and where code belongs.
- Use Glob/Grep/Read to find the files this change touches. Read them.
- Identify existing patterns, utilities, and models you should reuse instead of
  reinventing. Note where the new code belongs per ARCHITECTURE.md.

## Step 3 — Check it against the roadmap

- Which ROADMAP.md item is this? If it's not on the roadmap, flag it: is this
  scope creep, or should the roadmap be updated first?
- Confirm we're building versions in order (don't pull v2 work into v1).

## Step 4 — Form 1–2 approaches

For the chosen work, write a short approach:
- What files change / get created (mapped to ARCHITECTURE.md layout).
- Key decisions (data shapes, where logic lives, `core/` vs `server/` vs `clients/`).
- Edge cases to handle (especially the empty-GitHub case).
- What tests will prove it works (per TESTING.md).

If there's a real fork in the road, present 2 approaches with tradeoffs.

## Step 5 — Validate with the user (STOP here)

Present the approach and **wait for approval**. Use AskUserQuestion if there's a
real choice. Do not write code until the user confirms the approach.

## Handoff

Once the user approves the approach → hand off to **`/implement`**.
Pass along: the approved approach, the files to touch, and the test plan.
