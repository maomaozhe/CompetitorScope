"""Optional runtime event hooks for graph nodes.

Graph nodes are shared by the API runtime and local/CLI tests.  The API installs
an emitter while a run is executing; outside that context these helpers no-op.
"""

from __future__ import annotations

import contextvars
import time
from collections.abc import Callable
from typing import Any


EventEmitter = Callable[[str, dict[str, Any]], Any]

_emitter: contextvars.ContextVar[EventEmitter | None] = contextvars.ContextVar(
    "analysis_event_emitter",
    default=None,
)
_event_context: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "analysis_event_context",
    default={},
)


def set_event_emitter(emitter: EventEmitter | None) -> contextvars.Token:
    return _emitter.set(emitter)


def reset_event_emitter(token: contextvars.Token) -> None:
    _emitter.reset(token)


def set_event_context(
    *, agent: str, node: str, parent_span_id: str | None = None
) -> contextvars.Token:
    context = {"agent": agent, "node": node}
    if parent_span_id:
        context["parent_span_id"] = parent_span_id
    return _event_context.set(context)


def reset_event_context(token: contextvars.Token) -> None:
    _event_context.reset(token)


def emit_event(event: str, data: dict[str, Any]) -> Any:
    emitter = _emitter.get()
    if emitter is None:
        return None
    context = _event_context.get()
    return emitter(event, {**context, **data})


def emit_agent_output(
    *,
    agent: str,
    node: str,
    title: str,
    summary: str,
    detail: str = "",
    artifact_type: str = "text",
) -> None:
    emit_event(
        "agent_output",
        {
            "id": f"{node}-{time.time_ns()}",
            "agent": agent,
            "node": node,
            "title": title,
            "summary": summary,
            "detail": detail,
            "artifact_type": artifact_type,
            "created_at": time.time(),
        },
    )


def emit_report_chunk(content: str) -> None:
    if content:
        emit_event("report_chunk", {"content": content})
