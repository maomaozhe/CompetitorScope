# 架构文档 (Architecture)

> 竞品分析 Agent 协作系统的架构视图集合。配合 `design-document.md` 阅读。
>
> 最后更新：2026-05-12

---

## 1. 系统全景图

```
                          ┌──────────┐
                          │   用户   │
                          └────┬─────┘
                               │  一句话需求 + 可选补充
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js Web UI                                │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  InputForm   │  │  AgentFlow   │  │  ReportView +      │    │
│  │  需求输入     │  │  进度流(SSE) │  │  EvidencePanel     │    │
│  └──────┬───────┘  └──────▲───────┘  └─────────▲──────────┘    │
│         │  REST           │ SSE                │ REST           │
└─────────┼─────────────────┼────────────────────┼────────────────┘
          │                 │                    │
          ▼                 │                    │
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                                │
│  ┌────────────┐  ┌────────────┐  ┌─────────┐  ┌────────────┐  │
│  │POST        │  │GET         │  │POST      │  │GET         │  │
│  │/analysis   │  │/stream     │  │/hitl     │  │/reports    │  │
│  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  └─────┬──────┘  │
│        │               │              │               │          │
│        ▼               ▼              ▼               │          │
│  ┌──────────────────────────────────────────────┐     │          │
│  │         LangGraph StateGraph                  │     │          │
│  │                                               │     │          │
│  │  Planner → Collector×N → Analyst×N →          │     │          │
│  │  Comparator → Writer                          │     │          │
│  │                                               │     │          │
│  │  SharedState (黑板) + interrupt() (HITL)       │◄────┘          │
│  │  AsyncSqliteSaver (checkpoint)                │                │
│  └───────┬───────────┬────────────┬──────────────┘                │
│          │           │            │                               │
└──────────┼───────────┼────────────┼───────────────────────────────┘
           │           │            │
           ▼           ▼            ▼
     ┌──────────┐ ┌─────────┐ ┌──────────┐
     │ Tavily   │ │ httpx   │ │ Reddit   │
     │ Search   │ │ Scraper │ │ API      │
     └──────────┘ └─────────┘ └──────────┘
           │           │            │
           └───────────┼────────────┘
                       ▼
              ┌─────────────────┐
              │   SQLite        │
              │  data/app.db    │
              │  data/ckpt.db   │
              │  data/reports/  │
              └─────────────────┘
```

---

## 2. Agent 协作与通信图

### 2.1 Agent 角色关系

```
                    ┌──────────────────────────────┐
                    │        🧭 Planner            │
                    │  解析需求 / 发现竞品 / 出大纲   │
                    │  调度 Collector + Analyst      │
                    └──────┬─────────────┬─────────┘
                           │ Send×N      │ Send×N
              ┌────────────┤             ├────────────┐
              ▼            ▼             ▼            ▼
         ┌─────────┐ ┌─────────┐   ┌─────────┐ ┌─────────┐
         │🕷️ Coll-1│ │🕷️ Coll-2│   │📊 Ana-1 │ │📊 Ana-2 │
         │ Cursor  │ │ Copilot │   │ Cursor  │ │ Copilot │
         └────┬────┘ └────┬────┘   └────┬────┘ └────┬────┘
              │           │             │           │
              ▼           ▼             ▼           ▼
         ┌─────────────────────────────────────────────┐
         │        共享黑板 (AnalysisState)               │
         │  raw_sources: [...] ← Collector 追加         │
         │  competitor_profiles: [...] ← Analyst 追加   │
         │  evidence_items: [...] ← Analyst 追加        │
         └──────────────────┬──────────────────────────┘
                            │ 全部完成后
                            ▼
                    ┌──────────────────┐
                    │  🆚 Comparator   │
                    │  横向对比 + 洞察  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   ✍️ Writer      │
                    │  Markdown 报告   │
                    └──────────────────┘
```

### 2.2 黑板模式通信规则

```
┌─────────────┬────────────────────────┬─────────────────────────┐
│ Agent       │ 读取 (Read)            │ 写入 (Write)            │
├─────────────┼────────────────────────┼─────────────────────────┤
│ Planner     │ query, user_specified_*│ candidate_competitors   │
│             │                        │ confirmed_competitors   │
│             │                        │ report_outline          │
│             │                        │ analysis_dimensions     │
├─────────────┼────────────────────────┼─────────────────────────┤
│ Collector   │ confirmed_competitors  │ raw_sources (append)    │
│ (per comp.) │ analysis_dimensions    │ search_queries (append) │
├─────────────┼────────────────────────┼─────────────────────────┤
│ Analyst     │ raw_sources (filtered) │ competitor_profiles     │
│ (per comp.) │ analysis_dimensions    │ evidence_items (append) │
├─────────────┼────────────────────────┼─────────────────────────┤
│ Comparator  │ competitor_profiles    │ comparison_result       │
│             │ evidence_items         │                         │
│             │ report_outline         │                         │
├─────────────┼────────────────────────┼─────────────────────────┤
│ Writer      │ comparison_result      │ report                  │
│             │ competitor_profiles    │                         │
│             │ evidence_items         │                         │
│             │ report_outline         │                         │
└─────────────┴────────────────────────┴─────────────────────────┘

注意:
- raw_sources / evidence_items 使用 operator.add reducer → 并发安全追加
- 大产物(raw_content 原文)走文件引用,state 中只存摘要 + 文件路径
```

---

## 3. 数据流图

```
用户输入
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Planner                                                       │
│  query ──► Tavily 搜索赛道关键词 ──► 候选清单 (8-10家)        │
│  ──► [HITL ⓵] 用户确认 ──► 确认清单 (4-5家)                  │
│  确认清单 + 4维度 ──► 报告大纲                                 │
│  ──► [HITL ⓶] 用户确认大纲                                   │
└──────────────────────────────────────────────────────────────┘
  │ Send × N (每家竞品一个)
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Collector × N (并发)                                          │
│                                                               │
│  竞品名 ──► Tavily "Cursor pricing" ──► RawSource            │
│         ──► httpx 抓取官网 Pricing 页 ──► RawSource          │
│         ──► Reddit API "Cursor review" ──► RawSource         │
│         ──► httpx 抓取 App Store 页 ──► RawSource            │
│                                                               │
│  [Gate] 数据量 ≥3? → 继续 | <3 → [HITL ⓷] 用户补充         │
└──────────────────────────────────────────────────────────────┘
  │ raw_sources 写入共享 state
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Analyst × N (并发)                                            │
│                                                               │
│  raw_sources(筛选本竞品) ──► LLM 结构化提取                   │
│    ──► CompetitorProfile (4维度字段)                           │
│    ──► EvidenceItem × M (每个字段附证据)                       │
└──────────────────────────────────────────────────────────────┘
  │ profiles + evidence 写入共享 state
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Comparator                                                    │
│                                                               │
│  all profiles + evidence ──► LLM 横向对比推理                  │
│    ──► 功能对比表                                              │
│    ──► 定价对比表                                              │
│    ──► 定位分布图 (文字)                                       │
│    ──► 关键洞察 + 建议 (每条附 evidence_ids)                   │
└──────────────────────────────────────────────────────────────┘
  │ comparison_result 写入共享 state
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Writer                                                        │
│                                                               │
│  report_outline + comparison + profiles + evidence            │
│    ──► Markdown 报告 (streaming 输出)                         │
│       - 执行摘要                                              │
│       - 各维度对比章节                                         │
│       - 建议                                                  │
│       - 参考文献 bibliography                                  │
│       - 每个结论内联引用 [N]                                   │
│                                                               │
│  [HITL ⓸] 用户可追问某段 → 触发子图补充调研                   │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
Report (Markdown + evidence_chain + bibliography)
```

---

## 4. LangGraph StateGraph 结构

```python
# graph/workflow.py 伪代码

from langgraph.graph import StateGraph, Send, START, END

graph = StateGraph(AnalysisState)

# 节点
graph.add_node("planner_discover", planner_discover_node)     # 需求解析 + 竞品发现
graph.add_node("planner_outline", planner_outline_node)       # 大纲生成
graph.add_node("collector", collector_node)                    # 单竞品采集 (fan-out)
graph.add_node("analyst", analyst_node)                        # 单竞品分析 (fan-out)
graph.add_node("comparator", comparator_node)                  # 横向对比
graph.add_node("writer", writer_node)                          # 报告生成

# 边
graph.add_edge(START, "planner_discover")
graph.add_edge("planner_discover", "planner_outline")           # 含 interrupt() ⓵
graph.add_conditional_edges("planner_outline", fan_out_collectors)  # 含 interrupt() ⓶
# fan_out_collectors 返回 [Send("collector", {competitor: "Cursor"}), ...]
graph.add_conditional_edges("collector", gate_collection)       # 判断数据量
graph.add_conditional_edges("gate_ok", fan_out_analysts)
# fan_out_analysts 返回 [Send("analyst", {competitor: "Cursor"}), ...]
graph.add_edge("analyst", "wait_all_analysts")                  # 汇聚点
graph.add_conditional_edges("wait_all_analysts", gate_analysis)
graph.add_edge("comparator", "writer")
graph.add_edge("writer", END)

# 编译
app = graph.compile(
    checkpointer=AsyncSqliteSaver.from_conn_string("data/checkpoints.db"),
    interrupt_before=[]  # interrupt 在节点内部通过 interrupt() 函数调用
)
```

**Fan-out 路由函数**:

```python
def fan_out_collectors(state: AnalysisState) -> list[Send]:
    """为每个确认的竞品创建一个 Collector 实例"""
    return [
        Send("collector", {"competitor": comp})
        for comp in state["confirmed_competitors"]
    ]
```

---

## 5. HITL 时序图

```
前端 (Next.js)          后端 (FastAPI)           LangGraph
─────────────          ──────────────           ─────────
                                                  │
POST /analysis ──────►  创建 run                  │
                        BackgroundTasks ──────────► graph.ainvoke()
                                                  │
SSE /stream ◄─────────  astream_events() ◄────────┤ Planner 运行中...
  agent_start                                     │
  agent_start                                     │
                                                  │
SSE ◄─────────────────  hitl_request ◄────────────┤ interrupt()
  弹出竞品确认弹窗                                  │ (graph 暂停)
  │                                               │
  │ 用户勾选确认                                    │
  │                                               │
POST /hitl ──────────►  update_state() ───────────► graph 恢复执行
                        ainvoke(resume) ──────────► Planner 继续...
                                                  │
SSE ◄─────────────────  agent_start ◄─────────────┤ Collector×N fan-out
  🕷️ Cursor ▶                                     │
  🕷️ Copilot ▶                                    │
  🕷️ Windsurf ▶                                   │
                                                  │ (并发采集)
SSE ◄─────────────────  agent_complete ◄──────────┤
  🕷️ Cursor ✓                                     │
SSE ◄─────────────────  agent_start ◄─────────────┤ Analyst×N fan-out
  📊 Cursor ▶                                     │
                                                  │ (并发分析)
                                                  │
SSE ◄─────────────────  report_chunk ◄────────────┤ Writer streaming
  渐进式报告渲染                                    │
                                                  │
SSE ◄─────────────────  complete ◄────────────────┤ END
  显示完整报告 + 证据锚点                           │
```

---

## 6. 存储架构

```
data/
├── app.db              # 业务数据 (SQLModel)
│   ├── analysis_run    # 分析任务记录
│   ├── competitor      # 竞品基础信息
│   ├── evidence        # 证据项
│   └── report          # 报告元数据
│
├── checkpoints.db      # LangGraph checkpoint
│   └── (内部管理)       # 每个 step 的完整 state 快照
│
├── reports/            # 报告文件
│   └── {run_id}.md     # Markdown 报告
│
└── raw/                # 原始抓取内容 (大产物,不进 state)
    └── {run_id}/
        └── {source_id}.txt   # 原始网页内容
```

**为什么大产物不放 state**：
- 一个竞品可能抓 5-10 个网页,每个 10-50KB
- 5 家竞品 × 10 页 × 30KB = ~1.5MB 纯文本
- 放进 state 会导致 checkpoint 膨胀 + 每次 LLM 调用传入过多上下文
- 解决：Collector 将 raw_content 写入文件,state 中的 RawSource 只存 file_path + 摘要

---

## 7. 关键架构约束

| 约束 | 原因 | 实现方式 |
|------|------|----------|
| Agent 上下文隔离 | 避免单个 LLM 调用超过上下文限制 | Analyst 只接收单家竞品的 sources,不看其他竞品 |
| 并发写入安全 | 多个 Collector/Analyst 同时写 state | operator.add reducer 保证追加合并 |
| 大产物外置 | 防止 state/checkpoint 膨胀 | raw_content → 文件系统,state 存引用 |
| HITL 非阻塞 | 演示模式要流畅 | hitl_mode="auto" 时 interrupt 直接返回默认值 |
| 降级容错 | 部分竞品采集失败不阻塞全局 | gate 函数:≥2 家成功即可进入 Comparator |
| 证据链完整 | 核心差异化 | 每层产出都带 evidence_id/source_id 引用 |
