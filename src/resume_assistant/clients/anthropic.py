"""Anthropic API client: extracts resume claims via Claude.

Owns the HTTP call, prompt assembly, and mapping the model's JSON into ``Claim``
models. Makes no business decisions — the claims→repos matching lives in
``core/analysis.py``. The model id always comes from ``config.anthropic_model``
(docs/ARCHITECTURE.md); the prompt follows the ``prompt-practices`` skill:
role + single task, delimited user text, an exact JSON schema, and explicit
empty-input handling so a thin resume yields an empty list, never fabrication.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic
from anthropic.types import MessageParam

from resume_assistant.core.models import Claim, GapReport, Profile, Suggestion

_MAX_TOKENS = 2048
# Suggestions carry a much heavier payload than claims (up to _MAX_SUGGESTIONS
# objects, each with several prose fields), so they need a larger budget or the
# JSON gets truncated mid-object and fails to parse.
_SUGGESTION_MAX_TOKENS = 4096
_MAX_CLAIMS = 12
_MAX_SUGGESTIONS = 5

# Retry transient Anthropic failures with exponential backoff (delay = base * 2**n).
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5

_SYSTEM_PROMPT = (
    "You extract concrete, verifiable claims from a software engineer's resume. "
    "Use ONLY the text provided between the <resume> tags — never invent facts, "
    "projects, or skills that are not present in that text.\n\n"
    "A 'claim' is a specific, checkable statement about what the person built, "
    "shipped, or is skilled in (e.g. 'Built a distributed cache in Go', "
    f"'Proficient in Kubernetes'). Extract at most the {_MAX_CLAIMS} strongest, "
    "most concrete claims, most concrete first. Skip vague filler "
    "('team player', 'fast learner').\n\n"
    "For each claim, list the normalized technologies/skills it names as short "
    "lowercase tokens (e.g. 'go', 'redis', 'react'), and a category — one of "
    "'project', 'skill', or 'impact'.\n\n"
    "Return ONLY a JSON object, no prose, matching exactly this shape:\n"
    '{"claims": [{"text": string, "skills": [string], "category": string}]}\n\n'
    "If the resume is empty or contains no concrete, verifiable claims, return "
    '{"claims": []}. Never fabricate a claim to fill the list.'
)


_SUGGESTION_SYSTEM_PROMPT = (
    "You are a senior engineer advising a peer on what to build and ship publicly "
    "to make their resume credible. Propose specific, shippable side projects.\n\n"
    "Use ONLY the gap report and repository facts provided between the <gap_report> "
    "tags — never invent skills, projects, or repos that are not present there. "
    "Ground every suggestion in a claim from that report.\n\n"
    "An empty or thin public GitHub is the EXPECTED case, not an error: it means the "
    "person's real work lives in private company repos. When it is empty, still "
    "prescribe concrete starter projects that would prove their claimed skills from "
    "scratch — never respond with 'nothing to suggest'.\n\n"
    f"Propose at most the {_MAX_SUGGESTIONS} highest-value projects. Each MUST:\n"
    "- prove a specific claim from the report (copy that claim's text verbatim into "
    "'proves_claim'), preferring claims with no public evidence;\n"
    "- be sized as exactly 'a weekend' or 'a week';\n"
    "- name what to deliberately skip so it stays shippable in that time.\n\n"
    "Return ONLY a JSON object, no prose, matching exactly this shape:\n"
    '{"suggestions": [{"title": string, "what_to_build": string, '
    '"proves_claim": string, "skills": [string], "size": string, "skip": string}]}\n\n'
    "If the report contains no claims at all, return {\"suggestions\": []}. Never "
    "fabricate a claim or a project to fill the list."
)


class AnthropicError(RuntimeError):
    """Base error for Anthropic client failures."""


class AnthropicAuthError(AnthropicError):
    """Raised when the Anthropic API key is missing or rejected."""


# Transient failures worth retrying: connection drops, rate limits, and 5xx.
# AuthenticationError and other 4xx are permanent — never retried.
_RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _create_with_retries(client: anthropic.Anthropic, **kwargs: Any) -> Any:
    """Call ``messages.create`` with exponential backoff on transient failures.

    Retries only transient errors (``_RETRYABLE_ERRORS``); a bad API key or other
    permanent error fails immediately with a typed, friendly exception. Lives in
    the client layer, where retries belong (docs/ARCHITECTURE.md).
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AnthropicAuthError("Anthropic rejected the API key.") from exc
        except _RETRYABLE_ERRORS as exc:
            if attempt == _MAX_RETRIES - 1:
                raise AnthropicError(
                    f"Anthropic request failed after {_MAX_RETRIES} attempts: {exc}"
                ) from exc
            time.sleep(_RETRY_BASE_DELAY * (2**attempt))
        except anthropic.APIError as exc:
            raise AnthropicError(f"Anthropic request failed: {exc}") from exc
    # The loop either returns or raises on the final attempt; this is unreachable.
    raise AnthropicError("Anthropic request failed: retries exhausted.")


def build_extraction_messages(resume_text: str) -> list[MessageParam]:
    """Build the user message that carries the resume inside delimiters.

    Kept separate (and returned as plain dicts) so tests can assert exactly what
    we send without invoking the API.
    """
    return [
        {
            "role": "user",
            "content": (
                "Extract the claims from this resume.\n\n"
                f"<resume>\n{resume_text}\n</resume>"
            ),
        }
    ]


def build_suggestion_messages(gap_report: GapReport, profile: Profile) -> list[MessageParam]:
    """Build the user message carrying the gap report + repo facts inside delimiters.

    Kept separate (and returned as plain dicts) so tests can assert exactly what we
    send without invoking the API. The gap report is rendered as plain text rather
    than raw JSON so the model reasons over readable claim/evidence pairs.
    """
    return [
        {
            "role": "user",
            "content": (
                "Prescribe projects to build, grounded in this gap report.\n\n"
                f"<gap_report>\n{_render_gap_report(gap_report, profile)}\n</gap_report>"
            ),
        }
    ]


def _render_gap_report(gap_report: GapReport, profile: Profile) -> str:
    """Render a gap report + profile into the readable text block the prompt grounds on."""
    lines = [
        f"GitHub user: @{gap_report.profile_login}",
        f"Public GitHub is empty: {gap_report.github_is_empty}",
    ]

    if profile.repos:
        lines.append("Public repositories:")
        for repo in profile.repos:
            language = repo.primary_language or "unknown language"
            lines.append(f"- {repo.name} ({language}): {repo.description or 'no description'}")
    else:
        lines.append("Public repositories: none.")

    lines.append("")
    lines.append("Claims WITHOUT public evidence (gaps to close):")
    if gap_report.unsupported:
        lines += [f"- {e.claim.text}" for e in gap_report.unsupported]
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("Claims already backed by public GitHub:")
    if gap_report.supported:
        lines += [f"- {e.claim.text}" for e in gap_report.supported]
    else:
        lines.append("- (none)")

    return "\n".join(lines)


class AnthropicClient:
    """Thin wrapper over the Anthropic SDK returning typed ``Claim`` models."""

    def __init__(self, api_key: str | None, model: str) -> None:
        if not api_key:
            raise AnthropicAuthError(
                "No ANTHROPIC_API_KEY set. Add one to your environment to analyze resumes."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def extract_claims(self, resume_text: str) -> list[Claim]:
        """Ask Claude for the strongest concrete claims in ``resume_text``.

        Returns an empty list for an empty/near-empty resume. Raises
        ``AnthropicError`` on API failure or an unparseable response.
        """
        response = _create_with_retries(
            self._client,
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=build_extraction_messages(resume_text),
        )
        return _parse_claims(_response_text(response))

    def generate_suggestions(
        self, gap_report: GapReport, profile: Profile
    ) -> list[Suggestion]:
        """Ask Claude for candidate projects grounded in ``gap_report``.

        Returns an empty list when the report has no claims to ground on. Raises
        ``AnthropicError`` on API failure or an unparseable response. Ranking is
        left to ``core/suggestions.py`` — this only produces candidates.
        """
        response = _create_with_retries(
            self._client,
            model=self._model,
            max_tokens=_SUGGESTION_MAX_TOKENS,
            system=_SUGGESTION_SYSTEM_PROMPT,
            messages=build_suggestion_messages(gap_report, profile),
        )
        return _parse_suggestions(_response_text(response))


def _response_text(response: Any) -> str:
    """Concatenate the text blocks of a messages response."""
    return "".join(block.text for block in response.content if block.type == "text")


def _parse_claims(raw: str) -> list[Claim]:
    """Parse the model's JSON payload into Claim models, tolerating stray prose."""
    payload = _extract_json_object(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AnthropicError("Anthropic returned an unparseable claims response.") from exc

    items = data.get("claims", []) if isinstance(data, dict) else []
    claims: list[Claim] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        skills = tuple(
            str(s).strip().lower() for s in item.get("skills", []) if str(s).strip()
        )
        category = str(item.get("category", "other")).strip() or "other"
        claims.append(Claim(text=text, skills=skills, category=category))
    return claims


def _parse_suggestions(raw: str) -> list[Suggestion]:
    """Parse the model's JSON payload into Suggestion models, tolerating stray prose."""
    payload = _extract_json_object(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AnthropicError(
            "Anthropic returned an incomplete or non-JSON suggestions response."
        ) from exc

    items = data.get("suggestions", []) if isinstance(data, dict) else []
    suggestions: list[Suggestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        what_to_build = str(item.get("what_to_build", "")).strip()
        if not title or not what_to_build:
            continue
        skills = tuple(
            str(s).strip().lower() for s in item.get("skills", []) if str(s).strip()
        )
        suggestions.append(
            Suggestion(
                title=title,
                what_to_build=what_to_build,
                proves_claim=str(item.get("proves_claim", "")).strip(),
                skills=skills,
                size=str(item.get("size", "")).strip() or "a week",
                skip=str(item.get("skip", "")).strip(),
            )
        )
    return suggestions


def _extract_json_object(raw: str) -> str:
    """Return the outermost ``{...}`` span, so minor prose around the JSON is tolerated."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]
