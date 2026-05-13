"""Analysis API — create/run/query analysis tasks."""

import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.api.v1.runtime import RUN_STORE, create_run, initial_state, run_until_pause
from src.graph.serialization import report as restore_report

router = APIRouter()


class CreateAnalysisRequest(BaseModel):
    query: str
    competitors: list[str] = []
    dimensions: list[str] = []
    hitl_mode: str = "auto"


@router.post("/analysis")
async def create_analysis(req: CreateAnalysisRequest, background_tasks: BackgroundTasks):
    run_id = uuid.uuid4().hex[:12]
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
        last_event_idx = 0
        last_stage = None
        report_sent = False
        while True:
            state = RUN_STORE[run_id]["state"]
            stage = state.get("current_stage", "planning")

            stage_events = {
                "planning": ("planner", "compass", "分析需求中..."),
                "collecting": ("collector", "search", "采集数据中..."),
                "analyzing": ("analyst", "chart", "分析结构化中..."),
                "comparing": ("comparator", "compare", "横向对比中..."),
                "writing": ("writer", "pen", "生成报告中..."),
            }
            if stage in stage_events and stage != last_stage:
                agent, avatar, msg = stage_events[stage]
                data = {"type": "agent_start", "agent": agent, "avatar": avatar, "message": msg}
                yield {"event": "agent_start", "data": json.dumps(data, ensure_ascii=False)}
                last_stage = stage

            events = RUN_STORE[run_id]["events"]
            while last_event_idx < len(events):
                item = events[last_event_idx]
                last_event_idx += 1
                data = {"type": item["event"], "payload": item["data"]}
                yield {"event": item["event"], "data": json.dumps(data, ensure_ascii=False)}

            report = restore_report(state.get("report"))
            if report and not report_sent:
                data = {"type": "report_chunk", "content": report.content_markdown}
                yield {"event": "report_chunk", "data": json.dumps(data, ensure_ascii=False)}
                report_sent = True

            if RUN_STORE[run_id]["done"]:
                break

            await asyncio.sleep(2)

        yield {"event": "complete", "data": json.dumps({"type": "complete", "done": True})}

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
    return {"run_id": run_id, "status": "cancelled"}

