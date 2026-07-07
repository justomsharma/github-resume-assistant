"""MCP server exposing the resume-assistant tools over stdio.

The MCP layer is intentionally dumb (docs/ARCHITECTURE.md, rule 4): each tool
validates input, calls a client/core function, and formats readable output.
Business logic and HTTP live elsewhere. v0.1 registers only ``fetch_github_repos``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from resume_assistant.clients.github import (
    GitHubClient,
    GitHubError,
    RateLimitError,
    UserNotFoundError,
)
from resume_assistant.config import load_config
from resume_assistant.core.models import Profile, Repo

mcp = FastMCP("github-resume-assistant")


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
