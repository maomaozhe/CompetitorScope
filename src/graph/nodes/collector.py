"""Collector node — collects raw data for one competitor."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send, interrupt

from src.graph.runtime_events import emit_agent_output
from src.graph.state import AnalysisState
from src.graph.serialization import dump_models, raw_sources as restore_raw_sources
from src.prompts.collector import COLLECTOR_SYSTEM
from src.services.llm import get_llm, extract_json
from src.tools.web_search import search
from src.tools.web_scraper import scrape
from src.schemas.domain import RawSource


logger = logging.getLogger(__name__)


def fan_out_collectors(state: AnalysisState) -> list[Send]:
    """Fan out to one collect_competitor node per competitor."""
    # Guard: avoid re-fan-out
    if state.get("raw_sources"):
        return []
    competitors = state.get("confirmed_competitors", [])
    logger.info("collector_fanout: competitors=%d", len(competitors))
    return [Send("collect_competitor", {"competitor": c}) for c in competitors]


def route_from_collector(state: AnalysisState) -> str:
    """Route to join_collectors only after all collectors have finished."""
    competitors = state.get("confirmed_competitors", [])
    finished = state.get("finished_collectors", [])
    # All done when every competitor's id is in finished
    if len(finished) >= len(competitors):
        return "join_collectors"
    return ""  # Stay in collector, wait for more


def collect_competitor(state: AnalysisState) -> dict:
    """Collect raw data for a single competitor (called per competitor via Send API)."""
    competitor = state.get("competitor", {})
    if not competitor:
        return {"finished_collectors": []}

    name = competitor["name"]
    comp_id = name.lower().replace(" ", "-")
    logger.info("collector: start competitor=%s", name)

    raw_sources: list[RawSource] = []

    # Ask LLM what to search
    llm = get_llm("collector")
    logger.info("collector: invoking query planner LLM competitor=%s", name)
    emit_agent_output(
        agent="collector",
        node="collect_competitor",
        title="规划采集查询",
        summary=f"正在为 {name} 生成搜索查询",
    )
    resp = llm.invoke([
        SystemMessage(content=COLLECTOR_SYSTEM),
        HumanMessage(content=f"Competitor: {name}\nWebsite: {competitor.get('website', '')}"),
    ])
    queries_data = extract_json(resp.content)
    queries = queries_data.get("queries", [])[:4]
    emit_agent_output(
        agent="collector",
        node="collect_competitor",
        title="搜索查询已生成",
        summary=f"{name} 将执行 {len(queries)} 个查询",
        detail="\n".join(f"- {item.get('query', '')}" for item in queries if isinstance(item, dict)),
        artifact_type="sources",
    )

    # Run searches + scrapes
    for qitem in queries:
        q = qitem.get("query", "")
        logger.info("collector: searching competitor=%s query=%s", name, q)
        emit_agent_output(
            agent="collector",
            node="collect_competitor",
            title="搜索来源",
            summary=f"{name}: {q}",
        )
        results = search(q, max_results=3)
        logger.info("collector: search results competitor=%s count=%d", name, len(results))
        emit_agent_output(
            agent="collector",
            node="collect_competitor",
            title="搜索结果已返回",
            summary=f"{name} 针对该查询找到 {len(results)} 条结果",
            detail="\n".join(f"- {r.get('title')}: {r.get('url')}" for r in results),
            artifact_type="sources",
        )

        # Scrape top results
        for r in results[:2]:
            try:
                logger.info("collector: scraping competitor=%s url=%s", name, r["url"])
                emit_agent_output(
                    agent="collector",
                    node="collect_competitor",
                    title="抓取网页",
                    summary=f"{name}: {r['url']}",
                )
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
                logger.warning("collector: scrape failed competitor=%s url=%s", name, r.get("url"))
                pass

    logger.info("collector: done competitor=%s sources=%d", name, len(raw_sources))
    emit_agent_output(
        agent="collector",
        node="collect_competitor",
        title="采集完成",
        summary=f"{name} 收集到 {len(raw_sources)} 条可用来源",
        detail="\n".join(f"- {source.title}\n  {source.url}" for source in raw_sources),
        artifact_type="sources",
    )
    return {
        "raw_sources": dump_models(raw_sources),
        "finished_collectors": [comp_id],
    }


def _source_counts_by_competitor(state: AnalysisState) -> dict[str, int]:
    counts = {c["name"].lower().replace(" ", "-"): 0 for c in state.get("confirmed_competitors", [])}
    for source in restore_raw_sources(state.get("raw_sources", [])):
        if source.raw_content:
            counts[source.competitor_id] = counts.get(source.competitor_id, 0) + 1
    return counts


def _normalize_supplement_response(response) -> tuple[str, dict[str, list[str]], list[str]]:
    """Return (action, supplement_urls, skipped_competitor_ids)."""
    if not isinstance(response, dict):
        return "continue", {}, []
    action = response.get("action", "continue")
    urls = response.get("supplement_urls") or response.get("urls") or {}
    if isinstance(urls, list):
        competitor_id = response.get("competitor_id") or response.get("competitor")
        urls = {competitor_id: urls} if competitor_id else {}
    normalized_urls = {
        str(comp_id): [str(url).strip() for url in comp_urls if str(url).strip()]
        for comp_id, comp_urls in urls.items()
        if isinstance(comp_urls, list)
    }
    skipped = response.get("skip_competitors") or response.get("skipped_competitors") or []
    return action, normalized_urls, [str(item) for item in skipped]


def _scrape_supplement_urls(urls_by_competitor: dict[str, list[str]]) -> list[RawSource]:
    sources = []
    for comp_id, urls in urls_by_competitor.items():
        for url in urls:
            try:
                scraped = scrape(url)
            except Exception:
                continue
            sources.append(RawSource(
                competitor_id=comp_id,
                url=scraped["url"],
                title=scraped["title"],
                raw_content=scraped["content"],
                source_type="website",
                search_query="user_supplement",
            ))
    return sources


def join_collectors(state: AnalysisState) -> dict:
    """Barrier after collectors; optionally ask for supplements for sparse competitors."""
    competitors = state.get("confirmed_competitors", [])
    counts = _source_counts_by_competitor(state)
    low_source_ids = [
        c["name"].lower().replace(" ", "-")
        for c in competitors
        if counts.get(c["name"].lower().replace(" ", "-"), 0) < 3
    ]

    if state.get("hitl_mode", "auto") != "interactive" or not low_source_ids:
        logger.info("join_collectors: complete low_source_count=%d", len(low_source_ids))
        emit_agent_output(
            agent="collector",
            node="join_collectors",
            title="采集汇总完成",
            summary=f"已汇总 {len(competitors)} 家竞品来源",
            detail="\n".join(f"- {comp_id}: {count} 条来源" for comp_id, count in counts.items()),
            artifact_type="status",
        )
        return {
            "current_stage": "analyzing",
            "stage_status": "Collection complete, starting analysis",
        }

    logger.info("join_collectors: interrupt collector_supplement low_source_count=%d", len(low_source_ids))
    low_source_items = [
        {
            "competitor_id": c["name"].lower().replace(" ", "-"),
            "name": c["name"],
            "source_count": counts.get(c["name"].lower().replace(" ", "-"), 0),
        }
        for c in competitors
        if c["name"].lower().replace(" ", "-") in low_source_ids
    ]
    response = interrupt({
        "type": "collector_supplement",
        "run_id": state.get("run_id"),
        "message": "部分竞品有效来源少于 3 条，请补充 URL、继续已有数据或跳过竞品",
        "low_source_competitors": low_source_items,
        "default_response": {"action": "continue", "supplement_urls": {}, "skip_competitors": []},
        "timeout_seconds": 120,
    })

    action, supplement_urls, skipped = _normalize_supplement_response(response)
    new_sources = _scrape_supplement_urls(supplement_urls) if action == "supplement" else []
    skipped_set = set(skipped)
    if action == "skip":
        skipped_set.update(low_source_ids)

    remaining_competitors = [
        c for c in competitors
        if c["name"].lower().replace(" ", "-") not in skipped_set
    ]
    next_stage = "analyzing" if remaining_competitors else "error"
    next_status = (
        "Collection complete, starting analysis"
        if remaining_competitors
        else "All competitors were skipped"
    )

    return {
        "confirmed_competitors": remaining_competitors,
        "raw_sources": dump_models(new_sources),
        "supplement_urls": supplement_urls,
        "skipped_competitors": list(skipped_set),
        "hitl_history": [{
            "type": "collector_supplement",
            "response": {
                "action": action,
                "supplement_urls": supplement_urls,
                "skipped_competitors": list(skipped_set),
            },
        }],
        "current_stage": next_stage,
        "stage_status": next_status,
        "error_message": "All competitors were skipped" if not remaining_competitors else None,
    }
