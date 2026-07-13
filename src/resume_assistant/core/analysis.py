"""Turn a resume + GitHub profile into a gap report (pure logic).

This module never imports ``mcp`` and never hits the network directly
(docs/ARCHITECTURE.md, rule 1). It gets claims from a claim extractor and graded
verdicts from a claim verifier (both implemented by the Anthropic client, or any
object satisfying the protocols), then buckets the verdicts itself — pure,
deterministic grouping that's testable by mocking the verifier. The empty-GitHub
case is the primary path: with no public repos there's no code to grade against,
so every claim is ``not_shown`` (the gap to close) and the verifier is never
called.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    RepoEvidence,
)


class ClaimExtractor(Protocol):
    """Anything that can turn resume text into claims (implemented by AnthropicClient)."""

    def extract_claims(self, resume_text: str) -> list[Claim]: ...


class ClaimVerifier(Protocol):
    """Anything that can grade claims against real code (implemented by AnthropicClient)."""

    def verify_claims(
        self,
        claims: list[Claim],
        evidence: list[RepoEvidence],
        on_batch_done: Callable[[int, int], None] | None = None,
    ) -> list[ClaimEvidence]: ...


def build_gap_report(
    resume_text: str,
    profile: Profile,
    evidence: list[RepoEvidence],
    extractor: ClaimExtractor,
    verifier: ClaimVerifier,
    on_verify_batch_done: Callable[[int, int], None] | None = None,
) -> GapReport:
    """Grade the resume's claims against real repo evidence and bucket the verdicts.

    ``on_verify_batch_done``, if given, is forwarded to the verifier so a caller
    can show progress through claim verification (see ``ClaimVerifier``).
    """
    claims = extractor.extract_claims(resume_text)
    github_is_empty = not profile.has_public_repos

    if github_is_empty or not evidence:
        # No public code to grade against: every claim is a gap to close, not a
        # mark against the person. Skip the verifier — there's nothing to cite.
        graded = [_not_shown(claim) for claim in claims]
    else:
        graded = verifier.verify_claims(claims, evidence, on_verify_batch_done)

    return _bucket(profile.login, graded, github_is_empty)


def _bucket(login: str, graded: list[ClaimEvidence], github_is_empty: bool) -> GapReport:
    """Partition graded claims into the three verdict buckets."""
    backed = tuple(e for e in graded if e.verdict == "backed")
    not_shown = tuple(e for e in graded if e.verdict == "not_shown")
    not_verifiable = tuple(e for e in graded if e.verdict == "not_verifiable")
    return GapReport(
        profile_login=login,
        backed=backed,
        not_shown=not_shown,
        not_verifiable=not_verifiable,
        github_is_empty=github_is_empty,
    )


def _not_shown(claim: Claim) -> ClaimEvidence:
    """A claim with no public code to grade against — a gap to close, not a failure."""
    return ClaimEvidence(
        claim=claim,
        verdict="not_shown",
        matching_repos=(),
        cited_files=(),
        rationale="No public repositories yet, so nothing public backs this — a gap to close.",
    )
