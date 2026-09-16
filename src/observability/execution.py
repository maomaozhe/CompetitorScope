"""Candidate execution service for frozen-input evaluation runs."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from src.observability.replay import reset_replay_context, set_replay_context
from src.observability.repository import ObservabilityRepository


async def execute_eval_execution(
    repository: ObservabilityRepository,
    execution_id: str,
    *,
    runner: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Run a candidate with recorded tool outputs unless live_tools is explicit."""
    from src.api.v1 import runtime

    execution = repository.get_eval_execution(execution_id)
    if execution is None:
        raise KeyError(execution_id)
    case = repository.get_eval_case(execution["case_id"])
    if case is None:
        raise KeyError(execution["case_id"])
    manifest = case["manifest"]
    request = manifest.get("request", {})
    variant = execution.get("variant", {})
    run_id = f"eval-{execution_id[:8]}-{uuid.uuid4().hex[:6]}"
    repository.update_eval_execution(execution_id, run_id=run_id, status="running")

    competitors = request.get("competitors") or []
    competitor_names = [
        item.get("name", "") if isinstance(item, dict) else str(item)
        for item in competitors
    ]
    hitl_responses = list(manifest.get("hitl_responses") or [])
    state = runtime.initial_state(
        run_id=run_id,
        query=request.get("query", ""),
        competitors=[name for name in competitor_names if name],
        dimensions=request.get("dimensions") or None,
        hitl_mode="interactive" if hitl_responses else "auto",
    )
    catalog = {} if variant.get("live_tools") else repository.build_replay_catalog(execution["case_id"])
    tokens = set_replay_context(
        tool_results=catalog,
        model_overrides=variant.get("model_overrides"),
        parameter_overrides=variant.get("parameter_overrides"),
        prompt_overrides=variant.get("prompt_overrides"),
        freeze_tools=not variant.get("live_tools", False),
    )
    try:
        runtime.create_run(state)
        repository.update_run(run_id, pinned=True)
        selected_runner = runner or runtime.run_until_pause
        await selected_runner(run_id, state)
        for recorded in hitl_responses:
            if not runtime.RUN_STORE.get(run_id, {}).get("pending_interrupt"):
                break
            await runtime.resume_run(
                run_id, recorded.get("response") or {}, runner=selected_runner
            )
        if runtime.RUN_STORE.get(run_id, {}).get("pending_interrupt"):
            raise RuntimeError("Frozen HITL responses were exhausted before run completion")
        trace_run = repository.get_run(run_id) or {}
        status = "completed" if trace_run.get("status") == "completed" else "failed"
        return repository.update_eval_execution(
            execution_id,
            status=status,
            metrics={
                **repository.run_metrics(run_id),
                "deterministic": not variant.get("live_tools", False),
            },
            finished_at=time.time(),
        )
    except Exception as exc:
        return repository.update_eval_execution(
            execution_id,
            status="failed",
            metrics={
                "completed": False,
                "error": str(exc),
                "deterministic": not variant.get("live_tools", False),
            },
            finished_at=time.time(),
        )
    finally:
        reset_replay_context(tokens)
