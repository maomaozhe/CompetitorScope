"""Tavily search wrapper with retry."""

from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def search(query: str, max_results: int = 5) -> list[dict]:
    """Search via Tavily. Returns list of {title, url, content, score}."""
    client = _get_client()
    response = client.search(query, max_results=max_results)
    return response.get("results", [])
