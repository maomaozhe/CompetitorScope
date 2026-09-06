"""HTTP source fetcher that returns bytes without interpreting claims."""

from __future__ import annotations

import re

import httpx

from src.v2.ports import FetchedResource


_CANONICAL_RE = re.compile(
    rb"<link[^>]+rel=[\"'][^\"']*canonical[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


class HttpSourceFetcher:
    version = "httpx-fetcher.v1"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch(self, url: str, *, locale: str) -> FetchedResource:
        headers = {
            "User-Agent": "CompetitorScope-V2/0.1 pricing-evidence",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
        }
        if locale != "und":
            headers["Accept-Language"] = locale
        response = httpx.get(
            url,
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        canonical_url = None
        match = _CANONICAL_RE.search(response.content)
        if match:
            canonical_url = match.group(1).decode("utf-8", errors="replace")
        return FetchedResource(
            requested_url=url,
            final_url=str(response.url),
            http_status=response.status_code,
            media_type=media_type,
            content=response.content,
            canonical_url=canonical_url,
        )
