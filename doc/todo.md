# TODO

> 优化项，待后续处理。

---

## Step 5 性能优化

**问题**：7 竞品端到端 ~466s（~7.8min），主要瓶颈是 17 次 LLM 串行调用。

**优化方向**：

1. **批量 Analyst** — 1 次 LLM 调用分析所有竞品，而非每个竞品单独调用（从 7 次 → 1 次）
2. **去掉 Collector 的 LLM** — 直接用规则/模板生成搜索词，不调用 LLM 决策（从 7 次 → 0 次）
3. **降级模型** — Analyst/Collector 用 Haiku 替代 Sonnet
4. **限制竞品数量** — 限制为 top 3-5 个，减少数据量

**预期效果**：466s → ~200-280s（提升 40-60%）

**状态**：部分完成。CLI 与后端节点级日志已完成；前端实时 AgentFlow 细节与耗时展示留到 Step 8。

---

## 可视化追踪（Agent 流程监控）

**问题**：当前只能看到开始/结束，看不到中间过程和各阶段耗时。

**目标**：前端点击分析任务，实时看到每个 Agent 的工作状态、流转、耗时。

**后端需求**：

1. `workflow.astream_events` 替代 `invoke`，实时推送每个节点的 start/end 事件
2. 每个节点内部加细粒度进度（如 Collector 开始抓取、开始分析等）
3. SSE 端点 `GET /api/v1/analysis/{id}/stream` 把事件实时推送

**前端需求**：

1. AgentFlow 组件 — 实时显示 Planner → Collector → Analyst → Comparator → Writer 的状态
2. 状态：pending（灰色）/ running（蓝色动画）/ done（绿色）/ error（红色）
3. 每个节点显示耗时（如 `Collector 42s`）
4. 数据量变化（如 `Sources: 0 → 12 → 35`）

**状态**：待处理
