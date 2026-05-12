"""Collector node — collects raw data for one competitor."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AnalysisState
from src.prompts.collector import COLLECTOR_SYSTEM
from src.services.llm import get_llm, extract_json
from src.tools.web_search import search
from src.tools.web_scraper import scrape
from src.schemas.domain import RawSource


def collector_node(state: AnalysisState) -> dict:
    competitors = state.get("confirmed_competitors", [])
    raw_sources: list[RawSource] = []

    for comp in competitors:
        name = comp["name"]
        website = comp.get("website", "")
        comp_id = name.lower().replace(" ", "-")

        # Ask LLM what to search
        llm = get_llm("collector")
        resp = llm.invoke([
            SystemMessage(content=COLLECTOR_SYSTEM),
            HumanMessage(content=f"Competitor: {name}\nWebsite: {website}"),
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

    return {"raw_sources": raw_sources}