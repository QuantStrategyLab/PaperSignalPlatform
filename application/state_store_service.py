from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class PaperAccountState:
    paper_account_group: str
    cash: float
    nav: float
    positions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class PaperStateStore(Protocol):
    def load(self, paper_account_group: str) -> PaperAccountState | None:
        """Load the last persisted paper account state."""

    def save(self, state: PaperAccountState) -> None:
        """Persist the latest paper account state."""


@dataclass
class InMemoryPaperStateStore(PaperStateStore):
    states: dict[str, PaperAccountState] = field(default_factory=dict)

    def load(self, paper_account_group: str) -> PaperAccountState | None:
        return self.states.get(paper_account_group)

    def save(self, state: PaperAccountState) -> None:
        self.states[state.paper_account_group] = state


@dataclass(frozen=True)
class LocalJsonPaperStateStore(PaperStateStore):
    root_dir: str

    def load(self, paper_account_group: str) -> PaperAccountState | None:
        path = self._path_for_group(paper_account_group)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PaperAccountState(
            paper_account_group=str(payload["paper_account_group"]),
            cash=float(payload["cash"]),
            nav=float(payload["nav"]),
            positions=dict(payload.get("positions") or {}),
            metadata=dict(payload.get("metadata") or {}),
        )

    def save(self, state: PaperAccountState) -> None:
        path = self._path_for_group(state.paper_account_group)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "paper_account_group": state.paper_account_group,
            "cash": float(state.cash),
            "nav": float(state.nav),
            "positions": dict(state.positions),
            "metadata": dict(state.metadata),
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    def _path_for_group(self, paper_account_group: str) -> Path:
        return Path(self.root_dir) / f"{paper_account_group}.json"
