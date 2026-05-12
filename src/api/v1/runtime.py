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
    RUN_STORE[state["run_id"]] = {
        "state": state,
        "done": False,
        "pending_interrupt": None,
        "events": [],
        "created_at": time.time(),
    }


def add_event(run_id: str, event: str, data: dict) -> None:
    RUN_STORE[run_id]["events"].append({
        "event": event,
        "data": data,
        "ts": time.time(),
    })


def _snapshot_state(run_id: str) -> dict:
    snapshot = WORKFLOW.get_state(graph_config(run_id))
    values = dict(snapshot.values or {})
    if values:
        RUN_STORE[run_id]["state"] = values
    return values


async def run_until_pause(run_id: str, graph_input: AnalysisState | Command) -> None:
    config = graph_config(run_id)
    RUN_STORE[run_id]["done"] = False
    RUN_STORE[run_id]["pending_interrupt"] = None
    try:
        async for event in WORKFLOW.astream(graph_input, config=config):
            if "__interrupt__" in event:
                interrupt_obj = event["__interrupt__"][0]
                payload = dict(interrupt_obj.value)
                payload["interrupt_id"] = interrupt_obj.id
                RUN_STORE[run_id]["pending_interrupt"] = {
                    "payload": payload,
                    "created_at": time.time(),
                }
                state = _snapshot_state(run_id)
                state["current_stage"] = state.get("current_stage", "planning")
                state["stage_status"] = "Waiting for human input"
                RUN_STORE[run_id]["state"] = state
                add_event(run_id, "hitl_request", payload)
                asyncio.create_task(auto_resume_after_timeout(run_id, payload))
                return
            _snapshot_state(run_id)

        snapshot = WORKFLOW.get_state(config)
        RUN_STORE[run_id]["state"] = dict(snapshot.values or RUN_STORE[run_id]["state"])
        RUN_STORE[run_id]["done"] = not snapshot.next
    except Exception as exc:
        state = RUN_STORE[run_id]["state"]
        state["current_stage"] = "error"
        state["error_message"] = str(exc)
        state["stage_status"] = "Pipeline failed"
        RUN_STORE[run_id]["state"] = state
        RUN_STORE[run_id]["done"] = True
        add_event(run_id, "error", {"message": str(exc)})


async def auto_resume_after_timeout(run_id: str, payload: dict) -> None:
    await asyncio.sleep(payload.get("timeout_seconds", 30))
    run = RUN_STORE.get(run_id)
    if not run or not run.get("pending_interrupt"):
        return
    pending = run["pending_interrupt"]["payload"]
    if pending.get("interrupt_id") != payload.get("interrupt_id"):
        return
    default_response = pending.get("default_response", {})
    run["pending_interrupt"] = None
    add_event(run_id, "hitl_timeout", {"response": default_response, "interrupt": pending})
    await run_until_pause(run_id, Command(resume=default_response))


async def resume_run(run_id: str, response: dict) -> None:
    run = RUN_STORE[run_id]
    pending = run.get("pending_interrupt")
    run["pending_interrupt"] = None
    add_event(run_id, "hitl_resumed", {
        "response": response,
        "interrupt": pending["payload"] if pending else None,
    })
    await run_until_pause(run_id, Command(resume=response))
