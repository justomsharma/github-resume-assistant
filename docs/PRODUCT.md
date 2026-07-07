# Product: GitHub Resume Assistant

> The single source of truth for *what* we are building and *why*.
> If a feature or line of code doesn't serve something in this doc, question it.

## One-line pitch

An MCP server that connects Claude to your real GitHub activity and tells you
**what to build and ship publicly to make your resume credible** — grounded in
your actual contribution history, not vibes.

## The problem (the real one)

Engineers improving their resume today paste it into ChatGPT and wing it.
ChatGPT can only critique the *words on the page* — it has no idea whether the
claims are true, and it can't see what you've actually built.

For the specific user we're building for (see below), the deeper problem is
different: their public GitHub is **too empty** to back up their resume, because
their real work lives in private company repos. A tool that just "grades your
resume against GitHub" would tell them their GitHub is empty — demoralizing and
useless. The valuable move is to **prescribe what to build next**.

## Target user (v1 = one person: the builder)

A **2–4 year engineer, often at a startup**, who:
- has strong real work, but most of it is in **private company repos**
- has a **thin or new public GitHub** (a portfolio site, a few repos)
- **doesn't know what's wrong with their resume** or how to make it credible
- reaches for ChatGPT copy-paste and gets generic advice

v1's only user is *you*. That is a feature, not a limitation — instant feedback,
zero user-research overhead, and the fastest path to knowing if the advice is
actually good.

## The wedge — what ChatGPT structurally cannot do

ChatGPT critiques words. This tool connects **real GitHub data → concrete,
buildable next steps**:

1. Read the resume's strongest claims.
2. Read the actual public GitHub reality.
3. Surface the **gap** — claims with no public evidence.
4. Prescribe a **ranked, shippable plan** to close the highest-value gaps.

That grounding in real repo data is the moat. It's the one thing a
copy-paste-into-ChatGPT workflow can't replicate.

## The three tools (reprioritized)

The original plan listed these in the wrong order. Corrected priority:

| Tool | Role in v1 | Why |
|------|-----------|-----|
| `fetch_github_repos()` | **Foundation** | Everything else needs real data: profile, repos, stars, languages, recency. |
| `suggest_projects()` | **The star** | The prescription. "Given your resume claims and empty-ish GitHub, build X, Y, Z this month." This is the heart of the product. |
| `analyze_resume(text)` | **Support** | The gap-finder feeding `suggest_projects`. On its own it's the weakest tool for our user, because their GitHub is thin. |

## What this is NOT (v1 scope guardrails)

- Not a general "resume grader" for everyone with a resume.
- Not a web app (that's a later version — see ROADMAP.md).
- Not a multi-user SaaS with accounts, billing, or a database of users.
- Not trying to beat ChatGPT at prose editing. We win on *grounded prescription*.

## The three goals this project serves

1. **Portfolio** — proves to AI-company engineers you can build a real MCP server.
2. **Learning MCP** — capability discovery, tool schemas, auth, real API integration.
3. **A real, useful tool** — starting with one user (you), earning the right to grow.

All three are served by shipping v1. Goals 1 and 2 need zero external users;
goal 3 is earned by proving the advice is good on yourself first.

## Success criteria for v1

- You can run it in Claude Desktop and get a resume gap report on **your own**
  resume + GitHub in under a minute.
- The `suggest_projects` output gives you at least **3 specific, shippable
  project ideas** you'd actually build, each tied to a real resume claim.
- You used it to change your own resume or GitHub at least once.
- The repo is public, documented, and something you'd link in an application.

## Competitor / status quo

| Option | Cost | Setup | Sees real GitHub? | Prescribes what to build? |
|--------|------|-------|-------------------|---------------------------|
| Paste into ChatGPT | Free | None | No | No |
| Hire resume consultant | $$$ | High | No | Rarely |
| **This tool** | Free | Install MCP server | **Yes** | **Yes** |

The bar to clear is "free ChatGPT copy-paste." We only win by doing what it can't.
