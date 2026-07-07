"""GitHub REST API client.

Owns HTTP calls, pagination and rate-limit/404 handling, and mapping raw JSON
into ``Profile``/``Repo`` models. Makes no business decisions — it just returns
data (docs/ARCHITECTURE.md). Uses only the primary ``language`` field from the
repo list (one call per page); a full per-repo language breakdown is deferred to
v1.0 to avoid N extra calls against the rate limit.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from resume_assistant.core.models import Profile, Repo

_API_ROOT = "https://api.github.com"
_PER_PAGE = 100  # GitHub caps page size at 100.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = 1.0
_TIMEOUT_SECONDS = 15


class GitHubError(RuntimeError):
    """Base error for GitHub client failures."""


class UserNotFoundError(GitHubError):
    """Raised when the requested username does not exist (HTTP 404)."""


class RateLimitError(GitHubError):
    """Raised when the GitHub rate limit is exhausted (HTTP 403 with no remaining)."""


class GitHubClient:
    """Thin synchronous GitHub REST client returning typed models."""

    def __init__(self, token: str | None = None) -> None:
        self._session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._session.headers.update(headers)

    def fetch_profile(self, username: str) -> Profile:
        """Fetch a user's profile plus all their public repositories.

        Raises ``UserNotFoundError`` for an unknown user and ``RateLimitError``
        when the API rate limit is exhausted.
        """
        user = self._get(f"{_API_ROOT}/users/{username}")
        repos = self._fetch_all_repos(username)
        return _to_profile(user, repos)

    def _fetch_all_repos(self, username: str) -> list[Repo]:
        """Page through the user's public repos until GitHub returns a short page."""
        repos: list[Repo] = []
        page = 1
        while True:
            batch = self._get(
                f"{_API_ROOT}/users/{username}/repos",
                params={"per_page": _PER_PAGE, "page": page, "sort": "pushed"},
            )
            if not isinstance(batch, list):
                break
            repos.extend(_to_repo(item) for item in batch)
            if len(batch) < _PER_PAGE:
                break
            page += 1
        return repos

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET with retry/backoff on transient errors, mapping known failures to typed errors."""
        last_exc: requests.RequestException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._session.get(url, params=params, timeout=_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
                continue

            if response.status_code == 404:
                raise UserNotFoundError(f"GitHub returned 404 for {url}")
            if response.status_code == 403 and _is_rate_limited(response):
                raise RateLimitError(
                    "GitHub API rate limit exceeded. Set GITHUB_TOKEN for a higher limit."
                )
            if response.status_code >= 500:
                # Transient server error — retry with backoff.
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
                continue
            if not response.ok:
                raise GitHubError(f"GitHub request failed ({response.status_code}): {url}")
            return response.json()

        if last_exc is not None:
            raise GitHubError(f"GitHub request failed after retries: {url}") from last_exc
        raise GitHubError(f"GitHub request failed after retries (server error): {url}")


def _is_rate_limited(response: requests.Response) -> bool:
    """True when a 403 is due to an exhausted rate limit rather than another forbidden reason."""
    return response.headers.get("X-RateLimit-Remaining") == "0"


def _to_repo(item: dict[str, Any]) -> Repo:
    """Map one raw repo JSON object into a Repo model."""
    return Repo(
        name=item["name"],
        description=item.get("description"),
        url=item["html_url"],
        stars=item.get("stargazers_count", 0),
        primary_language=item.get("language"),
        created_at=item.get("created_at"),
        last_pushed_at=item.get("pushed_at"),
        is_fork=item.get("fork", False),
    )


def _to_profile(user: dict[str, Any], repos: list[Repo]) -> Profile:
    """Map raw user JSON plus fetched repos into a Profile model."""
    return Profile(
        login=user["login"],
        name=user.get("name"),
        bio=user.get("bio"),
        profile_url=user["html_url"],
        public_repo_count=user.get("public_repos", 0),
        followers=user.get("followers", 0),
        repos=repos,
    )
