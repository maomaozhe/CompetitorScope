"""Bounded context provider backed only by stored snapshots."""

from __future__ import annotations

from src.v2.domain.models import SourceDocument
from src.v2.ports import SourceRepositoryPort


class SnapshotContextProvider:
    version = "snapshot-context.v1"

    def __init__(self, repository: SourceRepositoryPort, *, max_chars: int = 100_000) -> None:
        self.repository = repository
        self.max_chars = max_chars

    def provide(self, document: SourceDocument) -> str:
        return self.repository.load_normalized(document)[: self.max_chars]
