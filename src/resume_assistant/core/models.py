"""Typed data models shared across the app.

Clients return these dataclasses, never raw API JSON (docs/ARCHITECTURE.md, rule 2).
v0.1 needs only ``Profile`` and ``Repo``; ``Claim``/``ClaimEvidence``/``GapReport``
arrive with v0.2; ``Suggestion`` with v0.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# The three honest verdicts a claim can earn against real public code.
# ``backed`` — public code proves it (cites specific files). ``not_shown`` — no
# public code proves it yet (a gap to close). ``not_verifiable`` — the kind of
# claim public code structurally can't prove (private/enterprise usage, latency
# numbers, "300+/day", cost percentages).
Verdict = Literal["backed", "not_shown", "not_verifiable"]


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
    default_branch: str | None = None


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
class RepoEvidence:
    """Code-level facts about a single public repo, used to ground verdicts.

    Fetched by ``clients/github.py`` (never in ``core/``). Every field is bounded
    so a repo with a huge README or dependency list can't blow the LLM token
    budget: ``readme_excerpt`` is truncated to a char cap, ``dependencies`` and
    ``notable_paths`` are capped lists, and ``file_count`` records how many paths
    the repo actually has so a truncated ``notable_paths`` still reads honestly.
    """

    repo_name: str
    primary_language: str | None
    language_breakdown: tuple[tuple[str, int], ...]
    dependencies: tuple[str, ...]
    notable_paths: tuple[str, ...]
    file_count: int
    readme_excerpt: str | None
    pushed_at: str | None


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
    """A claim paired with an LLM-graded verdict against real public code.

    ``verdict`` is the honest three-way grade (see ``Verdict``); ``cited_files``
    are the specific repo files the verifier pointed to when backing the claim
    (empty unless ``verdict == "backed"``). ``matching_repos`` names the repos
    those files live in. ``supported`` stays as a convenience alias for a
    ``backed`` verdict so existing consumers keep working.
    """

    claim: Claim
    verdict: Verdict
    matching_repos: tuple[str, ...]
    cited_files: tuple[str, ...]
    rationale: str

    @property
    def supported(self) -> bool:
        """True only when public code backs the claim (verdict == ``backed``)."""
        return self.verdict == "backed"


@dataclass(frozen=True)
class GapReport:
    """The result of grading resume claims against real public code.

    Claims are bucketed by verdict. The empty-GitHub case (our real target user)
    is represented naturally: with no public repos every claim lands in
    ``not_shown`` and ``github_is_empty`` is ``True``. Consumers should frame that
    as the gap to close, never as "nothing found". ``supported``/``unsupported``
    are convenience views over the buckets so the ranking in
    ``core/suggestions.py`` and the cache fingerprint keep working unchanged.
    """

    profile_login: str
    backed: tuple[ClaimEvidence, ...]
    not_shown: tuple[ClaimEvidence, ...]
    not_verifiable: tuple[ClaimEvidence, ...]
    github_is_empty: bool

    @property
    def supported(self) -> tuple[ClaimEvidence, ...]:
        """Claims public code backs up (the ``backed`` bucket)."""
        return self.backed

    @property
    def unsupported(self) -> tuple[ClaimEvidence, ...]:
        """Claims public code does not back up (gaps + unprovable claims)."""
        return self.not_shown + self.not_verifiable

    @property
    def total_claims(self) -> int:
        """How many claims were extracted and evaluated."""
        return len(self.backed) + len(self.not_shown) + len(self.not_verifiable)


@dataclass(frozen=True)
class Suggestion:
    """One specific, shippable project to make a resume claim credible.

    Each suggestion is tied to a concrete claim (``proves_claim``), sized so the
    user knows the effort (``size`` — e.g. "a weekend", "a week"), and scoped with
    an explicit ``skip`` so it stays shippable. ``skills`` are the normalized
    technologies it would demonstrate.
    """

    title: str
    what_to_build: str
    proves_claim: str
    skills: tuple[str, ...]
    size: str
    skip: str


@dataclass(frozen=True)
class ProjectPlan:
    """A ranked 30-day plan of projects derived from a gap report.

    ``suggestions`` are ordered by ``core/suggestions.py`` (gaps first, quicker
    wins earlier). The empty-GitHub case (our real target user) is carried through
    in ``github_is_empty`` so the renderer can frame the plan as the way to build
    public credibility from scratch, never as "nothing to suggest".
    """

    profile_login: str
    suggestions: tuple[Suggestion, ...]
    github_is_empty: bool
