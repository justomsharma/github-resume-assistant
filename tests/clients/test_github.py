"""Tests for the GitHub client. All HTTP is mocked with `responses` — no network."""

from __future__ import annotations

import base64
from typing import Any

import pytest
import responses

from resume_assistant.clients.github import (
    GitHubClient,
    GitHubError,
    RateLimitError,
    UserNotFoundError,
    _parse_go_mod,
    _parse_package_json,
    _parse_pyproject,
    _parse_requirements,
    _select_notable_paths,
    _truncate_readme,
)
from resume_assistant.core.models import Profile, Repo

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


# --- fetch_repo_evidence (v2.1) ----------------------------------------------


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _repo(name: str, *, is_fork: bool = False, branch: str = "main") -> Repo:
    return Repo(
        name=name,
        description=None,
        url=f"https://github.com/octocat/{name}",
        stars=0,
        primary_language="Go",
        created_at=None,
        last_pushed_at="2024-06-01T00:00:00Z",
        is_fork=is_fork,
        default_branch=branch,
    )


def _profile(repos: list[Repo]) -> Profile:
    return Profile("octocat", None, None, "https://github.com/octocat", len(repos), 0, repos=repos)


def _register_evidence(
    name: str,
    *,
    tree: list[dict[str, Any]],
    files: dict[str, str] | None = None,
    languages: dict[str, int] | None = None,
    readme: str | None = None,
    branch: str = "main",
) -> None:
    """Register the tree/contents/languages/readme responses one repo needs."""
    base = f"{_API}/repos/octocat/{name}"
    responses.add(responses.GET, f"{base}/git/trees/{branch}", json={"tree": tree}, status=200)
    for path, content in (files or {}).items():
        responses.add(
            responses.GET,
            f"{base}/contents/{path}",
            json={"content": _b64(content), "encoding": "base64"},
            status=200,
        )
    responses.add(responses.GET, f"{base}/languages", json=languages or {}, status=200)
    if readme is None:
        responses.add(responses.GET, f"{base}/readme", json={"message": "Not Found"}, status=404)
    else:
        responses.add(
            responses.GET,
            f"{base}/readme",
            json={"content": _b64(readme), "encoding": "base64"},
            status=200,
        )


@responses.activate
def test_fetch_repo_evidence_happy_path() -> None:
    _register_evidence(
        "go-cache",
        tree=[
            {"type": "blob", "path": "Dockerfile"},
            {"type": "blob", "path": "requirements.txt"},
            {"type": "blob", "path": "src/cache.py"},
            {"type": "blob", "path": "tests/test_cache.py"},
            {"type": "blob", "path": "README.md"},
            {"type": "tree", "path": "src"},  # non-blob entries are ignored
        ],
        files={"requirements.txt": "flask==2.0\nredis>=4\n# a comment\n-e .\n"},
        languages={"Python": 8000, "Shell": 200},
        readme="# go-cache\nA distributed cache.",
    )

    evidence = GitHubClient().fetch_repo_evidence(_profile([_repo("go-cache")]))

    assert len(evidence) == 1
    ev = evidence[0]
    assert ev.repo_name == "go-cache"
    assert ev.dependencies == ("flask", "redis")  # versions/comments/-e stripped
    assert ev.file_count == 5  # only blob paths counted
    assert "Dockerfile" in ev.notable_paths
    assert "src/cache.py" in ev.notable_paths and "tests/test_cache.py" in ev.notable_paths
    assert ev.language_breakdown == (("Python", 8000), ("Shell", 200))  # largest first
    assert ev.readme_excerpt is not None and "distributed cache" in ev.readme_excerpt
    assert ev.pushed_at == "2024-06-01T00:00:00Z"


@responses.activate
def test_fetch_repo_evidence_skips_forks() -> None:
    _register_evidence("mine", tree=[{"type": "blob", "path": "main.go"}], languages={"Go": 10})

    evidence = GitHubClient().fetch_repo_evidence(
        _profile([_repo("mine"), _repo("a-fork", is_fork=True)])
    )

    assert [e.repo_name for e in evidence] == ["mine"]  # the fork contributes no evidence


@responses.activate
def test_fetch_repo_evidence_missing_readme_and_manifests() -> None:
    _register_evidence(
        "bare",
        tree=[{"type": "blob", "path": "notes.txt"}],
        languages={},
        readme=None,  # 404 → absent, not an error
    )

    evidence = GitHubClient().fetch_repo_evidence(_profile([_repo("bare")]))

    assert evidence[0].dependencies == ()  # no known manifest present
    assert evidence[0].readme_excerpt is None
    assert evidence[0].file_count == 1


@responses.activate
def test_fetch_repo_evidence_reports_progress_per_repo() -> None:
    """``on_repo_done`` fires once per non-fork repo, in order, with the running count."""
    _register_evidence("one", tree=[{"type": "blob", "path": "a.py"}], languages={"Python": 1})
    _register_evidence("two", tree=[{"type": "blob", "path": "b.py"}], languages={"Python": 1})

    calls: list[tuple[int, int]] = []
    evidence = GitHubClient().fetch_repo_evidence(
        _profile([_repo("one"), _repo("two"), _repo("a-fork", is_fork=True)]),
        on_repo_done=lambda done, total: calls.append((done, total)),
    )

    assert len(evidence) == 2  # the fork is skipped, and doesn't count toward the total
    assert calls == [(1, 2), (2, 2)]


@responses.activate
def test_fetch_repo_evidence_without_callback_is_unaffected() -> None:
    """Omitting ``on_repo_done`` (the default) still fetches evidence normally."""
    _register_evidence("solo", tree=[{"type": "blob", "path": "a.py"}], languages={"Python": 1})

    evidence = GitHubClient().fetch_repo_evidence(_profile([_repo("solo")]))

    assert [e.repo_name for e in evidence] == ["solo"]


@responses.activate
def test_fetch_repo_evidence_empty_repo_tree_missing() -> None:
    base = f"{_API}/repos/octocat/empty"
    responses.add(responses.GET, f"{base}/git/trees/main", json={"message": "empty"}, status=404)
    responses.add(responses.GET, f"{base}/languages", json={}, status=200)
    responses.add(responses.GET, f"{base}/readme", json={"message": "Not Found"}, status=404)

    evidence = GitHubClient().fetch_repo_evidence(_profile([_repo("empty")]))

    assert evidence[0].file_count == 0  # empty/absent tree degrades to no paths
    assert evidence[0].notable_paths == ()


# --- manifest + path parsers (unit) ------------------------------------------


def test_parse_requirements_strips_versions_and_comments() -> None:
    content = "flask==2.0.1\nrequests>=2\n# comment\n\n-r other.txt\nhttpx[http2]~=0.27\n"
    assert _parse_requirements(content) == ["flask", "requests", "httpx"]


def test_parse_pyproject_reads_pep621_and_poetry() -> None:
    pep621 = '[project]\ndependencies = ["flask>=2", "requests"]\n'
    assert _parse_pyproject(pep621) == ["flask", "requests"]

    poetry = '[tool.poetry.dependencies]\npython = "^3.11"\nfastapi = "^0.1"\n'
    assert _parse_pyproject(poetry) == ["fastapi"]  # python itself is excluded


def test_parse_pyproject_malformed_returns_empty() -> None:
    assert _parse_pyproject("not = = valid toml [[[") == []


def test_parse_package_json_reads_both_dependency_sections() -> None:
    content = '{"dependencies": {"react": "^18"}, "devDependencies": {"jest": "^29"}}'
    assert _parse_package_json(content) == ["react", "jest"]


def test_parse_package_json_malformed_returns_empty() -> None:
    assert _parse_package_json("{not json") == []


def test_parse_go_mod_reads_single_and_block_requires() -> None:
    content = (
        "module example.com/m\n\n"
        "require github.com/gin-gonic/gin v1.9.1\n\n"
        "require (\n\tgithub.com/redis/go-redis/v9 v9.0.0\n\t// a comment\n"
        "\tgolang.org/x/sync v0.3.0\n)\n"
    )
    assert _parse_go_mod(content) == [
        "github.com/gin-gonic/gin",
        "github.com/redis/go-redis/v9",
        "golang.org/x/sync",
    ]


def test_truncate_readme_marks_the_cut() -> None:
    long_text = "x" * 5000
    trimmed = _truncate_readme(long_text)
    assert len(trimmed) < 5000
    assert trimmed.endswith("(truncated)")

    short = "# short readme"
    assert _truncate_readme(short) == short  # under the cap, untouched


def test_select_notable_paths_filters_and_caps() -> None:
    paths = ["Dockerfile", ".github/workflows/ci.yml", "src/app.py", "random.txt", "LICENSE"]
    notable = _select_notable_paths(paths)
    assert "Dockerfile" in notable
    assert ".github/workflows/ci.yml" in notable
    assert "src/app.py" in notable
    assert "random.txt" not in notable and "LICENSE" not in notable
