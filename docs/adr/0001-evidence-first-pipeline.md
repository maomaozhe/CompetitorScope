# ADR-0001: Adopt an independent evidence-first pipeline

- Status: Accepted
- Date: 2026-09-06
- Owners: CompetitorScope maintainers

## Context

CompetitorScope V1 是可运行的 LangGraph 竞品分析 Baseline，但当前 Source、Evidence、Profile 和 Report 之间主要由提示词和自由字符串维持。现有流程不能强制每个报告事实绑定到稳定 snapshot，也不能确定性证明 quote 与 source 匹配。

V2 需要支持可验证事实和可重复 eval，同时避免破坏 V1 API、前端、HITL 和演示能力。未来可能采用不同 runtime、tool 或 context provider，但这些技术选择不应决定产品目标或领域模型。

## Decision

1. 新建独立 V2 evidence-first pipeline，不在 V1 LangGraph 中原地替换节点。
2. V1 LangGraph 作为可运行 Baseline 保留；V2 通过独立 application service 和 adapter 演进。
3. 搜索结果及 snippet 只用于 discovery，最终 Evidence 必须引用已保存的 `SourceDocument` snapshot。
4. Evidence 必须包含 exact quote 和 deterministic span。
5. LLM 或其他 extractor 只能生成 candidate claim；只有 `VerifierPort` 可以构造 `VerifiedClaim`。
6. Result writer 或未来 Reporter 只能消费 `VerifiedClaim` 作为事实输入。
7. Runtime、Tool、ContextProvider、Verifier 通过独立 ports 解耦，domain 不依赖其具体实现。
8. 首个纵向切片只处理官方定价事实，并以离线 golden snapshot eval 作为完成门槛。
9. pi Runtime、OpenViking、MiniViking 和 MCP 只可能作为未来 adapter；它们不是产品目标，也不是 CS-001 依赖。

## Consequences

### Positive

- V1 可以持续运行并作为效果、成本和行为 Baseline。
- V2 的事实链可以逐项验证，而不是依赖提示词承诺。
- 固定 snapshot 使离线回归和组件替换比较成为可能。
- runtime、搜索、fetch、context 和 verifier 可以独立演进。
- Strangler 迁移允许按事实类型逐步扩展，降低一次性重写风险。

### Costs and constraints

- V1 与 V2 在迁移期存在两套领域模型和执行入口。
- Snapshot、稳定 ID、版本记录和 eval fixtures 增加存储与维护成本。
- Fail-closed 会使首版结果更少，但不会用未验证内容填补空缺。
- 如需展示 V1/V2 对照，需要显式 Legacy Adapter，不能直接共享 mutable state。

## Alternatives

### Directly extend V1 `EvidenceItem`

Rejected。V1 Comparator 和 Writer 仍可绕过 Evidence 消费 profile 自由文本，单独扩字段不能建立 verified-only 边界，并会提高破坏 Baseline 的风险。

### Replace LangGraph or adopt a new runtime first

Rejected。Runtime 不是当前事实质量问题的根因。先迁移 runtime 无法提供 snapshot、claim verification 或 eval，并会把产品进展绑定到技术重构。

### Treat search snippets as evidence

Rejected。Snippet 不稳定、不完整且通常无法提供可重放 span，只能作为发现信号。

### Let Reporter decide whether a claim is trustworthy

Rejected。自由文本生成阶段不能承担 durable verification；这会允许不受支持的事实绕过结构化检查。

### Make pi, OpenViking, MiniViking, or MCP the V2 objective

Rejected。这些是潜在实现或集成选择，不是用户价值或可验证性标准。核心 pipeline 必须在没有这些组件时成立。

## References

- [V2 Vision](../v2/VISION.md)
- [V2 Architecture](../v2/ARCHITECTURE.md)
- [V2 Domain Model](../v2/DOMAIN_MODEL.md)
- [V2 Eval Specification](../v2/EVAL_SPEC.md)
- [CS-001](../tasks/CS-001-pricing-evidence-slice.md)
