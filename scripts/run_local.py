"""Run the pipeline end-to-end from CLI."""

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graph.workflow import build_workflow
from src.graph.state import AnalysisState
from src.graph.serialization import (
    competitor_profiles,
    raw_sources,
    report as restore_report,
)


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")


def timestamp():
    return time.strftime("%H:%M:%S")


def _initial_state(run_id: str, query: str, hitl_mode: str) -> AnalysisState:
    return {
        "run_id": run_id,
        "query": query,
        "hitl_mode": hitl_mode,
        "candidate_competitors": [],
        "confirmed_competitors": [],
        "analysis_dimensions": ["positioning", "features", "pricing", "reviews"],
        "report_outline": "",
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


def _parse_competitor_selection(raw: str, candidates: list[dict]) -> list[dict]:
    """Parse CLI competitor selection.

    Supported forms:
    - "1,3,5"
    - "1-3"
    - "+New Product|https://example.com"
    """
    selected = []
    seen_names = set()
    for part in [item.strip() for item in raw.split(",") if item.strip()]:
        if part.startswith("+"):
            name_url = part[1:].strip()
            name, _, website = name_url.partition("|")
            name = name.strip()
            if name and name.lower() not in seen_names:
                selected.append({"name": name, "website": website.strip()})
                seen_names.add(name.lower())
            continue

        if "-" in part:
            start_text, _, end_text = part.partition("-")
            try:
                start = int(start_text.strip())
                end = int(end_text.strip())
            except ValueError:
                continue
            indexes = range(min(start, end), max(start, end) + 1)
        else:
            try:
                indexes = [int(part)]
            except ValueError:
                continue

        for idx in indexes:
            if 1 <= idx <= len(candidates):
                competitor = candidates[idx - 1]
                name = str(competitor.get("name", "")).lower()
                if name and name not in seen_names:
                    selected.append(competitor)
                    seen_names.add(name)
    return selected


def _prompt_competitor_confirm(payload: dict) -> dict:
    candidates = payload.get("candidates", [])
    print("\n需要确认竞品清单：")
    for idx, competitor in enumerate(candidates, start=1):
        print(f"{idx}. {competitor.get('name')} {competitor.get('website', '')}")
    raw = input(
        "选择竞品序号（支持 1,3,5 或 1-3）；"
        "新增用 +名称|网址；直接回车使用默认前 5 家："
    ).strip()
    if not raw:
        return payload.get("default_response", {})
    selected = _parse_competitor_selection(raw, candidates)
    return {"competitors": selected or payload.get("default_response", {}).get("competitors", [])}


def _looks_like_competitor_selection(raw: str) -> bool:
    return bool(
        re.search(
            r"(前\s*\d+\s*家|只要|只需要|改.*竞品|选.*竞品|选择.*竞品|competitors?)",
            raw,
            re.IGNORECASE,
        )
    )


def _prompt_outline_confirm(payload: dict) -> dict:
    print("\n报告大纲：")
    print(payload.get("outline", ""))
    while True:
        raw = input(
            "直接回车确认大纲；输入 Markdown 大纲覆盖。"
            "这里不能再改竞品清单，竞品数量请在上一阶段选择："
        ).strip()
        if not raw:
            return payload.get("default_response", {})
        if _looks_like_competitor_selection(raw):
            print("这看起来是在改竞品清单；当前阶段只确认报告大纲。请直接回车确认，或输入 Markdown 大纲。")
            continue
        return {"outline": raw, "dimensions": payload.get("dimensions", [])}


def _prompt_collector_supplement(payload: dict) -> dict:
    print("\n以下竞品来源不足：")
    for item in payload.get("low_source_competitors", []):
        print(f"- {item['name']} ({item['competitor_id']}): {item['source_count']} 条")
    action = input("操作 [continue/supplement/skip]，默认 continue：").strip() or "continue"
    if action == "skip":
        skipped = [item["competitor_id"] for item in payload.get("low_source_competitors", [])]
        return {"action": "skip", "skip_competitors": skipped}
    if action != "supplement":
        return {"action": "continue"}
    supplement_urls = {}
    for item in payload.get("low_source_competitors", []):
        raw = input(f"为 {item['name']} 补充 URL，逗号分隔；可留空：").strip()
        if raw:
            supplement_urls[item["competitor_id"]] = [url.strip() for url in raw.split(",") if url.strip()]
    return {"action": "supplement", "supplement_urls": supplement_urls}


def _resume_payload(payload: dict) -> dict:
    kind = payload.get("type")
    if kind == "competitor_confirm":
        return _prompt_competitor_confirm(payload)
    if kind == "outline_confirm":
        return _prompt_outline_confirm(payload)
    if kind == "collector_supplement":
        return _prompt_collector_supplement(payload)
    return payload.get("default_response", {})


def _summarize_event(event: dict) -> str:
    if "__interrupt__" in event:
        payload = event["__interrupt__"][0].value
        return f"interrupt type={payload.get('type')}"
    node, payload = next(iter(event.items()))
    if payload is None:
        return f"{node}: no state update"
    parts = []
    for key, value in payload.items():
        if isinstance(value, list):
            parts.append(f"{key}[{len(value)}]")
        elif isinstance(value, dict):
            parts.append(f"{key}{{{len(value)}}}")
        elif isinstance(value, str) and len(value) > 120:
            parts.append(f"{key}={value[:117]}...")
        else:
            parts.append(f"{key}={value}")
    return f"{node}: " + ", ".join(parts)


def _invoke_with_hitl(workflow, state: AnalysisState, run_id: str, log) -> dict:
    config = {"configurable": {"thread_id": run_id}}
    graph_input = state
    while True:
        interrupted = None
        for event in workflow.stream(graph_input, config=config):
            log(f"Graph event: {_summarize_event(event)}")
            if "__interrupt__" in event:
                interrupted = event["__interrupt__"][0].value
                break
        if not interrupted:
            return dict(workflow.get_state(config).values)
        response = _resume_payload(dict(interrupted))
        graph_input = Command(resume=response)


def _follow_up_once(report_markdown: str) -> str:
    question = input("\n可选追问（直接回车跳过）：").strip()
    if not question:
        return report_markdown
    return f"{report_markdown.rstrip()}\n\n## 补充追问: {question}\n\nCLI 已记录追问；API 模式会执行补充采集与生成。\n"


def run(query: str, hitl_mode: str):
    run_id = uuid.uuid4().hex[:8]
    output_dir = Path("output") / f"run-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    log_lines = []

    def log(msg: str) -> None:
        line = f"[{timestamp()}] {msg}"
        log_lines.append(line)
        print(line, flush=True)

    log(f"=== CompetitorScope Run {run_id} ===")
    log(f"Query: {query}")

    workflow = build_workflow(checkpointer=MemorySaver())
    state = _initial_state(run_id, query, hitl_mode)

    log("Pipeline starting...")
    overall_start = time.time()
    result = _invoke_with_hitl(workflow, state, run_id, log)
    elapsed = time.time() - overall_start

    log(f"Pipeline done in {elapsed:.1f}s. stage={result.get('current_stage')}")

    report = restore_report(result.get("report"))
    if report:
        report_path = output_dir / "report.md"
        if hitl_mode == "interactive":
            report.content_markdown = _follow_up_once(report.content_markdown)
        report_path.write_text(report.content_markdown, encoding="utf-8")
        log(f"Report saved: {report_path}")

        profiles = competitor_profiles(result.get("competitor_profiles", []))
        sources = raw_sources(result.get("raw_sources", []))
        data = {
            "run_id": run_id,
            "query": query,
            "elapsed_seconds": round(elapsed, 1),
            "competitors_found": len(result.get("confirmed_competitors", [])),
            "profiles_count": len(profiles),
            "raw_sources_count": len(sources),
            "report_chars": len(report.content_markdown),
            "bibliography_count": len(report.bibliography),
            "competitor_profiles": [
                {
                    "name": p.name,
                    "website": p.website,
                    "one_liner": p.one_liner,
                    "tech_form": p.tech_form,
                    "pricing_tiers": [
                        {"tier": t.tier_name, "price": t.price, "features": t.key_features}
                        for t in p.pricing_tiers
                    ],
                    "positive_themes": p.positive_themes[:3],
                    "negative_themes": p.negative_themes[:3],
                }
                for p in profiles
            ],
            "raw_sources": [
                {"competitor": s.competitor_id, "url": s.url, "type": s.source_type, "title": s.title}
                for s in sources
            ],
            "bibliography": report.bibliography,
        }
        data_path = output_dir / "data.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Data saved: {data_path}")

        print()
        print(f"✅ Competitors: {len(result.get('confirmed_competitors', []))}")
        print(f"✅ Profiles: {len(result.get('competitor_profiles', []))}")
        print(f"✅ Sources: {len(result.get('raw_sources', []))}")
    else:
        log(f"ERROR: {result.get('error_message', 'unknown')}")

    log_path = output_dir / "log.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    log(f"Log saved: {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="AI Coding IDE 赛道的主要竞品")
    parser.add_argument("--hitl", choices=["auto", "interactive"], default="auto")
    args = parser.parse_args()
    run(args.query, args.hitl)
