from types import SimpleNamespace

import src.services.llm as llm_service
import src.tools.web_scraper as web_scraper
import src.tools.web_search as web_search
from src.graph.runtime_events import reset_event_emitter, set_event_emitter


def test_llm_wrapper_emits_request_and_response(monkeypatch):
    events = []

    class FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return SimpleNamespace(content="answer", usage_metadata={"input_tokens": 4, "output_tokens": 2})

    monkeypatch.setattr(llm_service, "ChatAnthropic", FakeChatModel)
    token = set_event_emitter(lambda event, data: events.append((event, data)))
    try:
        response = llm_service.get_llm("planner").invoke([SimpleNamespace(content="question")])
    finally:
        reset_event_emitter(token)

    assert response.content == "answer"
    assert [event for event, _ in events] == ["llm.requested", "llm.completed"]
    assert events[0][1]["role"] == "planner"
    assert events[1][1]["usage"]["input_tokens"] == 4


def test_search_and_scrape_emit_tool_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        web_search,
        "_get_client",
        lambda: SimpleNamespace(search=lambda query, max_results: {"results": [{"url": "https://example.com"}]}),
    )
    monkeypatch.setattr(
        web_scraper.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            text="<html><title>Example</title><body>content</body></html>",
            raise_for_status=lambda: None,
        ),
    )
    token = set_event_emitter(lambda event, data: events.append((event, data)))
    try:
        assert web_search.search("example", max_results=1)[0]["url"] == "https://example.com"
        assert web_scraper.scrape("https://example.com")["url"] == "https://example.com"
    finally:
        reset_event_emitter(token)

    assert [event for event, _ in events] == [
        "tool.requested", "tool.completed", "tool.requested", "tool.completed"
    ]
    assert events[1][1]["tool"] == "web_search"
    assert events[3][1]["tool"] == "web_scrape"
