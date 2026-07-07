"""Shared fixtures: fake GitHub profile + repo JSON matching the REST API shape."""

from __future__ import annotations

from typing import Any

import pytest

from resume_assistant.core.models import Profile, Repo, RepoEvidence


@pytest.fixture
def sample_resume() -> str:
    """A short resume with strong (backable) and weak (unbacked) claims."""
    return (
        "Built a distributed cache in Go used in production.\n"
        "Proficient in React for frontend work.\n"
        "Led a team of five engineers to deliver on time."
    )


@pytest.fixture
def profile_with_repos() -> Profile:
    """A profile whose repos back some claims (Go) but not others (React)."""
    return Profile(
        login="octocat",
        name="The Octocat",
        bio="Building things.",
        profile_url="https://github.com/octocat",
        public_repo_count=2,
        followers=10,
        repos=[
            Repo(
                name="go-cache",
                description="A distributed cache",
                url="https://github.com/octocat/go-cache",
                stars=42,
                primary_language="Go",
                created_at="2020-01-01T00:00:00Z",
                last_pushed_at="2024-06-01T00:00:00Z",
                is_fork=False,
            ),
            Repo(
                name="forked-thing",
                description="A React app",
                url="https://github.com/octocat/forked-thing",
                stars=0,
                primary_language="JavaScript",
                created_at="2021-01-01T00:00:00Z",
                last_pushed_at="2021-01-02T00:00:00Z",
                is_fork=True,  # forks don't count as evidence
            ),
        ],
    )


@pytest.fixture
def empty_profile() -> Profile:
    """Our real target user: a valid profile with no public repos."""
    return Profile(
        login="newgrad",
        name=None,
        bio=None,
        profile_url="https://github.com/newgrad",
        public_repo_count=0,
        followers=0,
        repos=[],
    )


@pytest.fixture
def repo_evidence() -> list[RepoEvidence]:
    """Code-level evidence for octocat's one non-fork repo (go-cache)."""
    return [
        RepoEvidence(
            repo_name="go-cache",
            primary_language="Go",
            language_breakdown=(("Go", 12000), ("Shell", 300)),
            dependencies=("github.com/redis/go-redis", "golang.org/x/sync"),
            notable_paths=("Dockerfile", "src/cache.go", "tests/cache_test.go"),
            file_count=14,
            readme_excerpt="# go-cache\nA distributed cache with an LRU eviction policy.",
            pushed_at="2024-06-01T00:00:00Z",
        )
    ]


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
