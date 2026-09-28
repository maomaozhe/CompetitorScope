# CompetitorScope

[English](README.en.md)

> 当前开发主线：`repo_research_poc`。原 V1 竞品分析系统已封存，保留代码与历史文档供查阅，不再作为新功能的开发入口。

CompetitorScope 正转向可追溯的源码研究：用户提出项目实现问题，系统在固定版本的仓库快照中检索代码，回答问题并核验引用。最终目标还包括按项目名定位并获取仓库、追踪跨文件实现链路，以及比较多个仓库的实现；这些目标尚未全部实现。

## 当前可运行能力

`repo_research_poc/` 提供独立的本机 Web 页面和 CLI。当前输入必须包含**本地仓库快照目录、40 位 Commit SHA 和问题**；系统不会自动发现或拉取仓库，也不会证明快照内容确属所填 Commit。Agent 只读过滤后的临时源码副本，默认工具为 `ls`、`glob`、`grep`、`read_file`，不开放宿主 Shell，也不执行被研究仓库代码。结果包含回答、经逐字校验的代码引用、未解决问题和运行记录。

### 启动本机页面

在 PowerShell 中：

```powershell
cd repo_research_poc
uv sync --locked
$env:ANTHROPIC_API_KEY = '<your key>'
uv run --locked python -m repo_research_poc.web --model 'ark-code-latest' --base-url 'https://ark.cn-beijing.volces.com/api/coding'
```

然后访问 `http://127.0.0.1:8765/`。也可使用其他兼容的模型服务；不要把密钥提交到仓库。详细运行、CLI、测试和限制见 [POC 使用说明](repo_research_poc/README.md)。

## 产品方向与开发入口

- [产品需求](doc/PRD.md)：当前主线、分阶段交付与验收口径。
- [源码研究产品规格](docs/v2/REPOSITORY_RESEARCH.md)：仓库定位、固定版本、链路追踪、跨仓比较和 RAG 待定决策。
- [POC 使用说明](repo_research_poc/README.md)：实际可运行能力、测试命令和已知限制。
- [开发指引](AGENTS.md)：代码区域与验证方式。

后续功能集中在 `repo_research_poc/` 演进。是否引入 RAG 由固定评测决定，目前不预设向量数据库。

## 历史版本

旧版 LangGraph/FastAPI/Next.js 竞品分析代码仍在 `src/`、`web/` 等目录，供历史回看；旧的运行说明、待办与 V2 官方定价方案见[封存索引](docs/v1/ARCHIVE.md)。这些资料描述的是当时的实现或方案，不代表当前路线。封存不表示已删除代码，也不承诺旧版环境在未来持续维护。
