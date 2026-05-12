"""LangGraph workflow — serial MVP pipeline."""

from langgraph.graph import StateGraph, START, END

from src.graph.state import AnalysisState
from src.graph.nodes import planner, collector, analyst, comparator, writer


def build_workflow():
    graph = StateGraph(AnalysisState)

    # Nodes
    graph.add_node("planner", planner.planner_node)
    graph.add_node("collector", collector.collector_node)
    graph.add_node("analyst", analyst.analyst_node)
    graph.add_node("comparator", comparator.comparator_node)
    graph.add_node("writer", writer.writer_node)

    # Edges — linear pipeline
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "collector")
    graph.add_edge("collector", "analyst")
    graph.add_edge("analyst", "comparator")
    graph.add_edge("comparator", "writer")
    graph.add_edge("writer", END)

    return graph.compile()