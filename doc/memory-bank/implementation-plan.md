# 实施计划 (Implementation Plan)

> 竞品分析 Agent 协作系统的分步实施路线与验收标准。
>
> 配套：`product-requirements.md`（PRD）、`design-document.md`（设计）、`architecture.md`（架构）、`tech-stack.md`（技术栈）。
>
> 最后更新：2026-05-12

---

## 总策略

**文档先行 → 后端骨架 → 核心管道跑通 → HITL + 并发 → 前端 → 联调 → Demo 打磨**

每个 Step 结束都要"能跑、能验证"。不追求一次到位。

---

## Step 0 — 文档落盘 ✅

**目标**：把架构与决策固化为文档，作为后续实施的契约。

**产物**

- [x] `product-requirements.md` — PRD
- [x] `design-document.md` — 系统设计
- [x] `architecture.md` — 架构图
- [x] `tech-stack.md` — 技术栈
- [x] `implementation-plan.md` — 本文件
- [x] `progress.md` — 进度追踪

**验收**：6 份文档完整覆盖产品需求、架构、技术栈、Agent 设计、数据模型、API、HITL、前端、实施计划。文档间无矛盾。

---

## Step 1 — 项目脚手架

**目标**：建立可运行的空项目骨架（后端 + 前端）。

**任务**

1. 初始化 `pyproject.toml`（uv），按 `tech-stack.md` 落后端依赖
2. 建立 `src/` 目录结构（按 design-document §2.2）
3. `src/config.py`：Pydantic Settings 读 `.env`，包含所有 Agent 模型配置 + HITL 配置
4. `.env.example` 写齐所有环境变量（含 ANTHROPIC_API_KEY、TAVILY_API_KEY、REDDIT_*、各 Agent 模型）
5. `Makefile`：`make install / dev / test / lint / format / web-dev`
6. `.gitignore`、`README.md` 骨架
7. `ruff` + `mypy` 基础配置
8. 简单的 `src/main.py`（空 FastAPI 应用 + CORS for Next.js）和 `src/cli/app.py`（空 Typer）
9. 初始化 `web/`：`npx create-next-app@latest --typescript --tailwind --app`
10. 前端空白首页能跑起来

**验收**

- ✅ `uv sync` 通过
- ✅ `uvicorn src.main:app --reload` 启动成功，`/api/v1/health` 返回 200
- ✅ `python -m src.cli.app --help` 打印帮助
- ✅ `cd web && pnpm dev` 启动成功，localhost:3000 显示空白页

---

## Step 2 — 数据模型与基础服务

**目标**：把架构里的"名词"先建好，后续 Agent 直接装配。

**任务**

1. ✅ `schemas/domain.py`：实现全部域模型（RawSource/EvidenceItem/CompetitorProfile/Report 等）
2. ✅ `graph/state.py`：`AnalysisState` TypedDict + `operator.add` reducer
3. ✅ `services/llm.py`：Anthropic LLM 工厂（含 `base_url` 可配置）
4. `services/database.py`：异步引擎 + Session 工厂
5. `models/*.py`：SQLModel ORM（暂不接 Alembic）

**验收**

- ✅ `pytest tests/unit/test_state.py`：AnalysisState 能创建、reducer 追加正确
- ✅ `get_llm("planner")` 返回 Sonnet，`get_llm("collector")` 返回 Haiku
- ✅ API key 已配置（MiniMax 端点），LLM 调用成功

---

## Step 3 — 工具层

**目标**：Agent 所需的外部能力封装就绪。

**任务**

1. ✅ `tools/web_search.py`：Tavily 封装（已验证，返回 ≥3 条结果）
2. ✅ `tools/web_scraper.py`：httpx + readability 抓取并清洗
   - 参数 `query, max_results`
   - 返回 `[{title, url, content, score}]`
   - tenacity 重试
2. `tools/web_scraper.py`：httpx + readability 抓取并清洗
   - 输入 URL → 输出去噪正文
   - 大产物落文件 `data/raw/{run_id}/{source_id}.txt`
3. `tools/reddit_search.py`：PRAW 封装
   - 搜索指定关键词的帖子 + 评论
   - 返回结构化结果
4. `tools/app_reviews.py`：httpx 抓取 App Store / Google Play 评论页
   - 基础版：抓取评论页 HTML → readability 清洗
5. `tools/structured_extract.py`：LLM 结构化提取包装
   - 接受 `text + output_schema`
   - 返回 Pydantic 实例
6. `tools/report_formatter.py`：Markdown 渲染（最小可用）

**验收**

- 集成测试：`web_search("Cursor pricing")` 返回 ≥3 条结果
- 集成测试：`web_scraper("https://cursor.com/pricing")` 返回非空正文
- 集成测试：`reddit_search("Cursor IDE review")` 返回 ≥1 条帖子
- 单测：`structured_extract` 在 mock LLM 下能解析为目标 Schema

---

## Step 4 — 核心管道最小可用版（串行）

**目标**：5 个 Agent 节点串行跑通，端到端生成报告。先不 fan-out，先不 HITL。

**任务**

1. `prompts/`：5 个 Agent 的初版 System Prompt
   - planner.py：需求解析 + 竞品发现 + 大纲生成
   - collector.py：围绕单竞品多策略采集
   - analyst.py：结构化提取 + 4 维度分析
   - comparator.py：横向对比 + 洞察
   - writer.py：Markdown 报告 + 引用
2. `graph/nodes/planner.py`：
   - 调 `web_search` 发现竞品候选
   - 硬编码确认（跳过 HITL）
   - 生成报告大纲
3. `graph/nodes/collector.py`：
   - 调 `web_search` + `web_scraper` + `reddit_search`
   - 写入 `state["raw_sources"]`
4. `graph/nodes/analyst.py`：
   - 对单竞品的 raw_sources 调 `structured_extract`
   - 输出 CompetitorProfile + EvidenceItem
5. `graph/nodes/comparator.py`：
   - 接收所有 profiles，输出 ComparisonResult
6. `graph/nodes/writer.py`：
   - 输出 Report.content_markdown，含 [N] 引用
7. `graph/workflow.py`：
   - StateGraph 串行：`START → planner → collector(竞品1) → collector(竞品2) → analyst(竞品1) → analyst(竞品2) → comparator → writer → END`
   - 编译加 `AsyncSqliteSaver`
8. 临时脚本 `scripts/run_local.py`：直接调用 `graph.ainvoke`

**验收**（端到端冒烟）

```bash
python scripts/run_local.py "分析 Cursor vs Windsurf"
```

成功打印 Markdown 报告，且：
- 收集到 ≥3 个 sources/竞品
- 报告含至少 2 个内联引用 `[1]` `[2]`
- CompetitorProfile 4 个维度均有数据

**实际实现**：

- ✅ `prompts/`：5 个 Agent System Prompt
- ✅ `graph/nodes/planner.py`：Tavily 搜索发现竞品，生成大纲
- ✅ `graph/nodes/collector.py`：Tavily + httpx 并发采集
- ✅ `graph/nodes/analyst.py`：LLM 结构化提取 4 维度
- ✅ `graph/nodes/comparator.py`：Markdown 对比表 + 洞察
- ✅ `graph/nodes/writer.py`：Markdown 报告
- ✅ `graph/workflow.py`：StateGraph 串行 pipeline
- ✅ `scripts/run_local.py`：直接调用 `graph.ainvoke`

---

## Step 5 — 并发 fan-out

**目标**：把串行改为并发，Collector × N 和 Analyst × N 同时跑。

**任务**

1. `workflow.py` 改用 `Send` API：
   - Planner 完成后 → `fan_out_collectors()` 返回 N 个 `Send("collect_competitor", ...)`
   - 所有 Collector 完成后 → `fan_out_analysts()` 返回 N 个 `Send("analyze_competitor", ...)`
2. 确认 `operator.add` reducer 在并发写入时正确合并
3. Barrier 节点：`join_collectors`、`join_analysts` 等待所有 fan-out 完成
4. `finished_collectors` / `finished_analysts: Annotated[set, union_reducer]` 追踪完成

**验收**

```bash
python scripts/run_local.py "分析 Cursor vs Windsurf vs Copilot"
```

- 日志显示 3 个 Collector 近乎同时启动
- 3 个 Analyst 近乎同时启动
- 总耗时 < 串行版本的 50%
- 输出报告与串行版质量一致

**实际实现**：

- ✅ `Send` API fan-out：collector 和 analyst 均并发 N 路
- ✅ join_collectors / join_analysts barrier 节点
- ✅ `finished_collectors` / `finished_analysts: Annotated[set, _union_sets]` 完成追踪
- ⚠️ 总耗时 ~466s vs 串行 ~510s：提升有限（LLM 瓶颈），collector 并行有效
- ⚠️ `MemorySaver` checkpoint 与 Pydantic model 序列化不兼容，本次未启用

---

## Step 6 — HITL 集成

**目标**：4 个 HITL 介入点全部落地，支持 interactive 和 auto 两种模式。

**任务**

1. Planner 节点加 `interrupt()`：竞品确认 + 大纲确认
   - auto 模式：直接采用默认值（前 5 家 / 标准详略）
   - interactive 模式：暂停等待外部输入
2. Collector 节点加 `interrupt()`：数据不足时提问
   - auto 模式：继续用已有数据
3. Writer 节点后加追问入口（子图）
4. `api/v1/hitl.py`：
   - `POST /analysis/{id}/hitl`：接收用户 HITL 响应
   - `GET /analysis/{id}/hitl/pending`：查询当前等待的 HITL 请求
5. 后端 HITL 流程：interrupt → SSE 推 hitl_request → 用户 POST 响应 → update_state → 续跑
6. 超时逻辑：30s 无响应自动采用默认值

**验收**

- auto 模式：全流程无暂停跑完
- interactive 模式（CLI 模拟）：
  - 脚本暂停，打印候选清单
  - 手动输入确认后继续
  - 正确使用用户选择的竞品

---

## Step 7 — FastAPI 接口层

**目标**：REST API 完整可用。

**任务**

1. `api/deps.py`：DB Session / Graph 实例的依赖注入
2. `api/v1/analysis.py`：
   - `POST /analysis`：建 run、BackgroundTasks 启动 graph
   - `GET /analysis/{id}`：从 checkpoint + DB 拼状态
   - `GET /analysis/{id}/stream`：SSE，转 `graph.astream_events()`
   - `DELETE`：interrupt thread
3. `api/v1/hitl.py`：HITL 端点（Step 6 已设计，这里接入 API 层）
4. `api/v1/reports.py`：报告 JSON / Markdown / 证据链端点
5. `api/v1/health.py`
6. `main.py` 装配 lifespan（DB 初始化、Graph 编译、CORS 配置）

**验收**

- `curl -X POST /api/v1/analysis -d '{"query": "...", "hitl_mode": "auto"}'` 返回 202
- SSE 客户端收到 agent_start / agent_complete / report_chunk / complete 事件
- `curl /api/v1/reports/{id}/markdown` 下载完整报告
- `curl /api/v1/reports/{id}/evidence` 返回证据链

---

## Step 8 — Next.js 前端

**目标**：Web UI 完整可用，三栏布局 + Agent 进度流 + HITL 弹窗 + 证据下钻。

**任务**

1. 首页 `/`：
   - InputForm 组件：需求输入 + 竞品补充 + 维度选择 + hitl_mode 开关
   - 历史分析列表
   - POST /analysis 发起分析
2. 分析页 `/analysis/[id]`：三栏布局
   - **左侧 AgentFlow 组件**：SSE 订阅，实时显示 Agent 头像 + 状态
   - **右侧 ReportView 组件**：渐进式 Markdown 渲染 + 引用锚点
   - **底部 EvidencePanel 组件**：点击引用 [N] 展开证据详情
3. HITL 交互：
   - HITLDialog 组件：根据 hitl_request 事件类型展示对应弹窗
   - 竞品确认弹窗：勾选框列表 + 手动添加
   - 大纲确认弹窗：详略调节
   - 抓取失败弹窗：补充链接 / 跳过 / 继续
   - 超时自动提交
4. `hooks/useSSE.ts`：EventSource 订阅 + 事件分发
5. `lib/api.ts`：封装 API 调用（创建分析、提交 HITL、获取报告）
6. 样式：Tailwind 快速搭建，暗色 + 亮色主题（可选）
7. 响应式适配（比赛大屏演示为主）

**验收**

- 首页输入需求 → 跳转分析页
- 左侧 Agent 进度流实时更新（≥3 个 Agent 同时显示）
- HITL 弹窗正确弹出并提交
- 报告渐进式渲染
- 点击引用 [N] → 证据面板展开，显示原文摘录 + 来源 URL

---

## Step 9 — 端到端联调 + Demo 打磨

**目标**：前后端联调完成，Demo 场景跑通。

**任务**

1. AI Coding IDE 场景完整跑通：
   - 输入："分析 AI Coding IDE 赛道的头部玩家，重点了解定价和开发者口碑"
   - Planner 返回 Cursor / Copilot / Windsurf / Cline / Aider 等
   - 勾选 5 家 → 并发采集 → 并发分析 → 对比 → 报告
2. 性能优化：
   - 确保 5 家竞品端到端 ≤ 5 分钟
   - 前端 Agent 流响应 ≤ 1s
3. 兜底方案：
   - 预录一套完整 trace（checkpoint 回放）
   - 本地缓存完整 agent 运行结果
4. Prompt 调优：
   - 报告质量审查：每个结论有证据吗？引用准确吗？
   - Planner 竞品发现质量：候选清单合理吗？
5. 演示模式打磨：
   - hitl_mode="auto" 全流程 ≤ 3 分钟
   - Agent 进度流的视觉效果（头像、动画、状态切换）
6. 错误处理 + 边界场景：
   - 网络断开怎么办
   - LLM 限流怎么办
   - 某竞品完全抓不到数据怎么办

**验收**

- Demo 场景 3 分钟内跑完
- 证据链随机抽查 5 个，≥4 个 URL 可访问且内容相符
- 兜底方案可用：断网后切换到预录 trace 正常展示

---

## Step 10 — CLI + 持久化 + 测试

**目标**：补齐非核心但完整度需要的部分。

**任务**

1. CLI 完整版：
   - `ca run` / `ca status` / `ca list` / `ca report` / `ca evidence` / `ca serve`
   - Rich 进度条 + Markdown 渲染
2. Alembic 迁移：
   - 初始化 + 首版迁移
   - 每个 run 落 `analysis_run` + 关联表
3. 报告落盘：`data/reports/{run_id}.md`
4. 测试：
   - 单测：State / Schema / Tools / LLM 工厂
   - 集成测试：完整 workflow（cassette 录制）
   - API 测试：FastAPI TestClient
   - 覆盖率目标：核心模块 ≥ 70%

**验收**

- `ca run "..." --hitl auto --output report.md` 正常工作
- `make test` 全绿
- `pytest --cov` 核心模块 ≥ 70%

---

## Step 11 — 部署与文档

**任务**

1. `docker/Dockerfile`（多阶段：后端 + 前端）
2. `docker/compose.yaml`（后端 + 前端 + 可选 PostgreSQL）
3. `README.md`：快速开始、示例命令、架构图、Demo 截图
4. 性能/成本观测：每 run 记录 tokens、搜索次数、耗时
5. 最终 Demo 录屏备份

**验收**

- `docker compose up` 启动完整服务（前端 + 后端）
- README 按步骤能让新人 10 分钟跑通示例

---

## 里程碑总览

| 里程碑 | 包含 Step | 关键交付 | 状态 |
|--------|-----------|---------|------|
| **M0 文档完整** | Step 0 | 6 份核心文档 | ✅ 完成 |
| **M1 骨架可运行** | Step 1-3 | 项目结构 + 数据模型 + 工具层 | ✅ 完成 |
| **M2 端到端可运行** | Step 4-5 | 5 Agent 串行 pipeline + API + 前端 MVP | ✅ 完成 |

---

## 风险与节点决策

| 节点 | 触发条件 | 决策 |
|------|---------|------|
| Step 4 结束 | 端到端跑不通 | 优先调 prompts；降级：减少竞品数量 |
| Step 5 结束 | fan-out 并发问题 | 回退串行 + 前端模拟并发动画 |
| Step 6 结束 | HITL interrupt 不稳定 | 降级：只保留 auto 模式，HITL 作为"讲解卖点"而非实际演示 |
| Step 8 结束 | 前端开发耗时过长 | 降级：用 Streamlit 快速替代核心页面 |
| Step 9 结束 | Demo 场景质量不达标 | 切换到预录 trace 回放，确保演示流畅 |
| 任何阶段 | 单 run > 10 分钟 | 减少竞品数（5→3）/ 减少搜索轮次 |
| 任何阶段 | LLM 成本超预算 | 更多 Agent 切到 Haiku / 减少搜索轮次 |
