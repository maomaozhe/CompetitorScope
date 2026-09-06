"""Factories that assign stable IDs to V2 domain records."""

from __future__ import annotations

from src.v2.domain.identifiers import stable_id
from src.v2.domain.models import Issue, IssueStage, IssueStatus


def make_issue(
    *,
    stage: IssueStage,
    status: IssueStatus,
    code: str,
    message: str,
    source_document_id: str | None = None,
    claim_id: str | None = None,
) -> Issue:
    identity = {
        "stage": stage,
        "status": status,
        "code": code,
        "message": message,
        "source_document_id": source_document_id,
        "claim_id": claim_id,
    }
    return Issue(
        issue_id=stable_id("issue", identity),
        stage=stage,
        status=status,
        code=code,
        message=message,
        source_document_id=source_document_id,
        claim_id=claim_id,
    )
