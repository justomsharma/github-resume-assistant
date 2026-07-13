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
from resume_assistant.web.service import (
    AnalysisError,
    AnalysisResult,
    ProgressEvent,
    ReportReady,
    SubProgressEvent,
)

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


def test_oversized_upload_returns_friendly_413(mocker: MockerFixture, client: FlaskClient) -> None:
    """A file over the WSGI-layer cap gets the 413 error handler's JSON, not Flask's HTML page."""
    from resume_assistant.web.resume_upload import MAX_UPLOAD_BYTES

    run = mocker.patch.object(webapp, "run_analysis")
    oversized = b"x" * (MAX_UPLOAD_BYTES + 1)

    resp = client.post(
        "/api/analyze",
        data={"username": "octocat", "resume_file": (io.BytesIO(oversized), "resume.pdf")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 413
    assert resp.get_json() == {
        "error": "That file is larger than the 10 MB limit. Upload a smaller file."
    }
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


def _parse_sse(body: str) -> list[dict]:
    """Extract the JSON payloads from an SSE response body."""
    import json

    payloads = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                payloads.append(json.loads(line[len("data:") :].strip()))
    return payloads


def test_stream_emits_progress_then_result(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """The stream endpoint sends progress SSE events, then a final result event."""
    outcome = _result(profile_with_repos, False)

    def events():
        yield ProgressEvent(stage="profile", index=1, total=4, label="Fetching your GitHub profile")
        yield ProgressEvent(stage="evidence", index=2, total=4, label="Reading your public repos")
        yield outcome

    mocker.patch.object(webapp, "run_analysis_events", return_value=events())

    resp = client.post("/api/analyze/stream", data={"resume_text": "x", "username": "octocat"})

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")
    assert resp.headers.get("X-Accel-Buffering") == "no"

    payloads = _parse_sse(resp.get_data(as_text=True))
    assert [p["type"] for p in payloads] == ["progress", "progress", "result"]
    assert payloads[0]["stage"] == "profile"
    assert payloads[0]["index"] == 1
    assert payloads[-1]["report"]["profile_login"] == "octocat"
    assert payloads[-1]["plan"]["github_is_empty"] is False


def test_stream_emits_subprogress_and_report_ready(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """Sub-progress and the early gap-report event serialize with their own SSE types."""
    report = GapReport(
        profile_login="octocat", backed=(), not_shown=(), not_verifiable=(), github_is_empty=False
    )
    outcome = _result(profile_with_repos, False)

    def events():
        yield SubProgressEvent(stage="evidence", detail="Reading repo 1 of 3")
        yield ReportReady(profile=profile_with_repos, report=report)
        yield outcome

    mocker.patch.object(webapp, "run_analysis_events", return_value=events())

    resp = client.post("/api/analyze/stream", data={"resume_text": "x", "username": "octocat"})

    payloads = _parse_sse(resp.get_data(as_text=True))
    assert [p["type"] for p in payloads] == ["subprogress", "report", "result"]
    assert payloads[0]["stage"] == "evidence"
    assert payloads[0]["detail"] == "Reading repo 1 of 3"
    assert payloads[1]["report"]["profile_login"] == "octocat"
    assert "plan" not in payloads[1]  # the plan isn't ready yet


def test_stream_emits_heartbeat_as_a_comment_not_a_data_line(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """Heartbeats keep the connection alive without the frontend's data: parser seeing them."""
    from resume_assistant.web.service import Heartbeat

    outcome = _result(profile_with_repos, False)

    def events():
        yield Heartbeat()
        yield outcome

    mocker.patch.object(webapp, "run_analysis_events", return_value=events())

    resp = client.post("/api/analyze/stream", data={"resume_text": "x", "username": "octocat"})

    raw = resp.get_data(as_text=True)
    assert ": heartbeat\n\n" in raw
    # The frontend only reacts to `data:` lines, so the heartbeat produces no payload.
    payloads = _parse_sse(raw)
    assert [p["type"] for p in payloads] == ["result"]


def test_stream_delivers_mid_run_error_as_event(mocker: MockerFixture, client: FlaskClient) -> None:
    """A failure once streaming has begun is delivered as an SSE error event (200)."""

    def events():
        yield ProgressEvent(stage="profile", index=1, total=4, label="Fetching your GitHub profile")
        yield AnalysisError("Couldn't fetch GitHub data right now: boom", 502)

    mocker.patch.object(webapp, "run_analysis_events", return_value=events())

    resp = client.post("/api/analyze/stream", data={"resume_text": "x", "username": "octocat"})

    assert resp.status_code == 200
    payloads = _parse_sse(resp.get_data(as_text=True))
    assert payloads[0]["type"] == "progress"
    assert payloads[-1] == {"type": "error", "error": "Couldn't fetch GitHub data right now: boom"}


def test_stream_blank_username_returns_400_before_streaming(
    mocker: MockerFixture, client: FlaskClient
) -> None:
    run = mocker.patch.object(webapp, "run_analysis_events")

    resp = client.post("/api/analyze/stream", data={"resume_text": "some resume", "username": ""})

    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    assert "GitHub username" in resp.get_json()["error"]
    run.assert_not_called()  # validation fails fast, before any streaming


def test_stream_blank_resume_returns_400_before_streaming(
    mocker: MockerFixture, client: FlaskClient
) -> None:
    run = mocker.patch.object(webapp, "run_analysis_events")

    resp = client.post("/api/analyze/stream", data={"resume_text": "  ", "username": "octocat"})

    assert resp.status_code == 400
    assert "upload your resume" in resp.get_json()["error"]
    run.assert_not_called()


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


def test_analyze_rate_limit_returns_friendly_429(
    mocker: MockerFixture, client: FlaskClient, profile_with_repos: Profile
) -> None:
    """/api/analyze is capped at 10/hour per IP; the 11th request gets a friendly 429."""
    outcome = _result(profile_with_repos, False)
    mocker.patch.object(webapp, "run_analysis", return_value=outcome)

    for _ in range(10):
        resp = client.post("/api/analyze", data={"resume_text": "x", "username": "octocat"})
        assert resp.status_code == 200

    resp = client.post("/api/analyze", data={"resume_text": "x", "username": "octocat"})

    assert resp.status_code == 429
    assert resp.get_json() == {"error": "Too many requests. Please wait a bit before trying again."}


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
