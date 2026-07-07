"""GitHub REST API client.

Owns HTTP calls, pagination and rate-limit/404 handling, and mapping raw JSON
into ``Profile``/``Repo`` models. Makes no business decisions — it just returns
data (docs/ARCHITECTURE.md). Uses only the primary ``language`` field from the
repo list (one call per page); a full per-repo language breakdown is deferred to
v1.0 to avoid N extra calls against the rate limit.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
import tomllib
from typing import Any

import requests

from resume_assistant.core.models import Profile, Repo, RepoEvidence

_API_ROOT = "https://api.github.com"
_PER_PAGE = 100  # GitHub caps page size at 100.
_MAX_RETRIES = 3

# Dependency-manifest files we know how to parse into a dependency name list.
_MANIFEST_FILES = ("requirements.txt", "pyproject.toml", "package.json", "go.mod")
# Bounds so one big repo can't blow the LLM token budget (docs: char budget).
_README_CHAR_CAP = 2000
_MAX_DEPS = 40
_MAX_NOTABLE_PATHS = 30
# Path markers worth surfacing as evidence of what a repo actually is/does.
_NOTABLE_BASENAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "makefile",
    "chart.yaml",
    "values.yaml",
)
_NOTABLE_PREFIXES = (
    ".github/workflows/",
    "helm/",
    "charts/",
    "k8s/",
    "kubernetes/",
    "terraform/",
    "src/",
    "tests/",
    "test/",
)
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

    def fetch_repo_evidence(self, profile: Profile) -> list[RepoEvidence]:
        """Fetch code-level facts for each of a profile's non-fork public repos.

        For every non-fork repo (no cap) this reads the recursive file tree, the
        dependency manifests present, the language breakdown, and a truncated
        README — the real code a claim gets graded against. Forks are skipped
        (they aren't evidence of the person's own work). Each repo needs several
        API calls, so an unauthenticated caller with many repos can exhaust the
        rate limit; that surfaces as ``RateLimitError`` (docs/README note).
        """
        return [
            self._fetch_one_repo_evidence(profile.login, repo)
            for repo in profile.repos
            if not repo.is_fork
        ]

    def _fetch_one_repo_evidence(self, owner: str, repo: Repo) -> RepoEvidence:
        """Assemble one repo's code-level evidence from tree, manifests, languages, README."""
        branch = repo.default_branch or "HEAD"
        paths = self._fetch_tree_paths(owner, repo.name, branch)
        dependencies = self._fetch_dependencies(owner, repo.name, branch, paths)
        return RepoEvidence(
            repo_name=repo.name,
            primary_language=repo.primary_language,
            language_breakdown=self._fetch_language_breakdown(owner, repo.name),
            dependencies=dependencies,
            notable_paths=_select_notable_paths(paths),
            file_count=len(paths),
            readme_excerpt=self._fetch_readme(owner, repo.name),
            pushed_at=repo.last_pushed_at,
        )

    def _fetch_tree_paths(self, owner: str, name: str, branch: str) -> list[str]:
        """Return every blob path in the repo's tree, or [] if the repo is empty."""
        data = self._get(
            f"{_API_ROOT}/repos/{owner}/{name}/git/trees/{branch}",
            params={"recursive": "1"},
            allow_missing=True,
        )
        if not isinstance(data, dict):
            return []
        return [
            entry["path"]
            for entry in data.get("tree", [])
            if entry.get("type") == "blob" and "path" in entry
        ]

    def _fetch_dependencies(
        self, owner: str, name: str, branch: str, paths: list[str]
    ) -> tuple[str, ...]:
        """Parse the dependency names from whichever known manifests the repo has."""
        deps: list[str] = []
        present = {p for p in paths if p.rsplit("/", 1)[-1] in _MANIFEST_FILES}
        for path in sorted(present):
            filename = path.rsplit("/", 1)[-1]
            content = self._fetch_text_file(owner, name, path, branch)
            if content is not None:
                deps.extend(_parse_manifest(filename, content))
        # De-duplicate while preserving first-seen order, then bound the list.
        seen: dict[str, None] = {}
        for dep in deps:
            seen.setdefault(dep, None)
        return tuple(seen)[:_MAX_DEPS]

    def _fetch_text_file(self, owner: str, name: str, path: str, branch: str) -> str | None:
        """Fetch and base64-decode a single file's text, or None if it's absent/binary."""
        data = self._get(
            f"{_API_ROOT}/repos/{owner}/{name}/contents/{path}",
            params={"ref": branch},
            allow_missing=True,
        )
        if not isinstance(data, dict):
            return None
        return _decode_content(data.get("content"), data.get("encoding"))

    def _fetch_language_breakdown(self, owner: str, name: str) -> tuple[tuple[str, int], ...]:
        """Fetch the byte-count-per-language breakdown, largest first."""
        data = self._get(f"{_API_ROOT}/repos/{owner}/{name}/languages", allow_missing=True)
        if not isinstance(data, dict):
            return ()
        ranked = sorted(data.items(), key=lambda kv: kv[1], reverse=True)
        return tuple((lang, int(count)) for lang, count in ranked)

    def _fetch_readme(self, owner: str, name: str) -> str | None:
        """Fetch and decode the repo's README, truncated to the char cap; None if absent."""
        data = self._get(f"{_API_ROOT}/repos/{owner}/{name}/readme", allow_missing=True)
        if not isinstance(data, dict):
            return None
        text = _decode_content(data.get("content"), data.get("encoding"))
        return _truncate_readme(text) if text is not None else None

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

    def _get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        allow_missing: bool = False,
    ) -> Any:
        """GET with retry/backoff on transient errors, mapping known failures to typed errors.

        With ``allow_missing`` a 404 returns ``None`` instead of raising — used for
        optional repo evidence (a repo may have no README, no manifests, or an empty
        tree), where absence is normal rather than a user-not-found error.
        """
        last_exc: requests.RequestException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._session.get(url, params=params, timeout=_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(_BACKOFF_BASE_SECONDS * 2**attempt)
                continue

            if response.status_code == 404:
                if allow_missing:
                    return None
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
        default_branch=item.get("default_branch"),
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


def _decode_content(content: Any, encoding: Any) -> str | None:
    """Base64-decode a GitHub contents payload into UTF-8 text, or None if it can't be."""
    if not isinstance(content, str) or encoding != "base64":
        return None
    try:
        return base64.b64decode(content).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        # Binary blob or malformed payload — not usable as text evidence.
        return None


def _truncate_readme(text: str) -> str:
    """Trim a README to the char cap, marking the cut so the excerpt reads honestly."""
    if len(text) <= _README_CHAR_CAP:
        return text
    return text[:_README_CHAR_CAP].rstrip() + "\n… (truncated)"


def _select_notable_paths(paths: list[str]) -> tuple[str, ...]:
    """Pick the paths that signal what a repo is (CI, containers, source/test layout)."""
    notable: list[str] = []
    for path in paths:
        lowered = path.lower()
        basename = lowered.rsplit("/", 1)[-1]
        if basename in _NOTABLE_BASENAMES or lowered.startswith(_NOTABLE_PREFIXES):
            notable.append(path)
        if len(notable) >= _MAX_NOTABLE_PATHS:
            break
    return tuple(notable)


def _parse_manifest(filename: str, content: str) -> list[str]:
    """Dispatch a manifest file to its parser, returning bare dependency names."""
    if filename == "requirements.txt":
        return _parse_requirements(content)
    if filename == "pyproject.toml":
        return _parse_pyproject(content)
    if filename == "package.json":
        return _parse_package_json(content)
    if filename == "go.mod":
        return _parse_go_mod(content)
    return []


def _parse_requirements(content: str) -> list[str]:
    """Extract package names from a requirements.txt, dropping versions and comments."""
    names: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        # Strip off version specifiers, extras, and environment markers.
        name = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    return names


def _parse_pyproject(content: str) -> list[str]:
    """Extract dependency names from PEP 621 and Poetry sections of a pyproject.toml."""
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return []
    names: list[str] = []
    project = data.get("project", {})
    if isinstance(project, dict):
        for spec in project.get("dependencies", []):
            if isinstance(spec, str):
                name = re.split(r"[<>=!~;\[ ]", spec, maxsplit=1)[0].strip()
                if name:
                    names.append(name)
    poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
    if isinstance(poetry, dict):
        deps = poetry.get("dependencies", {})
        if isinstance(deps, dict):
            names.extend(name for name in deps if name.lower() != "python")
    return names


def _parse_package_json(content: str) -> list[str]:
    """Extract dependency names from a package.json's dependencies + devDependencies."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section, {})
        if isinstance(deps, dict):
            names.extend(str(name) for name in deps)
    return names


def _parse_go_mod(content: str) -> list[str]:
    """Extract module paths required by a go.mod (both single-line and block form)."""
    names: list[str] = []
    in_block = False
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if in_block:
            module = line.split()[0] if line and not line.startswith("//") else ""
        elif line.startswith("require "):
            parts = line[len("require ") :].split()
            module = parts[0] if parts else ""
        else:
            module = ""
        if module:
            names.append(module)
    return names
