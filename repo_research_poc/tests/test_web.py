"""Exercise the local browser API over real HTTP without calling a model."""

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from repo_research_poc.web import create_server


SHA = "a" * 40
MODEL = {"provider": "anthropic", "model": "test-model", "max_tokens": 1024, "temperature": 0}
LOCAL_OPENER = build_opener(ProxyHandler({}))


@contextmanager
def running_server(output_dir: Path, runner):
    server = create_server("127.0.0.1", 0, output_dir, MODEL, runner=runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request_json(url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with LOCAL_OPENER.open(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_submit_job_then_read_validated_result_and_history(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "main.py").write_text("value = 42\n", encoding="utf-8")
    output_dir = tmp_path / "runs"

    def fake_runner(snapshot_path, sha, question, output_path, model_config, **kwargs):
        assert snapshot_path == snapshot
        assert sha == SHA
        assert question == "What is the value?"
        assert model_config == MODEL
        result = {
            "run_id": "b" * 32,
            "status": "ok",
            "question": question,
            "answer": "The value is 42.",
            "citations": [
                {"path": "main.py", "start_line": 1, "end_line": 1, "quote": "value = 42"}
            ],
            "unresolved_questions": [],
            "tool_calls": [],
            "errors": [],
            "duration_ms": 12,
            "started_at": "2026-09-28T00:00:00+00:00",
        }
        output_path.mkdir()
        (output_path / ("b" * 32 + ".json")).write_text(json.dumps(result), encoding="utf-8")
        return result

    with running_server(output_dir, fake_runner) as base:
        status, job = request_json(
            base + "/api/jobs",
            {
                "snapshot": str(snapshot),
                "commit_sha": SHA,
                "question": "What is the value?",
            },
        )
        assert status == 202
        for _ in range(50):
            status, state = request_json(base + "/api/jobs/" + job["job_id"])
            if state["status"] == "complete":
                break
            time.sleep(0.02)
        assert status == 200
        assert state["result"]["answer"] == "The value is 42."
        assert request_json(base + "/api/runs")[1]["runs"][0]["run_id"] == "b" * 32
        assert (
            request_json(base + "/api/runs/" + "b" * 32)[1]["citations"][0]["quote"] == "value = 42"
        )


def test_rejects_invalid_inputs_and_untrusted_record_ids(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    called = []
    with running_server(tmp_path / "runs", lambda *args, **kwargs: called.append(args)) as base:
        status, body = request_json(
            base + "/api/jobs",
            {
                "snapshot": str(snapshot),
                "commit_sha": "not-a-sha",
                "question": "Question",
            },
        )
        assert status == 400
        assert "commit SHA" in body["error"]
        assert request_json(base + "/api/runs/..%2Fsecret")[0] == 404
        assert request_json(base + "/api/runs/" + "f" * 32)[0] == 404
        assert called == []


def test_page_is_served_and_failed_result_has_no_answer(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    def failing_runner(*args, **kwargs):
        return {
            "run_id": "c" * 32,
            "status": "invalid_citations",
            "answer": None,
            "citations": [],
            "citation_issues": [{"code": "quote_mismatch", "detail": "main.py"}],
            "errors": [],
            "tool_calls": [],
            "unresolved_questions": [],
        }

    with running_server(tmp_path / "runs", failing_runner) as base:
        with LOCAL_OPENER.open(base + "/", timeout=3) as response:
            page = response.read().decode("utf-8")
        assert "仓库快照" in page
        assert "Commit SHA" in page
        assert "运行记录" in page
        with LOCAL_OPENER.open(base + "/app.css", timeout=3) as response:
            css = response.read().decode("utf-8")
        assert "@import" not in css
        assert "https://" not in css
        status, job = request_json(
            base + "/api/jobs",
            {
                "snapshot": str(snapshot),
                "commit_sha": SHA,
                "question": "Question",
            },
        )
        assert status == 202
        for _ in range(50):
            _, state = request_json(base + "/api/jobs/" + job["job_id"])
            if state["status"] == "complete":
                break
            time.sleep(0.02)
        assert state["result"]["status"] == "invalid_citations"
        assert state["result"]["answer"] is None
