"""Context-local inputs and variant overrides for deterministic eval reruns."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any


_tool_results: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "observability_replay_tool_results", default={}
)
_model_overrides: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "observability_model_overrides", default={}
)
_parameter_overrides: contextvars.ContextVar[dict[str, dict[str, Any]]] = contextvars.ContextVar(
    "observability_parameter_overrides", default={}
)
_prompt_overrides: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "observability_prompt_overrides", default={}
)
_freeze_tools: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "observability_freeze_tools", default=False
)


class FrozenToolResultMissing(RuntimeError):
    """Raised instead of accessing the network when a frozen catalog is incomplete."""


@dataclass(frozen=True)
class ReplayTokens:
    tool_results: contextvars.Token
    model_overrides: contextvars.Token
    parameter_overrides: contextvars.Token
    prompt_overrides: contextvars.Token
    freeze_tools: contextvars.Token


def set_replay_context(
    *,
    tool_results: dict[str, Any] | None = None,
    model_overrides: dict[str, str] | None = None,
    parameter_overrides: dict[str, dict[str, Any]] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    freeze_tools: bool = False,
) -> ReplayTokens:
    return ReplayTokens(
        tool_results=_tool_results.set(tool_results or {}),
        model_overrides=_model_overrides.set(model_overrides or {}),
        parameter_overrides=_parameter_overrides.set(parameter_overrides or {}),
        prompt_overrides=_prompt_overrides.set(prompt_overrides or {}),
        freeze_tools=_freeze_tools.set(freeze_tools),
    )


def reset_replay_context(tokens: ReplayTokens) -> None:
    _tool_results.reset(tokens.tool_results)
    _model_overrides.reset(tokens.model_overrides)
    _parameter_overrides.reset(tokens.parameter_overrides)
    _prompt_overrides.reset(tokens.prompt_overrides)
    _freeze_tools.reset(tokens.freeze_tools)


def replayed_tool_result(tool: str, input_hash: str) -> tuple[bool, Any]:
    key = f"{tool}:{input_hash}"
    catalog = _tool_results.get()
    if key in catalog:
        return True, catalog[key]
    if _freeze_tools.get():
        raise FrozenToolResultMissing(f"No frozen result for {key}")
    return False, None


def model_for_role(role: str, default: str) -> str:
    return _model_overrides.get().get(role, default)


def parameters_for_role(role: str) -> dict[str, Any]:
    return dict(_parameter_overrides.get().get(role, {}))


def prompt_for_role(role: str) -> str | None:
    return _prompt_overrides.get().get(role)
