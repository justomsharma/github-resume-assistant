"""Typed data models shared across the app.

Clients return these dataclasses, never raw API JSON (docs/ARCHITECTURE.md, rule 2).
v0.1 needs only ``Profile`` and ``Repo``; ``Claim``/``ClaimEvidence``/``GapReport``
arrive with v0.2; ``Suggestion`` with v0.3.
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


@dataclass(frozen=True)
class Claim:
    """One concrete, verifiable claim extracted from a resume.

    ``skills`` holds the normalized technologies/skills the claim names (e.g.
    ``("go", "redis")``); ``core/analysis.py`` matches these against real repos.
    ``category`` is a coarse bucket like ``"project"``, ``"skill"``, or ``"impact"``.
    """

    text: str
    skills: tuple[str, ...] = ()
    category: str = "other"


@dataclass(frozen=True)
class ClaimEvidence:
    """A claim paired with the verdict on whether public GitHub backs it up."""

    claim: Claim
    supported: bool
    matching_repos: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class GapReport:
    """The result of cross-referencing resume claims against GitHub reality.

    The empty-GitHub case (our real target user) is represented naturally: every
    claim lands in ``unsupported`` and ``github_is_empty`` is ``True``. Consumers
    should frame that as the gap to close, never as "nothing found".
    """

    profile_login: str
    supported: tuple[ClaimEvidence, ...]
    unsupported: tuple[ClaimEvidence, ...]
    github_is_empty: bool

    @property
    def total_claims(self) -> int:
        """How many claims were extracted and evaluated."""
        return len(self.supported) + len(self.unsupported)
