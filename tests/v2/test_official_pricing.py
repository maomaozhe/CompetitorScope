import json
from datetime import datetime, timezone
from pathlib import Path

from evals.official_pricing import (
    FIXTURE_ROOT,
    FixtureDiscovery,
    FixtureFetcher,
    evaluate_dataset,
    load_dataset,
    run_case,
)
from src.v2.application.official_pricing import OfficialPricingUseCase
from src.v2.domain.identifiers import sha256_text
from src.v2.domain.models import Issue, OfficialPricingInput, VerifiedClaim
from src.v2.infrastructure.context import SnapshotContextProvider
from src.v2.infrastructure.extractor import DeterministicPricingClaimExtractor
from src.v2.infrastructure.normalizer import DeterministicTextNormalizer
from src.v2.infrastructure.repository import FilesystemSourceRepository
from src.v2.infrastructure.result_writer import JsonPricingResultWriter
from src.v2.infrastructure.runtime import LocalSequentialRuntime
from src.v2.infrastructure.verifier import DeterministicPricingVerifier
from src.v2.ports import FetchedResource


def _build_use_case(tmp_path: Path, url: str, fixture: str, *, final_url: str | None = None):
    repository = FilesystemSourceRepository(tmp_path / "sources")
    fetcher = FixtureFetcher(
        {url: FIXTURE_ROOT / fixture},
        {url: final_url} if final_url else None,
    )
    use_case = OfficialPricingUseCase(
        runtime=LocalSequentialRuntime(),
        discovery=FixtureDiscovery([url]),
        fetcher=fetcher,
        normalizer=DeterministicTextNormalizer(),
        repository=repository,
        context_provider=SnapshotContextProvider(repository),
        extractor=DeterministicPricingClaimExtractor(),
        verifier=DeterministicPricingVerifier(repository),
        result_writer=JsonPricingResultWriter(),
        output_root=tmp_path / "results",
    )
    return use_case, repository


def test_explicit_url_pipeline_persists_verified_only_result(tmp_path):
    case = load_dataset()["cases"][0]
    result = run_case(case, tmp_path)

    assert len(result.verified_claims) == 5
    assert all(isinstance(item, VerifiedClaim) for item in result.verified_claims)
    assert {item.claim.billing_period for item in result.verified_claims} >= {"month", "year"}
    assert result.source_documents[0].raw_sha256 == result.source_documents[0].source_document_id

    result_path = tmp_path / "results" / result.run_manifest.run_id / "result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert "facts" not in payload
    assert len(payload["verified_claims"]) == 5
    assert "candidate_claims" in payload


def test_discovery_path_ignores_non_official_candidates(tmp_path):
    case = load_dataset()["cases"][1]
    url = case["pricing_url"]
    use_case, _ = _build_use_case(tmp_path, url, case["fixture"])
    use_case.discovery = FixtureDiscovery(["https://cursor.com.attacker.example/pricing", url])
    request = OfficialPricingInput(
        competitor=case["competitor"],
        official_domain=case["official_domain"],
        as_of=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    result = use_case.run(request)

    assert result.source_documents[0].requested_url == url
    assert {item.claim.price_kind for item in result.verified_claims} == {"free", "contact_sales"}


def test_non_official_redirect_fails_closed(tmp_path):
    case = load_dataset()["cases"][1]
    url = case["pricing_url"]
    use_case, _ = _build_use_case(
        tmp_path,
        url,
        case["fixture"],
        final_url="https://attacker.example/pricing",
    )
    result = use_case.run(
        OfficialPricingInput(
            competitor="Cursor",
            official_domain="cursor.com",
            pricing_url=url,
            as_of=datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
    )

    assert result.verified_claims == []
    assert any(issue.code == "verification-failed" for issue in result.issues)


def test_verifier_rejects_tampered_quote(tmp_path):
    case = load_dataset()["cases"][0]
    result = run_case(case, tmp_path)
    document = result.source_documents[0]
    claim = result.candidate_claims[0]
    evidence = next(item for item in result.evidence if item.evidence_id == claim.evidence_id)
    tampered = evidence.model_copy(
        update={"exact_quote": f"{evidence.exact_quote} altered", "quote_sha256": sha256_text("wrong")}
    )
    repository = FilesystemSourceRepository(tmp_path / "sources")
    outcome = DeterministicPricingVerifier(repository).verify(
        claim,
        tampered,
        document,
        verified_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    assert isinstance(outcome, Issue)
    assert outcome.status == "rejected"


def test_offline_eval_dataset_meets_release_gates():
    metrics = evaluate_dataset()
    assert metrics.passes_release_gates(), metrics


class InlineFetcher:
    version = "inline-fetcher.v1"

    def __init__(self, content: bytes, *, media_type: str = "text/html", status: int = 200):
        self.content = content
        self.media_type = media_type
        self.status = status

    def fetch(self, url: str, *, locale: str) -> FetchedResource:
        del locale
        return FetchedResource(
            requested_url=url,
            final_url=url,
            http_status=self.status,
            media_type=self.media_type,
            content=self.content,
        )


class FailingFetcher:
    version = "failing-fetcher.v1"

    def fetch(self, url: str, *, locale: str) -> FetchedResource:
        del url, locale
        raise TimeoutError("fixture timeout")


class FailingWriter:
    version = "failing-writer.v1"

    def write(self, result, path):
        del result, path
        raise OSError("fixture write failure")


def _inline_use_case(tmp_path: Path, content: bytes, *, media_type: str = "text/html"):
    url = "https://example.com/pricing"
    repository = FilesystemSourceRepository(tmp_path / "sources")
    return OfficialPricingUseCase(
        runtime=LocalSequentialRuntime(),
        discovery=FixtureDiscovery([url]),
        fetcher=InlineFetcher(content, media_type=media_type),
        normalizer=DeterministicTextNormalizer(),
        repository=repository,
        context_provider=SnapshotContextProvider(repository),
        extractor=DeterministicPricingClaimExtractor(),
        verifier=DeterministicPricingVerifier(repository),
        result_writer=JsonPricingResultWriter(),
        output_root=tmp_path / "results",
    )


def _inline_request(*, pricing_url: str | None = "https://example.com/pricing"):
    return OfficialPricingInput(
        competitor="Example",
        official_domain="example.com",
        pricing_url=pricing_url,
        as_of=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def test_annual_effective_monthly_price_keeps_qualifier(tmp_path):
    html = b"<h2>Core</h2><p>$17 USD / month, billed annually</p>"
    result = _inline_use_case(tmp_path, html).run(_inline_request())

    assert len(result.verified_claims) == 1
    claim = result.verified_claims[0].claim
    assert claim.billing_period == "month"
    assert claim.billing_qualifier == "billed_annually"


def test_tax_and_credit_amounts_are_not_verified_as_plan_prices(tmp_path):
    html = (
        b"<h2>Pro</h2><p>$10 USD / month</p>"
        b"<p>$2 USD tax may apply</p><p>$15 USD monthly credits included</p>"
    )
    result = _inline_use_case(tmp_path, html).run(_inline_request())

    assert [item.claim.amount for item in result.verified_claims] == ["10"]
    assert any(issue.code == "unsupported-pricing-modifier" for issue in result.issues)


def test_generic_free_mentions_are_not_promoted_to_pricing_facts(tmp_path):
    html = (
        b"<h1>Documentation</h1><p>Free use of the product is available to students.</p>"
        b"<p>Upgrade beyond the free plan limits.</p>"
        b"<h2>Product Free</h2><p>$0 USD</p>"
    )
    result = _inline_use_case(tmp_path, html).run(_inline_request())

    assert len(result.verified_claims) == 1
    assert result.verified_claims[0].claim.plan_name == "Product Free"


def test_named_free_plan_at_no_cost_is_supported(tmp_path):
    html = b"<p>Product Free: limited access to product features at no cost.</p>"
    result = _inline_use_case(tmp_path, html).run(_inline_request())

    assert len(result.verified_claims) == 1
    assert result.verified_claims[0].claim.plan_name == "Product Free"


def test_no_price_is_a_structured_success_with_issue(tmp_path):
    result = _inline_use_case(tmp_path, b"<h1>Pricing</h1><p>Ask us about plans.</p>").run(
        _inline_request()
    )

    assert result.verified_claims == []
    assert any(issue.code == "no-pricing-found" for issue in result.issues)


def test_unsupported_media_does_not_enter_extraction(tmp_path):
    result = _inline_use_case(tmp_path, b"%PDF", media_type="application/pdf").run(
        _inline_request()
    )

    assert result.source_documents == []
    assert result.candidate_claims == []
    assert any(issue.code == "normalization-failed" for issue in result.issues)


def test_fetch_failure_does_not_enter_extraction(tmp_path):
    use_case = _inline_use_case(tmp_path, b"unused")
    use_case.fetcher = FailingFetcher()
    result = use_case.run(_inline_request())

    assert result.source_documents == []
    assert result.candidate_claims == []
    assert any(issue.code == "fetch-failed" for issue in result.issues)


def test_result_write_failure_is_reported_without_losing_verified_claims(tmp_path):
    use_case = _inline_use_case(tmp_path, b"<h2>Pro</h2><p>$10 USD / month</p>")
    use_case.result_writer = FailingWriter()
    result = use_case.run(_inline_request())

    assert len(result.verified_claims) == 1
    assert any(issue.code == "result-write-failed" for issue in result.issues)


def test_discovery_without_official_candidate_returns_issue(tmp_path):
    use_case = _inline_use_case(tmp_path, b"<p>unused</p>")
    use_case.discovery = FixtureDiscovery(["https://attacker.example/pricing"])
    result = use_case.run(_inline_request(pricing_url=None))

    assert result.source_documents == []
    assert any(issue.code == "pricing-page-not-found" for issue in result.issues)


def test_duplicate_source_content_is_deduplicated(tmp_path):
    first = "https://example.com/pricing"
    second = "https://www.example.com/plans"
    fixture = b"<h2>Pro</h2><p>$10 USD / month</p>"
    repository = FilesystemSourceRepository(tmp_path / "sources")
    use_case = OfficialPricingUseCase(
        runtime=LocalSequentialRuntime(),
        discovery=FixtureDiscovery([first, second]),
        fetcher=FixtureFetcher({
            first: tmp_path / "fixture.html",
            second: tmp_path / "fixture.html",
        }),
        normalizer=DeterministicTextNormalizer(),
        repository=repository,
        context_provider=SnapshotContextProvider(repository),
        extractor=DeterministicPricingClaimExtractor(),
        verifier=DeterministicPricingVerifier(repository),
        result_writer=JsonPricingResultWriter(),
        output_root=tmp_path / "results",
    )
    (tmp_path / "fixture.html").write_bytes(fixture)
    result = use_case.run(_inline_request(pricing_url=None))

    assert len(result.source_documents) == 1
    assert len(result.verified_claims) == 1
