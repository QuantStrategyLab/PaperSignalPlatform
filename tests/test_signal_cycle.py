from __future__ import annotations

from dataclasses import dataclass, field

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
