import pytest
from pydantic import ValidationError

from src.v2.domain.identifiers import normalize_official_domain, url_has_official_authority
from src.v2.domain.models import BillingPeriod, PriceKind, PricingClaim


def test_official_domain_normalization_and_boundary_matching():
    assert normalize_official_domain("HTTPS://GitHub.COM.:443/path") == "github.com"
    assert url_has_official_authority("https://docs.github.com/pricing", "github.com")
    assert not url_has_official_authority("https://github.com.attacker.example/pricing", "github.com")


def test_fixed_price_requires_explicit_currency_and_normalizes_decimal():
    claim = PricingClaim(
        claim_id="claim-1",
        competitor="Example",
        plan_name="Pro",
        price_kind=PriceKind.FIXED,
        amount="010.00",
        currency="usd",
        billing_period=BillingPeriod.MONTH,
        display_price="$10 USD/month",
        evidence_id="evidence-1",
    )
    assert claim.amount == "10"
    assert claim.currency == "USD"

    with pytest.raises(ValidationError):
        PricingClaim(
            claim_id="claim-2",
            competitor="Example",
            plan_name="Pro",
            price_kind=PriceKind.FIXED,
            amount="10",
            currency=None,
            display_price="$10/month",
            evidence_id="evidence-1",
        )


def test_free_price_must_not_carry_amount():
    with pytest.raises(ValidationError):
        PricingClaim(
            claim_id="claim-3",
            competitor="Example",
            plan_name="Free",
            price_kind=PriceKind.FREE,
            amount="0",
            currency="USD",
            display_price="$0 USD",
            evidence_id="evidence-1",
        )
