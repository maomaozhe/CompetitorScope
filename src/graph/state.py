"""AnalysisState — the shared blackboard for the LangGraph pipeline."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict


def _append_lists(a: list | None, b: list | None) -> list:
    return (a or []) + (b or [])


def _union_lists(a: list[str] | None, b: list[str] | None) -> list[str]:
    seen = set()
    merged = []
    for item in (a or []) + (b or []):
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


class AnalysisState(TypedDict, total=False):
    # ── Run metadata ──
    run_id: str
    query: str
    hitl_mode: Literal["auto", "interactive"]

    # ── Planner outputs ──
    candidate_competitors: list[dict]  # [{name, website}]
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
    raw_sources: Annotated[list[dict], _append_lists]

    # ── Completion tracking for fan-out barriers ──
    # Track which competitors have been processed (collector → analyst barrier)
    finished_collectors: Annotated[list[str], _union_lists]
    finished_analysts: Annotated[list[str], _union_lists]

    # ── HITL bookkeeping ──
    hitl_history: Annotated[list[dict], _append_lists]
    supplement_urls: dict[str, list[str]]
    skipped_competitors: Annotated[list[str], _union_lists]

    # ── Analyst outputs (append via reducer) ──
    competitor_profiles: Annotated[list[dict], _append_lists]
    evidence_items: Annotated[list[dict], _append_lists]

    # ── Comparator output ──
    comparison_result: dict | None

    # ── Writer output ──
    report: dict | None
