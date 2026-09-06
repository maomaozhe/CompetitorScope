# CompetitorScope V2 Vision

## Current

CompetitorScope V1 是基于 LangGraph 的竞品分析 Baseline，提供竞品发现、网页采集、画像分析、横向比较、Markdown 报告、HITL 和 SSE 事件流。V1 必须继续保持可运行，用于行为回归和 V2 效果对照。

当前仓库尚未实现 V2 的 `SourceDocument`、原子 `PricingClaim`、确定性 `Verifier` 或离线 eval 数据集。本文描述的是 V2 产品方向，不代表现有能力。

## Decision

CompetitorScope V2 的产品目标是构建 evidence-first、eval-first 的竞品情报 Agent：系统先保存可复核来源，再生成原子事实声明，将声明绑定到精确证据，通过验证后才允许进入面向用户的结果。

核心信息链为：

```text
SourceDocument snapshot
  -> Evidence with exact quote/span
  -> candidate PricingClaim
  -> Verifier
  -> VerifiedClaim
  -> result/report
```

V2 必须满足以下产品原则：

1. 搜索结果和 snippet 只用于发现来源，不能作为最终 Evidence。
2. 每个事实声明必须引用已保存的 `SourceDocument` snapshot。
3. 每个 `Evidence` 必须包含精确 quote 和可确定性重放的 span。
4. 只有通过 `Verifier` 的 `VerifiedClaim` 才能进入事实结果或报告。
5. LLM 只能提出 candidate claim，不能直接写入 durable verified state。
6. 每次 Agent 行为变化都必须新增或更新 eval case。
7. 固定输入与固定 snapshot 必须支持可重复评测。
8. V1 LangGraph 与 V2 独立演进，V1 始终保留为可运行 Baseline。

成功不是“生成更长的报告”，而是以下能力可以被自动证明：

- 来源可复核：事实能够定位到稳定 snapshot。
- 引用可重放：quote 与 span 能从 snapshot 确定性恢复。
- 声明受支持：结构化事实与引用表达的语义一致。
- 结果受约束：未经验证的事实无法绕过类型和流程进入输出。
- 效果可回归：同一 eval dataset 能比较 Baseline 与候选实现。

## Non-goals

pi Runtime、OpenViking、MiniViking 和 MCP 不是产品目标。它们未来可以作为可替换 adapter 或集成机制，但 V2 的领域模型、验证规则和评测标准不得依赖它们，CS-001 也不以接入它们为完成条件。

首个纵向切片不处理：

- 通用竞品分析报告；
- 用户评论和情感；
- 产品功能、套餐权益和使用额度；
- 税费、促销、优惠券和限时折扣；
- V1 runtime 迁移或 LangGraph 替换；
- `/api/v2` 公共 HTTP API；
- 前端改造。

## Planned

第一个纵向切片 CS-001 只处理官方定价事实。它将验证从官方定价页到持久化 JSON 结果的完整证据链，并以薄 CLI 提供人工检查入口。

CS-001 完成后，只有在 eval 证明该链路可靠的前提下，才逐步扩展到功能、定位、评论和综合报告。任何 runtime、tool 或 context provider 的替换，都应当在不改变领域契约和 eval 口径的情况下进行。

架构决策见 [ADR-0001](../adr/0001-evidence-first-pipeline.md)，首个任务规格见 [CS-001](../tasks/CS-001-pricing-evidence-slice.md)。
