# CLAUDE.md

CompetitorScope 项目的 Claude Code 工作指引。

## 项目概述

CompetitorScope 是多 Agent 竞品分析系统，基于 LangGraph 工作流编排 5 个专业 Agent（Planner → Collector → Analyst → Comparator → Writer）生成竞品分析报告。

**当前状态**：Step 7/8 API + 前端主链路已完成，Step 9 Demo 打磨阶段。
当前进度和进行中 bug 见 `doc/memory-bank/progress.md` 和 `doc/memory-bank/bug.md`。

## 架构

### 后端 `src/` — Python/FastAPI + LangGraph

```
src/
├── main.py                    # FastAPI 入口
├── config.py                  # Pydantic Settings
├── api/v1/                    # REST API 端点
├── graph/
│   ├── state.py               # AnalysisState TypedDict
│   ├── workflow.py            # StateGraph（5 Agent 串行）
│   └── nodes/                 # 各 Agent 节点
├── schemas/domain.py          # Pydantic 模型
├── services/llm.py            # LLM 工厂
└── tools/                     # 工具层
```

### 前端 `web/` — Next.js 15

## 数据流

```
query → Planner(发现竞品+大纲) → Collector(采集) → Analyst(分析) → Comparator(对比) → Writer(报告)
         ↓ HITL              ↓              ↓             ↓
      竞品确认           采集确认         分析确认       对比确认
```

## AnalysisState

```python
class AnalysisState(TypedDict, total=False):
    run_id: str
    query: str
    confirmed_competitors: list[dict]
    analysis_dimensions: list[str]
    report_outline: str
    current_stage: Literal["planning","collecting","analyzing","comparing","writing","complete","error"]
    raw_sources: Annotated[list[RawSource], operator.add]
    competitor_profiles: Annotated[list[CompetitorProfile], operator.add]
    evidence_items: Annotated[list[EvidenceItem], operator.add]
    comparison_result: ComparisonResult | None
    report: Report | None
```

## API 端点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/analysis` | 创建分析任务 |
| GET | `/api/v1/analysis/{run_id}/stream` | SSE 实时事件流 |
| GET | `/api/v1/analysis/{run_id}` | 获取状态 |
| DELETE | `/api/v1/analysis/{run_id}` | 取消任务 |
| GET | `/api/v1/analysis/{run_id}/hitl/pending` | HITL 待处理请求 |
| POST | `/api/v1/analysis/{run_id}/hitl` | 提交 HITL 响应 |
| GET | `/api/v1/reports/{run_id}` | 获取报告 |
| GET | `/api/v1/reports/{run_id}/evidence` | 证据链 |

## 项目规则

1. 称呼规则：每次回复前使用 "maomao" 作为称呼
2. 决策确认：遇到不确定的代码设计，必须先询问 maomao，不可直接行动
3. 代码兼容：不写兼容性代码，除非主动要求
4. Commit 规范：完成功能/需求后 commit，commit 前和 maomao 确认，按开源方式规范
5. 状态更新：每次完成功能/需求要更新 `progress.md`，让后续 agent 能识别进展

## 验证标准

每次完成功能后，必须自行验证：

1. **网页应用**：Playwright 或 DevTools 验证
2. **有说服力的证明**：截图/录屏证据，保存到 `docs/review/<feature>/`
3. **严格人工判定**：截图只是证据不是通过条件，逐张检查 URL、状态、文案、布局、弹窗、报告，符合预期才能写 pass

## 工程教训（避免重蹈覆辙）

- LangGraph `interrupt()` 只能在节点内部调用，不能替代条件边
- `operator.add` reducer 保证并发追加时数据不丢失，但字段类型必须正确声明
- 大产物（raw_content）应落文件而不是放 state，避免 checkpoint 膨胀
- CLAUDE.md 更新时必须基于 `progress.md` 实际状态，不能凭记忆

## 参考
需要的时候再看
- 当前状态：`doc/memory-bank/progress.md`
- 实施计划：`doc/memory-bank/implementation-plan.md`
- 进行中 bug：`doc/memory-bank/bug.md`
- 待开发需求：`doc/PRD.md`