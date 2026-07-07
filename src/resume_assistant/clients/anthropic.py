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

from resume_assistant.core.models import (
    Claim,
    ClaimEvidence,
    GapReport,
    Profile,
    RepoEvidence,
    Suggestion,
    Verdict,
)

_MAX_TOKENS = 2048
# Verifying claims sends real code evidence plus a graded verdict per claim, so it
# needs a larger budget than extraction, like suggestions.
_VERIFY_MAX_TOKENS = 4096
# Per-batch cap on rendered evidence characters. "All repos" evidence can be large,
# so we split it into batches under this budget and merge the verdicts.
_EVIDENCE_CHAR_BUDGET = 12000
# Merge precedence when a claim is graded across several evidence batches: backed
# wins outright; otherwise not_shown (absent here) beats not_verifiable (unprovable).
_VERDICT_RANK: dict[Verdict, int] = {"backed": 0, "not_shown": 1, "not_verifiable": 2}
_VALID_VERDICTS: frozenset[str] = frozenset(_VERDICT_RANK)
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
    'If the report contains no claims at all, return {"suggestions": []}. Never '
    "fabricate a claim or a project to fill the list."
)


_VERIFY_SYSTEM_PROMPT = (
    "You grade whether a software engineer's resume claims are backed by their real "
    "public code. Use ONLY the repository evidence provided between the <evidence> "
    "tags — never assume code, files, or dependencies that are not shown there.\n\n"
    "For each claim, return exactly one of three honest verdicts:\n"
    "- 'backed': the evidence clearly proves the claim. You MUST cite the specific "
    "files that prove it in 'cited_files', each as '<repo_name>/<path>'. No files, no "
    "'backed'.\n"
    "- 'not_shown': the claim is the kind of thing public code could prove, but the "
    "evidence here does not — a gap to close, not a mark against the person.\n"
    "- 'not_verifiable': the claim is the kind public code structurally cannot prove "
    "(private/enterprise usage, traffic like '300+/day', latency numbers, cost or "
    "percentage impact). Do NOT force these into 'backed' or 'not_shown'.\n\n"
    "Be strict: a technology merely appearing in a repo name or description is NOT "
    "proof. Grade 'backed' only when the cited files actually demonstrate the claim.\n\n"
    "Copy each claim's text verbatim into 'claim'. Ground every rationale in the cited "
    "files. Return ONLY a JSON object, no prose, matching exactly this shape:\n"
    '{"verdicts": [{"claim": string, "verdict": "backed"|"not_shown"|"not_verifiable", '
    '"cited_files": [string], "rationale": string}]}\n\n'
    "Grade every claim you are given exactly once. Never invent evidence to reach "
    "'backed'."
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
                f"Extract the claims from this resume.\n\n<resume>\n{resume_text}\n</resume>"
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
    lines.append("Claims WITHOUT public evidence (gaps to close — prioritize these):")
    if gap_report.not_shown:
        lines += [f"- {e.claim.text}" for e in gap_report.not_shown]
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("Claims already backed by public GitHub:")
    if gap_report.backed:
        lines += [f"- {e.claim.text}" for e in gap_report.backed]
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append(
        "Claims public code can't prove (do NOT propose projects for these — they're "
        "not the kind of thing a public repo demonstrates):"
    )
    if gap_report.not_verifiable:
        lines += [f"- {e.claim.text}" for e in gap_report.not_verifiable]
    else:
        lines.append("- (none)")

    return "\n".join(lines)


def build_verification_messages(
    claims: list[Claim], evidence: list[RepoEvidence]
) -> list[MessageParam]:
    """Build the user message carrying the claims + repo evidence inside delimiters.

    Kept separate (and returned as plain dicts) so tests can assert exactly what we
    send without invoking the API. Claims and evidence go in distinct delimited
    blocks so injected text in a README can't be read as instructions.
    """
    return [
        {
            "role": "user",
            "content": (
                "Grade each claim against the repository evidence.\n\n"
                f"<claims>\n{_render_claims(claims)}\n</claims>\n\n"
                f"<evidence>\n{_render_evidence(evidence)}\n</evidence>"
            ),
        }
    ]


def _render_claims(claims: list[Claim]) -> str:
    """Render claims as a plain numbered list for the verifier to grade."""
    if not claims:
        return "(none)"
    return "\n".join(f"{i}. {claim.text}" for i, claim in enumerate(claims, start=1))


def _render_evidence(evidence: list[RepoEvidence]) -> str:
    """Render a batch of repo evidence into the readable block the prompt grounds on."""
    if not evidence:
        return "(no public repositories)"
    return "\n\n".join(_render_one_repo(repo) for repo in evidence)


def _render_one_repo(repo: RepoEvidence) -> str:
    """Render a single repo's code-level facts as a readable block."""
    languages = (
        ", ".join(f"{lang} ({count})" for lang, count in repo.language_breakdown)
        or repo.primary_language
        or "unknown"
    )
    lines = [
        f"## {repo.repo_name}",
        f"Languages: {languages}",
        f"Dependencies: {', '.join(repo.dependencies) if repo.dependencies else 'none found'}",
        f"Notable files ({repo.file_count} total): "
        f"{', '.join(repo.notable_paths) if repo.notable_paths else 'none'}",
        f"README:\n{repo.readme_excerpt}" if repo.readme_excerpt else "README: none",
    ]
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

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]:
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

    def verify_claims(
        self, claims: list[Claim], evidence: list[RepoEvidence]
    ) -> list[ClaimEvidence]:
        """Grade each claim against real repo evidence, returning one verdict per claim.

        Evidence for "all repos" can be large, so it's split into batches under a
        char budget; each batch grades every claim, and the verdicts are merged
        (``backed`` in any batch wins). Returns claims in their original order.
        Raises ``AnthropicError`` on API failure or an unparseable response.
        """
        if not claims:
            return []
        if not evidence:
            return [_default_verdict(claim) for claim in claims]

        batches = _batch_evidence(evidence)
        per_batch = [self._verify_one_batch(claims, batch) for batch in batches]
        return _merge_verdicts(claims, per_batch)

    def _verify_one_batch(
        self, claims: list[Claim], evidence: list[RepoEvidence]
    ) -> list[ClaimEvidence]:
        """Grade every claim against a single evidence batch."""
        response = _create_with_retries(
            self._client,
            model=self._model,
            max_tokens=_VERIFY_MAX_TOKENS,
            system=_VERIFY_SYSTEM_PROMPT,
            messages=build_verification_messages(claims, evidence),
        )
        return _parse_verdicts(_response_text(response), claims)


def _batch_evidence(evidence: list[RepoEvidence]) -> list[list[RepoEvidence]]:
    """Split repo evidence into batches whose rendered size stays under the char budget.

    A single repo larger than the budget still forms its own batch (never dropped),
    so every repo is graded. Order is preserved.
    """
    batches: list[list[RepoEvidence]] = []
    current: list[RepoEvidence] = []
    size = 0
    for repo in evidence:
        rendered = len(_render_one_repo(repo))
        if current and size + rendered > _EVIDENCE_CHAR_BUDGET:
            batches.append(current)
            current = []
            size = 0
        current.append(repo)
        size += rendered
    if current:
        batches.append(current)
    return batches


def _merge_verdicts(
    claims: list[Claim], per_batch: list[list[ClaimEvidence]]
) -> list[ClaimEvidence]:
    """Merge each claim's per-batch verdicts, keeping the strongest (backed wins)."""
    merged: list[ClaimEvidence] = []
    for index, claim in enumerate(claims):
        candidates = [batch[index] for batch in per_batch if index < len(batch)]
        if not candidates:
            merged.append(_default_verdict(claim))
            continue
        best = min(candidates, key=lambda e: _VERDICT_RANK[e.verdict])
        merged.append(best)
    return merged


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
        skills = tuple(str(s).strip().lower() for s in item.get("skills", []) if str(s).strip())
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
        skills = tuple(str(s).strip().lower() for s in item.get("skills", []) if str(s).strip())
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


def _parse_verdicts(raw: str, claims: list[Claim]) -> list[ClaimEvidence]:
    """Parse the model's verdicts into ClaimEvidence, one per claim in original order.

    Verdicts are matched back to claims by verbatim text. Any claim the model
    skipped, or gave an unknown verdict, degrades to ``not_shown`` rather than
    crashing — an honest gap beats a fabricated pass.
    """
    payload = _extract_json_object(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AnthropicError("Anthropic returned an unparseable verdicts response.") from exc

    items = data.get("verdicts", []) if isinstance(data, dict) else []
    by_text: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("claim", "")).strip()
            if text and text not in by_text:
                by_text[text] = item

    return [_verdict_for(claim, by_text.get(claim.text.strip())) for claim in claims]


def _verdict_for(claim: Claim, item: dict[str, Any] | None) -> ClaimEvidence:
    """Build one claim's evidence from its matched verdict item, defaulting safely."""
    if item is None:
        return _default_verdict(claim)
    verdict = str(item.get("verdict", "")).strip().lower()
    if verdict not in _VALID_VERDICTS:
        return _default_verdict(claim)
    cited = tuple(str(f).strip() for f in item.get("cited_files", []) if str(f).strip())
    rationale = str(item.get("rationale", "")).strip()
    if verdict == "backed" and not cited:
        # 'backed' without a cited file isn't grounded — downgrade to an honest gap.
        return _default_verdict(claim)
    return ClaimEvidence(
        claim=claim,
        verdict=verdict,  # type: ignore[arg-type]  # guarded by _VALID_VERDICTS above
        matching_repos=_repos_from_cited(cited),
        cited_files=cited,
        rationale=rationale or "Graded against your public repositories.",
    )


def _repos_from_cited(cited_files: tuple[str, ...]) -> tuple[str, ...]:
    """Derive the repo names from cited '<repo_name>/<path>' files, first-seen order."""
    repos: dict[str, None] = {}
    for path in cited_files:
        repo = path.split("/", 1)[0].strip()
        if repo:
            repos.setdefault(repo, None)
    return tuple(repos)


def _default_verdict(claim: Claim) -> ClaimEvidence:
    """A neutral ``not_shown`` verdict for a claim the model didn't clearly back."""
    return ClaimEvidence(
        claim=claim,
        verdict="not_shown",
        matching_repos=(),
        cited_files=(),
        rationale="No public code clearly demonstrates this yet — a gap to close.",
    )


def _extract_json_object(raw: str) -> str:
    """Return the outermost ``{...}`` span, so minor prose around the JSON is tolerated."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]
