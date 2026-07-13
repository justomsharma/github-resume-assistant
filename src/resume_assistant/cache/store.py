"""SQLite key/value cache so repeated analyses don't re-hit the GitHub/Anthropic APIs.

Stores opaque string values keyed by a caller-computed key (docs/ARCHITECTURE.md:
the cache makes no business decisions — callers decide what to key on and how to
serialize). Used in dev to avoid burning API quota on re-runs of the same resume.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from typing import Protocol

from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    RepoEvidence,
    Suggestion,
    Verdict,
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


class SqliteCache:
    """A tiny string→string cache backed by a SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(_CREATE_TABLE)

    def get(self, key: str) -> str | None:
        """Return the cached value for ``key``, or ``None`` on a miss."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row is not None else None

    def set(self, key: str, value: str) -> None:
        """Store ``value`` under ``key``, overwriting any existing entry."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO cache (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a connection; ``closing`` closes it, the ``conn`` block commits."""
        return sqlite3.connect(self._path)


class ClaimExtractorProtocol(Protocol):
    """Structural stand-in: anything with ``extract_claims(str) -> list[Claim]``."""

    def extract_claims(self, resume_text: str) -> list[Claim]: ...


class CachingClaimExtractor:
    """Wrap a claim extractor so identical resumes don't re-hit the paid API.

    Claims are keyed on the model id plus a hash of the resume text: re-analyzing
    the same resume returns cached claims (no Anthropic call), while the GitHub
    profile is always re-fetched so the report reflects current repos.
    Satisfies ``core.analysis.ClaimExtractor`` structurally.
    """

    def __init__(self, inner: ClaimExtractorProtocol, cache: SqliteCache, model: str) -> None:
        self._inner = inner
        self._cache = cache
        self._model = model

    def extract_claims(self, resume_text: str) -> list[Claim]:
        """Return cached claims for this resume, or extract and cache them."""
        key = self._key(resume_text)
        cached = self._cache.get(key)
        if cached is not None:
            return _deserialize_claims(cached)

        claims = self._inner.extract_claims(resume_text)
        self._cache.set(key, _serialize_claims(claims))
        return claims

    def _key(self, resume_text: str) -> str:
        """Cache key: model id + a stable hash of the resume text."""
        digest = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
        return f"claims:{self._model}:{digest}"


class SuggestionGeneratorProtocol(Protocol):
    """Structural stand-in: anything that proposes candidate projects for a gap report."""

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]: ...


class CachingSuggestionGenerator:
    """Wrap a suggestion generator so identical inputs don't re-hit the paid API.

    Suggestions are keyed on the model id plus a hash of the gap report's content
    (login, empty flag, and the supported/unsupported claim texts): the same gap
    report yields cached candidates with no Anthropic call. Ranking still happens
    downstream in ``core/suggestions.py``, so cached candidates re-rank freely.
    Satisfies ``core.suggestions.SuggestionGenerator`` structurally.
    """

    def __init__(self, inner: SuggestionGeneratorProtocol, cache: SqliteCache, model: str) -> None:
        self._inner = inner
        self._cache = cache
        self._model = model

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]:
        """Return cached candidates for this gap report, or generate and cache them."""
        key = self._key(gap_report)
        cached = self._cache.get(key)
        if cached is not None:
            return _deserialize_suggestions(cached)

        suggestions = self._inner.generate_suggestions(gap_report, profile)
        self._cache.set(key, _serialize_suggestions(suggestions))
        return suggestions

    def _key(self, gap_report: GapReport) -> str:
        """Cache key: model id + a stable hash of the gap report's content."""
        fingerprint = json.dumps(
            {
                "login": gap_report.profile_login,
                "empty": gap_report.github_is_empty,
                "supported": sorted(e.claim.text for e in gap_report.supported),
                "unsupported": sorted(e.claim.text for e in gap_report.unsupported),
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        return f"suggestions:{self._model}:{digest}"


class RepoEvidenceFetcherProtocol(Protocol):
    """Structural stand-in: anything that fetches code-level evidence for a profile."""

    def fetch_repo_evidence(
        self,
        profile: Profile,
        on_repo_done: Callable[[int, int], None] | None = None,
    ) -> list[RepoEvidence]: ...


class CachingRepoEvidenceFetcher:
    """Wrap an evidence fetcher so unchanged repos don't re-hit the GitHub API.

    Evidence is keyed on a fingerprint of each repo's ``(name, pushed_at)``: it
    only changes when a repo is pushed to, so a re-run over the same profile
    returns cached evidence with no GitHub calls. The key is model-independent —
    this is GitHub data, not model output. Satisfies
    ``core.analysis``'s evidence-fetch dependency structurally.
    """

    def __init__(self, inner: RepoEvidenceFetcherProtocol, cache: SqliteCache) -> None:
        self._inner = inner
        self._cache = cache

    def fetch_repo_evidence(
        self,
        profile: Profile,
        on_repo_done: Callable[[int, int], None] | None = None,
    ) -> list[RepoEvidence]:
        """Return cached evidence for this profile's repos, or fetch and cache it.

        ``on_repo_done`` is only invoked on a cache miss — a cache hit has no
        per-repo work to report progress on.
        """
        key = self._key(profile)
        cached = self._cache.get(key)
        if cached is not None:
            return _deserialize_evidence(cached)

        evidence = self._inner.fetch_repo_evidence(profile, on_repo_done)
        self._cache.set(key, _serialize_evidence(evidence))
        return evidence

    def _key(self, profile: Profile) -> str:
        """Cache key: a stable hash of each non-fork repo's name + last-push time."""
        fingerprint = json.dumps(
            {
                "login": profile.login,
                "repos": sorted([r.name, r.last_pushed_at] for r in profile.repos if not r.is_fork),
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        return f"evidence:{digest}"


class ClaimVerifierProtocol(Protocol):
    """Structural stand-in: anything that grades claims against repo evidence."""

    def verify_claims(
        self,
        claims: list[Claim],
        evidence: list[RepoEvidence],
        on_batch_done: Callable[[int, int], None] | None = None,
    ) -> list[ClaimEvidence]: ...


class CachingClaimVerifier:
    """Wrap a claim verifier so identical (claims, evidence) don't re-hit the paid API.

    Verdicts are keyed on the model id plus a hash of the claim texts and the
    evidence fingerprint (repo names + push times): the same claims graded against
    the same code return cached verdicts with no Anthropic call. Satisfies
    ``core.analysis.ClaimVerifier`` structurally.
    """

    def __init__(self, inner: ClaimVerifierProtocol, cache: SqliteCache, model: str) -> None:
        self._inner = inner
        self._cache = cache
        self._model = model

    def verify_claims(
        self,
        claims: list[Claim],
        evidence: list[RepoEvidence],
        on_batch_done: Callable[[int, int], None] | None = None,
    ) -> list[ClaimEvidence]:
        """Return cached verdicts for these claims + evidence, or verify and cache them.

        ``on_batch_done`` is only invoked on a cache miss — a cache hit has no
        per-batch work to report progress on.
        """
        key = self._key(claims, evidence)
        cached = self._cache.get(key)
        if cached is not None:
            return _deserialize_claim_evidence(cached)

        verdicts = self._inner.verify_claims(claims, evidence, on_batch_done)
        self._cache.set(key, _serialize_claim_evidence(verdicts))
        return verdicts

    def _key(self, claims: list[Claim], evidence: list[RepoEvidence]) -> str:
        """Cache key: model id + a stable hash of the claim texts and evidence identity."""
        fingerprint = json.dumps(
            {
                "claims": [c.text for c in claims],
                "evidence": sorted([e.repo_name, e.pushed_at] for e in evidence),
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        return f"verdicts:{self._model}:{digest}"


def _serialize_evidence(evidence: list[RepoEvidence]) -> str:
    """Serialize repo evidence to a JSON string for storage."""
    return json.dumps(
        [
            {
                "repo_name": e.repo_name,
                "primary_language": e.primary_language,
                "language_breakdown": [list(pair) for pair in e.language_breakdown],
                "dependencies": list(e.dependencies),
                "notable_paths": list(e.notable_paths),
                "file_count": e.file_count,
                "readme_excerpt": e.readme_excerpt,
                "pushed_at": e.pushed_at,
            }
            for e in evidence
        ]
    )


def _deserialize_evidence(raw: str) -> list[RepoEvidence]:
    """Rebuild RepoEvidence models from a stored JSON string."""
    return [
        RepoEvidence(
            repo_name=item["repo_name"],
            primary_language=item.get("primary_language"),
            language_breakdown=tuple(
                (str(lang), int(count)) for lang, count in item.get("language_breakdown", [])
            ),
            dependencies=tuple(item.get("dependencies", [])),
            notable_paths=tuple(item.get("notable_paths", [])),
            file_count=item.get("file_count", 0),
            readme_excerpt=item.get("readme_excerpt"),
            pushed_at=item.get("pushed_at"),
        )
        for item in json.loads(raw)
    ]


def _serialize_claim_evidence(evidence: list[ClaimEvidence]) -> str:
    """Serialize graded claim evidence to a JSON string for storage."""
    return json.dumps(
        [
            {
                "claim": {
                    "text": e.claim.text,
                    "skills": list(e.claim.skills),
                    "category": e.claim.category,
                },
                "verdict": e.verdict,
                "matching_repos": list(e.matching_repos),
                "cited_files": list(e.cited_files),
                "rationale": e.rationale,
            }
            for e in evidence
        ]
    )


def _deserialize_claim_evidence(raw: str) -> list[ClaimEvidence]:
    """Rebuild ClaimEvidence models from a stored JSON string."""
    result: list[ClaimEvidence] = []
    for item in json.loads(raw):
        claim_data = item["claim"]
        verdict: Verdict = item["verdict"]
        result.append(
            ClaimEvidence(
                claim=Claim(
                    text=claim_data["text"],
                    skills=tuple(claim_data.get("skills", [])),
                    category=claim_data.get("category", "other"),
                ),
                verdict=verdict,
                matching_repos=tuple(item.get("matching_repos", [])),
                cited_files=tuple(item.get("cited_files", [])),
                rationale=item.get("rationale", ""),
            )
        )
    return result


def _serialize_claims(claims: list[Claim]) -> str:
    """Serialize claims to a JSON string for storage."""
    return json.dumps(
        [{"text": c.text, "skills": list(c.skills), "category": c.category} for c in claims]
    )


def _deserialize_claims(raw: str) -> list[Claim]:
    """Rebuild Claim models from a stored JSON string."""
    return [
        Claim(
            text=item["text"],
            skills=tuple(item.get("skills", [])),
            category=item.get("category", "other"),
        )
        for item in json.loads(raw)
    ]


def _serialize_suggestions(suggestions: list[Suggestion]) -> str:
    """Serialize suggestions to a JSON string for storage."""
    return json.dumps(
        [
            {
                "title": s.title,
                "what_to_build": s.what_to_build,
                "proves_claim": s.proves_claim,
                "skills": list(s.skills),
                "size": s.size,
                "skip": s.skip,
            }
            for s in suggestions
        ]
    )


def _deserialize_suggestions(raw: str) -> list[Suggestion]:
    """Rebuild Suggestion models from a stored JSON string."""
    return [
        Suggestion(
            title=item["title"],
            what_to_build=item["what_to_build"],
            proves_claim=item.get("proves_claim", ""),
            skills=tuple(item.get("skills", [])),
            size=item.get("size", "a week"),
            skip=item.get("skip", ""),
        )
        for item in json.loads(raw)
    ]
