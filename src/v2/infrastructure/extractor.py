"""Deterministic candidate extractor for core official-pricing facts."""

from __future__ import annotations

import re

from src.v2.domain.factories import make_issue
from src.v2.domain.identifiers import sha256_text, stable_id
from src.v2.domain.models import (
    BillingPeriod,
    Evidence,
    IssueStage,
    IssueStatus,
    PriceKind,
    PricingClaim,
    SourceDocument,
)
from src.v2.ports import ExtractionBatch


_MONEY_RE = re.compile(
    r"(?:(?P<code_before>USD|EUR|GBP|INR)\s*)?"
    r"(?P<symbol>[$€£₹¥])\s*(?P<amount>\d+(?:[,.]\d+)?)"
    r"(?:\s*(?P<code_after>USD|EUR|GBP|INR))?",
    re.IGNORECASE,
)
_GENERIC_LINES = {
    "pricing",
    "plans",
    "plans & pricing",
    "monthly",
    "yearly",
    "individual",
    "business",
    "for individuals",
    "for businesses",
    "what's included",
    "features",
}
_SYMBOL_CURRENCIES = {"€": "EUR", "£": "GBP", "₹": "INR"}
_UNSUPPORTED_FACT_TERMS = (
    "tax",
    "vat",
    "discount",
    "coupon",
    "promotion",
    "promo",
    "monthly credits",
    "ai credits",
)


def _line_records(text: str) -> list[tuple[str, int, int]]:
    records: list[tuple[str, int, int]] = []
    cursor = 0
    for raw in text.splitlines(keepends=True):
        content = raw.rstrip("\r\n")
        leading = len(content) - len(content.lstrip())
        line = content.strip()
        if line:
            start = cursor + leading
            records.append((line, start, start + len(line)))
        cursor += len(raw)
    if text and not text.endswith(("\n", "\r")) and not records:
        records.append((text.strip(), 0, len(text.strip())))
    return records


def _period(value: str) -> BillingPeriod:
    lowered = value.casefold()
    if (
        re.search(r"(?:/\s*|per\s+)(?:user\s*/\s*)?(?:calendar\s+)?(?:mo\.?|month)", lowered)
        or "monthly" in lowered
    ):
        return BillingPeriod.MONTH
    if (
        re.search(r"(?:/\s*|per\s+)(?:calendar\s+)?(?:yr\.?|year)", lowered)
        or "annual" in lowered
        or "yearly" in lowered
    ):
        return BillingPeriod.YEAR
    if "one-time" in lowered or "one time" in lowered:
        return BillingPeriod.ONE_TIME
    if "usage" in lowered or "pay as you go" in lowered:
        return BillingPeriod.USAGE
    return BillingPeriod.UNKNOWN


def _currency(match: re.Match[str], line: str) -> str | None:
    code = match.group("code_before") or match.group("code_after")
    if code:
        return code.upper()
    explicit_codes = {item.upper() for item in re.findall(r"\b(?:USD|EUR|GBP|INR)\b", line, re.I)}
    if len(explicit_codes) == 1:
        return next(iter(explicit_codes))
    return _SYMBOL_CURRENCIES.get(match.group("symbol"))


def _clean_plan_prefix(value: str) -> str:
    return value.strip(" \t|:–—-·")


class DeterministicPricingClaimExtractor:
    version = "deterministic-pricing.v1"

    def extract(
        self,
        competitor: str,
        document: SourceDocument,
        context: str,
    ) -> ExtractionBatch:
        claims: list[PricingClaim] = []
        evidence_items: list[Evidence] = []
        issues = []
        evidence_by_id: dict[str, Evidence] = {}
        current_plan = ""
        current_plan_start = 0

        records = _line_records(context)
        for record_index, (line, line_start, line_end) in enumerate(records):
            lowered = line.casefold()
            money_matches = list(_MONEY_RE.finditer(line))
            is_contact = "contact sales" in lowered
            colon_prefix = lowered.split(":", 1)[0] if ":" in lowered else ""
            is_free_text = lowered == "free" or (
                " at no cost" in lowered and "free" in colon_prefix
            )

            next_line = records[record_index + 1][0] if record_index + 1 < len(records) else ""
            next_money = list(_MONEY_RE.finditer(next_line))
            if (
                is_free_text
                and not money_matches
                and next_money
                and all(float(match.group("amount").replace(",", "")) == 0 for match in next_money)
            ):
                current_plan = line
                current_plan_start = line_start
                continue

            if money_matches and any(term in lowered for term in _UNSUPPORTED_FACT_TERMS):
                issues.append(
                    make_issue(
                        stage=IssueStage.EXTRACT,
                        status=IssueStatus.UNSUPPORTED,
                        code="unsupported-pricing-modifier",
                        message="Tax, promotion, or credit entitlement is outside the CS-001 fact scope",
                        source_document_id=document.source_document_id,
                    )
                )
                continue

            if not money_matches and not is_contact and not is_free_text:
                if lowered == "custom":
                    continue
                if lowered not in _GENERIC_LINES and len(line) <= 80:
                    current_plan = line
                    current_plan_start = line_start
                continue

            if money_matches:
                first_marker = money_matches[0].start()
            elif is_contact:
                first_marker = lowered.find("contact sales")
            elif " at no cost" in lowered and ":" in line:
                first_marker = line.find(":")
            else:
                first_marker = lowered.find("free")
            prefix = _clean_plan_prefix(line[:first_marker])
            if prefix and len(prefix) <= 80:
                plan_name = prefix
                quote_start = line_start
            else:
                plan_name = current_plan
                quote_start = current_plan_start if current_plan else line_start

            if not plan_name:
                issues.append(
                    make_issue(
                        stage=IssueStage.EXTRACT,
                        status=IssueStatus.NEEDS_REVIEW,
                        code="plan-name-missing",
                        message="Pricing marker has no deterministic plan name",
                        source_document_id=document.source_document_id,
                    )
                )
                continue

            quote = context[quote_start:line_end]
            evidence_id = stable_id(
                "evidence",
                {
                    "source_document_id": document.source_document_id,
                    "span_start": quote_start,
                    "span_end": line_end,
                    "quote_sha256": sha256_text(quote),
                },
            )
            evidence = Evidence(
                evidence_id=evidence_id,
                source_document_id=document.source_document_id,
                exact_quote=quote,
                span_start=quote_start,
                span_end=line_end,
                quote_sha256=sha256_text(quote),
                locator=plan_name,
                extraction_method=self.version,
            )
            evidence_by_id[evidence_id] = evidence

            candidate_specs: list[dict[str, str | None | BillingPeriod | PriceKind]] = []
            if is_contact:
                candidate_specs.append(
                    {
                        "price_kind": PriceKind.CONTACT_SALES,
                        "amount": None,
                        "currency": None,
                        "billing_period": BillingPeriod.UNKNOWN,
                        "billing_qualifier": None,
                        "display_price": line,
                    }
                )
            elif is_free_text and not money_matches:
                candidate_specs.append(
                    {
                        "price_kind": PriceKind.FREE,
                        "amount": None,
                        "currency": None,
                        "billing_period": BillingPeriod.UNKNOWN,
                        "billing_qualifier": None,
                        "display_price": line,
                    }
                )

            for index, match in enumerate(money_matches):
                amount = match.group("amount").replace(",", "")
                if float(amount) == 0:
                    candidate_specs.append(
                        {
                            "price_kind": PriceKind.FREE,
                            "amount": None,
                            "currency": None,
                            "billing_period": BillingPeriod.UNKNOWN,
                            "billing_qualifier": None,
                            "display_price": line,
                        }
                    )
                    continue
                currency = _currency(match, line)
                if currency is None:
                    issues.append(
                        make_issue(
                            stage=IssueStage.EXTRACT,
                            status=IssueStatus.NEEDS_REVIEW,
                            code="currency-ambiguous",
                            message=f"Currency is not explicit for plan {plan_name}",
                            source_document_id=document.source_document_id,
                        )
                    )
                    continue
                next_start = money_matches[index + 1].start() if index + 1 < len(money_matches) else len(line)
                price_segment = line[match.start():next_start].strip()
                period = _period(price_segment)
                qualifier = "billed_annually" if "billed annually" in lowered else None
                candidate_specs.append(
                    {
                        "price_kind": PriceKind.FIXED,
                        "amount": amount,
                        "currency": currency,
                        "billing_period": period,
                        "billing_qualifier": qualifier,
                        "display_price": price_segment,
                    }
                )

            for spec in candidate_specs:
                identity = {
                    "competitor": competitor,
                    "plan_name": plan_name,
                    **{key: (value.value if isinstance(value, (PriceKind, BillingPeriod)) else value) for key, value in spec.items()},
                    "evidence_id": evidence_id,
                }
                claims.append(
                    PricingClaim(
                        claim_id=stable_id("claim", identity),
                        competitor=competitor,
                        plan_name=plan_name,
                        evidence_id=evidence_id,
                        **spec,
                    )
                )

        evidence_items.extend(evidence_by_id.values())
        if not claims:
            issues.append(
                make_issue(
                    stage=IssueStage.EXTRACT,
                    status=IssueStatus.NEEDS_REVIEW,
                    code="no-pricing-found",
                    message="No candidate core pricing facts were extracted",
                    source_document_id=document.source_document_id,
                )
            )
        return ExtractionBatch(claims=claims, evidence=evidence_items, issues=issues)
