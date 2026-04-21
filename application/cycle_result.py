from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SignalCycleResult:
    status: str
    platform_id: str
    strategy_profile: str
    paper_account_group: str
    summary: Mapping[str, Any] = field(default_factory=dict)
