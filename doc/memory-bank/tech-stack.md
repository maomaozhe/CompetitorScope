# 技术栈说明 (Tech Stack)

> 竞品分析 Agent 协作系统的完整技术选型清单。所有依赖、版本与选型理由集中维护于此文档。
>
> 最后更新：2026-05-12

---

## 1. 概览

| 维度 | 选择 |
|------|------|
| 后端语言 | Python 3.11+ |
| 前端框架 | Next.js 15 (App Router) + TypeScript |
| 包/项目管理 | `uv` (Python) / `pnpm` (Node.js) |
| Agent 编排 | LangGraph |
| Web 框架 | FastAPI |
| CLI 框架 | Typer + Rich |
| 数据库 | SQLite (MVP) → PostgreSQL (生产) |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| 迁移 | Alembic |
| 搜索 | Tavily Search API |
| 网页提取 | httpx + readability-lxml |
| 社区数据 | Reddit API (PRAW) + httpx (知乎/App Store) |
| LLM Provider | Anthropic (主力) — Claude Sonnet + Haiku |
| 实时通信 | SSE (sse-starlette → Next.js EventSource) |
| 部署 | Docker + Docker Compose |

---

## 2. 后端依赖（pyproject.toml）

```toml
[project]
name = "competitor-scope"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Agent 编排核心
    "langgraph>=0.3.0",
    "langchain-core>=0.3.0",
    "langgraph-checkpoint-sqlite>=2.0.0",

    # LLM Provider — Anthropic 为主力
    "langchain-anthropic>=0.3.0",

    # Web 层
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.0.0",

    # CLI 层
    "typer>=0.15.0",
    "rich>=13.0.0",

    # 搜索 & 网页提取
    "tavily-python>=0.5.0",
    "httpx>=0.28.0",
    "readability-lxml>=0.8.0",
    "lxml>=5.0.0",

    # 社区数据
    "praw>=7.7.0",                # Reddit API

    # 数据持久化
    "sqlmodel>=0.0.22",
    "aiosqlite>=0.20.0",
    "alembic>=1.14.0",

    # 配置与工具
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "python-dotenv>=1.0.0",
    "tenacity>=9.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "httpx>=0.28.0",
    "ruff>=0.7.0",
    "mypy>=1.13.0",
    "pre-commit>=4.0.0",
]
```

---

## 3. 前端依赖（web/package.json 关键项）

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-markdown": "^9.0.0",
    "tailwindcss": "^4.0.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "@types/react": "^19.0.0",
    "eslint": "^9.0.0"
  }
}
```

**前端技术栈说明**：
- **Next.js 15 App Router**：SSR + 客户端混合，路由简洁
- **React 19**：与 Next.js 15 配套
- **Tailwind CSS 4**：快速 UI 开发，比赛场景下效率最高
- **react-markdown**：Markdown 报告渲染
- **lucide-react**：图标库（Agent 头像等）
- **原生 EventSource**：SSE 订阅，不需要额外库

---

## 4. 选型理由

### 4.1 Agent 编排：LangGraph

- **为什么不用 CrewAI / AutoGen**：CrewAI 偏 Role-Playing 模式不易约束证据链；AutoGen 多 Agent 群聊难以保证可复现
- **LangGraph 优势**：
  - StateGraph 显式定义状态流转，易于审计
  - **Send API 原生支持并发 fan-out** — 这是"多 Agent 在干活"的视觉卖点
  - **interrupt() 原生支持 HITL** — 不需要自建暂停/恢复机制
  - 内置 Checkpoint，支持断点续跑 + 过程可回放
  - `astream_events()` 原生 SSE 事件流
  - LangChain 生态成熟（搜索、LLM、结构化输出）

### 4.2 前端：Next.js + SSE

- **为什么不用 Streamlit / Gradio**：
  - Streamlit：Agent 进度流展示受限，左右分栏自由度低，"工作台"感弱
  - Gradio：布局灵活度差，HITL 弹窗交互不好做
- **Next.js 优势**：
  - 完全自由的 UI 布局（三栏布局、弹窗、抽屉面板）
  - SSE 用原生 EventSource，实现简单
  - SSR 对比赛 demo 不重要，但开发体验好
  - TypeScript 类型安全，前后端 schema 可共享

### 4.3 LLM：Anthropic Claude

| Agent | 模型 | 理由 |
|-------|------|------|
| Planner | Claude Sonnet | 需要强推理：解析需求、发现竞品、设计大纲 |
| Collector | Claude Haiku | 简单决策：搜索什么、抓取什么 |
| Analyst | Claude Haiku | 结构化提取任务，Haiku 足够 |
| Comparator | Claude Sonnet | 跨竞品综合推理，需要强能力 |
| Writer | Claude Sonnet | 报告写作质量优先 |

- 通过 LangChain 的 `ChatAnthropic` 统一封装
- 每个 Agent 独立配置模型
- **后续可加 OpenAI / Google**：改为 `BaseChatModel` 工厂模式即可扩展

### 4.4 搜索：Tavily

- 专为 AI Agent 设计：返回干净结构化结果（title、url、content、score）
- LangChain 原生 `TavilySearchResults` 工具
- 替代方案：SerpAPI 仅在 Tavily 不可用时作为 fallback

### 4.5 数据源策略

| 数据源 | 获取方式 | 覆盖维度 | MVP 优先级 |
|--------|---------|---------|-----------|
| 竞品官网 | httpx + readability | 定位/功能/定价 | P0 |
| Tavily 搜索 | Tavily API | 全维度补充 | P0 |
| Reddit | PRAW (Reddit API) | 用户口碑 | P0 |
| 知乎 | httpx 抓取搜索结果页 | 用户口碑(中文) | P1 |
| App Store / Google Play | httpx 抓取评论页 | 用户口碑 | P1 |
| HN / X (Twitter) | Tavily 搜索覆盖 | 用户口碑 | P2 (通过 Tavily 间接获取) |
| 小红书 | **不做** | — | — (反爬风险) |

### 4.6 网页提取：httpx + readability-lxml

- `httpx`：异步 HTTP 客户端，支持 HTTP/2
- `readability-lxml`：从 HTML 中提取主体内容（去广告、导航等噪声）
- 轻量、无浏览器依赖、容器友好
- **不引入 Playwright/Selenium**：MVP 阶段大多数公开信息通过 HTTP 抓取够用

### 4.7 数据库：SQLite → PostgreSQL

- **MVP 用 SQLite**：零基础设施，单文件部署
  - 业务库：`data/app.db`
  - Checkpoint 库：`data/checkpoints.db`
- **平滑升级 PostgreSQL**：改 `DATABASE_URL` + 换 `AsyncPostgresSaver`

### 4.8 实时通信：SSE

- **为什么不用 WebSocket**：SSE 单向已够（后端→前端推事件，前端→后端走 REST）
- `sse-starlette`：FastAPI 生态成熟
- `astream_events()`：LangGraph 原生输出 SSE 事件流
- 前端用原生 `EventSource` API，不需要 socket.io 等库

---

## 5. 环境变量

```bash
# .env.example

# LLM — Anthropic (主力)
ANTHROPIC_API_KEY=

# 搜索
TAVILY_API_KEY=

# 社区数据
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=competitor-scope/0.1

# LLM 配置
PLANNER_MODEL=claude-sonnet-4-6
COLLECTOR_MODEL=claude-haiku-4-5-20251001
ANALYST_MODEL=claude-haiku-4-5-20251001
COMPARATOR_MODEL=claude-sonnet-4-6
WRITER_MODEL=claude-sonnet-4-6

# 数据库
DATABASE_URL=sqlite+aiosqlite:///data/app.db
CHECKPOINT_DB_URL=sqlite+aiosqlite:///data/checkpoints.db

# 应用
APP_ENV=dev                       # dev | prod
LOG_LEVEL=INFO
MAX_SEARCH_ROUNDS=3
MAX_RETRIES=2
HITL_TIMEOUT=30                   # HITL 超时秒数,0=不超时
```

---

## 6. 目录约定

```
competitor-scope/
├── doc/
│   └── memory-bank/          # 文档集
│       ├── product-requirements.md
│       ├── design-document.md
│       ├── architecture.md
│       ├── tech-stack.md       (本文件)
│       ├── implementation-plan.md
│       └── progress.md
│
├── src/                      # Python 后端
│   ├── main.py
│   ├── config.py
│   ├── api/v1/
│   ├── cli/
│   ├── graph/
│   ├── tools/
│   ├── schemas/
│   ├── models/
│   ├── services/
│   └── prompts/
│
├── web/                      # Next.js 前端
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── lib/
│   ├── package.json
│   └── next.config.js
│
├── tests/                    # 测试
├── data/                     # SQLite / 报告文件（gitignore）
├── alembic/                  # DB 迁移脚本
├── docker/                   # Dockerfile, compose.yaml
├── pyproject.toml
├── .env.example
└── Makefile
```

---

## 7. 开发工具链

| 用途 | 工具 |
|------|------|
| Python 格式化 + Lint | ruff |
| Python 类型检查 | mypy |
| Python 测试 | pytest + pytest-asyncio |
| 前端 Lint | ESLint |
| 前端格式化 | Prettier (通过 ESLint) |
| Git hooks | pre-commit |
| 任务运行 | Makefile (`make dev`, `make test`, `make lint`) |

---

## 8. 升级路径

| 当前 | 未来升级 | 触发条件 |
|------|---------|---------|
| SQLite | PostgreSQL | 并发分析 > 5/分钟 或数据量 > 1GB |
| FastAPI BackgroundTasks | Celery / ARQ | 单任务超过 10 分钟 |
| Anthropic only | + OpenAI / Google | 需要多 Provider 备选 |
| Tavily only | + SerpAPI fallback | Tavily 限流/不可用 |
| httpx 抓取 | + Playwright | 需要 JS 渲染的关键源 |
| 本地文件存储 | S3 / OSS | 多实例部署 |
| 单进程 Graph | LangGraph Platform | 需要可观测性、A/B 测试 |
| SSE | WebSocket (双向) | 需要前端实时发消息给运行中的 Agent |
