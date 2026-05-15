"""Optional runtime event hooks for graph nodes.

Graph nodes are shared by the API runtime and local/CLI tests.  The API installs
an emitter while a run is executing; outside that context these helpers no-op.
"""

from __future__ import annotations

import contextvars
import time
from collections.abc import Callable
from typing import Any


EventEmitter = Callable[[str, dict[str, Any]], None]

_emitter: contextvars.ContextVar[EventEmitter | None] = contextvars.ContextVar(
    "analysis_event_emitter",
    default=None,
)


def set_event_emitter(emitter: EventEmitter | None) -> contextvars.Token:
    return _emitter.set(emitter)


def reset_event_emitter(token: contextvars.Token) -> None:
    _emitter.reset(token)


def emit_event(event: str, data: dict[str, Any]) -> None:
    emitter = _emitter.get()
    if emitter is None:
        return
    emitter(event, data)


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
