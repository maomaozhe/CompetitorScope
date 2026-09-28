# 旧路线封存索引

> 2026-09-28：原 V1 竞品分析及此前 `src/v2/` 官方定价方案停止作为主动开发路线。封存保留源码、历史设计、测试记录和运行说明；不删除或宣称当前仍持续维护。新功能集中在 [`repo_research_poc`](../../repo_research_poc/README.md)，当前需求见[产品 PRD](../../doc/PRD.md)。

## V1 竞品分析

- [中文历史运行说明](README.md)、[English historical guide](README.en.md)：原 FastAPI、LangGraph、Next.js 竞品分析流程及当时的启动命令。
- [历史 PRD](PRD.md)：原 Demo 的 P0/P1/P2 待办；这些待办已停止排期。
- [可观测性与评测回放](OBSERVABILITY.md)：原 V1 功能设计与运行记录。
- [历史进度](../../doc/memory-bank/progress.md)：早期里程碑保留在“封存历史”部分。
- [历史实施计划](../../doc/memory-bank/implementation-plan.md)、[历史 Bug 列表](../../doc/memory-bank/bug.md)：原 Step 框架和未完成项，不再排期。

## 此前的 V2 官方定价方案

`src/v2/`、`docs/v2/` 的官方定价纵向切片与 `CS-001` 曾是另一条研发方向，现不作为源码研究 POC 的实施计划。它们的已完成事实仍由各自代码与历史测试记录说明，但后续里程碑已暂停。

- [原 Vision](../v2/VISION.md)、[架构](../v2/ARCHITECTURE.md)、[领域模型](../v2/DOMAIN_MODEL.md)、[评测规格](../v2/EVAL_SPEC.md)、[状态记录](../v2/STATUS.md)
- [ADR-0001](../adr/0001-evidence-first-pipeline.md)、[CS-001 任务规格](../tasks/CS-001-pricing-evidence-slice.md)

当前源码研究规格虽然位于 `docs/v2/`，应以[源码研究产品规格](../v2/REPOSITORY_RESEARCH.md)为准；不要把上述官方定价方案的 `PricingClaim` 或旧 V1 Demo 待办当作新主线的默认需求。
