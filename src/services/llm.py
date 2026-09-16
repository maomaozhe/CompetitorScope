"""LLM factory — returns ChatAnthropic configured per agent role."""

import json
import logging
import re
import time
import uuid
import copy
from typing import Any
from langchain_anthropic import ChatAnthropic

from src.config import settings
from src.graph.runtime_events import emit_event
from src.observability.replay import model_for_role, parameters_for_role, prompt_for_role

_MODEL_MAP = {
    "planner": settings.planner_model,
    "collector": settings.collector_model,
    "analyst": settings.analyst_model,
    "comparator": settings.comparator_model,
    "writer": settings.writer_model,
}
logger = logging.getLogger(__name__)


def _message_payload(messages: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": type(message).__name__,
            "content": getattr(message, "content", str(message)),
        }
        for message in messages
    ]


class ObservedChatModel:
    """Thin proxy that records LLM calls without changing LangChain behavior."""

    def __init__(self, inner: Any, *, role: str, model: str):
        self.inner = inner
        self.role = role
        self.model = model

    def _messages_with_override(self, messages: list[Any]) -> list[Any]:
        prompt = prompt_for_role(self.role)
        if not prompt or not messages:
            return messages
        updated = list(messages)
        first = updated[0]
        if hasattr(first, "model_copy"):
            updated[0] = first.model_copy(update={"content": prompt})
        else:
            updated[0] = copy.copy(first)
            updated[0].content = prompt
        return updated

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
        messages = self._messages_with_override(messages)
        started = time.perf_counter()
        call_id = uuid.uuid4().hex
        emit_event("llm.requested", {
            "call_id": call_id,
            "role": self.role,
            "model": self.model,
            "request": _message_payload(messages),
            "parameters": kwargs,
        })
        try:
            response = self.inner.invoke(messages, *args, **kwargs)
        except Exception as exc:
            emit_event("llm.failed", {
                "call_id": call_id,
                "role": self.role,
                "model": self.model,
                "error": str(exc),
                "duration_ms": (time.perf_counter() - started) * 1000,
            })
            raise
        emit_event("llm.completed", {
            "call_id": call_id,
            "role": self.role,
            "model": self.model,
            "response": getattr(response, "content", response),
            "usage": getattr(response, "usage_metadata", None) or {},
            "duration_ms": (time.perf_counter() - started) * 1000,
        })
        return response

    def stream(self, messages: list[Any], *args: Any, **kwargs: Any):
        messages = self._messages_with_override(messages)
        started = time.perf_counter()
        call_id = uuid.uuid4().hex
        emit_event("llm.requested", {
            "call_id": call_id,
            "role": self.role,
            "model": self.model,
            "request": _message_payload(messages),
            "parameters": kwargs,
            "stream": True,
        })
        chunks = []
        try:
            for chunk in self.inner.stream(messages, *args, **kwargs):
                chunks.append(getattr(chunk, "content", chunk))
                yield chunk
        except Exception as exc:
            emit_event("llm.failed", {
                "call_id": call_id,
                "role": self.role,
                "model": self.model,
                "error": str(exc),
                "duration_ms": (time.perf_counter() - started) * 1000,
            })
            raise
        emit_event("llm.completed", {
            "call_id": call_id,
            "role": self.role,
            "model": self.model,
            "response": chunks,
            "usage": {},
            "duration_ms": (time.perf_counter() - started) * 1000,
            "stream": True,
        })

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _normalize_base_url(base_url: str) -> str:
    """Anthropic SDK appends /v1/messages; tolerate env values that include /v1."""
    return base_url.removesuffix("/").removesuffix("/v1") if base_url else base_url


def extract_text(content) -> str:
    """Extract readable text from Anthropic block-list response.

    Priority: text block > thinking block > string fallback.
    Strips markdown code fences before returning.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    return block.get("text", "")
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return block.get("thinking", "")
    return str(content)


def extract_json(content) -> dict:
    """Extract and parse JSON from LLM response.

    Tries text block first (strips ```json fences), falls back to thinking block.
    Returns {} if parsing fails.
    """
    text = extract_text(content)
    # Strip markdown code fences
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        return {}


def get_llm(role: str, **kwargs) -> ObservedChatModel:
    model = model_for_role(role, _MODEL_MAP.get(role, settings.planner_model))
    configured_kwargs = parameters_for_role(role)
    configured_kwargs.update(kwargs)
    base_url = _normalize_base_url(settings.anthropic_base_url)
    logger.info("llm: create role=%s model=%s base_url=%s", role, model, base_url)
    inner = ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        base_url=base_url,
        max_tokens=4096,
        **configured_kwargs,
    )
    return ObservedChatModel(inner, role=role, model=model)
