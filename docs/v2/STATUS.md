# CompetitorScope V2 Status

## Current

更新时间：2026-09-06

| Area | Status | Notes |
|---|---|---|
| V1 LangGraph Baseline | Available | 当前仓库已有可运行 workflow、API、HITL、SSE 和报告链路 |
| V2 engineering contract | Available | 根目录 `AGENTS.md` 定义 evidence-first/eval-first 不变量 |
| V2 design documents | Available | 本目录记录已确认设计与当前实施状态 |
| ADR-0001 | Accepted | 采用独立 evidence-first pipeline，保留 V1 Baseline |
| CS-001 | Complete | 官方定价事实纵向切片及 fail-closed 证据链已实现 |
| V2 domain/application code | Available | 已实现 `SourceDocument`、`Evidence`、`PricingClaim`、`VerifiedClaim` 和 application use case |
| V2 eval dataset | Available | 已实现 4 组官方页面最小 snapshots、golden claims 和确定性 grader |
| V2 CLI | Available | `scripts/run_pricing_evidence.py` 支持显式 URL 和官方域名发现 |
| `/api/v2` | Not planned for CS-001 | 首版不承诺公共 HTTP API |
| pi Runtime integration | Not integrated | 不是产品目标或当前阻塞项 |
| OpenViking/MiniViking integration | Not integrated | 不是产品目标或当前阻塞项 |
| MCP integration | Not integrated | 不是产品目标或当前阻塞项 |

## Decisions

- V1 的 `src/graph/`、`src/api/v1/` 和 V1 domain model 保持独立、可运行。
- V2 从新的 namespace 开始，不原地修补 V1 evidence chain。
- Runtime、Tool、ContextProvider、Verifier 通过 ports 解耦。
- 第一纵向切片只处理官方定价事实。
- 显式 pricing URL 优先；没有 URL 时只在已知 official domain 内发现。
- Snapshot 使用内容寻址文件，metadata 通过 repository port 管理。
- 验证采用 fail-closed；未确定性验证的 candidate 不进入 `VerifiedClaim`。
- 第一版输出为持久化 JSON 加 CLI 摘要，不生成综合 Markdown 报告。

## CS-001 verification

- 完整 V1+V2 测试：26 passed；
- Ruff：全部新增范围及现有 `src`/`tests` 检查通过；
- 离线 eval：provenance、quote replay、precision、recall、semantic determinism 均为 100%；
- unsupported verified claims：0；
- GitHub Copilot 官方页 live smoke：成功保存 snapshot，并输出 5 条 verified pricing facts；
- V1 graph、V1 API、V1 domain 和前端未修改。

## Not implemented

- V1/V2 对照报告工具；
- 浏览器渲染、登录态或受阻页面抓取；
- 替代 runtime、context provider 或公共 API adapter；
- 通用报告和官方定价以外的事实类型。

## Next milestone

以 [CS-001](../tasks/CS-001-pricing-evidence-slice.md) 为稳定纵向切片，先审阅 live smoke 与 golden fixtures，再为下一事实类型单独建立任务和 eval dataset。公共 API、通用报告和 runtime/context adapter 不自动进入下一阶段。

架构依据见 [ADR-0001](../adr/0001-evidence-first-pipeline.md)。
