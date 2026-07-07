"""Orchestrate a full resume analysis for the web adapter.

This mirrors the fetch -> core sequence in ``server/app.py``'s ``suggest_projects``
tool, translating the client-layer exceptions into friendly messages so the route
stays dumb (docs/ARCHITECTURE.md, rule 4). It contains no analysis logic itself:
the gap report and the ranked plan come from ``core/`` unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from resume_assistant.cache.store import (
    CachingClaimExtractor,
    CachingSuggestionGenerator,
    SqliteCache,
)
from resume_assistant.clients.anthropic import AnthropicClient, AnthropicError
from resume_assistant.clients.github import (
    GitHubClient,
    GitHubError,
    RateLimitError,
    UserNotFoundError,
)
from resume_assistant.config import Config
from resume_assistant.core.analysis import build_gap_report
from resume_assistant.core.models import GapReport, Profile, ProjectPlan
from resume_assistant.core.suggestions import build_project_plan


@dataclass(frozen=True)
class AnalysisResult:
    """A successful analysis: the profile, its gap report, and the ranked plan."""

    profile: Profile
    report: GapReport
    plan: ProjectPlan


@dataclass(frozen=True)
class AnalysisError:
    """A friendly, user-facing failure message plus its HTTP status code."""

    message: str
    status: int


_RATE_LIMIT_MESSAGE = (
    "GitHub's API rate limit is exhausted. It resets within the hour — try again "
    "shortly, or run this with a GITHUB_TOKEN set for a much higher limit."
)


def run_analysis(resume_text: str, username: str, config: Config) -> AnalysisResult | AnalysisError:
    """Fetch the profile, build the gap report, and rank the plan.

    Returns an ``AnalysisResult`` on success or an ``AnalysisError`` with a
    friendly message when GitHub or Anthropic fails. The empty-GitHub case is a
    normal success (an ``AnalysisResult`` with ``github_is_empty`` set), never an
    error — it's the main case for our user.
    """
    github = GitHubClient(token=config.github_token)
    try:
        profile = github.fetch_profile(username)
    except UserNotFoundError:
        return AnalysisError(f"No GitHub user found with the username '{username}'.", 404)
    except RateLimitError:
        return AnalysisError(_RATE_LIMIT_MESSAGE, 503)
    except GitHubError as exc:
        return AnalysisError(f"Couldn't fetch GitHub data right now: {exc}", 502)

    try:
        cache = SqliteCache(config.cache_path)
        client = AnthropicClient(api_key=config.anthropic_api_key, model=config.anthropic_model)
        extractor = CachingClaimExtractor(client, cache=cache, model=config.anthropic_model)
        report = build_gap_report(resume_text, profile, extractor)
        suggester = CachingSuggestionGenerator(client, cache=cache, model=config.anthropic_model)
        plan = build_project_plan(report, profile, suggester)
    except AnthropicError as exc:
        return AnalysisError(f"Couldn't analyze the resume right now: {exc}", 502)

    return AnalysisResult(profile=profile, report=report, plan=plan)
