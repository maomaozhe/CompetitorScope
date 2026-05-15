"""Writer node — generates the final Markdown report."""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.graph.runtime_events import emit_agent_output, emit_report_chunk
from src.graph.state import AnalysisState
from src.graph.serialization import (
    comparison_result,
    competitor_profiles,
    dump_model,
    evidence_items,
)
from src.prompts.writer import WRITER_SYSTEM
from src.services.llm import get_llm, extract_text
from src.schemas.domain import Report


logger = logging.getLogger(__name__)


def _as_text(value: Any) -> str:
    """Render arbitrary structured values as readable prompt text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return "\n".join(f"- {item}" for item in value)
        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _list_text(values: Any) -> str:
    if not values:
        return ""
    if not isinstance(values, list):
        return _as_text(values)
    return "\n".join(f"- {_as_text(item)}" for item in values)


def _comparison_field(raw_comparison: Any, field: str) -> Any:
    if isinstance(raw_comparison, BaseModel):
        return getattr(raw_comparison, field, "")
    if isinstance(raw_comparison, dict):
        return raw_comparison.get(field, "")
    return ""


def _restore_comparison(raw_comparison: Any):
    try:
        return comparison_result(raw_comparison)
    except Exception:
        logger.warning("writer: comparison_result contained non-schema values; using raw formatting")
        return None


def _content_text(message: Any) -> str:
    return extract_text(getattr(message, "content", message))


def _generate_report_markdown(llm: Any, messages: list[Any]) -> str:
    stream = getattr(llm, "stream", None)
    if callable(stream):
        chunks: list[str] = []
        try:
            for chunk in stream(messages):
                text = _content_text(chunk)
                if not text:
                    continue
                chunks.append(text)
                emit_report_chunk(text)
            if chunks:
                return "".join(chunks)
        except Exception as exc:
            logger.info("writer: streaming unavailable, falling back to invoke: %s", exc)

    resp = llm.invoke(messages)
    markdown = _content_text(resp)
    emit_report_chunk(markdown)
    return markdown


def writer_node(state: AnalysisState) -> dict:
    profiles = competitor_profiles(state.get("competitor_profiles", []))
    raw_comparison = state.get("comparison_result")
    comparison = _restore_comparison(raw_comparison)
    evidence = evidence_items(state.get("evidence_items", []))
    outline = state.get("report_outline", "")
    logger.info("writer: start profiles=%d evidence=%d", len(profiles), len(evidence))

    # Build competitor summaries
    lines = []
    for p in profiles:
        pricing_str = "\n".join(
            f"  - {t.tier_name}: {t.price} | {_list_text(t.key_features).replace(chr(10), '; ')}"
            for t in p.pricing_tiers
        )
        lines.append(f"### {p.name}")
        lines.append(f"**定位**: {_as_text(p.one_liner)}")
        lines.append(f"**目标用户**: {_list_text(p.target_audience).replace(chr(10), '; ')}")
        lines.append(f"**技术形态**: {_as_text(p.tech_form)}")
        lines.append(f"**定价**:\n{pricing_str}")
        lines.append(f"**好评**: {_list_text(p.positive_themes[:3]).replace(chr(10), '; ')}")
        lines.append(f"**吐槽**: {_list_text(p.negative_themes[:3]).replace(chr(10), '; ')}")
        lines.append("")

    profiles_text = "\n".join(lines)

    # Build evidence for bibliography
    seen_urls = {}
    bibliography = []
    for e in evidence:
        if e.source_url and e.source_url not in seen_urls:
            seen_urls[e.source_url] = len(seen_urls) + 1
            bibliography.append({"url": e.source_url, "title": e.source_url})

    llm = get_llm("writer")
    logger.info("writer: invoking LLM")
    emit_agent_output(
        agent="writer",
        node="writer",
        title="准备生成报告",
        summary=f"正在整合 {len(profiles)} 个竞品 profile 和 {len(evidence)} 条证据",
        artifact_type="report",
    )
    feature_table = (
        comparison.feature_table
        if comparison
        else _comparison_field(raw_comparison, "feature_table")
    )
    pricing_table = (
        comparison.pricing_table
        if comparison
        else _comparison_field(raw_comparison, "pricing_table")
    )
    key_insights = (
        comparison.key_insights
        if comparison
        else _comparison_field(raw_comparison, "key_insights")
    )
    recommendations = (
        comparison.recommendations
        if comparison
        else _comparison_field(raw_comparison, "recommendations")
    )
    messages = [
        SystemMessage(content=WRITER_SYSTEM),
        HumanMessage(content=f"""Report outline:
{outline}

Competitor profiles:
{profiles_text}

Feature comparison:
{_as_text(feature_table) or 'N/A'}

Pricing comparison:
{_as_text(pricing_table) or 'N/A'}

Key insights:
{_list_text(key_insights) or 'N/A'}

Recommendations:
{_list_text(recommendations) or 'N/A'}
"""),
    ]

    emit_agent_output(
        agent="writer",
        node="writer",
        title="开始撰写 Markdown 报告",
        summary="报告内容将按 chunk 渐进输出",
        artifact_type="report",
    )
    content_markdown = _generate_report_markdown(llm, messages)

    report = Report(
        title=f"竞品分析报告: {state['query']}",
        executive_summary="见下方报告全文",
        content_markdown=content_markdown,
        bibliography=bibliography,
    )
    logger.info("writer: done report_chars=%d bibliography=%d", len(report.content_markdown), len(bibliography))

    return {
        "report": dump_model(report),
        "current_stage": "complete",
        "stage_status": "Report generated",
    }
