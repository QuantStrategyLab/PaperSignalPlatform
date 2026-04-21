from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from us_equity_strategies.catalog import resolve_canonical_profile

from quant_platform_kit.strategy_contracts import (
    StrategyDecision,
    build_allocation_intent,
    build_allocation_payload,
)


def _resolve_allocation_order(strategy_profile: str) -> str:
    canonical_profile = resolve_canonical_profile(strategy_profile)
    if canonical_profile == "soxl_soxx_trend_income":
        return "risk_income_safe"
    return "risk_safe_income"


def map_strategy_decision(
    decision: StrategyDecision,
    *,
    strategy_profile: str,
    runtime_metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    runtime_metadata = dict(runtime_metadata or {})
    canonical_profile = resolve_canonical_profile(strategy_profile)
    diagnostics = dict(decision.diagnostics)
    actionable = bool(diagnostics.get("actionable", True))
    allocation_payload = None
    if actionable and decision.positions:
        allocation_payload = build_allocation_payload(
            build_allocation_intent(
                decision,
                strategy_profile=canonical_profile,
                strategy_symbols_order=_resolve_allocation_order(canonical_profile),
            )
        )
    metadata: dict[str, Any] = {**runtime_metadata, **diagnostics}
    metadata.setdefault("strategy_profile", canonical_profile)
    metadata.setdefault("risk_flags", tuple(str(flag) for flag in decision.risk_flags))
    metadata.setdefault("actionable", actionable)
    if allocation_payload is not None:
        metadata["allocation"] = allocation_payload
    return allocation_payload, metadata
