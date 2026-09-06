"""Fail-closed deterministic verifier for pricing claims."""

from __future__ import annotations

import re
from datetime import datetime

from src.v2.domain.factories import make_issue
from src.v2.domain.identifiers import sha256_bytes, sha256_text, stable_id, url_has_official_authority
from src.v2.domain.models import (
    BillingPeriod,
    Evidence,
    Issue,
    IssueStage,
    IssueStatus,
    PriceKind,
    PricingClaim,
    SourceDocument,
    VerificationCheck,
    VerifiedClaim,
)
from src.v2.ports import SourceRepositoryPort


class DeterministicPricingVerifier:
    version = "deterministic-pricing-verifier.v1"

    def __init__(self, repository: SourceRepositoryPort) -> None:
        self.repository = repository

    def verify(
        self,
        claim: PricingClaim,
        evidence: Evidence,
        document: SourceDocument,
        *,
        verified_at: datetime,
    ) -> VerifiedClaim | Issue:
        checks: list[VerificationCheck] = []

        stored = self.repository.get(document.source_document_id)
        checks.append(self._check("source-stored", stored is not None))
        checks.append(
            self._check(
                "source-link",
                evidence.source_document_id == document.source_document_id,
            )
        )
        checks.append(
            self._check(
                "official-authority",
                url_has_official_authority(document.final_url, document.official_domain),
            )
        )

        try:
            raw = self.repository.load_raw(document)
            normalized = self.repository.load_normalized(document)
        except (OSError, ValueError):
            raw = b""
            normalized = ""
        checks.append(self._check("raw-hash", sha256_bytes(raw) == document.raw_sha256))
        checks.append(
            self._check(
                "normalized-hash",
                sha256_text(normalized) == document.normalized_text_sha256,
            )
        )
        replayed = normalized[evidence.span_start:evidence.span_end]
        checks.append(self._check("quote-span", replayed == evidence.exact_quote))
        checks.append(self._check("quote-hash", sha256_text(evidence.exact_quote) == evidence.quote_sha256))
        checks.append(self._check("claim-evidence-link", claim.evidence_id == evidence.evidence_id))
        checks.append(self._check("plan-supported", claim.plan_name.casefold() in evidence.exact_quote.casefold()))
        checks.append(self._check("display-supported", claim.display_price in evidence.exact_quote))
        checks.extend(self._price_checks(claim, evidence.exact_quote))

        if not all(check.passed for check in checks):
            failed = ", ".join(check.name for check in checks if not check.passed)
            return make_issue(
                stage=IssueStage.VERIFY,
                status=IssueStatus.REJECTED,
                code="verification-failed",
                message=f"Fail-closed verification failed: {failed}",
                source_document_id=document.source_document_id,
                claim_id=claim.claim_id,
            )

        identity = {
            "claim_id": claim.claim_id,
            "source_document_id": document.source_document_id,
            "raw_sha256": document.raw_sha256,
            "verifier_version": self.version,
        }
        return VerifiedClaim(
            verified_claim_id=stable_id("verified", identity),
            claim=claim,
            verification_checks=checks,
            verified_at=verified_at,
            verifier_version=self.version,
        )

    @staticmethod
    def _check(name: str, passed: bool) -> VerificationCheck:
        return VerificationCheck(name=name, passed=passed, code="ok" if passed else f"{name}-failed")

    def _price_checks(self, claim: PricingClaim, quote: str) -> list[VerificationCheck]:
        lowered = quote.casefold()
        if claim.price_kind == PriceKind.FREE:
            supported = (
                "free" in lowered
                or "at no cost" in lowered
                or bool(re.search(r"(?:\$|USD\s*)0(?:\D|$)", quote, re.I))
            )
            return [self._check("free-supported", supported)]
        if claim.price_kind == PriceKind.CONTACT_SALES:
            return [self._check("contact-sales-supported", "contact sales" in lowered)]

        normalized_amount = claim.amount or ""
        amount_supported = bool(
            re.search(rf"(?<!\d){re.escape(normalized_amount)}(?:\.0+)?(?!\d)", quote.replace(",", ""))
        )
        currency_tokens = {
            "USD": ("usd", "$"),
            "EUR": ("eur", "€"),
            "GBP": ("gbp", "£"),
            "INR": ("inr", "₹"),
        }.get(claim.currency or "", ((claim.currency or "").casefold(),))
        currency_supported = any(token and token in lowered for token in currency_tokens)
        period_tokens = {
            BillingPeriod.MONTH: (
                "/mo",
                "/ mo",
                "/month",
                "/ month",
                "per month",
                "per calendar month",
                "monthly",
            ),
            BillingPeriod.YEAR: (
                "/yr",
                "/ yr",
                "/year",
                "/ year",
                "per year",
                "per calendar year",
                "annual",
                "yearly",
            ),
            BillingPeriod.ONE_TIME: ("one-time", "one time"),
            BillingPeriod.USAGE: ("usage", "pay as you go"),
            BillingPeriod.UNKNOWN: ("",),
        }[claim.billing_period]
        period_supported = claim.billing_period == BillingPeriod.UNKNOWN or any(
            token in lowered for token in period_tokens
        )
        checks = [
            self._check("amount-supported", amount_supported),
            self._check("currency-supported", currency_supported),
            self._check("period-supported", period_supported),
        ]
        if claim.billing_qualifier == "billed_annually":
            checks.append(self._check("annual-qualifier-supported", "billed annually" in lowered))
        return checks
