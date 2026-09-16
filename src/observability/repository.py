"""SQLite event ledger and content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "trace.v1"
_SENSITIVE_PARTS = ("api_key", "apikey", "authorization", "cookie", "secret", "password")
_SENSITIVE_TOKEN_KEYS = {"token", "access_token", "refresh_token", "id_token", "auth_token"}


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, Path)):
        return str(value)
    return repr(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def redact(value: Any) -> Any:
    """Remove common credentials before content is hashed or persisted."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            lowered = str(key).lower()
            sensitive = any(part in lowered for part in _SENSITIVE_PARTS) or lowered in _SENSITIVE_TOKEN_KEYS
            cleaned[key] = "[REDACTED]" if sensitive else redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


class ObservabilityRepository:
    """Small synchronous repository optimized for a single-process demo."""

    def __init__(self, database_path: str | Path, artifact_root: str | Path):
        self.database_path = Path(database_path)
        self.artifact_root = Path(artifact_root)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trace_runs (
                    run_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    versions_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    next_seq INTEGER NOT NULL DEFAULT 0,
                    token_total INTEGER NOT NULL DEFAULT 0,
                    estimated_cost REAL,
                    replayable INTEGER NOT NULL DEFAULT 1,
                    degraded INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS trace_spans (
                    span_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES trace_runs(run_id) ON DELETE CASCADE,
                    parent_span_id TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    agent TEXT,
                    node TEXT,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    attributes_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS ix_trace_spans_run ON trace_spans(run_id, started_at);
                CREATE TABLE IF NOT EXISTS trace_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES trace_runs(run_id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    span_id TEXT,
                    parent_span_id TEXT,
                    event_type TEXT NOT NULL,
                    occurred_at REAL NOT NULL,
                    agent TEXT,
                    node TEXT,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
                    schema_version TEXT NOT NULL,
                    UNIQUE(run_id, seq)
                );
                CREATE INDEX IF NOT EXISTS ix_trace_events_run_seq ON trace_events(run_id, seq);
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL UNIQUE,
                    artifact_type TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    redaction_level TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES trace_runs(run_id) ON DELETE CASCADE,
                    boundary TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    changed_keys_json TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_snapshots_run ON state_snapshots(run_id, sequence);
                CREATE TABLE IF NOT EXISTS eval_cases (
                    case_id TEXT PRIMARY KEY,
                    source_run_id TEXT NOT NULL REFERENCES trace_runs(run_id),
                    label TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS eval_executions (
                    execution_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES eval_cases(case_id),
                    run_id TEXT,
                    variant_label TEXT NOT NULL,
                    variant_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    finished_at REAL
                );
                """
            )

    def create_run(self, run_id: str, request: dict[str, Any], versions: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        with self._connect() as connection:
            connection.execute("DELETE FROM trace_runs WHERE run_id = ?", (run_id,))
            connection.execute(
                "INSERT INTO trace_runs(run_id, request_json, versions_json, started_at) VALUES (?, ?, ?, ?)",
                (run_id, _canonical_json(redact(request)), _canonical_json(versions or {}), now),
            )
        return self.get_run(run_id) or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM trace_runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trace_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def _run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["versions"] = json.loads(result.pop("versions_json"))
        for key in ("replayable", "degraded", "pinned"):
            result[key] = bool(result[key])
        return result

    def update_run(self, run_id: str, **changes: Any) -> None:
        allowed = {
            "status", "finished_at", "token_total", "estimated_cost", "replayable",
            "degraded", "pinned", "error_message",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE trace_runs SET {assignments} WHERE run_id = ?",
                (*values.values(), run_id),
            )

    def increment_token_total(self, run_id: str, amount: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE trace_runs SET token_total = token_total + ? WHERE run_id = ?",
                (amount, run_id),
            )

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        agent: str | None = None,
        node: str | None = None,
        status: str | None = None,
        artifact_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        event_id = uuid.uuid4().hex
        occurred_at = time.time()
        clean_payload = redact(payload or {})
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_seq FROM trace_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown trace run: {run_id}")
            seq = int(row["next_seq"]) + 1
            connection.execute("UPDATE trace_runs SET next_seq = ? WHERE run_id = ?", (seq, run_id))
            connection.execute(
                """INSERT INTO trace_events(
                    event_id, run_id, seq, span_id, parent_span_id, event_type, occurred_at,
                    agent, node, status, payload_json, artifact_refs_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, run_id, seq, span_id, parent_span_id, event_type, occurred_at,
                    agent, node, status, _canonical_json(clean_payload),
                    _canonical_json(artifact_refs or []), SCHEMA_VERSION,
                ),
            )
        return {
            "event_id": event_id, "run_id": run_id, "seq": seq, "span_id": span_id,
            "parent_span_id": parent_span_id, "type": event_type, "event": event_type,
            "occurred_at": occurred_at, "agent": agent, "node": node, "status": status,
            "payload": clean_payload, "data": clean_payload, "artifact_refs": artifact_refs or [],
            "schema_version": SCHEMA_VERSION,
        }

    def list_events(self, run_id: str, after_seq: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trace_events WHERE run_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (run_id, after_seq, limit),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("payload_json"))
            refs = json.loads(item.pop("artifact_refs_json"))
            item["type"] = item.pop("event_type")
            item["event"] = item["type"]
            item["payload"] = payload
            item["data"] = payload
            item["artifact_refs"] = refs
            events.append(item)
        return events

    def create_span(
        self,
        run_id: str,
        name: str,
        kind: str,
        *,
        parent_span_id: str | None = None,
        agent: str | None = None,
        node: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        span_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO trace_spans(
                    span_id, run_id, parent_span_id, name, kind, agent, node, status,
                    started_at, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
                (
                    span_id, run_id, parent_span_id, name, kind, agent, node,
                    time.time(), _canonical_json(redact(attributes or {})),
                ),
            )
        return span_id

    def finish_span(self, span_id: str, status: str = "completed", attributes: dict[str, Any] | None = None) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attributes_json FROM trace_spans WHERE span_id = ?", (span_id,)
            ).fetchone()
            existing = json.loads(row["attributes_json"]) if row else {}
            existing.update(redact(attributes or {}))
            connection.execute(
                "UPDATE trace_spans SET status = ?, finished_at = ?, attributes_json = ? WHERE span_id = ?",
                (status, time.time(), _canonical_json(existing), span_id),
            )

    def list_spans(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trace_spans WHERE run_id = ? ORDER BY started_at", (run_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["attributes"] = json.loads(item.pop("attributes_json"))
            result.append(item)
        return result

    def save_artifact(self, artifact_type: str, content: Any, media_type: str | None = None) -> dict[str, Any]:
        cleaned = redact(content)
        is_text = isinstance(cleaned, str)
        serialized = cleaned if is_text else _canonical_json(cleaned)
        raw = serialized.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        artifact_id = digest
        suffix = ".txt" if is_text else ".json"
        destination = self.artifact_root / digest[:2] / f"{digest}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            file_descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
            try:
                with os.fdopen(file_descriptor, "wb") as handle:
                    handle.write(raw)
                os.replace(temporary_name, destination)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO artifacts(
                    artifact_id, sha256, artifact_type, media_type, size_bytes, path,
                    redaction_level, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'secrets', ?)""",
                (
                    artifact_id, digest, artifact_type,
                    media_type or ("text/plain" if is_text else "application/json"),
                    len(raw), str(destination), time.time(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return dict(row)

    def read_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        raw = Path(result["path"]).read_text(encoding="utf-8")
        result["content"] = json.loads(raw) if result["media_type"] == "application/json" else raw
        return result

    def create_snapshot(self, run_id: str, boundary: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT state_json, sequence FROM state_snapshots WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        prior_state = json.loads(previous["state_json"]) if previous else {}
        compact: dict[str, Any] = {}
        refs: list[str] = []
        for key, value in state.items():
            serialized = _canonical_json(redact(value))
            if len(serialized.encode("utf-8")) > 4096:
                artifact = self.save_artifact(f"state.{key}", value)
                compact[key] = {"artifact_id": artifact["artifact_id"], "size_bytes": artifact["size_bytes"]}
                refs.append(artifact["artifact_id"])
            else:
                compact[key] = redact(value)
        changed_keys = sorted(key for key in set(prior_state) | set(compact) if prior_state.get(key) != compact.get(key))
        sequence = int(previous["sequence"]) + 1 if previous else 1
        snapshot_id = uuid.uuid4().hex
        created_at = time.time()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO state_snapshots(
                    snapshot_id, run_id, boundary, sequence, state_json, changed_keys_json,
                    artifact_refs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id, run_id, boundary, sequence, _canonical_json(compact),
                    _canonical_json(changed_keys), _canonical_json(refs), created_at,
                ),
            )
        return {
            "snapshot_id": snapshot_id, "run_id": run_id, "boundary": boundary,
            "sequence": sequence, "state_json": _canonical_json(compact),
            "changed_keys": changed_keys, "artifact_refs": refs, "created_at": created_at,
        }

    def list_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM state_snapshots WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["state"] = json.loads(item.pop("state_json"))
            item["changed_keys"] = json.loads(item.pop("changed_keys_json"))
            item["artifact_refs"] = json.loads(item.pop("artifact_refs_json"))
            result.append(item)
        return result

    def create_eval_case(
        self, run_id: str, label: str, annotations: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] != "completed" or run["degraded"] or not run["replayable"]:
            raise ValueError("Eval cases require a completed, healthy, replayable run")
        events = self.list_events(run_id, limit=100_000)
        snapshots = self.list_snapshots(run_id)
        report_events = [event for event in events if event["type"] == "report.finalized"]
        manifest = {
            "schema_version": "eval-case.v1",
            "source_run_id": run_id,
            "request": run["request"],
            "versions": run["versions"],
            "hitl_responses": [
                event["payload"]
                for event in events
                if event["type"] in {"hitl.resolved", "hitl.timed_out"}
            ],
            "tool_results": [
                {"payload": event["payload"], "artifact_refs": event["artifact_refs"]}
                for event in events if event["type"] == "tool.completed"
            ],
            "node_inputs": [
                {
                    "snapshot_id": item["snapshot_id"],
                    "boundary": item["boundary"],
                    "artifact_refs": item["artifact_refs"],
                }
                for item in snapshots
            ],
            "baseline_output": {
                "artifact_refs": [
                    ref for event in report_events for ref in event["artifact_refs"]
                ],
                "report_event": report_events[-1]["payload"] if report_events else None,
            },
            "decisions": [
                event["payload"] for event in events if event["type"] == "decision.recorded"
            ],
            "annotations": annotations or {},
        }
        case_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO eval_cases(case_id, source_run_id, label, manifest_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (case_id, run_id, label, _canonical_json(manifest), time.time()),
            )
            connection.execute("UPDATE trace_runs SET pinned = 1 WHERE run_id = ?", (run_id,))
        return {"case_id": case_id, "source_run_id": run_id, "label": label, "manifest": manifest}

    def get_eval_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM eval_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["manifest"] = json.loads(result.pop("manifest_json"))
        return result

    def create_eval_execution(self, case_id: str, variant_label: str, variant: dict[str, Any]) -> dict[str, Any]:
        execution_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO eval_executions(
                    execution_id, case_id, variant_label, variant_json, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)""",
                (execution_id, case_id, variant_label, _canonical_json(variant), time.time()),
            )
        return self.get_eval_execution(execution_id) or {}

    def get_eval_execution(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM eval_executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["variant"] = json.loads(result.pop("variant_json"))
        result["metrics"] = json.loads(result.pop("metrics_json"))
        return result

    def list_eval_executions(self, case_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT execution_id FROM eval_executions WHERE case_id = ? ORDER BY created_at", (case_id,)
            ).fetchall()
        return [self.get_eval_execution(row["execution_id"]) for row in rows]

    def update_eval_execution(self, execution_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"run_id", "status", "metrics", "finished_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "metrics" in values:
            values["metrics_json"] = _canonical_json(values.pop("metrics"))
        if values:
            assignments = ", ".join(f"{key} = ?" for key in values)
            with self._connect() as connection:
                connection.execute(
                    f"UPDATE eval_executions SET {assignments} WHERE execution_id = ?",
                    (*values.values(), execution_id),
                )
        return self.get_eval_execution(execution_id) or {}

    def build_replay_catalog(self, case_id: str) -> dict[str, Any]:
        case = self.get_eval_case(case_id)
        if case is None:
            raise KeyError(case_id)
        catalog: dict[str, Any] = {}
        for item in case["manifest"].get("tool_results", []):
            payload = item.get("payload", {})
            refs = item.get("artifact_refs", [])
            if not payload.get("tool") or not payload.get("input_hash") or not refs:
                continue
            artifact = self.read_artifact(refs[0])
            if artifact is not None:
                catalog[f"{payload['tool']}:{payload['input_hash']}"] = artifact["content"]
        return catalog

    def run_metrics(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            return {}
        events = self.list_events(run_id, limit=100_000)
        finished_at = run.get("finished_at")
        duration_ms = None
        if finished_at is not None:
            duration_ms = round((finished_at - run["started_at"]) * 1000)
        return {
            "completed": run["status"] == "completed",
            "status": run["status"],
            "duration_ms": duration_ms,
            "token_total": run.get("token_total", 0),
            "estimated_cost": run.get("estimated_cost"),
            "error_count": sum(event["type"].endswith("failed") for event in events),
            "tool_calls": sum(event["type"] == "tool.completed" for event in events),
            "decision_count": sum(event["type"] == "decision.recorded" for event in events),
            "replayable": run["replayable"],
        }

    def cleanup(self, retention_days: int = 30) -> dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp()
        with self._connect() as connection:
            removable = connection.execute(
                "SELECT run_id FROM trace_runs WHERE pinned = 0 AND started_at < ?", (cutoff,)
            ).fetchall()
            for row in removable:
                connection.execute("DELETE FROM trace_runs WHERE run_id = ?", (row["run_id"],))
        referenced: set[str] = set()
        with self._connect() as connection:
            for row in connection.execute("SELECT artifact_refs_json FROM trace_events").fetchall():
                referenced.update(json.loads(row["artifact_refs_json"]))
            for row in connection.execute("SELECT artifact_refs_json FROM state_snapshots").fetchall():
                referenced.update(json.loads(row["artifact_refs_json"]))
            artifacts = connection.execute("SELECT artifact_id, path FROM artifacts").fetchall()
            unreferenced = [row for row in artifacts if row["artifact_id"] not in referenced]
            for row in unreferenced:
                connection.execute("DELETE FROM artifacts WHERE artifact_id = ?", (row["artifact_id"],))
        for row in unreferenced:
            try:
                Path(row["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        return {"runs_deleted": len(removable), "artifacts_deleted": len(unreferenced)}

    def mark_unfinished_runs_interrupted(self) -> int:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE trace_runs
                SET status = 'interrupted', finished_at = ?, replayable = 0,
                    error_message = COALESCE(error_message, 'Process stopped before run completion')
                WHERE status IN ('running', 'paused')""",
                (now,),
            )
        return cursor.rowcount
