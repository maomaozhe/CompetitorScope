# 进度追踪 (Progress)

> 最后更新：2026-05-13

---

## 当前状态

**里程碑 M3：Step 6 HITL 后端 + CLI — ✅ 已验证跑通**

Pipeline 全流程（Planner→HITL gates→Collector→Analyst→Comparator→Writer）实测通过：
- auto 模式真实跑通：3 家竞品，21 条原始数据，3 个结构化档案，报告输出成功
- 可观测 CLI 真实跑通：5 家竞品，37 条原始数据，5 个结构化档案，节点级日志输出成功
- interactive 模式 mock 验证通过：竞品确认、大纲确认、低 source 补充 3 类 interrupt 均可 resume

---

## 完成记录

### 2026-05-12 上午 — Step 0 文档落盘

| 文档 | 状态 | 说明 |
|------|------|------|
| `product-requirements.md` | ✅ 新建 | PRD：场景、维度、HITL 设计、Demo 剧本、成功标准 |
| `design-document.md` | ✅ 重写 | 5 Agent 架构、fan-out、HITL interrupt、新 State schema、前端设计 |
| `architecture.md` | ✅ 新建 | 系统全景图、Agent 通信图、数据流图、HITL 时序图、存储架构 |
| `tech-stack.md` | ✅ 重写 | 加 Next.js 前端、数据源策略、Anthropic 主力、Reddit API |
| `implementation-plan.md` | ✅ 重写 | 12 步计划对齐新架构，含 HITL/前端/Demo 打磨步骤 |
| `progress.md` | ✅ 新建 | 本文件 |

### 2026-05-12 — Step 1-5 MVP 代码

| 步骤 | 状态 | 说明 |
|------|------|------|
| Step 1 脚手架 | ✅ | pyproject.toml + 目录结构 + config + .env + Makefile |
| Step 2 数据模型 | ✅ | domain.py (RawSource/EvidenceItem/CompetitorProfile/Report 等) + AnalysisState + LLM factory |
| Step 3 工具层 | ✅ | web_search.py (Tavily) + web_scraper.py (httpx+readability) |
| Step 4 核心管道 | ✅ | 5 Agent prompts + nodes + workflow(串行) + run_local.py |
| Step 5 API+前端 | ✅ | FastAPI 端点 + Next.js 15 三栏布局 + AgentFlow + ReportView |

### 2026-05-12 — API 配置

| 服务 | 配置 | 状态 |
|------|------|------|
| LLM (Anthropic/MiniMax) | `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic/v1` | ✅ 已验证 |
| 搜索 (Tavily) | `TAVILY_API_KEY=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` | ✅ 已验证 |

### 2026-05-12 — Step 5 并发 Fan-out 调试记录

| 日期 | 问题 | 修复 | 耗时 |
|------|------|------|------|
| 2026-05-12 | Send API 并行写 `current_stage` → `InvalidUpdateError` | 移除 join 节点的 `current_stage` 写回 | ~2h |
| 2026-05-12 | N 个 collector 都触发 join_collectors → 5 并发写 LastValue | 加 `finished_collectors/analysts: Annotated[set, union]` track 完成 | ~1h |
| 2026-05-12 | `operator.add` 不支持 set 类型 | 自定义 `_union_sets` reducer | ~10min |
| 2026-05-12 | Planner LLM JSON 解析失败 → `KeyError: competitors` | 加 fallback 从 search results 提取竞品 | ~10min |
| 2026-05-12 | `workflow.stream` 不更新 input state | 改用 `workflow.invoke` 获取最终 state | ~30min |
| 2026-05-12 | `workflow.stream` 不发射 START 事件（只有 END） | 时钟计算错误，简化用 wall clock | ~30min |
| 2026-05-12 | `workflow.invoke` 在 `stream` 后重复执行 pipeline | 去掉重复 invoke，只用一次 | ~20min |
| 2026-05-12 | `MemorySaver` 无法序列化 Pydantic RawSource | 放弃 checkpoint 方案，简化为 invoke 单次执行 | ~1h |
| 2026-05-12 | `MemorySaver` + 并行 fan-out → `dictionary changed size during iteration` | 同上 | - |

### 2026-05-12 — Step 5 性能结果（7 竞品）

| 阶段 | 估算耗时 | 说明 |
|------|------|------|
| Planner | ~56s | LLM + Tavily 搜索 |
| Collectors（并行）| ~42s | 最慢 collector 耗时，并行 |
| Analysts（并行）| ~164s | 最慢 analyst 耗时，LLM 分析 |
| Comparator | ~54s | LLM 横向对比 |
| Writer | ~68s | LLM 生成报告 |
| **Wall Clock** | **~466s (~7.8min)** | 串行约 510s，提升有限（LLM 是瓶颈） |

**结论**：Collector 并行有效，但 LLM 调用（Planner/Analyst/Writer）必须串行等待真正瓶颈。并行收益在 collector 网络 IO。

### 2026-05-12 — Step 6 HITL 后端 + CLI

| 项目 | 状态 | 说明 |
|------|------|------|
| LangGraph interrupt/checkpoint | ✅ | `build_workflow(checkpointer=...)`，用 `thread_id=run_id` 暂停/恢复 |
| JSON-safe state | ✅ | `raw_sources`、`competitor_profiles`、`evidence_items`、`comparison_result`、`report` 在 state 中存 dict |
| Planner HITL | ✅ | `planner_discover` 竞品确认；`planner_outline` 大纲确认 |
| Collector HITL | ✅ | `join_collectors` 汇总低 source 竞品，支持补 URL、继续或跳过 |
| API HITL | ✅ | `GET /analysis/{run_id}/hitl/pending` + `POST /analysis/{run_id}/hitl` |
| SSE 事件 | ✅ | `hitl_request`、`hitl_resumed`、`hitl_timeout` 已加入后端事件流 |
| Follow-up API | ✅ | `POST /analysis/{run_id}/follow-up` 支持报告后追问补充 |
| CLI interactive | ✅ | 支持选择竞品、范围选择、手动新增竞品、确认/覆盖大纲、低 source 补充 |
| 可观测 CLI | ✅ | 节点级 logging + graph event 摘要，输出到 stdout 和 `output/run-*/log.txt` |
| 前端 HITL 弹窗 | ⏭️ | 留到 Step 8，只保留事件协议兼容 |

### 2026-05-12 — Step 6 验证记录

| 验证 | 状态 | 结果 |
|------|------|------|
| `uv run pytest` | ✅ | 4 passed |
| `uv run ruff check src scripts tests` | ✅ | passed |
| `uv run python -m compileall src scripts tests` | ✅ | passed |
| FastAPI mock smoke | ✅ | 创建 interactive run、3 次 pending/resume、最终报告获取通过 |
| CLI 真实 auto | ✅ | `output/run-b7da1b70/report.md`：3 competitors / 3 profiles / 21 sources |
| CLI 真实可观测 auto | ✅ | `output/run-d94173e0/report.md`：5 competitors / 5 profiles / 37 sources |

### 2026-05-13 — Step 7/8 收口 + SSE/HITL/Evidence 修复

| 项目 | 状态 | 说明 |
|------|------|------|
| SQLite + SQLModel schema/init | ⚠️ | `database.py`、`models/run.py`、`models/source.py` 已有；当前 API 运行态仍主要使用 `RUN_STORE` |
| DELETE /analysis/{id} | ✅ | interrupt thread + 清理 RUN_STORE + 队列 sentinel |
| API deps 依赖注入 | ✅ | `api/deps.py` |
| Next.js 三栏布局 | ✅ | AgentFlow + ReportView + EvidencePanel |
| Next rewrite | ✅ | `/api/v1/:path*` 统一代理到 FastAPI，首页 POST 不再依赖硬编码后端地址 |
| HITLDialog 组件 | ✅ | CompetitorConfirm / OutlineConfirm / CollectorSupplement；提交使用当前 `runId` |
| EvidencePanel 组件 | ✅ | complete 后拉取 evidence，右侧证据面板支持点击引用展开详情 |
| SSE streaming 后端 | ✅ | `astream` + `asyncio.Queue`，事件正确推送（agent_start/complete/ report_chunk） |
| SSE 实时渲染前端 | ✅ | named event 用 `addEventListener`，AgentFlow 可被 agent_start/complete 驱动 |
| E2E 截图自判定 | ✅ | `web/test_step7_8_regression.mjs` 9/9 通过，报告见 `docs/review/step7-8/2026-05-13-step7-8-regression.md` |

**SSE/HITL/Evidence 修复 (2026-05-13)**：

1. `web/src/hooks/useSSE.ts` — `es.onmessage` 只处理无类型的 SSE 消息。`event: agent_start` 需要 `es.addEventListener("agent_start", ...)` 而不是 `es.onagent_start`。修复：改用 `addEventListener()`。

2. `web/src/app/analysis/[id]/page.tsx` — `setRunId(id)` 在 render 阶段直接调用（非 useEffect），React 报错并拒绝渲染。修复：包在 `useEffect()` 里。

3. `web/src/hooks/useSSE.ts` — EventSource URL 是相对路径 `/api/v1/analysis/.../stream`，需要 Next rewrite 转发到 FastAPI。修复：`web/next.config.ts` 增加 rewrite，前端保留相对路径。

4. `web/src/components/HITLDialog.tsx` — 原先把 `interrupt_id` 当成 `run_id` 提交 HITL。修复：从 AnalysisContext 使用当前 `runId` 调用 `POST /analysis/{runId}/hitl`。

5. `web/src/hooks/useSSE.ts` — 原先未处理 HITL 和 Evidence 闭环。修复：监听 `hitl_request` / `hitl_resumed` / `hitl_timeout`，complete 后拉取 `/reports/{runId}/evidence`。

**历史 SSE E2E 测试结果：2/2 通过**
- `docs/review/step7-api/2026-05-13-sse-page-loaded.png` — Planner "运行中" / "生成大纲中..."
- `docs/review/step7-api/2026-05-13-sse-planner-complete.png` — "1/5 完成", Planner "完成", Collector "运行中"

**本轮收口验证**：`web/test_step7_8_regression.mjs` 9/9 通过；截图只作为证据，每项均由脚本 DOM/API 结果 + Codex 自判定结论确认。

---

### 2026-05-13 — 遗留 Issue（记录）

| Issue | 状态 | 说明 |
|-------|------|------|
| InputForm POST `/api/v1/analysis` 返回 404 | ✅ 已修 | Next rewrite 代理 `/api/v1/*` 到 FastAPI |
| HITL 前端提交使用错误 id | ✅ 已修 | `HITLDialog` 使用 context `runId`，不再使用 `interrupt_id` 作路径参数 |
| AgentFlow 只显示 Planner 实时更新 | ✅ 已修 | E2E 确认 AgentFlow 可推进到 Collector/后续完成状态 |
| 报告内容只在 isComplete=true 后显示 | ✅ 已澄清 | `ReportView` 收到 `reportContent` 即显示；当前后端仍是 writer 完成后一次性发完整 report_chunk，不是 token 级流式 |
| Evidence 引用下钻 | ✅ 已修 | complete 后拉取 evidence；E2E 确认报告完成且 evidence endpoint 返回 11 条 |

### 2026-05-12 — 调试修复记录

| 问题 | 修复 |
|------|------|
| LangGraph 缺少 `START` 边 | `workflow.py` 加 `graph.add_edge(START, "planner")` |
| LLM 返回 block-list 而非 string | `services/llm.py` 加 `extract_text()` / `extract_json()` |
| `collector_node` 是 async 但 graph 是 sync | 改为 sync 函数 + 同步调用 `scrape()` |
| `scrape()` 是 async httpx | 改为同步 `httpx.get()` |
| Planner 变量名 typo (`resp` vs `response`) | 已修复 |
| 报告引用格式 `[1]` 无证据支撑 | V2 问题（当前为 Markdown 引用） |
| MiniMax Anthropic base_url 带 `/v1` 导致 404 | `services/llm.py` 规范化 base URL，兼容 env 中包含 `/v1` |

---

## MVP 代码结构

```
src/
├── config.py                  # 环境变量 (含 MiniMax base_url)
├── main.py                    # FastAPI 入口
├── api/v1/
│   ├── analysis.py            # POST /analysis + GET /stream SSE
│   ├── reports.py
│   └── health.py
├── graph/
│   ├── state.py               # AnalysisState TypedDict
│   ├── workflow.py            # StateGraph 串行 pipeline
│   └── nodes/
│       ├── planner.py         # 🧭 需求解析 + 竞品发现 (Tavily)
│       ├── collector.py       # 🕷️ 搜索 + 抓取 (Tavily + httpx)
│       ├── analyst.py         # 📊 结构化提取 4 维度
│       ├── comparator.py      # 🆚 横向对比表 + 洞察
│       └── writer.py          # ✍️ Markdown 报告
├── schemas/domain.py          # 所有 Pydantic 模型
├── services/llm.py            # Anthropic LLM 工厂 (base_url 可配置,含 extract_json)
├── tools/
│   ├── web_search.py          # Tavily 封装
│   └── web_scraper.py         # httpx + readability (同步)
└── prompts/                   # 5 个 Agent System Prompt

web/                          # Next.js 15 前端
├── src/app/
│   ├── page.tsx              # 首页：渐变背景 + InputForm
│   └── analysis/[id]/page.tsx  # 三栏布局
├── components/
│   ├── InputForm.tsx        # 深色玻璃态输入框
│   ├── AgentFlow.tsx        # 🧭🕷️📊🆚✍️ 实时进度流
│   └── ReportView.tsx       # Markdown 渲染 + 引用锚点
├── contexts/AnalysisContext.tsx
└── hooks/useSSE.ts
```

---

## 待办与风险追踪

| 风险 | 状态 | 对策 |
|------|------|------|
| 单次 pipeline > 5 分钟 | ⚠️ 真实约 5 分钟（LLM 延迟） | 后续做批量 Analyst、去掉 Collector LLM |
| LangGraph Send API + interrupt 组合未验证 | ✅ 已验证 | Step 6 采用汇总 gate，避免并行 collector 内 interrupt |
| 前端开发耗时 | ⚠️ 待评估 | 降级方案：Streamlit 替代 |
| Demo 网络不稳定 | ⚠️ 待准备 | 预录 trace 回放兜底 |
| Tavily 限流 | ⚠️ 潜在 | 缓存 + fallback SerpAPI |
