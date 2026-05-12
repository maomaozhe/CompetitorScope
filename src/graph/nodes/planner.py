"""Planner nodes — discover competitors and confirm report outline."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from src.graph.state import AnalysisState
from src.prompts.planner import PLANNER_SYSTEM
from src.services.llm import get_llm, extract_json
from src.tools.web_search import search


DEFAULT_DIMENSIONS = ["positioning", "features", "pricing", "reviews"]
logger = logging.getLogger(__name__)


def _normalize_competitors(value) -> list[dict]:
    competitors = []
    for item in value or []:
        if isinstance(item, str):
            name = item.strip()
            if name:
                competitors.append({"name": name, "website": ""})
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                competitors.append({"name": name, "website": item.get("website", "") or ""})
    return competitors


def _discover(query: str) -> tuple[list[dict], list[str], str]:
    """Use search + planner LLM to get candidate competitors, dimensions, and outline."""
    llm = get_llm("planner")

    logger.info("planner_discover: searching competitors query=%s", query)
    search_results = search(f"top competitors {query}", max_results=8)
    logger.info("planner_discover: search returned %d results", len(search_results))
    search_context = "\n".join(
        f"- {r['title']}: {r['url']} | {r['content'][:200]}"
        for r in search_results
    )

    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=f"Query: {query}\n\nSearch results:\n{search_context}"),
    ]
    logger.info("planner_discover: invoking planner LLM")
    response = llm.invoke(messages)
    parsed = extract_json(response.content)

    competitors = _normalize_competitors(parsed.get("competitors", []))
    dimensions = parsed.get("dimensions", DEFAULT_DIMENSIONS)
    outline = parsed.get("outline", "")

    if not competitors:
        competitors = [
            {"name": r["title"].split("|")[0].strip(), "website": r["url"]}
            for r in search_results[:5]
        ]

    logger.info("planner_discover: selected %d candidate competitors", len(competitors))
    return competitors, dimensions, outline


def _extract_competitor_response(response, default: list[dict]) -> list[dict]:
    if isinstance(response, dict):
        competitors = response.get("competitors", response.get("confirmed_competitors"))
    else:
        competitors = response
    normalized = _normalize_competitors(competitors)
    return normalized or default


def _extract_outline_response(response, default_outline: str, default_dimensions: list[str]) -> tuple[str, list[str]]:
    if not isinstance(response, dict):
        return default_outline, default_dimensions
    outline = response.get("outline") or response.get("report_outline") or default_outline
    dimensions = response.get("dimensions") or response.get("analysis_dimensions") or default_dimensions
    return outline, dimensions


def planner_discover(state: AnalysisState) -> dict:
    """Discover candidate competitors and optionally pause for confirmation."""
    query = state["query"]
    requested_competitors = _normalize_competitors(state.get("confirmed_competitors", []))

    if requested_competitors:
        competitors = requested_competitors
        dimensions = state.get("analysis_dimensions") or DEFAULT_DIMENSIONS
        outline = state.get("report_outline", "")
    else:
        competitors, dimensions, outline = _discover(query)

    default_competitors = competitors[:5]
    hitl_history = []

    if state.get("hitl_mode", "auto") == "interactive":
        logger.info("planner_discover: interrupt competitor_confirm candidates=%d", len(competitors))
        response = interrupt({
            "type": "competitor_confirm",
            "run_id": state.get("run_id"),
            "message": "确认本次要分析的竞品清单",
            "candidates": competitors,
            "default_response": {"competitors": default_competitors},
            "timeout_seconds": 30,
        })
        confirmed = _extract_competitor_response(response, default_competitors)
        hitl_history.append({
            "type": "competitor_confirm",
            "response": {"competitors": confirmed},
        })
    else:
        confirmed = default_competitors

    return {
        "candidate_competitors": competitors,
        "confirmed_competitors": confirmed,
        "analysis_dimensions": dimensions,
        "report_outline": outline,
        "hitl_history": hitl_history,
        "current_stage": "planning",
        "stage_status": f"Confirmed {len(confirmed)} competitors",
    }


def planner_outline(state: AnalysisState) -> dict:
    """Generate or confirm the report outline before collection starts."""
    query = state["query"]
    competitors = _normalize_competitors(state.get("confirmed_competitors", []))
    dimensions = state.get("analysis_dimensions") or DEFAULT_DIMENSIONS
    outline = state.get("report_outline", "")

    if not outline:
        names = ", ".join(c["name"] for c in competitors)
        llm = get_llm("planner")
        logger.info("planner_outline: invoking planner LLM for outline competitors=%s", names)
        response = llm.invoke([
            SystemMessage(content=PLANNER_SYSTEM),
            HumanMessage(content=f"Query: {query}\nConfirmed competitors: {names}\nDimensions: {dimensions}"),
        ])
        parsed = extract_json(response.content)
        outline = parsed.get("outline", "") or (
            "# 竞品分析报告\n\n"
            "## 1. 执行摘要\n## 2. 竞品概览\n## 3. 核心维度对比\n"
            "## 4. 关键洞察\n## 5. 建议"
        )
        dimensions = parsed.get("dimensions", dimensions)

    hitl_history = []
    if state.get("hitl_mode", "auto") == "interactive":
        logger.info("planner_outline: interrupt outline_confirm")
        response = interrupt({
            "type": "outline_confirm",
            "run_id": state.get("run_id"),
            "message": "确认报告大纲与分析维度",
            "outline": outline,
            "dimensions": dimensions,
            "default_response": {"outline": outline, "dimensions": dimensions},
            "timeout_seconds": 30,
        })
        outline, dimensions = _extract_outline_response(response, outline, dimensions)
        hitl_history.append({
            "type": "outline_confirm",
            "response": {"outline": outline, "dimensions": dimensions},
        })

    return {
        "analysis_dimensions": dimensions,
        "report_outline": outline,
        "hitl_history": hitl_history,
        "current_stage": "collecting",
        "stage_status": f"Starting collection for {len(competitors)} competitors",
    }
