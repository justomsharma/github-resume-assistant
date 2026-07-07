"""Shared fixtures: fake GitHub profile + repo JSON matching the REST API shape."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def user_json() -> dict[str, Any]:
    """A realistic /users/{login} response for a user with public repos."""
    return {
        "login": "octocat",
        "name": "The Octocat",
        "bio": "Building things.",
        "html_url": "https://github.com/octocat",
        "public_repos": 2,
        "followers": 1500,
    }


@pytest.fixture
def empty_user_json() -> dict[str, Any]:
    """A /users/{login} response for our real target: a user with no public repos."""
    return {
        "login": "newgrad",
        "name": None,
        "bio": None,
        "html_url": "https://github.com/newgrad",
        "public_repos": 0,
        "followers": 0,
    }


@pytest.fixture
def repos_json() -> list[dict[str, Any]]:
    """A short /users/{login}/repos page with varied languages, stars, and a fork."""
    return [
        {
            "name": "hello-world",
            "description": "My first repo",
            "html_url": "https://github.com/octocat/hello-world",
            "stargazers_count": 42,
            "language": "Python",
            "created_at": "2020-01-01T00:00:00Z",
            "pushed_at": "2024-06-01T00:00:00Z",
            "fork": False,
        },
        {
            "name": "forked-lib",
            "description": None,
            "html_url": "https://github.com/octocat/forked-lib",
            "stargazers_count": 0,
            "language": None,
            "created_at": "2021-05-01T00:00:00Z",
            "pushed_at": "2021-05-02T00:00:00Z",
            "fork": True,
        },
    ]
