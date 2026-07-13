"""Flask JSON API exposing the resume-assistant engine (v2.3).

The web layer is intentionally dumb (docs/ARCHITECTURE.md, rule 4), exactly like
``server/app.py`` is for MCP: the route validates input, calls ``service.py``
(which calls ``core/``), and serializes the result to JSON. No business logic
or HTTP-to-external-API calls live here. ``core/`` never imports Flask.

Previously this app rendered Jinja templates directly (PRs #9, #12, #14). As of
v2.3 the UI is a separately-deployed Next.js frontend (``frontend/``); this app
now only serves ``/api/*`` JSON, with CORS scoped to that frontend's origin.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict

from flask import Flask, jsonify, request
from flask.wrappers import Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from resume_assistant.config import Config, load_config
from resume_assistant.web.resume_upload import (
    MAX_UPLOAD_BYTES,
    ResumeUploadError,
    extract_resume_text,
)
from resume_assistant.web.serialize import gap_report_to_dict, project_plan_to_dict
from resume_assistant.web.service import (
    AnalysisError,
    AnalysisResult,
    ProgressEvent,
    run_analysis,
    run_analysis_events,
)

# Flask route return type: a JSON response, or a (response, status) tuple.
ResponseReturn = Response | tuple[Response, int]


def create_app(config: Config | None = None) -> Flask:
    """Build the Flask app. ``config`` is resolved from the environment if omitted."""
    app = Flask(__name__)
    # Reject oversized uploads at the WSGI layer before we read them into memory.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    resolved = config or load_config()
    CORS(app, resources={"/api/*": {"origins": resolved.frontend_origin}})

    # In-memory storage is safe here only because render.yaml runs a single
    # gunicorn worker; it would silently stop enforcing limits across workers
    # if this app were ever scaled to more than one process.
    limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri="memory://",
        default_limits=["60 per hour"],
    )

    @app.errorhandler(413)
    def _upload_too_large(_exc: Exception) -> ResponseReturn:
        """A friendly JSON error instead of Flask's default 413 page."""
        message = "That file is larger than the 10 MB limit. Upload a smaller file."
        return jsonify(error=message), 413

    @app.errorhandler(429)
    def _rate_limited(_exc: Exception) -> ResponseReturn:
        """A friendly JSON error instead of Flask-Limiter's default 429 page."""
        message = "Too many requests. Please wait a bit before trying again."
        return jsonify(error=message), 429

    def _read_inputs() -> tuple[str, str] | Response:
        """Parse + validate the resume text and username shared by both endpoints.

        Returns ``(resume_text, username)`` on success, or a 400 JSON error
        ``Response`` to return directly on bad input.
        """
        username = request.form.get("username", "").strip()

        upload = request.files.get("resume_file")
        if upload is not None and upload.filename:
            try:
                resume_text = extract_resume_text(upload.filename, upload.read())
            except ResumeUploadError as exc:
                return _error(str(exc), 400)
        else:
            # Kept as a tolerant fallback for any text-only client (e.g. tests).
            resume_text = request.form.get("resume_text", "").strip()

        error = _validate(resume_text, username)
        if error is not None:
            return _error(error, 400)
        return resume_text, username

    @app.post("/api/analyze")
    @limiter.limit("10 per hour")
    def analyze() -> ResponseReturn:
        """Validate input, run the analysis, and return the gap report + plan as JSON."""
        parsed = _read_inputs()
        if isinstance(parsed, Response):
            return parsed
        resume_text, username = parsed

        outcome = run_analysis(resume_text, username, resolved)
        if isinstance(outcome, AnalysisError):
            return jsonify(error=outcome.message), outcome.status

        return jsonify(
            report=gap_report_to_dict(outcome.report),
            plan=project_plan_to_dict(outcome.plan),
        )

    @app.post("/api/analyze/stream")
    @limiter.limit("10 per hour")
    def analyze_stream() -> ResponseReturn:
        """Same analysis as ``/api/analyze``, but stream real per-stage progress via SSE.

        Bad input still fails fast with a 400 JSON error (before any streaming
        starts). Once streaming begins the response is committed as 200, so a
        mid-run GitHub/Anthropic failure is delivered as an ``error`` SSE event
        rather than an HTTP status — the frontend handles both.
        """
        parsed = _read_inputs()
        if isinstance(parsed, Response):
            return parsed
        resume_text, username = parsed

        stream = _sse_stream(run_analysis_events(resume_text, username, resolved))
        response = app.response_class(stream, mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        # Defeat proxy/gunicorn response buffering so events flush as they happen.
        response.headers["X-Accel-Buffering"] = "no"
        return response

    return app


def _sse_stream(
    events: Iterator[ProgressEvent | AnalysisResult | AnalysisError],
) -> Iterator[str]:
    """Serialize analysis events into Server-Sent Events (``data: <json>\\n\\n``)."""
    for event in events:
        if isinstance(event, ProgressEvent):
            payload = {"type": "progress", **asdict(event)}
        elif isinstance(event, AnalysisResult):
            payload = {
                "type": "result",
                "report": gap_report_to_dict(event.report),
                "plan": project_plan_to_dict(event.plan),
            }
        else:
            payload = {"type": "error", "error": event.message}
        yield f"data: {json.dumps(payload)}\n\n"


def _error(message: str, status: int) -> Response:
    """A JSON ``{"error": ...}`` response carrying an HTTP status code."""
    response = jsonify(error=message)
    response.status_code = status
    return response


def _validate(resume_text: str, username: str) -> str | None:
    """Return a friendly message if the inputs are unusable, else ``None``."""
    if not resume_text:
        return "Please upload your resume (PDF or DOCX) before running the analysis."
    if not username:
        return "Please enter a GitHub username to cross-reference against."
    return None


def main() -> None:
    """Entry point: run the development server."""
    create_app().run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
