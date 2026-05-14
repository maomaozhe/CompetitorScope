"""Shared in-memory runtime for analysis API routes."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graph.state import AnalysisState
from src.graph.workflow import build_workflow


CHECKPOINTER = MemorySaver()
WORKFLOW = build_workflow(checkpointer=CHECKPOINTER)
RUN_STORE: dict[str, dict[str, Any]] = {}

# Per-run event queues for true SSE streaming (replaces polling)
# Maps run_id → asyncio.Queue of SSE event dicts
_EVENT_QUEUES: dict[str, asyncio.Queue] = {}
_EVENT_HISTORY: dict[str, list[dict[str, Any]]] = {}


def graph_config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def initial_state(
    *,
    run_id: str,
    query: str,
    competitors: list[str] | None = None,
    dimensions: list[str] | None = None,
    hitl_mode: str = "auto",
) -> AnalysisState:
    return {
        "run_id": run_id,
        "query": query,
        "hitl_mode": "interactive" if hitl_mode == "interactive" else "auto",
        "candidate_competitors": [],
        "confirmed_competitors": [{"name": c, "website": ""} for c in (competitors or [])],
        "analysis_dimensions": dimensions or ["positioning", "features", "pricing", "reviews"],
        "report_outline": "",
        "comparison_dimensions": dimensions or ["positioning", "features", "pricing", "reviews"],
        "comparison_focus_notes": "",
        "current_stage": "planning",
        "stage_status": "Starting...",
        "error_message": None,
        "raw_sources": [],
        "competitor_profiles": [],
        "evidence_items": [],
        "finished_collectors": [],
        "finished_analysts": [],
        "hitl_history": [],
        "supplement_urls": {},
        "skipped_competitors": [],
        "comparison_result": None,
        "report": None,
    }


def create_run(state: AnalysisState) -> None:
    run_id = state["run_id"]
    RUN_STORE[run_id] = {
        "state": state,
        "done": False,
        "pending_interrupt": None,
        "created_at": time.time(),
    }
    _EVENT_QUEUES[run_id] = asyncio.Queue()
    _EVENT_HISTORY[run_id] = []


def get_event_queue(run_id: str) -> asyncio.Queue | None:
    return _EVENT_QUEUES.get(run_id)


def _emit_event(run_id: str, event: str, data: dict) -> None:
    """Emit an SSE event to the run's queue (non-blocking)."""
    item = {"event": event, "data": data}
    _EVENT_HISTORY.setdefault(run_id, []).append(item)
    q = _EVENT_QUEUES.get(run_id)
    if q:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass


def _emit_agent_output(
    run_id: str,
    *,
    agent: str,
    node: str,
    title: str,
    summary: str,
    detail: str = "",
    artifact_type: str = "text",
) -> None:
    _emit_event(run_id, "agent_output", {
        "id": f"{node}-{len(_EVENT_HISTORY.get(run_id, []))}",
        "agent": agent,
        "node": node,
        "title": title,
        "summary": summary,
        "detail": detail,
        "artifact_type": artifact_type,
        "created_at": time.time(),
    })


def _shorten(value: Any, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else f"{text[:limit].rstrip()}\n..."


def _summarize_agent_result(node_name: str, result: dict) -> tuple[str, str, str, str] | None:
    if not isinstance(result, dict):
        return None

    if node_name == "planner_discover":
        candidates = result.get("candidate_competitors") or []
        confirmed = result.get("confirmed_competitors") or []
        names = ", ".join(item.get("name", "") for item in confirmed if isinstance(item, dict))
        detail = "\n".join(
            f"- {item.get('name', '')}: {item.get('website', '')}"
            for item in candidates
            if isinstance(item, dict)
        )
        return ("候选竞品已确认", f"确认 {len(confirmed)} 家竞品：{names}", detail, "competitors")

    if node_name == "planner_outline":
        dimensions = result.get("analysis_dimensions") or []
        outline = result.get("report_outline") or ""
        return ("分析计划已生成", f"维度：{', '.join(dimensions)}", _shorten(outline), "outline")

    if node_name == "collect_competitor":
        sources = result.get("raw_sources") or []
        competitor_id = (result.get("finished_collectors") or [""])[0]
        detail = "\n".join(
            f"- {item.get('title') or item.get('url')}\n  {item.get('url')}"
            for item in sources
            if isinstance(item, dict)
        )
        return ("数据采集完成", f"{competitor_id} 收集到 {len(sources)} 条来源", _shorten(detail), "sources")

    if node_name == "join_collectors":
        return ("采集汇总完成", result.get("stage_status", "Collection complete"), "", "status")

    if node_name == "analyze_competitor":
        profiles = result.get("competitor_profiles") or []
        evidence = result.get("evidence_items") or []
        if not profiles:
            competitor_id = (result.get("finished_analysts") or [""])[0]
            return ("结构化分析跳过", f"{competitor_id} 没有可分析来源", "", "profile")
        profile = profiles[0]
        name = profile.get("name", "competitor") if isinstance(profile, dict) else "competitor"
        detail = ""
        if isinstance(profile, dict):
            features = profile.get("features") or []
            feature_names = [
                item.get("name", "")
                for item in features
                if isinstance(item, dict) and item.get("name")
            ]
            detail = "\n".join([
                f"定位：{profile.get('one_liner', '')}",
                f"技术形态：{profile.get('tech_form', '')}",
                f"功能：{', '.join(feature_names[:8])}",
                f"好评：{', '.join((profile.get('positive_themes') or [])[:3])}",
                f"吐槽：{', '.join((profile.get('negative_themes') or [])[:3])}",
            ])
        return ("结构化分析完成", f"{name} 产出 profile，证据 {len(evidence)} 条", detail, "profile")

    if node_name == "join_analysts":
        return ("分析汇总完成", "所有竞品结构化分析已汇总", "", "status")

    if node_name == "comparator":
        comparison = result.get("comparison_result") or {}
        insights = comparison.get("key_insights") or [] if isinstance(comparison, dict) else []
        detail = "\n".join(f"- {item}" for item in insights)
        return ("横向对比完成", f"生成 {len(insights)} 条关键洞察", detail, "comparison")

    if node_name == "writer":
        report = result.get("report") or {}
        markdown = report.get("content_markdown", "") if isinstance(report, dict) else ""
        return ("报告生成完成", f"Markdown 报告 {len(markdown)} 字符", _shorten(markdown), "report")

    return None


def get_event_history(run_id: str) -> list[dict[str, Any]]:
    return list(_EVENT_HISTORY.get(run_id, []))


async def _snapshot_state(run_id: str) -> dict:
    snapshot = WORKFLOW.get_state(graph_config(run_id))
    values = dict(snapshot.values or {})
    if values:
        RUN_STORE[run_id]["state"] = values
    return values


async def run_until_pause(run_id: str, graph_input: AnalysisState | Command) -> None:
    config = graph_config(run_id)
    RUN_STORE[run_id]["done"] = False
    RUN_STORE[run_id]["pending_interrupt"] = None
    close_stream = True

    # Map node names → agent IDs for SSE events
    NODE_AGENT_MAP = {
        "planner_discover": "planner",
        "planner_outline": "planner",
        "collect_competitor": "collector",
        "join_collectors": "collector",
        "analyze_competitor": "analyst",
        "join_analysts": "analyst",
        "comparator": "comparator",
        "writer": "writer",
    }

    try:
        async for event in WORKFLOW.astream(graph_input, config=config, stream_mode="debug"):
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            payload = event.get("payload", {})
            node_name = payload.get("name", "") if isinstance(payload, dict) else ""

            if event_type == "task":
                agent_id = NODE_AGENT_MAP.get(node_name, node_name)
                _emit_event(run_id, "agent_start", {
                    "agent": agent_id,
                    "node": node_name,
                    "message": _node_status_message(node_name),
                })

            elif event_type == "task_result":
                agent_id = NODE_AGENT_MAP.get(node_name, node_name)
                error = payload.get("error")
                if error:
                    _emit_event(run_id, "error", {"agent": agent_id, "message": str(error)})
                else:
                    interrupts = payload.get("interrupts") or []
                    if interrupts:
                        interrupt_obj = interrupts[0]
                        value = interrupt_obj.get("value", {}) if isinstance(interrupt_obj, dict) else {}
                        if isinstance(value, dict):
                            value["interrupt_id"] = interrupt_obj.get("id", "")
                        else:
                            value = {"interrupt_id": interrupt_obj.get("id", "")}
                        RUN_STORE[run_id]["pending_interrupt"] = {
                            "payload": value if isinstance(value, dict) else {},
                            "created_at": time.time(),
                        }
                        state = await _snapshot_state(run_id)
                        state["current_stage"] = state.get("current_stage", "planning")
                        state["stage_status"] = "Waiting for human input"
                        RUN_STORE[run_id]["state"] = state
                        _emit_event(run_id, "hitl_request", value if isinstance(value, dict) else {})
                        asyncio.create_task(
                            _auto_resume_after_timeout(run_id, value if isinstance(value, dict) else {})
                        )
                        close_stream = False
                        return

                    _emit_event(run_id, "agent_complete", {"agent": agent_id, "node": node_name})
                    result = payload.get("result", {})
                    summary = _summarize_agent_result(node_name, result)
                    if summary:
                        title, text, detail, artifact_type = summary
                        _emit_agent_output(
                            run_id,
                            agent=agent_id,
                            node=node_name,
                            title=title,
                            summary=text,
                            detail=detail,
                            artifact_type=artifact_type,
                        )
                    # Forward report_chunk if writer finished
                    if node_name == "writer" and isinstance(result, dict):
                        report = result.get("report")
                        if report and isinstance(report, dict) and "content_markdown" in report:
                            _emit_event(run_id, "report_chunk", {"content": report["content_markdown"]})

            elif event_type == "__interrupt__":
                interrupt_obj = event.get("__interrupt__", [{}])[0]
                if isinstance(interrupt_obj, dict):
                    value = interrupt_obj.get("value", {})
                    if isinstance(value, dict):
                        value["interrupt_id"] = interrupt_obj.get("id", "")
                    else:
                        value = {"interrupt_id": interrupt_obj.get("id", "")}
                    RUN_STORE[run_id]["pending_interrupt"] = {
                        "payload": value if isinstance(value, dict) else {},
                        "created_at": time.time(),
                    }
                    state = await _snapshot_state(run_id)
                    state["current_stage"] = state.get("current_stage", "planning")
                    state["stage_status"] = "Waiting for human input"
                    RUN_STORE[run_id]["state"] = state
                    _emit_event(run_id, "hitl_request", value if isinstance(value, dict) else {})
                    asyncio.create_task(_auto_resume_after_timeout(run_id, value if isinstance(value, dict) else {}))
                    close_stream = False
                    return

            # Update state snapshot
            await _snapshot_state(run_id)

        snapshot = WORKFLOW.get_state(config)
        RUN_STORE[run_id]["state"] = dict(snapshot.values or RUN_STORE[run_id]["state"])
        RUN_STORE[run_id]["done"] = not snapshot.next
        if RUN_STORE[run_id]["done"]:
            RUN_STORE[run_id]["pending_interrupt"] = None
        _emit_event(run_id, "complete", {"done": True})

    except Exception as exc:
        state = RUN_STORE[run_id]["state"]
        state["current_stage"] = "error"
        state["error_message"] = str(exc)
        state["stage_status"] = "Pipeline failed"
        RUN_STORE[run_id]["state"] = state
        RUN_STORE[run_id]["done"] = True
        RUN_STORE[run_id]["pending_interrupt"] = None
        _emit_event(run_id, "error", {"message": str(exc)})
    finally:
        # Signal end-of-stream
        q = _EVENT_QUEUES.get(run_id)
        if close_stream and q:
            try:
                q.put_nowait(None)  # None = sentinel for "done"
            except asyncio.QueueFull:
                pass


def _node_status_message(node_name: str) -> str:
    return {
        "planner_discover": "发现竞品中...",
        "planner_outline": "生成大纲中...",
        "collect_competitor": "采集数据中...",
        "join_collectors": "汇总数据中...",
        "analyze_competitor": "分析结构化中...",
        "join_analysts": "汇总分析中...",
        "comparator": "横向对比中...",
        "writer": "生成报告中...",
    }.get(node_name, "处理中...")


async def _auto_resume_after_timeout(run_id: str, payload: dict) -> None:
    await asyncio.sleep(payload.get("timeout_seconds", 30))
    run = RUN_STORE.get(run_id)
    if not run or run.get("done") or not run.get("pending_interrupt"):
        return
    pending = run["pending_interrupt"]["payload"]
    if pending.get("interrupt_id") != payload.get("interrupt_id"):
        return
    default_response = pending.get("default_response", {})
    run["pending_interrupt"] = None
    _emit_event(run_id, "hitl_timeout", {"response": default_response, "interrupt": pending})
    await run_until_pause(run_id, Command(resume=default_response))


async def resume_run(run_id: str, response: dict) -> None:
    run = RUN_STORE[run_id]
    pending = run.get("pending_interrupt")
    run["pending_interrupt"] = None
    _emit_event(run_id, "hitl_resumed", {
        "response": response,
        "interrupt": pending["payload"] if pending else None,
    })
    await run_until_pause(run_id, Command(resume=response))
