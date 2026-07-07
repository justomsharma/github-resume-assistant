"""Tests for the MCP server adapter. The GitHub client is mocked — no network."""

from __future__ import annotations

import asyncio

from pytest_mock import MockerFixture

from resume_assistant.clients.github import GitHubError, UserNotFoundError
from resume_assistant.core.models import Profile, Repo
from resume_assistant.server import app


def test_tool_registered_with_schema() -> None:
    tools = asyncio.run(app.mcp.list_tools())
    by_name = {t.name: t for t in tools}

    assert set(by_name) == {"fetch_github_repos"}
    tool = by_name["fetch_github_repos"]
    assert tool.description  # a description exists for Claude to reason over
    assert "username" in tool.inputSchema["properties"]
    assert tool.inputSchema["required"] == ["username"]


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
