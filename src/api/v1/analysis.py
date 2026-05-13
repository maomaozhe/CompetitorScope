"""Analysis API — create/run/query analysis tasks."""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.api.v1.runtime import (
    RUN_STORE,
    create_run,
    get_event_history,
    initial_state,
    run_until_pause,
)

router = APIRouter()

AGENT_DEFAULTS = [
    {"id": "planner", "status": "idle", "message": "等待启动"},
    {"id": "collector", "status": "idle", "message": "等待启动"},
    {"id": "analyst", "status": "idle", "message": "等待启动"},
    {"id": "comparator", "status": "idle", "message": "等待启动"},
    {"id": "writer", "status": "idle", "message": "等待启动"},
]


class CreateAnalysisRequest(BaseModel):
    query: str
    competitors: list[str] = []
    dimensions: list[str] = []
    hitl_mode: str = "auto"


def _agent_statuses_from_history(run_id: str) -> list[dict[str, str]]:
    statuses = {agent["id"]: dict(agent) for agent in AGENT_DEFAULTS}
    for item in get_event_history(run_id):
        event = item.get("event")
        data = item.get("data", {})
        agent = data.get("agent") if isinstance(data, dict) else None
        if not agent or agent not in statuses:
            if event == "complete":
                statuses["writer"].update({"status": "complete", "message": "已完成"})
            continue

        if event == "agent_start":
            statuses[agent].update({
                "status": "running",
                "message": str(data.get("message") or "处理中..."),
            })
        elif event == "agent_complete":
            statuses[agent].update({"status": "complete", "message": "已完成"})
        elif event == "error":
            statuses[agent].update({
                "status": "error",
                "message": str(data.get("message") or "运行失败"),
            })

    return [statuses[agent["id"]] for agent in AGENT_DEFAULTS]


@router.post("/analysis")
async def create_analysis(req: CreateAnalysisRequest, background_tasks: BackgroundTasks):
    run_id = req.query[:12].replace(" ", "-") + "-" + __import__("uuid").uuid4().hex[:8]
    state = initial_state(
        run_id=run_id,
        query=req.query,
        competitors=req.competitors,
        dimensions=req.dimensions,
        hitl_mode=req.hitl_mode,
    )
    create_run(state)
    background_tasks.add_task(run_until_pause, run_id, state)
    return {"run_id": run_id, "status": "running", "stream_url": f"/api/v1/analysis/{run_id}/stream"}


@router.get("/analysis/{run_id}/stream")
async def stream_analysis(run_id: str):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Run not found")

    async def event_generator():
        sent_count = 0
        while True:
            history = get_event_history(run_id)
            for event in history[sent_count:]:
                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(event.get("data", {}), ensure_ascii=False),
                }
            sent_count = len(history)

            run = RUN_STORE.get(run_id)
            if not run or (run.get("done") and sent_count >= len(get_event_history(run_id))):
                break

            await asyncio.sleep(0.25)

    return EventSourceResponse(event_generator())


@router.get("/analysis/{run_id}")
async def get_analysis(run_id: str):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    state = RUN_STORE[run_id]["state"]
    return {
        "run_id": run_id,
        "stage": state.get("current_stage", "unknown"),
        "status": state.get("stage_status", ""),
        "done": RUN_STORE[run_id]["done"],
        "pending_hitl": RUN_STORE[run_id].get("pending_interrupt") is not None,
        "agents": _agent_statuses_from_history(run_id),
    }


@router.delete("/analysis/{run_id}")
async def delete_analysis(run_id: str):
    """Cancel a running analysis and clean up its state."""
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    RUN_STORE[run_id]["done"] = True
    RUN_STORE[run_id]["pending_interrupt"] = None
    return {"run_id": run_id, "status": "cancelled"}
