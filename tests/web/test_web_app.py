"""Tests for the Flask JSON API (v2.3). The service (and thus all external APIs)
is mocked — the route is tested for its JSON success/error shapes and CORS."""

from __future__ import annotations

import io

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
from resume_assistant.web.resume_upload import ResumeUploadError
from resume_assistant.web.service import AnalysisError, AnalysisResult

FRONTEND_ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture
def client() -> FlaskClient:
    config = Config(
        github_token=None,
        anthropic_api_key="test-key",
        anthropic_model="claude-sonnet-5",
        cache_path=":memory:",
        frontend_origin=FRONTEND_ORIGIN,
    )
    return webapp.create_app(config).test_client()


def _result(
    profile: Profile,
    empty: bool,
    backed=(),
    not_shown=(),
    not_verifiable=(),
    suggestions=(),
) -> AnalysisResult:
    report = GapReport(
        profile_login=profile.login,
        backed=tuple(backed),
        not_shown=tuple(not_shown),
        not_verifiable=tuple(not_verifiable),
        github_is_empty=empty,
    )
    plan = ProjectPlan(
        profile_login=profile.login, suggestions=tuple(suggestions), github_is_empty=empty
    )
    return AnalysisResult(profile=profile, report=report, plan=plan)


def test_file_upload_happy_path(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """An uploaded file is parsed to text, then analyzed; the JSON mirrors the models."""
    claim = Claim(text="Built a distributed cache in Go", skills=("go",))
    backed = (
        ClaimEvidence(
            claim, "backed", ("go-cache",), ("go-cache/src/cache.go",), "LRU cache in cache.go."
        ),
    )
    suggestion = Suggestion(
        "react-dashboard",
        "A live dashboard.",
        "Proficient in React",
        ("react",),
        "a weekend",
        "auth",
    )
    outcome = _result(profile_with_repos, False, backed, suggestions=(suggestion,))
    extract = mocker.patch.object(
        webapp, "extract_resume_text", return_value="Built a distributed cache in Go"
    )
    run = mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post(
        "/api/analyze",
        data={"username": "octocat", "resume_file": (io.BytesIO(b"%PDF-fake"), "resume.pdf")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    extract.assert_called_once()
    # The engine receives the extracted text, never the raw file bytes.
    assert run.call_args.args[0] == "Built a distributed cache in Go"

    body = resp.get_json()
    assert body["report"]["profile_login"] == "octocat"
    assert body["report"]["github_is_empty"] is False
    assert body["report"]["backed"][0]["cited_files"] == ["go-cache/src/cache.go"]
    assert body["plan"]["suggestions"][0]["title"] == "react-dashboard"


def test_empty_github_is_the_main_case(
    mocker: MockerFixture, client: FlaskClient, empty_profile: Profile
) -> None:
    """The empty-GitHub path returns a build plan, not 'nothing found'."""
    claim = Claim(text="Built a distributed cache in Go", skills=("go",))
    not_shown = (ClaimEvidence(claim, "not_shown", (), (), "No public repo demonstrates this."),)
    suggestion = Suggestion(
        "go-lru-cache",
        "A concurrent LRU cache.",
        "Built a distributed cache in Go",
        ("go",),
        "a weekend",
        "real distributed consensus",
    )
    outcome = _result(empty_profile, True, not_shown=not_shown, suggestions=(suggestion,))
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post("/api/analyze", data={"resume_text": "x", "username": "newgrad"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["report"]["github_is_empty"] is True
    assert body["report"]["not_shown"][0]["claim"]["text"] == "Built a distributed cache in Go"
    assert body["plan"]["suggestions"][0]["title"] == "go-lru-cache"  # still prescribes a build


def test_total_claims_zero_returns_empty_buckets(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """No verifiable claims: report/plan JSON has empty lists, not an error."""
    outcome = _result(profile_with_repos, False)
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post("/api/analyze", data={"resume_text": "x", "username": "octocat"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["report"]["backed"] == []
    assert body["report"]["not_shown"] == []
    assert body["plan"]["suggestions"] == []


def test_bad_file_returns_friendly_400(mocker: MockerFixture, client: FlaskClient) -> None:
    """A file that can't be parsed returns the parser's message as JSON, not a crash."""
    mocker.patch.object(
        webapp,
        "extract_resume_text",
        side_effect=ResumeUploadError("That PDF file looks corrupted."),
    )
    run = mocker.patch.object(webapp, "run_analysis")

    resp = client.post(
        "/api/analyze",
        data={"username": "octocat", "resume_file": (io.BytesIO(b"garbage"), "resume.pdf")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "That PDF file looks corrupted."}
    run.assert_not_called()


def test_blank_resume_returns_validation_error(mocker: MockerFixture, client: FlaskClient) -> None:
    run = mocker.patch.object(webapp, "run_analysis")

    resp = client.post("/api/analyze", data={"resume_text": "  ", "username": "octocat"})

    assert resp.status_code == 400
    assert "upload your resume" in resp.get_json()["error"]
    run.assert_not_called()  # never runs the analysis on invalid input


def test_blank_username_returns_validation_error(
    mocker: MockerFixture, client: FlaskClient
) -> None:
    run = mocker.patch.object(webapp, "run_analysis")

    resp = client.post("/api/analyze", data={"resume_text": "some resume", "username": ""})

    assert resp.status_code == 400
    assert "GitHub username" in resp.get_json()["error"]
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
def test_service_errors_return_friendly_json(
    mocker: MockerFixture, client: FlaskClient, error: AnalysisError, status: int, needle: str
) -> None:
    mocker.patch.object(webapp, "run_analysis", return_value=error)

    resp = client.post("/api/analyze", data={"resume_text": "x", "username": "ghost"})

    assert resp.status_code == status
    assert needle in resp.get_json()["error"]


def test_cors_allows_configured_frontend_origin(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """The browser-facing origin check: only the configured frontend origin is allowed."""
    outcome = _result(profile_with_repos, False)
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post(
        "/api/analyze",
        data={"resume_text": "x", "username": "octocat"},
        headers={"Origin": FRONTEND_ORIGIN},
    )

    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == FRONTEND_ORIGIN


def test_cors_rejects_other_origins(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    outcome = _result(profile_with_repos, False)
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    resp = client.post(
        "/api/analyze",
        data={"resume_text": "x", "username": "octocat"},
        headers={"Origin": "https://evil.example.com"},
    )

    # flask-cors still lets the request through (CORS is enforced by the
    # browser, not the server) but omits the allow-origin header for an
    # origin outside the allowlist, so the browser blocks the response.
    assert "Access-Control-Allow-Origin" not in resp.headers
