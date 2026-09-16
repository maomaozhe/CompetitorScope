"""Tavily search wrapper with retry."""

import hashlib
import json
import time
import uuid

from tavily import TavilyClient
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.graph.runtime_events import emit_event
from src.observability.replay import FrozenToolResultMissing, replayed_tool_result

_client: TavilyClient | None = None


def tool_input_hash(arguments: dict) -> str:
    return hashlib.sha256(json.dumps(arguments, sort_keys=True).encode("utf-8")).hexdigest()


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_not_exception_type(FrozenToolResultMissing),
    reraise=True,
)
def search(query: str, max_results: int = 5) -> list[dict]:
    """Search via Tavily. Returns list of {title, url, content, score}."""
    arguments = {"query": query, "max_results": max_results}
    input_hash = tool_input_hash(arguments)
    started = time.perf_counter()
    call_id = uuid.uuid4().hex
    emit_event("tool.requested", {"call_id": call_id, "tool": "web_search", "arguments": arguments, "input_hash": input_hash})
    replayed, frozen_result = replayed_tool_result("web_search", input_hash)
    if replayed:
        emit_event("tool.completed", {
            "call_id": call_id, "tool": "web_search", "input_hash": input_hash,
            "result": frozen_result, "result_count": len(frozen_result), "duration_ms": 0,
            "replayed": True,
        })
        return frozen_result
    try:
        client = _get_client()
        response = client.search(query, max_results=max_results)
        results = response.get("results", [])
    except Exception as exc:
        emit_event("tool.failed", {
            "call_id": call_id, "tool": "web_search", "input_hash": input_hash, "error": str(exc),
            "duration_ms": (time.perf_counter() - started) * 1000,
        })
        raise
    emit_event("tool.completed", {
        "call_id": call_id, "tool": "web_search", "input_hash": input_hash, "result": results,
        "result_count": len(results), "duration_ms": (time.perf_counter() - started) * 1000,
    })
    return results
