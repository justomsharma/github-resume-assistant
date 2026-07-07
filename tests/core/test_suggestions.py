"""Tests for the pure suggestion-ranking logic. No network, no API."""

from __future__ import annotations

from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    Suggestion,
)
from resume_assistant.core.suggestions import build_project_plan


def _evidence(text: str, supported: bool) -> ClaimEvidence:
    return ClaimEvidence(
        claim=Claim(text=text),
        supported=supported,
        matching_repos=(),
        rationale="",
    )


def _profile() -> Profile:
    return Profile("octocat", None, None, "", 0, 0)


def _suggestion(proves: str, size: str, title: str = "Project") -> Suggestion:
    return Suggestion(
        title=title,
        what_to_build="Build the thing.",
        proves_claim=proves,
        skills=("go",),
        size=size,
        skip="auth",
    )


class FakeSuggester:
    """Returns a fixed candidate list (stands in for the Anthropic client)."""

    def __init__(self, suggestions: list[Suggestion]) -> None:
        self._suggestions = suggestions

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]:
        return self._suggestions


def test_gaps_ranked_before_supported_claims() -> None:
    report = GapReport(
        profile_login="octocat",
        supported=(_evidence("Backed claim", supported=True),),
        unsupported=(_evidence("Gap claim", supported=False),),
        github_is_empty=False,
    )
    # Candidate order deliberately puts the supported-claim project first.
    candidates = [
        _suggestion("Backed claim", "a week", title="Reinforce"),
        _suggestion("Gap claim", "a week", title="Close the gap"),
    ]

    plan = build_project_plan(report, _profile(), FakeSuggester(candidates))

    assert [s.title for s in plan.suggestions] == ["Close the gap", "Reinforce"]


def test_within_gaps_quicker_wins_come_first() -> None:
    report = GapReport(
        profile_login="octocat",
        supported=(),
        unsupported=(_evidence("Gap claim", supported=False),),
        github_is_empty=False,
    )
    candidates = [
        _suggestion("Gap claim", "a week", title="Week-long"),
        _suggestion("Gap claim", "a weekend", title="Weekend"),
    ]

    plan = build_project_plan(report, _profile(), FakeSuggester(candidates))

    assert [s.title for s in plan.suggestions] == ["Weekend", "Week-long"]


def test_stable_order_for_equal_rank() -> None:
    report = GapReport(
        profile_login="octocat",
        supported=(),
        unsupported=(_evidence("Gap claim", supported=False),),
        github_is_empty=False,
    )
    candidates = [
        _suggestion("Gap claim", "a weekend", title="First"),
        _suggestion("Gap claim", "a weekend", title="Second"),
    ]

    plan = build_project_plan(report, _profile(), FakeSuggester(candidates))

    assert [s.title for s in plan.suggestions] == ["First", "Second"]


def test_empty_github_with_claims_still_yields_a_plan(empty_profile: Profile) -> None:
    """Our real user: empty GitHub, but claims exist → buildable plan, not nothing."""
    report = GapReport(
        profile_login="newgrad",
        supported=(),
        unsupported=(
            _evidence("Built a cache in Go", supported=False),
            _evidence("Proficient in React", supported=False),
        ),
        github_is_empty=True,
    )
    candidates = [
        _suggestion("Built a cache in Go", "a weekend", title="Cache demo"),
        _suggestion("Proficient in React", "a week", title="React app"),
    ]

    plan = build_project_plan(report, empty_profile, FakeSuggester(candidates))

    assert plan.github_is_empty is True
    assert len(plan.suggestions) == 2  # produces ideas, never "nothing to suggest"
    assert plan.suggestions[0].title == "Cache demo"  # weekend before week


def test_no_candidates_yields_empty_plan(empty_profile: Profile) -> None:
    report = GapReport(
        profile_login="newgrad",
        supported=(),
        unsupported=(),
        github_is_empty=True,
    )

    plan = build_project_plan(report, empty_profile, FakeSuggester([]))

    assert plan.suggestions == ()
    assert plan.profile_login == "newgrad"
