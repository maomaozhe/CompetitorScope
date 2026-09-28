from pathlib import Path

from repo_research_poc.__main__ import main


def test_cli_passes_explicit_inputs_and_reports_result(tmp_path: Path, capsys) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    captured = {}

    def fake_runner(*args, **kwargs):
        captured["args"] = args
        return {"status": "ok", "answer": "Answer", "citations": [],
                "unresolved_questions": [], "result_path": str(tmp_path / "result.json")}

    status = main(
        ["--snapshot", str(snapshot), "--commit", "a" * 40,
         "--question", "Where?", "--output-dir", str(tmp_path / "runs")],
        runner=fake_runner,
    )
    assert status == 0
    assert captured["args"][0] == snapshot
    assert captured["args"][1] == "a" * 40
    assert "Answer" in capsys.readouterr().out
