from src.observability.recorder import TraceRecorder
from src.observability.repository import ObservabilityRepository


def test_recorder_creates_nested_spans_and_decision_event(tmp_path):
    repository = ObservabilityRepository(tmp_path / "trace.db", tmp_path / "artifacts")
    repository.create_run("run-1", {"query": "AI IDE"})
    recorder = TraceRecorder(repository)

    parent = recorder.start_span("run-1", name="collector", kind="agent", agent="collector")
    child = recorder.start_span(
        "run-1",
        name="web_search",
        kind="tool",
        parent_span_id=parent,
        agent="collector",
    )
    recorder.record_decision(
        "run-1",
        span_id=parent,
        decision_point="source_selection",
        candidates=["official", "review"],
        selected=["official"],
        reason="Prefer primary sources",
        confidence=0.9,
        evidence_refs=["artifact-1"],
        strategy_version="collector.v1",
    )
    recorder.finish_span("run-1", child)
    recorder.finish_span("run-1", parent)

    spans = repository.list_spans("run-1")
    assert spans[1]["parent_span_id"] == parent
    decision = [event for event in repository.list_events("run-1") if event["type"] == "decision.recorded"][0]
    assert decision["payload"]["reason"] == "Prefer primary sources"
    assert decision["payload"]["confidence"] == 0.9


def test_recorder_moves_raw_payloads_into_artifacts(tmp_path):
    repository = ObservabilityRepository(tmp_path / "trace.db", tmp_path / "artifacts")
    repository.create_run("run-1", {"query": "AI IDE"})
    recorder = TraceRecorder(repository)

    event = recorder.record_event(
        "run-1",
        "llm.completed",
        {"model": "demo", "response": {"text": "result", "api_key": "secret"}},
        artifact_fields={"response": "llm.response"},
    )

    assert "response" not in event["payload"]
    assert len(event["artifact_refs"]) == 1
    artifact = repository.read_artifact(event["artifact_refs"][0])
    assert artifact["content"]["api_key"] == "[REDACTED]"
