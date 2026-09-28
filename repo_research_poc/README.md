# repo_research_poc

这是独立的源码问答 POC。输入必须明确给出本地仓库快照目录、40 位 Commit SHA 和问题；不会发现或拉取仓库，也不修改 V1。Agent 只看到快照的临时副本，原始仓库不被写入或执行。

## 依赖与实际 SDK 接口

已在隔离环境中安装、调用并检查接口，随后生成本目录的 `uv.lock`。直接依赖固定为：

| 包 | 固定版本 | 用途 |
|---|---:|---|
| `deepagents` | 0.7.19 | Agent、文件工具及后端路由 |
| `langchain-anthropic` | 1.7.4 | Anthropic 兼容模型 |
| `langsmith` | 0.14.1 | 可选追踪与实验 |
| `pydantic` | 2.13.5 | 结果契约 |
| `httpx[socks]` | 0.28.1 | 支持当前环境的 SOCKS 代理 |
| `pytest` | 9.0.3 | 开发测试 |

锁文件还固定了传递依赖；本次安装中的 `langchain` 为 1.4.2，`langchain-core` 为 1.6.5。实测的相关签名和行为：

- `create_deep_agent(model, tools=None, *, system_prompt=None, middleware=(), subagents=None, backend=None, ...)` 返回可 `invoke` 的编译图。
- `FilesystemMiddleware(*, backend=None, tools=None, ...)` 的 `tools` 可限定为 `ls`、`read_file`、`glob`、`grep`。
- `FilesystemBackend(root_dir=None, virtual_mode=True, max_file_size_mb=10)` 会把虚拟路径限制在根目录，且不提供 Shell `execute`。
- `CompositeBackend(default, routes, *, artifacts_root="/")` 将 `/repo/` 路由到只读快照后端，其他路径使用临时 `StateBackend`。
- `register_harness_profile("anthropic", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))` 关闭默认 `task` 子 Agent。
- `langsmith.evaluate(target, data=..., evaluators=..., experiment_prefix=..., upload_results=True)` 仅由显式实验命令调用。

SDK 接口来源：[Deep Agents 文档](https://docs.langchain.com/oss/deepagents/overview)、[Profile 文档](https://docs.langchain.com/oss/python/deepagents/profiles)、[PyPI 0.7.19](https://pypi.org/project/deepagents/0.7.19/)。本目录测试还直接检查编译图实际暴露的工具名。

## 运行

### 本地 Web 页面

在 PowerShell 中启动服务，再打开 `http://127.0.0.1:8765/`：

```powershell
cd E:\GitHub\CompetitorScope\repo_research_poc
uv sync --locked
$env:ANTHROPIC_API_KEY = '<your key>'
uv run --locked python -m repo_research_poc.web `
  --model 'ark-code-latest' `
  --base-url 'https://ark.cn-beijing.volces.com/api/coding'
```

也可使用 `ANTHROPIC_AUTH_TOKEN`，服务会在本进程内将其传给模型 SDK。已有根目录 `.env` 时，可用 `uv run --locked --env-file ..\.env python -m repo_research_poc.web ...`，无需在网页中填写密钥。Web 服务仅绑定 `127.0.0.1`；页面必填快照目录、40 位 SHA 和问题。任务在后台运行，页面会轮询状态；同一时间只接收一个任务。默认结果目录为用户主目录下的 `.competitorscope/repo-research-runs`，使用 `--output-dir` 可查看另一个目录中的既有 JSON 记录。前端静态资源不依赖外部 CDN。

页面只把 `status=ok` 的回答和引用作为正式结果展示；失败记录仍可查看诊断、解析尝试和工具调用。Web 不提供 LangSmith 上传开关，默认不上传追踪。桌面与窄屏验收截图在 `../docs/review/repo-research-web/`。

### 命令行

在 PowerShell 中，从本目录运行：

```powershell
cd E:\GitHub\CompetitorScope\repo_research_poc
uv sync --locked
$env:ANTHROPIC_API_KEY = '<your key>'
# 使用 Anthropic 兼容网关时再设置：
# $env:ANTHROPIC_BASE_URL = 'https://your-endpoint'
uv run --locked python -m repo_research_poc `
  --snapshot 'E:\snapshots\project-at-commit' `
  --commit '0123456789abcdef0123456789abcdef01234567' `
  --question '这个函数如何处理错误？' `
  --model 'claude-sonnet-4-6'
```

也可用 `--base-url`、`--output-dir`、`--temperature`、`--max-tokens` 覆盖配置。`--recursion-limit`（默认 100）是 LangGraph 的步数预算；大快照上的宽泛问题可能探索过深而触发上限，可显式调大或收窄问题。默认运行记录写入用户主目录下的 `.competitorscope/repo-research-runs`，必须位于源码快照之外。CLI 输出回答、已验证代码引用、未解决问题及记录路径；无效引用会使运行状态为 `invalid_citations`，不展示未经验证的回答。

单次运行默认关闭 LangSmith 上传。要上传包含问题、工具调用和源码片段的追踪，显式加 `--langsmith-project NAME --allow-source-upload` 并配置 `LANGSMITH_API_KEY`。模型服务仍会收到 Agent 所选的源码片段，这是远程模型问答的必要数据流。

## 测试和实验

```powershell
uv run --locked pytest -q
uv run --locked python -m repo_research_poc.experiment `
  --snapshot 'E:\snapshots\project-at-commit' `
  --commit '0123456789abcdef0123456789abcdef01234567' `
  --cases evals/cases.json
```

`evals/cases.json` 只有三个问题结构；`reference_answer` 暂为空，`review_status` 为 `pending`。本地评测只报告运行状态与引用完整性，不打业务正确性分。标准答案须人工核实后加入评测文件。Agent 的工具后端只挂载过滤后的 `/repo`，`evals`、整个 `repo_research_poc`、`.git`、`.env`、虚拟环境和生成目录不会复制到该视图；评测元数据不进入 Agent 提示或工具返回。

可选的真正 LangSmith 数据集实验会上传案例、追踪和结果，必须显式执行：

```powershell
uv run --locked python -m repo_research_poc.experiment `
  --snapshot 'E:\snapshots\project-at-commit' `
  --commit '0123456789abcdef0123456789abcdef01234567' `
  --cases evals/cases.json `
  --langsmith-dataset 'repo-research-poc-my-unique-dataset' `
  --experiment-prefix 'repo-research-poc' `
  --allow-source-upload
```

LangSmith 实验目前只自动评分 `citation_integrity`；业务答案仍待人工审定。建议每次使用新的数据集名称。

## 实测状态（2026-09-28）

- 已执行：POC 的单元及 HTTP 测试（含故意击穿引用校验器的路径穿越、错行引用、文件篡改、symlink、二进制用例，以及截断 JSON 的成功重试和二次失败留痕）；经 Anthropic 兼容网关（`ark-code-latest`）对临时 3 文件快照完成端到端冒烟，状态 `ok`，引用通过确定性校验，运行记录完整落盘。Web 页面已在桌面与窄屏浏览器检查历史结果和失败诊断。
- 真实仓库冒烟：deepagents 0.7.19 源码（55 文件）窄问题 `ok`，引用逐字校验通过；2026-09-28 同一宽问题先在 40 步内失败（49 次工具调用/360 秒），增加收敛提示后在 40 步内返回 `ok`（27 次调用/305 秒），第一次引用不匹配由已有重试纠正。提示中的 12 次调用预算没有被严格遵守。earendil-works/pi monorepo（1941 文件）上，宽泛问题曾触发步数上限或长 JSON 截断，收窄问题后 12 条引用 11 条通过、1 条 quote 漂移被正确判为 `invalid_citations`（fail-closed）。
- 截断 JSON 的真实模型重试也已观察：3 文件样本使用极低的 `--max-tokens 128` 时，两次输出均截断，运行记录保留两次 `parse_attempts` 并以 `error` 结束。重试机制生效，但远端模型不保证恢复。
- 未执行：私有仓库端到端验收、LangSmith 在线数据集实验、业务标准答案评分（`reference_answer` 待人工核实）。

实测暴露的问题、证据和处置状态见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)。

## 边界和限制

- Commit SHA 是调用者提供的标识；POC 不通过 Git 证明快照字节属于该提交。运行时会哈希源文件，并在引用校验时发现文件变化。
- 引用校验能证明引用路径、行号和原文在该快照中有效，不能证明回答对代码含义的解释正确。
- 临时视图最多 20,000 个文件、512 MiB；符号链接、评测目录、密钥文件和生成目录不进入视图。大仓库需先裁剪快照。
- 默认工具只有 `ls`、`glob`、`grep`、`read_file`。没有 Shell `execute`、源码执行、网络搜索、写入工具或子 Agent；长期 Memory、向量检索和自动摘要均未接入。
- 只接入 Anthropic 及其兼容网关。私有仓库、远程 LangSmith 实验和业务正确性门槛尚未端到端验收。
