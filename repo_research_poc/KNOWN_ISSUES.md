# repo_research_poc 实现与实测问题记录

> 记录 POC 在真实仓库冒烟中暴露的问题。每条含现象、证据（运行记录 ID）、根因分析、处置状态。
> 最近更新：2026-09-28

## 测试环境

- 模型：`ark-code-latest`，经 Anthropic 兼容网关 `https://ark.cn-beijing.volces.com/api/coding`
- 快照 A：deepagents 0.7.19 源码（55 个 .py 文件，自 site-packages 复制）
- 快照 B：earendil-works/pi monorepo @ `2b0a123de98318c2ff8069661721ce0c3794c34e`（1941 文件，TypeScript）

---

## I-1 宽泛问题上 Agent 探索不止，撞 recursion_limit

- **现象**：双部分/流程类问题（"backend 参数怎么被使用 + FilesystemMiddleware 如何决定工具"、"tool calling 完整流程"）下，Agent 持续读文件不给最终答案，直到 `GraphRecursionError`。
- **证据**：
  - deepagents 宽问题：limit=50 失败（59 次工具调用/173s）；limit=100 仍失败（80 次调用/540s）— `07755cdd…`、`b814378e…`
  - pi 宽问题：limit=100 失败（64 次调用/298s）— `5ff3ba07…`
  - 2026-09-28 再现：deepagents 双部分问题，limit=40、max_tokens=256，49 次工具调用/360s 后仍为 `GraphRecursionError`，未进入 JSON 解析阶段 — `888046f7…`。
  - 工具调用序列无重复循环，是"合法但收敛不了"的探索。
- **根因**：模型（ark-code-latest）缺少"够了就答"的收敛压力；系统提示只约束输出格式，没有探索预算意识。每个工具调用消耗多个图步，100 步≈60~80 次调用。
- **处置**：部分缓解——`--recursion-limit` 已参数化（默认 100，2026-09-27）。2026-09-28 给 Agent 明确的探索预算、证据足够即作答及不足处列为未解决问题的指令；同一 deepagents 问题在 limit=40、max_tokens=1024 下返回 `ok`，27 次工具调用/305s，首轮引用漂移后自动纠正 — `3dd2a7cf…`。指令中的 12 次调用并非硬限制，实测超过；单次成功不能证明宽问题稳定收敛。
- **未做**（超出 POC 边界）：程序化工具调用预算、子 Agent 分担检索、自动摘要。

## I-2 长回答 JSON 被 max_tokens 截断

- **现象**：宽问题探索完成后，最终 `ResearchAnswer` JSON 输出到一半被截断（回答长 + 引用要求逐字 quote，体积大），报 `ValidationError: Invalid JSON: EOF while parsing a string`，运行状态 `error`。
- **证据**：pi 宽问题 @limit=300：max_tokens=4096 在第 50 行截断（`99c63937…`）；8192 在第 122 行截断（`61964eb6…`）。
- **2026-09-28 复现**：新增 `test_truncated_json_gets_one_short_response_retry` 与 `test_repeated_truncated_json_stops_after_second_attempt`；修复前两项均失败，Agent 各只调用一次，确认解析错误没有进入重试回路。原有 22 项测试通过。
- **根因**：runner 的重试回路只覆盖**引用校验失败**（quote_mismatch 等），不覆盖 **JSON 解析失败**。截断属于可恢复错误却被直接归入 `errors`。
- **处置**：2026-09-28 已修复：解析失败时记录 `parse_attempts`，反馈模型使用已查证的证据生成更短的合法 JSON，最多重试一次；再次失败仍保存错误运行记录。两项先失败后通过的回归测试分别覆盖恢复和二次失败。重试不能保证远端模型一定恢复；仍可调大 `--max-tokens` 或收窄问题。
- **实测边界**：3 文件样本、`max_tokens=128` 的故意压测中，首次 JSON 在 404 字符截断，重试仍在 439 字符截断；`parse_attempts` 为 2，状态 `error`，4 次工具调用/262s — `dd79ea28…`。确认真实模型会进入重试分支，但极低上限无法容纳有效回答与引用。

## I-3 个别引用 quote 漂移，重试一次后仍 quote_mismatch

- **现象**：pi 收窄问题（@limit=300, max_tokens=16384）回答完整，12 条引用中 11 条通过，`packages/agent/src/harness/runtime/drive/response.ts:292-307` 的 quote 与快照原文不一致；runner 给了一次纠正机会，第二次仍不符 → `invalid_citations`。
- **证据**：`18fcbf3e…`（23 次工具调用/308s，2 次尝试）。
- **根因**：模型凭"印象"重组了代码片段（tab/换行/片段拼接），没有严格逐字复制。多跳文件多时单点漂移概率上升。
- **处置**：**不修为缺陷**——这正是 fail-closed 设计要的：宁可不展示，也不展示未验证引用。缓解方向：反馈中附上该行真实原文片段（目前是提示模型自己重读）。
- **附注**：回答正文质量实际良好（正确列出 pi 的两套 runtime 链路），失败仅在这一条引用上。

## I-4 控制台中文乱码（非缺陷）

- **现象**：Windows Git Bash 直接运行时 CLI 输出的中文显示为 `���`。
- **根因**：Windows 控制台默认代码页非 UTF-8，落盘 JSON 完好（已用 unicode_escape 验证无 `U+FFFD`）。
- **处置**：运行时加 `PYTHONIOENCODING=utf-8 python -X utf8` 即可。不改动代码。

## I-5 输入校验对非 40 位 SHA fail-fast（设计确认）

- **现象**：首次跑 deepagents 时手造 SHA 长度非法，直接 `Input error: commit SHA must be 40 hexadecimal characters`。
- **处置**：符合"输入必须显式"的需求，非问题。提醒：对 pip 包快照没有真实 git SHA，本 POC 把 SHA 当调用方标识，不做 git 证明（README 限制一节已声明）。

---

## 状态汇总

| ID | 问题 | 状态 |
|---|---|---|
| I-1 | 宽问题探索不止 | 部分缓解（步数上限、收敛提示）；27 次调用仍超提示预算 |
| I-2 | JSON 截断不重试 | 已修：一次短回答重试，二次失败留痕 |
| I-3 | 引用漂移 fail-closed | 设计行为，不修 |
| I-4 | 控制台乱码 | 非缺陷，已有运行方式 |
| I-5 | SHA 校验 fail-fast | 设计行为 |
