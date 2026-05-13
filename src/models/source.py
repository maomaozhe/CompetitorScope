"""Raw source and evidence records persisted to SQLite."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class RawSourceRecord(SQLModel, table=True):
    """Persisted raw source from collector."""

    __tablename__ = "raw_sources"

    source_id: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    competitor_id: str = Field(index=True)
    url: str
    title: str = ""
    raw_content: str = ""
    source_type: str = "website"
    search_query: str = ""
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceRecord(SQLModel, table=True):
    """Persisted evidence item from analyst."""

    __tablename__ = "evidence_items"

    evidence_id: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    source_id: str = Field(index=True)
    source_url: str = ""
    excerpt: str = ""
    extracted_fact: str = ""
    fact_type: str = "feature"
    confidence: float = 0.8
    competitor_id: str = Field(index=True)


class CompetitorProfileRecord(SQLModel, table=True):
    """Persisted competitor profile (denormalized JSON blob)."""

    __tablename__ = "competitor_profiles"

    competitor_id: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    name: str = ""
    website: str = ""
    profile_json: str = "{}"  # full CompetitorProfile as JSON


class HITLHistoryRecord(SQLModel, table=True):
    """Persisted HITL interrupt history."""

    __tablename__ = "hitl_history"

    id: int = Field(primary_key=True, autoincrement=True)
    run_id: str = Field(index=True)
    interrupt_type: str = ""  # competitor_confirm | outline_confirm | collector_supplement
    interrupt_payload: str = "{}"  # JSON
    user_response: str = "{}"  # JSON
    responded_at: datetime | None = None
