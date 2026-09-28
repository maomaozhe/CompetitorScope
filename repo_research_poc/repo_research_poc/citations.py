"""Deterministic replay of source citations against a fixed local snapshot."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field


EXCLUDED_PARTS = frozenset({
    ".git", ".venv", "node_modules", "__pycache__", "output", "evals", "repo_research_poc"
})
MAX_FILES = 20_000
MAX_BYTES = 512 * 1024 * 1024


class Citation(BaseModel):
    path: str = Field(description="POSIX path relative to the repository snapshot")
    start_line: int = Field(description="First one-based source line")
    end_line: int = Field(description="Last one-based source line")
    quote: str = Field(description="Exact source text within the cited lines")


@dataclass(frozen=True)
class CitationIssue:
    index: int
    code: str
    detail: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture_manifest(snapshot: Path) -> dict[str, str]:
    """Hash readable source files, excluding local eval data and generated trees."""
    snapshot = snapshot.resolve(strict=True)
    if not snapshot.is_dir():
        raise ValueError("snapshot must be a directory")
    manifest: dict[str, str] = {}
    total_bytes = 0
    for directory, dirs, files in os.walk(snapshot, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_PARTS and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            if name == ".env" or name.startswith(".env."):
                continue
            source = Path(directory) / name
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(snapshot).as_posix()
            size = source.stat().st_size
            total_bytes += size
            if len(manifest) >= MAX_FILES or total_bytes > MAX_BYTES:
                raise ValueError("snapshot exceeds POC file or byte limit")
            manifest[relative] = _sha256(source)
    return manifest


def validate_citations(
    snapshot: Path, manifest: dict[str, str], citations: list[Citation]
) -> list[CitationIssue]:
    root = snapshot.resolve(strict=True)
    issues: list[CitationIssue] = []
    for index, citation in enumerate(citations):
        relative = PurePosixPath(citation.path)
        if (
            not citation.path
            or "\\" in citation.path
            or relative.is_absolute()
            or any(part in (".", "..") for part in relative.parts)
            or relative.as_posix() not in manifest
        ):
            issues.append(CitationIssue(index, "invalid_path", citation.path))
            continue
        source = root.joinpath(*relative.parts)
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            issues.append(CitationIssue(index, "invalid_path", citation.path))
            continue
        if not source.is_file() or _sha256(source) != manifest[citation.path]:
            issues.append(CitationIssue(index, "source_changed", citation.path))
            continue
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(CitationIssue(index, "unreadable_source", citation.path))
            continue
        if "\x00" in text:
            issues.append(CitationIssue(index, "unreadable_source", citation.path))
            continue
        lines = text.splitlines()
        if citation.start_line < 1 or citation.end_line < citation.start_line or citation.end_line > len(lines):
            issues.append(CitationIssue(index, "invalid_lines", citation.path))
            continue
        span = "\n".join(lines[citation.start_line - 1 : citation.end_line])
        if not citation.quote.strip() or citation.quote not in span:
            issues.append(CitationIssue(index, "quote_mismatch", citation.path))
    return issues
