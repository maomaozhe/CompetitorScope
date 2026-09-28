"""Offline case structure and explicitly opted-in LangSmith experiments."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Literal

from langsmith import Client, evaluate
from pydantic import BaseModel

from .citations import EXCLUDED_PARTS
from .runner import run_research


class ResearchCase(BaseModel):
    id: str
    question: str
    review_status: Literal["pending", "verified"] = "pending"
    reference_answer: str | None = None


def load_cases(path: Path) -> list[ResearchCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = [ResearchCase.model_validate(item) for item in payload["cases"]]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("duplicate case ID")
    if any(case.review_status == "pending" and case.reference_answer is not None for case in cases):
        raise ValueError("pending cases cannot contain unreviewed reference answers")
    return cases


def run_local_suite(
    snapshot: Path,
    commit_sha: str,
    cases_path: Path,
    output_dir: Path,
    model_config: dict[str, Any],
    *,
    runner: Callable = run_research,
) -> dict[str, Any]:
    try:
        relative_cases = cases_path.resolve().relative_to(snapshot.resolve())
    except ValueError:
        relative_cases = None
    if relative_cases is not None and not any(part in EXCLUDED_PARTS for part in relative_cases.parts[:-1]):
        raise ValueError("evaluation metadata must be outside the Agent-readable snapshot")
    cases = load_cases(cases_path)
    rows = []
    for case in cases:
        result = runner(snapshot, commit_sha, case.question, output_dir, model_config)
        rows.append({
            "case_id": case.id,
            "review_status": case.review_status,
            "run_id": result.get("run_id"),
            "status": result["status"],
            "citation_integrity": result["status"] == "ok",
            "business_answer_score": None,
            "result_path": result["result_path"],
        })
    suite = {"schema_version": "repo-research-eval.v1", "commit_sha": commit_sha, "cases": rows}
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"suite-{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")
    suite["result_path"] = str(path.resolve())
    return suite


def record_langsmith_experiment(
    cases: list[ResearchCase],
    snapshot: Path,
    commit_sha: str,
    output_dir: Path,
    model_config: dict[str, Any],
    *,
    dataset_name: str,
    experiment_prefix: str,
    allow_source_upload: bool,
    client: Client | None = None,
    runner: Callable = run_research,
):
    if not allow_source_upload:
        raise ValueError("LangSmith experiment requires explicit source upload opt-in")
    if not cases:
        raise ValueError("experiment needs at least one case")
    client = client or Client()
    client.create_dataset(dataset_name, description="Repo research POC; answer keys require human review")
    client.create_examples(dataset_name=dataset_name, examples=[
        {
            "inputs": {"question": case.question},
            "outputs": {"reference_answer": case.reference_answer} if case.review_status == "verified" else {},
            "metadata": {"case_id": case.id, "review_status": case.review_status},
        }
        for case in cases
    ])

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        result = runner(snapshot, commit_sha, inputs["question"], output_dir, model_config)
        return {
            "answer": result["answer"],
            "status": result["status"],
            "citations": result["citations"],
            "citation_issues": result["citation_issues"],
        }

    def citation_integrity(run, example) -> dict[str, Any]:
        return {"key": "citation_integrity", "score": run.outputs.get("status") == "ok"}

    return evaluate(
        target,
        data=dataset_name,
        evaluators=[citation_integrity],
        experiment_prefix=experiment_prefix,
        metadata={"component": "repo_research_poc", "commit_sha": commit_sha, "model": model_config},
        max_concurrency=0,
        upload_results=True,
        client=client,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a small repository research case set")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] / "evals" / "cases.json")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / ".competitorscope" / "repo-research-runs")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--base-url", default=os.getenv("ANTHROPIC_BASE_URL"))
    parser.add_argument("--langsmith-dataset")
    parser.add_argument("--experiment-prefix", default="repo-research-poc")
    parser.add_argument("--allow-source-upload", action="store_true")
    args = parser.parse_args(argv)
    config = {"provider": "anthropic", "model": args.model, "temperature": 0, "max_tokens": 4096}
    if args.base_url:
        config["base_url"] = args.base_url
    if args.langsmith_dataset:
        cases = load_cases(args.cases)
        results = record_langsmith_experiment(
            cases, args.snapshot, args.commit, args.output_dir, config,
            dataset_name=args.langsmith_dataset,
            experiment_prefix=args.experiment_prefix,
            allow_source_upload=args.allow_source_upload,
        )
        print(f"LangSmith experiment: {results.experiment_name}")
    else:
        result = run_local_suite(args.snapshot, args.commit, args.cases, args.output_dir, config)
        print(f"Local evaluation: {result['result_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
