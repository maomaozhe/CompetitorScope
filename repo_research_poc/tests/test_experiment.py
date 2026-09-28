import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_research_poc.experiment import load_cases, record_langsmith_experiment, run_local_suite


SHA = "c" * 40


def test_pending_cases_have_no_business_gold(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps({"cases": [
        {"id": "entry", "question": "Where is the entry point?", "review_status": "pending", "reference_answer": None}
    ]}), encoding="utf-8")
    cases = load_cases(cases_path)
    assert cases[0].reference_answer is None
    assert cases[0].review_status == "pending"


def test_local_suite_passes_only_question_to_runner(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps({"cases": [
        {"id": "entry", "question": "Where is the entry point?", "review_status": "pending", "reference_answer": None}
    ]}), encoding="utf-8")
    received = []

    def fake_runner(*args, **kwargs):
        received.append(args[2])
        return {"status": "ok", "answer": "Here", "citations": [], "result_path": "run.json"}

    result = run_local_suite(snapshot, SHA, cases_path, tmp_path / "runs", {"provider": "anthropic", "model": "m"}, runner=fake_runner)
    assert received == ["Where is the entry point?"]
    assert result["cases"][0]["review_status"] == "pending"
    assert result["cases"][0]["business_answer_score"] is None


def test_local_suite_allows_cases_under_excluded_poc_tree(tmp_path: Path) -> None:
    cases_path = tmp_path / "repo_research_poc" / "evals" / "cases.json"
    cases_path.parent.mkdir(parents=True)
    cases_path.write_text(json.dumps({"cases": [
        {"id": "entry", "question": "Where?", "review_status": "pending", "reference_answer": None}
    ]}), encoding="utf-8")
    result = run_local_suite(
        tmp_path, SHA, cases_path, tmp_path.parent / "runs", {"provider": "anthropic", "model": "m"},
        runner=lambda *_args, **_kwargs: {"status": "ok", "answer": "A", "citations": [], "result_path": "run.json"},
    )
    assert len(result["cases"]) == 1


def test_langsmith_experiment_needs_explicit_upload_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source upload"):
        record_langsmith_experiment([], tmp_path, SHA, tmp_path / "runs", {},
                                    dataset_name="test", experiment_prefix="test",
                                    allow_source_upload=False)


def test_langsmith_experiment_records_citation_metric_without_gold_upload(tmp_path: Path, monkeypatch) -> None:
    import repo_research_poc.experiment as experiment

    calls = {}

    class FakeClient:
        def create_dataset(self, name, **kwargs):
            calls["dataset"] = name

        def create_examples(self, **kwargs):
            calls["examples"] = kwargs["examples"]

    def fake_evaluate(target, **kwargs):
        calls["target_output"] = target({"question": "Where?"})
        calls["score"] = kwargs["evaluators"][0](SimpleNamespace(outputs=calls["target_output"]), None)
        return SimpleNamespace(experiment_name="run-1")

    monkeypatch.setattr(experiment, "evaluate", fake_evaluate)
    cases = [experiment.ResearchCase(id="case-1", question="Where?")]
    result = record_langsmith_experiment(
        cases, tmp_path, SHA, tmp_path.parent / "runs", {"provider": "anthropic", "model": "m"},
        dataset_name="dataset-1", experiment_prefix="experiment-1", allow_source_upload=True,
        client=FakeClient(),
        runner=lambda *_args, **_kwargs: {"answer": "A", "status": "ok", "citations": [], "citation_issues": []},
    )
    assert result.experiment_name == "run-1"
    assert calls["dataset"] == "dataset-1"
    assert calls["examples"][0]["outputs"] == {}
    assert calls["score"]["score"] is True
