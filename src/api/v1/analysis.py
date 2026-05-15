"""Analysis API — create/run/query analysis tasks."""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.api.v1.runtime import (
    RUN_STORE,
    create_run,
    get_event_history,
    initial_state,
    run_until_pause,
    wait_for_events_after,
)

router = APIRouter()

AGENT_DEFAULTS = [
    {"id": "planner", "status": "idle", "message": "等待启动"},
    {"id": "collector", "status": "idle", "message": "等待启动"},
    {"id": "analyst", "status": "idle", "message": "等待启动"},
    {"id": "comparator", "status": "idle", "message": "等待启动"},
    {"id": "writer", "status": "idle", "message": "等待启动"},
]


def _shorten(value: object, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else f"{text[:limit].rstrip()}\n..."


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


def _agent_outputs_from_history(run_id: str) -> list[dict]:
    return [
        item.get("data", {})
        for item in get_event_history(run_id)
        if item.get("event") == "agent_output" and isinstance(item.get("data"), dict)
    ]


def _agent_outputs_from_state(run_id: str, state: dict) -> list[dict]:
    """Build snapshot outputs so the UI can recover if SSE events were missed."""
    outputs: list[dict] = []
    created_at = RUN_STORE[run_id].get("created_at", 0)

    confirmed = state.get("confirmed_competitors") or []
    candidates = state.get("candidate_competitors") or confirmed
    if confirmed:
        names = ", ".join(item.get("name", "") for item in confirmed if isinstance(item, dict))
        outputs.append({
            "id": "snapshot-planner-competitors",
            "agent": "planner",
            "node": "planner_discover",
            "title": "候选竞品已确认",
            "summary": f"确认 {len(confirmed)} 家竞品：{names}",
            "detail": "\n".join(
                f"- {item.get('name', '')}: {item.get('website', '')}"
                for item in candidates
                if isinstance(item, dict)
            ),
            "artifact_type": "competitors",
            "created_at": created_at,
        })

    outline = state.get("report_outline") or ""
    dimensions = state.get("analysis_dimensions") or []
    if outline:
        outputs.append({
            "id": "snapshot-planner-outline",
            "agent": "planner",
            "node": "planner_outline",
            "title": "分析计划已生成",
            "summary": f"维度：{', '.join(dimensions)}",
            "detail": _shorten(outline),
            "artifact_type": "outline",
            "created_at": created_at,
        })

    raw_sources = [item for item in state.get("raw_sources", []) if isinstance(item, dict)]
    if raw_sources:
        counts: dict[str, int] = {}
        for source in raw_sources:
            comp_id = str(source.get("competitor_id") or "unknown")
            counts[comp_id] = counts.get(comp_id, 0) + 1
        outputs.append({
            "id": "snapshot-collector-sources",
            "agent": "collector",
            "node": "join_collectors",
            "title": "采集汇总完成",
            "summary": f"已汇总 {len(raw_sources)} 条来源",
            "detail": "\n".join(
                f"- {source.get('title') or source.get('url')}\n  {source.get('url')}"
                for source in raw_sources[:12]
            ),
            "artifact_type": "sources",
            "created_at": created_at,
        })

    profiles = [item for item in state.get("competitor_profiles", []) if isinstance(item, dict)]
    if profiles:
        evidence = [item for item in state.get("evidence_items", []) if isinstance(item, dict)]
        outputs.append({
            "id": "snapshot-analyst-profiles",
            "agent": "analyst",
            "node": "join_analysts",
            "title": "结构化分析完成",
            "summary": f"生成 {len(profiles)} 个竞品 profile，证据 {len(evidence)} 条",
            "detail": "\n".join(
                f"- {profile.get('name', profile.get('competitor_id', 'competitor'))}: {profile.get('one_liner', '')}"
                for profile in profiles
            ),
            "artifact_type": "profile",
            "created_at": created_at,
        })

    comparison = state.get("comparison_result")
    if isinstance(comparison, dict):
        insights = comparison.get("key_insights") or []
        outputs.append({
            "id": "snapshot-comparator-result",
            "agent": "comparator",
            "node": "comparator",
            "title": "横向对比完成",
            "summary": f"生成 {len(insights)} 条关键洞察",
            "detail": "\n".join(f"- {item}" for item in insights),
            "artifact_type": "comparison",
            "created_at": created_at,
        })
    elif state.get("current_stage") == "comparing" and profiles:
        dimensions = state.get("comparison_dimensions") or state.get("analysis_dimensions") or []
        outputs.append({
            "id": "snapshot-comparator-running",
            "agent": "comparator",
            "node": "comparator",
            "title": "准备横向对比",
            "summary": f"正在比较 {len(profiles)} 个竞品 profile",
            "detail": f"比较维度：{', '.join(dimensions)}",
            "artifact_type": "comparison",
            "created_at": created_at,
        })

    return outputs


def _agent_outputs_for_response(run_id: str, state: dict) -> list[dict]:
    outputs_by_id = {
        output.get("id"): output
        for output in _agent_outputs_from_state(run_id, state)
        if output.get("id")
    }
    for output in _agent_outputs_from_history(run_id):
        output_id = output.get("id")
        if output_id:
            outputs_by_id[output_id] = output
    return list(outputs_by_id.values())[-80:]


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
async def stream_analysis(run_id: str, request: Request):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Run not found")

    async def event_generator():
        try:
            last_seq = int(request.headers.get("last-event-id") or "0")
        except ValueError:
            last_seq = 0

        while True:
            events = await wait_for_events_after(run_id, last_seq)
            for event in events:
                seq = int(event.get("seq", 0))
                last_seq = max(last_seq, seq)
                yield {
                    "id": str(seq),
                    "event": event.get("event", "message"),
                    "data": json.dumps(event.get("data", {}), ensure_ascii=False),
                }

            run = RUN_STORE.get(run_id)
            done = run and run.get("done")
            if done:
                has_unread = any(
                    item.get("seq", 0) > last_seq
                    for item in get_event_history(run_id)
                )
                if not has_unread:
                    break

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
        "agent_outputs": _agent_outputs_for_response(run_id, state),
    }


@router.delete("/analysis/{run_id}")
async def delete_analysis(run_id: str):
    """Cancel a running analysis and clean up its state."""
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    RUN_STORE[run_id]["done"] = True
    RUN_STORE[run_id]["pending_interrupt"] = None
    return {"run_id": run_id, "status": "cancelled"}
