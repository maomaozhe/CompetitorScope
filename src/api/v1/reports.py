"""Reports API — query report and evidence."""

from fastapi import APIRouter, HTTPException

from src.api.v1.runtime import RUN_STORE
from src.graph.serialization import evidence_items, report as restore_report

router = APIRouter()


@router.get("/reports/{run_id}")
async def get_report(run_id: str):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    state = RUN_STORE[run_id]["state"]
    report = restore_report(state.get("report"))
    if not report:
        return {"status": "pending"}
    return {
        "report_id": report.report_id,
        "title": report.title,
        "markdown": report.content_markdown,
        "bibliography": report.bibliography,
    }


@router.get("/reports/{run_id}/evidence")
async def get_evidence(run_id: str):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Not found")
    evidence = evidence_items(RUN_STORE[run_id]["state"].get("evidence_items", []))
    return {"evidence": [item.model_dump(mode="json") for item in evidence]}
