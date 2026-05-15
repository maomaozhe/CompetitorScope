"""Analyst node — extracts structured profile for one competitor."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from src.graph.runtime_events import emit_agent_output
from src.graph.state import AnalysisState
from src.graph.serialization import dump_model, dump_models, raw_sources as restore_raw_sources
from src.prompts.analyst import ANALYST_SYSTEM
from src.services.llm import get_llm, extract_json
from src.schemas.domain import (
    CompetitorProfile,
    EvidenceItem,
    Feature,
    PricingTier,
)


logger = logging.getLogger(__name__)


def _build_profile(raw_text: str, competitor_id: str, competitor_name: str) -> dict:
    llm = get_llm("analyst")
    logger.info("analyst: invoking LLM competitor=%s raw_chars=%d", competitor_name, len(raw_text))
    emit_agent_output(
        agent="analyst",
        node="analyze_competitor",
        title="调用结构化分析",
        summary=f"{competitor_name} 合并来源文本 {len(raw_text)} 字符",
    )
    resp = llm.invoke([
        SystemMessage(content=ANALYST_SYSTEM),
        HumanMessage(content=f"Competitor: {competitor_name}\n\nRaw data:\n{raw_text[:6000]}"),
    ])
    return extract_json(resp.content)


def fan_out_analysts(state: AnalysisState) -> list[Send]:
    """Fan out to one analyze_competitor node per competitor.

    Each Send carries the competitor info PLUS its raw sources.
    """
    # Guard: avoid re-fan-out
    if state.get("competitor_profiles"):
        return []
    competitors = state.get("confirmed_competitors", [])
    raw_sources = restore_raw_sources(state.get("raw_sources", []))
    logger.info("analyst_fanout: competitors=%d raw_sources=%d", len(competitors), len(raw_sources))

    sends = []
    for c in competitors:
        comp_id = c["name"].lower().replace(" ", "-")
        comp_sources = [s for s in raw_sources if s.competitor_id == comp_id]
        sends.append(Send("analyze_competitor", {
            "competitor": c,
            "raw_sources": dump_models(comp_sources),
        }))
    return sends


def route_from_analyst(state: AnalysisState) -> str:
    """Route to join_analysts only after all analysts have finished."""
    competitors = state.get("confirmed_competitors", [])
    finished = state.get("finished_analysts", [])
    if len(finished) >= len(competitors):
        return "join_analysts"
    return ""


def analyze_competitor(state: AnalysisState) -> dict:
    """Analyze a single competitor's raw sources into a structured profile (via Send API)."""
    competitor = state.get("competitor", {})
    if not competitor:
        return {"finished_analysts": []}

    name = competitor["name"]
    comp_id = name.lower().replace(" ", "-")
    website = competitor.get("website", "")
    raw_sources = restore_raw_sources(state.get("raw_sources", []))
    logger.info("analyst: start competitor=%s sources=%d", name, len(raw_sources))
    emit_agent_output(
        agent="analyst",
        node="analyze_competitor",
        title="整理分析来源",
        summary=f"{name} 将分析 {len(raw_sources)} 条来源",
        detail="\n".join(f"- {source.title or source.url}\n  {source.url}" for source in raw_sources),
        artifact_type="sources",
    )

    if not raw_sources:
        logger.info("analyst: no sources competitor=%s", name)
        emit_agent_output(
            agent="analyst",
            node="analyze_competitor",
            title="跳过结构化分析",
            summary=f"{name} 没有可用来源",
            artifact_type="profile",
        )
        return {"finished_analysts": [comp_id]}

    # Combine all text
    combined = "\n\n".join(
        f"[Source: {s.url}]\n{s.raw_content}"
        for s in raw_sources
    )

    data = _build_profile(combined, comp_id, name)
    logger.info("analyst: parsed profile competitor=%s features=%d", name, len(data.get("features", [])))
    emit_agent_output(
        agent="analyst",
        node="analyze_competitor",
        title="提取结构化证据",
        summary=f"{name} 提取 {len(data.get('features', []))} 个功能点和 {len(data.get('evidence', []))} 条证据",
        artifact_type="profile",
    )

    # Build profile
    features = [
        Feature(
            name=f.get("name", ""),
            description=f.get("description", ""),
            evidence_id="",
        )
        for f in data.get("features", [])
    ]
    pricing = [
        PricingTier(
            tier_name=p.get("tier_name", ""),
            price=p.get("price", ""),
            key_features=p.get("key_features", []),
            evidence_id="",
        )
        for p in data.get("pricing_tiers", [])
    ]

    profile = CompetitorProfile(
        competitor_id=comp_id,
        name=name,
        website=website,
        one_liner=data.get("one_liner", ""),
        target_audience=data.get("target_audience", []),
        core_scenarios=data.get("core_scenarios", []),
        market_position=data.get("market_position", ""),
        features=features,
        differentiators=data.get("differentiators", []),
        recent_updates=data.get("recent_updates", []),
        tech_form=data.get("tech_form", ""),
        pricing_tiers=pricing,
        pricing_strategy=data.get("pricing_strategy", ""),
        positive_themes=data.get("positive_themes", []),
        negative_themes=data.get("negative_themes", []),
        review_summary=data.get("review_summary", ""),
    )

    # Build evidence items
    all_evidence = []
    for ev in data.get("evidence", []):
        all_evidence.append(EvidenceItem(
            source_id=ev.get("source_id", ""),
            source_url=ev.get("source_url", ""),
            excerpt=ev.get("excerpt", ""),
            extracted_fact=ev.get("extracted_fact", ""),
            fact_type=ev.get("fact_type", "feature"),
            competitor_id=comp_id,
        ))

    emit_agent_output(
        agent="analyst",
        node="analyze_competitor",
        title="结构化 profile 完成",
        summary=f"{name} profile 已生成，证据 {len(all_evidence)} 条",
        detail=profile.one_liner,
        artifact_type="profile",
    )
    return {
        "competitor_profiles": [dump_model(profile)],
        "evidence_items": dump_models(all_evidence),
        "finished_analysts": [comp_id],
    }


def join_analysts(state: AnalysisState) -> dict:
    """Barrier: fires once after all analysts are done, triggers comparator."""
    emit_agent_output(
        agent="analyst",
        node="join_analysts",
        title="分析汇总完成",
        summary=f"已完成 {len(state.get('competitor_profiles', []))} 个竞品 profile",
        artifact_type="status",
    )
    return {}
