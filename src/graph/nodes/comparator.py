"""Comparator node — cross-competitor comparison."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AnalysisState
from src.prompts.comparator import COMPARATOR_SYSTEM
from src.services.llm import get_llm, extract_json
from src.schemas.domain import ComparisonResult


def comparator_node(state: AnalysisState) -> dict:
    profiles = state.get("competitor_profiles", [])
    if not profiles:
        return {"error_message": "No profiles to compare"}

    # Build a compact text summary for LLM
    lines = []
    for p in profiles:
        lines.append(f"## {p.name}")
        lines.append(f"One-liner: {p.one_liner}")
        lines.append(f"Market position: {p.market_position}")
        lines.append(f"Tech form: {p.tech_form}")
        lines.append(f"Features: {', '.join(f.name for f in p.features)}")
        pricing_str = ", ".join(f"{t.tier_name}:{t.price}" for t in p.pricing_tiers)
        lines.append(f"Pricing: {pricing_str}")
        lines.append(f"Positive: {', '.join(p.positive_themes[:3])}")
        lines.append(f"Negative: {', '.join(p.negative_themes[:3])}")

    content = "\n".join(lines)

    llm = get_llm("comparator")
    resp = llm.invoke([
        SystemMessage(content=COMPARATOR_SYSTEM),
        HumanMessage(content=f"Competitors:\n{content}"),
    ])

    try:
        data = extract_json(resp.content)
    except Exception:
        data = {}

    result = ComparisonResult(
        feature_table=data.get("feature_table", ""),
        pricing_table=data.get("pricing_table", ""),
        key_insights=data.get("key_insights", []),
        recommendations=data.get("recommendations", []),
    )

    return {
        "comparison_result": result,
        "current_stage": "comparing",
        "stage_status": "Comparison complete",
    }