# V1 Observability and Evaluation Replay

> Archived V1 documentation. See the [archive index](ARCHIVE.md) and the [current repository-research specification](../v2/REPOSITORY_RESEARCH.md).

V1 uses a local, append-only trace ledger for runtime inspection and evaluation. The ledger is independent from LangGraph checkpoints: checkpoints resume workflow execution, while the ledger preserves audit, replay, and comparison data.

## Storage

- SQLite metadata defaults to `data/observability/observability.db` with WAL enabled.
- Redacted large payloads are stored by SHA-256 under `data/observability/artifacts/`.
- `trace_runs`, `trace_spans`, and `trace_events` form the execution timeline.
- `state_snapshots` stores compact state plus references to large artifacts.
- `eval_cases` pins a source run; `eval_executions` records candidate variants and metrics.

Ordinary runs are retained for 30 days. Runs pinned by an eval case are retained, and cleanup removes only unreferenced artifacts. On process startup, unfinished historical runs are marked `interrupted`; V1 does not automatically resume them.

## Event contract

Every event has a stable `run_id`, monotonically increasing `seq`, optional span relationship, type, timestamp, status, payload, artifact references, and schema version. Important event families are:

- `run.*`, `span.*`, and `agent.status_changed`
- `llm.*` and `tool.*`
- `hitl.*` and `decision.recorded`
- `state.snapshot_created`, `state.diff_recorded`, and `artifact.created`
- `report.chunk_appended` and `observability.degraded`

Decision records contain candidates, the selected value, a concise auditable reason, confidence when available, evidence references, and a strategy version. They do not contain private chain-of-thought.

## APIs and UI

The existing analysis SSE endpoint reads the persistent ledger and continues to support `Last-Event-ID`. Developer APIs are available below `/api/v1/observability` for runs, events, snapshots, artifacts, eval cases, candidate executions, and comparisons.

- `/observability` lists current and historical runs.
- `/observability/{runId}` shows metrics, timeline replay, decisions, snapshots, artifacts, and Baseline/Candidate evaluation.

## Evaluation replay

Creating an eval case freezes recorded search and scrape results as artifacts. Candidate execution uses those results without accessing the network unless `live_tools=true` is explicit. A variant can override models, model parameters, and the first system prompt per Agent role. Candidate runs create normal traces and report duration, tokens, errors, tool calls, and decision counts.

The Demo runner executes the current checkout only. Git commit and dirty state are recorded for diagnosis, but arbitrary historical checkout is intentionally out of scope.
