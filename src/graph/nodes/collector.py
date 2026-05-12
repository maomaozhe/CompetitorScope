"""Collector node — collects raw data for one competitor."""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from src.graph.state import AnalysisState
from src.prompts.collector import COLLECTOR_SYSTEM
from src.services.llm import get_llm, extract_json
from src.tools.web_search import search
from src.tools.web_scraper import scrape
from src.schemas.domain import RawSource


def fan_out_collectors(state: AnalysisState) -> list[Send]:
    """Fan out to one collect_competitor node per competitor."""
    # Guard: avoid re-fan-out
    if state.get("raw_sources"):
        return []
    competitors = state.get("confirmed_competitors", [])
    return [Send("collect_competitor", {"competitor": c}) for c in competitors]


def route_from_collector(state: AnalysisState) -> str:
    """Route to join_collectors only after all collectors have finished."""
    competitors = state.get("confirmed_competitors", [])
    finished = state.get("finished_collectors", set())
    # All done when every competitor's id is in finished
    if len(finished) >= len(competitors):
        return "join_collectors"
    return ""  # Stay in collector, wait for more


def collect_competitor(state: AnalysisState) -> dict:
    """Collect raw data for a single competitor (called per competitor via Send API)."""
    competitor = state.get("competitor", {})
    if not competitor:
        return {"finished_collectors": set()}

    name = competitor["name"]
    comp_id = name.lower().replace(" ", "-")

    raw_sources: list[RawSource] = []

    # Ask LLM what to search
    llm = get_llm("collector")
    resp = llm.invoke([
        SystemMessage(content=COLLECTOR_SYSTEM),
        HumanMessage(content=f"Competitor: {name}\nWebsite: {competitor.get('website', '')}"),
    ])
    queries_data = extract_json(resp.content)

    # Run searches + scrapes
    for qitem in queries_data.get("queries", [])[:4]:
        q = qitem.get("query", "")
        results = search(q, max_results=3)

        # Scrape top results
        for r in results[:2]:
            try:
                scraped = scrape(r["url"])
                raw_sources.append(RawSource(
                    competitor_id=comp_id,
                    url=scraped["url"],
                    title=scraped["title"],
                    raw_content=scraped["content"],
                    source_type="website",
                    search_query=q,
                ))
            except Exception:
                pass

    return {
        "raw_sources": raw_sources,
        "finished_collectors": {comp_id},
    }


def join_collectors(state: AnalysisState) -> dict:
    """Barrier: fires once after all collectors are done, triggers analyst fan-out."""
    return {}
