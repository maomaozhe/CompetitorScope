from pathlib import Path
import subprocess

import pytest

from repo_research_poc.snapshot import ReadOnlySnapshotBackend, staged_snapshot, validate_request


SHA = "a" * 40


def test_stage_excludes_evaluation_and_secret_files(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("answer = 42\n", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "gold.json").write_text("answer key", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    with staged_snapshot(tmp_path) as staged:
        assert (staged.root / "main.py").read_text(encoding="utf-8") == "answer = 42\n"
        assert not (staged.root / "evals").exists()
        assert not (staged.root / ".env").exists()
        assert set(staged.manifest) == {"main.py"}


def test_snapshot_backend_rejects_write(tmp_path: Path) -> None:
    backend = ReadOnlySnapshotBackend(root_dir=tmp_path, virtual_mode=True)
    with pytest.raises(PermissionError):
        backend.write("/main.py", "bad")
    with pytest.raises(PermissionError):
        backend.delete("/main.py")


def test_grep_uses_no_host_process_and_reads_unicode(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "main.py").write_text("# 启动时初始化数据库\n", encoding="utf-8")
    backend = ReadOnlySnapshotBackend(root_dir=tmp_path, virtual_mode=True)

    def forbidden_process(*args, **kwargs):
        raise AssertionError("grep started a host process")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    result = backend.grep("启动", path="/")
    assert result.error is None
    assert result.matches[0]["text"] == "# 启动时初始化数据库"


def test_request_requires_explicit_snapshot_sha_and_question(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_request(tmp_path, "HEAD", "Where is it?", tmp_path.parent / "runs")
    with pytest.raises(ValueError):
        validate_request(tmp_path, SHA, " ", tmp_path.parent / "runs")
    with pytest.raises(ValueError):
        validate_request(tmp_path, SHA, "Where is it?", tmp_path / "runs")


def test_agent_exposes_only_retrieval_tools(tmp_path: Path) -> None:
    from repo_research_poc.agent import build_agent, normalize_anthropic_base_url

    model_config = {"provider": "anthropic", "model": "ark-code-latest", "base_url": "https://example.com/v1"}
    agent = build_agent(tmp_path, model_config, api_key="dummy")
    names = set(agent.nodes["tools"].bound.tools_by_name)
    assert names == {"ls", "glob", "grep", "read_file"}
    assert "execute" not in names
    assert "task" not in names
    assert normalize_anthropic_base_url(model_config["base_url"]) == "https://example.com"
