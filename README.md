# CompetitorScope / 竞品雷达

[English](README.en.md)

CompetitorScope 是一个多 Agent 竞品分析系统，用于从用户输入的赛道或产品问题出发，规划竞品清单、采集公开信息、提炼证据、比较差异，并生成带证据链的 Markdown 报告。

## 效果展示
<img width="2870" height="1548" alt="image" src="https://github.com/user-attachments/assets/0af809f9-441a-42d9-bb20-ba4fff14eb21" />

<img width="2846" height="1530" alt="image" src="https://github.com/user-attachments/assets/3e22d974-4bd8-421c-b801-aa6c0534ddf1" />
<img width="2686" height="1492" alt="image" src="https://github.com/user-attachments/assets/45cbda8f-ec3b-4e56-b9b9-34dcff3e164a" />


<img width="2786" height="1528" alt="image" src="https://github.com/user-attachments/assets/8e570475-d3c7-4c00-aa0e-34c9ccaef1e8" />


## 项目简介

系统围绕 LangGraph 工作流组织多个 Agent：Planner 负责竞品和报告规划，Collector 负责搜索和采集，Analyst 负责单个竞品画像，Comparator 负责横向对比，Writer 负责最终报告生成。前端提供实时进度、Agent 输出流、人机确认（HITL）、证据面板和报告查看。

当前实现支持：

- FastAPI 后端 API 和 SSE 实时事件流。
- Next.js 前端交互界面。
- Tavily 搜索和网页内容抓取。
- Anthropic-compatible LLM 接口及各 Agent 独立模型配置。
- 自动或交互式 HITL 确认流程。
- Markdown 报告和证据链输出。

## 架构概览

后端入口是 `src/main.py`，API 位于 `src/api/v1/`，运行态由 `src/api/v1/runtime.py` 管理。工作流定义在 `src/graph/workflow.py`，各 Agent 节点在 `src/graph/nodes/`。LLM 和搜索能力分别封装在 `src/services/llm.py`、`src/tools/web_search.py` 和 `src/tools/web_scraper.py`。

前端位于 `web/`，使用 Next.js。`web/src/lib/api.ts` 负责访问后端，`web/src/hooks/useSSE.ts` 负责订阅实时事件，`web/src/components/` 中包含输入表单、Agent 流程、HITL 弹窗、证据面板和报告视图。

## 目录结构

```text
.
├── src/                 # FastAPI backend, LangGraph workflow, agents, services, tools
├── web/                 # Next.js frontend
├── scripts/             # Local CLI and end-to-end helper scripts
├── tests/               # Backend pytest tests
├── doc/                 # Project notes and memory-bank documents
├── data/                # Local data directory used by the app
├── Makefile             # Common backend commands
├── pyproject.toml       # Python dependencies and tooling
└── .env.example         # Environment variable template
```

## 环境要求

- Python 3.11+
- `uv`
- Node.js
- `npm` 或 `pnpm`
- Anthropic-compatible LLM API key
- Tavily API key

Python 依赖使用 `uv` 管理；前端依赖在 `web/` 目录中使用你选择的 Node 包管理器管理。

## 配置

复制环境变量模板并填写密钥：

```bash
cp .env.example .env
```

主要配置项：

- `ANTHROPIC_API_KEY`: LLM API key。
- `ANTHROPIC_BASE_URL`: Anthropic-compatible API base URL。
- `TAVILY_API_KEY`: Tavily search API key。
- `PLANNER_MODEL`, `COLLECTOR_MODEL`, `ANALYST_MODEL`, `COMPARATOR_MODEL`, `WRITER_MODEL`: 各 Agent 使用的模型名。
- `LOG_LEVEL`: 后端日志级别。
- `MAX_SEARCH_ROUNDS`: 最大搜索轮数。
- `DATA_DIR`: 本地数据目录。

代码中还支持可选的 `DATABASE_URL`。未设置时会使用本地 SQLite 文件 `competitorscope.db`。

## 快速开始

安装后端依赖：

```bash
uv sync
```

启动后端：

```bash
make dev
```

如果当前 shell 找不到 `uvicorn`，可以使用：

```bash
uv run uvicorn src.main:app --reload --port 8000
```

启动前端：

```bash
cd web
npm install
npm run dev
```

打开浏览器访问：

```text
http://localhost:3000
```

默认后端地址为 `http://localhost:8000`，前端开发服务器运行在 `http://localhost:3000`。

## CLI 本地运行

可以不启动前端，直接运行本地端到端流程：

```bash
make run
```

或指定查询和 HITL 模式：

```bash
uv run python scripts/run_local.py "AI Coding IDE 赛道的主要竞品" --hitl interactive
```

CLI 输出会写入 `output/run-<id>/`，包括 `report.md`、`data.json` 和 `log.txt`。

## 测试与检查

后端测试：

```bash
uv run pytest tests/ -v
```

后端 lint：

```bash
uv run ruff check src tests
```

注意：`Makefile` 中的 `make lint` 当前只检查 `src/`。

前端 lint：

```bash
cd web
npm run lint
```

关键浏览器 guard 脚本：

- `web/test_hitl_done_guard.mjs`: 检查 HITL 完成行为。
- `web/test_hitl_countdown_guard.mjs`: 检查 HITL 倒计时行为。
- `web/test_agent_output_hitl_guard.mjs`: 检查 HITL 状态附近的 Agent 输出。
- `web/test_report_rendering_guard.mjs`: 检查报告渲染。
- `web/test_transition_hitl_evidence.mjs`: 检查 HITL 与证据展示之间的状态切换。

这些脚本依赖本地前后端服务，运行前请先启动后端和前端。

## 当前状态与限制

运行态主要保存在内存 `RUN_STORE` 中，数据库表会在后端启动时创建，但完整的持久化恢复能力仍在完善。重启服务后，正在运行或刚完成的分析状态可能无法完整恢复。

当前仓库没有可直接使用的 Docker 或 Alembic 迁移流程。请不要把 Docker、数据库迁移或生产部署视为已完成能力。

## 开发提示

- 不要提交 `.env`、本地数据库文件、构建缓存、测试截图或本地输出目录。
- 根目录 README 是项目主入口；`web/README.md` 仍保留为前端子项目文档。
- 新增能力时，请同步更新 `.env.example`、测试说明和相关命令。

## 规划

- 完善数据库持久化和恢复能力。
- 增加正式迁移流程。
- 补充部署和容器化文档。
- 扩展自动化 E2E 覆盖。
