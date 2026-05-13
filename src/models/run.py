"""Analysis run — persisted to SQLite via SQLModel."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"  # waiting for HITL
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisRun(SQLModel, table=True):
    """Persisted record for each analysis run."""

    __tablename__ = "analysis_runs"

    run_id: str = Field(primary_key=True)
    query: str
    hitl_mode: str = "auto"
    status: str = Field(default=RunStatus.RUNNING.value)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Key outputs (JSON stored as text)
    confirmed_competitors: str = "[]"  # JSON list
    report_outline: str = ""
    report_content: str = ""  # markdown
    comparison_result: str = "{}"  # JSON
