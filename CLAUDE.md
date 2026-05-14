# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CompetitorScope is a multi-agent competitive analysis system using LangGraph-based workflow orchestration. The system orchestrates specialized agents via a state graph to produce competitive analysis reports.

**Current Status**: Step 7/8 主链路已收口，严格 E2E 9/9 + Transition/HITL 8/8 通过（截图 + 自判定）。
- Step 0-4: docs, scaffold, core models/tools, 5-agent serial pipeline ✅
- Step 5: Parallel fan-out via Send API ✅
- Step 6: HITL integration (interrupt/checkpoint, 3 interrupt types, CLI interactive) ✅
- Step 7: FastAPI API layer (SSE, HITL, reports/evidence endpoints, DELETE, deps, lifespan) ✅; SQLite/SQLModel schema/init exists, but active run state is still primarily `RUN_STORE`.
- Step 8: Next.js UI（Next rewrite, AgentFlow SSE, HITL dialogs, EvidencePanel, 三栏布局, API client）代码完成 ✅
- **验证**: `web/test_step7_8_regression.mjs` 9/9 通过；`web/test_transition_hitl_evidence.mjs` 8/8 通过，逐张覆盖 HITL 两次确认与 Planner→Collector→Analyst→Comparator→Writer handoff。证据在 `docs/review/step7-8/`。
- **HITL 完成态回归**: `web/test_hitl_done_guard.mjs` 验证 `done=true` 后即使 pending/SSE 返回 stale HITL，也不会重新弹窗。

`doc/memory-bank/progress.md` is the source of truth for current implementation status.
`doc/memory-bank/implementation-plan.md` is the source of truth for Step numbering.

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
    发现竞品      数据采集      结构化分析     横向对比    报告输出
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
| DELETE | `/api/v1/analysis/{run_id}` | Cancel analysis run |
| GET | `/api/v1/analysis/{run_id}/hitl/pending` | Get pending HITL request |
| POST | `/api/v1/analysis/{run_id}/hitl` | Resume paused HITL run |
| GET | `/api/v1/reports/{run_id}` | Get full report (markdown + bibliography) |
| GET | `/api/v1/reports/{run_id}/markdown` | Download report markdown |
| GET | `/api/v1/reports/{run_id}/evidence` | Get evidence chain |
| GET | `/api/v1/health` | Health check |

## MVP vs Future

**MVP (Current)**:
- 5 agents use LangGraph fan-out for collector/analyst paths, with HITL gates between major stages
- FastAPI API and Next.js UI cover the Step 7/8 main path
- HITL backend, CLI, SSE events, and frontend dialogs exist
- SQLite/SQLModel schema/init exists, but active API state and report/evidence reads still primarily use `RUN_STORE`
- Report quality: functional but citations need improvement

**Planned Enhancements**:
- Complete DB persistence for run/source/evidence records beyond current schema/init
- Production hardening for deployment URLs, auth, cancellation semantics, and replayable traces
- Better report citations with evidence chain

## Project Rules

1. 称呼规则： 每次回复前使用"maomao"作为称呼
2. 决策确认： 遇到不确定的代码设计，必须先询问maomao, 不可直接行动
3. 代码兼容： 不能写兼容性代码，除非主动要求
4. 完成一个功能/需求就commit，commit前和我确认一下，按照开源方式规范就好
5. 每次完成功能/需求 要更新状态，让后续agent在新上下文环境能够识别到进展。

## Testing & Verification

每次完成功能后，必须自行验证结果：

1. **网页应用**：用 Playwright 或 Chrome DevTools 打开验证
2. **有说服力的证明**：前端需要有截图/录屏等视觉证据，保存目录需要清晰，如 `docs/review/<feature>/...`
3. **严格人工判定**：截图只是证据，不是通过条件。必须逐张检查 URL、状态、文案、布局、弹窗、报告和证据链是否符合预期，确认后才能写 pass。

```markdown
docs/review/
├── step7-8/
└── ...
```

验证文档内容应包含：测试步骤、实际结果、截图链接或 base64 图像，以及人工判定结论。

## Lessons Learned (避免重蹈覆辙)

### CLAUDE.md 更新时必须避免的错误

1. **不要基于假设更新进度** — 必须读取 `doc/memory-bank/implementation-plan.md` 和 `doc/memory-bank/progress.md` 确认实际状态，不能凭记忆或猜测。
2. **Step 编号要对应实际任务** — Step 4 是串行管道，Step 5 是并发 fan-out，Step 6 才是 HITL。写错会导致 future session 得到错误的上下文。
3. **复述文档时保持准确** — 引述代码实现状态、验收标准、任务清单时，要对照原文，不能"大概差不多"。

### 其他工程教训

- LangGraph 的 `interrupt()` 只能在节点内部调用，不能替代条件边
- `operator.add` reducer 保证并发追加时数据不丢失，但前提是字段类型必须正确声明
- 大产物（raw_content）应落文件而不是放 state，避免 checkpoint 膨胀

## References

- Implementation plan: `doc/memory-bank/implementation-plan.md`
- Architecture diagrams: `doc/memory-bank/architecture.md`
- Progress tracking: `doc/memory-bank/progress.md`
