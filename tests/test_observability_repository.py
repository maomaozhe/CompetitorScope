import json
import time

from src.observability.repository import ObservabilityRepository


def make_repository(tmp_path):
    return ObservabilityRepository(
        database_path=tmp_path / "observability.db",
        artifact_root=tmp_path / "artifacts",
    )


def test_events_are_persistent_and_sequence_is_monotonic(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("run-1", {"query": "AI IDE"})

    first = repository.append_event("run-1", "run.started", {"status": "running"})
    second = repository.append_event("run-1", "agent.status_changed", {"agent": "planner"})

    reopened = make_repository(tmp_path)
    events = reopened.list_events("run-1", after_seq=0)
    assert [event["seq"] for event in events] == [1, 2]
    assert first["event_id"] != second["event_id"]
    assert events[1]["payload"] == {"agent": "planner"}


def test_artifacts_are_redacted_content_addressed_and_deduplicated(tmp_path):
    repository = make_repository(tmp_path)
    payload = {
        "Authorization": "Bearer secret-token",
        "nested": {"api_key": "private", "value": "safe"},
    }

    first = repository.save_artifact("llm.request", payload)
    second = repository.save_artifact("llm.request", payload)

    assert first["artifact_id"] == second["artifact_id"]
    stored = repository.read_artifact(first["artifact_id"])
    assert stored["content"]["Authorization"] == "[REDACTED]"
    assert stored["content"]["nested"]["api_key"] == "[REDACTED]"
    assert stored["content"]["nested"]["value"] == "safe"


def test_usage_token_counts_are_not_treated_as_credentials(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("usage", {"query": "AI IDE"})

    event = repository.append_event(
        "usage",
        "llm.completed",
        {"usage": {"input_tokens": 12, "output_tokens": 7}, "access_token": "secret"},
    )

    assert event["payload"]["usage"] == {"input_tokens": 12, "output_tokens": 7}
    assert event["payload"]["access_token"] == "[REDACTED]"


def test_token_total_increment_is_atomic(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("usage", {"query": "AI IDE"})

    repository.increment_token_total("usage", 12)
    repository.increment_token_total("usage", 7)

    assert repository.get_run("usage")["token_total"] == 19


def test_snapshot_replaces_large_values_with_artifact_references(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("run-1", {"query": "AI IDE"})

    snapshot = repository.create_snapshot(
        "run-1",
        boundary="node.completed",
        state={"current_stage": "collecting", "raw_sources": [{"raw_content": "x" * 6000}]},
    )

    compact = json.loads(snapshot["state_json"])
    assert compact["current_stage"] == "collecting"
    assert compact["raw_sources"]["artifact_id"]
    assert snapshot["changed_keys"] == ["current_stage", "raw_sources"]


def test_eval_case_pins_referenced_run_and_builds_manifest(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("run-1", {"query": "AI IDE", "hitl_mode": "auto"})
    repository.append_event("run-1", "tool.completed", {"tool": "search", "input_hash": "abc"})
    repository.create_snapshot("run-1", boundary="run.completed", state={"report": {"title": "Report"}})
    repository.update_run("run-1", status="completed", finished_at=time.time())

    case = repository.create_eval_case("run-1", label="baseline")

    assert case["manifest"]["request"]["query"] == "AI IDE"
    assert case["manifest"]["source_run_id"] == "run-1"
    assert repository.get_run("run-1")["pinned"] is True


def test_retention_keeps_pinned_runs_and_collects_unreferenced_artifacts(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("expired", {"query": "old"})
    orphan = repository.save_artifact("tool.result", {"value": "old"})
    repository.append_event("expired", "tool.completed", {}, artifact_refs=[orphan["artifact_id"]])
    repository.create_run("pinned", {"query": "important"})
    kept = repository.save_artifact("tool.result", {"value": "keep"})
    repository.append_event("pinned", "tool.completed", {}, artifact_refs=[kept["artifact_id"]])
    repository.update_run("pinned", status="completed", finished_at=time.time())
    repository.create_eval_case("pinned", "baseline")
    with repository._connect() as connection:
        connection.execute("UPDATE trace_runs SET started_at = ?", (time.time() - 40 * 86400,))

    result = repository.cleanup(retention_days=30)

    assert result == {"runs_deleted": 1, "artifacts_deleted": 1}
    assert repository.get_run("expired") is None
    assert repository.get_run("pinned") is not None
    assert repository.read_artifact(orphan["artifact_id"]) is None
    assert repository.read_artifact(kept["artifact_id"]) is not None


def test_startup_marks_unfinished_runs_interrupted(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("running", {"query": "AI IDE"})

    count = repository.mark_unfinished_runs_interrupted()

    assert count == 1
    assert repository.get_run("running")["status"] == "interrupted"
