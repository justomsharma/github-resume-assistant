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

from flask import Flask, jsonify, request
from flask.wrappers import Response
from flask_cors import CORS

from resume_assistant.config import Config, load_config
from resume_assistant.web.resume_upload import (
    MAX_UPLOAD_BYTES,
    ResumeUploadError,
    extract_resume_text,
)
from resume_assistant.web.serialize import gap_report_to_dict, project_plan_to_dict
from resume_assistant.web.service import AnalysisError, run_analysis

# Flask route return type: a JSON response, or a (response, status) tuple.
ResponseReturn = Response | tuple[Response, int]


def create_app(config: Config | None = None) -> Flask:
    """Build the Flask app. ``config`` is resolved from the environment if omitted."""
    app = Flask(__name__)
    # Reject oversized uploads at the WSGI layer before we read them into memory.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    resolved = config or load_config()
    CORS(app, resources={"/api/*": {"origins": resolved.frontend_origin}})

    @app.errorhandler(413)
    def _upload_too_large(_exc: Exception) -> ResponseReturn:
        """A friendly JSON error instead of Flask's default 413 page."""
        message = "That file is larger than the 10 MB limit. Upload a smaller file."
        return jsonify(error=message), 413

    @app.post("/api/analyze")
    def analyze() -> ResponseReturn:
        """Validate input, run the analysis, and return the gap report + plan as JSON."""
        username = request.form.get("username", "").strip()

        upload = request.files.get("resume_file")
        if upload is not None and upload.filename:
            try:
                resume_text = extract_resume_text(upload.filename, upload.read())
            except ResumeUploadError as exc:
                return jsonify(error=str(exc)), 400
        else:
            # Kept as a tolerant fallback for any text-only client (e.g. tests).
            resume_text = request.form.get("resume_text", "").strip()

        error = _validate(resume_text, username)
        if error is not None:
            return jsonify(error=error), 400

        outcome = run_analysis(resume_text, username, resolved)
        if isinstance(outcome, AnalysisError):
            return jsonify(error=outcome.message), outcome.status

        return jsonify(
            report=gap_report_to_dict(outcome.report),
            plan=project_plan_to_dict(outcome.plan),
        )

    return app


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
