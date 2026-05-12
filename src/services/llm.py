"""LLM factory — returns ChatAnthropic configured per agent role."""

import json
import logging
import re
from langchain_anthropic import ChatAnthropic

from src.config import settings

_MODEL_MAP = {
    "planner": settings.planner_model,
    "collector": settings.collector_model,
    "analyst": settings.analyst_model,
    "comparator": settings.comparator_model,
    "writer": settings.writer_model,
}
logger = logging.getLogger(__name__)


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


def get_llm(role: str, **kwargs) -> ChatAnthropic:
    model = _MODEL_MAP.get(role, settings.planner_model)
    base_url = _normalize_base_url(settings.anthropic_base_url)
    logger.info("llm: create role=%s model=%s base_url=%s", role, model, base_url)
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        base_url=base_url,
        max_tokens=4096,
        **kwargs,
    )
