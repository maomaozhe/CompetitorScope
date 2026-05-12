"""Web scraper — httpx + readability for clean text extraction."""

import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 15.0
_MAX_CONTENT_LEN = 8000


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def scrape(url: str) -> dict:
    """Fetch URL and extract clean text. Returns {url, title, content}."""
    resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()

    from readability import Document

    doc = Document(resp.text)
    title = doc.title() or ""
    content = re.sub(r"<[^>]+>", " ", doc.summary())
    content = re.sub(r"\s+", " ", content).strip()

    if len(content) > _MAX_CONTENT_LEN:
        content = content[:_MAX_CONTENT_LEN] + "..."

    return {"url": url, "title": title, "content": content}