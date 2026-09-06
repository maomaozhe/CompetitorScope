"""Local sequential runtime adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


class LocalSequentialRuntime:
    version = "local-sequential.v1"

    def run_step(self, name: str, operation: Callable[[], T]) -> T:
        del name
        return operation()
