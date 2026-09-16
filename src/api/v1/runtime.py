"""Shared in-memory runtime for analysis API routes."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graph.runtime_events import reset_event_emitter, set_event_emitter
from src.graph.state import AnalysisState
from src.graph.workflow import build_workflow
from src.config import settings
from src.observability.recorder import TraceRecorder
from src.observability.repository import ObservabilityRepository


CHECKPOINTER = MemorySaver()
WORKFLOW = build_workflow(checkpointer=CHECKPOINTER)
RUN_STORE: dict[str, dict[str, Any]] = {}

# Per-run append-only event history for SSE streaming. Each connection keeps its
# own last seen sequence so multiple clients do not compete for a shared queue.
_EVENT_HISTORY: dict[str, list[dict[str, Any]]] = {}
_EVENT_CONDITIONS: dict[str, asyncio.Condition] = {}
_EVENT_SEQ: dict[str, int] = {}
logger = logging.getLogger(__name__)

_OBSERVABILITY_REPOSITORY = ObservabilityRepository(
    settings.observability_database_path,
    settings.observability_artifact_dir,
)
_TRACE_RECORDER = TraceRecorder(_OBSERVABILITY_REPOSITORY)

_SEMANTIC_EVENT_TYPES = {
    "agent_start": ("agent.status_changed", "running"),
    "agent_complete": ("agent.status_changed", "completed"),
    "agent_output": ("agent.output", "completed"),
    "report_chunk": ("report.chunk_appended", "running"),
    "hitl_request": ("hitl.requested", "waiting"),
    "hitl_resumed": ("hitl.resolved", "completed"),
    "hitl_timeout": ("hitl.timed_out", "completed"),
    "complete": ("run.finished", "completed"),
    "error": ("run.failed", "failed"),
    "cancelled": ("run.cancelled", "cancelled"),
}


def get_observability_repository() -> ObservabilityRepository:
    return _OBSERVABILITY_REPOSITORY


def configure_observability(repository: ObservabilityRepository) -> None:
    """Swap the repository, primarily for isolated tests."""
    global _OBSERVABILITY_REPOSITORY, _TRACE_RECORDER
    _OBSERVABILITY_REPOSITORY = repository
    _TRACE_RECORDER = TraceRecorder(repository)


def _version_fingerprint() -> dict[str, Any]:
    result: dict[str, Any] = {"app_version": "0.1.0", "event_schema": "trace.v1"}
    try:
        result["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=1
        ).strip()
        result["git_dirty"] = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], text=True, timeout=1
        ).strip())
    except Exception:
        result.update({"git_commit": "unknown", "git_dirty": None})
    return result


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
        "writer_streamed": False,
        "operation_spans": {},
        "observability_degraded": False,
    }
    _EVENT_HISTORY[run_id] = []
    _EVENT_CONDITIONS[run_id] = asyncio.Condition()
    _EVENT_SEQ[run_id] = 0
    try:
        _OBSERVABILITY_REPOSITORY.create_run(
            run_id,
            {
                "query": state.get("query", ""),
                "competitors": state.get("confirmed_competitors", []),
                "dimensions": state.get("analysis_dimensions", []),
                "hitl_mode": state.get("hitl_mode", "auto"),
            },
            _version_fingerprint(),
        )
        _TRACE_RECORDER.record_event(
            run_id,
            "run.started",
            {"query": state.get("query", ""), "hitl_mode": state.get("hitl_mode", "auto")},
            status="running",
        )
        _safe_snapshot(run_id, "run.started", dict(state))
    except Exception:
        RUN_STORE[run_id]["observability_degraded"] = True
        logger.exception("observability: trace initialization failed for run %s", run_id)


def _emit_event(run_id: str, event: str, data: dict) -> None:
    """Persist an event and wake all stream readers after commit."""
    if event in {"complete", "error"} and RUN_STORE.get(run_id, {}).get("cancelled"):
        return None
    if event == "_agent_span_started":
        return _safe_start_span(
            run_id,
            name=str(data.get("node") or "agent"),
            kind="agent",
            agent=data.get("agent"),
            node=data.get("node"),
        )
    if event == "_agent_span_finished":
        span_id = data.get("parent_span_id")
        if span_id:
            _safe_finish_span(
                run_id,
                span_id,
                status="failed" if data.get("status") == "failed" else "completed",
                attributes={"error": data.get("error")} if data.get("error") else None,
            )
            RUN_STORE.get(run_id, {}).setdefault("completed_agent_spans", {}).setdefault(
                f"{data.get('agent')}:{data.get('node')}", []
            ).append(span_id)
        return span_id
    semantic_type, status = _SEMANTIC_EVENT_TYPES.get(event, (event, data.get("status")))
    operation_spans = RUN_STORE.get(run_id, {}).setdefault("operation_spans", {})
    call_id = data.get("call_id")
    span_id = operation_spans.get(call_id) if call_id else None
    event_agent = data.get("agent") or data.get("role")
    event_node = data.get("node")
    parent_span_id = data.get("parent_span_id")
    if parent_span_id is None:
        agent_span_key = f"{event_agent}:{event_node}"
        agent_span_stack = RUN_STORE.get(run_id, {}).get("active_agent_spans", {}).get(
            agent_span_key, []
        )
        parent_span_id = agent_span_stack[-1] if agent_span_stack else None
    if event in {"llm.requested", "tool.requested"} and call_id:
        kind = "llm" if event.startswith("llm.") else "tool"
        name = str(data.get("role") or data.get("tool") or kind)
        try:
            span_id = _TRACE_RECORDER.start_span(
                run_id,
                name=name,
                kind=kind,
                parent_span_id=parent_span_id,
                agent=event_agent,
                node=event_node,
                attributes={"call_id": call_id, "model": data.get("model"), "input_hash": data.get("input_hash")},
            )
            operation_spans[call_id] = span_id
        except Exception:
            _mark_observability_degraded(run_id)
            logger.exception("observability: failed to start %s span for run %s", kind, run_id)
    artifact_fields = {}
    if event == "llm.requested":
        artifact_fields = {"request": "llm.request"}
    elif event == "llm.completed":
        artifact_fields = {"response": "llm.response"}
    elif event == "tool.completed":
        artifact_fields = {"result": f"tool.{data.get('tool', 'result')}"}
    try:
        persisted = _TRACE_RECORDER.record_event(
            run_id,
            semantic_type,
            {**data, "_legacy_event": event},
            artifact_fields=artifact_fields,
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent=event_agent,
            node=event_node,
            status=status,
        )
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: failed to persist %s for run %s", semantic_type, run_id)
        return
    _EVENT_SEQ[run_id] = persisted["seq"]
    if event == "report_chunk" and data.get("content"):
        RUN_STORE.get(run_id, {})["writer_streamed"] = True
    try:
        if event == "complete":
            _OBSERVABILITY_REPOSITORY.update_run(
                run_id, status="completed", finished_at=time.time()
            )
        elif event == "error" and not data.get("agent"):
            _OBSERVABILITY_REPOSITORY.update_run(
                run_id,
                status="failed",
                finished_at=time.time(),
                error_message=str(data.get("message") or "Pipeline failed"),
            )
        elif event == "cancelled":
            _OBSERVABILITY_REPOSITORY.update_run(
                run_id, status="cancelled", finished_at=time.time()
            )
        elif event == "hitl_request":
            _OBSERVABILITY_REPOSITORY.update_run(run_id, status="paused")
        elif event in {"hitl_resumed", "hitl_timeout"}:
            _OBSERVABILITY_REPOSITORY.update_run(run_id, status="running")
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: run status update failed for %s", run_id)
    if event in {"llm.completed", "tool.completed", "llm.failed", "tool.failed"} and span_id:
        try:
            _TRACE_RECORDER.finish_span(
                run_id,
                span_id,
                status="failed" if event.endswith("failed") else "completed",
                attributes={"duration_ms": data.get("duration_ms"), "error": data.get("error")},
            )
        except Exception:
            _mark_observability_degraded(run_id)
            logger.exception("observability: failed to finish operation span for run %s", run_id)
        operation_spans.pop(call_id, None)
    if event == "llm.completed":
        usage = data.get("usage") or {}
        token_delta = sum(
            int(usage.get(key) or 0)
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if key != "total_tokens" or not (usage.get("input_tokens") or usage.get("output_tokens"))
        )
        if token_delta:
            try:
                _OBSERVABILITY_REPOSITORY.increment_token_total(run_id, token_delta)
            except Exception:
                _mark_observability_degraded(run_id)
                logger.exception("observability: token aggregation failed for %s", run_id)

    condition = _EVENT_CONDITIONS.get(run_id)
    if condition is None:
        return

    async def _notify() -> None:
        async with condition:
            condition.notify_all()

    try:
        asyncio.get_running_loop().create_task(_notify())
    except RuntimeError:
        pass


def _mark_observability_degraded(run_id: str) -> None:
    if run_id in RUN_STORE:
        RUN_STORE[run_id]["observability_degraded"] = True
    try:
        _OBSERVABILITY_REPOSITORY.update_run(run_id, degraded=1, replayable=0)
    except Exception:
        logger.exception("observability: unable to mark run %s degraded", run_id)


def _safe_snapshot(run_id: str, boundary: str, state: dict[str, Any]) -> None:
    try:
        _TRACE_RECORDER.snapshot(run_id, boundary, state)
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: snapshot %s failed for run %s", boundary, run_id)


def _safe_start_span(run_id: str, **kwargs: Any) -> str | None:
    try:
        return _TRACE_RECORDER.start_span(run_id, **kwargs)
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: span start failed for run %s", run_id)
        return None


def _safe_finish_span(
    run_id: str,
    span_id: str,
    *,
    status: str = "completed",
    attributes: dict[str, Any] | None = None,
) -> None:
    try:
        _TRACE_RECORDER.finish_span(
            run_id, span_id, status=status, attributes=attributes
        )
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: span finish failed for run %s", run_id)


def _safe_record_final_report(run_id: str, report: dict[str, Any]) -> None:
    try:
        _TRACE_RECORDER.record_event(
            run_id,
            "report.finalized",
            {"report": report, "title": report.get("title")},
            artifact_fields={"report": "report.final"},
            agent="writer",
            node="writer",
            status="completed",
        )
    except Exception:
        _mark_observability_degraded(run_id)
        logger.exception("observability: final report artifact failed for run %s", run_id)


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
        "id": f"{node}-{uuid.uuid4().hex}",
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


def _record_node_decision(
    run_id: str,
    node_name: str,
    result: dict[str, Any],
    *,
    span_id: str | None,
    agent: str,
) -> None:
    decision = None
    if node_name == "planner_discover":
        decision = {
            "decision_point": "competitor_selection",
            "candidates": result.get("candidate_competitors") or [],
            "selected": result.get("confirmed_competitors") or [],
            "reason": "Selected competitors produced by discovery and confirmation policy.",
            "strategy_version": "planner-discover.v1",
        }
    elif node_name == "planner_outline":
        decision = {
            "decision_point": "analysis_dimensions",
            "candidates": result.get("analysis_dimensions") or [],
            "selected": result.get("analysis_dimensions") or [],
            "reason": "Dimensions retained by the analysis planning step.",
            "strategy_version": "planner-outline.v1",
        }
    elif node_name == "collect_competitor":
        sources = result.get("raw_sources") or []
        decision = {
            "decision_point": "source_selection",
            "candidates": [item.get("url") for item in sources if isinstance(item, dict)],
            "selected": [item.get("url") for item in sources if isinstance(item, dict)],
            "reason": "Sources that passed search and scraping for this competitor.",
            "strategy_version": "collector.v1",
        }
    elif node_name == "analyze_competitor":
        decision = {
            "decision_point": "evidence_selection",
            "candidates": [],
            "selected": [
                item.get("evidence_id") or item.get("source_url")
                for item in (result.get("evidence_items") or [])
                if isinstance(item, dict)
            ],
            "reason": "Evidence retained in the structured competitor profile.",
            "strategy_version": "analyst.v1",
        }
    elif node_name == "comparator":
        comparison = result.get("comparison_result") or {}
        decision = {
            "decision_point": "comparison_insights",
            "candidates": [],
            "selected": comparison.get("key_insights", []) if isinstance(comparison, dict) else [],
            "reason": "Cross-competitor insights selected by the comparator.",
            "strategy_version": "comparator.v1",
        }
    if decision:
        try:
            _TRACE_RECORDER.record_decision(
                run_id,
                span_id=span_id,
                agent=agent,
                node=node_name,
                confidence=None,
                evidence_refs=[],
                **decision,
            )
        except Exception:
            _mark_observability_degraded(run_id)
            logger.exception("observability: decision recording failed for run %s", run_id)


def get_event_history(run_id: str) -> list[dict[str, Any]]:
    history = []
    for item in _OBSERVABILITY_REPOSITORY.list_events(run_id, limit=100_000):
        payload = dict(item["payload"])
        legacy_event = payload.pop("_legacy_event", None)
        history.append({"seq": item["seq"], "event": legacy_event or item["type"], "data": payload})
    return history


async def wait_for_events_after(
    run_id: str,
    last_seq: int,
    *,
    timeout: float = 0.5,
) -> list[dict[str, Any]]:
    """Wait until this run has events newer than last_seq, then return them."""
    condition = _EVENT_CONDITIONS.get(run_id)
    if condition is None:
        await asyncio.sleep(timeout)
        return [item for item in get_event_history(run_id) if item.get("seq", 0) > last_seq]

    async with condition:
        pending = [item for item in get_event_history(run_id) if item.get("seq", 0) > last_seq]
        if pending:
            return pending
        try:
            await asyncio.wait_for(condition.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return [item for item in get_event_history(run_id) if item.get("seq", 0) > last_seq]


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
    emitter_token = set_event_emitter(lambda event, data: _emit_event(run_id, event, data))
    active_spans: dict[str, str] = {}

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
                task_key = str(payload.get("id") or f"{node_name}:{len(active_spans)}")
                active_spans[task_key] = ""

            elif event_type == "task_result":
                agent_id = NODE_AGENT_MAP.get(node_name, node_name)
                error = payload.get("error")
                task_key = str(payload.get("id") or "")
                active_spans.pop(task_key, None)
                completed_spans = RUN_STORE[run_id].setdefault(
                    "completed_agent_spans", {}
                ).get(f"{agent_id}:{node_name}", [])
                span_id = completed_spans.pop(0) if completed_spans else None
                if error:
                    _emit_event(run_id, "error", {"agent": agent_id, "message": str(error)})
                else:
                    result = payload.get("result", {})
                    if isinstance(result, dict):
                        _record_node_decision(
                            run_id, node_name, result, span_id=span_id, agent=agent_id
                        )
                    # Emit agent_output for ALL nodes (including those about to interrupt)
                    # before checking interrupts, so the UI always sees the output summary.
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

                    interrupts = payload.get("interrupts") or []
                    if interrupts:
                        interrupt_obj = interrupts[0]
                        value = interrupt_obj.get("value", {}) if isinstance(interrupt_obj, dict) else {}
                        if isinstance(value, dict):
                            value["interrupt_id"] = interrupt_obj.get("id", "")
                        else:
                            value = {"interrupt_id": interrupt_obj.get("id", "")}
                        created_at = time.time()
                        RUN_STORE[run_id]["pending_interrupt"] = {
                            "payload": value if isinstance(value, dict) else {},
                            "created_at": created_at,
                        }
                        state = await _snapshot_state(run_id)
                        state["current_stage"] = state.get("current_stage", "planning")
                        state["stage_status"] = "Waiting for human input"
                        RUN_STORE[run_id]["state"] = state
                        _safe_snapshot(run_id, "hitl.requested", state)
                        _emit_event(run_id, "hitl_request", {
                            **value,
                            "created_at": created_at,
                        })
                        asyncio.create_task(
                            _auto_resume_after_timeout(run_id, value if isinstance(value, dict) else {})
                        )
                        close_stream = False
                        return

                    # Only reached for non-interrupting nodes
                    # Forward report_chunk if writer finished
                    if node_name == "writer" and isinstance(result, dict):
                        report = result.get("report")
                        if report and isinstance(report, dict):
                            _safe_record_final_report(run_id, report)
                        if (
                            report
                            and isinstance(report, dict)
                            and "content_markdown" in report
                            and not RUN_STORE[run_id].get("writer_streamed")
                        ):
                            _emit_event(run_id, "report_chunk", {"content": report["content_markdown"]})

                    state = await _snapshot_state(run_id)
                    _safe_snapshot(run_id, f"node.completed:{node_name}", state)

            elif event_type == "__interrupt__":
                interrupt_obj = event.get("__interrupt__", [{}])[0]
                if isinstance(interrupt_obj, dict):
                    value = interrupt_obj.get("value", {})
                    if isinstance(value, dict):
                        value["interrupt_id"] = interrupt_obj.get("id", "")
                    else:
                        value = {"interrupt_id": interrupt_obj.get("id", "")}
                    created_at = time.time()
                    RUN_STORE[run_id]["pending_interrupt"] = {
                        "payload": value if isinstance(value, dict) else {},
                        "created_at": created_at,
                    }
                    state = await _snapshot_state(run_id)
                    state["current_stage"] = state.get("current_stage", "planning")
                    state["stage_status"] = "Waiting for human input"
                    RUN_STORE[run_id]["state"] = state
                    _safe_snapshot(run_id, "hitl.requested", state)
                    _emit_event(run_id, "hitl_request", {
                        **value,
                        "created_at": created_at,
                    })
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
        _safe_snapshot(run_id, "run.completed", RUN_STORE[run_id]["state"])
        if RUN_STORE[run_id].get("cancelled"):
            return
        _emit_event(run_id, "complete", {"done": True})

    except Exception as exc:
        state = RUN_STORE[run_id]["state"]
        state["current_stage"] = "error"
        state["error_message"] = str(exc)
        state["stage_status"] = "Pipeline failed"
        RUN_STORE[run_id]["state"] = state
        RUN_STORE[run_id]["done"] = True
        RUN_STORE[run_id]["pending_interrupt"] = None
        _safe_snapshot(run_id, "run.failed", state)
        _emit_event(run_id, "error", {"message": str(exc)})
    finally:
        reset_event_emitter(emitter_token)
        if close_stream:
            condition = _EVENT_CONDITIONS.get(run_id)
            if condition is not None:
                async with condition:
                    condition.notify_all()


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


async def resume_run(run_id: str, response: dict, *, runner=None) -> None:
    run = RUN_STORE[run_id]
    pending = run.get("pending_interrupt")
    run["pending_interrupt"] = None
    _emit_event(run_id, "hitl_resumed", {
        "response": response,
        "interrupt": pending["payload"] if pending else None,
    })
    _safe_snapshot(run_id, "hitl.resolved", dict(run["state"]))
    await (runner or run_until_pause)(run_id, Command(resume=response))


def cancel_run(run_id: str) -> None:
    run = RUN_STORE[run_id]
    run["done"] = True
    run["cancelled"] = True
    run["pending_interrupt"] = None
    state = dict(run["state"])
    state["stage_status"] = "Cancelled"
    run["state"] = state
    _safe_snapshot(run_id, "run.cancelled", state)
    _emit_event(run_id, "cancelled", {"done": True})
