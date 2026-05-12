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
        "finished_collectors": set(),
        "finished_analysts": set(),
        "comparison_result": None,
        "report": None,
    }

    # Phase timing
    phase_times = {}
    overall_start = time.time()

    # Use stream to track node-level timing
    stream = workflow.stream(state, stream_output=["all"])
    pending = {}  # node_name -> start_time

    for item in stream:
        if not isinstance(item, dict):
            continue
        for node_name, node_output in item.items():
            if node_output is None:
                pending[node_name] = time.time()
                log(f"  ▶ START  {node_name}")
            else:
                elapsed = time.time() - pending.pop(node_name, time.time())
                phase_times[node_name] = elapsed
                log(f"  ✔ END   {node_name}  ({elapsed:.1f}s)")

    elapsed = time.time() - overall_start
    final_state = workflow.invoke(state)

    log(f"\nPipeline done in {elapsed:.1f}s. stage={final_state.get('current_stage')}")

    # Print per-node timing
    if phase_times:
        log("\n--- Node Timing (seconds) ---")
        for node, sec in sorted(phase_times.items(), key=lambda x: x[1], reverse=True):
            log(f"  {sec:7.1f}s  {node}")
        log(f"  {'------':>7}  ----------")
        log(f"  {elapsed:7.1f}s  TOTAL (wall clock)")

    report = final_state.get("report")
    if report:
        report_path = output_dir / "report.md"
        report_path.write_text(report.content_markdown, encoding="utf-8")
        log(f"Report saved: {report_path}")

        data = {
            "run_id": run_id,
            "query": query,
            "elapsed_seconds": round(elapsed, 1),
            "node_timings": {k: round(v, 1) for k, v in phase_times.items()},
            "competitors_found": len(final_state.get("confirmed_competitors", [])),
            "profiles_count": len(final_state.get("competitor_profiles", [])),
            "raw_sources_count": len(final_state.get("raw_sources", [])),
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
                for p in final_state.get("competitor_profiles", [])
            ],
            "raw_sources": [
                {"competitor": s.competitor_id, "url": s.url, "type": s.source_type, "title": s.title}
                for s in final_state.get("raw_sources", [])
            ],
            "bibliography": report.bibliography,
        }
        data_path = output_dir / "data.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Data saved: {data_path}")

        print()
        print(f"✅ Competitors: {len(final_state.get('confirmed_competitors', []))}")
        print(f"✅ Profiles: {len(final_state.get('competitor_profiles', []))}")
        print(f"✅ Sources: {len(final_state.get('raw_sources', []))}")
    else:
        log(f"ERROR: {final_state.get('error_message', 'unknown')}")

    log_path = output_dir / "log.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    log(f"Log saved: {log_path}")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "AI Coding IDE 赛道的主要竞品"
    run(query)
