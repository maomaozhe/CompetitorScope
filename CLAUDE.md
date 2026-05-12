# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CompetitorScope is a multi-agent competitive analysis system using LangGraph-based workflow orchestration. The system orchestrates specialized agents via a state graph to produce competitive analysis reports.

**Current Status**: MVP verified (Step 0-5 complete). Step 6+ (HITL, fan-out, etc.) pending implementation.

## Project Architecture

### Backend (`src/`) — Python/FastAPI + LangGraph

```
src/
├── main.py                    # FastAPI app entry point
├── config.py                  # Pydantic Settings (env vars + model configs)
├── api/v1/
│   ├── analysis.py            # POST /analysis, GET /stream (SSE), GET /{id}, DELETE
│   ├── reports.py             # GET /reports/{id}
│   └── health.py              # Health check
├── graph/
│   ├── state.py               # AnalysisState TypedDict (shared blackboard)
│   ├── workflow.py            # StateGraph builder (5 agents in sequence)
│   └── nodes/
│       ├── planner.py         # 🧭 Discover competitors via Tavily, generate outline
│       ├── collector.py       # 🕷️ Search + scrape competitor websites
│       ├── analyst.py         # 📊 Structured extraction (4 dimensions)
│       ├── comparator.py      # 🆚 Cross-competitor comparison table
│       └── writer.py          # ✍️ Markdown report generation
├── schemas/domain.py          # Pydantic models: RawSource, EvidenceItem, CompetitorProfile, Report, ComparisonResult
├── services/llm.py            # Anthropic LLM factory (configurable base_url)
├── tools/
│   ├── web_search.py          # Tavily wrapper: search(query, max_results) → [{title, url, content, score}]
│   └── web_scraper.py         # httpx + readability: scrape(url) → {url, title, content}
└── prompts/                   # System prompts for each agent
```

### Frontend (`web/`) — Next.js application

## LangGraph Pipeline (5-Agent Sequence)

```
START → Planner → Collector → Analyst → Comparator → Writer → END
         │          │           │          │          │
         ▼          ▼           ▼          ▼          ▼
    发现竞品      并发采集      并发分析     横向对比    报告输出
    生成大纲      (当前串行)    (当前串行)   洞察提炼    (Markdown)
```

**Data Flow**:
1. `query` → Planner discovers competitors via Tavily search → `confirmed_competitors`, `analysis_dimensions`, `report_outline`
2. `confirmed_competitors` → Collector scrapes each competitor's data → `raw_sources` (append via `operator.add`)
3. `raw_sources` → Analyst extracts structured profiles per competitor → `competitor_profiles`, `evidence_items` (append)
4. `competitor_profiles` + `evidence_items` → Comparator produces `comparison_result`
5. `comparison_result` + `report_outline` → Writer generates final `report`

## AnalysisState Structure

The shared blackboard passed through all pipeline nodes:

```python
class AnalysisState(TypedDict, total=False):
    # Run metadata
    run_id: str
    query: str

    # Planner outputs
    confirmed_competitors: list[dict]  # [{name, website}]
    analysis_dimensions: list[str]
    report_outline: str

    # Flow control
    current_stage: Literal["planning", "collecting", "analyzing", "comparing", "writing", "complete", "error"]
    stage_status: str
    error_message: str | None

    # Append-only lists (use operator.add reducer for thread-safety)
    raw_sources: Annotated[list[RawSource], operator.add]
    competitor_profiles: Annotated[list[CompetitorProfile], operator.add]
    evidence_items: Annotated[list[EvidenceItem], operator.add]

    # Single outputs
    comparison_result: ComparisonResult | None
    report: Report | None
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/analysis` | Create new analysis run (background task) |
| GET | `/api/v1/analysis/{run_id}/stream` | SSE stream for real-time agent progress |
| GET | `/api/v1/analysis/{run_id}` | Get analysis status |
| GET | `/api/v1/reports/{run_id}` | Get full report (markdown + bibliography) |
| GET | `/api/v1/health` | Health check |

## MVP vs Future (Step 6+)

**MVP (Current)**:
- 5 agents run in **serial** (not parallel)
- No HITL (Human-In-The-Loop) interruptions
- In-memory run store (no persistent DB)
- Report quality: functional but citations need improvement

**Planned Enhancements**:
- Step 6: HITL with 4 interrupt points (competitor confirm, outline confirm, data supplement, writer follow-up)
- Step 5: Parallel fan-out (Collector×N, Analyst×N concurrently)
- Better report citations with evidence chain
- Persistent storage (SQLModel + SQLite)

## Project Rules

1. 称呼规则： 每次回复前使用"maomao"作为称呼
2. 决策确认： 遇到不确定的代码设计，必须先询问maomao, 不可直接行动
3. 代码兼容： 不能写兼容性代码，除非主动要求
4. 完成一个功能就，commit，按照开源方式规范就好

## References

- Implementation plan: `doc/memory-bank/implementation-plan.md`
- Architecture diagrams: `doc/memory-bank/architecture.md`
- Progress tracking: `doc/memory-bank/progress.md`