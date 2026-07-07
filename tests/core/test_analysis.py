"""Tests for the gap-finder logic. The claim extractor is a fake — no network."""

from __future__ import annotations

from resume_assistant.core.analysis import build_gap_report
from resume_assistant.core.models import Claim, Profile, Repo


class FakeExtractor:
    """A stand-in claim extractor returning canned claims (no Anthropic call)."""

    def __init__(self, claims: list[Claim]) -> None:
        self._claims = claims

    def extract_claims(self, resume_text: str) -> list[Claim]:
        return self._claims


def test_happy_path_splits_supported_and_unsupported(profile_with_repos: Profile) -> None:
    claims = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
        Claim(text="Proficient in React", skills=("react",), category="skill"),
    ]

    report = build_gap_report("resume", profile_with_repos, FakeExtractor(claims))

    assert report.github_is_empty is False
    assert report.total_claims == 2
    assert len(report.supported) == 1
    assert report.supported[0].claim.text == "Built a cache in Go"
    assert report.supported[0].matching_repos == ("go-cache",)
    assert len(report.unsupported) == 1
    assert report.unsupported[0].claim.text == "Proficient in React"


def test_forks_do_not_count_as_evidence(profile_with_repos: Profile) -> None:
    # The React app lives only in a fork, so a React claim stays unsupported.
    claims = [Claim(text="React work", skills=("react",), category="skill")]

    report = build_gap_report("resume", profile_with_repos, FakeExtractor(claims))

    assert len(report.unsupported) == 1
    assert report.unsupported[0].matching_repos == ()


def test_inflated_claim_is_unsupported(profile_with_repos: Profile) -> None:
    claims = [Claim(text="Expert in Rust and Kubernetes", skills=("rust", "kubernetes"))]

    report = build_gap_report("resume", profile_with_repos, FakeExtractor(claims))

    assert len(report.supported) == 0
    assert len(report.unsupported) == 1
    assert "gap to close" in report.unsupported[0].rationale


def test_empty_github_degrades_gracefully(empty_profile: Profile) -> None:
    claims = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
        Claim(text="Proficient in React", skills=("react",), category="skill"),
    ]

    report = build_gap_report("resume", empty_profile, FakeExtractor(claims))

    assert report.github_is_empty is True
    assert len(report.supported) == 0
    assert len(report.unsupported) == 2  # every claim is a gap, not "nothing found"
    assert report.total_claims == 2


def test_no_claims_returns_empty_report(profile_with_repos: Profile) -> None:
    report = build_gap_report("resume", profile_with_repos, FakeExtractor([]))

    assert report.total_claims == 0
    assert report.supported == ()
    assert report.unsupported == ()


def test_skill_matches_whole_token_not_substring() -> None:
    # "go" must not be "backed" by a django-blog repo just because it contains "go".
    profile = Profile(
        login="dev",
        name=None,
        bio=None,
        profile_url="https://github.com/dev",
        public_repo_count=1,
        followers=0,
        repos=[
            Repo(
                name="django-blog",
                description="A mongo-backed blog",
                url="https://github.com/dev/django-blog",
                stars=1,
                primary_language="Python",
                created_at=None,
                last_pushed_at=None,
                is_fork=False,
            )
        ],
    )
    claims = [Claim(text="Built services in Go", skills=("go",), category="project")]

    report = build_gap_report("resume", profile, FakeExtractor(claims))

    assert len(report.unsupported) == 1  # no false-positive substring match
    assert report.unsupported[0].matching_repos == ()


def test_claim_without_skills_is_unsupported(profile_with_repos: Profile) -> None:
    claims = [Claim(text="Led a team of five", skills=(), category="impact")]

    report = build_gap_report("resume", profile_with_repos, FakeExtractor(claims))

    assert len(report.unsupported) == 1
    assert "can't be verified" in report.unsupported[0].rationale
