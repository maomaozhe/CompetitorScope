"""Planner node — parses query, discovers competitors, generates outline."""

import json
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AnalysisState
from src.prompts.planner import PLANNER_SYSTEM
from src.services.llm import get_llm, extract_json
from src.tools.web_search import search


def planner_node(state: AnalysisState) -> dict:
    query = state["query"]
    llm = get_llm("planner")

    # Step 1: search to discover competitors
    search_results = search(f"top competitors {query}", max_results=8)
    search_context = "\n".join(
        f"- {r['title']}: {r['url']} | {r['content'][:200]}"
        for r in search_results
    )

    # Step 2: LLM decides competitors + outline
    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=f"Query: {query}\n\nSearch results:\n{search_context}"),
    ]
    response = llm.invoke(messages)
    parsed = extract_json(response.content)

    return {
        "confirmed_competitors": parsed["competitors"],
        "analysis_dimensions": parsed["dimensions"],
        "report_outline": parsed["outline"],
        "current_stage": "collecting",
        "stage_status": f"Found {len(parsed['competitors'])} competitors, starting collection",
    }