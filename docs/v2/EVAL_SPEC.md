# CompetitorScope V2 Evaluation Specification

## Current

V1 测试主要验证 workflow、HITL、SSE 和报告格式，没有固定官方定价 snapshot 或 claim-level 质量指标。V2 eval dataset 和 graders 尚未实现。

## Decision

CS-001 使用仓库内固定 golden snapshot 做离线、可重复评测。Live web 只能作为观察性检查，不能作为确定性 CI gate，也不能更新 golden expectation。

### Evaluation unit

一个 eval case 至少包含：

- competitor 和 official domain；
- 可选显式 pricing URL；
- locale 和固定 as-of；
- raw response fixture、redirect metadata 和期望 normalized text；
- eligible golden `PricingClaim`；
- 对每个 golden claim 的 exact quote 与 span；
- 预期 issues；
- extractor、parser 和 verifier 的固定版本配置。

Fixture 是测试输入，不是运行时搜索 snippet。Golden snapshot 变更必须经过人工 review，并说明来源内容或 parser 变化。

### Required cases

| Case | Expected behavior |
|---|---|
| 显式官方 pricing URL | 不执行 discovery，保存 snapshot 并抽取事实 |
| 无显式 URL | 只在 official domain 内发现候选页 |
| Free plan | `price_kind=free`，amount/currency 为空 |
| 固定月价 | amount、currency、month 与 quote 一致 |
| 固定年价 | amount、currency、year 与 quote 一致 |
| 年付折算月价 | 保留 `billed_annually` qualifier |
| Contact sales | `price_kind=contact_sales`，不虚构金额 |
| 多币种 | 每个价格只使用对应 quote 的币种，不跨 locale 合并 |
| 重复页面/URL | 相同 raw hash 复用 snapshot，结果不重复计数 |
| 非官方 redirect | 不产生 `VerifiedClaim`，记录 authority issue |
| Quote/span 不匹配 | fail closed，进入 rejected issue |
| 无价格页面 | verified list 为空，并明确记录 no-pricing-found |
| 抓取失败 | 不进入 extraction，返回稳定 fetch issue |
| 税费/促销/权益 | 标记 unsupported 或 needs_review，不生成对应 VerifiedClaim |

动态渲染、登录墙或地区阻断页面在首版作为 `blocked`/`unsupported` 失败用例，不承诺浏览器渲染能力。

### Graders and metrics

1. **Source provenance**：每个 Evidence 和 VerifiedClaim 都能解析到已保存 `SourceDocument`。
2. **Quote replay**：span 切片严格等于 exact quote，quote hash 一致。
3. **Authority**：官方 claim 的 final URL host 必须符合规范化 official domain policy。
4. **Field support**：plan、display price、amount、currency、period 和 qualifier 均能从 Evidence 确定性支持。
5. **Claim precision/recall**：按规范化原子 claim 与 golden 集合比较。
6. **Output isolation**：result facts 和 CLI 事实摘要只来自 `verified_claims`。
7. **Replay determinism**：排除 run ID、抓取/验证时间等明确非语义字段后比较 canonical JSON。

### Release gates

| Metric | Gate |
|---|---:|
| Source provenance validity | 100% |
| Quote/span replay validity | 100% |
| Unsupported verified claims | 0 |
| Verified pricing field precision | 100% |
| Eligible golden claim recall | >= 90% |
| Semantic replay determinism | 100% |

任何硬门槛失败都阻止 CS-001 完成。不能用平均分掩盖无效引用、非官方来源或未经验证事实。

### Baseline comparison

V1 可对相同 competitor 运行以收集 Baseline 输出，但 V1 live-web 结果不作为 CS-001 golden truth。比较报告应分别展示：

- V1 输出的定价文本；
- V2 candidate claims；
- V2 verified claims；
- V2 rejected/needs-review issues。

V2 的发布门槛由上述确定性指标决定，不要求伪造 V1 与 V2 字段兼容。

## Planned

每次 extractor、parser、context selection、verification rule 或输出行为变化，必须新增或更新对应 case，并在变更说明中报告门槛结果。未来扩展新的事实类型时应建立独立 dataset，不能稀释官方定价集的门槛。
