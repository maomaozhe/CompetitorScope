"""Reports API — query report and evidence."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/reports/{run_id}")
async def get_report(run_id: str):
    # Placeholder — real implementation uses DB
    return {"status": "pending"}


@router.get("/reports/{run_id}/evidence")
async def get_evidence(run_id: str):
    return {"status": "pending"}