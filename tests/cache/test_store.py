"""Tests for the SQLite cache and the caching claim extractor. No network."""

from __future__ import annotations

from pathlib import Path

from resume_assistant.cache.store import CachingClaimExtractor, SqliteCache
from resume_assistant.core.models import Claim


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
