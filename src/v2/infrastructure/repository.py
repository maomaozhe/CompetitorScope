"""Content-addressed filesystem repository for immutable source snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.v2.domain.identifiers import sha256_bytes, sha256_text
from src.v2.domain.models import FetchStatus, SourceDocument
from src.v2.ports import FetchedResource, NormalizedResource


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


class FilesystemSourceRepository:
    version = "filesystem-cas.v1"

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(
        self,
        resource: FetchedResource,
        normalized: NormalizedResource,
        *,
        official_domain: str,
        locale: str,
        retrieved_at: datetime,
    ) -> SourceDocument:
        raw_hash = sha256_bytes(resource.content)
        text_hash = sha256_text(normalized.text)
        raw_relative = Path("raw") / f"{raw_hash}.bin"
        text_relative = Path("normalized") / f"{text_hash}.txt"
        meta_relative = Path("metadata") / f"{raw_hash}.json"
        document = SourceDocument(
            source_document_id=raw_hash,
            requested_url=resource.requested_url,
            final_url=resource.final_url,
            canonical_url=resource.canonical_url,
            official_domain=official_domain,
            retrieved_at=retrieved_at,
            http_status=resource.http_status,
            media_type=resource.media_type,
            locale=locale,
            fetch_status=FetchStatus.SUCCESS,
            raw_artifact_path=raw_relative.as_posix(),
            raw_sha256=raw_hash,
            normalized_text_path=text_relative.as_posix(),
            normalized_text_sha256=text_hash,
            parser_version=normalized.parser_version,
        )
        _atomic_write(self.root / raw_relative, resource.content)
        _atomic_write(self.root / text_relative, normalized.text.encode("utf-8"))
        payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
        _atomic_write(self.root / meta_relative, f"{payload}\n".encode("utf-8"))
        return document

    def get(self, source_document_id: str) -> SourceDocument | None:
        path = self.root / "metadata" / f"{source_document_id}.json"
        if not path.exists():
            return None
        return SourceDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def load_raw(self, document: SourceDocument) -> bytes:
        if not document.raw_artifact_path:
            raise ValueError("SourceDocument has no raw artifact")
        return (self.root / document.raw_artifact_path).read_bytes()

    def load_normalized(self, document: SourceDocument) -> str:
        if not document.normalized_text_path:
            raise ValueError("SourceDocument has no normalized artifact")
        return (self.root / document.normalized_text_path).read_text(encoding="utf-8")
