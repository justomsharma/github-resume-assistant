"""Tests for the GitHub client. All HTTP is mocked with `responses` — no network."""

from __future__ import annotations

from typing import Any

import pytest
import responses

from resume_assistant.clients.github import (
    GitHubClient,
    GitHubError,
    RateLimitError,
    UserNotFoundError,
)

_API = "https://api.github.com"


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record (and skip) time.sleep calls in the client so tests run instantly."""
    recorded: list[float] = []
    monkeypatch.setattr(
        "resume_assistant.clients.github.time.sleep",
        lambda seconds: recorded.append(seconds),
    )
    return recorded


def _register_repos(username: str, pages: list[list[dict[str, Any]]]) -> None:
    """Register one mocked repos response per page, in order."""
    for page in pages:
        responses.add(
            responses.GET,
            f"{_API}/users/{username}/repos",
            json=page,
            status=200,
        )


@responses.activate
def test_fetch_profile_happy_path(
    user_json: dict[str, Any], repos_json: list[dict[str, Any]]
) -> None:
    responses.add(responses.GET, f"{_API}/users/octocat", json=user_json, status=200)
    _register_repos("octocat", [repos_json])

    profile = GitHubClient().fetch_profile("octocat")

    assert profile.login == "octocat"
    assert profile.name == "The Octocat"
    assert profile.bio == "Building things."
    assert profile.public_repo_count == 2
    assert profile.followers == 1500
    assert profile.has_public_repos is True
    assert len(profile.repos) == 2

    first = profile.repos[0]
    assert first.name == "hello-world"
    assert first.stars == 42
    assert first.primary_language == "Python"  # taken from the list `language` field
    assert first.is_fork is False
    assert first.last_pushed_at == "2024-06-01T00:00:00Z"

    fork = profile.repos[1]
    assert fork.primary_language is None
    assert fork.description is None
    assert fork.is_fork is True


@responses.activate
def test_fetch_profile_paginates(user_json: dict[str, Any]) -> None:
    # A full page of 100 must trigger a second request; a short page stops paging.
    full_page = [
        {"name": f"repo-{i}", "html_url": f"https://github.com/octocat/repo-{i}"}
        for i in range(100)
    ]
    second_page = [{"name": "repo-last", "html_url": "https://github.com/octocat/repo-last"}]
    responses.add(responses.GET, f"{_API}/users/octocat", json=user_json, status=200)
    _register_repos("octocat", [full_page, second_page])

    profile = GitHubClient().fetch_profile("octocat")

    assert len(profile.repos) == 101
    assert profile.repos[-1].name == "repo-last"
    # Two repo requests were made (page 1 and page 2).
    repo_calls = [c for c in responses.calls if "/repos" in c.request.url]
    assert len(repo_calls) == 2


@responses.activate
def test_fetch_profile_unknown_user_raises() -> None:
    responses.add(
        responses.GET,
        f"{_API}/users/ghost",
        json={"message": "Not Found"},
        status=404,
    )

    with pytest.raises(UserNotFoundError):
        GitHubClient().fetch_profile("ghost")


@responses.activate
def test_fetch_profile_rate_limited_raises() -> None:
    responses.add(
        responses.GET,
        f"{_API}/users/octocat",
        json={"message": "API rate limit exceeded"},
        status=403,
        headers={"X-RateLimit-Remaining": "0"},
    )

    with pytest.raises(RateLimitError):
        GitHubClient().fetch_profile("octocat")


@responses.activate
def test_fetch_profile_empty_github(empty_user_json: dict[str, Any]) -> None:
    responses.add(responses.GET, f"{_API}/users/newgrad", json=empty_user_json, status=200)
    _register_repos("newgrad", [[]])

    profile = GitHubClient().fetch_profile("newgrad")

    assert profile.login == "newgrad"
    assert profile.public_repo_count == 0
    assert profile.repos == []
    assert profile.has_public_repos is False


@responses.activate
def test_short_retry_after_waits_then_succeeds(
    user_json: dict[str, Any], sleeps: list[float]
) -> None:
    # A 429 with a short Retry-After is waited out, then the retry succeeds.
    responses.add(
        responses.GET,
        f"{_API}/users/octocat",
        json={"message": "secondary rate limit"},
        status=429,
        headers={"Retry-After": "3"},
    )
    responses.add(responses.GET, f"{_API}/users/octocat", json=user_json, status=200)
    _register_repos("octocat", [[]])

    profile = GitHubClient().fetch_profile("octocat")

    assert profile.login == "octocat"
    assert sleeps == [3]  # slept exactly the Retry-After, once


@responses.activate
def test_retry_after_over_cap_raises_without_long_sleep(sleeps: list[float]) -> None:
    responses.add(
        responses.GET,
        f"{_API}/users/octocat",
        json={"message": "secondary rate limit"},
        status=403,
        headers={"Retry-After": "600"},
    )

    with pytest.raises(RateLimitError) as exc_info:
        GitHubClient().fetch_profile("octocat")

    assert "600s" in str(exc_info.value)
    assert sleeps == []  # never waited out a limit longer than the cap


@responses.activate
def test_primary_rate_limit_raises_with_reset(sleeps: list[float]) -> None:
    responses.add(
        responses.GET,
        f"{_API}/users/octocat",
        json={"message": "API rate limit exceeded"},
        status=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1720000000"},
    )

    with pytest.raises(RateLimitError) as exc_info:
        GitHubClient().fetch_profile("octocat")

    assert "1720000000" in str(exc_info.value)
    assert sleeps == []  # primary limit is surfaced immediately, never waited out


@responses.activate
def test_persistent_secondary_limit_retries_then_raises(sleeps: list[float]) -> None:
    # A short Retry-After that never clears is retried up to the cap, then fails.
    for _ in range(3):
        responses.add(
            responses.GET,
            f"{_API}/users/octocat",
            json={"message": "secondary rate limit"},
            status=429,
            headers={"Retry-After": "2"},
        )

    with pytest.raises(GitHubError) as exc_info:
        GitHubClient().fetch_profile("octocat")

    assert not isinstance(exc_info.value, RateLimitError)
    assert sleeps == [2, 2, 2]  # one wait per retry attempt (_MAX_RETRIES)


@responses.activate
def test_server_error_backs_off_exponentially_then_succeeds(
    user_json: dict[str, Any], sleeps: list[float]
) -> None:
    responses.add(responses.GET, f"{_API}/users/octocat", status=500)
    responses.add(responses.GET, f"{_API}/users/octocat", status=502)
    responses.add(responses.GET, f"{_API}/users/octocat", json=user_json, status=200)
    _register_repos("octocat", [[]])

    profile = GitHubClient().fetch_profile("octocat")

    assert profile.login == "octocat"
    assert sleeps == [1.0, 2.0]  # exponential: base*2**0, base*2**1


@responses.activate
def test_token_sets_authorization_header(user_json: dict[str, Any]) -> None:
    responses.add(responses.GET, f"{_API}/users/octocat", json=user_json, status=200)
    _register_repos("octocat", [[]])

    GitHubClient(token="secret-token").fetch_profile("octocat")

    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret-token"
