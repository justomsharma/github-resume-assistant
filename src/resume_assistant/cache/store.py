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
from contextlib import closing
from typing import Protocol

from resume_assistant.core.models import Claim

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


def _serialize_claims(claims: list[Claim]) -> str:
    """Serialize claims to a JSON string for storage."""
    return json.dumps(
        [
            {"text": c.text, "skills": list(c.skills), "category": c.category}
            for c in claims
        ]
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
