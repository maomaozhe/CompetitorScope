# CS-001: Official Pricing Evidence Slice

- Status: Complete
- Priority: P0 for V2
- Decision: [ADR-0001](../adr/0001-evidence-first-pipeline.md)

## Goal

交付 V2 第一个端到端纵向切片：从显式官方定价 URL，或已知 official domain 内发现的定价页，保存稳定 `SourceDocument` snapshot，抽取原子 `PricingClaim`，绑定 exact quote/span，通过确定性 `Verifier` 生成 `VerifiedClaim`，最后持久化机器可评测 JSON 并在 CLI 打印证据摘要。

完成后，固定 snapshot 上的官方定价事实应可复核、可重放、可重复评测，同时 V1 LangGraph Baseline 保持原样可运行。

## Non-goals

- 不生成通用竞品分析或正式 Markdown 报告。
- 不抽取功能、套餐权益、额度、用户评论或市场定位。
- 不验证税费、促销、优惠券或限时折扣；发现时记录 unsupported/needs-review。
- 不新增或承诺 `/api/v2`。
- 不修改 V1 graph、nodes、state、API、domain model 或前端。
- 不迁移、替换或重构 V1 LangGraph runtime。
- 不接入 pi Runtime、OpenViking、MiniViking 或 MCP。
- 不把搜索 snippet 当作 Evidence。
- 不实现浏览器渲染、登录态抓取或人工审批流程。

## Input / Output

### Application input

| Field | Required | Description |
|---|---:|---|
| `competitor` | yes | 产品或竞品显示名称 |
| `official_domain` | yes | 已确认的官方域名，规范化后用于 authority 检查 |
| `pricing_url` | no | 显式官方定价页；有值时跳过 discovery |
| `locale` | no | BCP 47 locale，默认 `und` |
| `as_of` | no | ISO 8601 UTC 观察时间；缺省使用 runtime clock |
| `output_path` | no | JSON 输出位置；缺省由 CLI 生成 run 目录 |

首版 CLI 约定：

```text
uv run python scripts/run_pricing_evidence.py \
  --competitor NAME \
  --official-domain DOMAIN \
  [--pricing-url URL] \
  [--locale LOCALE] \
  [--as-of ISO8601] \
  [--output PATH]
```

### Output

主产物是符合 `pricing-evidence.v1` 的 `PricingEvidenceResult` JSON，包含 run manifest、source documents、candidate claims、evidence、verified claims 和 issues。

终端摘要只把 `verified_claims` 显示为事实，并为每项显示 plan、price、billing semantics、source URL 和 quote。Rejected/needs-review 只显示为诊断，不得混入已确认事实。

退出状态必须区分：

- 成功完成且可有零条 verified facts；
- 输入无效；
- pipeline/system failure；
- result 写入失败。

“页面没有可验证价格”是结构化成功结果，不等同于系统异常。

## Data contracts

实现必须使用 [DOMAIN_MODEL](../v2/DOMAIN_MODEL.md) 定义的：

- `SourceDocument`
- `Evidence`
- `PricingClaim`
- `VerifiedClaim`
- `PricingEvidenceResult`
- `Issue`

额外要求：

- raw snapshot ID 等于 raw payload SHA-256；同内容重试必须复用同一 snapshot。
- `official_domain` 按小写 IDNA hostname 规范化并移除端口和末尾点；final hostname 必须等于它或是其点边界子域名，禁止使用字符串包含判断。
- Evidence span 基于已保存 normalized text 的零基字符位置。
- `fixed` claim 必须有 decimal amount；`free` 和 `contact_sales` 不得携带 amount。
- 页面未显示 currency 时不得从 official domain、locale 或模型知识推断。
- 年付折算月价必须携带 `billed_annually` qualifier。
- Candidate、verification checks、组件版本和 issues 必须保留在 JSON，便于 eval 和诊断。

## Invariants

1. 搜索 snippet 只能用于 discovery。
2. 每个 `PricingClaim` 必须绑定 `Evidence`，每个 `Evidence` 必须绑定已保存的 `SourceDocument`。
3. `exact_quote` 必须严格等于 normalized snapshot 的 span 切片。
4. LLM 输出不能直接构造 `VerifiedClaim` 或写 durable verified state。
5. 只有 `VerifierPort` 能产生 `VerifiedClaim`。
6. JSON facts 和 CLI 事实摘要只能读取 `verified_claims`。
7. 任一关键 authority、hash、span、quote 或字段支持检查失败时 fail closed。
8. Runtime、Tool、ContextProvider、Verifier 不能相互依赖具体 adapter SDK 类型。
9. V1 LangGraph 必须在 CS-001 前后保持可运行。
10. 任何 Agent/extractor 行为变化必须更新 eval case。

## Allowed change surface

未来实施 CS-001 时允许：

- 新增 `src/v2/**`；
- 新增薄 CLI `scripts/run_pricing_evidence.py`；
- 新增 `evals/**`；
- 新增 V2 专属测试，例如 `tests/v2/**`；
- 更新 `docs/v2/STATUS.md` 和本任务状态；
- 在不引入新生产依赖的前提下使用仓库已有库。

禁止：

- 修改 `src/graph/**`；
- 修改 `src/api/v1/**`；
- 修改 V1 `src/schemas/domain.py`；
- 修改 `web/**`；
- 改变现有测试的断言以掩盖回归；
- 重命名或删除 V1 公共 API 字段；
- 新增生产依赖，除非拆分为独立决策并获得明确批准。

若实现发现必须越过允许范围，应停止任务并先更新任务规格或新增 ADR，不得顺手重构。

## Acceptance criteria

- 显式 pricing URL 路径和 official-domain discovery 路径均端到端工作。
- 成功来源保存 raw 与 normalized 内容寻址 artifact、hash 和完整 metadata。
- 每条 verified pricing fact 都能重放到 exact quote/span。
- 非官方 redirect、quote mismatch 或缺失字段不会产生 `VerifiedClaim`。
- 支持 Free、固定月价、固定年价、年付折算月价和 Contact sales。
- 税费、促销和权益内容不会被误报为首版 verified pricing fact。
- JSON 严格符合 `pricing-evidence.v1`，CLI 事实摘要只来自 verified claims。
- 固定输入重复运行的 canonical semantic JSON 一致。
- [EVAL_SPEC](../v2/EVAL_SPEC.md) 的所有硬门槛通过，包括 eligible recall >= 90%。
- V1 现有测试继续通过，且 `src/graph/**`、`src/api/v1/**`、V1 domain 和 `web/**` 无行为修改。
- pi Runtime、OpenViking、MiniViking 和 MCP 均不是运行或测试依赖。

## Test cases

### Domain and verifier unit tests

- 稳定 ID 和 content hash 可重复。
- Decimal amount 序列化无 float 漂移。
- Free、fixed、contact-sales 的条件字段校验。
- Span 边界、空 quote、quote hash mismatch 和 source-not-found 全部 fail closed。
- Annual effective monthly 只有在 quote 支持 annual qualifier 时通过。
- Result writer 拒绝把 candidate/rejected item 写入 facts。

### Offline pipeline tests

- 显式官方 URL 跳过 discovery。
- 缺省 URL 只接受 official domain 候选。
- Free、月价、年价、年付折算价、Contact sales、多币种 fixtures。
- 相同内容的重复 URL 不重复 snapshot 或 verified fact。
- 非官方 redirect、无价格、抓取失败、unsupported media、动态/登录墙 fixture。
- 税费、促销、套餐权益进入 issue，不进入 verified facts。
- 固定 snapshot 重放得到相同 canonical semantic JSON。

### Compatibility tests

- 运行现有 V1 后端测试，确认 Baseline 未受影响。
- 静态检查 CS-001 diff 未修改禁止路径。
- V2 imports 不引用 V1 graph state、LangGraph runtime 或具体 context 产品。

Live-web smoke test 可人工运行，但结果不计入离线 acceptance gate。

## Failure modes

| Failure | Required result |
|---|---|
| Discovery 无候选 | 成功返回零事实和 `pricing-page-not-found` issue |
| Fetch timeout/HTTP error | 不执行 extraction，记录稳定 fetch issue |
| 非官方 redirect | 保存诊断 metadata，禁止 verified claim |
| Snapshot 写入失败 | pipeline failure，不使用内存文本绕过 durable source |
| Normalization 失败 | 标记 unsupported/failed，不执行 extraction |
| Extractor 非法输出 | 保留诊断，不宽松补字段 |
| Quote/span/hash mismatch | rejected，不能升级为 verified |
| Currency/period 不明确 | needs_review 或 rejected，不猜测 |
| 部分 claim 失败 | 保留其他 verified claims，并逐项记录 issue |
| JSON 写入失败 | 返回 write failure；snapshot 保留且可安全重试 |

## Rollback strategy

CS-001 与 V1 无共享迁移和公共 API 变更。回滚时：

1. 禁用或移除独立 `run_pricing_evidence.py` 入口。
2. 回滚新增的 `src/v2/**`、`evals/**` 和 V2 专属测试。
3. 保留或清理内容寻址 artifacts 均不影响 V1；清理必须按明确 run/output 路径执行，不扫描删除 V1 数据。
4. 无需迁移或回滚 V1 database、LangGraph checkpoint、API 或前端。
5. 回滚后运行 V1 测试，确认 Baseline 仍保持原行为。

如果只需回滚某个 adapter，应替换对应 port 实现，保留 domain、golden fixtures 和 eval history，以便比较回归原因。

## Completion evidence

- 实现范围：`src/v2/**`、`scripts/run_pricing_evidence.py`、`evals/**`、`tests/v2/**`。
- 完整测试：`uv run pytest tests/ -q`，26 passed。
- 静态检查：`uv run ruff check src tests scripts/run_pricing_evidence.py evals`，通过。
- Eval runner：全部确定性指标 100%，unsupported verified claims 为 0。
- Live smoke：GitHub Copilot 官方 billing 页面输出 5 条 verified pricing facts，所有输出均绑定已保存 quote/span。
- Compatibility：未修改 V1 LangGraph、V1 API、V1 domain、前端或既有测试。
