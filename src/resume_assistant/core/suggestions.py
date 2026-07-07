"""Turn a gap report into a ranked 30-day build plan (pure logic).

This module never imports ``mcp`` and never hits the network directly
(docs/ARCHITECTURE.md, rule 1). It gets candidate projects from a suggester (the
Anthropic client, or any object satisfying ``SuggestionGenerator``) and then
*ranks* them itself, deterministically, so the ordering is testable offline —
mirroring how ``core/analysis.py`` gets claims from an extractor then does the
matching itself. The empty-GitHub case is the primary path: with no public repos
every claim is a gap, and the plan prescribes what to build from scratch rather
than reporting "nothing to suggest".
"""

from __future__ import annotations

from typing import Protocol

from resume_assistant.core.models import GapReport, Profile, ProjectPlan, Suggestion

# Effort ordering for ranking: quicker wins come earlier in the 30 days.
_SIZE_ORDER = {"a weekend": 0, "a weekend project": 0, "a week": 1}
_UNKNOWN_SIZE_RANK = 2


class SuggestionGenerator(Protocol):
    """Anything that can propose candidate projects (implemented by AnthropicClient)."""

    def generate_suggestions(self, gap_report: GapReport, profile: Profile) -> list[Suggestion]: ...


def build_project_plan(
    gap_report: GapReport, profile: Profile, suggester: SuggestionGenerator
) -> ProjectPlan:
    """Generate candidate projects for the gap report, then rank them into a plan."""
    candidates = suggester.generate_suggestions(gap_report, profile)
    ranked = _rank_suggestions(candidates, gap_report)
    return ProjectPlan(
        profile_login=gap_report.profile_login,
        suggestions=tuple(ranked),
        github_is_empty=gap_report.github_is_empty,
    )


def _rank_suggestions(suggestions: list[Suggestion], gap_report: GapReport) -> list[Suggestion]:
    """Order suggestions so the highest-value, quickest work comes first.

    Ranking is deterministic and explainable:
      1. Suggestions that prove a currently-*unsupported* claim (a real gap) rank
         before ones reinforcing a claim GitHub already backs up.
      2. Within that, smaller efforts first (a weekend before a week) — quick wins
         early in the 30 days.
      3. Original suggester order breaks any remaining ties (stable sort).
    """
    unsupported_claims = {e.claim.text for e in gap_report.unsupported}

    def sort_key(indexed: tuple[int, Suggestion]) -> tuple[int, int, int]:
        index, suggestion = indexed
        closes_gap = 0 if suggestion.proves_claim in unsupported_claims else 1
        size_rank = _SIZE_ORDER.get(suggestion.size.strip().lower(), _UNKNOWN_SIZE_RANK)
        return (closes_gap, size_rank, index)

    return [s for _, s in sorted(enumerate(suggestions), key=sort_key)]
