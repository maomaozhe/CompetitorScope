# 进度追踪 (Progress)

> 最后更新：2026-05-14

## 当前状态

**里程碑 M4：Step 7/8 API + 前端主链路 — 已完成**

Pipeline 全流程（Planner → HITL → Collector → Analyst → Comparator → Writer）通过 API + Next.js UI 验证通过：
- Step 7/8 回归测试 9/9 通过
- Transition/HITL 证据链测试 8/8 通过
- 报告 Markdown 渲染修复（[object Object]、GFM 表格）
- Agent 实时输出 SSE + HITL 强化完成

**下一步**：Step 9 Demo 打磨（进行中：流式输出 + HITL 倒计时待修复）

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