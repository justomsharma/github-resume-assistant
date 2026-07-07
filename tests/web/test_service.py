"""Tests for the web service orchestration. GitHub + Anthropic are mocked."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from resume_assistant.clients.github import GitHubError, RateLimitError, UserNotFoundError
from resume_assistant.config import Config
from resume_assistant.core.models import GapReport, Profile, ProjectPlan
from resume_assistant.web import service
from resume_assistant.web.service import AnalysisError, AnalysisResult, run_analysis


@pytest.fixture
def config() -> Config:
    return Config(
        github_token=None,
        anthropic_api_key="test-key",
        anthropic_model="claude-sonnet-5",
        cache_path=":memory:",
    )


def _patch_profile(mocker: MockerFixture, profile: Profile) -> None:
    """Make GitHubClient().fetch_profile return the given profile."""
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.return_value = profile


def _stub_anthropic(mocker: MockerFixture) -> None:
    """Neutralize the Anthropic-backed pieces so no network/keys are needed."""
    mocker.patch.object(service, "AnthropicClient")
    mocker.patch.object(service, "SqliteCache")
    mocker.patch.object(service, "CachingClaimExtractor")
    mocker.patch.object(service, "CachingClaimVerifier")
    mocker.patch.object(service, "CachingRepoEvidenceFetcher")
    mocker.patch.object(service, "CachingSuggestionGenerator")


def test_happy_path_returns_result(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="octocat",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=False,
    )
    plan = ProjectPlan(profile_login="octocat", suggestions=(), github_is_empty=False)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisResult)
    assert outcome.report is report
    assert outcome.plan is plan
    assert outcome.profile is profile_with_repos


def test_empty_github_is_a_success_not_an_error(
    mocker: MockerFixture, config: Config, empty_profile: Profile
) -> None:
    """Our real user: an empty GitHub must be a normal result, never an error."""
    _patch_profile(mocker, empty_profile)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="newgrad",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=True,
    )
    plan = ProjectPlan(profile_login="newgrad", suggestions=(), github_is_empty=True)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    outcome = run_analysis("resume text", "newgrad", config)

    assert isinstance(outcome, AnalysisResult)
    assert outcome.report.github_is_empty is True


def test_user_not_found_maps_to_404(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = UserNotFoundError("nope")

    outcome = run_analysis("resume text", "ghost", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 404
    assert "ghost" in outcome.message


def test_rate_limit_maps_to_503(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = RateLimitError("limited")

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 503
    assert "rate limit" in outcome.message.lower()


def test_generic_github_error_maps_to_502(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = GitHubError("boom")

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 502


def test_anthropic_failure_maps_to_502(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    from resume_assistant.clients.anthropic import AnthropicError

    mocker.patch.object(service, "build_gap_report", side_effect=AnthropicError("overloaded"))

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 502
