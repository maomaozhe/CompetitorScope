# TODO

> 优化项，待后续处理。

---

## Step 6 HITL 已完成

- ✅ LangGraph interrupt/checkpoint with MemorySaver
- ✅ JSON-safe state（dump_model / restore helpers）
- ✅ Planner两阶段：discover → outline，各带HITL确认
- ✅ Collector HITL：低source竞品可补充URL/跳过
- ✅ API HITL：pending + resume + follow-up 端点
- ✅ SSE事件：hitl_request / hitl_resumed / hitl_timeout
- ✅ CLI interactive模式：支持竞品选择、大纲确认、source补充
- ✅ 前端HITL弹窗：Step 8 已接入 SSE `hitl_request`，提交使用当前 run id

---

## 可视化追踪（Agent 流程监控）

**问题**：已能通过 SSE 看到 Agent start/complete，但细粒度过程、阶段耗时和数据量变化还不完整。

**目标**：前端点击分析任务，实时看到每个 Agent 的工作状态、流转、耗时。

**后端需求**：

1. `workflow.astream`/event stream 实时推送每个节点的 start/end 事件
2. 每个节点内部加细粒度进度（如 Collector 开始抓取、开始分析等）
3. SSE 端点 `GET /api/v1/analysis/{id}/stream` 把事件实时推送

**前端需求**：

1. AgentFlow 组件 — 实时显示 Planner → Collector → Analyst → Comparator → Writer 的状态
2. 状态：pending（灰色）/ running（蓝色动画）/ done（绿色）/ error（红色）
3. 每个节点显示耗时（如 `Collector 42s`）
4. 数据量变化（如 `Sources: 0 → 12 → 35`）

**状态**：Agent start/complete 与前端渲染已完成并通过 E2E；剩余为细粒度进度、耗时统计和数据量变化。

**2026-05-13 补充**：已增加 agent 状态快照兜底同步，并通过 `web/test_transition_hitl_evidence.mjs` 截图验证 Planner→Collector→Analyst→Comparator→Writer 每个 handoff 中间态。

---

## 报告内容质量

**问题**：真实最终报告中曾偶现 `[object Object]`，说明 Writer 输入上下文和前端 Markdown children 渲染都可能把对象结构错误字符串化。

**证据**：`docs/review/step7-8/2026-05-13-transition-05-final-5-of-5-report.png`

**状态**：✅ 已修（2026-05-14）。

**修复**：
- `src/graph/nodes/writer.py`：Writer prompt 输入增加结构化值文本化，dict/list/Pydantic 值统一转成可读文本，避免对象值进入最终报告上下文。
- `web/src/components/ReportView.tsx`：引用渲染不再对 ReactMarkdown children 使用 `String(children)`，改为递归处理文本节点；接入 `remark-gfm` 并保留真实 `<table>` DOM，修复 Markdown 表格被当普通段落渲染的问题。
- `tests/test_hitl_workflow.py`：新增 Writer structured comparison 回归测试。
- `web/test_report_rendering_guard.mjs`：新增前端渲染 guard，验证报告不含 `[object Object]`、`[1]` 引用按钮可点击并打开证据详情、GFM table 正确渲染为 `<table>`。

**验证**：
- `uv run pytest tests -q` → 5 passed
- `uv run ruff check src tests scripts` → passed
- `npm run lint` → passed
- `npm run build` → passed
- `node web/test_report_rendering_guard.mjs` → passed，截图：`docs/review/step7-8/2026-05-14-report-rendering-guard.png`

---

## Step 5 性能优化（可选）

**问题**：7 竞品端到端 ~466s（~7.8min），主要瓶颈是 17 次 LLM 串行调用。

**优化方向**：

1. **批量 Analyst** — 1 次 LLM 调用分析所有竞品
2. **去掉 Collector 的 LLM** — 直接用规则/模板生成搜索词
3. **降级模型** — Analyst/Collector 用 Haiku 替代 Sonnet
4. **限制竞品数量** — 限制为 top 3-5 个

**预期效果**：466s → ~200-280s（提升 40-60%）

**状态**：待处理
