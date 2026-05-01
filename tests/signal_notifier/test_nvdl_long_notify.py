from __future__ import annotations

import json

import pandas as pd

from signal_notifier.grouped_tool_choice_notify import (
    GROUP_MAGS7,
    RECOMMENDATION_BUCKET_MAGS7_TACTICAL,
    GroupedToolChoiceSignal,
    ToolChoiceAssetSignal,
)
from signal_notifier.nvdl_long_notify import (
    build_nvdl_long_log,
    build_nvdl_long_notification,
    build_nvdl_long_snapshot,
    read_nvdl_long_snapshot,
    should_send_nvdl_long_notification,
    write_nvdl_long_snapshot,
)


def _sample_signal(*, side: str = "long") -> GroupedToolChoiceSignal:
    target_symbol = "NVDL" if side == "long" else None
    gross_exposure = 0.7379 if target_symbol else 0.0
    asset = ToolChoiceAssetSignal(
        group=GROUP_MAGS7,
        underlying_symbol="NVDA",
        as_of=pd.Timestamp("2026-04-24"),
        ready=True,
        side=side,
        target_symbol=target_symbol,
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        gross_exposure=gross_exposure,
        diagnostics={
            "signal_source": "grouped_tool_choice_eod",
            "target_symbol": "NVDL",
            "route_config": {
                "group": GROUP_MAGS7,
                "underlying_symbol": "NVDA",
                "side": "long",
                "tool": "long2",
                "tool_label_zh": "2x",
                "tool_label_en": "2x",
                "target_symbol": "NVDL",
                "sma_window": 200,
                "momentum_lookback": 60,
                "momentum_threshold": 0.05,
                "qqq_sma_window": 150,
                "vol_target": 0.60,
                "description": "NVDA > SMA200, 60d momentum > 5%, QQQ > SMA150; NVDL/2x vt 60%.",
                "recommendation_score": 1.0614,
                "recommendation_bucket": RECOMMENDATION_BUCKET_MAGS7_TACTICAL,
            },
            "decision_reasons": ("nvda_long_signal",) if target_symbol else ("momentum_below_threshold",),
            "underlying_close": 208.27,
            "underlying_sma": 185.03,
            "underlying_momentum": 0.125,
            "underlying_momentum_20": 0.2162,
            "underlying_momentum_60": 0.125,
            "underlying_rv20": 0.3144,
            "instrument_close": 48.2,
            "instrument_rv20_prev": 0.8131,
            "vol_scale": gross_exposure,
            "qqq_close": 430.0,
            "qqq_sma": 410.0,
            "qqq_momentum_20": 0.08,
            "qqq_momentum_60": 0.05,
        },
    )
    return GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(asset,),
        target_weights={"NVDL": 0.60} if target_symbol else {},
        diagnostics={"signal_source": "grouped_tool_choice_eod"},
    )


def test_build_nvdl_long_notification_zh_uses_mags7_tool_choice_rules():
    signal = _sample_signal(side="long")

    text = build_nvdl_long_notification(signal, lang="zh")

    assert "【杠杆 / MAG7科技龙头】资金池 60%" in text
    assert "NVDA: 做多 / 推荐#1 / 2x" in text
    assert "账户建议 60.00%" in text
    assert "60日动量 12.50%" in text


def test_build_nvdl_long_log_zh_includes_specialist_route_diagnostics():
    signal = _sample_signal(side="long")

    text = build_nvdl_long_log(signal, lang="zh")

    assert "分组工具选择策略" in text
    assert "杠杆 / MAG7科技龙头 / 推荐#1 NVDA" in text
    assert "规则: NVDA > SMA200, 60d momentum > 5%, QQQ > SMA150; NVDL/2x vt 60%." in text
    assert "60日动量: 12.50%" in text


def test_build_nvdl_long_notification_en_mentions_mags7_bucket():
    signal = _sample_signal(side="long")

    text = build_nvdl_long_notification(signal, lang="en")

    assert "[Leverage / MAG7 tech leaders] sleeve 60%" in text
    assert "NVDA: long / rec #1 / 2x" in text


def test_build_nvdl_long_notification_includes_reference_capital_details():
    signal = _sample_signal(side="long")

    text = build_nvdl_long_notification(signal, lang="zh", reference_capital_usd=100000)

    assert "账户建议 60.00% ($60,000)" in text


def test_build_nvdl_long_snapshot_and_write_json(tmp_path):
    signal = _sample_signal(side="cash")

    snapshot = build_nvdl_long_snapshot(signal)
    target_path = tmp_path / "nvdl_signal.json"
    output_path = write_nvdl_long_snapshot(snapshot, target_path)

    assert output_path == str(target_path.resolve())
    loaded = json.loads(target_path.read_text(encoding="utf-8"))
    assert loaded["strategy_name"] == "mags7_tool_choice"
    assert "legacy_strategy_name" not in loaded
    assert loaded["as_of"] == "2026-04-24"
    assert loaded["target_weights"] == {}


def test_should_send_nvdl_long_notification_only_when_identity_changes(tmp_path):
    first_signal = _sample_signal(side="long")
    first_snapshot = build_nvdl_long_snapshot(first_signal)
    state_path = write_nvdl_long_snapshot(first_snapshot, tmp_path / "nvdl_state.json")
    previous_snapshot = read_nvdl_long_snapshot(state_path)

    assert should_send_nvdl_long_notification(first_snapshot, previous_snapshot) is False

    changed_signal = _sample_signal(side="cash")
    changed_snapshot = build_nvdl_long_snapshot(changed_signal)
    assert should_send_nvdl_long_notification(changed_snapshot, previous_snapshot) is True
