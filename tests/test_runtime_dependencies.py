from __future__ import annotations

from dataclasses import dataclass, field

from application.reconciliation_service import GcsJsonArtifactWriter, ReconciliationRecord
from application.runtime_dependencies import build_runtime_dependencies
from application.state_store_service import FirestorePaperStateStore, PaperAccountState
from runtime_config_support import PlatformRuntimeSettings


@dataclass
class FakeFirestoreDocumentSnapshot:
    payload: dict | None

    @property
    def exists(self) -> bool:
        return self.payload is not None

    def to_dict(self):
        return self.payload


@dataclass
class FakeFirestoreDocumentRef:
    store: dict[str, dict]
    collection_name: str
    document_id: str

    def get(self):
        return FakeFirestoreDocumentSnapshot(
            self.store.get(self.collection_name, {}).get(self.document_id)
        )

    def set(self, payload):
        self.store.setdefault(self.collection_name, {})[self.document_id] = dict(payload)


@dataclass
class FakeFirestoreCollectionRef:
    store: dict[str, dict]
    collection_name: str

    def document(self, document_id: str):
        return FakeFirestoreDocumentRef(self.store, self.collection_name, document_id)


@dataclass
class FakeFirestoreClient:
    store: dict[str, dict] = field(default_factory=dict)

    def collection(self, collection_name: str):
        return FakeFirestoreCollectionRef(self.store, collection_name)


@dataclass
class FakeBlob:
    objects: dict[str, dict]
    name: str

    def upload_from_string(self, payload: str, content_type: str):
        self.objects[self.name] = {"payload": payload, "content_type": content_type}


@dataclass
class FakeBucket:
    objects: dict[str, dict]

    def blob(self, name: str):
        return FakeBlob(self.objects, name)


@dataclass
class FakeStorageClient:
    buckets: dict[str, dict[str, dict]] = field(default_factory=dict)

    def bucket(self, bucket_name: str):
        objects = self.buckets.setdefault(bucket_name, {})
        return FakeBucket(objects)


def test_firestore_paper_state_store_round_trip():
    store = FirestorePaperStateStore(
        client=FakeFirestoreClient(),
        collection_name="paper_signal_states",
    )
    state = PaperAccountState(
        paper_account_group="sg_coin_notify",
        cash=10123.45,
        nav=12000.0,
        positions={"SOXL": {"quantity": 10.0, "average_cost": 22.5}},
        metadata={"last_run_as_of": "2026-04-22"},
    )

    store.save(state)
    loaded = store.load("sg_coin_notify")

    assert loaded is not None
    assert loaded.paper_account_group == "sg_coin_notify"
    assert loaded.cash == 10123.45
    assert loaded.positions["SOXL"]["quantity"] == 10.0
    assert loaded.metadata["last_run_as_of"] == "2026-04-22"


def test_gcs_json_artifact_writer_writes_record():
    client = FakeStorageClient()
    writer = GcsJsonArtifactWriter(
        client=client,
        bucket_name="quant-strategy-artifacts",
        prefix="paper-signal/sg/coin",
    )

    writer.write_record(
        ReconciliationRecord(
            strategy_profile="soxl_soxx_trend_income",
            paper_account_group="sg_coin_notify",
            payload={"as_of": "2026-04-22", "nav": 100000.0},
        )
    )

    objects = client.buckets["quant-strategy-artifacts"]
    assert (
        "paper-signal/sg/coin/2026-04-22/soxl_soxx_trend_income__sg_coin_notify.json"
        in objects
    )
    assert (
        objects[
            "paper-signal/sg/coin/2026-04-22/soxl_soxx_trend_income__sg_coin_notify.json"
        ]["content_type"]
        == "application/json"
    )


def test_build_runtime_dependencies_supports_firestore_and_gcs():
    firestore_client = FakeFirestoreClient()
    storage_client = FakeStorageClient()
    settings = _make_settings(
        state_store_backend="firestore",
        artifact_store_backend="gcs",
        gcs_bucket="quant-strategy-artifacts",
        artifact_bucket_prefix="paper-signal/sg/coin",
    )

    deps = build_runtime_dependencies(
        settings,
        firestore_client_factory=lambda **kwargs: firestore_client,
        storage_client_factory=lambda **kwargs: storage_client,
    )

    deps.state_store.save(
        PaperAccountState(
            paper_account_group="sg_coin_notify",
            cash=1.0,
            nav=2.0,
        )
    )
    loaded = deps.state_store.load("sg_coin_notify")
    assert loaded is not None
    assert loaded.nav == 2.0
    deps.artifact_writer.write_record(
        ReconciliationRecord(
            strategy_profile="global_etf_rotation",
            paper_account_group="sg_coin_notify",
            payload={"as_of": "2026-04-22"},
        )
    )
    assert (
        "paper-signal/sg/coin/2026-04-22/global_etf_rotation__sg_coin_notify.json"
        in storage_client.buckets["quant-strategy-artifacts"]
    )


def test_build_runtime_dependencies_rejects_gcs_without_bucket():
    settings = _make_settings(artifact_store_backend="gcs", gcs_bucket=None)

    try:
        build_runtime_dependencies(settings)
    except ValueError as exc:
        assert "PAPER_SIGNAL_GCS_BUCKET" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing PAPER_SIGNAL_GCS_BUCKET")


def _make_settings(**overrides) -> PlatformRuntimeSettings:
    payload = {
        "project_id": "quant-strategy-lab",
        "strategy_profile": "global_etf_rotation",
        "strategy_display_name": "Global ETF Rotation",
        "strategy_domain": "us_equity",
        "strategy_target_mode": "weight",
        "strategy_artifact_root": None,
        "strategy_artifact_dir": None,
        "feature_snapshot_path": None,
        "feature_snapshot_manifest_path": None,
        "strategy_config_path": None,
        "strategy_config_source": None,
        "reconciliation_output_path": None,
        "paper_account_group": "sg_coin_notify",
        "service_name": "paper-signal-coin-sg",
        "account_alias": "sg-paper-coin",
        "base_currency": "USD",
        "market_calendar": "XNYS",
        "starting_equity": 100000.0,
        "slippage_bps": 15.0,
        "commission_bps": 0.0,
        "fill_model": "next_open",
        "artifact_bucket_prefix": None,
        "gcs_bucket": None,
        "firestore_collection": "paper_signal_states",
        "state_store_backend": "memory",
        "artifact_store_backend": "local_json",
        "state_dir": "/tmp/paper-signal-state",
        "artifact_dir": "/tmp/paper-signal-artifacts",
        "market_data_provider": "fake",
        "history_lookback_days": 420,
        "tg_token": None,
        "tg_chat_id": None,
        "notify_lang": "en",
    }
    payload.update(overrides)
    return PlatformRuntimeSettings(**payload)
