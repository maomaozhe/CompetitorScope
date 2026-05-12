"""Domain models — all Pydantic schemas for the pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Raw data from Collector ──


class RawSource(BaseModel):
    source_id: str = Field(default_factory=_uuid)
    competitor_id: str
    url: str
    title: str | None = None
    raw_content: str  # cleaned text (truncated for state; full saved to file)
    source_type: str = "website"  # website | reddit | app_store | news
    search_query: str = ""
    retrieved_at: datetime = Field(default_factory=_now)


# ── Evidence from Analyst ──


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=_uuid)
    source_id: str
    source_url: str
    excerpt: str  # verbatim quote from the source
    extracted_fact: str  # one-sentence distilled fact
    fact_type: str = "feature"  # positioning | feature | pricing | review
    confidence: float = 0.8
    competitor_id: str


# ── Structured profile from Analyst ──


class Feature(BaseModel):
    name: str
    description: str
    evidence_id: str = ""


class PricingTier(BaseModel):
    tier_name: str
    price: str  # e.g. "$20/mo", "Free", "Contact sales"
    key_features: list[str] = Field(default_factory=list)
    evidence_id: str = ""


class CompetitorProfile(BaseModel):
    competitor_id: str
    name: str
    website: str = ""
    # Dimension 1: Positioning
    one_liner: str = ""
    target_audience: list[str] = Field(default_factory=list)
    core_scenarios: list[str] = Field(default_factory=list)
    market_position: str = ""
    # Dimension 2: Core features
    features: list[Feature] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    recent_updates: list[str] = Field(default_factory=list)
    tech_form: str = ""
    # Dimension 3: Pricing
    pricing_tiers: list[PricingTier] = Field(default_factory=list)
    pricing_strategy: str = ""
    # Dimension 4: User reviews
    positive_themes: list[str] = Field(default_factory=list)
    negative_themes: list[str] = Field(default_factory=list)
    review_summary: str = ""


# ── Comparison from Comparator ──


class ComparisonResult(BaseModel):
    feature_table: str = ""  # markdown table
    pricing_table: str = ""  # markdown table
    key_insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ── Final report from Writer ──


class Report(BaseModel):
    report_id: str = Field(default_factory=_uuid)
    title: str = ""
    executive_summary: str = ""
    content_markdown: str = ""
    bibliography: list[dict] = Field(default_factory=list)  # [{url, title}]
