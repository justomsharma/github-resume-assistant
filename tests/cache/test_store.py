"""Tests for the SQLite cache and the caching claim extractor. No network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from resume_assistant.cache.store import (
    CachingClaimExtractor,
    CachingClaimVerifier,
    CachingRepoEvidenceFetcher,
    CachingSuggestionGenerator,
    SqliteCache,
)
from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    Repo,
    RepoEvidence,
    Suggestion,
)


def _cache(tmp_path: Path) -> SqliteCache:
    return SqliteCache(str(tmp_path / "nested" / "cache.db"))


def test_set_get_round_trip(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_get_miss_returns_none(tmp_path: Path) -> None:
    assert _cache(tmp_path).get("absent") is None


def test_set_overwrites(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.set("k", "one")
    cache.set("k", "two")
    assert cache.get("k") == "two"


def test_persists_across_instances(tmp_path: Path) -> None:
    path = str(tmp_path / "c.db")
    SqliteCache(path).set("k", "v")
    assert SqliteCache(path).get("k") == "v"  # a fresh instance reads the same file


class CountingExtractor:
    """Records how many times it was asked to extract (stands in for the API)."""

    def __init__(self, claims: list[Claim]) -> None:
        self._claims = claims
        self.calls = 0

    def extract_claims(self, resume_text: str) -> list[Claim]:
        self.calls += 1
        return self._claims


def test_caching_extractor_second_call_hits_cache(tmp_path: Path) -> None:
    inner = CountingExtractor([Claim(text="Built X", skills=("go",), category="project")])
    extractor = CachingClaimExtractor(inner, _cache(tmp_path), model="claude-sonnet-5")

    first = extractor.extract_claims("resume text")
    second = extractor.extract_claims("resume text")

    assert inner.calls == 1  # the API was called once; the second call was served from cache
    assert first == second
    assert second[0].text == "Built X"
    assert second[0].skills == ("go",)


def test_caching_extractor_distinct_resumes_miss(tmp_path: Path) -> None:
    inner = CountingExtractor([Claim(text="Built X")])
    extractor = CachingClaimExtractor(inner, _cache(tmp_path), model="claude-sonnet-5")

    extractor.extract_claims("resume A")
    extractor.extract_claims("resume B")

    assert inner.calls == 2  # different resume text → different key → not a cache hit


def _report(*, login: str = "octocat", gap: str = "Proficient in React") -> GapReport:
    return GapReport(
        profile_login=login,
        backed=(),
        not_shown=(
            ClaimEvidence(
                claim=Claim(text=gap),
                verdict="not_shown",
                matching_repos=(),
                cited_files=(),
                rationale="",
            ),
        ),
        not_verifiable=(),
        github_is_empty=True,
    )


def _profile() -> Profile:
    return Profile("octocat", None, None, "", 0, 0, repos=[])


class CountingSuggester:
    """Records how many times it was asked to generate (stands in for the API)."""

    def __init__(self, suggestions: list[Suggestion]) -> None:
        self._suggestions = suggestions
        self.calls = 0

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]:
        self.calls += 1
        return self._suggestions


def test_caching_suggester_second_call_hits_cache(tmp_path: Path) -> None:
    inner = CountingSuggester(
        [
            Suggestion(
                title="React app",
                what_to_build="Build it",
                proves_claim="Proficient in React",
                skills=("react",),
                size="a weekend",
                skip="auth",
            )
        ]
    )
    suggester = CachingSuggestionGenerator(inner, _cache(tmp_path), model="claude-sonnet-5")

    first = suggester.generate_suggestions(_report(), _profile())
    second = suggester.generate_suggestions(_report(), _profile())

    assert inner.calls == 1  # second call served from cache
    assert first == second
    assert second[0].title == "React app"
    assert second[0].skills == ("react",)


def test_caching_suggester_distinct_reports_miss(tmp_path: Path) -> None:
    inner = CountingSuggester([])
    suggester = CachingSuggestionGenerator(inner, _cache(tmp_path), model="claude-sonnet-5")

    suggester.generate_suggestions(_report(gap="Proficient in React"), _profile())
    suggester.generate_suggestions(_report(gap="Built a cache in Go"), _profile())

    assert inner.calls == 2  # different gap content → different key → not a cache hit


# --- CachingRepoEvidenceFetcher (v2.1) ---------------------------------------


def _repo(name: str, pushed_at: str | None, *, is_fork: bool = False) -> Repo:
    return Repo(
        name=name,
        description=None,
        url=f"https://github.com/octocat/{name}",
        stars=0,
        primary_language="Go",
        created_at=None,
        last_pushed_at=pushed_at,
        is_fork=is_fork,
    )


def _profile_with(repos: list[Repo]) -> Profile:
    return Profile("octocat", None, None, "", len(repos), 0, repos=repos)


def _evidence(name: str, pushed_at: str | None) -> RepoEvidence:
    return RepoEvidence(
        repo_name=name,
        primary_language="Go",
        language_breakdown=(("Go", 100),),
        dependencies=("dep-a",),
        notable_paths=("src/main.go",),
        file_count=3,
        readme_excerpt="# readme",
        pushed_at=pushed_at,
    )


class CountingFetcher:
    """Records how many times it fetched (stands in for the GitHub client)."""

    def __init__(self, evidence: list[RepoEvidence]) -> None:
        self._evidence = evidence
        self.calls = 0

    def fetch_repo_evidence(
        self,
        profile: Profile,
        on_repo_done: Callable[[int, int], None] | None = None,
    ) -> list[RepoEvidence]:
        self.calls += 1
        if on_repo_done is not None:
            on_repo_done(1, 1)
        return self._evidence


def test_caching_fetcher_second_call_hits_cache(tmp_path: Path) -> None:
    profile = _profile_with([_repo("go-cache", "2024-06-01T00:00:00Z")])
    inner = CountingFetcher([_evidence("go-cache", "2024-06-01T00:00:00Z")])
    fetcher = CachingRepoEvidenceFetcher(inner, _cache(tmp_path))

    first = fetcher.fetch_repo_evidence(profile)
    second = fetcher.fetch_repo_evidence(profile)

    assert inner.calls == 1  # unchanged repos → cache hit, no GitHub calls
    assert first == second
    assert second[0].repo_name == "go-cache"
    assert second[0].dependencies == ("dep-a",)


def test_caching_fetcher_forwards_callback_on_miss_not_on_hit(tmp_path: Path) -> None:
    profile = _profile_with([_repo("go-cache", "2024-06-01T00:00:00Z")])
    inner = CountingFetcher([_evidence("go-cache", "2024-06-01T00:00:00Z")])
    fetcher = CachingRepoEvidenceFetcher(inner, _cache(tmp_path))
    calls: list[tuple[int, int]] = []

    def on_done(done: int, total: int) -> None:
        calls.append((done, total))

    fetcher.fetch_repo_evidence(profile, on_repo_done=on_done)
    assert calls == [(1, 1)]  # cache miss → forwarded to the inner fetcher

    fetcher.fetch_repo_evidence(profile, on_repo_done=on_done)
    assert calls == [(1, 1)]  # cache hit → nothing to report, callback not invoked


def test_caching_fetcher_rekeys_when_a_repo_is_pushed(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    inner = CountingFetcher([_evidence("go-cache", "2024-06-01T00:00:00Z")])
    fetcher = CachingRepoEvidenceFetcher(inner, cache)

    fetcher.fetch_repo_evidence(_profile_with([_repo("go-cache", "2024-06-01T00:00:00Z")]))
    fetcher.fetch_repo_evidence(_profile_with([_repo("go-cache", "2024-07-01T00:00:00Z")]))

    assert inner.calls == 2  # a new pushed_at changes the fingerprint → re-fetch


# --- CachingClaimVerifier (v2.1) ---------------------------------------------


def _verdict(text: str) -> ClaimEvidence:
    return ClaimEvidence(
        claim=Claim(text=text, skills=("go",)),
        verdict="backed",
        matching_repos=("go-cache",),
        cited_files=("go-cache/src/main.go",),
        rationale="cited",
    )


class CountingVerifier:
    """Records how many times it graded (stands in for the Anthropic client)."""

    def __init__(self, verdicts: list[ClaimEvidence]) -> None:
        self._verdicts = verdicts
        self.calls = 0

    def verify_claims(
        self,
        claims: list[Claim],
        evidence: list[RepoEvidence],
        on_batch_done: Callable[[int, int], None] | None = None,
    ) -> list[ClaimEvidence]:
        self.calls += 1
        if on_batch_done is not None:
            on_batch_done(1, 1)
        return self._verdicts


def test_caching_verifier_second_call_hits_cache(tmp_path: Path) -> None:
    claims = [Claim(text="Built a cache in Go", skills=("go",))]
    evidence = [_evidence("go-cache", "2024-06-01T00:00:00Z")]
    inner = CountingVerifier([_verdict("Built a cache in Go")])
    verifier = CachingClaimVerifier(inner, _cache(tmp_path), model="claude-sonnet-5")

    first = verifier.verify_claims(claims, evidence)
    second = verifier.verify_claims(claims, evidence)

    assert inner.calls == 1  # same claims + evidence → cache hit
    assert first == second
    assert second[0].verdict == "backed"
    assert second[0].cited_files == ("go-cache/src/main.go",)


def test_caching_verifier_forwards_callback_on_miss_not_on_hit(tmp_path: Path) -> None:
    claims = [Claim(text="Built a cache in Go", skills=("go",))]
    evidence = [_evidence("go-cache", "2024-06-01T00:00:00Z")]
    inner = CountingVerifier([_verdict("Built a cache in Go")])
    verifier = CachingClaimVerifier(inner, _cache(tmp_path), model="claude-sonnet-5")
    calls: list[tuple[int, int]] = []

    def on_done(done: int, total: int) -> None:
        calls.append((done, total))

    verifier.verify_claims(claims, evidence, on_batch_done=on_done)
    assert calls == [(1, 1)]  # cache miss → forwarded to the inner verifier

    verifier.verify_claims(claims, evidence, on_batch_done=on_done)
    assert calls == [(1, 1)]  # cache hit → nothing to report, callback not invoked


def test_caching_verifier_rekeys_when_evidence_changes(tmp_path: Path) -> None:
    claims = [Claim(text="Built a cache in Go", skills=("go",))]
    inner = CountingVerifier([_verdict("Built a cache in Go")])
    verifier = CachingClaimVerifier(inner, _cache(tmp_path), model="claude-sonnet-5")

    verifier.verify_claims(claims, [_evidence("go-cache", "2024-06-01T00:00:00Z")])
    verifier.verify_claims(claims, [_evidence("go-cache", "2024-07-01T00:00:00Z")])

    assert inner.calls == 2  # evidence pushed_at changed → different key → re-verify
