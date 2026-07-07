"""Load and validate configuration from environment variables.

All secrets flow through here — no ``os.getenv`` scattered in business logic
(see docs/ARCHITECTURE.md, rule 3). ``.env`` is loaded if present so local dev
mirrors production without committing secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
_DEFAULT_CACHE_PATH = os.path.join(os.getcwd(), ".cache", "resume_assistant.db")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Resolved settings for the server.

    ``github_token`` is optional: the GitHub REST API works unauthenticated,
    just with a lower rate limit. ``anthropic_api_key`` is required for
    ``analyze_resume`` (v0.2); ``cache_path`` is where the SQLite cache lives.
    """

    github_token: str | None
    anthropic_api_key: str | None
    anthropic_model: str
    cache_path: str


def _load_dotenv() -> None:
    """Populate os.environ from a local .env file if one exists.

    Kept dependency-free: a minimal ``KEY=value`` parser is enough for dev and
    avoids pulling in python-dotenv for the walking skeleton. Existing
    environment variables always win over the file.
    """
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_config() -> Config:
    """Read settings from the environment (and .env), returning a validated Config."""
    _load_dotenv()
    return Config(
        github_token=os.environ.get("GITHUB_TOKEN") or None,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL") or _DEFAULT_ANTHROPIC_MODEL,
        cache_path=os.environ.get("CACHE_PATH") or _DEFAULT_CACHE_PATH,
    )
