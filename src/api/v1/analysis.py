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
    get_event_queue,
    initial_state,
    run_until_pause,
)

router = APIRouter()


class CreateAnalysisRequest(BaseModel):
    query: str
    competitors: list[str] = []
    dimensions: list[str] = []
    hitl_mode: str = "auto"


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

    q = get_event_queue(run_id)
    if not q:
        raise HTTPException(404, "Run event queue not found")

    async def event_generator():
        for event in get_event_history(run_id):
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(event.get("data", {}), ensure_ascii=False),
            }
        while True:
            event = await q.get()
            if event is None:
                # Sentinel: run completed or stopped
                break
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(event.get("data", {}), ensure_ascii=False),
            }

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
    }


@router.delete("/analysis/{run_id}")
async def delete_analysis(run_id: str):
    """Cancel a running analysis and clean up its state."""
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    RUN_STORE[run_id]["done"] = True
    RUN_STORE[run_id]["pending_interrupt"] = None
    # Signal the SSE queue to stop
    q = get_event_queue(run_id)
    if q:
        try:
            q.put_nowait(None)
        except asyncio.QueueFull:
            pass
    return {"run_id": run_id, "status": "cancelled"}
