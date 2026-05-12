"""Writer node — generates the final Markdown report."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

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


def writer_node(state: AnalysisState) -> dict:
    profiles = competitor_profiles(state.get("competitor_profiles", []))
    comparison = comparison_result(state.get("comparison_result"))
    evidence = evidence_items(state.get("evidence_items", []))
    outline = state.get("report_outline", "")
    logger.info("writer: start profiles=%d evidence=%d", len(profiles), len(evidence))

    # Build competitor summaries
    lines = []
    for p in profiles:
        pricing_str = "\n".join(
            f"  - {t.tier_name}: {t.price} | {', '.join(t.key_features)}"
            for t in p.pricing_tiers
        )
        lines.append(f"### {p.name}")
        lines.append(f"**定位**: {p.one_liner}")
        lines.append(f"**目标用户**: {', '.join(p.target_audience)}")
        lines.append(f"**技术形态**: {p.tech_form}")
        lines.append(f"**定价**:\n{pricing_str}")
        lines.append(f"**好评**: {', '.join(p.positive_themes[:3])}")
        lines.append(f"**吐槽**: {', '.join(p.negative_themes[:3])}")
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
    resp = llm.invoke([
        SystemMessage(content=WRITER_SYSTEM),
        HumanMessage(content=f"""Report outline:
{outline}

Competitor profiles:
{profiles_text}

Feature comparison:
{comparison.feature_table if comparison else 'N/A'}

Pricing comparison:
{comparison.pricing_table if comparison else 'N/A'}

Key insights:
{chr(10).join(f"- {i}" for i in (comparison.key_insights if comparison else []))}

Recommendations:
{chr(10).join(f"- {r}" for r in (comparison.recommendations if comparison else []))}
"""),
    ])

    report = Report(
        title=f"竞品分析报告: {state['query']}",
        executive_summary="见下方报告全文",
        content_markdown=extract_text(resp.content),
        bibliography=bibliography,
    )
    logger.info("writer: done report_chars=%d bibliography=%d", len(report.content_markdown), len(bibliography))

    return {
        "report": dump_model(report),
        "current_stage": "complete",
        "stage_status": "Report generated",
    }
