from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from quant_platform_kit.strategy_contracts import StrategyEntrypoint, StrategyRuntimeAdapter

from runtime_config_support import PlatformRuntimeSettings
from strategy_loader import (
    load_strategy_entrypoint_for_profile,
    load_strategy_runtime_adapter_for_profile,
)


@dataclass(frozen=True)
class LoadedStrategyRuntime:
    entrypoint: StrategyEntrypoint
    runtime_settings: PlatformRuntimeSettings
    runtime_adapter: StrategyRuntimeAdapter

    @property
    def profile(self) -> str:
        return self.entrypoint.manifest.profile

    @property
    def required_inputs(self) -> frozenset[str]:
        return frozenset(self.entrypoint.manifest.required_inputs)

    def describe(self) -> Mapping[str, Any]:
        return {
            "strategy_profile": self.profile,
            "strategy_domain": self.entrypoint.manifest.domain,
            "strategy_target_mode": self.entrypoint.manifest.target_mode,
            "required_inputs": sorted(self.required_inputs),
            "available_inputs": sorted(self.runtime_adapter.available_inputs or ()),
            "available_capabilities": sorted(self.runtime_adapter.available_capabilities or ()),
            "paper_account_group": self.runtime_settings.paper_account_group,
            "service_name": self.runtime_settings.service_name,
            "mode": "paper_only",
        }


def load_strategy_runtime(settings: PlatformRuntimeSettings) -> LoadedStrategyRuntime:
    entrypoint = load_strategy_entrypoint_for_profile(settings.strategy_profile)
    runtime_adapter = load_strategy_runtime_adapter_for_profile(settings.strategy_profile)
    return LoadedStrategyRuntime(
        entrypoint=entrypoint,
        runtime_settings=settings,
        runtime_adapter=runtime_adapter,
    )
