# CompetitorScope V2 Domain Model

## Current

V1 的 `RawSource`、`EvidenceItem`、`CompetitorProfile` 和 `Report` 继续服务于 Baseline。它们不作为 V2 类型的父类，也不在 CS-001 中原地扩展。

以下为计划中的 V2 首版数据契约，尚未实现。

## Decision

### Common rules

- 所有 ID 均使用规范化字段计算的稳定 SHA-256，不使用随机 ID 表达内容身份。
- 时间使用带时区的 ISO 8601 UTC 字符串。
- 金额使用十进制字符串，不使用 binary float。
- 枚举值使用本文给出的英文小写值；未知状态显式表示，不能用空字符串代替。
- Immutable snapshot 和验证结果只追加，不原地覆盖。
- `official_domain` 规范化为小写 IDNA hostname，移除端口和末尾点。`final_url` hostname 只有在等于该域名，或以 `.` 加该域名为边界后缀时，才满足 official authority；字符串包含或无边界后缀不算匹配。

### `SourceDocument`

表示一次可重放的来源 snapshot，而不是搜索结果。

| Field | Type | Required | Contract |
|---|---|---:|---|
| `source_document_id` | string | yes | raw payload SHA-256 |
| `requested_url` | string | yes | fetch 输入 URL |
| `final_url` | string | yes | redirect 后 URL |
| `canonical_url` | string/null | no | 页面声明的 canonical URL |
| `official_domain` | string | yes | 用户输入并规范化的官方域名 |
| `authority` | `official` | yes | CS-001 只允许 `official` |
| `retrieved_at` | datetime | yes | snapshot 抓取时间 |
| `http_status` | integer/null | no | HTTP 状态；网络失败时为空 |
| `media_type` | string/null | no | 响应 MIME |
| `locale` | string | yes | 请求的 BCP 47 locale 或 `und` |
| `fetch_status` | enum | yes | `success|failed|blocked|unsupported` |
| `raw_artifact_path` | string/null | no | 内容寻址 raw 文件相对路径 |
| `raw_sha256` | string/null | no | 成功抓取时等于 document ID |
| `normalized_text_path` | string/null | no | 规范化文本相对路径 |
| `normalized_text_sha256` | string/null | no | 规范化文本 SHA-256 |
| `parser_version` | string/null | no | 规范化器版本 |
| `failure_code` | string/null | no | 失败时稳定错误码 |

`success` snapshot 必须同时具备 raw 与 normalized artifact/hash。URL 或 metadata 相同但 raw hash 不同的页面是不同 `SourceDocument`。

### `Evidence`

表示 candidate claim 对 snapshot 中一个精确文本区间的引用。

| Field | Type | Required | Contract |
|---|---|---:|---|
| `evidence_id` | string | yes | source ID、span、quote hash 的稳定 SHA-256 |
| `source_document_id` | string | yes | 必须指向已保存 snapshot |
| `exact_quote` | string | yes | 非空原样引用 |
| `span_start` | integer | yes | normalized text 的零基字符起点，inclusive |
| `span_end` | integer | yes | normalized text 的零基字符终点，exclusive |
| `quote_sha256` | string | yes | `exact_quote` 的 SHA-256 |
| `locator` | string/null | no | 标题、DOM 路径或可读 section 提示；不替代 span |
| `extraction_method` | string | yes | extractor 名称和版本 |

必须满足：

```text
normalized_text[span_start:span_end] == exact_quote
sha256(exact_quote) == quote_sha256
```

### `PricingClaim`

表示尚未通过验证的原子定价事实。

| Field | Type | Required | Contract |
|---|---|---:|---|
| `claim_id` | string | yes | 规范化事实字段与 evidence ID 的稳定 SHA-256 |
| `competitor` | string | yes | 用户提供的产品/竞品名称 |
| `plan_name` | string | yes | 页面显示的套餐名称 |
| `price_kind` | enum | yes | `free|fixed|contact_sales` |
| `amount` | decimal string/null | conditional | `fixed` 时必需；其他类型必须为空 |
| `currency` | ISO 4217/null | conditional | 固定货币价格时必需；页面未给币种则不得猜测 |
| `billing_period` | enum | yes | `month|year|one_time|usage|unknown` |
| `billing_qualifier` | string/null | no | 如 `billed_annually`、`effective_monthly` |
| `display_price` | string | yes | 页面中的价格展示文本 |
| `evidence_id` | string | yes | 必须绑定一个 Evidence |

一条 claim 只表达一个套餐的一个价格事实。套餐权益、额度、税费和促销不放入 `PricingClaim`。

年付折算月价必须使用 `billing_period=month` 和 `billing_qualifier=billed_annually`，并保留支持该限定的 quote；不得输出为无条件普通月付价。

### `VerifiedClaim`

表示由 `VerifierPort` 验证通过的 candidate claim。

| Field | Type | Required | Contract |
|---|---|---:|---|
| `verified_claim_id` | string | yes | claim ID、snapshot hash、verifier version 的稳定 SHA-256 |
| `claim` | `PricingClaim` | yes | 原 candidate claim，不由 verifier 扩写事实 |
| `verification_status` | `verified` | yes | 只有完全通过才可构造此类型 |
| `verification_checks` | list | yes | 每项包含 check 名称、pass 状态和诊断码 |
| `verified_at` | datetime | yes | 验证时间 |
| `verifier_version` | string | yes | 确定性 verifier 版本 |

验证失败不会产生带其他 status 的 `VerifiedClaim`。失败记录进入 `Issue`，status 为 `rejected` 或 `needs_review`。

### `PricingEvidenceResult`

机器可评测的顶层 JSON 产物：

| Field | Type | Contract |
|---|---|---|
| `schema_version` | string | 首版为 `pricing-evidence.v1` |
| `run_manifest` | object | 输入、组件版本、时间和稳定配置，不含密钥 |
| `source_documents` | list[`SourceDocument`] | 本次读取或写入的 snapshots |
| `candidate_claims` | list[`PricingClaim`] | extractor 原始结构化输出 |
| `evidence` | list[`Evidence`] | 所有 candidate evidence |
| `verified_claims` | list[`VerifiedClaim`] | 唯一可作为事实消费的集合 |
| `issues` | list[`Issue`] | discovery/fetch/extract/verify/write 诊断 |

CLI 的事实摘要只能遍历 `verified_claims`。`candidate_claims` 和 issues 可显示为诊断，但不得混写为已确认事实。

### `RunManifest`

`run_manifest` 至少包含：`run_id`、规范化 application input、`started_at`、`completed_at`、runtime/extractor/parser/verifier/result-writer 版本，以及影响结果的非密钥配置。密钥、authorization header 和完整环境变量不得进入 manifest。

用于 replay determinism 比较时，canonical semantic JSON 排除 `run_id`、`started_at`、`completed_at`、`retrieved_at` 和 `verified_at`，其余字段必须参与比较。

### `Issue`

| Field | Type | Required | Contract |
|---|---|---:|---|
| `issue_id` | string | yes | stage、code、关联对象 ID 和稳定 detail 的 SHA-256 |
| `stage` | enum | yes | `input|discovery|fetch|store|normalize|extract|verify|write` |
| `status` | enum | yes | `rejected|needs_review|failed|unsupported` |
| `code` | string | yes | 稳定机器可读错误码 |
| `message` | string | yes | 不含密钥的可读说明 |
| `source_document_id` | string/null | no | 与来源有关时填写 |
| `claim_id` | string/null | no | 与 candidate claim 有关时填写 |

`Issue` 是诊断对象，不是事实，也不能被 result writer 转换为 `VerifiedClaim`。

## Planned

CS-001 实现上述最小契约。通用 Claim、多个 Evidence 支持一个 claim、来源时效关系和综合 Report schema 留给后续 ADR，不在首版中预设。
