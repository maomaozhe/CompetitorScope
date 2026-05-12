"""Run the pipeline end-to-end from CLI."""

import sys, os, time, json, uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph.workflow import build_workflow
from src.graph.state import AnalysisState


def timestamp():
    return time.strftime("%H:%M:%S")


def run(query: str):
    run_id = uuid.uuid4().hex[:8]
    output_dir = Path("output") / f"run-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    log_lines = []
    log = lambda msg: (log_lines.append(f"[{timestamp()}] {msg}"), print(f"[{timestamp()}] {msg}"))

    log(f"=== CompetitorScope Run {run_id} ===")
    log(f"Query: {query}")

    workflow = build_workflow()
    state: AnalysisState = {
        "run_id": run_id,
        "query": query,
        "confirmed_competitors": [],
        "analysis_dimensions": ["positioning", "features", "pricing", "reviews"],
        "report_outline": "",
        "current_stage": "planning",
        "stage_status": "Starting...",
        "error_message": None,
        "raw_sources": [],
        "competitor_profiles": [],
        "evidence_items": [],
        "comparison_result": None,
        "report": None,
    }

    log("Pipeline starting...")
    start = time.time()
    result = workflow.invoke(state)
    elapsed = time.time() - start
    log(f"Pipeline done in {elapsed:.1f}s. stage={result.get('current_stage')}")

    report = result.get("report")
    if report:
        # Save report markdown
        report_path = output_dir / "report.md"
        report_path.write_text(report.content_markdown, encoding="utf-8")
        log(f"Report saved: {report_path}")

        # Save structured data
        data = {
            "run_id": run_id,
            "query": query,
            "elapsed_seconds": round(elapsed, 1),
            "competitors_found": len(result.get("confirmed_competitors", [])),
            "profiles_count": len(result.get("competitor_profiles", [])),
            "raw_sources_count": len(result.get("raw_sources", [])),
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
                for p in result.get("competitor_profiles", [])
            ],
            "raw_sources": [
                {"competitor": s.competitor_id, "url": s.url, "type": s.source_type, "title": s.title}
                for s in result.get("raw_sources", [])
            ],
            "bibliography": report.bibliography,
        }
        data_path = output_dir / "data.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Data saved: {data_path}")

        print()
        print("=" * 60)
        print(report.content_markdown)
        print("=" * 60)
        print()
        print(f"✅ 报告: {report_path}")
        print(f"✅ 数据: {data_path}")
    else:
        log(f"ERROR: {result.get('error_message', 'unknown')}")

    # Save log
    log_path = output_dir / "log.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    log(f"Log saved: {log_path}")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "AI Coding IDE 赛道的主要竞品"
    run(query)