"""Tests for the gap-finder logic. Extractor and verifier are fakes — no network.

``core/analysis`` no longer matches claims itself: it gets graded verdicts from an
injected verifier and only buckets them. So these tests mock the verifier and
assert the bucketing, plus the empty-GitHub short-circuit (verifier never called).
"""

from __future__ import annotations

from resume_assistant.core.analysis import build_gap_report
from resume_assistant.core.models import Claim, ClaimEvidence, Profile, RepoEvidence, Verdict


class FakeExtractor:
    """A stand-in claim extractor returning canned claims (no Anthropic call)."""

    def __init__(self, claims: list[Claim]) -> None:
        self._claims = claims

    def extract_claims(self, resume_text: str) -> list[Claim]:
        return self._claims


class FakeVerifier:
    """A stand-in verifier returning canned verdicts and recording its calls."""

    def __init__(self, verdicts: dict[str, Verdict]) -> None:
        self._verdicts = verdicts
        self.calls = 0
        self.seen_claims: list[Claim] = []
        self.seen_evidence: list[RepoEvidence] = []

    def verify_claims(
        self, claims: list[Claim], evidence: list[RepoEvidence]
    ) -> list[ClaimEvidence]:
        self.calls += 1
        self.seen_claims = claims
        self.seen_evidence = evidence
        return [
            ClaimEvidence(
                claim=claim,
                verdict=self._verdicts.get(claim.text, "not_shown"),
                matching_repos=("go-cache",) if self._verdicts.get(claim.text) == "backed" else (),
                cited_files=(
                    ("go-cache/src/cache.go",) if self._verdicts.get(claim.text) == "backed" else ()
                ),
                rationale="graded",
            )
            for claim in claims
        ]


def test_verdicts_are_bucketed(
    profile_with_repos: Profile, repo_evidence: list[RepoEvidence]
) -> None:
    claims = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
        Claim(text="Proficient in React", skills=("react",), category="skill"),
        Claim(text="Handled 300+ requests/day", skills=(), category="impact"),
    ]
    verifier = FakeVerifier(
        {
            "Built a cache in Go": "backed",
            "Proficient in React": "not_shown",
            "Handled 300+ requests/day": "not_verifiable",
        }
    )

    report = build_gap_report(
        "resume", profile_with_repos, repo_evidence, FakeExtractor(claims), verifier
    )

    assert verifier.calls == 1
    assert report.total_claims == 3
    assert [e.claim.text for e in report.backed] == ["Built a cache in Go"]
    assert [e.claim.text for e in report.not_shown] == ["Proficient in React"]
    assert [e.claim.text for e in report.not_verifiable] == ["Handled 300+ requests/day"]
    # backed carries cited files; supported is the convenience alias for backed.
    assert report.backed[0].cited_files == ("go-cache/src/cache.go",)
    assert report.backed[0].supported is True
    assert report.supported == report.backed
    assert report.unsupported == report.not_shown + report.not_verifiable


def test_verifier_receives_claims_and_evidence(
    profile_with_repos: Profile, repo_evidence: list[RepoEvidence]
) -> None:
    claims = [Claim(text="Built a cache in Go", skills=("go",))]
    verifier = FakeVerifier({"Built a cache in Go": "backed"})

    build_gap_report("resume", profile_with_repos, repo_evidence, FakeExtractor(claims), verifier)

    assert verifier.seen_claims == claims
    assert verifier.seen_evidence == repo_evidence


def test_empty_github_short_circuits_without_calling_verifier(empty_profile: Profile) -> None:
    claims = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
        Claim(text="Proficient in React", skills=("react",), category="skill"),
    ]
    verifier = FakeVerifier({})  # would grade everything not_shown if called

    report = build_gap_report("resume", empty_profile, [], FakeExtractor(claims), verifier)

    assert verifier.calls == 0  # no public code to grade against — verifier skipped
    assert report.github_is_empty is True
    assert len(report.not_shown) == 2  # every claim is a gap, not "nothing found"
    assert report.backed == ()
    assert report.not_verifiable == ()


def test_no_evidence_short_circuits_even_with_repos(profile_with_repos: Profile) -> None:
    # A profile with repos but no fetched evidence (e.g. all empty repos) still
    # short-circuits rather than sending an empty evidence block to the model.
    claims = [Claim(text="Built a cache in Go", skills=("go",))]
    verifier = FakeVerifier({})

    report = build_gap_report("resume", profile_with_repos, [], FakeExtractor(claims), verifier)

    assert verifier.calls == 0
    assert len(report.not_shown) == 1


def test_no_claims_returns_empty_report(
    profile_with_repos: Profile, repo_evidence: list[RepoEvidence]
) -> None:
    verifier = FakeVerifier({})

    report = build_gap_report(
        "resume", profile_with_repos, repo_evidence, FakeExtractor([]), verifier
    )

    assert report.total_claims == 0
    assert report.backed == ()
    assert report.not_shown == ()
    assert report.not_verifiable == ()
