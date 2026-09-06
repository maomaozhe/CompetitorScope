"""JSON result writer that serializes the verified-only facts view."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from src.v2.domain.models import PricingEvidenceResult


class JsonPricingResultWriter:
    version = "pricing-json-writer.v1"

    def write(self, result: PricingEvidenceResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = result.model_dump(mode="json")
        encoded = f"{json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)}\n".encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()
        return path
