from __future__ import annotations

from dataclasses import dataclass

import requests

from application.notification_service import NotificationMessage, NotificationPort


@dataclass(frozen=True)
class TelegramNotificationPort(NotificationPort):
    token: str
    chat_id: str
    timeout_sec: float = 10.0

    def publish(self, message: NotificationMessage) -> None:
        text = f"{message.title}\n\n{message.body}".strip()
        requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=self.timeout_sec,
        ).raise_for_status()
