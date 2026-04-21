from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ReconciliationRecord:
    strategy_profile: str
    paper_account_group: str
    payload: Mapping[str, Any]
    artifacts: Mapping[str, Any] = field(default_factory=dict)


class ArtifactWriter(Protocol):
    def write_record(self, record: ReconciliationRecord) -> None:
        """Persist one reconciliation record."""


@dataclass(frozen=True)
class LocalJsonArtifactWriter(ArtifactWriter):
    root_dir: str

    def write_record(self, record: ReconciliationRecord) -> None:
        payload = {
            "strategy_profile": record.strategy_profile,
            "paper_account_group": record.paper_account_group,
            "payload": dict(record.payload),
            "artifacts": dict(record.artifacts),
        }
        as_of = str(record.payload.get("as_of") or "unknown-date")
        output_dir = Path(self.root_dir) / as_of
        output_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{record.strategy_profile}__{record.paper_account_group}.json"
        (output_dir / file_name).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
