from types import SimpleNamespace
import time

import pytest
import src.services.llm as llm_service
import src.tools.web_search as web_search
from src.graph.runtime_events import reset_event_emitter, set_event_emitter
from src.observability.replay import reset_replay_context, set_replay_context
from src.observability.replay import FrozenToolResultMissing
from src.observability.execution import execute_eval_execution
from src.observability.repository import ObservabilityRepository
from src.api.v1 import runtime


def test_frozen_tool_result_prevents_live_network_call(monkeypatch):
    events = []
    arguments = {"query": "example", "max_results": 1}
    input_hash = web_search.tool_input_hash(arguments)
    token = set_replay_context(
        tool_results={f"web_search:{input_hash}": [{"url": "https://frozen.example"}]}
    )
    emitter = set_event_emitter(lambda event, data: events.append((event, data)))
    monkeypatch.setattr(web_search, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("network used")))
    try:
        result = web_search.search("example", max_results=1)
    finally:
        reset_event_emitter(emitter)
        reset_replay_context(token)

    assert result == [{"url": "https://frozen.example"}]
    assert events[-1][1]["replayed"] is True


def test_frozen_mode_rejects_missing_tool_result_without_network(monkeypatch):
    token = set_replay_context(tool_results={}, freeze_tools=True)
    monkeypatch.setattr(
        web_search,
        "_get_client",
        lambda: (_ for _ in ()).throw(AssertionError("network used")),
    )
    try:
        with pytest.raises(FrozenToolResultMissing):
            web_search.search("not-recorded", max_results=1)
    finally:
        reset_replay_context(token)


def test_eval_variant_overrides_model_parameters_and_system_prompt(monkeypatch):
    captured = {}

    class FakeChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content="answer", usage_metadata={})

    monkeypatch.setattr(llm_service, "ChatAnthropic", FakeChatModel)
    token = set_replay_context(
        model_overrides={"planner": "candidate-model"},
        parameter_overrides={"planner": {"temperature": 0.2}},
        prompt_overrides={"planner": "Candidate system prompt"},
    )
    try:
        model = llm_service.get_llm("planner")
        model.invoke([SimpleNamespace(content="Original system"), SimpleNamespace(content="Question")])
    finally:
        reset_replay_context(token)

    assert captured["model"] == "candidate-model"
    assert captured["temperature"] == 0.2
    assert captured["messages"][0].content == "Candidate system prompt"


@pytest.mark.asyncio
async def test_eval_execution_uses_frozen_catalog_and_records_metrics(tmp_path):
    repository = ObservabilityRepository(tmp_path / "eval.db", tmp_path / "artifacts")
    previous = runtime.get_observability_repository()
    runtime.configure_observability(repository)
    try:
        repository.create_run("baseline", {"query": "AI IDE", "hitl_mode": "auto"})
        artifact = repository.save_artifact("tool.web_search", [{"url": "https://frozen.example"}])
        repository.append_event(
            "baseline",
            "tool.completed",
            {"tool": "web_search", "input_hash": "frozen-hash"},
            artifact_refs=[artifact["artifact_id"]],
        )
        repository.update_run("baseline", status="completed", finished_at=1)
        case = repository.create_eval_case("baseline", "baseline")
        execution = repository.create_eval_execution(case["case_id"], "candidate", {})

        async def fake_runner(run_id, state):
            found, result = __import__(
                "src.observability.replay", fromlist=["replayed_tool_result"]
            ).replayed_tool_result("web_search", "frozen-hash")
            assert found is True
            assert result[0]["url"] == "https://frozen.example"
            repository.update_run(run_id, status="completed", finished_at=repository.get_run(run_id)["started_at"] + 1)

        finished = await execute_eval_execution(repository, execution["execution_id"], runner=fake_runner)

        assert finished["status"] == "completed"
        assert finished["run_id"].startswith("eval-")
        assert finished["metrics"]["completed"] is True
        assert finished["metrics"]["duration_ms"] == 1000
        assert repository.get_run(finished["run_id"])["pinned"] is True
    finally:
        runtime.configure_observability(previous)


@pytest.mark.asyncio
async def test_eval_execution_replays_recorded_hitl_responses(tmp_path):
    repository = ObservabilityRepository(tmp_path / "hitl.db", tmp_path / "artifacts")
    previous = runtime.get_observability_repository()
    runtime.configure_observability(repository)
    try:
        repository.create_run("baseline", {"query": "AI IDE", "hitl_mode": "interactive"})
        repository.append_event(
            "baseline",
            "hitl.resolved",
            {"response": {"competitors": [{"name": "Cursor"}]}},
        )
        repository.update_run("baseline", status="completed", finished_at=1)
        case = repository.create_eval_case("baseline", "interactive baseline")
        execution = repository.create_eval_execution(case["case_id"], "candidate", {})
        resumes = []

        async def fake_runner(run_id, graph_input):
            if isinstance(graph_input, dict):
                runtime.RUN_STORE[run_id]["pending_interrupt"] = {
                    "payload": {"interrupt_id": "recorded-1"},
                    "created_at": 1,
                }
            else:
                resumes.append(graph_input.resume)
                repository.update_run(run_id, status="completed", finished_at=time.time())

        await execute_eval_execution(repository, execution["execution_id"], runner=fake_runner)

        assert resumes == [{"competitors": [{"name": "Cursor"}]}]
    finally:
        runtime.configure_observability(previous)
