"""LangGraph workflow — parallel fan-out MVP pipeline."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from langgraph.graph import StateGraph, START, END

from src.graph.state import AnalysisState
from src.graph.nodes import planner, collector, analyst, comparator, writer
from src.graph.runtime_events import reset_event_context, set_event_context


def _observed_node(agent: str, node: str, function: Callable[..., Any]) -> Callable[..., Any]:
    """Attach agent/node metadata to events emitted while a graph node runs."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = set_event_context(agent=agent, node=node)
        try:
            from src.graph.runtime_events import emit_event

            span_id = emit_event("_agent_span_started", {})
        finally:
            reset_event_context(token)

        token = set_event_context(agent=agent, node=node, parent_span_id=span_id)
        failure: Exception | None = None
        try:
            emit_event("agent_start", {"message": f"{node} started"})
            result = function(*args, **kwargs)
            emit_event("agent_complete", {})
            return result
        except Exception as exc:
            failure = exc
            raise
        finally:
            emit_event(
                "_agent_span_finished",
                {"status": "failed", "error": str(failure)} if failure else {},
            )
            reset_event_context(token)

    return wrapped


def build_workflow(checkpointer=None):
    graph = StateGraph(AnalysisState)

    # Nodes
    graph.add_node("planner_discover", _observed_node("planner", "planner_discover", planner.planner_discover))
    graph.add_node("planner_outline", _observed_node("planner", "planner_outline", planner.planner_outline))
    graph.add_node("collect_competitor", _observed_node("collector", "collect_competitor", collector.collect_competitor))
    graph.add_node("join_collectors", _observed_node("collector", "join_collectors", collector.join_collectors))
    graph.add_node("analyze_competitor", _observed_node("analyst", "analyze_competitor", analyst.analyze_competitor))
    graph.add_node("join_analysts", _observed_node("analyst", "join_analysts", analyst.join_analysts))
    graph.add_node("comparator", _observed_node("comparator", "comparator", comparator.comparator_node))
    graph.add_node("writer", _observed_node("writer", "writer", writer.writer_node))

    # Linear start
    graph.add_edge(START, "planner_discover")
    graph.add_edge("planner_discover", "planner_outline")

    # Planner → fan out collectors (Send API)
    graph.add_conditional_edges("planner_outline", collector.fan_out_collectors)

    # Collectors all feed back → join_collectors (barrier, no routing needed)
    graph.add_edge("collect_competitor", "join_collectors")

    # Join → fan out analysts
    graph.add_conditional_edges("join_collectors", analyst.fan_out_analysts)

    # Analysts → join_analysts (barrier)
    graph.add_edge("analyze_competitor", "join_analysts")

    # Join → comparator → writer → end
    graph.add_edge("join_analysts", "comparator")
    graph.add_edge("comparator", "writer")
    graph.add_edge("writer", END)

    return graph.compile(checkpointer=checkpointer)
