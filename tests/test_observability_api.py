from fastapi.testclient import TestClient

from src.api.v1 import runtime
from src.main import app
from src.observability.repository import ObservabilityRepository


def test_observability_read_and_eval_endpoints(tmp_path):
    repository = ObservabilityRepository(tmp_path / "api.db", tmp_path / "artifacts")
    previous = runtime.get_observability_repository()
    runtime.configure_observability(repository)
    try:
        state = runtime.initial_state(run_id="api-run", query="AI IDE")
        runtime.create_run(state)
        artifact = repository.save_artifact("report", "# Report")
        repository.append_event(
            "api-run", "decision.recorded", {"decision_point": "competitors", "selected": ["A"]},
            artifact_refs=[artifact["artifact_id"]],
        )
        repository.create_snapshot("api-run", "run.completed", {"report": "# Report"})
        repository.update_run("api-run", status="completed", finished_at=1)

        client = TestClient(app)
        assert client.get("/api/v1/observability/runs").json()["runs"][0]["run_id"] == "api-run"
        detail = client.get("/api/v1/observability/runs/api-run").json()
        assert detail["run"]["request"]["query"] == "AI IDE"
        assert detail["spans"] == []

        events = client.get("/api/v1/observability/runs/api-run/events?after_seq=0").json()
        assert any(event["type"] == "decision.recorded" for event in events["events"])
        snapshots = client.get("/api/v1/observability/runs/api-run/snapshots").json()
        assert snapshots["snapshots"][-1]["boundary"] == "run.completed"
        stored_artifact = client.get(
            f"/api/v1/observability/artifacts/{artifact['artifact_id']}"
        ).json()
        assert stored_artifact["content"] == "# Report"

        case_response = client.post(
            "/api/v1/observability/runs/api-run/eval-cases", json={"label": "baseline"}
        )
        assert case_response.status_code == 200
        case_id = case_response.json()["case_id"]
        execution = client.post(
            f"/api/v1/observability/eval-cases/{case_id}/executions",
            json={"variant_label": "candidate", "model_overrides": {"planner": "demo-model"}},
        )
        assert execution.status_code == 200
        assert execution.json()["status"] == "pending"
        comparison = client.get(
            f"/api/v1/observability/eval-cases/{case_id}/compare"
        )
        assert comparison.status_code == 200
        assert comparison.json()["case_id"] == case_id

        cancel_state = runtime.initial_state(run_id="cancel-run", query="cancel me")
        runtime.create_run(cancel_state)
        assert client.delete("/api/v1/analysis/cancel-run").status_code == 200
        assert repository.get_run("cancel-run")["status"] == "cancelled"
        assert repository.list_events("cancel-run")[-1]["type"] == "run.cancelled"
    finally:
        runtime.configure_observability(previous)


def test_sse_replays_terminal_run_after_memory_restart(tmp_path):
    repository = ObservabilityRepository(tmp_path / "restart.db", tmp_path / "artifacts")
    previous = runtime.get_observability_repository()
    runtime.configure_observability(repository)
    try:
        runtime.create_run(runtime.initial_state(run_id="persisted-run", query="AI IDE"))
        runtime._emit_event("persisted-run", "complete", {"done": True})
        runtime.RUN_STORE.pop("persisted-run", None)
        runtime._EVENT_CONDITIONS.pop("persisted-run", None)

        client = TestClient(app)
        with client.stream(
            "GET",
            "/api/v1/analysis/persisted-run/stream",
            headers={"Last-Event-ID": "0"},
        ) as response:
            body = "\n".join(response.iter_lines())

        assert response.status_code == 200
        assert "event: complete" in body
    finally:
        runtime.configure_observability(previous)
