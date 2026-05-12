# 进度追踪 (Progress)

> 最后更新：2026-05-12

---

## 当前状态

**里程碑 M2：端到端可运行 — ✅ 已验证跑通**

Pipeline 全流程（Planner→Collector→Analyst→Comparator→Writer）实测通过：
- 8 家竞品发现，59 条原始数据，8 个结构化档案，7348 字报告
- 耗时约 6 分钟（受 LLM 响应速度限制）

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

### 2026-05-12 — 调试修复记录

| 问题 | 修复 |
|------|------|
| LangGraph 缺少 `START` 边 | `workflow.py` 加 `graph.add_edge(START, "planner")` |
| LLM 返回 block-list 而非 string | `services/llm.py` 加 `extract_text()` / `extract_json()` |
| `collector_node` 是 async 但 graph 是 sync | 改为 sync 函数 + 同步调用 `scrape()` |
| `scrape()` 是 async httpx | 改为同步 `httpx.get()` |
| Planner 变量名 typo (`resp` vs `response`) | 已修复 |
| 报告引用格式 `[1]` 无证据支撑 | V2 问题（当前为 Markdown 引用） |

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
| 单次 pipeline > 5 分钟 | ⚠️ 约 6 分钟（LLM 延迟） | 并发 fan-out 可降至 ~2 分钟 |
| LangGraph Send API + interrupt 组合未验证 | ⚠️ 待实现 (Step 5-6) | Step 4 串行已通，Step 5 再改并发 |
| 前端开发耗时 | ⚠️ 待评估 | 降级方案：Streamlit 替代 |
| Demo 网络不稳定 | ⚠️ 待准备 | 预录 trace 回放兜底 |
| Tavily 限流 | ⚠️ 潜在 | 缓存 + fallback SerpAPI |