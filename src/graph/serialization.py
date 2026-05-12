"""Small helpers for storing Pydantic models as checkpoint-safe dicts."""

from __future__ import annotations

from pydantic import BaseModel

from src.schemas.domain import ComparisonResult, CompetitorProfile, EvidenceItem, RawSource, Report


def dump_model(model: BaseModel | dict | None) -> dict | None:
    if model is None:
        return None
    if isinstance(model, dict):
        return model
    return model.model_dump(mode="json")


def dump_models(models: list[BaseModel | dict]) -> list[dict]:
    return [dump_model(model) or {} for model in models]


def raw_source(value: RawSource | dict) -> RawSource:
    return value if isinstance(value, RawSource) else RawSource.model_validate(value)


def raw_sources(values: list[RawSource | dict]) -> list[RawSource]:
    return [raw_source(value) for value in values]


def competitor_profile(value: CompetitorProfile | dict) -> CompetitorProfile:
    return (
        value
        if isinstance(value, CompetitorProfile)
        else CompetitorProfile.model_validate(value)
    )


def competitor_profiles(values: list[CompetitorProfile | dict]) -> list[CompetitorProfile]:
    return [competitor_profile(value) for value in values]


def evidence_item(value: EvidenceItem | dict) -> EvidenceItem:
    return value if isinstance(value, EvidenceItem) else EvidenceItem.model_validate(value)


def evidence_items(values: list[EvidenceItem | dict]) -> list[EvidenceItem]:
    return [evidence_item(value) for value in values]


def comparison_result(value: ComparisonResult | dict | None) -> ComparisonResult | None:
    if value is None:
        return None
    return value if isinstance(value, ComparisonResult) else ComparisonResult.model_validate(value)


def report(value: Report | dict | None) -> Report | None:
    if value is None:
        return None
    return value if isinstance(value, Report) else Report.model_validate(value)
