from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    body: str
    channel: str = "telegram"
    metadata: dict[str, object] = field(default_factory=dict)


class NotificationPort(Protocol):
    def publish(self, message: NotificationMessage) -> None:
        """Deliver a runtime notification."""


@dataclass(frozen=True)
class NullNotificationPort(NotificationPort):
    def publish(self, message: NotificationMessage) -> None:
        return None
