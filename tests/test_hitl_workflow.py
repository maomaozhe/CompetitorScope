import json
from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import src.graph.nodes.analyst as analyst
import src.graph.nodes.collector as collector
import src.graph.nodes.comparator as comparator
import src.graph.nodes.planner as planner
import src.graph.nodes.writer as writer
from src.api.v1.runtime import initial_state
from src.graph.workflow import build_workflow
from scripts.run_local import _looks_like_competitor_selection, _parse_competitor_selection


class MockLLM:
    def __init__(self, role: str):
        self.role = role

    def invoke(self, messages):
        if self.role == "planner":
            return SimpleNamespace(content=json.dumps({
                "competitors": [
                    {"name": "Alpha", "website": "https://alpha.example"},
                    {"name": "Beta", "website": "https://beta.example"},
                ],
                "dimensions": ["features"],
                "outline": "# Outline",
            }))
        if self.role == "collector":
            return SimpleNamespace(content=json.dumps({"queries": [{"query": "alpha beta"}]}))
        if self.role == "analyst":
            return SimpleNamespace(content=json.dumps({
                "one_liner": "AI coding tool",
                "target_audience": ["developers"],
                "core_scenarios": ["coding"],
                "market_position": "developer productivity",
                "features": [{"name": "Autocomplete", "description": "Suggests code"}],
                "differentiators": ["fast"],
                "recent_updates": [],
                "tech_form": "IDE",
                "pricing_tiers": [{"tier_name": "Free", "price": "$0", "key_features": ["basic"]}],
                "pricing_strategy": "freemium",
                "positive_themes": ["useful"],
                "negative_themes": ["limited"],
                "review_summary": "Generally useful",
                "evidence": [{
                    "source_url": "https://source.example",
                    "excerpt": "quote",
                    "extracted_fact": "fact",
                    "fact_type": "feature",
                }],
            }))
        if self.role == "comparator":
            return SimpleNamespace(content=json.dumps({
                "feature_table": "| Feature |",
                "pricing_table": "| Pricing |",
                "key_insights": ["insight"],
                "recommendations": ["recommendation"],
            }))
        return SimpleNamespace(content="Final report")


def _patch_external_services(monkeypatch, *, scrape_count: int = 2):
    def get_llm(role: str, **kwargs):
        return MockLLM(role)

    def search(query: str, max_results: int = 5):
        return [
            {"title": "Alpha", "url": "https://alpha.example", "content": "alpha"},
            {"title": "Beta", "url": "https://beta.example", "content": "beta"},
            {"title": "Gamma", "url": "https://gamma.example", "content": "gamma"},
        ][:max_results]

    def scrape(url: str):
        return {"url": url, "title": url, "content": "raw content"}

    monkeypatch.setattr(planner, "get_llm", get_llm)
    monkeypatch.setattr(planner, "search", search)
    monkeypatch.setattr(collector, "get_llm", get_llm)
    monkeypatch.setattr(collector, "search", lambda query, max_results=5: search(query, scrape_count))
    monkeypatch.setattr(collector, "scrape", scrape)
    monkeypatch.setattr(analyst, "get_llm", get_llm)
    monkeypatch.setattr(comparator, "get_llm", get_llm)
    monkeypatch.setattr(writer, "get_llm", get_llm)


def test_auto_mode_completes_without_interrupt(monkeypatch):
    _patch_external_services(monkeypatch, scrape_count=3)
    workflow = build_workflow(checkpointer=MemorySaver())
    state = initial_state(run_id="auto-test", query="AI IDE", hitl_mode="auto")

    events = list(workflow.stream(state, config={"configurable": {"thread_id": "auto-test"}}))
    result = workflow.get_state({"configurable": {"thread_id": "auto-test"}}).values

    assert all("__interrupt__" not in event for event in events)
    assert result["current_stage"] == "complete"
    assert result["report"]["content_markdown"] == "Final report"
    assert isinstance(result["raw_sources"][0], dict)


def test_interactive_mode_resumes_three_hitl_gates(monkeypatch):
    _patch_external_services(monkeypatch, scrape_count=2)
    workflow = build_workflow(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "interactive-test"}}
    state = initial_state(run_id="interactive-test", query="AI IDE", hitl_mode="interactive")

    first = next(iter(workflow.stream(state, config=config)))
    assert first["__interrupt__"][0].value["type"] == "competitor_confirm"

    events = workflow.stream(
        Command(resume={"competitors": [{"name": "Alpha", "website": "https://alpha.example"}]}),
        config=config,
    )
    second_interrupt = [event for event in events if "__interrupt__" in event][0]
    assert second_interrupt["__interrupt__"][0].value["type"] == "outline_confirm"

    events = workflow.stream(Command(resume={"outline": "# Confirmed", "dimensions": ["features"]}), config=config)
    third_interrupt = [event for event in events if "__interrupt__" in event][0]
    assert third_interrupt["__interrupt__"][0].value["type"] == "collector_supplement"

    list(workflow.stream(Command(resume={"action": "continue"}), config=config))
    result = workflow.get_state(config).values

    assert result["current_stage"] == "complete"
    assert [item["type"] for item in result["hitl_history"]] == [
        "competitor_confirm",
        "outline_confirm",
        "collector_supplement",
    ]


def test_cli_competitor_selection_supports_ranges_and_custom_additions():
    candidates = [
        {"name": "Cursor", "website": "https://cursor.com"},
        {"name": "Windsurf", "website": "https://windsurf.com"},
        {"name": "Copilot", "website": "https://github.com/features/copilot"},
    ]

    selected = _parse_competitor_selection(
        "1-2,+Claude Code|https://claude.ai/code,2",
        candidates,
    )

    assert selected == [
        {"name": "Cursor", "website": "https://cursor.com"},
        {"name": "Windsurf", "website": "https://windsurf.com"},
        {"name": "Claude Code", "website": "https://claude.ai/code"},
    ]


def test_cli_outline_prompt_can_detect_competitor_selection_text():
    assert _looks_like_competitor_selection("我只需要前三家")
    assert not _looks_like_competitor_selection("# 竞品分析报告\n## 产品定位")


def test_writer_formats_structured_comparison_values(monkeypatch):
    captured = {}

    class CapturingWriterLLM:
        def invoke(self, messages):
            captured["prompt"] = messages[-1].content
            return SimpleNamespace(content="Final report without object marker")

    monkeypatch.setattr(writer, "get_llm", lambda role: CapturingWriterLLM())

    state = {
        "run_id": "writer-format-test",
        "query": "AI IDE",
        "report_outline": "# Outline",
        "competitor_profiles": [{
            "competitor_id": "alpha",
            "name": "Alpha",
            "website": "https://alpha.example",
            "one_liner": "AI coding tool",
            "target_audience": ["developers"],
            "core_scenarios": ["coding"],
            "market_position": "developer productivity",
            "features": [{"name": "Autocomplete", "description": "Suggests code"}],
            "differentiators": ["fast"],
            "recent_updates": [],
            "tech_form": "IDE",
            "pricing_tiers": [{
                "tier_name": "Free",
                "price": "$0",
                "key_features": ["basic"],
            }],
            "pricing_strategy": "freemium",
            "positive_themes": ["useful"],
            "negative_themes": ["limited"],
            "review_summary": "Generally useful",
        }],
        "evidence_items": [{
            "source_id": "source-1",
            "source_url": "https://source.example",
            "excerpt": "quote",
            "extracted_fact": "fact",
            "fact_type": "feature",
            "competitor_id": "alpha",
        }],
        "comparison_result": {
            "feature_table": [{"feature": "Autocomplete", "alpha": "yes"}],
            "pricing_table": {"free": "$0"},
            "key_insights": [{"insight": "Alpha has a free tier"}],
            "recommendations": ["Prioritize pricing review"],
        },
    }

    result = writer.writer_node(state)

    assert result["report"]["content_markdown"] == "Final report without object marker"
    assert '"feature": "Autocomplete"' in captured["prompt"]
    assert '"free": "$0"' in captured["prompt"]
