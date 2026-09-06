"""Command-line entry point for the deterministic CS-001 eval."""

# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.official_pricing import evaluate_dataset


def main() -> int:
    metrics = evaluate_dataset()
    print(json.dumps(metrics.__dict__, indent=2, sort_keys=True))
    return 0 if metrics.passes_release_gates() else 1


if __name__ == "__main__":
    raise SystemExit(main())
