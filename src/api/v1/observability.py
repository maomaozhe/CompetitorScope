"""Developer-facing APIs for persistent traces, replay, and evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.v1.runtime import get_observability_repository
from src.observability.execution import execute_eval_execution


router = APIRouter(prefix="/observability", tags=["observability"])


class CreateEvalCaseRequest(BaseModel):
    label: str = "baseline"
    annotations: dict[str, Any] = Field(default_factory=dict)


class CreateEvalExecutionRequest(BaseModel):
    variant_label: str
    model_overrides: dict[str, str] = Field(default_factory=dict)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    live_tools: bool = False


@router.get("/runs")
async def list_trace_runs(limit: int = Query(default=100, ge=1, le=500)):
    return {"runs": get_observability_repository().list_runs(limit)}


@router.get("/runs/{run_id}")
async def get_trace_run(run_id: str):
    repository = get_observability_repository()
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Trace run not found")
    return {"run": run, "spans": repository.list_spans(run_id)}


@router.get("/runs/{run_id}/events")
async def list_trace_events(
    run_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    repository = get_observability_repository()
    if repository.get_run(run_id) is None:
        raise HTTPException(404, "Trace run not found")
    return {"events": repository.list_events(run_id, after_seq=after_seq, limit=limit)}


@router.get("/runs/{run_id}/snapshots")
async def list_trace_snapshots(run_id: str):
    repository = get_observability_repository()
    if repository.get_run(run_id) is None:
        raise HTTPException(404, "Trace run not found")
    return {"snapshots": repository.list_snapshots(run_id)}


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    artifact = get_observability_repository().read_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    artifact.pop("path", None)
    return artifact


@router.post("/runs/{run_id}/eval-cases")
async def create_eval_case(run_id: str, body: CreateEvalCaseRequest):
    repository = get_observability_repository()
    try:
        return repository.create_eval_case(run_id, body.label, body.annotations)
    except KeyError as exc:
        raise HTTPException(404, "Trace run not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/eval-cases/{case_id}/executions")
async def create_eval_execution(
    case_id: str,
    body: CreateEvalExecutionRequest,
    background_tasks: BackgroundTasks,
):
    repository = get_observability_repository()
    if repository.get_eval_case(case_id) is None:
        raise HTTPException(404, "Eval case not found")
    execution = repository.create_eval_execution(
        case_id,
        body.variant_label,
        {
            "model_overrides": body.model_overrides,
            "parameter_overrides": body.parameter_overrides,
            "prompt_overrides": body.prompt_overrides,
            "live_tools": body.live_tools,
        },
    )
    background_tasks.add_task(
        execute_eval_execution, repository, execution["execution_id"]
    )
    return execution


@router.get("/eval-cases/{case_id}/compare")
async def compare_eval_executions(case_id: str):
    repository = get_observability_repository()
    case = repository.get_eval_case(case_id)
    if case is None:
        raise HTTPException(404, "Eval case not found")
    source_run = repository.get_run(case["source_run_id"])
    baseline_metrics = repository.run_metrics(case["source_run_id"])
    executions = repository.list_eval_executions(case_id)
    for execution in executions:
        metrics = execution.get("metrics") or {}
        execution["delta"] = {
            key: metrics[key] - baseline_metrics[key]
            for key in ("duration_ms", "token_total", "error_count", "tool_calls", "decision_count")
            if isinstance(metrics.get(key), (int, float))
            and isinstance(baseline_metrics.get(key), (int, float))
        }
    return {
        "case_id": case_id,
        "baseline": {"run": source_run, "metrics": baseline_metrics},
        "executions": executions,
    }
