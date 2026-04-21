from __future__ import annotations

from dataclasses import dataclass

from application.notification_service import NotificationPort, NullNotificationPort
from application.reconciliation_service import ArtifactWriter, LocalJsonArtifactWriter
from application.state_store_service import (
    InMemoryPaperStateStore,
    LocalJsonPaperStateStore,
    PaperStateStore,
)
from notifications.telegram import TelegramNotificationPort
from runtime_config_support import PlatformRuntimeSettings


@dataclass(frozen=True)
class PaperSignalRuntimeDependencies:
    state_store: PaperStateStore
    notification_port: NotificationPort
    artifact_writer: ArtifactWriter


def build_runtime_dependencies(
    settings: PlatformRuntimeSettings,
) -> PaperSignalRuntimeDependencies:
    if settings.state_store_backend == "memory":
        state_store: PaperStateStore = InMemoryPaperStateStore()
    elif settings.state_store_backend == "local_json":
        state_store = LocalJsonPaperStateStore(settings.state_dir)
    else:
        raise ValueError(f"Unsupported PAPER_SIGNAL_STATE_STORE_BACKEND={settings.state_store_backend!r}")

    if settings.artifact_store_backend == "local_json":
        artifact_writer: ArtifactWriter = LocalJsonArtifactWriter(settings.artifact_dir)
    else:
        raise ValueError(
            f"Unsupported PAPER_SIGNAL_ARTIFACT_STORE_BACKEND={settings.artifact_store_backend!r}"
        )

    if settings.tg_token and settings.tg_chat_id:
        notification_port: NotificationPort = TelegramNotificationPort(
            token=settings.tg_token,
            chat_id=settings.tg_chat_id,
        )
    else:
        notification_port = NullNotificationPort()

    return PaperSignalRuntimeDependencies(
        state_store=state_store,
        notification_port=notification_port,
        artifact_writer=artifact_writer,
    )
