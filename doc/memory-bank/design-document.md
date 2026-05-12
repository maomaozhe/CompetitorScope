# 系统设计文档 (Design Document)

> 竞品分析 Agent 协作系统的架构与详细设计。
>
> 本文配套：`product-requirements.md`（PRD）、`architecture.md`（架构图）、`tech-stack.md`（技术栈）、`implementation-plan.md`（实施计划）。
>
> 最后更新：2026-05-12

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 全流程覆盖 | 竞品发现 → 数据采集 → 结构化分析 → 横向对比 → 报告生成 |
| 多 Agent 并发 | Collector 和 Analyst 并发 fan-out，体现多 Agent 协作价值 |
| 人在环路 (HITL) | 4 个可选介入点，演示模式可全部跳过 |
| 证据链可追溯 | 从最终结论倒查到原始 URL + 原文摘录 + Agent 推理过程 |
| 过程可回放 | 前端实时展示 Agent 工作流，支持历史回溯 |
| 可复现 | 同样输入 → 同样工作流；LangGraph checkpoint 支持断点续跑 |
| API-first | 同时服务 Web 前端与 CLI |

---

## 2. 总体架构

### 2.1 分层视图

```
┌──────────────────────────────────────────────────────────────────┐
│  展示层  Presentation Layer                                       │
│  ┌────────────────────┐    ┌────────────────┐                    │
│  │  Next.js Web UI    │    │  Typer CLI     │                    │
│  │  SSE 订阅 Agent 流  │    │  ca <command>  │                    │
│  │  HITL 交互界面      │    │  Rich 进度条    │                    │
│  └─────────┬──────────┘    └───────┬────────┘                    │
└────────────┼───────────────────────┼─────────────────────────────┘
             │ REST + SSE           │ 直跑 / REST
             ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│  接口层  API Layer (FastAPI)                                      │
│  POST /analysis          创建分析任务                              │
│  GET  /analysis/{id}/stream   SSE 事件流                          │
│  POST /analysis/{id}/hitl     HITL 响应提交                       │
│  GET  /reports/{id}           报告 + 证据链                       │
└──────────────────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│  编排层  Orchestration Layer (LangGraph StateGraph)               │
│                                                                   │
│  Planner ─┬─► Collector × N ─► Analyst × N ─► Comparator ─► Writer│
│           │   (Send fan-out)   (Send fan-out)                     │
│           │                                                       │
│  AnalysisState (共享黑板) + interrupt() (HITL)                    │
│  AsyncSqliteSaver (checkpoint)                                    │
└──────────────────────────────────────────────────────────────────┘
             │                    │                    │
             ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│  工具层      │    │  服务层      │    │  持久化层        │
│  Tools       │    │  Services    │    │  Storage         │
│  web_search  │    │  LLM Factory │    │  SQLite / FS     │
│  web_scraper │    │  Database    │    │  Checkpoint DB   │
│  app_reviews │    │  Storage     │    │  Reports 文件    │
│  reddit_api  │    │              │    │                  │
└──────────────┘    └──────────────┘    └──────────────────┘
```

### 2.2 项目结构

```
src/
├── main.py                 # FastAPI app factory + lifespan
├── config.py               # Pydantic Settings
│
├── api/v1/                 # REST API
│   ├── router.py
│   ├── analysis.py         # 任务创建/状态/流式
│   ├── hitl.py             # HITL 响应提交
│   ├── reports.py          # 报告与证据查询
│   └── health.py
│
├── cli/
│   └── app.py              # Typer CLI 入口
│
├── graph/                  # LangGraph 核心
│   ├── state.py            # AnalysisState (TypedDict)
│   ├── workflow.py         # StateGraph 编译
│   ├── gates.py            # gate 条件函数
│   └── nodes/
│       ├── planner.py      # 🧭 需求解析 + 竞品发现 + 大纲
│       ├── collector.py    # 🕷️ 数据采集(web + 社区 + 评论)
│       ├── analyst.py      # 📊 单家竞品结构化分析
│       ├── comparator.py   # 🆚 横向对比
│       └── writer.py       # ✍️ 报告生成
│
├── tools/                  # 可被多个 Agent 复用的工具
│   ├── web_search.py       # Tavily 封装
│   ├── web_scraper.py      # httpx + readability
│   ├── app_reviews.py      # 应用商店评论抓取
│   ├── reddit_search.py    # Reddit API 封装
│   ├── structured_extract.py
│   └── report_formatter.py
│
├── schemas/                # Pydantic 域模型
│   ├── domain.py           # CompetitorProfile / EvidenceItem / AnalysisResult / Report
│   ├── requests.py         # API 请求体
│   └── responses.py        # API 响应体
│
├── models/                 # SQLModel ORM 模型
│   ├── base.py
│   ├── analysis_run.py
│   ├── competitor.py
│   ├── evidence.py
│   └── report.py
│
├── services/
│   ├── llm.py              # LLM 工厂 (Anthropic 主力,可扩展多 Provider)
│   ├── database.py         # 异步引擎 + Session
│   └── storage.py          # 报告文件存储
│
└── prompts/                # 各 Agent 的 System Prompt
    ├── planner.py
    ├── collector.py
    ├── analyst.py
    ├── comparator.py
    └── writer.py

web/                        # Next.js 前端 (独立目录)
├── src/
│   ├── app/                # App Router
│   │   ├── page.tsx        # 首页：输入需求
│   │   └── analysis/
│   │       └── [id]/
│   │           └── page.tsx  # 分析页：进度流 + 报告 + 证据
│   ├── components/
│   │   ├── InputForm.tsx     # 需求输入 + 竞品补充
│   │   ├── AgentFlow.tsx     # 左侧 Agent 实时进度流
│   │   ├── HITLDialog.tsx    # HITL 弹窗（确认/补充/追问）
│   │   ├── ReportView.tsx    # 报告渲染 + 证据锚点
│   │   └── EvidencePanel.tsx # 证据下钻面板
│   ├── hooks/
│   │   └── useSSE.ts         # SSE 订阅 hook
│   └── lib/
│       └── api.ts            # API 客户端
├── package.json
└── next.config.js
```

---

## 3. Agent 协作设计

### 3.1 协作模式

**Orchestrator (Planner) + 4 个专项 Agent + 并发 fan-out**

- Planner 是**有状态的协调者**：解析需求、发现竞品、生成大纲、调度子 Agent
- Collector 和 Analyst 通过 LangGraph `Send` API 并发 fan-out，一家竞品一个实例
- Comparator 是**汇聚点**：等所有 Analyst 完成后执行横向对比
- Writer 是**终结者**：基于对比结果 + 证据生成报告
- HITL 通过 LangGraph `interrupt()` 实现，嵌入在工作流关键节点

### 3.2 工作流拓扑

```
                         START
                           │
                           ▼
                    ┌─────────────┐
                    │   Planner   │  解析需求 → 搜索竞品 → 候选清单
                    └──────┬──────┘
                           │
                    ⓵ interrupt(): 竞品确认 (HITL, 可跳过)
                           │
                    ┌─────────────┐
                    │   Planner   │  生成报告大纲 (4 维度 × N 竞品)
                    └──────┬──────┘
                           │
                    ⓶ interrupt(): 大纲确认 (HITL, 可跳过)
                           │
                    ┌──────┴──────┐
                    │  fan-out    │  Send API: 为每个竞品创建一个 Collector
                    └──────┬──────┘
                    ╱      │      ╲
          ┌────────┐ ┌────────┐ ┌────────┐
          │Collect-1│ │Collect-2│ │Collect-N│   并发抓取
          └───┬────┘ └───┬────┘ └───┬────┘
              │          │          │
          ◇ gate: 数据量是否足够?
          │ 不足 → ⓷ interrupt(): 抓取失败提问 (HITL)
          │ 足够 → 继续
              │          │          │
          ┌────────┐ ┌────────┐ ┌────────┐
          │Analyst-1│ │Analyst-2│ │Analyst-N│   并发分析
          └───┬────┘ └───┬────┘ └───┬────┘
              │          │          │
              └──────────┼──────────┘
                    ╲    │    ╱
                    ┌────┴─────┐
                    │Comparator│  横向对比 → 对比表 + 洞察
                    └────┬─────┘
                         │
                    ┌────┴─────┐
                    │  Writer  │  生成 Markdown 报告 (渐进输出)
                    └────┬─────┘
                         │
                    ⓸ 报告追问 (HITL, 用户主动触发, 可循环)
                         │
                        END
```

### 3.3 Agent 规格

#### 🧭 Planner (`graph/nodes/planner.py`)

| 项 | 内容 |
|----|------|
| 职责 | (1) 解析用户需求，识别赛道和关注维度；(2) 搜索发现候选竞品(8-10家)；(3) 根据确认的竞品 + 4 维模板生成报告大纲；(4) 通过 Send API 派发 Collector/Analyst 任务 |
| 工具 | `web_search`（用于竞品发现搜索） |
| 输入 | `query`, `user_specified_competitors`, `user_specified_dimensions` |
| 输出 | `candidate_competitors`, `confirmed_competitors`, `report_outline`, `analysis_dimensions` |
| HITL | 两次 `interrupt()`：竞品确认 + 大纲确认 |
| 模型 | Claude Sonnet（需要强推理能力） |

#### 🕷️ Collector (`graph/nodes/collector.py`)

| 项 | 内容 |
|----|------|
| 职责 | 围绕**单个竞品**执行多策略数据采集：官网抓取、社区搜索、应用商店评论 |
| 工具 | `web_search`, `web_scraper`, `reddit_search`, `app_reviews` |
| 输入 | `competitor_name`, `competitor_website`, `analysis_dimensions` |
| 输出 | `raw_sources: list[RawSource]`（追加到共享 state） |
| 策略 | 按维度逐项搜索：先 pricing 页 → 再 features → 再评论 → 再社区；受 `max_search_rounds` 约束 |
| 并发 | 通过 Send API fan-out，N 个竞品 = N 个并发 Collector 实例 |
| HITL | 数据不足时触发 `interrupt()` 请求用户补充 |
| 模型 | Claude Haiku（高性价比，简单的搜索+抓取决策） |

#### 📊 Analyst (`graph/nodes/analyst.py`)

| 项 | 内容 |
|----|------|
| 职责 | 对**单个竞品**的原始数据进行结构化分析：从 raw_sources 提取结构化字段 + 生成 EvidenceItem |
| 工具 | `structured_extract`（LLM 结构化输出） |
| 输入 | 该竞品的 `raw_sources`（从共享 state 中筛选） |
| 输出 | `CompetitorProfile`（含 4 维度结构化数据）+ `evidence_items: list[EvidenceItem]` |
| 关键约束 | 每个提取字段必须附带 `source_evidence_id`；evidence 必须保留原文 `excerpt` |
| 并发 | 通过 Send API fan-out，与 Collector 类似 |
| 模型 | Claude Haiku（结构化提取任务，Haiku 足够） |

> **注意**：旧设计中 Extraction 和 Analysis 是两个独立阶段。新设计将两者合并为 Analyst：先提取再分析，避免中间传递开销。Analyst 对单家竞品"从头到尾"负责。

#### 🆚 Comparator (`graph/nodes/comparator.py`)

| 项 | 内容 |
|----|------|
| 职责 | 汇聚所有 CompetitorProfile，执行横向对比分析 |
| 工具 | 无外部工具，纯 LLM 推理 |
| 输入 | `competitor_profiles: list[CompetitorProfile]`, `evidence_items`, `report_outline` |
| 输出 | `comparison_result: ComparisonResult`（对比表 + 关键洞察 + 每项附 evidence_ids） |
| 模型 | Claude Sonnet（需要强推理和综合判断能力） |

#### ✍️ Writer (`graph/nodes/writer.py`)

| 项 | 内容 |
|----|------|
| 职责 | 基于 report_outline + comparison_result + profiles + evidence 生成最终 Markdown 报告 |
| 工具 | `report_formatter`（Markdown 渲染） |
| 输入 | `report_outline`, `comparison_result`, `competitor_profiles`, `evidence_items` |
| 输出 | `report: Report`（Markdown + bibliography + evidence_chain） |
| 关键约束 | 所有结论必须有内联引用 `[N]` 对应 bibliography；渐进式输出（streaming） |
| 模型 | Claude Sonnet（报告写作质量优先） |

### 3.4 Gate 条件函数 (`graph/gates.py`)

```python
def gate_collection(state: AnalysisState, competitor_id: str) -> Literal["analyst", "hitl_insufficient", "skip"]:
    """单个 Collector 完成后判断数据是否充足"""
    sources = [s for s in state["raw_sources"] if s.competitor_id == competitor_id]
    if len(sources) >= 3:
        return "analyst"      # 数据足够,进入 Analyst
    if state["hitl_mode"] == "auto":
        return "skip"          # 演示模式,跳过不足的竞品
    return "hitl_insufficient" # 触发 HITL 询问用户

def gate_analysis(state: AnalysisState) -> Literal["comparator", "error"]:
    """所有 Analyst 完成后判断是否可以进入对比"""
    profiles = state["competitor_profiles"]
    if len(profiles) >= 2:     # 至少 2 家才能对比
        return "comparator"
    return "error"
```

---

## 4. 数据模型

> **实现备注**：当前 MVP 代码（`src/graph/state.py`）为简化版本，State 字段比以下设计更精简（M2 里程碑）。完整设计为 V2 目标。

### 4.1 LangGraph 状态 (`graph/state.py`)

```python
from typing import Annotated, Literal, TypedDict
import operator
from langgraph.graph import add_messages

class AnalysisState(TypedDict):
    # ── 运行元数据 ──
    run_id: str
    query: str
    hitl_mode: Literal["interactive", "auto"]  # auto = 演示模式,跳过所有 HITL

    # ── Planner 产出 ──
    candidate_competitors: list[dict]          # Planner 发现的候选 [{name, website, reason}]
    confirmed_competitors: list[dict]          # 用户确认的 [{name, website}]
    analysis_dimensions: list[str]             # 锁定的维度列表
    report_outline: dict | None                # 报告大纲 {sections: [...]}

    # ── 流程控制 ──
    current_stage: Literal[
        "planning", "collecting", "analyzing", "comparing", "writing", "complete", "error"
    ]
    stage_status: str                          # 人类可读进度描述
    active_agents: Annotated[list[dict], operator.add]  # [{agent_type, competitor, status}]
    retry_count: int
    max_retries: int
    error_message: str | None

    # ── Collector 产出 (并发追加) ──
    raw_sources: Annotated[list[RawSource], operator.add]
    search_queries_used: Annotated[list[str], operator.add]

    # ── Analyst 产出 (并发追加) ──
    competitor_profiles: Annotated[list[CompetitorProfile], operator.add]
    evidence_items: Annotated[list[EvidenceItem], operator.add]

    # ── Comparator 产出 ──
    comparison_result: ComparisonResult | None

    # ── Writer 产出 ──
    report: Report | None

    # ── 调试用 ──
    messages: Annotated[list, add_messages]
```

**Reducer 设计原则**：
- 并发 fan-out 的产出（raw_sources / profiles / evidence / active_agents）→ `operator.add`（追加合并）
- 单点产出（comparison_result / report / outline）→ 默认覆盖

### 4.2 域模型 (`schemas/domain.py`)

核心实体关系：

```
                    ┌─────────────────────────────┐
                    │         RawSource            │
                    │  source_id, url, content     │
                    │  competitor_id, retrieved_at  │
                    └──────┬──────────────────────┘
                           │ 1:N
                           ▼
                    ┌─────────────────────────────┐
                    │       EvidenceItem           │
                    │  evidence_id, source_id      │
                    │  excerpt, extracted_fact      │
                    │  fact_type, confidence        │
                    └──────┬──────────────────────┘
                           │ N:1
                ┌──────────┴──────────┐
                ▼                     ▼
    ┌───────────────────┐  ┌───────────────────────┐
    │ CompetitorProfile │  │  ComparisonResult     │
    │ name, positioning │  │  feature_comparison   │
    │ features, pricing │  │  pricing_comparison   │
    │ reviews           │  │  key_insights         │
    └───────────────────┘  └───────────────────────┘
                │                     │
                └──────────┬──────────┘
                           ▼
                    ┌─────────────────────────────┐
                    │          Report              │
                    │  content_markdown            │
                    │  bibliography                │
                    │  evidence_chain              │
                    └─────────────────────────────┘
```

关键字段（简版）：

```python
class RawSource(BaseModel):
    source_id: str              # UUID
    competitor_id: str          # 所属竞品
    url: str
    title: str | None
    raw_content: str            # 已去噪
    source_type: Literal["website", "app_store", "reddit", "zhihu", "news"]
    search_query: str
    retrieved_at: datetime

class EvidenceItem(BaseModel):
    evidence_id: str
    source_id: str
    source_url: str
    excerpt: str                # 原文片段（证据本体）
    extracted_fact: str         # 从原文中提炼的事实
    fact_type: Literal["positioning", "feature", "pricing", "review"]
    confidence: float           # 0.0-1.0
    competitor_id: str

class CompetitorProfile(BaseModel):
    competitor_id: str
    name: str
    website: str
    # 维度 1: 产品定位
    one_liner: str | None
    target_audience: list[str]
    core_scenarios: list[str]
    market_position: str | None
    # 维度 2: 核心功能
    features: list[Feature]                  # 每项含 evidence_id
    differentiators: list[str]
    recent_updates: list[str]
    tech_form: str | None                    # Web/桌面/插件
    # 维度 3: 定价
    pricing_tiers: list[PricingTier]         # 每项含 evidence_id
    pricing_strategy: str | None
    # 维度 4: 用户口碑
    overall_rating: float | None
    positive_themes: list[str]               # 好评聚类
    negative_themes: list[str]               # 吐槽聚类
    review_volume_trend: str | None

class ComparisonResult(BaseModel):
    comparison_id: str
    feature_comparison: list[FeatureComparison]    # 含 evidence_ids
    pricing_comparison: dict[str, list[PricingTier]]
    positioning_map: dict[str, str]                # competitor → 定位描述
    key_insights: list[str]                        # 横向对比核心洞察
    recommendations: list[str]
    evidence_ids_used: list[str]

class Report(BaseModel):
    report_id: str
    title: str
    executive_summary: str
    content_markdown: str                          # 含内联引用 [1] [2]
    source_bibliography: list[dict]                # [{url, title, accessed_at}]
    evidence_chain: dict[str, list[str]]           # conclusion_id → [evidence_id, ...]
```

### 4.3 证据链机制

> **核心差异化**：让每一个结论可追溯到原文 + Agent 推理过程。

五层链条：

```
[1] 报告中的论断 (Writer 生成)
    └─[2] ComparisonResult.key_insights[i].evidence_ids = ["e1","e2"]  (Comparator 生成)
          └─[3] CompetitorProfile.features[j].evidence_id = "e1"       (Analyst 生成)
                └─[4] EvidenceItem(e1): excerpt = "Cursor charges $20/mo..."
                      source_url = "https://cursor.com/pricing"         (Analyst 提取)
                      └─[5] RawSource: 完整原文 + 抓取时间              (Collector 采集)
```

前端证据下钻 UX：
```
用户点击报告结论 [N]
  → 弹出 EvidencePanel
    → 显示: 原文摘录 (excerpt)
    → 显示: 提炼事实 (extracted_fact)
    → 显示: 来源 URL (可点击跳转)
    → 显示: 抓取时间
    → 显示: 置信度分数
```

### 4.4 持久化模型

`models/*.py`（SQLModel）字段与 domain 模型对应，但增加：
- `id` 主键
- `created_at` / `updated_at`
- 外键：`AnalysisRun ─< Competitor ─< Evidence`，`AnalysisRun ─< Report`

LangGraph Checkpoint 独立存到 `data/checkpoints.db`，由 `AsyncSqliteSaver` 管理。

---

## 5. API 设计 (FastAPI)

### 5.1 端点列表

```
# 分析任务
POST   /api/v1/analysis                         创建分析任务 (202 Accepted)
GET    /api/v1/analysis                         列出历史任务（分页）
GET    /api/v1/analysis/{run_id}                任务详情 + 进度
GET    /api/v1/analysis/{run_id}/stream         SSE 事件流
DELETE /api/v1/analysis/{run_id}                取消任务

# HITL 交互
POST   /api/v1/analysis/{run_id}/hitl           提交 HITL 响应
GET    /api/v1/analysis/{run_id}/hitl/pending    获取当前等待的 HITL 请求

# 报告
GET    /api/v1/reports/{run_id}                 报告 JSON
GET    /api/v1/reports/{run_id}/markdown         报告 Markdown（下载）
GET    /api/v1/reports/{run_id}/evidence         完整证据链
GET    /api/v1/reports/{run_id}/evidence/{eid}   单条证据详情

# 系统
GET    /api/v1/health
GET    /api/v1/info                             可用 Provider/模型
```

### 5.2 关键请求/响应

**创建任务**

```http
POST /api/v1/analysis
Content-Type: application/json

{
  "query": "分析 AI Coding IDE 赛道的头部玩家，重点了解定价和开发者口碑",
  "competitors": ["Cursor", "Windsurf"],        // 可选：用户已知竞品
  "dimensions": ["pricing", "reviews"],          // 可选：重点关注维度
  "hitl_mode": "interactive",                    // interactive | auto
  "config": {
    "max_search_rounds": 3,
    "llm_provider": "anthropic"
  }
}

→ 202 Accepted
{
  "run_id": "uuid",
  "status": "planning",
  "stream_url": "/api/v1/analysis/uuid/stream"
}
```

**SSE 事件流**

```
event: agent_start
data: {"agent": "planner", "avatar": "🧭", "message": "正在分析需求..."}

event: hitl_request
data: {"hitl_id": "h1", "type": "competitor_confirm", "candidates": [...], "timeout": 30}

event: agent_start
data: {"agent": "collector", "instance": "cursor", "avatar": "🕷️", "message": "正在抓取 Cursor 官网..."}

event: agent_start
data: {"agent": "collector", "instance": "copilot", "avatar": "🕷️", "message": "正在搜索 Copilot 评论..."}

event: agent_complete
data: {"agent": "collector", "instance": "cursor", "sources_found": 8}

event: agent_start
data: {"agent": "analyst", "instance": "cursor", "avatar": "📊", "message": "正在分析 Cursor..."}

event: report_chunk
data: {"content": "## 1. 产品定位对比\n\n..."}

event: complete
data: {"report_url": "/api/v1/reports/uuid"}
```

**HITL 提交**

```http
POST /api/v1/analysis/{run_id}/hitl
{
  "hitl_id": "h1",
  "response": {
    "confirmed_competitors": ["Cursor", "Copilot", "Windsurf", "Cline", "Aider"]
  }
}
```

### 5.3 实现要点

- `BackgroundTasks` 启动 `graph.ainvoke(state, config={"configurable": {"thread_id": run_id}})`
- SSE 通过 `graph.astream_events()` 转换为前端事件
- HITL 通过 `interrupt()` 暂停 graph → 前端 SSE 收到 `hitl_request` → 用户提交 → `graph.update_state()` + `graph.ainvoke()` 续跑
- 取消通过 LangGraph 的 thread interrupt 实现
- 错误：5xx 返回 `{error_code, message, run_id?}`

---

## 6. 前端设计 (Next.js)

### 6.1 页面结构

**首页 `/`**
- 输入框：一句话需求
- 可折叠区域：手动添加竞品、选择关注维度
- hitl_mode 开关："演示模式"（默认关）
- 历史分析列表

**分析页 `/analysis/[id]`** — 核心页面，三栏布局
```
┌──────────────────────────────────────────────────────────────┐
│  Header: "分析 AI Coding IDE 赛道"          [导出] [分享]     │
├────────────────┬─────────────────────────────────────────────┤
│                │                                             │
│  Agent 进度流   │  报告区 / HITL 交互区                       │
│  (左侧 ~25%)   │  (右侧 ~75%)                               │
│                │                                             │
│  🧭 Planner ✓  │  ┌─ HITL 弹窗 (竞品确认) ─────────────┐    │
│  🕷️ Cursor ▶   │  │  □ Cursor                           │    │
│  🕷️ Copilot ▶  │  │  □ GitHub Copilot                   │    │
│  🕷️ Windsurf ▶ │  │  □ Windsurf                         │    │
│  📊 待分析...   │  │  ☑ Cline                            │    │
│                │  │  [确认] [全选] [跳过]                 │    │
│                │  └──────────────────────────────────────┘    │
│                │                                             │
│                │  (HITL 完成后显示渐进式报告)                  │
│                │  ## 1. 产品定位对比                          │
│                │  Cursor 定位为... [1]  ← 可点击查看证据      │
│                │                                             │
├────────────────┴─────────────────────────────────────────────┤
│  EvidencePanel (底部抽屉,点击引用后展开)                      │
│  📄 原文摘录 | 🔗 来源 URL | ⏰ 抓取时间 | 📊 置信度         │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 SSE 订阅机制

```typescript
// hooks/useSSE.ts
function useAnalysisSSE(runId: string) {
  // 订阅 /api/v1/analysis/{runId}/stream
  // 按 event type 分发:
  //   agent_start  → 更新 AgentFlow 组件
  //   agent_complete → 标记完成
  //   hitl_request → 弹出 HITLDialog
  //   report_chunk → 追加到 ReportView
  //   complete → 标记完成
}
```

### 6.3 HITL 前端流程

1. SSE 收到 `hitl_request` 事件
2. 弹出对应类型的 HITLDialog（竞品确认 / 大纲确认 / 补充链接 / 追问）
3. 用户操作后 POST `/api/v1/analysis/{id}/hitl`
4. 超时（30s）自动提交默认选项
5. Dialog 关闭，agent 流继续

---

## 7. CLI 设计 (Typer)

```bash
# 运行分析（直跑模式）
ca run "分析 AI Coding IDE 赛道" \
   --competitors "Cursor,Windsurf" \
   --hitl auto \
   --output report.md

# 运行分析（远端 API 模式）
ca run "..." --remote http://localhost:8000

# 查询状态
ca status <run_id>

# 列表
ca list --limit 20

# 导出报告
ca report <run_id> -o ./out/

# 查看证据链
ca evidence <run_id>

# 启动 API 服务
ca serve --host 0.0.0.0 --port 8000
```

---

## 8. 关键技术决策摘要

| 决策 | 选择 | 关键理由 |
|------|------|----------|
| Agent 数量 | 5 个(Planner/Collector/Analyst/Comparator/Writer) | 最小但完整的角色分工,能清晰展示多 Agent 协作 |
| 并发模式 | LangGraph Send API fan-out | Collector/Analyst 并发是视觉卖点 + 性能关键 |
| Agent 通信 | 黑板模式(共享 state) | 简单、可追溯、LangGraph 原生支持 |
| Extraction 合并 | 不单独设 ExtractionAgent | Analyst 对单家竞品端到端负责,减少传递开销 |
| HITL | LangGraph interrupt() | 原生支持,前端 SSE 订阅 + REST 提交 |
| 前端 | Next.js + SSE | 最成熟方案,自由度高,支持实时流 + 复杂交互 |
| LLM 分层 | Sonnet(Planner/Comparator/Writer) + Haiku(Collector/Analyst) | 推理重的用强模型,执行型用快模型 |
| 搜索 | Tavily | AI-native,结构化输出 |
| 抓取 | httpx + readability | 轻量、无浏览器依赖 |
| 数据库 | SQLite (MVP) → PostgreSQL | 零运维；升级路径清晰 |
| 流式输出 | SSE (sse-starlette) | 单向、低耦合、前端友好 |

---

## 9. 非功能性需求

| 维度 | 要求 |
|------|------|
| 可观测性 | 结构化日志（JSON）+ run_id 贯穿；SSE 事件同时用于前端展示和调试 |
| 重试 | tenacity 包装 LLM / Tavily / HTTP 调用，指数退避 |
| 限速 | Tavily / LLM 客户端层做并发上限（asyncio.Semaphore） |
| 隐私 | 抓取内容只缓存 24h；evidence excerpt 限长 |
| 成本控制 | 每 run 记 token / 搜索次数；超阈值告警 |
| 安全 | API Key 仅从环境变量读取；不写入日志/数据库 |

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| LLM 结构化输出失败 | `with_structured_output()` + 自动重试 + 兜底解析 |
| Tavily 限流/不可用 | tenacity 重试 + 缓存 + 后续引入 SerpAPI fallback |
| 长时分析超时 | LangGraph checkpoint 续跑 + SSE 进度通知 |
| 数据过时/有偏 | EvidenceItem 带 `retrieved_at` + `confidence`；UI 提示用户验证 |
| 大上下文超模型 | Analyst 只处理单家竞品(上下文受限)；大产物落文件 |
| 并发写 SQLite | WAL 模式；超过吞吐时升级 PostgreSQL |
| 比赛现场网络差 | 预录 trace + 本地缓存兜底（见 PRD §7.5） |
| Send API fan-out 部分失败 | gate 函数降级处理:≥2 家成功即可进入 Comparator |

---

## 11. 关联文档

| 文档 | 路径 | 职责 |
|------|------|------|
| 产品需求 | `product-requirements.md` | 场景、维度、HITL、Demo、成功标准 |
| 架构图 | `architecture.md` | 系统全景、通信、数据流、时序图 |
| 技术栈 | `tech-stack.md` | 依赖、选型理由、升级路径 |
| 实施计划 | `implementation-plan.md` | 分步计划、验收标准 |
| 进度 | `progress.md` | 当前状态 |
