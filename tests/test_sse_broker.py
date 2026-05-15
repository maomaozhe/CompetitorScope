import pytest

from src.api.v1 import runtime
from src.api.v1.analysis import _agent_outputs_for_response


@pytest.mark.asyncio
async def test_sse_history_is_per_connection_and_not_consumed():
    run_id = "sse-broker-test"
    runtime.create_run(runtime.initial_state(run_id=run_id, query="AI IDE", hitl_mode="auto"))
    try:
        runtime._emit_event(run_id, "agent_start", {"agent": "planner", "message": "start"})

        first_client = await runtime.wait_for_events_after(run_id, 0, timeout=0.01)
        second_client = await runtime.wait_for_events_after(run_id, 0, timeout=0.01)

        assert [event["seq"] for event in first_client] == [1]
        assert [event["seq"] for event in second_client] == [1]

        runtime._emit_event(run_id, "agent_complete", {"agent": "planner"})
        next_events = await runtime.wait_for_events_after(run_id, first_client[-1]["seq"], timeout=0.01)

        assert [event["event"] for event in next_events] == ["agent_complete"]
        assert next_events[0]["seq"] == 2
    finally:
        runtime.RUN_STORE.pop(run_id, None)
        runtime._EVENT_HISTORY.pop(run_id, None)
        runtime._EVENT_CONDITIONS.pop(run_id, None)
        runtime._EVENT_SEQ.pop(run_id, None)


def test_analysis_status_synthesizes_agent_outputs_from_state():
    run_id = "status-output-snapshot-test"
    state = runtime.initial_state(run_id=run_id, query="AI IDE", hitl_mode="auto")
    runtime.create_run(state)
    try:
        state.update({
            "current_stage": "comparing",
            "confirmed_competitors": [
                {"name": "Cursor", "website": "https://cursor.com"},
                {"name": "GitHub Copilot", "website": "https://github.com/features/copilot"},
            ],
            "candidate_competitors": [
                {"name": "Cursor", "website": "https://cursor.com"},
                {"name": "GitHub Copilot", "website": "https://github.com/features/copilot"},
            ],
            "analysis_dimensions": ["features", "pricing"],
            "comparison_dimensions": ["features", "pricing"],
            "raw_sources": [{
                "competitor_id": "cursor",
                "url": "https://cursor.com/pricing",
                "title": "Cursor Pricing",
                "raw_content": "pricing",
            }],
            "competitor_profiles": [{
                "competitor_id": "cursor",
                "name": "Cursor",
                "one_liner": "AI coding IDE",
            }],
            "evidence_items": [{"competitor_id": "cursor"}],
        })
        runtime.RUN_STORE[run_id]["state"] = state

        outputs = _agent_outputs_for_response(run_id, state)

        assert {output["agent"] for output in outputs} == {
            "planner",
            "collector",
            "analyst",
            "comparator",
        }
        assert any(output["title"] == "准备横向对比" for output in outputs)
    finally:
        runtime.RUN_STORE.pop(run_id, None)
        runtime._EVENT_HISTORY.pop(run_id, None)
        runtime._EVENT_CONDITIONS.pop(run_id, None)
        runtime._EVENT_SEQ.pop(run_id, None)
