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
                    # Forward report_chunk if writer finished
                    result = payload.get("result", {})
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
        _emit_event(run_id, "complete", {"done": True})

    except Exception as exc:
        state = RUN_STORE[run_id]["state"]
        state["current_stage"] = "error"
        state["error_message"] = str(exc)
        state["stage_status"] = "Pipeline failed"
        RUN_STORE[run_id]["state"] = state
        RUN_STORE[run_id]["done"] = True
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
    if not run or not run.get("pending_interrupt"):
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
