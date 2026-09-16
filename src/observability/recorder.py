"""High-level trace recording API used by the graph runtime and services."""

from __future__ import annotations

from typing import Any

from src.observability.repository import ObservabilityRepository


class TraceRecorder:
    def __init__(self, repository: ObservabilityRepository):
        self.repository = repository

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        artifact_fields: dict[str, str] | None = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        event_payload = dict(payload or {})
        refs: list[str] = list(metadata.pop("artifact_refs", []) or [])
        for field, artifact_type in (artifact_fields or {}).items():
            if field not in event_payload:
                continue
            artifact = self.repository.save_artifact(artifact_type, event_payload.pop(field))
            refs.append(artifact["artifact_id"])
            self.repository.append_event(
                run_id,
                "artifact.created",
                {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_type": artifact["artifact_type"],
                    "media_type": artifact["media_type"],
                    "size_bytes": artifact["size_bytes"],
                },
                span_id=metadata.get("span_id"),
                agent=metadata.get("agent"),
                node=metadata.get("node"),
                status="completed",
                artifact_refs=[artifact["artifact_id"]],
            )
        return self.repository.append_event(
            run_id, event_type, event_payload, artifact_refs=refs, **metadata
        )

    def start_span(
        self,
        run_id: str,
        *,
        name: str,
        kind: str,
        parent_span_id: str | None = None,
        agent: str | None = None,
        node: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        span_id = self.repository.create_span(
            run_id,
            name,
            kind,
            parent_span_id=parent_span_id,
            agent=agent,
            node=node,
            attributes=attributes,
        )
        self.record_event(
            run_id,
            "span.started",
            {"name": name, "kind": kind, "attributes": attributes or {}},
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent=agent,
            node=node,
            status="running",
        )
        return span_id

    def finish_span(
        self,
        run_id: str,
        span_id: str,
        *,
        status: str = "completed",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        spans = {span["span_id"]: span for span in self.repository.list_spans(run_id)}
        span = spans.get(span_id, {})
        self.repository.finish_span(span_id, status=status, attributes=attributes)
        self.record_event(
            run_id,
            "span.finished" if status == "completed" else "span.failed",
            {"name": span.get("name"), "kind": span.get("kind"), "attributes": attributes or {}},
            span_id=span_id,
            parent_span_id=span.get("parent_span_id"),
            agent=span.get("agent"),
            node=span.get("node"),
            status=status,
        )

    def record_decision(
        self,
        run_id: str,
        *,
        span_id: str | None,
        decision_point: str,
        candidates: list[Any],
        selected: Any,
        reason: str,
        confidence: float | None,
        evidence_refs: list[str],
        strategy_version: str,
        agent: str | None = None,
        node: str | None = None,
    ) -> dict[str, Any]:
        return self.record_event(
            run_id,
            "decision.recorded",
            {
                "decision_point": decision_point,
                "candidates": candidates,
                "selected": selected,
                "reason": reason,
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "strategy_version": strategy_version,
            },
            span_id=span_id,
            agent=agent,
            node=node,
            status="completed",
        )

    def snapshot(self, run_id: str, boundary: str, state: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.repository.create_snapshot(run_id, boundary, state)
        self.record_event(
            run_id,
            "state.snapshot_created",
            {
                "snapshot_id": snapshot["snapshot_id"],
                "boundary": boundary,
                "changed_keys": snapshot["changed_keys"],
            },
            artifact_refs=snapshot["artifact_refs"],
        )
        if snapshot["changed_keys"]:
            self.record_event(
                run_id,
                "state.diff_recorded",
                {"snapshot_id": snapshot["snapshot_id"], "changed_keys": snapshot["changed_keys"]},
            )
        return snapshot
