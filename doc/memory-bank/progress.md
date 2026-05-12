# 进度追踪 (Progress)

> 最后更新：2026-05-12

---

## 当前状态

**里程碑 M0：文档完整 — ✅ 已完成**

下一步：Step 1 — 项目脚手架

---

## 完成记录

### 2026-05-12 — Step 0 文档落盘

**完成事项**：

| 文档 | 状态 | 说明 |
|------|------|------|
| `product-requirements.md` | ✅ 新建 | PRD：场景、维度、HITL 设计、Demo 剧本、成功标准 |
| `design-document.md` | ✅ 重写 | 5 Agent 架构、fan-out、HITL interrupt、新 State schema、前端设计 |
| `architecture.md` | ✅ 新建 | 系统全景图、Agent 通信图、数据流图、HITL 时序图、存储架构 |
| `tech-stack.md` | ✅ 重写 | 加 Next.js 前端、数据源策略、Anthropic 主力、Reddit API |
| `implementation-plan.md` | ✅ 重写 | 12 步计划对齐新架构，含 HITL/前端/Demo 打磨步骤 |
| `progress.md` | ✅ 新建 | 本文件 |

**关键决策记录**：

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 数量 | 5 个 (Planner/Collector/Analyst/Comparator/Writer) | 最小但完整，能展示多 Agent 协作 |
| 协作模式 | Orchestrator + 专项子 Agent + Send fan-out | 并发是视觉卖点 |
| Agent 通信 | 黑板模式 (共享 state) | 简单、可追溯、LangGraph 原生 |
| HITL | 4 个介入点 + 演示模式全跳过 | 兼顾可控性和演示流畅度 |
| 分析维度 | 4 维 (产品定位/核心功能/定价/用户口碑) | MVP 瘦身，V2 再拓展 |
| 前端 | Next.js + SSE | 最成熟方案，自由度高 |
| LLM | Anthropic (Sonnet + Haiku 分层) | 推理重用强模型，执行型用快模型 |
| 编排框架 | LangGraph | Send API + interrupt + checkpoint 三位一体 |
| Demo 赛道 | AI Coding IDE | 评委秒懂、数据丰富 |

---

## 待办与风险追踪

| 风险 | 状态 | 对策 |
|------|------|------|
| LangGraph Send API + interrupt 组合未验证 | ⚠️ 待验证 (Step 5-6) | Step 4 串行先跑通，Step 5 再改并发 |
| 前端开发耗时 | ⚠️ 待评估 | 降级方案：Streamlit 替代 |
| Demo 网络不稳定 | ⚠️ 待准备 | Step 9 准备预录 trace |
