import pytest

from src.api.v1 import runtime
from src.observability.repository import ObservabilityRepository


@pytest.fixture
def observed_runtime(tmp_path):
    repository = ObservabilityRepository(tmp_path / "runtime.db", tmp_path / "artifacts")
    previous = runtime.get_observability_repository()
    runtime.configure_observability(repository)
    yield repository
    runtime.configure_observability(previous)


@pytest.mark.asyncio
async def test_runtime_persists_sse_events_and_replays_legacy_names(observed_runtime):
    run_id = "persistent-sse"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))
    runtime._emit_event(run_id, "agent_start", {"agent": "planner", "message": "start"})

    events = await runtime.wait_for_events_after(run_id, 0, timeout=0.01)
    stored = observed_runtime.list_events(run_id)

    assert events[-1]["event"] == "agent_start"
    assert events[-1]["data"]["agent"] == "planner"
    assert stored[-1]["type"] == "agent.status_changed"
    assert stored[-1]["status"] == "running"


def test_runtime_run_start_and_snapshot_are_durable(observed_runtime):
    run_id = "snapshot-runtime"
    state = runtime.initial_state(run_id=run_id, query="AI IDE")
    runtime.create_run(state)

    trace_run = observed_runtime.get_run(run_id)
    snapshots = observed_runtime.list_snapshots(run_id)

    assert trace_run["request"]["query"] == "AI IDE"
    assert observed_runtime.list_events(run_id)[0]["type"] == "run.started"
    assert snapshots[0]["boundary"] == "run.started"


@pytest.mark.asyncio
async def test_graph_debug_events_create_agent_spans_and_node_snapshots(observed_runtime, monkeypatch):
    class FakeWorkflow:
        async def astream(self, graph_input, config, stream_mode):
            span_id = runtime._emit_event(
                "span-runtime",
                "_agent_span_started",
                {"agent": "planner", "node": "planner_discover"},
            )
            yield {"type": "task", "payload": {"id": "task-1", "name": "planner_discover"}}
            runtime._emit_event(
                "span-runtime",
                "_agent_span_finished",
                {
                    "agent": "planner",
                    "node": "planner_discover",
                    "parent_span_id": span_id,
                },
            )
            yield {
                "type": "task_result",
                "payload": {
                    "id": "task-1",
                    "name": "planner_discover",
                    "result": {"candidate_competitors": [], "confirmed_competitors": []},
                },
            }

        def get_state(self, config):
            return type("Snapshot", (), {
                "values": {"run_id": "span-runtime", "current_stage": "complete"},
                "next": (),
            })()

    monkeypatch.setattr(runtime, "WORKFLOW", FakeWorkflow())
    state = runtime.initial_state(run_id="span-runtime", query="AI IDE")
    runtime.create_run(state)

    await runtime.run_until_pause("span-runtime", state)

    spans = observed_runtime.list_spans("span-runtime")
    assert [(span["kind"], span["name"], span["status"]) for span in spans] == [
        ("agent", "planner_discover", "completed")
    ]
    boundaries = [item["boundary"] for item in observed_runtime.list_snapshots("span-runtime")]
    assert "node.completed:planner_discover" in boundaries
    assert boundaries[-1] == "run.completed"
    decisions = [
        event for event in observed_runtime.list_events("span-runtime")
        if event["type"] == "decision.recorded"
    ]
    assert decisions[0]["payload"]["decision_point"] == "competitor_selection"


@pytest.mark.asyncio
async def test_hitl_resume_records_response_and_after_snapshot(observed_runtime, monkeypatch):
    run_id = "hitl-observed"
    state = runtime.initial_state(run_id=run_id, query="AI IDE", hitl_mode="interactive")
    runtime.create_run(state)
    runtime.RUN_STORE[run_id]["pending_interrupt"] = {
        "payload": {"interrupt_id": "interrupt-1", "type": "competitor_confirm"},
        "created_at": 1,
    }

    async def no_op_runner(run_id, graph_input):
        return None

    monkeypatch.setattr(runtime, "run_until_pause", no_op_runner)
    await runtime.resume_run(run_id, {"competitors": [{"name": "Cursor"}]})

    events = observed_runtime.list_events(run_id)
    resolved = [event for event in events if event["type"] == "hitl.resolved"]
    assert resolved[-1]["payload"]["response"]["competitors"][0]["name"] == "Cursor"
    assert observed_runtime.list_snapshots(run_id)[-1]["boundary"] == "hitl.resolved"


def test_noncritical_observability_failure_degrades_without_breaking_run(observed_runtime, monkeypatch):
    run_id = "degraded-observability"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))

    monkeypatch.setattr(
        runtime._TRACE_RECORDER,
        "record_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    runtime._emit_event(run_id, "agent_start", {"agent": "planner", "message": "start"})

    trace_run = observed_runtime.get_run(run_id)
    assert trace_run["degraded"] is True
    assert trace_run["replayable"] is False
    assert runtime.RUN_STORE[run_id]["done"] is False


def test_span_recorder_failure_is_noncritical(observed_runtime, monkeypatch):
    run_id = "degraded-span"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))
    monkeypatch.setattr(
        runtime._TRACE_RECORDER,
        "start_span",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("database locked")),
    )

    assert runtime._emit_event(
        run_id,
        "_agent_span_started",
        {"agent": "planner", "node": "planner_outline"},
    ) is None
    assert observed_runtime.get_run(run_id)["degraded"] is True
    assert runtime.RUN_STORE[run_id]["done"] is False


def test_trace_initialization_failure_does_not_reject_analysis(observed_runtime, monkeypatch):
    monkeypatch.setattr(
        observed_runtime,
        "create_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("database unavailable")),
    )
    state = runtime.initial_state(run_id="no-trace", query="AI IDE")

    runtime.create_run(state)

    assert runtime.RUN_STORE["no-trace"]["done"] is False
    assert runtime.RUN_STORE["no-trace"]["observability_degraded"] is True


def test_llm_span_is_parented_to_active_agent_span(observed_runtime):
    run_id = "nested-span"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))
    parent = runtime._TRACE_RECORDER.start_span(
        run_id, name="planner_outline", kind="agent", agent="planner", node="planner_outline"
    )
    runtime._emit_event(
        run_id,
        "llm.requested",
        {"call_id": "call-1", "role": "planner", "agent": "planner", "node": "planner_outline", "parent_span_id": parent, "model": "demo", "request": []},
    )
    runtime._emit_event(
        run_id,
        "llm.completed",
        {"call_id": "call-1", "role": "planner", "agent": "planner", "node": "planner_outline", "model": "demo", "response": "ok", "usage": {}},
    )

    llm_span = [span for span in observed_runtime.list_spans(run_id) if span["kind"] == "llm"][0]
    assert llm_span["parent_span_id"] == parent


def test_interleaved_fanout_operations_keep_explicit_parent_spans(observed_runtime):
    run_id = "fanout-parents"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))
    first = runtime._TRACE_RECORDER.start_span(
        run_id, name="collect_competitor", kind="agent", agent="collector", node="collect_competitor"
    )
    second = runtime._TRACE_RECORDER.start_span(
        run_id, name="collect_competitor", kind="agent", agent="collector", node="collect_competitor"
    )

    for call_id, parent in (("first", first), ("second", second)):
        runtime._emit_event(
            run_id,
            "tool.requested",
            {"call_id": call_id, "tool": "web_search", "agent": "collector", "node": "collect_competitor", "parent_span_id": parent},
        )

    tool_spans = [span for span in observed_runtime.list_spans(run_id) if span["kind"] == "tool"]
    assert [span["parent_span_id"] for span in tool_spans] == [first, second]


def test_cancelled_run_cannot_be_overwritten_by_completion(observed_runtime):
    run_id = "cancel-terminal"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE"))

    runtime.cancel_run(run_id)
    runtime._emit_event(run_id, "complete", {"done": True})

    assert observed_runtime.get_run(run_id)["status"] == "cancelled"
    assert all(event["type"] != "run.finished" for event in observed_runtime.list_events(run_id))
