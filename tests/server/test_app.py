"""Tests for the MCP server adapter. The GitHub client is mocked — no network."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pytest_mock import MockerFixture

from resume_assistant.clients.anthropic import AnthropicError
from resume_assistant.clients.github import GitHubError, UserNotFoundError
from resume_assistant.config import Config
from resume_assistant.core.models import Claim, Profile, Repo, Suggestion
from resume_assistant.server import app


def test_tools_registered_with_schema() -> None:
    tools = asyncio.run(app.mcp.list_tools())
    by_name = {t.name: t for t in tools}

    assert set(by_name) == {"fetch_github_repos", "analyze_resume", "suggest_projects"}

    fetch = by_name["fetch_github_repos"]
    assert fetch.description
    assert fetch.inputSchema["required"] == ["username"]

    analyze = by_name["analyze_resume"]
    assert analyze.description  # a description exists for Claude to reason over
    assert set(analyze.inputSchema["properties"]) == {"resume_text", "username"}
    assert set(analyze.inputSchema["required"]) == {"resume_text", "username"}

    suggest = by_name["suggest_projects"]
    assert suggest.description
    assert set(suggest.inputSchema["properties"]) == {"resume_text", "username"}
    assert set(suggest.inputSchema["required"]) == {"resume_text", "username"}


def _fetch(username: str) -> str:
    """Call the underlying tool function directly."""
    return app.fetch_github_repos(username)


def test_blank_username_handled(mocker: MockerFixture) -> None:
    client = mocker.patch.object(app, "GitHubClient")

    result = _fetch("   ")

    assert "provide a GitHub username" in result
    client.assert_not_called()  # never hits the network for blank input


def _patch_profile(mocker: MockerFixture, profile: Profile) -> None:
    instance = mocker.patch.object(app, "GitHubClient").return_value
    instance.fetch_profile.return_value = profile


def test_happy_path_formats_repos(mocker: MockerFixture) -> None:
    profile = Profile(
        login="octocat",
        name="The Octocat",
        bio="Building things.",
        profile_url="https://github.com/octocat",
        public_repo_count=1,
        followers=10,
        repos=[
            Repo(
                name="hello-world",
                description="My first repo",
                url="https://github.com/octocat/hello-world",
                stars=42,
                primary_language="Python",
                created_at="2020-01-01T00:00:00Z",
                last_pushed_at="2024-06-01T00:00:00Z",
                is_fork=False,
            )
        ],
    )
    _patch_profile(mocker, profile)

    result = _fetch("octocat")

    assert "The Octocat (@octocat)" in result
    assert "hello-world" in result
    assert "★ 42" in result
    assert "Python" in result


def test_empty_github_friendly_message(mocker: MockerFixture) -> None:
    profile = Profile(
        login="newgrad",
        name=None,
        bio=None,
        profile_url="https://github.com/newgrad",
        public_repo_count=0,
        followers=0,
        repos=[],
    )
    _patch_profile(mocker, profile)

    result = _fetch("newgrad")

    assert "no public repositories yet" in result
    assert "private company repos" in result  # degrades gracefully, not "nothing found"


def test_unknown_user_friendly_message(mocker: MockerFixture) -> None:
    instance = mocker.patch.object(app, "GitHubClient").return_value
    instance.fetch_profile.side_effect = UserNotFoundError("404")

    result = _fetch("ghost")

    assert "No GitHub user found" in result
    assert "ghost" in result


def test_generic_github_error_friendly_message(mocker: MockerFixture) -> None:
    instance = mocker.patch.object(app, "GitHubClient").return_value
    instance.fetch_profile.side_effect = GitHubError("boom")

    result = _fetch("octocat")

    assert "Couldn't fetch GitHub data" in result


# --- analyze_resume (v0.2) ---------------------------------------------------


def _patch_config(mocker: MockerFixture, tmp_path: Path, api_key: str | None) -> None:
    """Point analyze_resume at a temp cache and control the API key."""
    mocker.patch.object(
        app,
        "load_config",
        return_value=Config(
            github_token=None,
            anthropic_api_key=api_key,
            anthropic_model="claude-sonnet-5",
            cache_path=str(tmp_path / "cache.db"),
        ),
    )


def test_analyze_blank_inputs_handled(mocker: MockerFixture) -> None:
    client = mocker.patch.object(app, "GitHubClient")

    assert "provide the resume text" in app.analyze_resume("   ", "octocat")
    assert "provide a GitHub username" in app.analyze_resume("Built X.", "  ")
    client.assert_not_called()  # never hits the network for blank input


def test_analyze_happy_path_formats_gap_report(
    mocker: MockerFixture, tmp_path: Path, profile_with_repos: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.return_value = profile_with_repos
    mocker.patch.object(app, "AnthropicClient").return_value.extract_claims.return_value = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
        Claim(text="Proficient in React", skills=("react",), category="skill"),
    ]

    result = app.analyze_resume("some resume", "octocat")

    assert "gap report for @octocat" in result
    assert "Built a cache in Go" in result  # supported (go-cache repo)
    assert "go-cache" in result
    assert "Proficient in React" in result  # unsupported
    assert "Not yet backed publicly" in result


def test_analyze_empty_github_degrades_gracefully(
    mocker: MockerFixture, tmp_path: Path, empty_profile: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(app, "GitHubClient").return_value.fetch_profile.return_value = empty_profile
    mocker.patch.object(app, "AnthropicClient").return_value.extract_claims.return_value = [
        Claim(text="Built a cache in Go", skills=("go",), category="project"),
    ]

    result = app.analyze_resume("some resume", "newgrad")

    assert "no public repositories yet" in result
    assert "gap to close" in result  # framed as the gap, not "nothing found"
    assert "Claims to make credible" in result


def test_analyze_missing_key_friendly_message(
    mocker: MockerFixture, tmp_path: Path, profile_with_repos: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key=None)
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.return_value = profile_with_repos

    result = app.analyze_resume("some resume", "octocat")

    assert "Couldn't analyze the resume" in result
    assert "ANTHROPIC_API_KEY" in result  # explains what's missing


def test_analyze_unknown_user_friendly_message(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.side_effect = UserNotFoundError("404")

    result = app.analyze_resume("some resume", "ghost")

    assert "No GitHub user found" in result


def test_analyze_anthropic_error_friendly_message(
    mocker: MockerFixture, tmp_path: Path, profile_with_repos: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.return_value = profile_with_repos
    mocker.patch.object(
        app, "AnthropicClient"
    ).return_value.extract_claims.side_effect = AnthropicError("rate limited")

    result = app.analyze_resume("some resume", "octocat")

    assert "Couldn't analyze the resume right now" in result


# --- suggest_projects (v0.3) -------------------------------------------------


def _suggestion(proves: str, size: str, title: str) -> Suggestion:
    return Suggestion(
        title=title,
        what_to_build="Build the thing and ship it.",
        proves_claim=proves,
        skills=("go",),
        size=size,
        skip="auth and polish",
    )


def _patch_anthropic(
    mocker: MockerFixture, claims: list[Claim], suggestions: list[Suggestion]
) -> None:
    """Patch AnthropicClient so both extract_claims and generate_suggestions are stubbed."""
    instance = mocker.patch.object(app, "AnthropicClient").return_value
    instance.extract_claims.return_value = claims
    instance.generate_suggestions.return_value = suggestions


def test_suggest_blank_inputs_handled(mocker: MockerFixture) -> None:
    client = mocker.patch.object(app, "GitHubClient")

    assert "provide the resume text" in app.suggest_projects("   ", "octocat")
    assert "provide a GitHub username" in app.suggest_projects("Built X.", "  ")
    client.assert_not_called()  # never hits the network for blank input


def test_suggest_happy_path_formats_ranked_plan(
    mocker: MockerFixture, tmp_path: Path, profile_with_repos: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.return_value = profile_with_repos
    _patch_anthropic(
        mocker,
        claims=[
            Claim(text="Built a cache in Go", skills=("go",), category="project"),
            Claim(text="Proficient in React", skills=("react",), category="skill"),
        ],
        suggestions=[
            _suggestion("Built a cache in Go", "a week", title="Reinforce cache"),
            _suggestion("Proficient in React", "a weekend", title="Ship a React app"),
        ],
    )

    result = app.suggest_projects("some resume", "octocat")

    assert "30-day build plan for @octocat" in result
    # React is the gap (unsupported) → ranked first over the already-backed Go claim.
    assert result.index("Ship a React app") < result.index("Reinforce cache")
    assert "Skip to ship it:" in result
    assert "a weekend" in result


def test_suggest_empty_github_still_prescribes(
    mocker: MockerFixture, tmp_path: Path, empty_profile: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(app, "GitHubClient").return_value.fetch_profile.return_value = empty_profile
    _patch_anthropic(
        mocker,
        claims=[Claim(text="Built a cache in Go", skills=("go",), category="project")],
        suggestions=[_suggestion("Built a cache in Go", "a weekend", title="Cache demo")],
    )

    result = app.suggest_projects("some resume", "newgrad")

    assert "no public repositories yet" in result  # empty case framed, not an error
    assert "Cache demo" in result  # still prescribes buildable ideas, not "nothing"


def test_suggest_thin_resume_degrades_gracefully(
    mocker: MockerFixture, tmp_path: Path, empty_profile: Profile
) -> None:
    """No claims and empty GitHub → guide the user, don't crash or fabricate."""
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(app, "GitHubClient").return_value.fetch_profile.return_value = empty_profile
    _patch_anthropic(mocker, claims=[], suggestions=[])

    result = app.suggest_projects("thin resume", "newgrad")

    assert "No concrete, verifiable claims" in result
    assert "run this again" in result


def test_suggest_anthropic_error_friendly_message(
    mocker: MockerFixture, tmp_path: Path, profile_with_repos: Profile
) -> None:
    _patch_config(mocker, tmp_path, api_key="k")
    mocker.patch.object(
        app, "GitHubClient"
    ).return_value.fetch_profile.return_value = profile_with_repos
    instance = mocker.patch.object(app, "AnthropicClient").return_value
    instance.extract_claims.side_effect = AnthropicError("rate limited")

    result = app.suggest_projects("some resume", "octocat")

    assert "Couldn't build suggestions right now" in result
