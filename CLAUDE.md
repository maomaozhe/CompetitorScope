# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CompetitorScope is a multi-agent competitive analysis system using LangGraph-based workflow orchestration. The system orchestrates specialized agents via a state graph to produce competitive analysis reports.

**Current Status**: Step 6 HITL + CLI verified.
- Step 0-4: docs, scaffold, core models/tools, 5-agent serial pipeline ✅
- Step 5: Parallel fan-out via Send API ✅
- Step 6: HITL integration (interrupt/checkpoint, 3 interrupt types, CLI interactive) ✅
- Step 7+: FastAPI hardening, persistent storage, evidence-grade citations ❌

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
| GET | `/api/v1/reports/{run_id}` | Get full report (markdown + bibliography) |
| GET | `/api/v1/health` | Health check |

## MVP vs Future

**MVP (Current)**:
- 5 agents run in **serial** (not parallel)
- Basic FastAPI API and Next.js UI exist, but they are MVP-level and not the full Step 7/8 target
- No HITL (Human-In-The-Loop) interruptions
- In-memory run store (no persistent DB)
- Report quality: functional but citations need improvement

**Planned Enhancements**:
- Step 5: Parallel fan-out (Collector×N, Analyst×N concurrently via Send API)
- Step 6: HITL with 4 interrupt points (competitor confirm, outline confirm, data supplement, writer follow-up)
- Step 7/8 hardening: full API surface, evidence endpoints, robust SSE mapping, production-quality UI states
- Better report citations with evidence chain
- Persistent storage (SQLModel + SQLite)

## Project Rules

1. 称呼规则： 每次回复前使用"maomao"作为称呼
2. 决策确认： 遇到不确定的代码设计，必须先询问maomao, 不可直接行动
3. 代码兼容： 不能写兼容性代码，除非主动要求
4. 完成一个功能就，commit，按照开源方式规范就好

## Lessons Learned (避免重蹈覆辙)

### CLAUDE.md 更新时必须避免的错误

1. **不要基于假设更新进度** — 必须读取 `doc/memory-bank/implementation-plan.md` 和 `doc/memory-bank/progress.md` 确认实际状态，不能凭记忆或猜测。
2. **Step 编号要对应实际任务** — Step 4 是串行管道，Step 5 是并发 fan-out，Step 6 才是 HITL。写错会导致 future session 得到错误的上下文。
3. **复述文档时保持准确** — 引述代码实现状态、验收标准、任务清单时，要对照原文，不能"大概差不多"。

### 其他工程教训

- LangGraph 的 `interrupt()` 只能在节点内部调用，不能替代条件边
- `operator.add` reducer 保证并发追加时数据不丢失，但前提是字段类型必须正确声明
- 大产物（raw_content）应落文件而不是放 state，避免 checkpoint 膨胀

### Step 5 Fan-out 实现教训

1. **并发不一定省时间** — 当 LLM 调用是主要瓶颈（Planner/Analyst/Writer），真正的并行收益只在 Collector 的 IO 操作（网络抓取）。Planner/Analyst 的 LLM 调用必须等前一步完成，并发收益有限。

2. **Send API 与 add_edge 混用有坑** — Send 启动的 N 个节点，每个都通过 `add_edge(node, join)` 触发 join 节点 → N 个 join 并发执行，同时写 `current_stage`（LastValue channel）→ `InvalidUpdateError`。解法：用 set union reducer + `add_conditional_edges` 路由，或 Send 汇合用单独 join 节点。

3. **`operator.add` 不支持 set** — 集合并发写要用自定义 reducer：
   ```python
   def _union_sets(a, b): return (a or set()) | (b or set())
   finished_collectors: Annotated[set[str], _union_sets]
   ```

4. **测试周期太长** — 每次端到端运行 ~12min（LLM 慢），导致迭代成本高。需要在 `scripts/` 下建立 `test_fan_out_small.py` 用 mock LLM + 假数据快速验证逻辑，再跑真实 Pipeline。

5. **`stream_output=["all"]` 不返回 START 事件** — 用 `workflow.invoke`（返回最终 state）做端到端，用 `workflow.stream` 逐节点观察状态更新，不要混用。

### Step 6 HITL 实现教训

1. **MemorySaver 无法序列化 Pydantic model** — 解法：在写入 state 前 `model → dict`（`dump_model`），读出时 `dict → model`（`restore_*` helpers）。见 `src/graph/serialization.py`。

2. **Interrupt 只在节点内部调用** — 不能在 conditional edge 函数里调用 interrupt，必须在 node 函数里。

3. **Planner 两阶段拆分** — `planner_discover`（竞品发现+HITL确认）和 `planner_outline`（大纲生成+HITL确认）串行，用 `add_edge` 连接。

4. **Collector 并行内的 interrupt** — 避免在 Send fan-out 内部 interrupt，改为 join 节点统一处理（汇总低 source 竞品后一次性 interrupt）。

## References

- Implementation plan: `doc/memory-bank/implementation-plan.md`
- Architecture diagrams: `doc/memory-bank/architecture.md`
- Progress tracking: `doc/memory-bank/progress.md`
