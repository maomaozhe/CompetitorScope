"""Make a disposable, filtered view of an explicitly supplied repository snapshot."""

from __future__ import annotations

import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from deepagents.backends import FilesystemBackend

from .citations import _sha256, capture_manifest


@dataclass(frozen=True)
class StagedSnapshot:
    root: Path
    manifest: dict[str, str]


class ReadOnlySnapshotBackend(FilesystemBackend):
    """Deny mutation even if a future caller accidentally exposes a write tool."""

    def _ripgrep_search(self, pattern, base_full, include_glob, max_count=None):
        # Deep Agents 0.7.19 otherwise launches host ripgrep with the Windows
        # default text codec. Force its bounded in-process Python grep path.
        return None, False

    def write(self, file_path: str, content: str):
        raise PermissionError("repository snapshot is read-only")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        raise PermissionError("repository snapshot is read-only")

    def delete(self, file_path: str):
        raise PermissionError("repository snapshot is read-only")


def validate_request(snapshot: Path, commit_sha: str, question: str, output_dir: Path) -> None:
    if not snapshot.is_dir():
        raise ValueError("snapshot must be an existing directory")
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha) is None:
        raise ValueError("commit SHA must be 40 hexadecimal characters")
    if not question.strip():
        raise ValueError("question cannot be empty")
    if output_dir.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("output directory must be outside the repository snapshot")


@contextmanager
def staged_snapshot(snapshot: Path) -> Iterator[StagedSnapshot]:
    """Copy source bytes into a temporary tree; never expose eval or secret files."""
    manifest = capture_manifest(snapshot)
    with tempfile.TemporaryDirectory(prefix="repo-research-") as temp:
        root = Path(temp)
        for relative, digest in manifest.items():
            source = snapshot / Path(relative)
            target = root / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if _sha256(target) != digest:
                raise ValueError(f"snapshot changed while staging: {relative}")
        yield StagedSnapshot(root=root, manifest=manifest)
