"""Tests for the Flask web adapter. The service (and thus all external APIs)
is mocked — routes are tested for the three UI states and their error paths."""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient
from pytest_mock import MockerFixture

from resume_assistant.config import Config
from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    ProjectPlan,
    Suggestion,
)
from resume_assistant.web import app as webapp
from resume_assistant.web.service import AnalysisError, AnalysisResult


@pytest.fixture
def client() -> FlaskClient:
    config = Config(
        github_token=None,
        anthropic_api_key="test-key",
        anthropic_model="claude-sonnet-5",
        cache_path=":memory:",
    )
    return webapp.create_app(config).test_client()


def _result(
    profile: Profile, empty: bool, supported=(), unsupported=(), suggestions=()
) -> AnalysisResult:
    report = GapReport(
        profile_login=profile.login,
        supported=tuple(supported),
        unsupported=tuple(unsupported),
        github_is_empty=empty,
    )
    plan = ProjectPlan(
        profile_login=profile.login, suggestions=tuple(suggestions), github_is_empty=empty
    )
    return AnalysisResult(profile=profile, report=report, plan=plan)


def test_landing_renders_form(client: FlaskClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Make your resume" in body
    assert 'name="resume_text"' in body
    assert 'name="username"' in body


def test_has_github_results_show_meter_and_plan(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    claim = Claim(text="Built a distributed cache in Go", skills=("go",))
    supported = (
        ClaimEvidence(claim, True, ("go-cache",), "Backed by public repo go-cache."),
    )
    react = Claim(text="Proficient in React", skills=("react",))
    unsupported = (ClaimEvidence(react, False, (), "No public repo names React."),)
    suggestion = Suggestion(
        "react-dashboard", "A live dashboard.", "Proficient in React",
        ("react",), "a weekend", "auth",
    )
    outcome = _result(
        profile_with_repos, False, supported, unsupported, (suggestion,)
    )
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post("/analyze", data={"resume_text": "x", "username": "octocat"})

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-empty="false"' in body
    assert "1 of 2 claims backed" in body  # credibility meter callout
    assert "backed" in body and "not shown yet" in body
    assert "react-dashboard" in body
    assert "signal, not proof" in body  # honest labeling


def test_empty_github_is_the_main_case(
    mocker: MockerFixture, client: FlaskClient, empty_profile: Profile
) -> None:
    """The empty-GitHub path renders a build plan, not 'nothing found'."""
    claim = Claim(text="Built a distributed cache in Go", skills=("go",))
    unsupported = (ClaimEvidence(claim, False, (), "No public repo demonstrates this."),)
    suggestion = Suggestion(
        "go-lru-cache", "A concurrent LRU cache.", "Built a distributed cache in Go",
        ("go",), "a weekend", "real distributed consensus",
    )
    outcome = _result(empty_profile, True, (), unsupported, (suggestion,))
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post("/analyze", data={"resume_text": "x", "username": "newgrad"})

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-empty="true"' in body
    assert "clean slate" in body
    assert "go-lru-cache" in body  # still prescribes what to build
    assert "not shown yet" in body


def test_blank_resume_returns_validation_error(
    mocker: MockerFixture, client: FlaskClient
) -> None:
    run = mocker.patch.object(webapp, "run_analysis")

    resp = client.post("/analyze", data={"resume_text": "  ", "username": "octocat"})

    assert resp.status_code == 400
    assert "paste your resume" in resp.get_data(as_text=True)
    run.assert_not_called()  # never runs the analysis on invalid input


def test_blank_username_returns_validation_error(
    mocker: MockerFixture, client: FlaskClient
) -> None:
    run = mocker.patch.object(webapp, "run_analysis")

    resp = client.post("/analyze", data={"resume_text": "some resume", "username": ""})

    assert resp.status_code == 400
    assert "GitHub username" in resp.get_data(as_text=True)
    run.assert_not_called()


@pytest.mark.parametrize(
    "error, status, needle",
    [
        (
            AnalysisError("No GitHub user found with the username 'ghost'.", 404),
            404,
            "No GitHub user found",
        ),
        (AnalysisError("GitHub's API rate limit is exhausted.", 503), 503, "rate limit"),
        (
            AnalysisError("Couldn't analyze the resume right now: overloaded", 502),
            502,
            "analyze the resume right now",
        ),
    ],
)
def test_service_errors_render_friendly_message(
    mocker: MockerFixture, client: FlaskClient, error: AnalysisError, status: int, needle: str
) -> None:
    mocker.patch.object(webapp, "run_analysis", return_value=error)

    resp = client.post("/analyze", data={"resume_text": "x", "username": "ghost"})

    assert resp.status_code == status
    body = resp.get_data(as_text=True)
    assert needle in body
    # errors re-render the form so the user can fix and retry, with inputs preserved
    assert 'name="resume_text"' in body
