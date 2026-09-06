"""Application orchestration for the official-pricing evidence slice."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from src.v2.domain.factories import make_issue
from src.v2.domain.identifiers import stable_id, url_has_official_authority
from src.v2.domain.models import (
    Evidence,
    Issue,
    IssueStage,
    IssueStatus,
    OfficialPricingInput,
    PricingClaim,
    PricingEvidenceResult,
    RunManifest,
    SourceDocument,
    VerifiedClaim,
)
from src.v2.ports import (
    ClaimExtractorPort,
    ContextProviderPort,
    DiscoveryToolPort,
    ResultWriterPort,
    RuntimePort,
    SourceFetcherPort,
    SourceNormalizerPort,
    SourceRepositoryPort,
    VerifierPort,
)


class OfficialPricingUseCase:
    version = "official-pricing-use-case.v1"

    def __init__(
        self,
        *,
        runtime: RuntimePort,
        discovery: DiscoveryToolPort,
        fetcher: SourceFetcherPort,
        normalizer: SourceNormalizerPort,
        repository: SourceRepositoryPort,
        context_provider: ContextProviderPort,
        extractor: ClaimExtractorPort,
        verifier: VerifierPort,
        result_writer: ResultWriterPort,
        output_root: Path = Path("output/v2/pricing"),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime = runtime
        self.discovery = discovery
        self.fetcher = fetcher
        self.normalizer = normalizer
        self.repository = repository
        self.context_provider = context_provider
        self.extractor = extractor
        self.verifier = verifier
        self.result_writer = result_writer
        self.output_root = output_root
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self, request: OfficialPricingInput) -> PricingEvidenceResult:
        started_at = self._effective_time(request)
        run_id = stable_id(
            "run",
            {
                "input": request.model_dump(mode="json", exclude={"output_path"}),
                "started_at": started_at.isoformat(),
                "use_case": self.version,
            },
        )
        issues: list[Issue] = []
        documents: list[SourceDocument] = []
        evidence_items: list[Evidence] = []
        claims: list[PricingClaim] = []
        verified_claims: list[VerifiedClaim] = []

        urls = self._resolve_urls(request, issues)
        for url in urls:
            document = self._acquire_document(url, request, started_at, issues)
            if document is None:
                continue
            if document.source_document_id not in {item.source_document_id for item in documents}:
                documents.append(document)

            try:
                context = self.runtime.run_step(
                    "context",
                    lambda document=document: self.context_provider.provide(document),
                )
                batch = self.runtime.run_step(
                    "extract",
                    lambda document=document, context=context: self.extractor.extract(
                        request.competitor,
                        document,
                        context,
                    ),
                )
            except Exception as exc:
                issues.append(
                    make_issue(
                        stage=IssueStage.EXTRACT,
                        status=IssueStatus.FAILED,
                        code="extraction-failed",
                        message=f"Extraction failed: {type(exc).__name__}",
                        source_document_id=document.source_document_id,
                    )
                )
                continue

            issues.extend(batch.issues)
            evidence_map = {item.evidence_id: item for item in batch.evidence}
            for item in batch.evidence:
                if item.evidence_id not in {existing.evidence_id for existing in evidence_items}:
                    evidence_items.append(item)
            for claim in batch.claims:
                if claim.claim_id in {existing.claim_id for existing in claims}:
                    continue
                claims.append(claim)
                evidence = evidence_map.get(claim.evidence_id)
                if evidence is None:
                    issues.append(
                        make_issue(
                            stage=IssueStage.VERIFY,
                            status=IssueStatus.REJECTED,
                            code="evidence-not-found",
                            message="Candidate claim references missing Evidence",
                            source_document_id=document.source_document_id,
                            claim_id=claim.claim_id,
                        )
                    )
                    continue
                outcome = self.runtime.run_step(
                    "verify",
                    lambda claim=claim, evidence=evidence, document=document: self.verifier.verify(
                        claim,
                        evidence,
                        document,
                        verified_at=started_at,
                    ),
                )
                if isinstance(outcome, VerifiedClaim):
                    if outcome.verified_claim_id not in {
                        existing.verified_claim_id for existing in verified_claims
                    }:
                        verified_claims.append(outcome)
                else:
                    issues.append(outcome)

        completed_at = started_at if request.as_of else self._aware(self.now())
        manifest = RunManifest(
            run_id=run_id,
            input=request,
            started_at=started_at,
            completed_at=completed_at,
            component_versions={
                "use_case": self.version,
                "runtime": self.runtime.version,
                "discovery": self.discovery.version,
                "fetcher": self.fetcher.version,
                "normalizer": self.normalizer.version,
                "repository": self.repository.version,
                "context_provider": self.context_provider.version,
                "extractor": self.extractor.version,
                "verifier": self.verifier.version,
                "result_writer": self.result_writer.version,
            },
            config={"discovery_limit": 5},
        )
        result = PricingEvidenceResult(
            run_manifest=manifest,
            source_documents=documents,
            candidate_claims=claims,
            evidence=evidence_items,
            verified_claims=verified_claims,
            issues=self._deduplicate_issues(issues),
        )
        path = self.output_path_for(result, request.output_path)
        try:
            self.runtime.run_step("write", lambda: self.result_writer.write(result, path))
        except Exception as exc:
            write_issue = make_issue(
                stage=IssueStage.WRITE,
                status=IssueStatus.FAILED,
                code="result-write-failed",
                message=f"Result write failed: {type(exc).__name__}",
            )
            result = result.model_copy(update={"issues": [*result.issues, write_issue]})
        return result

    def output_path_for(self, result: PricingEvidenceResult, requested_path: str | None = None) -> Path:
        if requested_path:
            return Path(requested_path)
        return self.output_root / result.run_manifest.run_id / "result.json"

    def _resolve_urls(self, request: OfficialPricingInput, issues: list[Issue]) -> list[str]:
        if request.pricing_url:
            return [request.pricing_url]
        try:
            candidates = self.runtime.run_step("discover", lambda: self.discovery.discover(request))
        except Exception as exc:
            issues.append(
                make_issue(
                    stage=IssueStage.DISCOVERY,
                    status=IssueStatus.FAILED,
                    code="discovery-failed",
                    message=f"Discovery failed: {type(exc).__name__}",
                )
            )
            return []
        urls: list[str] = []
        for candidate in candidates:
            if candidate.url in urls:
                continue
            if url_has_official_authority(candidate.url, request.official_domain):
                urls.append(candidate.url)
            if len(urls) == 5:
                break
        if not urls:
            issues.append(
                make_issue(
                    stage=IssueStage.DISCOVERY,
                    status=IssueStatus.NEEDS_REVIEW,
                    code="pricing-page-not-found",
                    message="No pricing page was found on the official domain",
                )
            )
        return urls

    def _acquire_document(
        self,
        url: str,
        request: OfficialPricingInput,
        retrieved_at: datetime,
        issues: list[Issue],
    ) -> SourceDocument | None:
        try:
            resource = self.runtime.run_step(
                "fetch",
                lambda: self.fetcher.fetch(url, locale=request.locale),
            )
        except Exception as exc:
            issues.append(
                make_issue(
                    stage=IssueStage.FETCH,
                    status=IssueStatus.FAILED,
                    code="fetch-failed",
                    message=f"Fetch failed: {type(exc).__name__}",
                )
            )
            return None
        if resource.http_status in {401, 403}:
            issues.append(
                make_issue(
                    stage=IssueStage.FETCH,
                    status=IssueStatus.UNSUPPORTED,
                    code="fetch-blocked",
                    message=f"Pricing source returned HTTP {resource.http_status}",
                )
            )
            return None
        if resource.http_status < 200 or resource.http_status >= 300:
            issues.append(
                make_issue(
                    stage=IssueStage.FETCH,
                    status=IssueStatus.FAILED,
                    code="fetch-http-error",
                    message=f"Pricing source returned HTTP {resource.http_status}",
                )
            )
            return None
        try:
            normalized = self.runtime.run_step("normalize", lambda: self.normalizer.normalize(resource))
        except Exception as exc:
            issues.append(
                make_issue(
                    stage=IssueStage.NORMALIZE,
                    status=IssueStatus.UNSUPPORTED,
                    code="normalization-failed",
                    message=f"Normalization failed: {type(exc).__name__}",
                )
            )
            return None
        try:
            return self.runtime.run_step(
                "store",
                lambda: self.repository.save(
                    resource,
                    normalized,
                    official_domain=request.official_domain,
                    locale=request.locale,
                    retrieved_at=retrieved_at,
                ),
            )
        except Exception as exc:
            issues.append(
                make_issue(
                    stage=IssueStage.STORE,
                    status=IssueStatus.FAILED,
                    code="snapshot-store-failed",
                    message=f"Snapshot store failed: {type(exc).__name__}",
                )
            )
            return None

    @staticmethod
    def _deduplicate_issues(issues: list[Issue]) -> list[Issue]:
        by_id = {issue.issue_id: issue for issue in issues}
        return list(by_id.values())

    def _effective_time(self, request: OfficialPricingInput) -> datetime:
        return self._aware(request.as_of or self.now())

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
