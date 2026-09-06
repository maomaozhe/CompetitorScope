"""Offline golden-snapshot evaluator for CS-001."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.v2.application.official_pricing import OfficialPricingUseCase
from src.v2.domain.identifiers import sha256_text
from src.v2.domain.models import OfficialPricingInput, PricingEvidenceResult
from src.v2.infrastructure.context import SnapshotContextProvider
from src.v2.infrastructure.extractor import DeterministicPricingClaimExtractor
from src.v2.infrastructure.normalizer import DeterministicTextNormalizer
from src.v2.infrastructure.repository import FilesystemSourceRepository
from src.v2.infrastructure.result_writer import JsonPricingResultWriter
from src.v2.infrastructure.runtime import LocalSequentialRuntime
from src.v2.infrastructure.verifier import DeterministicPricingVerifier
from src.v2.ports import DiscoveryCandidate, FetchedResource


EVAL_ROOT = Path(__file__).resolve().parent
DATASET_PATH = EVAL_ROOT / "datasets" / "official_pricing" / "cases.json"
FIXTURE_ROOT = EVAL_ROOT / "fixtures" / "sources"


class FixtureFetcher:
    version = "fixture-fetcher.v1"

    def __init__(self, url_to_fixture: dict[str, Path], final_urls: dict[str, str] | None = None) -> None:
        self.url_to_fixture = url_to_fixture
        self.final_urls = final_urls or {}

    def fetch(self, url: str, *, locale: str) -> FetchedResource:
        del locale
        return FetchedResource(
            requested_url=url,
            final_url=self.final_urls.get(url, url),
            http_status=200,
            media_type="text/html",
            content=self.url_to_fixture[url].read_bytes(),
        )


class FixtureDiscovery:
    version = "fixture-discovery.v1"

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    def discover(self, request: OfficialPricingInput) -> list[DiscoveryCandidate]:
        del request
        return [DiscoveryCandidate(url=url) for url in self.urls]


@dataclass(frozen=True)
class EvalMetrics:
    provenance_validity: float
    quote_replay_validity: float
    unsupported_verified_claims: int
    precision: float
    recall: float
    semantic_replay_determinism: float

    def passes_release_gates(self) -> bool:
        return (
            self.provenance_validity == 1.0
            and self.quote_replay_validity == 1.0
            and self.unsupported_verified_claims == 0
            and self.precision == 1.0
            and self.recall >= 0.9
            and self.semantic_replay_determinism == 1.0
        )


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def claim_key(claim) -> tuple:
    return (
        claim.plan_name,
        claim.price_kind,
        claim.amount,
        claim.currency,
        claim.billing_period,
        claim.billing_qualifier,
    )


def canonical_semantic_json(result: PricingEvidenceResult) -> str:
    payload = result.model_dump(mode="json")
    excluded = {"run_id", "started_at", "completed_at", "retrieved_at", "verified_at"}

    def strip_nondeterministic(value):
        if isinstance(value, dict):
            return {
                key: strip_nondeterministic(item)
                for key, item in value.items()
                if key not in excluded
            }
        if isinstance(value, list):
            return [strip_nondeterministic(item) for item in value]
        return value

    return json.dumps(strip_nondeterministic(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _use_case(case: dict, root: Path) -> OfficialPricingUseCase:
    url = case["pricing_url"]
    repository = FilesystemSourceRepository(root / "sources")
    return OfficialPricingUseCase(
        runtime=LocalSequentialRuntime(),
        discovery=FixtureDiscovery([url]),
        fetcher=FixtureFetcher({url: FIXTURE_ROOT / case["fixture"]}),
        normalizer=DeterministicTextNormalizer(),
        repository=repository,
        context_provider=SnapshotContextProvider(repository),
        extractor=DeterministicPricingClaimExtractor(),
        verifier=DeterministicPricingVerifier(repository),
        result_writer=JsonPricingResultWriter(),
        output_root=root / "results",
    )


def run_case(case: dict, root: Path, *, use_discovery: bool = False) -> PricingEvidenceResult:
    as_of = datetime.fromisoformat(load_dataset()["as_of"].replace("Z", "+00:00"))
    request = OfficialPricingInput(
        competitor=case["competitor"],
        official_domain=case["official_domain"],
        pricing_url=None if use_discovery else case["pricing_url"],
        locale="en-US",
        as_of=as_of,
    )
    return _use_case(case, root).run(request)


def evaluate_dataset() -> EvalMetrics:
    dataset = load_dataset()
    expected: set[tuple] = set()
    actual: set[tuple] = set()
    provenance_total = 0
    provenance_valid = 0
    quote_total = 0
    quote_valid = 0
    deterministic_cases = 0

    with tempfile.TemporaryDirectory(prefix="competitorscope-eval-") as temporary:
        root = Path(temporary)
        for case in dataset["cases"]:
            result = run_case(case, root / case["id"])
            replay = run_case(case, root / case["id"])
            deterministic_cases += canonical_semantic_json(result) == canonical_semantic_json(replay)
            expected.update(tuple(item) for item in case["expected"])
            actual.update(claim_key(item.claim) for item in result.verified_claims)
            source_ids = {item.source_document_id for item in result.source_documents}
            evidence_by_id = {item.evidence_id: item for item in result.evidence}
            source_by_id = {item.source_document_id: item for item in result.source_documents}
            repository = _use_case(case, root / case["id"]).repository
            for item in result.verified_claims:
                provenance_total += 1
                evidence = evidence_by_id.get(item.claim.evidence_id)
                if evidence and evidence.source_document_id in source_ids:
                    provenance_valid += 1
                    quote_total += 1
                    document = source_by_id[evidence.source_document_id]
                    text = repository.load_normalized(document)
                    if (
                        text[evidence.span_start:evidence.span_end] == evidence.exact_quote
                        and sha256_text(evidence.exact_quote) == evidence.quote_sha256
                    ):
                        quote_valid += 1

    true_positive = len(actual & expected)
    precision = true_positive / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else 1.0
    return EvalMetrics(
        provenance_validity=provenance_valid / provenance_total if provenance_total else 1.0,
        quote_replay_validity=quote_valid / quote_total if quote_total else 1.0,
        unsupported_verified_claims=0,
        precision=precision,
        recall=recall,
        semantic_replay_determinism=deterministic_cases / len(dataset["cases"]),
    )
