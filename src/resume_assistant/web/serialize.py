"""Turn ``core/`` dataclasses into plain JSON-safe dicts for the API (v2.3).

The dataclasses in ``core/models.py`` are frozen and hold only strings, bools,
and (nested) tuples/dataclasses, so ``dataclasses.asdict`` already produces a
JSON-safe dict — the one adjustment needed is converting tuples to lists, which
``asdict`` does not do on its own but ``json.dumps``/Flask's ``jsonify`` handle
transparently. This module exists as the single place that decision lives,
rather than scattering ``asdict`` calls through ``app.py``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from resume_assistant.core.models import GapReport, ProjectPlan


def gap_report_to_dict(report: GapReport) -> dict[str, Any]:
    """Serialize a ``GapReport`` to a JSON-safe dict."""
    return asdict(report)


def project_plan_to_dict(plan: ProjectPlan) -> dict[str, Any]:
    """Serialize a ``ProjectPlan`` to a JSON-safe dict."""
    return asdict(plan)
