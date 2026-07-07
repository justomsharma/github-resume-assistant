# MCP server image. Runs the stdio server via the `resume-assistant` console
# script, so a host (e.g. Claude Desktop) launches it with `docker run -i --rm`.
# Secrets are never baked in — pass GITHUB_TOKEN / ANTHROPIC_API_KEY at runtime.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# README.md is required: pyproject.toml references it as the package readme, so
# the build fails without it. src/ + pyproject give pip everything to install
# the package, its runtime deps, and the console script in one step.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user rather than root. /app is handed to that user so
# the server can write its SQLite cache (config.py defaults CACHE_PATH under the
# working directory) without needing root.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

CMD ["resume-assistant"]
