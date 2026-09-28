import json
from pathlib import Path

from langchain_core.messages import AIMessage

from repo_research_poc.runner import run_research


SHA = "b" * 40
MODEL = {"provider": "anthropic", "model": "claude-sonnet-4-6", "temperature": 0, "base_url": "https://example.com"}


class FakeAgent:
    def __init__(self, content: str, *, fail: bool = False):
        self.content = content
        self.fail = fail

    def invoke(self, inputs, config):
        assert "/repo" in inputs["messages"][0]["content"]
        callback = config["callbacks"][0]
        callback.on_tool_start({"name": "read_file"}, '{"file_path":"/repo/main.py"}', run_id="tool-1")
        callback.on_tool_end("source text", run_id="tool-1")
        if self.fail:
            raise RuntimeError("model failed")
        return {"messages": [AIMessage(content=self.content)]}


class CorrectingAgent:
    def __init__(self):
        self.calls = 0

    def invoke(self, inputs, config):
        self.calls += 1
        if self.calls == 1:
            content = json.dumps({"answer": "42", "citations": [
                {"path": "main.py", "start_line": 2, "end_line": 2, "quote": "value = 42"}
            ], "unresolved_questions": []})
            return {"messages": [*inputs["messages"], AIMessage(content=content)]}
        assert "quote_mismatch" in inputs["messages"][-1].content
        content = json.dumps({"answer": "42", "citations": [
            {"path": "main.py", "start_line": 1, "end_line": 1, "quote": "value = 42"}
        ], "unresolved_questions": []})
        return {"messages": [*inputs["messages"], AIMessage(content=content)]}


class TruncatedThenValidAgent:
    def __init__(self, *, always_truncated: bool = False):
        self.calls = 0
        self.always_truncated = always_truncated

    def invoke(self, inputs, config):
        self.calls += 1
        if self.calls == 1 or self.always_truncated:
            content = '{"answer":"unfinished'
        else:
            assert "short" in inputs["messages"][-1].content.lower()
            content = json.dumps({
                "answer": "42",
                "citations": [{"path": "main.py", "start_line": 1, "end_line": 1, "quote": "value = 42"}],
                "unresolved_questions": [],
            })
        return {"messages": [*inputs["messages"], AIMessage(content=content)]}


def test_run_saves_valid_answer_and_auditable_metadata(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    answer = json.dumps({
        "answer": "The value is 42.",
        "citations": [{"path": "main.py", "start_line": 1, "end_line": 1, "quote": "value = 42"}],
        "unresolved_questions": [],
    })
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: FakeAgent(answer),
    )
    saved = json.loads(Path(result["result_path"]).read_text(encoding="utf-8"))
    assert saved["status"] == "ok"
    assert saved["answer"] == "The value is 42."
    assert saved["citations"][0]["path"] == "main.py"
    assert saved["tool_calls"][0]["name"] == "read_file"
    assert saved["tool_calls"][0]["duration_ms"] >= 0
    assert saved["duration_ms"] >= 0
    assert saved["model"] == MODEL
    assert "api_key" not in saved["model"]


def test_invalid_citation_fails_closed(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    answer = json.dumps({
        "answer": "The value is 99.",
        "citations": [{"path": "main.py", "start_line": 1, "end_line": 1, "quote": "value = 99"}],
        "unresolved_questions": [],
    })
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: FakeAgent(answer),
    )
    assert result["status"] == "invalid_citations"
    assert result["answer"] is None
    assert result["citation_issues"][0]["code"] == "quote_mismatch"
    assert result["unverified_response"]["citations"][0]["quote"] == "value = 99"


def test_model_error_is_saved(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: FakeAgent("", fail=True),
    )
    assert result["status"] == "error"
    assert result["errors"][0]["type"] == "RuntimeError"
    assert Path(result["result_path"]).is_file()


def test_empty_answer_without_unresolved_question_is_rejected(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    answer = json.dumps({"answer": "", "citations": [], "unresolved_questions": []})
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: FakeAgent(answer),
    )
    assert result["status"] == "invalid_citations"


def test_agent_gets_one_chance_to_correct_invalid_line_number(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\nother\n", encoding="utf-8")
    agent = CorrectingAgent()
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: agent,
    )
    assert agent.calls == 2
    assert result["status"] == "ok"
    assert result["citations"][0]["start_line"] == 1
    assert result["citation_attempts"][0]["issues"][0]["code"] == "quote_mismatch"


def test_truncated_json_gets_one_short_response_retry(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    agent = TruncatedThenValidAgent()
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: agent,
    )
    assert agent.calls == 2
    assert result["status"] == "ok"
    assert result["answer"] == "42"
    assert result["parse_attempts"][0]["error_type"] == "ValidationError"


def test_repeated_truncated_json_stops_after_second_attempt(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    agent = TruncatedThenValidAgent(always_truncated=True)
    result = run_research(
        snapshot, SHA, "What is the value?", tmp_path / "runs", MODEL,
        agent_factory=lambda *_args, **_kwargs: agent,
    )
    assert agent.calls == 2
    assert result["status"] == "error"
    assert len(result["parse_attempts"]) == 2
