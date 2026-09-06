# CompetitorScope V2 Architecture

## Current

V1 通过 FastAPI、进程内运行态和 LangGraph 组织 Planner、Collector、Analyst、Comparator、Writer。V1 是现有可运行 Baseline，保持原入口、state、nodes、domain model 和前端行为不变。

V2 当前尚未实现。本文件定义计划中的依赖边界，不声明 runtime、存储或 context 集成已经存在。

## Decision

V2 采用与 V1 并行的独立 pipeline。迁移采用 Strangler 模式，不在 V1 LangGraph 内部替换节点。

```text
V1 API -> LegacyAnalysisRunner -> Existing LangGraph

V2 CLI -> OfficialPricingUseCase
          |-- RuntimePort
          |-- DiscoveryToolPort
          |-- SourceFetcherPort
          |-- SourceRepositoryPort
          |-- ContextProviderPort
          |-- ClaimExtractorPort
          |-- VerifierPort
          `-- ResultWriterPort
```

### Dependency direction

```text
CLI / adapters -> application use case -> domain
       |                  |
       `------ ports <----'
```

- Domain 不依赖 LangGraph、LangChain、具体 LLM SDK、搜索厂商、数据库、文件系统或 context 产品。
- Application 层只通过 ports 调用外部能力。
- Adapters 实现 ports，可以被替换而不改变 `SourceDocument`、`Evidence`、`PricingClaim`、`VerifiedClaim` 或 eval dataset。
- V1 类型不进入 V2 domain；如未来需要比较结果，应在边界处使用只读 Legacy Adapter 转换。

### Port responsibilities

| Port | 唯一职责 | 禁止职责 |
|---|---|---|
| `RuntimePort` | 调度 use case 步骤并传递结构化结果 | 定义领域事实或验证标准 |
| `DiscoveryToolPort` | 在已知官方域名内返回候选 URL | 将 snippet 升级为 Evidence |
| `SourceFetcherPort` | 获取 URL 响应并提供 raw payload/metadata | 生成 claim 或判定事实正确性 |
| `SourceRepositoryPort` | 内容寻址保存和读取 immutable snapshot | 改写已保存 snapshot |
| `ContextProviderPort` | 从已保存 snapshot 选择有界上下文 | 抓取 live web、修改来源或验证 claim |
| `ClaimExtractorPort` | 从上下文提出 candidate `PricingClaim` | 构造 `VerifiedClaim` 或写 durable verified state |
| `VerifierPort` | 确定性检查来源、quote/span 和价格字段 | 补写模型没有证据支持的字段 |
| `ResultWriterPort` | 持久化机器可评测 JSON 和打印摘要 | 接受未验证 claim 作为事实输出 |

Runtime、Tool、ContextProvider、Verifier 是相互独立的 ports；任何一个实现都不能被另一个具体实现的 SDK 类型污染。

### CS-001 reference flow

1. CLI 校验 competitor、official domain、locale、as-of 和可选 pricing URL。
2. 有显式 URL 时直接进入 fetch；否则 `DiscoveryToolPort` 仅在 official domain 内寻找候选定价页。
3. `SourceFetcherPort` 获取页面，`SourceRepositoryPort` 以 raw content hash 保存 snapshot，并保存规范化文本及元数据。
4. `ContextProviderPort` 从已保存的规范化文本选择上下文。
5. `ClaimExtractorPort` 产出 candidate `PricingClaim` 和 Evidence 候选。
6. `VerifierPort` 从 repository 重新读取 snapshot，验证 authority、hash、quote/span 和结构化价格字段。
7. 通过的声明成为 `VerifiedClaim`；失败项进入 `rejected` 或 `needs_review` issue。
8. `ResultWriterPort` 只用 `VerifiedClaim` 生成 JSON 事实列表和终端摘要。

### Default adapters for the first slice

- 本地顺序 runtime；
- official-domain-scoped discovery；
- HTTP source fetcher；
- 内容寻址文件 snapshot 加 repository metadata；
- 从 snapshot 读取文本的 bounded context provider；
- candidate claim extractor；
- 确定性 fail-closed verifier；
- JSON result writer 和只读 CLI 摘要。

具体 adapter 可以演进，但 ports 与 domain contract 是稳定边界。pi Runtime、OpenViking、MiniViking 或 MCP 如未来接入，只能位于 adapter 层；它们不是产品目标，也不是 CS-001 依赖。

## Failure policy

- Discovery 无结果：返回结构化 issue，不回退到非官方来源。
- Fetch、解析或 snapshot 保存失败：不进入 extraction。
- 非官方 redirect：snapshot 可记录诊断信息，但不能产生官方 `VerifiedClaim`。
- Quote/span、hash 或价格字段任一关键检查失败：fail closed。
- 部分 claim 失败：保留成功的 `VerifiedClaim`，失败项单独记录，不用 LLM 补齐。
- Result 写入失败：已保存 snapshot 不回滚或改写；运行返回失败状态，可安全重试 result 写入。

## Planned

CS-001 不新增 `/api/v2`，第一版入口固定为 application service 加薄 CLI。后续公共 API、替代 runtime 或 context provider 必须通过新的 adapter 任务接入，并复用相同 eval gate。

规范依据见 [ADR-0001](../adr/0001-evidence-first-pipeline.md)。
