"""Strict domain models for the official-pricing evidence slice."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.v2.domain.identifiers import normalize_official_domain


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class FetchStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"


class PriceKind(str, Enum):
    FREE = "free"
    FIXED = "fixed"
    CONTACT_SALES = "contact_sales"


class BillingPeriod(str, Enum):
    MONTH = "month"
    YEAR = "year"
    ONE_TIME = "one_time"
    USAGE = "usage"
    UNKNOWN = "unknown"


class IssueStage(str, Enum):
    INPUT = "input"
    DISCOVERY = "discovery"
    FETCH = "fetch"
    STORE = "store"
    NORMALIZE = "normalize"
    EXTRACT = "extract"
    VERIFY = "verify"
    WRITE = "write"


class IssueStatus(str, Enum):
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class OfficialPricingInput(FrozenModel):
    competitor: str = Field(min_length=1)
    official_domain: str
    pricing_url: str | None = None
    locale: str = "und"
    as_of: datetime | None = None
    output_path: str | None = None

    @field_validator("competitor", "locale")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("official_domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @field_validator("pricing_url")
    @classmethod
    def validate_pricing_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("pricing_url must be an absolute HTTP(S) URL")
        return value


class SourceDocument(FrozenModel):
    source_document_id: str = Field(min_length=64)
    requested_url: str
    final_url: str
    canonical_url: str | None = None
    official_domain: str
    authority: Literal["official"] = "official"
    retrieved_at: datetime
    http_status: int | None = None
    media_type: str | None = None
    locale: str = "und"
    fetch_status: FetchStatus
    raw_artifact_path: str | None = None
    raw_sha256: str | None = None
    normalized_text_path: str | None = None
    normalized_text_sha256: str | None = None
    parser_version: str | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def successful_snapshot_is_complete(self) -> "SourceDocument":
        if self.fetch_status == FetchStatus.SUCCESS:
            required = (
                self.raw_artifact_path,
                self.raw_sha256,
                self.normalized_text_path,
                self.normalized_text_sha256,
                self.parser_version,
            )
            if any(value is None or value == "" for value in required):
                raise ValueError("successful SourceDocument requires durable raw and normalized artifacts")
            if self.raw_sha256 != self.source_document_id:
                raise ValueError("source_document_id must equal raw_sha256")
        return self


class Evidence(FrozenModel):
    evidence_id: str
    source_document_id: str
    exact_quote: str = Field(min_length=1)
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    quote_sha256: str
    locator: str | None = None
    extraction_method: str = Field(min_length=1)

    @model_validator(mode="after")
    def span_is_ordered(self) -> "Evidence":
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be greater than span_start")
        return self


class PricingClaim(FrozenModel):
    claim_id: str
    competitor: str = Field(min_length=1)
    plan_name: str = Field(min_length=1)
    price_kind: PriceKind
    amount: str | None = None
    currency: str | None = None
    billing_period: BillingPeriod = BillingPeriod.UNKNOWN
    billing_qualifier: str | None = None
    display_price: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)

    @field_validator("amount")
    @classmethod
    def normalize_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            decimal = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal string") from exc
        if decimal < 0:
            raise ValueError("amount must not be negative")
        return format(decimal.normalize(), "f")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper().strip()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be an ISO 4217-style code")
        return normalized

    @model_validator(mode="after")
    def validate_price_shape(self) -> "PricingClaim":
        if self.price_kind == PriceKind.FIXED:
            if self.amount is None or self.currency is None:
                raise ValueError("fixed price requires amount and explicit currency")
        elif self.amount is not None or self.currency is not None:
            raise ValueError("free/contact_sales prices must not carry amount or currency")
        return self


class VerificationCheck(FrozenModel):
    name: str
    passed: bool
    code: str


class VerifiedClaim(FrozenModel):
    verified_claim_id: str
    claim: PricingClaim
    verification_status: Literal["verified"] = "verified"
    verification_checks: list[VerificationCheck]
    verified_at: datetime
    verifier_version: str

    @model_validator(mode="after")
    def all_checks_pass(self) -> "VerifiedClaim":
        if not self.verification_checks or not all(check.passed for check in self.verification_checks):
            raise ValueError("VerifiedClaim requires all verification checks to pass")
        return self


class Issue(FrozenModel):
    issue_id: str
    stage: IssueStage
    status: IssueStatus
    code: str
    message: str
    source_document_id: str | None = None
    claim_id: str | None = None


class RunManifest(FrozenModel):
    run_id: str
    input: OfficialPricingInput
    started_at: datetime
    completed_at: datetime
    component_versions: dict[str, str]
    config: dict[str, Any] = Field(default_factory=dict)


class PricingEvidenceResult(FrozenModel):
    schema_version: Literal["pricing-evidence.v1"] = "pricing-evidence.v1"
    run_manifest: RunManifest
    source_documents: list[SourceDocument] = Field(default_factory=list)
    candidate_claims: list[PricingClaim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    verified_claims: list[VerifiedClaim] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
