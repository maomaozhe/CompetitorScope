"""Comparator node — cross-competitor comparison."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.graph.runtime_events import emit_agent_output
from src.graph.state import AnalysisState
from src.graph.serialization import competitor_profiles, dump_model
from src.prompts.comparator import COMPARATOR_SYSTEM
from src.services.llm import get_llm, extract_json
from src.schemas.domain import ComparisonResult


logger = logging.getLogger(__name__)


def _default_comparison_dimensions(state: AnalysisState) -> list[str]:
    dimensions = state.get("comparison_dimensions") or state.get("analysis_dimensions") or []
    return [str(item).strip() for item in dimensions if str(item).strip()]


def _normalize_plan_response(response, default_dimensions: list[str], default_focus: str) -> tuple[list[str], str]:
    if not isinstance(response, dict):
        return default_dimensions, default_focus
    dimensions = response.get("comparison_dimensions") or response.get("dimensions") or default_dimensions
    if isinstance(dimensions, str):
        dimensions = [item.strip() for item in dimensions.split(",")]
    normalized = [str(item).strip() for item in dimensions if str(item).strip()]
    focus = response.get("focus_notes") or response.get("comparison_focus_notes") or default_focus
    return normalized or default_dimensions, str(focus or "")


def comparator_node(state: AnalysisState) -> dict:
    profiles = competitor_profiles(state.get("competitor_profiles", []))
    if not profiles:
        return {"error_message": "No profiles to compare"}
    logger.info("comparator: start profiles=%d", len(profiles))
    emit_agent_output(
        agent="comparator",
        node="comparator",
        title="准备横向对比",
        summary=f"正在合并 {len(profiles)} 个竞品 profile",
        artifact_type="comparison",
    )

    dimensions = _default_comparison_dimensions(state)
    focus_notes = state.get("comparison_focus_notes") or (
        "优先比较各竞品在产品定位、核心功能、定价模型、用户口碑上的差异，"
        "突出对进入该市场有决策价值的洞察。"
    )
    hitl_history = []

    if state.get("hitl_mode", "auto") == "interactive":
        logger.info("comparator: interrupt comparison_plan_confirm dimensions=%d", len(dimensions))
        response = interrupt({
            "type": "comparison_plan_confirm",
            "run_id": state.get("run_id"),
            "message": "确认横向对比的主要维度和重点",
            "comparison_dimensions": dimensions,
            "focus_notes": focus_notes,
            "default_response": {
                "comparison_dimensions": dimensions,
                "focus_notes": focus_notes,
            },
            "timeout_seconds": 120,
        })
        dimensions, focus_notes = _normalize_plan_response(response, dimensions, focus_notes)
        hitl_history.append({
            "type": "comparison_plan_confirm",
            "response": {
                "comparison_dimensions": dimensions,
                "focus_notes": focus_notes,
            },
        })

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
    logger.info("comparator: invoking LLM summary_chars=%d", len(content))
    emit_agent_output(
        agent="comparator",
        node="comparator",
        title="执行横向对比",
        summary=f"比较维度：{', '.join(dimensions)}",
        detail=focus_notes,
        artifact_type="comparison",
    )
    resp = llm.invoke([
        SystemMessage(content=COMPARATOR_SYSTEM),
        HumanMessage(content=(
            f"Comparison dimensions: {', '.join(dimensions)}\n"
            f"Comparison focus notes: {focus_notes}\n\n"
            f"Competitors:\n{content}"
        )),
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
    logger.info("comparator: done insights=%d recommendations=%d", len(result.key_insights), len(result.recommendations))
    emit_agent_output(
        agent="comparator",
        node="comparator",
        title="横向对比完成",
        summary=f"生成 {len(result.key_insights)} 条洞察和 {len(result.recommendations)} 条建议",
        detail="\n".join(f"- {item}" for item in result.key_insights),
        artifact_type="comparison",
    )

    return {
        "comparison_result": dump_model(result),
        "comparison_dimensions": dimensions,
        "comparison_focus_notes": focus_notes,
        "hitl_history": hitl_history,
        "current_stage": "comparing",
        "stage_status": "Comparison complete",
    }
