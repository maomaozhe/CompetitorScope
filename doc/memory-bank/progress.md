# 进度追踪 (Progress)

> 最后更新：2026-09-28

## 当前状态

**产品方向（2026-09-28）**：原 V1 竞品分析和此前 `src/v2/` 官方定价方案已封存，保留代码及历史记录；新功能集中在 `repo_research_poc/`。当前能力、后续仓库定位/链路追踪/跨仓比较与 RAG 待定决策分别见 `repo_research_poc/README.md`、`doc/PRD.md` 和 `docs/v2/REPOSITORY_RESEARCH.md`。

**repo_research_poc（2026-09-28）**：固定快照源码问答 POC 已有 CLI 和仅绑定本机的 Web 研究页；只读检索、逐字引用校验、运行记录、历史回看和后台任务均位于独立目录。宽问题已在真实 deepagents 快照返回 `ok`，但仍耗时约 305 秒、27 次工具调用；低 token 上限可触发 JSON 重试，极低上限下两次均截断并留痕。POC 的 pytest、Web HTTP 测试及浏览器桌面/窄屏检查见 `repo_research_poc/README.md` 与 `docs/review/repo-research-web/`。业务标准答案、私有仓库验收和 LangSmith 在线实验仍待执行。

以下 M4、Step 9 与 V1 可观测性记录为**封存历史**，其“下一步”不再代表当前开发计划。

**里程碑 M4：Step 7/8 API + 前端主链路 — 已完成**

Pipeline 全流程（Planner → HITL → Collector → Analyst → Comparator → Writer）通过 API + Next.js UI 验证通过：
- Step 7/8 回归测试 9/9 通过
- Transition/HITL 证据链测试 8/8 通过
- 报告 Markdown 渲染修复（[object Object]、GFM 表格）
- Agent 实时输出 SSE + HITL 强化完成

**下一步**：Step 9 Demo 打磨（进行中：流式输出 + HITL 倒计时待修复）

## 2026-09-16：V1 可观测性与评测回放

- 新增 SQLite 追加式 trace ledger，持久化 run、span、统一事件和状态快照。
- 新增经脱敏的内容寻址 Artifact Store，保存 LLM、工具和大型 state payload。
- SSE 改为读取持久事件，支持多客户端与 `Last-Event-ID` 补发。
- 五个 Agent、LLM、search/scrape、HITL 和报告流均有结构化事件；关键业务节点产出 `decision.recorded`。
- 新增固定外部工具结果的 Eval Case 和 Candidate 重跑，支持模型、参数及 Prompt 变体。
- 新增 `/observability` 运行列表和详情页，支持时间线回放、决策/快照/Artifact 下钻及 Baseline/Candidate 对比。
- 普通 trace 默认保留 30 天，Eval 引用长期保留；进程重启后未完成 run 标记为 `interrupted`。
- 验收证据位于 `docs/review/observability/`，详细契约见 `docs/v1/OBSERVABILITY.md`。

---

## 完成总览

| 里程碑 | 包含 Step | 状态 |
|--------|-----------|------|
| M0 文档完整 | Step 0 | ✅ |
| M1 骨架可运行 | Step 1-3 | ✅ |
| M2 端到端可运行 | Step 4-6 | ✅ |
| M3 API + 前端 | Step 7-8 | ✅ |
| M4 Demo 打磨 | Step 9 | 🔜 |

## 关键工程记录

- **进行中 bug**：`bug.md` 中记录了 2 个进行中 bug（HITL 倒计时 + 流式输出）
- **SSE 事件**：agent_start / agent_complete / agent_output / hitl_request / report_chunk / complete
- **HITL 完成态回归**：done=true 后忽略 stale HITL，不重新弹窗
