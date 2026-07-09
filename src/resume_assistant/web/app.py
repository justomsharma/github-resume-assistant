"""Flask web app exposing the resume-assistant engine with no install.

The web layer is intentionally dumb (docs/ARCHITECTURE.md, rule 4), exactly like
``server/app.py`` is for MCP: each route validates input, calls ``service.py``
(which calls ``core/``), and renders a template. No business logic or HTTP-to-
external-API calls live here. ``core/`` never imports Flask.
"""

from __future__ import annotations

from flask import Flask, render_template, request

from resume_assistant.config import Config, load_config
from resume_assistant.web.resume_upload import (
    MAX_UPLOAD_BYTES,
    ResumeUploadError,
    extract_resume_text,
)
from resume_assistant.web.service import AnalysisError, run_analysis

# Flask route return type: a rendered body, or a (body, status) tuple.
ResponseReturn = str | tuple[str, int]


def create_app(config: Config | None = None) -> Flask:
    """Build the Flask app. ``config`` is resolved from the environment if omitted."""
    app = Flask(__name__)
    # Reject oversized uploads at the WSGI layer before we read them into memory.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    resolved = config or load_config()

    @app.get("/")
    def index() -> str:
        """Render the landing form (paste resume + GitHub username)."""
        return render_template("index.html")

    @app.post("/analyze")
    def analyze() -> ResponseReturn:
        """Validate input, run the analysis, and render the results (or an error)."""
        username = request.form.get("username", "").strip()

        # The landing uploads a PDF/DOCX; the route still accepts pasted
        # ``resume_text`` as a fallback (used by tests and any text client).
        upload = request.files.get("resume_file")
        if upload is not None and upload.filename:
            try:
                resume_text = extract_resume_text(upload.filename, upload.read())
            except ResumeUploadError as exc:
                return render_template("index.html", error=str(exc), username=username), 400
        else:
            resume_text = request.form.get("resume_text", "").strip()

        error = _validate(resume_text, username)
        if error is not None:
            return render_template("index.html", error=error, username=username), 400

        outcome = run_analysis(resume_text, username, resolved)
        if isinstance(outcome, AnalysisError):
            return render_template(
                "index.html", error=outcome.message, username=username
            ), outcome.status

        return render_template("results.html", report=outcome.report, plan=outcome.plan)

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
