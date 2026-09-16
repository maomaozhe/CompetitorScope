"""Web scraper — httpx + readability for clean text extraction."""

import hashlib
import json
import re
import time
import uuid

import httpx
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from src.graph.runtime_events import emit_event
from src.observability.replay import FrozenToolResultMissing, replayed_tool_result

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 15.0
_MAX_CONTENT_LEN = 8000


def tool_input_hash(arguments: dict) -> str:
    return hashlib.sha256(json.dumps(arguments, sort_keys=True).encode("utf-8")).hexdigest()


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=5),
    retry=retry_if_not_exception_type(FrozenToolResultMissing),
    reraise=True,
)
def scrape(url: str) -> dict:
    """Fetch URL and extract clean text. Returns {url, title, content}."""
    arguments = {"url": url}
    input_hash = tool_input_hash(arguments)
    started = time.perf_counter()
    call_id = uuid.uuid4().hex
    emit_event("tool.requested", {"call_id": call_id, "tool": "web_scrape", "arguments": arguments, "input_hash": input_hash})
    replayed, frozen_result = replayed_tool_result("web_scrape", input_hash)
    if replayed:
        emit_event("tool.completed", {
            "call_id": call_id, "tool": "web_scrape", "input_hash": input_hash,
            "result": frozen_result, "duration_ms": 0, "replayed": True,
        })
        return frozen_result
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()

        from readability import Document

        doc = Document(resp.text)
        title = doc.title() or ""
        content = re.sub(r"<[^>]+>", " ", doc.summary())
        content = re.sub(r"\s+", " ", content).strip()

        if len(content) > _MAX_CONTENT_LEN:
            content = content[:_MAX_CONTENT_LEN] + "..."
        result = {"url": url, "title": title, "content": content}
    except Exception as exc:
        emit_event("tool.failed", {
            "call_id": call_id, "tool": "web_scrape", "input_hash": input_hash, "error": str(exc),
            "duration_ms": (time.perf_counter() - started) * 1000,
        })
        raise

    emit_event("tool.completed", {
        "call_id": call_id, "tool": "web_scrape", "input_hash": input_hash, "result": result,
        "duration_ms": (time.perf_counter() - started) * 1000,
    })
    return result
