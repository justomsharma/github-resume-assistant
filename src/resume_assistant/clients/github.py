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
# Exponential backoff for transient errors: delay = base * 2**attempt, matching
# the Anthropic client's convention (clients/anthropic.py).
_BACKOFF_BASE_SECONDS = 1.0
_TIMEOUT_SECONDS = 15
# Longest Retry-After we'll wait out before raising instead. Short secondary
# rate limits (seconds) are worth retrying; a long/primary limit (up to an hour)
# would hang the MCP call, so we surface a friendly error instead.
_MAX_RETRY_AFTER_SECONDS = 60


class GitHubError(RuntimeError):
    """Base error for GitHub client failures."""


class UserNotFoundError(GitHubError):
    """Raised when the requested username does not exist (HTTP 404)."""


class RateLimitError(GitHubError):
    """Raised on a GitHub rate limit that isn't worth waiting out.

    Covers a primary limit (403/429 with ``X-RateLimit-Remaining: 0``) and a
    secondary limit whose ``Retry-After`` exceeds ``_MAX_RETRY_AFTER_SECONDS``.
    """


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
                time.sleep(_BACKOFF_BASE_SECONDS * 2**attempt)
                continue

            if response.status_code == 404:
                raise UserNotFoundError(f"GitHub returned 404 for {url}")
            if _is_rate_limited(response):
                # A short secondary limit (Retry-After within cap) is worth waiting
                # out and retrying; a long or primary limit is surfaced as an error.
                retry_after = _retry_after_seconds(response)
                if retry_after is not None and retry_after <= _MAX_RETRY_AFTER_SECONDS:
                    time.sleep(retry_after)
                    continue
                raise RateLimitError(_rate_limit_message(response, retry_after))
            if response.status_code >= 500:
                # Transient server error — retry with backoff.
                time.sleep(_BACKOFF_BASE_SECONDS * 2**attempt)
                continue
            if not response.ok:
                raise GitHubError(f"GitHub request failed ({response.status_code}): {url}")
            return response.json()

        if last_exc is not None:
            raise GitHubError(f"GitHub request failed after retries: {url}") from last_exc
        # Retries exhausted while backing off a short secondary rate limit or 5xx.
        raise GitHubError(f"GitHub request failed after {_MAX_RETRIES} retries: {url}")


def _is_rate_limited(response: requests.Response) -> bool:
    """True when a 403/429 is a rate limit rather than another forbidden reason.

    GitHub signals a rate limit two ways: the primary limit exhausts
    ``X-RateLimit-Remaining`` to ``0``, while secondary limits reply with a
    ``Retry-After`` header. Either, on a 403 or 429, means we're throttled.
    """
    if response.status_code not in (403, 429):
        return False
    return response.headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in response.headers


def _retry_after_seconds(response: requests.Response) -> int | None:
    """Parse the ``Retry-After`` header as whole seconds, if present and numeric.

    GitHub sends ``Retry-After`` as an integer number of seconds for secondary
    rate limits. A missing or non-numeric value returns ``None``.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _rate_limit_message(response: requests.Response, retry_after: int | None) -> str:
    """Build a friendly rate-limit error, noting the wait time and the token hint."""
    hint = "Set GITHUB_TOKEN for a much higher limit, then try again."
    if retry_after is not None:
        return f"GitHub rate limit hit; retry after {retry_after}s. {hint}"
    reset = response.headers.get("X-RateLimit-Reset")
    if reset:
        return f"GitHub API rate limit exceeded (resets at epoch {reset}). {hint}"
    return f"GitHub API rate limit exceeded. {hint}"


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
