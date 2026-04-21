from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from application.notification_service import NotificationPort, NullNotificationPort
from application.reconciliation_service import (
    ArtifactWriter,
    GcsJsonArtifactWriter,
    LocalJsonArtifactWriter,
)
from application.state_store_service import (
    FirestorePaperStateStore,
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
    *,
    firestore_client_factory: Callable[..., Any] | None = None,
    storage_client_factory: Callable[..., Any] | None = None,
) -> PaperSignalRuntimeDependencies:
    if settings.state_store_backend == "memory":
        state_store: PaperStateStore = InMemoryPaperStateStore()
    elif settings.state_store_backend == "local_json":
        state_store = LocalJsonPaperStateStore(settings.state_dir)
    elif settings.state_store_backend == "firestore":
        state_store = FirestorePaperStateStore(
            client=_build_firestore_client(
                project_id=settings.project_id,
                client_factory=firestore_client_factory,
            ),
            collection_name=settings.firestore_collection,
        )
    else:
        raise ValueError(f"Unsupported PAPER_SIGNAL_STATE_STORE_BACKEND={settings.state_store_backend!r}")

    if settings.artifact_store_backend == "local_json":
        artifact_writer: ArtifactWriter = LocalJsonArtifactWriter(settings.artifact_dir)
    elif settings.artifact_store_backend == "gcs":
        if not settings.gcs_bucket:
            raise ValueError("PAPER_SIGNAL_GCS_BUCKET is required when PAPER_SIGNAL_ARTIFACT_STORE_BACKEND=gcs")
        artifact_writer = GcsJsonArtifactWriter(
            client=_build_storage_client(
                project_id=settings.project_id,
                client_factory=storage_client_factory,
            ),
            bucket_name=settings.gcs_bucket,
            prefix=settings.artifact_bucket_prefix or "",
        )
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


def _build_firestore_client(
    *,
    project_id: str | None,
    client_factory: Callable[..., Any] | None,
):
    if client_factory is None:
        from google.cloud import firestore

        client_factory = firestore.Client
    if project_id:
        return client_factory(project=project_id)
    return client_factory()


def _build_storage_client(
    *,
    project_id: str | None,
    client_factory: Callable[..., Any] | None,
):
    if client_factory is None:
        from google.cloud import storage

        client_factory = storage.Client
    if project_id:
        return client_factory(project=project_id)
    return client_factory()
