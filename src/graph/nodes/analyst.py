"""Analyst node — extracts structured profile for one competitor."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AnalysisState
from src.prompts.analyst import ANALYST_SYSTEM
from src.services.llm import get_llm, extract_json
from src.schemas.domain import (
    CompetitorProfile,
    EvidenceItem,
    Feature,
    PricingTier,
)


def _build_profile(raw_text: str, competitor_id: str, competitor_name: str) -> dict:
    llm = get_llm("analyst")
    resp = llm.invoke([
        SystemMessage(content=ANALYST_SYSTEM),
        HumanMessage(content=f"Competitor: {competitor_name}\n\nRaw data:\n{raw_text[:6000]}"),
    ])
    return extract_json(resp.content)


def analyst_node(state: AnalysisState) -> dict:
    competitors = state.get("confirmed_competitors", [])
    raw_sources = state.get("raw_sources", [])
    profiles: list[CompetitorProfile] = []
    all_evidence: list[EvidenceItem] = []

    for comp in competitors:
        name = comp["name"]
        comp_id = name.lower().replace(" ", "-")
        website = comp.get("website", "")

        # Gather this competitor's sources
        comp_sources = [s for s in raw_sources if s.competitor_id == comp_id]
        if not comp_sources:
            continue

        # Combine all text
        combined = "\n\n".join(
            f"[Source: {s.url}]\n{s.raw_content}"
            for s in comp_sources
        )

        data = _build_profile(combined, comp_id, name)

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
        profiles.append(profile)

        # Build evidence items
        for ev in data.get("evidence", []):
            all_evidence.append(EvidenceItem(
                source_id=ev.get("source_id", ""),
                source_url=ev.get("source_url", ""),
                excerpt=ev.get("excerpt", ""),
                extracted_fact=ev.get("extracted_fact", ""),
                fact_type=ev.get("fact_type", "feature"),
                competitor_id=comp_id,
            ))

    return {
        "competitor_profiles": profiles,
        "evidence_items": all_evidence,
        "current_stage": "analyzing",
        "stage_status": f"Extracted profiles for {len(profiles)} competitors",
    }