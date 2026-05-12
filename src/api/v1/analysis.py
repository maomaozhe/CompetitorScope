"""Analysis API — create/run/query analysis tasks."""

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.graph.workflow import build_workflow
from src.graph.state import AnalysisState

router = APIRouter()


class CreateAnalysisRequest(BaseModel):
    query: str
    competitors: list[str] = []
    dimensions: list[str] = []
    hitl_mode: str = "auto"


# In-memory store for demo (replace with DB in production)
_RUN_STORE: dict[str, Any] = {}


@router.post("/analysis")
async def create_analysis(req: CreateAnalysisRequest, background_tasks: BackgroundTasks):
    run_id = uuid.uuid4().hex[:12]

    initial_state: AnalysisState = {
        "run_id": run_id,
        "query": req.query,
        "confirmed_competitors": [{"name": c} for c in req.competitors] if req.competitors else [],
        "analysis_dimensions": req.dimensions or ["positioning", "features", "pricing", "reviews"],
        "report_outline": "",
        "current_stage": "planning",
        "stage_status": "Starting...",
        "error_message": None,
        "raw_sources": [],
        "competitor_profiles": [],
        "evidence_items": [],
        "comparison_result": None,
        "report": None,
    }

    _RUN_STORE[run_id] = {"state": initial_state, "done": False}

    async def run_pipeline():
        workflow = build_workflow()
        state = initial_state.copy()
        async for event in workflow.astream(state):
            # Update store with latest state
            for k, v in event.items():
                if k in state:
                    state[k] = v if not isinstance(v, list) else state.get(k, []) + v if v else state[k]
            _RUN_STORE[run_id]["state"] = state

        _RUN_STORE[run_id]["done"] = True

    background_tasks.add_task(run_pipeline)

    return {"run_id": run_id, "status": "running", "stream_url": f"/api/v1/analysis/{run_id}/stream"}


@router.get("/analysis/{run_id}/stream")
async def stream_analysis(run_id: str):
    if run_id not in _RUN_STORE:
        raise HTTPException(404, "Run not found")

    async def event_generator():
        import asyncio, time
        last_done = False
        while not _RUN_STORE[run_id]["done"]:
            state = _RUN_STORE[run_id]["state"]
            stage = state.get("current_stage", "planning")
            status = state.get("stage_status", "")

            # Emit agent stage events
            stage_events = {
                "planning": ("planner", "🧭", "分析需求中..."),
                "collecting": ("collector", "🕷️", "采集数据中..."),
                "analyzing": ("analyst", "📊", "分析结构化中..."),
                "comparing": ("comparator", "🆚", "横向对比中..."),
                "writing": ("writer", "✍️", "生成报告中..."),
            }
            if stage in stage_events and stage != "complete":
                agent, avatar, msg = stage_events[stage]
                yield {"event": "agent_start", "data": f'{{"agent":"{agent}","avatar":"{avatar}","message":"{msg}"}}'}

            if state.get("report"):
                report = state["report"]
                yield {"event": "report_chunk", "data": f'{{"content":"{report.content_markdown[:200]}"}}'}

            await asyncio.sleep(2)

        # Final complete event
        yield {"event": "complete", "data": '{"done": true}'}

    return EventSourceResponse(event_generator())


@router.get("/analysis/{run_id}")
async def get_analysis(run_id: str):
    if run_id not in _RUN_STORE:
        raise HTTPException(404, "Not found")
    state = _RUN_STORE[run_id]["state"]
    return {
        "run_id": run_id,
        "stage": state.get("current_stage", "unknown"),
        "status": state.get("stage_status", ""),
        "done": _RUN_STORE[run_id]["done"],
    }


@router.get("/reports/{run_id}")
async def get_report(run_id: str):
    if run_id not in _RUN_STORE:
        raise HTTPException(404, "Not found")
    state = _RUN_STORE[run_id]["state"]
    report = state.get("report")
    if not report:
        return {"status": "pending"}
    return {
        "report_id": report.report_id,
        "title": report.title,
        "markdown": report.content_markdown,
        "bibliography": report.bibliography,
    }