from __future__ import annotations

import json

import pandas as pd

from signal_notifier.coin_short_hold_notify import (
    build_coin_short_hold_log,
    build_coin_short_hold_notification,
    build_coin_short_hold_snapshot,
    read_coin_short_hold_snapshot,
    should_send_coin_short_hold_notification,
    write_coin_short_hold_snapshot,
)
from signal_notifier.coin_short_hold_vt50 import CoinShortHoldVT50Signal


def _sample_signal(*, ready: bool = True, side: str = "long") -> CoinShortHoldVT50Signal:
    target_symbol = {"long": "CONL", "short": "CONI", "cash": None}[side]
    target_weights = {target_symbol: 0.42} if target_symbol else {}
    return CoinShortHoldVT50Signal(
        as_of=pd.Timestamp("2026-04-21"),
        effective_after_trading_days=1,
        ready=ready,
        target_weights=target_weights,
        side=side,
        target_symbol=target_symbol,
        gross_exposure=0.42 if target_symbol else 0.0,
        state_position={"long": 1, "short": -1, "cash": 0}[side],
        held_days=3 if target_symbol else 0,
        entry_reference_price=115.0 if target_symbol else None,
        diagnostics={
            "signal_source": "coin_short_hold_vt50_eod",
            "long_symbol": "CONL",
            "short_symbol": "CONI",
            "strategy_config": {"coin_sma": 150, "btc_ma": 50},
            "coin_close": 210.0,
            "coin_sma": 195.0,
            "coin_momentum": 0.12 if side == "long" else -0.12 if side == "short" else 0.0,
            "coin_rv_20": 0.55,
            "btc_close_lagged": 82000.0,
            "btc_ma": 78000.0,
            "dual_rv_20_prev": 0.38,
            "vol_scale": 0.42,
            "dashboard_text": "sample",
        },
    )


def test_build_coin_short_hold_notification_zh_mentions_target_symbol():
    signal = _sample_signal(side="long")

    text = build_coin_short_hold_notification(signal, lang="zh")

    assert text == "【加密货币】\nCOIN: 做多 CONL / 仓位 42.00%"
    assert "BTC(滞后1日)/MA50" not in text


def test_build_coin_short_hold_log_zh_includes_strategy_diagnostics():
    signal = _sample_signal(side="long")

    text = build_coin_short_hold_log(signal, lang="zh")

    assert "COIN 短持双向 vt_50 策略日志" in text
    assert "分组: 加密货币" in text
    assert "标的: CONL" in text
    assert "BTC(滞后1日)/MA50" in text


def test_build_coin_short_hold_notification_en_mentions_short_side():
    signal = _sample_signal(side="short")

    text = build_coin_short_hold_notification(signal, lang="en")

    assert text == "[Crypto]\nCOIN: short CONI / position 42.00%"
    assert "BTC(lagged 1d)/MA50" not in text


def test_build_coin_short_hold_notification_omits_reference_capital_details():
    signal = _sample_signal(side="long")

    text = build_coin_short_hold_notification(signal, lang="zh", reference_capital_usd=100000)

    assert "按参考资金 $100,000" not in text
    assert "仓位 42.00%" in text


def test_build_coin_short_hold_snapshot_and_write_json(tmp_path):
    signal = _sample_signal(side="cash")

    snapshot = build_coin_short_hold_snapshot(signal)
    target_path = tmp_path / "coin_signal.json"
    output_path = write_coin_short_hold_snapshot(snapshot, target_path)

    assert output_path == str(target_path.resolve())
    loaded = json.loads(target_path.read_text(encoding="utf-8"))
    assert loaded["as_of"] == "2026-04-21"
    assert loaded["side"] == "cash"
    assert loaded["target_weights"] == {}


def test_should_send_coin_short_hold_notification_only_when_identity_changes(tmp_path):
    first_signal = _sample_signal(side="long")
    first_snapshot = build_coin_short_hold_snapshot(first_signal)
    state_path = write_coin_short_hold_snapshot(first_snapshot, tmp_path / "coin_state.json")
    previous_snapshot = read_coin_short_hold_snapshot(state_path)

    assert should_send_coin_short_hold_notification(first_snapshot, previous_snapshot) is False

    changed_signal = _sample_signal(side="short")
    changed_snapshot = build_coin_short_hold_snapshot(changed_signal)
    assert should_send_coin_short_hold_notification(changed_snapshot, previous_snapshot) is True
