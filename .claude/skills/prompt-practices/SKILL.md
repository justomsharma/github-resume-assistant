---
name: prompt-practices
description: Best practices for writing LLM prompts sent to the Anthropic API in this project. Use whenever you write, edit, or review a prompt that goes to Claude (e.g. claim extraction in clients/anthropic.py). Enforces grounded, structured, testable prompts that fit our clients/ layer.
---

# prompt-practices

**The rule: every prompt we send to Claude is code. Write it to be read, grounded,
and testable — never a vibe.**

When you write or change any prompt string that goes to the Anthropic API in this
project, follow this. It pairs with `docs/CODING_PRACTICES.md` (the API-clients and
model-id rules) and the `claude-api` skill (SDK usage, model ids, params).

## Where prompts live (non-negotiable)

- Prompts are assembled in **`clients/anthropic.py`**, one function per tool's prompt
  (ARCHITECTURE.md: clients own prompt assembly). `core/` never builds prompts.
- The **model id comes from `config.anthropic_model`**, never hardcoded in the prompt
  or the call.
- Keep the prompt text in a named module-level constant or a small builder function so
  a test can assert what we send.

## The seven rules for a good prompt here

1. **Assign a role + task in one line.** Start the system prompt with who Claude is and
   the single job. "You extract concrete, verifiable claims from an engineer's resume."
   One responsibility per prompt — mirror the "functions do one thing" rule.

2. **Ground every instruction in the real input.** Our whole moat is grounding in real
   data (PRODUCT.md). Tell Claude to use *only* the supplied resume/GitHub text and to
   never invent facts not present in the input.

3. **Separate instructions from data.** Put the user's resume text inside clear
   delimiters (XML tags like `<resume>...</resume>`), so injected text in the resume
   can't be read as instructions. Never string-concatenate user text into the middle of
   an instruction sentence.

4. **Demand structured output and specify the schema.** Ask for JSON matching an exact
   shape (field names, types), and say "return only the JSON, no prose." This is what
   `core/` parses into `Claim` dataclasses — the shape is a contract, so state it
   explicitly and keep it in sync with `core/models.py`.

5. **Handle the empty / thin case in the prompt itself.** Our real user has a near-empty
   resume or GitHub (PRODUCT.md). Tell Claude what to do when there's little to extract:
   return an empty list, not fabricated claims. Never let the prompt pressure Claude into
   inventing content to "find something."

6. **Constrain, don't ramble.** Prefer positive, specific instructions ("extract at most
   the 10 strongest claims, most concrete first") over vague ones ("be thorough"). Bound
   list sizes and lengths so output stays parseable and cheap.

7. **Give one short example of the output shape** (a tiny input→JSON pair) when the schema
   is non-trivial. One example beats three paragraphs of description. Keep it minimal.

## Prompt-writing checklist (before the prompt ships)

- [ ] Role + single task stated in the first line.
- [ ] User-supplied text is inside delimiters, never concatenated into instructions.
- [ ] Output schema stated exactly; "return only JSON" instructed.
- [ ] Schema matches the `core/models.py` dataclass it will be parsed into.
- [ ] Empty/thin-input behavior specified (return empty, never fabricate).
- [ ] List sizes / lengths bounded.
- [ ] Model id read from `config.anthropic_model`, not hardcoded.
- [ ] Prompt text is a named constant/builder a test can assert on.
- [ ] A test asserts the assembled prompt contains the key instructions + the input.

## Testing prompts (ties into docs/TESTING.md)

- The Anthropic SDK call is **always mocked** — never hit the real API in tests.
- Assert the **assembled prompt** contains the delimited user text and the schema
  instruction (rule 4/8 above) — this is how we verify prompt correctness offline.
- Assert we **parse a realistic model response** into the right dataclasses, and that a
  malformed / empty response degrades gracefully (no crash, sensible empty result).

## Handoff

This is a reference skill, not a chain step. After writing a prompt with it, continue
the normal chain (`/implement` → `/test` → ...). If the prompt is for a brand-new tool,
you should already have come through `/plan-first`.
