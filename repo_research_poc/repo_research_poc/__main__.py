"""Command-line entry point for one fixed-snapshot source question."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

from .runner import run_research


def main(argv: list[str] | None = None, *, runner: Callable = run_research) -> int:
    parser = argparse.ArgumentParser(description="Ask a question about an explicit local repo snapshot")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--commit", required=True, help="40-character Git commit SHA")
    parser.add_argument("--question", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path.home() / ".competitorscope" / "repo-research-runs")
    parser.add_argument("--model", default=os.getenv("REPO_RESEARCH_MODEL", "claude-sonnet-4-6"))
    parser.add_argument("--base-url", default=os.getenv("ANTHROPIC_BASE_URL"))
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--recursion-limit", type=int, default=100,
                        help="LangGraph step budget; raise for broad questions on large snapshots")
    parser.add_argument("--langsmith-project", help="Opt in to uploading traces, including source excerpts")
    parser.add_argument("--allow-source-upload", action="store_true")
    args = parser.parse_args(argv)
    config = {
        "provider": "anthropic",
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    if args.base_url:
        config["base_url"] = args.base_url
    try:
        result = runner(
            args.snapshot, args.commit, args.question, args.output_dir, config,
            langsmith_project=args.langsmith_project,
            allow_source_upload=args.allow_source_upload,
            recursion_limit=args.recursion_limit,
        )
    except ValueError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 2
    print(f"Status: {result['status']}")
    if result.get("answer"):
        print(f"Answer: {result['answer']}")
    for citation in result.get("citations", []):
        print(f"  {citation['path']}:{citation['start_line']}-{citation['end_line']} — {citation['quote']}")
    for question in result.get("unresolved_questions", []):
        print(f"Unresolved: {question}")
    for issue in result.get("citation_issues", []):
        print(f"Citation issue: {issue['code']} ({issue['detail']})")
    for error in result.get("errors", []):
        print(f"Error: {error['type']}: {error['message']}", file=sys.stderr)
    print(f"Run record: {result['result_path']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
