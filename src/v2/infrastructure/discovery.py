"""Official-domain-scoped discovery adapter."""

from __future__ import annotations

from src.tools.web_search import search
from src.v2.domain.identifiers import url_has_official_authority
from src.v2.domain.models import OfficialPricingInput
from src.v2.ports import DiscoveryCandidate


class TavilyOfficialPricingDiscovery:
    version = "tavily-official-pricing.v1"

    def discover(self, request: OfficialPricingInput) -> list[DiscoveryCandidate]:
        query = f"site:{request.official_domain} pricing plans {request.competitor}"
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for item in search(query, max_results=8):
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if not url_has_official_authority(url, request.official_domain):
                continue
            seen.add(url)
            candidates.append(
                DiscoveryCandidate(
                    url=url,
                    title=str(item.get("title") or ""),
                    snippet=str(item.get("content") or ""),
                )
            )
        return candidates
