"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.api.v1.runtime import RUN_STORE
from src.models.run import AnalysisRun
from src.services.database import get_db_session


async def get_db() -> AsyncSession:
    """DB session dependency."""
    async with get_db_session() as session:
        yield session


async def get_run_record(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisRun | None:
    """Load an AnalysisRun from DB; returns None if not yet persisted."""
    result = await db.execute(select(AnalysisRun).where(AnalysisRun.run_id == run_id))
    return result.scalar_one_or_none()


async def cancel_run_in_store(run_id: str) -> None:
    """Mark run as cancelled in RUN_STORE and DB."""
    if run_id in RUN_STORE:
        RUN_STORE[run_id]["done"] = True
        RUN_STORE[run_id]["pending_interrupt"] = None
    # DB update
    # (handled in endpoint with get_db_session)


DB = Annotated[AsyncSession, Depends(get_db)]
