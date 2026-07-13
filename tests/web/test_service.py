"""Tests for the web service orchestration. GitHub + Anthropic are mocked."""

from __future__ import annotations

import time

import pytest
from pytest_mock import MockerFixture

from resume_assistant.clients.github import GitHubError, RateLimitError, UserNotFoundError
from resume_assistant.config import Config
from resume_assistant.core.models import GapReport, Profile, ProjectPlan
from resume_assistant.web import service
from resume_assistant.web.service import (
    AnalysisError,
    AnalysisResult,
    Heartbeat,
    ProgressEvent,
    ReportReady,
    SubProgressEvent,
    _run_with_subprogress,
    run_analysis,
    run_analysis_events,
)


@pytest.fixture
def config() -> Config:
    return Config(
        github_token=None,
        anthropic_api_key="test-key",
        anthropic_model="claude-sonnet-5",
        cache_path=":memory:",
        frontend_origin="http://127.0.0.1:3000",
    )


def _patch_profile(mocker: MockerFixture, profile: Profile) -> None:
    """Make GitHubClient().fetch_profile return the given profile."""
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.return_value = profile


def _stub_anthropic(mocker: MockerFixture) -> None:
    """Neutralize the Anthropic-backed pieces so no network/keys are needed."""
    mocker.patch.object(service, "AnthropicClient")
    mocker.patch.object(service, "SqliteCache")
    mocker.patch.object(service, "CachingClaimExtractor")
    mocker.patch.object(service, "CachingClaimVerifier")
    mocker.patch.object(service, "CachingRepoEvidenceFetcher")
    mocker.patch.object(service, "CachingSuggestionGenerator")


def test_happy_path_returns_result(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="octocat",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=False,
    )
    plan = ProjectPlan(profile_login="octocat", suggestions=(), github_is_empty=False)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisResult)
    assert outcome.report is report
    assert outcome.plan is plan
    assert outcome.profile is profile_with_repos


def test_empty_github_is_a_success_not_an_error(
    mocker: MockerFixture, config: Config, empty_profile: Profile
) -> None:
    """Our real user: an empty GitHub must be a normal result, never an error."""
    _patch_profile(mocker, empty_profile)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="newgrad",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=True,
    )
    plan = ProjectPlan(profile_login="newgrad", suggestions=(), github_is_empty=True)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    outcome = run_analysis("resume text", "newgrad", config)

    assert isinstance(outcome, AnalysisResult)
    assert outcome.report.github_is_empty is True


def test_user_not_found_maps_to_404(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = UserNotFoundError("nope")

    outcome = run_analysis("resume text", "ghost", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 404
    assert "ghost" in outcome.message


def test_rate_limit_maps_to_503(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = RateLimitError("limited")

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 503
    assert "rate limit" in outcome.message.lower()


def test_generic_github_error_maps_to_502(mocker: MockerFixture, config: Config) -> None:
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = GitHubError("boom")

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 502


def test_anthropic_failure_maps_to_502(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    from resume_assistant.clients.anthropic import AnthropicError

    mocker.patch.object(service, "build_gap_report", side_effect=AnthropicError("overloaded"))

    outcome = run_analysis("resume text", "octocat", config)

    assert isinstance(outcome, AnalysisError)
    assert outcome.status == 502


# --- _run_with_subprogress: threaded progress helper -------------------------


def test_run_with_subprogress_yields_events_then_returns_value() -> None:
    def call(on_progress: object) -> str:
        on_progress(1, 3)  # type: ignore[operator]
        on_progress(2, 3)  # type: ignore[operator]
        on_progress(3, 3)  # type: ignore[operator]
        return "done"

    gen = _run_with_subprogress(call, stage="evidence", make_detail=lambda d, t: f"{d}/{t}")
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    assert events == [
        SubProgressEvent(stage="evidence", detail="1/3"),
        SubProgressEvent(stage="evidence", detail="2/3"),
        SubProgressEvent(stage="evidence", detail="3/3"),
    ]
    assert result == "done"


def test_run_with_subprogress_with_no_progress_calls_just_returns() -> None:
    gen = _run_with_subprogress(
        lambda _on_progress: 42, stage="report", make_detail=lambda d, t: ""
    )

    events = list(gen)  # no StopIteration.value access needed when only checking events

    assert events == []


def test_run_with_subprogress_emits_heartbeats_when_quiet(mocker: MockerFixture) -> None:
    """A long silent stretch (e.g. a rate-limit backoff) still sends periodic keep-alives."""
    mocker.patch.object(service, "_HEARTBEAT_INTERVAL_SECONDS", 0.02)

    def call(on_progress: object) -> str:
        time.sleep(0.1)  # several heartbeat intervals with nothing to report
        on_progress(1, 1)  # type: ignore[operator]
        return "done"

    gen = _run_with_subprogress(call, stage="evidence", make_detail=lambda d, t: f"{d}/{t}")
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    # Every event but the last is a heartbeat.
    assert events[:-1] == [Heartbeat()] * (len(events) - 1)
    assert events[-1] == SubProgressEvent(stage="evidence", detail="1/1")
    assert len(events) >= 3  # 0.1s of silence over a 0.02s interval → several heartbeats
    assert result == "done"


def test_run_with_subprogress_reraises_the_calls_exception() -> None:
    def call(on_progress: object) -> str:
        on_progress(1, 2)  # type: ignore[operator]
        raise GitHubError("boom")

    gen = _run_with_subprogress(call, stage="evidence", make_detail=lambda d, t: f"{d}/{t}")

    first = next(gen)
    assert first == SubProgressEvent(stage="evidence", detail="1/2")
    with pytest.raises(GitHubError, match="boom"):
        next(gen)


# --- run_analysis_events: real streamed progress -----------------------------


def test_events_yield_four_stages_then_result(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    """Success streams a ProgressEvent per real stage (in order) then the result."""
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="octocat",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=False,
    )
    plan = ProjectPlan(profile_login="octocat", suggestions=(), github_is_empty=False)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    events = list(run_analysis_events("resume text", "octocat", config))

    progress = [e for e in events if isinstance(e, ProgressEvent)]
    report_ready = [e for e in events if isinstance(e, ReportReady)]
    terminal = events[-1]
    assert [e.stage for e in progress] == ["parsing", "profile", "evidence", "report", "plan"]
    assert [e.index for e in progress] == [1, 2, 3, 4, 5]
    assert all(e.total == 5 for e in progress)
    # The report is ready (and streamed) right after its stage, before the plan is built.
    assert len(report_ready) == 1
    assert report_ready[0].report is report
    assert events.index(report_ready[0]) == events.index(
        next(e for e in progress if e.stage == "report")
    ) + 1
    assert isinstance(terminal, AnalysisResult)
    assert terminal.report is report
    assert terminal.plan is plan


def test_events_stream_subprogress_within_evidence_and_report_stages(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    """Sub-progress from evidence-fetching and claim-verification reaches the SSE stream."""
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="octocat", backed=(), not_shown=(), not_verifiable=(), github_is_empty=False
    )
    plan = ProjectPlan(profile_login="octocat", suggestions=(), github_is_empty=False)

    def fake_fetch_evidence(profile: Profile, on_repo_done: object = None) -> list[object]:
        if on_repo_done is not None:
            on_repo_done(1, 2)  # type: ignore[operator]
            on_repo_done(2, 2)  # type: ignore[operator]
        return []

    mocker.patch.object(
        service, "CachingRepoEvidenceFetcher"
    ).return_value.fetch_repo_evidence.side_effect = fake_fetch_evidence

    def fake_build_gap_report(
        resume_text: str,
        profile: Profile,
        evidence: list[object],
        extractor: object,
        verifier: object,
        on_verify_batch_done: object = None,
    ) -> GapReport:
        if on_verify_batch_done is not None:
            on_verify_batch_done(1, 1)  # type: ignore[operator]
        return report

    mocker.patch.object(service, "build_gap_report", side_effect=fake_build_gap_report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    events = list(run_analysis_events("resume text", "octocat", config))
    subprogress = [e for e in events if isinstance(e, SubProgressEvent)]

    assert subprogress == [
        SubProgressEvent(stage="evidence", detail="Reading repo 1 of 2"),
        SubProgressEvent(stage="evidence", detail="Reading repo 2 of 2"),
        SubProgressEvent(stage="report", detail="Grading batch 1 of 1"),
    ]
    # Sub-progress for a stage arrives before that stage's ProgressEvent completion marker.
    progress = [e for e in events if isinstance(e, ProgressEvent)]
    evidence_progress_index = events.index(next(e for e in progress if e.stage == "evidence"))
    assert events.index(subprogress[1]) < evidence_progress_index


def test_events_empty_github_still_streams_all_stages(
    mocker: MockerFixture, config: Config, empty_profile: Profile
) -> None:
    """Our real user: an empty GitHub still streams all four stages to a result."""
    _patch_profile(mocker, empty_profile)
    _stub_anthropic(mocker)
    report = GapReport(
        profile_login="newgrad",
        backed=(),
        not_shown=(),
        not_verifiable=(),
        github_is_empty=True,
    )
    plan = ProjectPlan(profile_login="newgrad", suggestions=(), github_is_empty=True)
    mocker.patch.object(service, "build_gap_report", return_value=report)
    mocker.patch.object(service, "build_project_plan", return_value=plan)

    events = list(run_analysis_events("resume text", "newgrad", config))

    progress = [e for e in events if isinstance(e, ProgressEvent)]
    assert [e.stage for e in progress] == ["parsing", "profile", "evidence", "report", "plan"]
    assert isinstance(events[-1], AnalysisResult)
    assert events[-1].report.github_is_empty is True


def test_events_error_before_first_stage_yields_only_error(
    mocker: MockerFixture, config: Config
) -> None:
    """A failure fetching the profile terminates with an error after only the parsing stage."""
    instance = mocker.patch.object(service, "GitHubClient").return_value
    instance.fetch_profile.side_effect = UserNotFoundError("nope")

    events = list(run_analysis_events("resume text", "ghost", config))

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent) and events[0].stage == "parsing"
    assert isinstance(events[1], AnalysisError)
    assert events[1].status == 404


def test_events_anthropic_error_terminates_after_partial_progress(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    """Later-stage failures still emit the earlier stages' progress first."""
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    from resume_assistant.clients.anthropic import AnthropicError

    mocker.patch.object(service, "build_gap_report", side_effect=AnthropicError("overloaded"))

    events = list(run_analysis_events("resume text", "octocat", config))

    # parsing + profile + evidence streamed before the report stage failed.
    assert [e.stage for e in events[:-1]] == ["parsing", "profile", "evidence"]
    assert isinstance(events[-1], AnalysisError)
    assert events[-1].status == 502


def test_events_unexpected_exception_yields_clean_error_not_a_crash(
    mocker: MockerFixture, config: Config, profile_with_repos: Profile
) -> None:
    """A bug (an exception type we don't explicitly handle) still ends the stream cleanly.

    Regression guard: previously an exception outside the known GitHub/Anthropic
    types would propagate out of the generator uncaught, killing the SSE stream
    mid-response with no explanation (surfaces to the frontend as a generic
    network error instead of an honest message).
    """
    _patch_profile(mocker, profile_with_repos)
    _stub_anthropic(mocker)
    mocker.patch.object(service, "build_gap_report", side_effect=ValueError("unexpected bug"))

    events = list(run_analysis_events("resume text", "octocat", config))

    assert [e.stage for e in events if isinstance(e, ProgressEvent)] == [
        "parsing",
        "profile",
        "evidence",
    ]
    assert isinstance(events[-1], AnalysisError)
    assert events[-1].status == 500
    assert "unexpected" in events[-1].message.lower()
