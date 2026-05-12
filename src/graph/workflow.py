"""LangGraph workflow — parallel fan-out MVP pipeline."""

from langgraph.graph import StateGraph, START, END

from src.graph.state import AnalysisState
from src.graph.nodes import planner, collector, analyst, comparator, writer


def build_workflow(checkpointer=None):
    graph = StateGraph(AnalysisState)

    # Nodes
    graph.add_node("planner_discover", planner.planner_discover)
    graph.add_node("planner_outline", planner.planner_outline)
    graph.add_node("collect_competitor", collector.collect_competitor)
    graph.add_node("join_collectors", collector.join_collectors)
    graph.add_node("analyze_competitor", analyst.analyze_competitor)
    graph.add_node("join_analysts", analyst.join_analysts)
    graph.add_node("comparator", comparator.comparator_node)
    graph.add_node("writer", writer.writer_node)

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
