"""Run the V2 official-pricing evidence slice from the command line."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError

from src.v2.application.official_pricing import OfficialPricingUseCase
from src.v2.domain.models import OfficialPricingInput
from src.v2.infrastructure.context import SnapshotContextProvider
from src.v2.infrastructure.discovery import TavilyOfficialPricingDiscovery
from src.v2.infrastructure.extractor import DeterministicPricingClaimExtractor
from src.v2.infrastructure.fetcher import HttpSourceFetcher
from src.v2.infrastructure.normalizer import DeterministicTextNormalizer
from src.v2.infrastructure.repository import FilesystemSourceRepository
from src.v2.infrastructure.result_writer import JsonPricingResultWriter
from src.v2.infrastructure.runtime import LocalSequentialRuntime
from src.v2.infrastructure.verifier import DeterministicPricingVerifier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract verified facts from an official pricing page")
    parser.add_argument("--competitor", required=True)
    parser.add_argument("--official-domain", required=True)
    parser.add_argument("--pricing-url")
    parser.add_argument("--locale", default="und")
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    parser.add_argument("--output", dest="output_path")
    return parser


def _build_use_case(output_root: Path) -> OfficialPricingUseCase:
    repository = FilesystemSourceRepository(output_root / "source_documents")
    return OfficialPricingUseCase(
        runtime=LocalSequentialRuntime(),
        discovery=TavilyOfficialPricingDiscovery(),
        fetcher=HttpSourceFetcher(),
        normalizer=DeterministicTextNormalizer(),
        repository=repository,
        context_provider=SnapshotContextProvider(repository),
        extractor=DeterministicPricingClaimExtractor(),
        verifier=DeterministicPricingVerifier(repository),
        result_writer=JsonPricingResultWriter(),
        output_root=output_root,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        request = OfficialPricingInput(
            competitor=args.competitor,
            official_domain=args.official_domain,
            pricing_url=args.pricing_url,
            locale=args.locale,
            as_of=args.as_of,
            output_path=args.output_path,
        )
    except ValidationError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2

    output_root = ROOT / "output" / "v2" / "pricing"
    use_case = _build_use_case(output_root)
    try:
        result = use_case.run(request)
    except Exception as exc:
        print(f"Pipeline failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    output_path = use_case.output_path_for(result, request.output_path)
    print(f"Run: {result.run_manifest.run_id}")
    print(f"Result: {output_path}")
    print(f"Verified pricing facts: {len(result.verified_claims)}")
    source_by_id = {item.source_document_id: item for item in result.source_documents}
    evidence_by_id = {item.evidence_id: item for item in result.evidence}
    for verified in result.verified_claims:
        claim = verified.claim
        evidence = evidence_by_id[claim.evidence_id]
        source = source_by_id[evidence.source_document_id]
        print(
            f"- {claim.plan_name}: {claim.display_price} "
            f"[{claim.billing_period}{f', {claim.billing_qualifier}' if claim.billing_qualifier else ''}]"
        )
        print(f"  Source: {source.final_url}")
        print(f"  Quote: {evidence.exact_quote}")
    if result.issues:
        print(f"Issues: {len(result.issues)}")
        for issue in result.issues:
            print(f"- [{issue.status}] {issue.code}: {issue.message}")
    if any(issue.code == "result-write-failed" for issue in result.issues):
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
