from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

import pandas as pd

from application.market_data_service import DailyBarProvider
from application.notification_service import NotificationMessage, NullNotificationPort
from application.reconciliation_service import ArtifactWriter, ReconciliationRecord
from application.runtime_dependencies import PaperSignalRuntimeDependencies
from application.signal_cycle import run_paper_signal_cycle
from application.state_store_service import InMemoryPaperStateStore
from runtime_config_support import PlatformRuntimeSettings
from strategy_runtime import load_strategy_runtime


@dataclass(frozen=True)
class RecordingArtifactWriter(ArtifactWriter):
    records: list[ReconciliationRecord] = field(default_factory=list)

    def write_record(self, record: ReconciliationRecord) -> None:
        self.records.append(record)


@dataclass(frozen=True)
class RecordingNotificationPort(NullNotificationPort):
    messages: list[NotificationMessage] = field(default_factory=list)

    def publish(self, message: NotificationMessage) -> None:
        self.messages.append(message)


@dataclass(frozen=True)
class FakeDailyBarProvider(DailyBarProvider):
    bars_by_symbol: dict[str, pd.DataFrame]

    def fetch_daily_bars(
        self,
        symbols: tuple[str, ...],
        *,
        as_of_date: pd.Timestamp,
        lookback_days: int,
    ) -> dict[str, pd.DataFrame]:
        cutoff = pd.Timestamp(as_of_date).normalize()
        return {
            symbol: self.bars_by_symbol[symbol].loc[self.bars_by_symbol[symbol].index <= cutoff].copy()
            for symbol in symbols
        }


def test_global_etf_rotation_cycle_queues_then_executes_pending_plan():
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="global_etf_rotation",
        strategy_display_name="Global ETF Rotation",
        strategy_domain="us_equity",
        strategy_target_mode="weight",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=None,
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_coin_notify",
        service_name="paper-signal-coin-sg",
        account_alias="sg-paper-coin",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_global_rotation_bars(end_date="2026-04-01"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-03-31",
    )

    assert first.status == "ok"
    assert first.summary["queue_status"] == "queued_pending_plan"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-01"
    assert set(pending["targets"]) == {"VOO", "XLK"}

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-01",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "no_actionable_allocation"
    assert {row["symbol"] for row in second.summary["positions"]} == {"VOO", "XLK"}
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"] is None
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_tqqq_growth_income_cycle_executes_and_requeues_next_day_plan():
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="tqqq_growth_income",
        strategy_display_name="TQQQ Growth Income",
        strategy_domain="us_equity",
        strategy_target_mode="value",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=None,
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_tqqq_notify",
        service_name="paper-signal-tqqq-sg",
        account_alias="sg-paper-tqqq",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_tqqq_growth_bars(end_date="2026-04-08"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-07",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-08"
    assert set(pending["targets"]) == {"TQQQ", "QQQ", "BOXX", "SPYI", "QQQI"}

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-08",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {row["symbol"] for row in second.summary["positions"]} == {"BOXX", "QQQ", "TQQQ"}
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-09"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_soxl_soxx_trend_income_cycle_executes_and_requeues_next_day_plan():
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="soxl_soxx_trend_income",
        strategy_display_name="SOXL/SOXX Semiconductor Trend Income",
        strategy_domain="us_equity",
        strategy_target_mode="value",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=None,
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_soxl_notify",
        service_name="paper-signal-soxl-sg",
        account_alias="sg-paper-soxl",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_soxl_trend_income_bars(end_date="2026-04-08"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-07",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-08"
    assert set(pending["targets"]) == {"SOXL", "SOXX", "BOXX", "SPYI", "QQQI"}

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-08",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {row["symbol"] for row in second.summary["positions"]} == {"BOXX", "SOXL", "SOXX"}
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-09"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_russell_feature_snapshot_cycle_executes_and_requeues_next_day_plan(tmp_path):
    snapshot_path = tmp_path / "russell_1000_multi_factor_defensive_feature_snapshot_latest.csv"
    snapshot_path.write_text(_build_russell_feature_snapshot_csv(), encoding="utf-8")
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="russell_1000_multi_factor_defensive",
        strategy_display_name="Russell 1000 Multi-Factor",
        strategy_domain="us_equity",
        strategy_target_mode="weight",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=str(snapshot_path),
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_r1000_notify",
        service_name="paper-signal-r1000-sg",
        account_alias="sg-paper-r1000",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_russell_bars(end_date="2026-04-08"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-07",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-08"
    assert {"AAPL", "MSFT", "LLY", "JPM"}.issubset(set(pending["targets"]))

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-08",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {"AAPL", "MSFT", "LLY", "JPM"}.issubset(
        {row["symbol"] for row in second.summary["positions"]}
    )
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-09"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_tech_feature_snapshot_cycle_executes_and_requeues_next_day_plan(tmp_path):
    snapshot_path = tmp_path / "tech_communication_pullback_enhancement_feature_snapshot_latest.csv"
    snapshot_path.write_text(_build_tech_feature_snapshot_csv(), encoding="utf-8")
    config_path = _ues_config_path(
        "src/us_equity_strategies/configs/tech_communication_pullback_enhancement.json"
    )
    _write_feature_snapshot_manifest(
        snapshot_path=snapshot_path,
        strategy_profile="tech_communication_pullback_enhancement",
        contract_version="tech_communication_pullback_enhancement.feature_snapshot.v1",
        snapshot_as_of="2026-03-31",
        config_name="tech_communication_pullback_enhancement",
        config_path=config_path,
    )
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="tech_communication_pullback_enhancement",
        strategy_display_name="Tech Communication Pullback Enhancement",
        strategy_domain="us_equity",
        strategy_target_mode="weight",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=str(snapshot_path),
        feature_snapshot_manifest_path=None,
        strategy_config_path=str(config_path),
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_tech_notify",
        service_name="paper-signal-tech-sg",
        account_alias="sg-paper-tech",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_tech_bars(end_date="2026-04-03"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-01",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-02"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(set(pending["targets"]))

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-02",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(
        {row["symbol"] for row in second.summary["positions"]}
    )
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-06"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_mega_cap_top50_feature_snapshot_cycle_executes_and_requeues_next_day_plan(tmp_path):
    snapshot_path = tmp_path / "mega_cap_leader_rotation_top50_balanced_feature_snapshot_latest.csv"
    snapshot_path.write_text(_build_mega_cap_feature_snapshot_csv(), encoding="utf-8")
    _write_feature_snapshot_manifest(
        snapshot_path=snapshot_path,
        strategy_profile="mega_cap_leader_rotation_top50_balanced",
        contract_version="mega_cap_leader_rotation_top50_balanced.feature_snapshot.v1",
        snapshot_as_of="2026-03-31",
        config_name="mega_cap_leader_rotation_top50_balanced",
    )
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="mega_cap_leader_rotation_top50_balanced",
        strategy_display_name="Mega Cap Leader Rotation Top50 Balanced",
        strategy_domain="us_equity",
        strategy_target_mode="weight",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=str(snapshot_path),
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_mega_notify",
        service_name="paper-signal-mega-sg",
        account_alias="sg-paper-mega",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_mega_cap_bars(end_date="2026-04-03"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-01",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-02"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(set(pending["targets"]))

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-02",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(
        {row["symbol"] for row in second.summary["positions"]}
    )
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-06"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def test_dynamic_mega_hybrid_cycle_executes_and_requeues_next_day_plan(tmp_path):
    snapshot_path = tmp_path / "dynamic_mega_leveraged_pullback_feature_snapshot_latest.csv"
    snapshot_path.write_text(_build_dynamic_mega_feature_snapshot_csv(), encoding="utf-8")
    _write_feature_snapshot_manifest(
        snapshot_path=snapshot_path,
        strategy_profile="dynamic_mega_leveraged_pullback",
        contract_version="dynamic_mega_leveraged_pullback.feature_snapshot.v1",
        snapshot_as_of="2026-03-31",
        config_name="dynamic_mega_leveraged_pullback",
    )
    settings = PlatformRuntimeSettings(
        project_id=None,
        strategy_profile="dynamic_mega_leveraged_pullback",
        strategy_display_name="Dynamic Mega Leveraged Pullback",
        strategy_domain="us_equity",
        strategy_target_mode="weight",
        strategy_artifact_root=None,
        strategy_artifact_dir=None,
        feature_snapshot_path=str(snapshot_path),
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
        reconciliation_output_path=None,
        paper_account_group="sg_dynamic_mega_notify",
        service_name="paper-signal-dynamic-mega-sg",
        account_alias="sg-paper-dynamic-mega",
        base_currency="USD",
        market_calendar="XNYS",
        starting_equity=100000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
        fill_model="next_open",
        artifact_bucket_prefix=None,
        gcs_bucket=None,
        firestore_collection="paper_signal_states",
        state_store_backend="memory",
        artifact_store_backend="local_json",
        state_dir="/tmp/paper-signal-state",
        artifact_dir="/tmp/paper-signal-artifacts",
        market_data_provider="fake",
        history_lookback_days=420,
        tg_token=None,
        tg_chat_id=None,
        notify_lang="en",
    )
    runtime = load_strategy_runtime(settings)
    state_store = InMemoryPaperStateStore()
    artifact_writer = RecordingArtifactWriter()
    notification_port = RecordingNotificationPort()
    dependencies = PaperSignalRuntimeDependencies(
        state_store=state_store,
        artifact_writer=artifact_writer,
        notification_port=notification_port,
    )
    provider = FakeDailyBarProvider(_build_dynamic_mega_bars(end_date="2026-04-08"))

    first = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-07",
    )

    assert first.status == "ok"
    assert first.summary["execution"]["status"] == "no_pending_plan"
    assert first.summary["queue_status"] == "queued_pending_plan"
    pending = state_store.load(settings.paper_account_group).metadata["pending_plan"]
    assert pending["effective_date"] == "2026-04-08"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(set(pending["targets"]))

    second = run_paper_signal_cycle(
        settings=settings,
        runtime=runtime,
        dependencies=dependencies,
        market_data_provider=provider,
        as_of_date="2026-04-08",
    )

    assert second.status == "ok"
    assert second.summary["execution"]["status"] == "executed_pending_plan"
    assert second.summary["queue_status"] == "queued_pending_plan"
    assert {"AAPL", "MSFT", "NVDA"}.issubset(
        {row["symbol"] for row in second.summary["positions"]}
    )
    latest_state = state_store.load(settings.paper_account_group)
    assert latest_state.metadata["pending_plan"]["effective_date"] == "2026-04-09"
    assert len(notification_port.messages) == 2
    assert len(artifact_writer.records) == 2


def _build_global_rotation_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    symbols = (
        "EWY", "EWT", "INDA", "FXI", "EWJ", "VGK", "VOO", "XLK", "SMH", "GLD", "SLV",
        "USO", "DBA", "XLE", "XLF", "ITA", "XLP", "XLU", "XLV", "IHI", "VNQ", "KRE",
        "SPY", "EFA", "EEM", "AGG", "BIL",
    )
    index = pd.bdate_range(end=pd.Timestamp(end_date), periods=320)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for offset, symbol in enumerate(symbols):
        slope = 0.05
        if symbol == "VOO":
            slope = 0.25
        elif symbol == "XLK":
            slope = 0.20
        elif symbol in {"SPY", "EFA", "EEM", "AGG"}:
            slope = 0.10
        base = 90.0 + offset
        close = pd.Series(
            [base + slope * step for step in range(len(index))],
            index=index,
            dtype=float,
        )
        open_ = close * 0.995
        bars_by_symbol[symbol] = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.01,
                "low": open_ * 0.99,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
    return bars_by_symbol


def _build_tqqq_growth_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    symbols = ("QQQ", "TQQQ", "BOXX", "SPYI", "QQQI")
    index = pd.bdate_range(end=pd.Timestamp(end_date), periods=320)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    slopes = {
        "QQQ": 0.40,
        "TQQQ": 1.20,
        "BOXX": 0.01,
        "SPYI": 0.03,
        "QQQI": 0.04,
    }
    bases = {
        "QQQ": 300.0,
        "TQQQ": 70.0,
        "BOXX": 100.0,
        "SPYI": 49.0,
        "QQQI": 51.0,
    }
    for symbol in symbols:
        close = pd.Series(
            [bases[symbol] + slopes[symbol] * step for step in range(len(index))],
            index=index,
            dtype=float,
        )
        open_ = close * 0.995
        bars_by_symbol[symbol] = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.01,
                "low": open_ * 0.99,
                "close": close,
                "volume": 2_000_000.0,
            }
        )
    return bars_by_symbol


def _build_soxl_trend_income_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    symbols = ("SOXL", "SOXX", "BOXX", "SPYI", "QQQI")
    index = pd.bdate_range(end=pd.Timestamp(end_date), periods=220)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    slopes = {
        "SOXL": 0.55,
        "SOXX": 0.80,
        "BOXX": 0.01,
        "SPYI": 0.03,
        "QQQI": 0.04,
    }
    bases = {
        "SOXL": 40.0,
        "SOXX": 180.0,
        "BOXX": 100.0,
        "SPYI": 49.0,
        "QQQI": 51.0,
    }
    for symbol in symbols:
        close = pd.Series(
            [bases[symbol] + slopes[symbol] * step for step in range(len(index))],
            index=index,
            dtype=float,
        )
        open_ = close * 0.995
        bars_by_symbol[symbol] = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.01,
                "low": open_ * 0.99,
                "close": close,
                "volume": 2_500_000.0,
            }
        )
    return bars_by_symbol


def _build_russell_feature_snapshot_csv() -> str:
    rows = [
        {
            "symbol": "SPY",
            "as_of": "2026-03-31",
            "sector": "Index",
            "mom_6_1": 0.10,
            "mom_12_1": 0.15,
            "sma200_gap": 0.08,
            "vol_63": 0.12,
            "maxdd_126": -0.10,
            "eligible": True,
        },
        {
            "symbol": "AAPL",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "mom_6_1": 0.42,
            "mom_12_1": 0.51,
            "sma200_gap": 0.18,
            "vol_63": 0.21,
            "maxdd_126": -0.14,
            "eligible": True,
        },
        {
            "symbol": "MSFT",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "mom_6_1": 0.38,
            "mom_12_1": 0.45,
            "sma200_gap": 0.17,
            "vol_63": 0.19,
            "maxdd_126": -0.12,
            "eligible": True,
        },
        {
            "symbol": "LLY",
            "as_of": "2026-03-31",
            "sector": "Health Care",
            "mom_6_1": 0.35,
            "mom_12_1": 0.41,
            "sma200_gap": 0.16,
            "vol_63": 0.18,
            "maxdd_126": -0.13,
            "eligible": True,
        },
        {
            "symbol": "JPM",
            "as_of": "2026-03-31",
            "sector": "Financials",
            "mom_6_1": 0.31,
            "mom_12_1": 0.37,
            "sma200_gap": 0.14,
            "vol_63": 0.20,
            "maxdd_126": -0.15,
            "eligible": True,
        },
    ]
    frame = pd.DataFrame(rows)
    return frame.to_csv(index=False)


def _build_russell_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    symbols = ("SPY", "BOXX", "AAPL", "MSFT", "LLY", "JPM")
    index = pd.bdate_range(end=pd.Timestamp(end_date), periods=220)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    slopes = {
        "SPY": 0.25,
        "BOXX": 0.01,
        "AAPL": 0.60,
        "MSFT": 0.55,
        "LLY": 0.45,
        "JPM": 0.35,
    }
    bases = {
        "SPY": 500.0,
        "BOXX": 100.0,
        "AAPL": 190.0,
        "MSFT": 410.0,
        "LLY": 770.0,
        "JPM": 220.0,
    }
    for symbol in symbols:
        close = pd.Series(
            [bases[symbol] + slopes[symbol] * step for step in range(len(index))],
            index=index,
            dtype=float,
        )
        open_ = close * 0.995
        bars_by_symbol[symbol] = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.01,
                "low": open_ * 0.99,
                "close": close,
                "volume": 3_000_000.0,
            }
        )
    return bars_by_symbol


def _build_tech_feature_snapshot_csv() -> str:
    rows = [
        {
            "symbol": "QQQ",
            "as_of": "2026-03-31",
            "sector": "Benchmark",
            "close": 520.0,
            "adv20_usd": 9_000_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.26,
            "mom_12_1": 0.34,
            "sma20_gap": 0.05,
            "sma50_gap": 0.09,
            "sma200_gap": 0.14,
            "ma50_over_ma200": 0.07,
            "vol_63": 0.18,
            "maxdd_126": -0.09,
            "breakout_252": 0.11,
            "dist_63_high": -0.02,
            "dist_126_high": -0.04,
            "rebound_20": 0.08,
            "eligible": True,
        },
        {
            "symbol": "BOXX",
            "as_of": "2026-03-31",
            "sector": "Cash",
            "close": 100.0,
            "adv20_usd": 500_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.01,
            "mom_12_1": 0.02,
            "sma20_gap": 0.00,
            "sma50_gap": 0.00,
            "sma200_gap": 0.00,
            "ma50_over_ma200": 0.00,
            "vol_63": 0.01,
            "maxdd_126": -0.01,
            "breakout_252": 0.00,
            "dist_63_high": 0.00,
            "dist_126_high": 0.00,
            "rebound_20": 0.00,
            "eligible": True,
        },
        {
            "symbol": "AAPL",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 225.0,
            "adv20_usd": 4_500_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.42,
            "mom_12_1": 0.55,
            "sma20_gap": 0.06,
            "sma50_gap": 0.10,
            "sma200_gap": 0.18,
            "ma50_over_ma200": 0.08,
            "vol_63": 0.21,
            "maxdd_126": -0.14,
            "breakout_252": 0.12,
            "dist_63_high": -0.05,
            "dist_126_high": -0.08,
            "rebound_20": 0.12,
            "eligible": True,
        },
        {
            "symbol": "MSFT",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 445.0,
            "adv20_usd": 3_900_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.40,
            "mom_12_1": 0.50,
            "sma20_gap": 0.05,
            "sma50_gap": 0.09,
            "sma200_gap": 0.17,
            "ma50_over_ma200": 0.08,
            "vol_63": 0.18,
            "maxdd_126": -0.12,
            "breakout_252": 0.10,
            "dist_63_high": -0.04,
            "dist_126_high": -0.07,
            "rebound_20": 0.10,
            "eligible": True,
        },
        {
            "symbol": "NVDA",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 135.0,
            "adv20_usd": 5_100_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.55,
            "mom_12_1": 0.75,
            "sma20_gap": 0.08,
            "sma50_gap": 0.12,
            "sma200_gap": 0.22,
            "ma50_over_ma200": 0.10,
            "vol_63": 0.28,
            "maxdd_126": -0.18,
            "breakout_252": 0.18,
            "dist_63_high": -0.06,
            "dist_126_high": -0.09,
            "rebound_20": 0.16,
            "eligible": True,
        },
        {
            "symbol": "META",
            "as_of": "2026-03-31",
            "sector": "Communication",
            "close": 520.0,
            "adv20_usd": 2_800_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.33,
            "mom_12_1": 0.44,
            "sma20_gap": 0.04,
            "sma50_gap": 0.08,
            "sma200_gap": 0.15,
            "ma50_over_ma200": 0.07,
            "vol_63": 0.20,
            "maxdd_126": -0.15,
            "breakout_252": 0.09,
            "dist_63_high": -0.03,
            "dist_126_high": -0.06,
            "rebound_20": 0.09,
            "eligible": True,
        },
        {
            "symbol": "GOOGL",
            "as_of": "2026-03-31",
            "sector": "Communication",
            "close": 190.0,
            "adv20_usd": 1_900_000_000.0,
            "history_days": 260,
            "mom_6_1": 0.29,
            "mom_12_1": 0.38,
            "sma20_gap": 0.03,
            "sma50_gap": 0.07,
            "sma200_gap": 0.13,
            "ma50_over_ma200": 0.06,
            "vol_63": 0.17,
            "maxdd_126": -0.11,
            "breakout_252": 0.08,
            "dist_63_high": -0.03,
            "dist_126_high": -0.05,
            "rebound_20": 0.07,
            "eligible": True,
        },
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def _build_mega_cap_feature_snapshot_csv() -> str:
    rows = [
        {
            "symbol": "QQQ",
            "as_of": "2026-03-31",
            "sector": "Benchmark",
            "close": 520.0,
            "adv20_usd": 9_000_000_000.0,
            "history_days": 260,
            "mom_3m": 0.11,
            "mom_6m": 0.24,
            "mom_12_1": 0.33,
            "rel_mom_6m_vs_benchmark": 0.00,
            "rel_mom_6m_vs_broad_benchmark": 0.02,
            "high_252_gap": -0.02,
            "sma200_gap": 0.14,
            "vol_63": 0.18,
            "maxdd_126": -0.09,
            "eligible": True,
        },
        {
            "symbol": "SPY",
            "as_of": "2026-03-31",
            "sector": "Benchmark",
            "close": 610.0,
            "adv20_usd": 8_500_000_000.0,
            "history_days": 260,
            "mom_3m": 0.08,
            "mom_6m": 0.18,
            "mom_12_1": 0.25,
            "rel_mom_6m_vs_benchmark": -0.06,
            "rel_mom_6m_vs_broad_benchmark": 0.00,
            "high_252_gap": -0.03,
            "sma200_gap": 0.10,
            "vol_63": 0.15,
            "maxdd_126": -0.08,
            "eligible": True,
        },
        {
            "symbol": "BOXX",
            "as_of": "2026-03-31",
            "sector": "Cash",
            "close": 100.0,
            "adv20_usd": 500_000_000.0,
            "history_days": 260,
            "mom_3m": 0.01,
            "mom_6m": 0.01,
            "mom_12_1": 0.02,
            "rel_mom_6m_vs_benchmark": -0.23,
            "rel_mom_6m_vs_broad_benchmark": -0.17,
            "high_252_gap": 0.00,
            "sma200_gap": 0.00,
            "vol_63": 0.01,
            "maxdd_126": -0.01,
            "eligible": True,
        },
        {
            "symbol": "AAPL",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 225.0,
            "adv20_usd": 4_500_000_000.0,
            "history_days": 260,
            "mom_3m": 0.16,
            "mom_6m": 0.36,
            "mom_12_1": 0.48,
            "rel_mom_6m_vs_benchmark": 0.12,
            "rel_mom_6m_vs_broad_benchmark": 0.18,
            "high_252_gap": -0.04,
            "sma200_gap": 0.19,
            "vol_63": 0.20,
            "maxdd_126": -0.13,
            "eligible": True,
        },
        {
            "symbol": "MSFT",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 445.0,
            "adv20_usd": 3_900_000_000.0,
            "history_days": 260,
            "mom_3m": 0.14,
            "mom_6m": 0.31,
            "mom_12_1": 0.42,
            "rel_mom_6m_vs_benchmark": 0.07,
            "rel_mom_6m_vs_broad_benchmark": 0.13,
            "high_252_gap": -0.03,
            "sma200_gap": 0.18,
            "vol_63": 0.18,
            "maxdd_126": -0.11,
            "eligible": True,
        },
        {
            "symbol": "NVDA",
            "as_of": "2026-03-31",
            "sector": "Information Technology",
            "close": 135.0,
            "adv20_usd": 5_100_000_000.0,
            "history_days": 260,
            "mom_3m": 0.22,
            "mom_6m": 0.52,
            "mom_12_1": 0.78,
            "rel_mom_6m_vs_benchmark": 0.28,
            "rel_mom_6m_vs_broad_benchmark": 0.34,
            "high_252_gap": -0.06,
            "sma200_gap": 0.24,
            "vol_63": 0.29,
            "maxdd_126": -0.17,
            "eligible": True,
        },
        {
            "symbol": "META",
            "as_of": "2026-03-31",
            "sector": "Communication Services",
            "close": 520.0,
            "adv20_usd": 2_800_000_000.0,
            "history_days": 260,
            "mom_3m": 0.12,
            "mom_6m": 0.28,
            "mom_12_1": 0.39,
            "rel_mom_6m_vs_benchmark": 0.04,
            "rel_mom_6m_vs_broad_benchmark": 0.10,
            "high_252_gap": -0.03,
            "sma200_gap": 0.16,
            "vol_63": 0.19,
            "maxdd_126": -0.12,
            "eligible": True,
        },
        {
            "symbol": "AMZN",
            "as_of": "2026-03-31",
            "sector": "Consumer Discretionary",
            "close": 230.0,
            "adv20_usd": 2_300_000_000.0,
            "history_days": 260,
            "mom_3m": 0.10,
            "mom_6m": 0.24,
            "mom_12_1": 0.35,
            "rel_mom_6m_vs_benchmark": 0.00,
            "rel_mom_6m_vs_broad_benchmark": 0.06,
            "high_252_gap": -0.03,
            "sma200_gap": 0.15,
            "vol_63": 0.17,
            "maxdd_126": -0.12,
            "eligible": True,
        },
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def _build_dynamic_mega_feature_snapshot_csv() -> str:
    rows = [
        {
            "symbol": "AAPL",
            "underlying_symbol": "AAPL",
            "sector": "Information Technology",
            "candidate_rank": 1,
            "product_leverage": 2.0,
            "product_available": True,
            "eligible": True,
            "as_of": "2026-03-31",
        },
        {
            "symbol": "MSFT",
            "underlying_symbol": "MSFT",
            "sector": "Information Technology",
            "candidate_rank": 2,
            "product_leverage": 2.0,
            "product_available": True,
            "eligible": True,
            "as_of": "2026-03-31",
        },
        {
            "symbol": "NVDA",
            "underlying_symbol": "NVDA",
            "sector": "Information Technology",
            "candidate_rank": 3,
            "product_leverage": 2.0,
            "product_available": True,
            "eligible": True,
            "as_of": "2026-03-31",
        },
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def _build_tech_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    return _build_linear_bars(
        end_date=end_date,
        periods=320,
        bases={
            "QQQ": 300.0,
            "BOXX": 100.0,
            "AAPL": 160.0,
            "MSFT": 300.0,
            "NVDA": 80.0,
            "META": 360.0,
            "GOOGL": 130.0,
        },
        slopes={
            "QQQ": 0.70,
            "BOXX": 0.01,
            "AAPL": 0.45,
            "MSFT": 0.55,
            "NVDA": 0.65,
            "META": 0.42,
            "GOOGL": 0.25,
        },
        volumes={
            "QQQ": 8_000_000.0,
            "BOXX": 600_000.0,
            "AAPL": 6_500_000.0,
            "MSFT": 5_900_000.0,
            "NVDA": 7_500_000.0,
            "META": 4_800_000.0,
            "GOOGL": 4_200_000.0,
        },
    )


def _build_mega_cap_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    return _build_linear_bars(
        end_date=end_date,
        periods=320,
        bases={
            "QQQ": 300.0,
            "SPY": 450.0,
            "BOXX": 100.0,
            "AAPL": 160.0,
            "MSFT": 300.0,
            "NVDA": 80.0,
            "META": 360.0,
            "AMZN": 150.0,
        },
        slopes={
            "QQQ": 0.70,
            "SPY": 0.50,
            "BOXX": 0.01,
            "AAPL": 0.45,
            "MSFT": 0.55,
            "NVDA": 0.65,
            "META": 0.42,
            "AMZN": 0.33,
        },
        volumes={
            "QQQ": 8_000_000.0,
            "SPY": 8_500_000.0,
            "BOXX": 600_000.0,
            "AAPL": 6_500_000.0,
            "MSFT": 5_900_000.0,
            "NVDA": 7_500_000.0,
            "META": 4_800_000.0,
            "AMZN": 4_600_000.0,
        },
    )


def _build_dynamic_mega_bars(*, end_date: str) -> dict[str, pd.DataFrame]:
    return _build_linear_bars(
        end_date=end_date,
        periods=320,
        bases={
            "QQQ": 300.0,
            "BOXX": 100.0,
            "AAPL": 160.0,
            "MSFT": 300.0,
            "NVDA": 80.0,
        },
        slopes={
            "QQQ": 0.72,
            "BOXX": 0.01,
            "AAPL": 0.46,
            "MSFT": 0.54,
            "NVDA": 0.67,
        },
        volumes={
            "QQQ": 8_000_000.0,
            "BOXX": 600_000.0,
            "AAPL": 6_500_000.0,
            "MSFT": 5_900_000.0,
            "NVDA": 7_500_000.0,
        },
    )


def _build_linear_bars(
    *,
    end_date: str,
    periods: int,
    bases: dict[str, float],
    slopes: dict[str, float],
    volumes: dict[str, float],
) -> dict[str, pd.DataFrame]:
    index = pd.bdate_range(end=pd.Timestamp(end_date), periods=periods)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol, base in bases.items():
        slope = slopes[symbol]
        close = pd.Series(
            [base + slope * step for step in range(len(index))],
            index=index,
            dtype=float,
        )
        open_ = close * 0.995
        bars_by_symbol[symbol] = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.01,
                "low": open_ * 0.99,
                "close": close,
                "volume": float(volumes[symbol]),
            }
        )
    return bars_by_symbol


def _write_feature_snapshot_manifest(
    *,
    snapshot_path: Path,
    strategy_profile: str,
    contract_version: str,
    snapshot_as_of: str,
    config_name: str,
    config_path: Path | None = None,
) -> None:
    manifest_path = Path(f"{snapshot_path}.manifest.json")
    payload = {
        "strategy_profile": strategy_profile,
        "config_name": config_name,
        "contract_version": contract_version,
        "snapshot_as_of": snapshot_as_of,
        "snapshot_sha256": _sha256_file(snapshot_path),
        "config_sha256": _sha256_file(config_path) if config_path is not None else "paper-signal-test-config",
    }
    if config_path is not None:
        payload["config_path"] = str(config_path)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ues_config_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[2] / "UsEquityStrategies" / relative_path

