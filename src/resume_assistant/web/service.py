"""Orchestrate a full resume analysis for the web adapter.

This mirrors the fetch -> core sequence in ``server/app.py``'s ``suggest_projects``
tool, translating the client-layer exceptions into friendly messages so the route
stays dumb (docs/ARCHITECTURE.md, rule 4). It contains no analysis logic itself:
the gap report and the ranked plan come from ``core/`` unchanged.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from typing import TypeVar

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

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class SubProgressEvent:
    """Finer-grained progress *within* a stage (e.g. "Reading repo 14 of 52").

    Fired from ``evidence`` (per repo) and ``report`` (per verification batch) —
    the two stages that dominate wall-clock time on a large GitHub account and
    were previously silent until they finished entirely.
    """

    stage: str
    detail: str


@dataclass(frozen=True)
class ReportReady:
    """The gap report is ready, before the 30-day plan has been built.

    Lets the frontend show the report immediately instead of waiting on
    suggestion generation too — the plan usually takes several more seconds.
    """

    profile: Profile
    report: GapReport


@dataclass(frozen=True)
class Heartbeat:
    """A no-op keep-alive.

    GitHub's secondary (abuse-detection) rate limit can make a single API call
    silently retry for up to a minute at a time — with no other event to yield,
    the SSE connection would go quiet long enough for a browser/proxy to kill it
    as dead. Emitted whenever a stage goes quiet for a bit so that never happens.
    """


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

_T = TypeVar("_T")

# How long to wait for real progress before emitting a Heartbeat instead. Well
# under any reasonable browser/proxy idle-connection timeout, so a long silent
# retry (e.g. GitHub's secondary rate limit backoff) never looks like a dead
# connection to the client.
_HEARTBEAT_INTERVAL_SECONDS = 5.0


def _run_with_subprogress(
    call: Callable[[Callable[[int, int], None]], _T],
    stage: str,
    make_detail: Callable[[int, int], str],
) -> Generator[SubProgressEvent | Heartbeat, None, _T]:
    """Run a blocking, callback-driven ``call`` on a worker thread, yielding a
    ``SubProgressEvent`` each time its progress callback fires (or a
    ``Heartbeat`` if it goes quiet for a bit), then returning its result (via
    ``yield from``'s return-value channel).

    ``call`` itself is a synchronous, blocking function (a GitHub/Anthropic API
    call under the hood); a plain generator can't interleave its own ``yield``s
    with a nested blocking call, so the call runs on a background thread and
    reports progress through a queue instead. Any exception ``call`` raises is
    re-raised here on the calling thread once the worker finishes.
    """
    progress: queue.Queue[tuple[int, int] | None] = queue.Queue()
    outcome: list[_T | Exception] = []

    def on_progress(done: int, total: int) -> None:
        progress.put((done, total))

    def worker() -> None:
        try:
            outcome.append(call(on_progress))
        except Exception as exc:  # re-raised on the calling thread below
            logger.warning("stage %r failed: %r", stage, exc)
            outcome.append(exc)
        finally:
            progress.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    heartbeats = 0
    while True:
        try:
            item = progress.get(timeout=_HEARTBEAT_INTERVAL_SECONDS)
        except queue.Empty:
            heartbeats += 1
            yield Heartbeat()
            continue
        if item is None:
            break
        done, total = item
        yield SubProgressEvent(stage=stage, detail=make_detail(done, total))

    if heartbeats:
        logger.debug("stage %r: %d heartbeat(s) emitted while waiting", stage, heartbeats)

    thread.join()
    result = outcome[0]
    if isinstance(result, Exception):
        raise result
    return result


_StreamEvent = (
    ProgressEvent | SubProgressEvent | Heartbeat | ReportReady | AnalysisResult | AnalysisError
)

_UNEXPECTED_ERROR_MESSAGE = (
    "Something unexpected went wrong during analysis. Please try again — if it "
    "keeps happening, check the server logs."
)


def run_analysis_events(
    resume_text: str, username: str, config: Config
) -> Iterator[_StreamEvent]:
    """Run the analysis, yielding a ``ProgressEvent`` after each real stage.

    ``evidence`` and ``report`` — the two stages that dominate wall-clock time on
    a large GitHub account — also yield ``SubProgressEvent``s per repo/batch so
    the frontend shows continuous progress instead of sitting still; every
    external-call stage also emits ``Heartbeat``s if it goes quiet (see
    ``_run_with_subprogress``). A ``ReportReady`` event fires once the gap
    report is built, before the plan is generated, so the frontend can show it
    early. The final item yielded is always terminal: an ``AnalysisResult`` on
    success or an ``AnalysisError`` with a friendly message when GitHub or
    Anthropic fails. The empty-GitHub case is a normal success (still streams
    all stages), never an error — it's the main case for our user.
    ``run_analysis`` is the non-streaming wrapper over this generator, so the
    fetch -> core sequence lives in exactly one place.

    Any exception that isn't one of the specific ones handled below is a bug,
    not a user-facing failure mode — it's still turned into a clean
    ``AnalysisError`` rather than letting the SSE stream die mid-response with
    no explanation (docs/CODING_PRACTICES.md: never show a raw stack trace).
    """
    try:
        yield from _run_analysis_stages(resume_text, username, config)
    except Exception:  # last-resort net; specific, expected errors are handled below
        logger.exception("unhandled exception during analysis for %r", username)
        yield AnalysisError(_UNEXPECTED_ERROR_MESSAGE, 500)


def _run_analysis_stages(resume_text: str, username: str, config: Config) -> Iterator[_StreamEvent]:
    """The real stage-by-stage sequence; wrapped by ``run_analysis_events`` for safety."""
    github = GitHubClient(token=config.github_token)
    cache = SqliteCache(config.cache_path)

    # Parsing already happened synchronously in the web layer before this generator
    # started (resume_upload.extract_resume_text), so reporting it here is just
    # telling the truth about completed work, not simulating a stage.
    yield _stage_event(0)

    try:
        profile = yield from _run_with_subprogress(
            lambda _on_progress: github.fetch_profile(username),
            stage="profile",
            make_detail=lambda done, total: "",
        )
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

    evidence_fetcher = CachingRepoEvidenceFetcher(github, cache=cache)
    try:
        evidence = yield from _run_with_subprogress(
            lambda on_repo_done: evidence_fetcher.fetch_repo_evidence(profile, on_repo_done),
            stage="evidence",
            make_detail=lambda done, total: f"Reading repo {done} of {total}",
        )
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
        report = yield from _run_with_subprogress(
            lambda on_batch_done: build_gap_report(
                resume_text, profile, evidence, extractor, verifier, on_batch_done
            ),
            stage="report",
            make_detail=lambda done, total: f"Grading batch {done} of {total}",
        )
    except AnthropicError as exc:
        yield AnalysisError(f"Couldn't analyze the resume right now: {exc}", 502)
        return
    yield _stage_event(3)
    yield ReportReady(profile=profile, report=report)

    try:
        suggester = CachingSuggestionGenerator(client, cache=cache, model=config.anthropic_model)
        plan = yield from _run_with_subprogress(
            lambda _on_progress: build_project_plan(report, profile, suggester),
            stage="plan",
            make_detail=lambda done, total: "",
        )
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
