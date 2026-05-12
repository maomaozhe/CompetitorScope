"""Human-in-the-loop API for paused analysis runs."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.runtime import RUN_STORE, resume_run
from src.graph.serialization import dump_model, report as restore_report
from src.services.llm import extract_text, get_llm
from src.tools.web_scraper import scrape
from src.tools.web_search import search

router = APIRouter()


class HitlResumeRequest(BaseModel):
    response: dict = Field(default_factory=dict)


class FollowUpRequest(BaseModel):
    question: str
    target: str | None = None
    urls: list[str] = Field(default_factory=list)


@router.get("/analysis/{run_id}/hitl/pending")
async def get_pending_hitl(run_id: str):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Run not found")
    pending = RUN_STORE[run_id].get("pending_interrupt")
    if not pending:
        return {"pending": False}
    return {"pending": True, **pending}


@router.post("/analysis/{run_id}/hitl")
async def resume_hitl(run_id: str, req: HitlResumeRequest, background_tasks: BackgroundTasks):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Run not found")
    if not RUN_STORE[run_id].get("pending_interrupt"):
        raise HTTPException(409, "Run is not waiting for HITL input")
    background_tasks.add_task(resume_run, run_id, req.response)
    return {"run_id": run_id, "status": "resuming"}


@router.post("/analysis/{run_id}/follow-up")
async def report_follow_up(run_id: str, req: FollowUpRequest):
    if run_id not in RUN_STORE:
        raise HTTPException(404, "Run not found")

    state = RUN_STORE[run_id]["state"]
    current_report = restore_report(state.get("report"))
    if not current_report:
        raise HTTPException(409, "Report is not ready")

    urls = req.urls[:5]
    if not urls:
        results = search(f"{req.target or state.get('query', '')} {req.question}", max_results=5)
        urls = [item["url"] for item in results[:5]]

    source_blocks = []
    bibliography = list(current_report.bibliography)
    seen_urls = {item.get("url") for item in bibliography}
    for url in urls:
        try:
            scraped = scrape(url)
        except Exception:
            continue
        source_blocks.append(f"[Source: {scraped['url']}]\n{scraped['content'][:3000]}")
        if scraped["url"] not in seen_urls:
            bibliography.append({"url": scraped["url"], "title": scraped.get("title") or scraped["url"]})
            seen_urls.add(scraped["url"])

    llm = get_llm("writer")
    response = llm.invoke(
        "请基于已有竞品分析报告和补充资料，回答用户追问并生成可追加到报告末尾的 Markdown。\n\n"
        f"用户追问: {req.question}\n"
        f"关注对象: {req.target or '不限'}\n\n"
        f"已有报告:\n{current_report.content_markdown[:6000]}\n\n"
        f"补充资料:\n{chr(10).join(source_blocks)}"
    )
    appendix = extract_text(response.content)
    current_report.content_markdown = (
        f"{current_report.content_markdown.rstrip()}\n\n"
        f"## 补充追问: {req.question}\n\n"
        f"{appendix.strip()}\n"
    )
    current_report.bibliography = bibliography
    state["report"] = dump_model(current_report)
    RUN_STORE[run_id]["state"] = state
    return {"run_id": run_id, "markdown": appendix, "bibliography": bibliography}
