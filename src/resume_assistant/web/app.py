"""Flask web app exposing the resume-assistant engine with no install.

The web layer is intentionally dumb (docs/ARCHITECTURE.md, rule 4), exactly like
``server/app.py`` is for MCP: each route validates input, calls ``service.py``
(which calls ``core/``), and renders a template. No business logic or HTTP-to-
external-API calls live here. ``core/`` never imports Flask.
"""

from __future__ import annotations

from flask import Flask, render_template, request

from resume_assistant.config import Config, load_config
from resume_assistant.web.service import AnalysisError, run_analysis

# Flask route return type: a rendered body, or a (body, status) tuple.
ResponseReturn = str | tuple[str, int]


def create_app(config: Config | None = None) -> Flask:
    """Build the Flask app. ``config`` is resolved from the environment if omitted."""
    app = Flask(__name__)
    resolved = config or load_config()

    @app.get("/")
    def index() -> str:
        """Render the landing form (paste resume + GitHub username)."""
        return render_template("index.html")

    @app.post("/analyze")
    def analyze() -> ResponseReturn:
        """Validate input, run the analysis, and render the results (or an error)."""
        resume_text = request.form.get("resume_text", "").strip()
        username = request.form.get("username", "").strip()

        error = _validate(resume_text, username)
        if error is not None:
            return render_template(
                "index.html", error=error, resume_text=resume_text, username=username
            ), 400

        outcome = run_analysis(resume_text, username, resolved)
        if isinstance(outcome, AnalysisError):
            return render_template(
                "index.html",
                error=outcome.message,
                resume_text=resume_text,
                username=username,
            ), outcome.status

        return render_template("results.html", report=outcome.report, plan=outcome.plan)

    return app


def _validate(resume_text: str, username: str) -> str | None:
    """Return a friendly message if the inputs are unusable, else ``None``."""
    if not resume_text:
        return "Please paste your resume text before running the analysis."
    if not username:
        return "Please enter a GitHub username to cross-reference against."
    return None


def main() -> None:
    """Entry point: run the development server."""
    create_app().run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
