# CompetitorScope

[中文](README.md)

CompetitorScope is a multi-agent competitive analysis system. It starts from a market or product query, plans competitor candidates, collects public sources, extracts evidence, compares competitors, and produces a Markdown report with traceable references.

## Overview

The system uses a LangGraph workflow with specialized agents: Planner for competitor and report planning, Collector for search and collection, Analyst for competitor profiles, Comparator for cross-competitor comparison, and Writer for the final report. The web UI shows live progress, agent output streams, human-in-the-loop checkpoints, evidence, and reports.

Current capabilities:

- FastAPI backend APIs with Server-Sent Events streaming.
- Next.js interactive frontend.
- Tavily search and web content scraping.
- Anthropic-compatible LLM API with per-agent model settings.
- Automatic or interactive HITL confirmation flow.
- Markdown report and evidence output.

## Architecture

The backend entry point is `src/main.py`. API routes live in `src/api/v1/`, and runtime state is managed by `src/api/v1/runtime.py`. The workflow is defined in `src/graph/workflow.py`, with agent nodes in `src/graph/nodes/`. LLM and search integrations are wrapped in `src/services/llm.py`, `src/tools/web_search.py`, and `src/tools/web_scraper.py`.

The frontend lives in `web/` and uses Next.js. `web/src/lib/api.ts` talks to the backend, `web/src/hooks/useSSE.ts` subscribes to live events, and `web/src/components/` contains the input form, agent flow, HITL dialog, evidence panel, and report view.

## Repository Layout

```text
.
├── src/                 # FastAPI backend, LangGraph workflow, agents, services, tools
├── web/                 # Next.js frontend
├── scripts/             # Local CLI and end-to-end helper scripts
├── tests/               # Backend pytest tests
├── doc/                 # Project notes and memory-bank documents
├── data/                # Local data directory used by the app
├── Makefile             # Common backend commands
├── pyproject.toml       # Python dependencies and tooling
└── .env.example         # Environment variable template
```

## Requirements

- Python 3.11+
- `uv`
- Node.js
- `npm` or `pnpm`
- Anthropic-compatible LLM API key
- Tavily API key

Python dependencies are managed with `uv`; frontend dependencies are managed under `web/` with the Node package manager you choose.

## Configuration

Copy the environment template and fill in credentials:

```bash
cp .env.example .env
```

Key settings:

- `ANTHROPIC_API_KEY`: LLM API key.
- `ANTHROPIC_BASE_URL`: Anthropic-compatible API base URL.
- `TAVILY_API_KEY`: Tavily search API key.
- `PLANNER_MODEL`, `COLLECTOR_MODEL`, `ANALYST_MODEL`, `COMPARATOR_MODEL`, `WRITER_MODEL`: per-agent model names.
- `LOG_LEVEL`: backend log level.
- `MAX_SEARCH_ROUNDS`: maximum search rounds.
- `DATA_DIR`: local data directory.

The code also supports optional `DATABASE_URL`. If it is not set, the backend uses local SQLite file `competitorscope.db`.

## Quick Start

Install backend dependencies:

```bash
uv sync
```

Start the backend:

```bash
make dev
```

If `uvicorn` is not on your shell path, use:

```bash
uv run uvicorn src.main:app --reload --port 8000
```

Start the frontend:

```bash
cd web
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The backend defaults to `http://localhost:8000`, and the frontend dev server runs at `http://localhost:3000`.

## Local CLI

You can run the end-to-end pipeline without the frontend:

```bash
make run
```

Or pass a query and HITL mode explicitly:

```bash
uv run python scripts/run_local.py "AI Coding IDE 赛道的主要竞品" --hitl interactive
```

The CLI writes results to `output/run-<id>/`, including `report.md`, `data.json`, and `log.txt`.

## Testing

Backend tests:

```bash
uv run pytest tests/ -v
```

Backend lint:

```bash
uv run ruff check src tests
```

Note: `make lint` currently checks `src/` only.

Frontend lint:

```bash
cd web
npm run lint
```

Key browser guard scripts:

- `web/test_hitl_done_guard.mjs`: checks HITL completion behavior.
- `web/test_hitl_countdown_guard.mjs`: checks HITL countdown behavior.
- `web/test_agent_output_hitl_guard.mjs`: checks agent output around HITL states.
- `web/test_report_rendering_guard.mjs`: checks report rendering.
- `web/test_transition_hitl_evidence.mjs`: checks transitions between HITL and evidence display.

These scripts depend on local backend and frontend services. Start both servers before running them.

## Current Status and Limits

Runtime state mainly lives in the in-memory `RUN_STORE`. Database tables are created on backend startup, but full persistence and recovery are still being improved. After a server restart, running or recently completed analysis state may not be fully recoverable.

This repository does not currently include a ready-to-use Docker or Alembic migration flow. Treat Docker, migrations, and production deployment as future work rather than completed features.

## Development Notes

- Do not commit `.env`, local database files, build caches, test screenshots, or local output directories.
- The root README is the project entry point; `web/README.md` remains the frontend subproject README.
- When adding capabilities, keep `.env.example`, test instructions, and related commands in sync.

## Roadmap

- Improve database persistence and recovery.
- Add a formal migration flow.
- Add deployment and containerization documentation.
- Expand automated end-to-end coverage.
