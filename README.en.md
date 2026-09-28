# CompetitorScope

[中文](README.md)

> Active development: `repo_research_poc`. The original V1 competitive-analysis application is archived. Its code and historical documents remain available for reference, but new features are developed in the repository-research POC.

CompetitorScope is moving toward evidence-backed source-code research. Users ask implementation questions; the system inspects a fixed repository snapshot and returns an answer with verified code citations. Locating and fetching repositories, tracing implementation paths, and comparing multiple repositories are product goals that are not yet fully implemented.

## Available today

`repo_research_poc/` provides a local web page and CLI. It currently requires a **local repository snapshot directory, a 40-character commit SHA, and a question**. It does not discover or fetch repositories, or prove that the snapshot matches the supplied commit. The agent reads a filtered temporary copy through `ls`, `glob`, `grep`, and `read_file`. It has no host shell and does not execute the studied repository. Results include an answer, verified citations, open questions, and a run record.

### Start the local page

In PowerShell:

```powershell
cd repo_research_poc
uv sync --locked
$env:ANTHROPIC_API_KEY = '<your key>'
uv run --locked python -m repo_research_poc.web --model 'ark-code-latest' --base-url 'https://ark.cn-beijing.volces.com/api/coding'
```

Open `http://127.0.0.1:8765/`. Other compatible model services can be used. Keep credentials out of the repository. See the [POC guide](repo_research_poc/README.md) for CLI usage, tests, and limits.

## Direction and documentation

- [Product requirements](doc/PRD.md) define the active roadmap and acceptance criteria.
- [Repository research specification](docs/v2/REPOSITORY_RESEARCH.md) covers repository acquisition, implementation tracing, cross-repository comparison, and the open RAG decision.
- [POC guide](repo_research_poc/README.md) describes the running implementation.
- [Development guide](AGENTS.md) identifies code areas and checks.

Future features are developed in `repo_research_poc/`. A fixed evaluation set will inform whether retrieval augmentation is needed; a vector database is not assumed.

## Archived work

The former LangGraph/FastAPI/Next.js application remains under `src/`, `web/`, and related directories for historical reference. Its old run guide, backlog, and the earlier V2 pricing proposal are linked from the [archive index](docs/v1/ARCHIVE.md). Archival does not delete code or imply ongoing maintenance of the old environment.
