"""Turn a resume + GitHub profile into a gap report (pure logic).

This module never imports ``mcp`` and never hits the network directly
(docs/ARCHITECTURE.md, rule 1). It gets claims from a claim extractor (the
Anthropic client, or any object satisfying ``ClaimExtractor``) and then does the
claim→repo matching itself, deterministically, so the matching is testable
offline. The empty-GitHub case is the primary path: with no public repos, every
claim is unsupported and ``github_is_empty`` is set — the gap to close, not a
dead end.
"""

from __future__ import annotations

import re
from typing import Protocol

from resume_assistant.core.models import Claim, ClaimEvidence, GapReport, Profile, Repo

_TOKEN = re.compile(r"[a-z0-9+#.]+")


class ClaimExtractor(Protocol):
    """Anything that can turn resume text into claims (implemented by AnthropicClient)."""

    def extract_claims(self, resume_text: str) -> list[Claim]: ...


def build_gap_report(resume_text: str, profile: Profile, extractor: ClaimExtractor) -> GapReport:
    """Cross-reference the resume's claims against the profile's public repos."""
    claims = extractor.extract_claims(resume_text)
    github_is_empty = not profile.has_public_repos

    supported: list[ClaimEvidence] = []
    unsupported: list[ClaimEvidence] = []
    for claim in claims:
        evidence = _evaluate_claim(claim, profile.repos)
        (supported if evidence.supported else unsupported).append(evidence)

    return GapReport(
        profile_login=profile.login,
        supported=tuple(supported),
        unsupported=tuple(unsupported),
        github_is_empty=github_is_empty,
    )


def _evaluate_claim(claim: Claim, repos: list[Repo]) -> ClaimEvidence:
    """Decide whether any public repo backs up ``claim`` via its named skills.

    A claim is supported when at least one of its skills appears in a non-fork
    repo's primary language, name, or description. Claims with no extractable
    skills can't be verified against repo metadata, so they stay unsupported —
    surfaced as a gap rather than silently assumed true.
    """
    matching: list[str] = []
    for repo in repos:
        if repo.is_fork:
            continue
        if _skills_match_repo(claim.skills, repo):
            matching.append(repo.name)

    if matching:
        skills = ", ".join(claim.skills)
        rationale = f"Backed by public repo(s) using {skills}: {', '.join(matching)}."
    elif not claim.skills:
        rationale = "No specific technology named, so it can't be verified against your repos."
    else:
        rationale = "No public repo demonstrates this — a gap to close."

    return ClaimEvidence(
        claim=claim,
        supported=bool(matching),
        matching_repos=tuple(matching),
        rationale=rationale,
    )


def _skills_match_repo(skills: tuple[str, ...], repo: Repo) -> bool:
    """True if any skill matches a whole token in the repo's language, name, or description.

    Token-based, not substring: the skill "go" matches a repo whose language is
    "Go" or whose name is "go-cache", but not "django-blog" or "mongo-client"
    (which merely contain the letters "go"). Avoids false "supported" verdicts.
    """
    if not skills:
        return False
    tokens = _repo_tokens(repo)
    return any(skill in tokens for skill in skills if skill)


def _repo_tokens(repo: Repo) -> set[str]:
    """Lowercased word tokens from a repo's language, name, and description."""
    text = " ".join(part for part in (repo.primary_language, repo.name, repo.description) if part)
    return set(_TOKEN.findall(text.lower()))
