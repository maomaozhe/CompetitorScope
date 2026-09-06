"""Replaceable ports for the V2 official-pricing use case."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TypeVar

from src.v2.domain.models import (
    Evidence,
    Issue,
    OfficialPricingInput,
    PricingClaim,
    PricingEvidenceResult,
    SourceDocument,
    VerifiedClaim,
)


T = TypeVar("T")


@dataclass(frozen=True)
class DiscoveryCandidate:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class FetchedResource:
    requested_url: str
    final_url: str
    http_status: int
    media_type: str
    content: bytes
    canonical_url: str | None = None


@dataclass(frozen=True)
class NormalizedResource:
    text: str
    parser_version: str


@dataclass(frozen=True)
class ExtractionBatch:
    claims: list[PricingClaim]
    evidence: list[Evidence]
    issues: list[Issue]


class RuntimePort(Protocol):
    version: str

    def run_step(self, name: str, operation: Callable[[], T]) -> T: ...


class DiscoveryToolPort(Protocol):
    version: str

    def discover(self, request: OfficialPricingInput) -> list[DiscoveryCandidate]: ...


class SourceFetcherPort(Protocol):
    version: str

    def fetch(self, url: str, *, locale: str) -> FetchedResource: ...


class SourceNormalizerPort(Protocol):
    version: str

    def normalize(self, resource: FetchedResource) -> NormalizedResource: ...


class SourceRepositoryPort(Protocol):
    version: str

    def save(
        self,
        resource: FetchedResource,
        normalized: NormalizedResource,
        *,
        official_domain: str,
        locale: str,
        retrieved_at: datetime,
    ) -> SourceDocument: ...

    def get(self, source_document_id: str) -> SourceDocument | None: ...

    def load_raw(self, document: SourceDocument) -> bytes: ...

    def load_normalized(self, document: SourceDocument) -> str: ...


class ContextProviderPort(Protocol):
    version: str

    def provide(self, document: SourceDocument) -> str: ...


class ClaimExtractorPort(Protocol):
    version: str

    def extract(self, competitor: str, document: SourceDocument, context: str) -> ExtractionBatch: ...


class VerifierPort(Protocol):
    version: str

    def verify(
        self,
        claim: PricingClaim,
        evidence: Evidence,
        document: SourceDocument,
        *,
        verified_at: datetime,
    ) -> VerifiedClaim | Issue: ...


class ResultWriterPort(Protocol):
    version: str

    def write(self, result: PricingEvidenceResult, path: Path) -> Path: ...
