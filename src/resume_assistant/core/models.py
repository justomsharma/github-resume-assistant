"""Typed data models shared across the app.

Clients return these dataclasses, never raw API JSON (docs/ARCHITECTURE.md, rule 2).
v0.1 needs only ``Profile`` and ``Repo``; Claim/Gap/Suggestion arrive with v0.2/v0.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Repo:
    """A single public repository's resume-relevant facts."""

    name: str
    description: str | None
    url: str
    stars: int
    primary_language: str | None
    created_at: str | None
    last_pushed_at: str | None
    is_fork: bool


@dataclass(frozen=True)
class Profile:
    """A GitHub user's profile plus their public repositories.

    The empty-GitHub case (our real target user) is represented naturally: a
    valid profile with ``repos == []`` and ``public_repo_count == 0``.
    """

    login: str
    name: str | None
    bio: str | None
    profile_url: str
    public_repo_count: int
    followers: int
    repos: list[Repo] = field(default_factory=list)

    @property
    def has_public_repos(self) -> bool:
        """True when the user has at least one public repository."""
        return len(self.repos) > 0
