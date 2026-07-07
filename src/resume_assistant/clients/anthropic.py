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
from typing import Any

import anthropic
from anthropic.types import MessageParam

from resume_assistant.core.models import Claim

_MAX_TOKENS = 2048
_MAX_CLAIMS = 12

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


class AnthropicError(RuntimeError):
    """Base error for Anthropic client failures."""


class AnthropicAuthError(AnthropicError):
    """Raised when the Anthropic API key is missing or rejected."""


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
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=build_extraction_messages(resume_text),
            )
        except anthropic.AuthenticationError as exc:
            raise AnthropicAuthError("Anthropic rejected the API key.") from exc
        except anthropic.APIError as exc:
            raise AnthropicError(f"Anthropic request failed: {exc}") from exc

        return _parse_claims(_response_text(response))


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


def _extract_json_object(raw: str) -> str:
    """Return the outermost ``{...}`` span, so minor prose around the JSON is tolerated."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]
