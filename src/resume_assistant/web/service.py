"""Orchestrate a full resume analysis for the web adapter.

This mirrors the fetch -> core sequence in ``server/app.py``'s ``suggest_projects``
tool, translating the client-layer exceptions into friendly messages so the route
stays dumb (docs/ARCHITECTURE.md, rule 4). It contains no analysis logic itself:
the gap report and the ranked plan come from ``core/`` unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from resume_assistant.cache.store import (
    CachingClaimExtractor,
    CachingClaimVerifier,
    CachingRepoEvidenceFetcher,
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


@dataclass(frozen=True)
class ProgressEvent:
    """One completed pipeline stage, for streaming real progress to the UI.

    ``index`` is the 1-based count of stages finished so far, so the frontend's
    progress fraction is simply ``index / total``.
    """

    stage: str
    index: int
    total: int
    label: str


# The five real stages of run_analysis_events, in order. The labels are shown in
# the loading UI's step list, so they read as user-facing progress, not internals.
_STAGES: tuple[tuple[str, str], ...] = (
    ("parsing", "Parsing your resume"),
    ("profile", "Fetching your GitHub profile"),
    ("evidence", "Reading your public repos"),
    ("report", "Matching your resume claims against your repos"),
    ("plan", "Writing your 30-day prescription"),
)
_TOTAL_STAGES = len(_STAGES)


def _stage_event(completed_index: int) -> ProgressEvent:
    """Build the ``ProgressEvent`` for the stage at ``completed_index`` (0-based)."""
    stage, label = _STAGES[completed_index]
    return ProgressEvent(stage=stage, index=completed_index + 1, total=_TOTAL_STAGES, label=label)


_RATE_LIMIT_MESSAGE = (
    "GitHub's API rate limit is exhausted. Grounding claims reads each repo's code, "
    "which is call-heavy — it resets within the hour, so try again shortly, or run "
    "this with a GITHUB_TOKEN set for a much higher limit."
)


def run_analysis_events(
    resume_text: str, username: str, config: Config
) -> Iterator[ProgressEvent | AnalysisResult | AnalysisError]:
    """Run the analysis, yielding a ``ProgressEvent`` after each real stage.

    The final item yielded is always terminal: an ``AnalysisResult`` on success
    or an ``AnalysisError`` with a friendly message when GitHub or Anthropic
    fails. The empty-GitHub case is a normal success (still streams all four
    stages), never an error — it's the main case for our user. ``run_analysis``
    is the non-streaming wrapper over this generator, so the fetch -> core
    sequence lives in exactly one place.
    """
    github = GitHubClient(token=config.github_token)
    cache = SqliteCache(config.cache_path)

    # Parsing already happened synchronously in the web layer before this generator
    # started (resume_upload.extract_resume_text), so reporting it here is just
    # telling the truth about completed work, not simulating a stage.
    yield _stage_event(0)

    try:
        profile = github.fetch_profile(username)
    except UserNotFoundError:
        yield AnalysisError(f"No GitHub user found with the username '{username}'.", 404)
        return
    except RateLimitError:
        yield AnalysisError(_RATE_LIMIT_MESSAGE, 503)
        return
    except GitHubError as exc:
        yield AnalysisError(f"Couldn't fetch GitHub data right now: {exc}", 502)
        return
    yield _stage_event(1)

    try:
        evidence = CachingRepoEvidenceFetcher(github, cache=cache).fetch_repo_evidence(profile)
    except RateLimitError:
        yield AnalysisError(_RATE_LIMIT_MESSAGE, 503)
        return
    except GitHubError as exc:
        yield AnalysisError(f"Couldn't fetch GitHub data right now: {exc}", 502)
        return
    yield _stage_event(2)

    try:
        client = AnthropicClient(api_key=config.anthropic_api_key, model=config.anthropic_model)
        extractor = CachingClaimExtractor(client, cache=cache, model=config.anthropic_model)
        verifier = CachingClaimVerifier(client, cache=cache, model=config.anthropic_model)
        report = build_gap_report(resume_text, profile, evidence, extractor, verifier)
    except AnthropicError as exc:
        yield AnalysisError(f"Couldn't analyze the resume right now: {exc}", 502)
        return
    yield _stage_event(3)

    try:
        suggester = CachingSuggestionGenerator(client, cache=cache, model=config.anthropic_model)
        plan = build_project_plan(report, profile, suggester)
    except AnthropicError as exc:
        yield AnalysisError(f"Couldn't analyze the resume right now: {exc}", 502)
        return
    yield _stage_event(4)

    yield AnalysisResult(profile=profile, report=report, plan=plan)


def run_analysis(resume_text: str, username: str, config: Config) -> AnalysisResult | AnalysisError:
    """Fetch the profile, build the gap report, and rank the plan (non-streaming).

    Thin wrapper over ``run_analysis_events``: it drives the generator to its
    terminal item and returns that, discarding the intermediate progress events.
    """
    outcome: AnalysisResult | AnalysisError | None = None
    for event in run_analysis_events(resume_text, username, config):
        if isinstance(event, (AnalysisResult, AnalysisError)):
            outcome = event
    if outcome is None:  # pragma: no cover - the generator always yields a terminal item
        raise RuntimeError("run_analysis_events did not yield a terminal result")
    return outcome
