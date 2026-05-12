"""AnalysisState — the shared blackboard for the LangGraph pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from src.schemas.domain import (
    ComparisonResult,
    CompetitorProfile,
    EvidenceItem,
    RawSource,
    Report,
)


class AnalysisState(TypedDict, total=False):
    # ── Run metadata ──
    run_id: str
    query: str

    # ── Planner outputs ──
    confirmed_competitors: list[dict]  # [{name, website}]
    analysis_dimensions: list[str]
    report_outline: str  # markdown outline

    # ── Flow control ──
    current_stage: Literal[
        "planning", "collecting", "analyzing", "comparing", "writing", "complete", "error"
    ]
    stage_status: str  # human-readable progress
    error_message: str | None

    # ── Collector outputs (append via reducer) ──
    raw_sources: Annotated[list[RawSource], operator.add]

    # ── Analyst outputs (append via reducer) ──
    competitor_profiles: Annotated[list[CompetitorProfile], operator.add]
    evidence_items: Annotated[list[EvidenceItem], operator.add]

    # ── Comparator output ──
    comparison_result: ComparisonResult | None

    # ── Writer output ──
    report: Report | None
