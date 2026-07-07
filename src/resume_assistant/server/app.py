"""MCP server exposing the resume-assistant tools over stdio.

The MCP layer is intentionally dumb (docs/ARCHITECTURE.md, rule 4): each tool
validates input, calls a client/core function, and formats readable output.
Business logic and HTTP live elsewhere. v0.1 registers only ``fetch_github_repos``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from resume_assistant.cache.store import (
    CachingClaimExtractor,
    CachingClaimVerifier,
    CachingRepoEvidenceFetcher,
    CachingSuggestionGenerator,
    SqliteCache,
)
from resume_assistant.clients.anthropic import AnthropicClient, AnthropicError
from resume_assistant.clients.github import (
    GitHubClient,
    GitHubError,
    RateLimitError,
    UserNotFoundError,
)
from resume_assistant.config import load_config
from resume_assistant.core.analysis import build_gap_report
from resume_assistant.core.models import (
    ClaimEvidence,
    GapReport,
    Profile,
    ProjectPlan,
    Repo,
    Suggestion,
)
from resume_assistant.core.suggestions import build_project_plan

mcp = FastMCP("github-resume-assistant")

# Grounding claims reads each repo's code (tree, manifests, languages, README), so
# analysis makes several GitHub calls per repo. Unauthenticated, that can exhaust
# the rate limit on a profile with many repos — hence the explicit token hint.
_RATE_LIMIT_MESSAGE = (
    "GitHub's API rate limit is exhausted. Grounding claims reads each repo's code, "
    "which is call-heavy — set a GITHUB_TOKEN in your environment for a much higher "
    "limit, then try again."
)


@mcp.tool()
def fetch_github_repos(username: str) -> str:
    """Fetch a GitHub user's public profile and repositories.

    Use this to ground resume advice in someone's real GitHub activity: it
    returns their profile summary plus every public repo with stars, primary
    language, and creation / last-push dates. Handles users with no public
    repositories gracefully.

    Args:
        username: The GitHub login to look up (e.g. "octocat").
    """
    username = username.strip()
    if not username:
        return "Please provide a GitHub username."

    config = load_config()
    client = GitHubClient(token=config.github_token)
    try:
        profile = client.fetch_profile(username)
    except UserNotFoundError:
        return f"No GitHub user found with the username '{username}'."
    except RateLimitError:
        return (
            "GitHub's API rate limit is exhausted. Set a GITHUB_TOKEN in your "
            "environment for a much higher limit, then try again."
        )
    except GitHubError as exc:
        return f"Couldn't fetch GitHub data right now: {exc}"

    return format_profile(profile)


@mcp.tool()
def analyze_resume(resume_text: str, username: str) -> str:
    """Find which resume claims a GitHub profile does and doesn't back up.

    Extracts the strongest, most concrete claims from the resume, cross-references
    them against the user's real public repositories, and returns a gap report:
    which claims have public GitHub evidence and which are gaps to close. Handles
    an empty or thin GitHub gracefully — that's the common case for engineers whose
    work lives in private repos, and the report frames it as the gap to close.

    Args:
        resume_text: The full text of the resume to analyze.
        username: The GitHub login whose public repos ground the analysis.
    """
    resume_text = resume_text.strip()
    username = username.strip()
    if not resume_text:
        return "Please provide the resume text to analyze."
    if not username:
        return "Please provide a GitHub username to cross-reference against."

    config = load_config()
    github = GitHubClient(token=config.github_token)
    cache = SqliteCache(config.cache_path)
    try:
        profile = github.fetch_profile(username)
        evidence = CachingRepoEvidenceFetcher(github, cache=cache).fetch_repo_evidence(profile)
    except UserNotFoundError:
        return f"No GitHub user found with the username '{username}'."
    except RateLimitError:
        return _RATE_LIMIT_MESSAGE
    except GitHubError as exc:
        return f"Couldn't fetch GitHub data right now: {exc}"

    try:
        client = AnthropicClient(api_key=config.anthropic_api_key, model=config.anthropic_model)
        extractor = CachingClaimExtractor(client, cache=cache, model=config.anthropic_model)
        verifier = CachingClaimVerifier(client, cache=cache, model=config.anthropic_model)
        report = build_gap_report(resume_text, profile, evidence, extractor, verifier)
    except AnthropicError as exc:
        return f"Couldn't analyze the resume right now: {exc}"

    return format_gap_report(report)


@mcp.tool()
def suggest_projects(resume_text: str, username: str) -> str:
    """Prescribe a ranked 30-day plan of projects to make a resume credible.

    Builds the resume-vs-GitHub gap report, then prescribes specific, shippable
    projects to close the highest-value gaps: each is tied to a concrete resume
    claim it would prove, sized ("a weekend" / "a week"), and scoped (what to skip).
    This is the star tool — the prescription, not just the diagnosis. Handles an
    empty or thin GitHub as the main case: it prescribes what to build from scratch
    rather than reporting that there's nothing to show.

    Args:
        resume_text: The full text of the resume to ground suggestions in.
        username: The GitHub login whose public repos ground the analysis.
    """
    resume_text = resume_text.strip()
    username = username.strip()
    if not resume_text:
        return "Please provide the resume text to build suggestions from."
    if not username:
        return "Please provide a GitHub username to ground the suggestions."

    config = load_config()
    github = GitHubClient(token=config.github_token)
    cache = SqliteCache(config.cache_path)
    try:
        profile = github.fetch_profile(username)
        evidence = CachingRepoEvidenceFetcher(github, cache=cache).fetch_repo_evidence(profile)
    except UserNotFoundError:
        return f"No GitHub user found with the username '{username}'."
    except RateLimitError:
        return _RATE_LIMIT_MESSAGE
    except GitHubError as exc:
        return f"Couldn't fetch GitHub data right now: {exc}"

    try:
        client = AnthropicClient(api_key=config.anthropic_api_key, model=config.anthropic_model)
        extractor = CachingClaimExtractor(client, cache=cache, model=config.anthropic_model)
        verifier = CachingClaimVerifier(client, cache=cache, model=config.anthropic_model)
        report = build_gap_report(resume_text, profile, evidence, extractor, verifier)
        suggester = CachingSuggestionGenerator(client, cache=cache, model=config.anthropic_model)
        plan = build_project_plan(report, profile, suggester)
    except AnthropicError as exc:
        return f"Couldn't build suggestions right now: {exc}"

    return format_project_plan(plan)


def format_gap_report(report: GapReport) -> str:
    """Render a GapReport into readable Markdown for Claude to present."""
    lines = [
        f"# Resume gap report for @{report.profile_login}",
        "",
        (
            f"Graded {report.total_claims} claim(s) against real public code: "
            f"{len(report.backed)} backed, {len(report.not_shown)} not shown yet, "
            f"{len(report.not_verifiable)} not verifiable from public code."
        ),
    ]

    if report.github_is_empty:
        lines += [
            "",
            f"**@{report.profile_login} has no public repositories yet.** That's the "
            "common case when real work lives in private company repos — so every claim "
            "below is currently unbacked publicly. This is the gap to close: the next "
            "step is deciding what to build and ship publicly to make each claim credible.",
        ]

    if report.backed:
        lines += ["", "## Backed by public code", ""]
        lines += [_format_evidence(e) for e in report.backed]

    if report.not_shown:
        heading = "## Claims to make credible" if report.github_is_empty else "## Not shown yet"
        lines += ["", heading, ""]
        lines += [_format_evidence(e) for e in report.not_shown]

    if report.not_verifiable:
        lines += ["", "## Not verifiable from public code", ""]
        lines += [_format_evidence(e) for e in report.not_verifiable]

    if report.total_claims == 0:
        lines += [
            "",
            "No concrete, verifiable claims were found in the resume text. Add specific "
            "projects, technologies, and outcomes, then run this again.",
        ]

    return "\n".join(lines)


def format_project_plan(plan: ProjectPlan) -> str:
    """Render a ProjectPlan into a readable Markdown 30-day plan for Claude to present."""
    lines = [f"# 30-day build plan for @{plan.profile_login}", ""]

    if plan.github_is_empty:
        lines += [
            f"**@{plan.profile_login} has no public repositories yet** — the common "
            "case when real work lives in private company repos. Every project below is "
            "a way to make a resume claim publicly credible, starting from scratch.",
            "",
        ]

    if not plan.suggestions:
        lines += [
            "No concrete, verifiable claims were found to ground suggestions on. Add "
            "specific projects, technologies, and outcomes to your resume, then run "
            "this again to get a build plan.",
        ]
        return "\n".join(lines)

    lines.append(
        f"Ranked by impact — gaps first, quicker wins earlier. {len(plan.suggestions)} project(s):"
    )
    lines.append("")
    for index, suggestion in enumerate(plan.suggestions, start=1):
        lines.append(_format_suggestion(index, suggestion))
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_suggestion(index: int, suggestion: Suggestion) -> str:
    """Render one ranked suggestion as a Markdown block."""
    skills = ", ".join(suggestion.skills) if suggestion.skills else "—"
    parts = [
        f"## {index}. {suggestion.title} ({suggestion.size})",
        suggestion.what_to_build,
        f"- **Proves:** {suggestion.proves_claim or 'a claimed skill'}",
        f"- **Skills shown:** {skills}",
        f"- **Skip to ship it:** {suggestion.skip or 'anything not core to the demo'}",
    ]
    return "\n".join(parts)


def _format_evidence(evidence: ClaimEvidence) -> str:
    """Render one claim + graded verdict as a Markdown bullet, citing files when backed."""
    bullet = f"- **{evidence.claim.text}**\n  {evidence.rationale}"
    if evidence.cited_files:
        bullet += f"\n  Cites: {', '.join(evidence.cited_files)}"
    return bullet


def format_profile(profile: Profile) -> str:
    """Render a Profile into readable Markdown for Claude to present."""
    header = _format_header(profile)
    if not profile.has_public_repos:
        return (
            f"{header}\n\n"
            f"**{profile.login} has no public repositories yet.**\n\n"
            "This is the common case for engineers whose real work lives in "
            "private company repos — it's a starting point, not a dead end. The "
            "next step is deciding what to build and ship publicly to make the "
            "resume credible."
        )

    lines = [header, "", f"## Public repositories ({len(profile.repos)})", ""]
    for repo in profile.repos:
        lines.append(_format_repo(repo))
    return "\n".join(lines)


def _format_header(profile: Profile) -> str:
    """Build the profile-summary block."""
    display = profile.name or profile.login
    parts = [
        f"# {display} (@{profile.login})",
        profile.profile_url,
        f"Public repos: {profile.public_repo_count} · Followers: {profile.followers}",
    ]
    if profile.bio:
        parts.insert(1, f"_{profile.bio}_")
    return "\n".join(parts)


def _format_repo(repo: Repo) -> str:
    """Render a single repo as a Markdown bullet."""
    language = repo.primary_language or "—"
    fork = " (fork)" if repo.is_fork else ""
    description = repo.description or "No description."
    pushed = repo.last_pushed_at or "unknown"
    return (
        f"- **[{repo.name}]({repo.url})**{fork} — {description}\n"
        f"  ★ {repo.stars} · {language} · last push: {pushed}"
    )


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
