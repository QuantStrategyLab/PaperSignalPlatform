from __future__ import annotations

import json

import numpy as np
import pandas as pd

from signal_notifier.grouped_tool_choice_notify import (
    GROUP_CRYPTO_ZH,
    GROUP_MAGS7,
    GroupedToolChoiceSignal,
    ToolChoiceAssetSignal,
    build_grouped_tool_choice_notification,
    build_grouped_tool_choice_snapshot,
    compute_grouped_tool_choice_signal,
    parse_mags7_universe,
    read_grouped_tool_choice_snapshot,
    should_send_grouped_tool_choice_notification,
    write_grouped_tool_choice_snapshot,
)


def _asset(
    symbol: str,
    *,
    group: str = GROUP_MAGS7,
    side: str = "cash",
    target_symbol: str | None = None,
    tool_label_zh: str = "2x",
    weight: float = 0.0,
    recommendation_score: float | None = None,
    momentum_lookback: int | None = None,
    momentum: float | None = None,
) -> ToolChoiceAssetSignal:
    route_config = {}
    if recommendation_score is not None:
        route_config["recommendation_score"] = recommendation_score
    if momentum_lookback is not None:
        route_config["momentum_lookback"] = momentum_lookback
    diagnostics = {"decision_reasons": ("sample",), "route_config": route_config}
    if momentum is not None:
        diagnostics["underlying_momentum"] = momentum
    return ToolChoiceAssetSignal(
        group=group,
        underlying_symbol=symbol,
        as_of=pd.Timestamp("2026-04-24"),
        ready=True,
        side=side,
        target_symbol=target_symbol,
        tool="long2" if tool_label_zh == "2x" else "stock_long",
        tool_label_zh=tool_label_zh,
        tool_label_en="2x" if tool_label_zh == "2x" else "stock",
        gross_exposure=weight,
        diagnostics=diagnostics,
    )


def test_grouped_notification_zh_includes_grouped_tool_choices():
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(
            _asset(
                "NVDA",
                side="long",
                target_symbol="NVDL",
                tool_label_zh="2x",
                weight=0.8854,
                recommendation_score=1.0614,
                momentum_lookback=60,
                momentum=0.0875,
            ),
            _asset(
                "MSFT",
                side="cash",
                tool_label_zh="正股",
                recommendation_score=0.0805,
                momentum_lookback=120,
                momentum=-0.1184,
            ),
            _asset(
                "META",
                side="cash",
                tool_label_zh="2x",
                recommendation_score=0.3159,
                momentum_lookback=40,
                momentum=0.0094,
            ),
            _asset(
                "COIN",
                group=GROUP_CRYPTO_ZH,
                side="short",
                target_symbol="CONI",
                tool_label_zh="2x",
                weight=0.25,
                recommendation_score=0.1060,
                momentum_lookback=10,
                momentum=-0.1902,
            ),
        ),
        target_weights={"NVDL": 0.8854, "CONI": 0.25},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert text == (
        "【杠杆 / MAG7科技龙头】资金池 60%\n"
        "NVDA: 做多 / 推荐#1 / 2x / 仓位 88.54% / 基础分 1.06 / 动态分 1.03 / 强度 1.00x / 组内分配 100.00% / 账户建议 60.00% / 60日动量 8.75%\n"
        "\n"
        "【杠杆 / 加密货币】资金池 10%\n"
        "COIN: 做空 / 推荐#1 / 2x / 仓位 25.00% / 基础分 0.11 / 动态分 0.33 / 强度 1.00x / 组内分配 100.00% / 账户建议 10.00% / 10日动量 -19.02%"
    )


def test_grouped_notification_zh_marks_stateful_coin_holding_age():
    coin_signal = _asset(
        "COIN",
        group=GROUP_CRYPTO_ZH,
        side="long",
        target_symbol="CONL",
        tool_label_zh="2x",
        weight=0.42,
        recommendation_score=0.4487,
        momentum_lookback=5,
        momentum=0.16,
    )
    diagnostics = dict(coin_signal.diagnostics)
    diagnostics.update(
        {
            "uses_stateful_short_hold": True,
            "previous_side": "long",
            "held_days": 2,
            "entry_reference_price": 115.25,
        }
    )
    coin_signal = ToolChoiceAssetSignal(
        **{
            **coin_signal.__dict__,
            "diagnostics": diagnostics,
        }
    )
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(coin_signal,),
        target_weights={"CONL": 0.42},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert "COIN: 做多 / 推荐#1 / 2x / 仓位 42.00% / 基础分 0.45 / 动态分 0.67 / 强度 1.00x / 组内分配 100.00%" in text
    assert "5日动量 16.00% / 持有第2天 / 参考入场 115.25" in text


def test_grouped_notification_zh_keeps_stateful_coin_exit_even_when_cash():
    coin_signal = _asset(
        "COIN",
        group=GROUP_CRYPTO_ZH,
        side="cash",
        tool_label_zh="2x",
        recommendation_score=0.4487,
        momentum_lookback=5,
        momentum=0.03,
    )
    diagnostics = dict(coin_signal.diagnostics)
    diagnostics.update(
        {
            "uses_stateful_short_hold": True,
            "previous_side": "long",
            "decision_reasons": ("take_profit_exit",),
        }
    )
    coin_signal = ToolChoiceAssetSignal(
        **{
            **coin_signal.__dict__,
            "diagnostics": diagnostics,
        }
    )
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(coin_signal,),
        target_weights={},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert "COIN: 空仓 / 推荐#1 / 2x / 仓位 0.00%" in text
    assert "止盈退出" in text


def test_grouped_notification_zh_repeats_recent_stateful_coin_exit():
    coin_signal = _asset(
        "COIN",
        group=GROUP_CRYPTO_ZH,
        side="cash",
        tool_label_zh="2x",
        recommendation_score=0.4487,
        momentum_lookback=5,
        momentum=0.01,
    )
    diagnostics = dict(coin_signal.diagnostics)
    diagnostics.update(
        {
            "uses_stateful_short_hold": True,
            "previous_side": "cash",
            "last_exit_reason": "take_profit_exit",
            "trading_days_since_exit": 2,
            "exit_reminder_trading_days": 3,
        }
    )
    coin_signal = ToolChoiceAssetSignal(
        **{
            **coin_signal.__dict__,
            "diagnostics": diagnostics,
        }
    )
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(coin_signal,),
        target_weights={},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert "止盈退出后第2天" in text


def test_grouped_notification_zh_returns_empty_message_when_all_cash():
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(
            _asset("META", side="cash", recommendation_score=0.3159),
            _asset("MSFT", side="cash", tool_label_zh="正股", recommendation_score=0.0805),
        ),
        target_weights={},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert text == "今日无持仓信号"


def test_grouped_notification_summarizes_core_stock_replaced_by_same_underlying_leverage():
    tactical_nvda = _asset(
        "NVDA",
        side="long",
        target_symbol="NVDL",
        tool_label_zh="2x",
        weight=0.88,
        recommendation_score=1.0614,
        momentum_lookback=60,
        momentum=0.0875,
    )
    core_nvda = _asset(
        "NVDA",
        side="long",
        target_symbol="NVDA",
        tool_label_zh="正股",
        weight=0.35,
        recommendation_score=0.7910,
    )
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(tactical_nvda, core_nvda),
        target_weights={"NVDL": 0.70},
    )

    text = build_grouped_tool_choice_notification(signal, lang="zh")

    assert "NVDA: 做多 / 推荐#1 / 2x" in text
    assert "账户建议 60.00%" in text
    assert "【正股长期动量】资金池 30%" in text
    assert "本轮无账户建议：NVDA 已由同标的杠杆替代" in text
    assert "NVDA: 做多 / 推荐#1 / 正股" not in text


def test_grouped_snapshot_identity_changes_when_asset_side_changes(tmp_path):
    signal = GroupedToolChoiceSignal(
        as_of=pd.Timestamp("2026-04-24"),
        effective_after_trading_days=1,
        ready=True,
        asset_signals=(_asset("NVDA", side="cash"),),
        target_weights={},
    )
    snapshot = build_grouped_tool_choice_snapshot(signal)
    state_path = write_grouped_tool_choice_snapshot(snapshot, tmp_path / "grouped_state.json")
    previous = read_grouped_tool_choice_snapshot(state_path)

    assert json.loads((tmp_path / "grouped_state.json").read_text(encoding="utf-8"))["as_of"] == "2026-04-24"
    assert should_send_grouped_tool_choice_notification(snapshot, previous) is False

    changed = build_grouped_tool_choice_snapshot(
        GroupedToolChoiceSignal(
            as_of=pd.Timestamp("2026-04-24"),
            effective_after_trading_days=1,
            ready=True,
            asset_signals=(_asset("NVDA", side="long", target_symbol="NVDL", weight=0.5),),
            target_weights={"NVDL": 0.5},
        )
    )
    assert should_send_grouped_tool_choice_notification(changed, previous) is True


def test_compute_mags7_prefers_nvda_leverage_over_same_underlying_stock():
    dates = pd.bdate_range("2025-01-02", periods=260)
    step = np.arange(len(dates))
    nvda_returns = 0.0025 + 0.0004 * np.sin(step / 3.0)
    qqq_returns = 0.0010 + 0.0002 * np.cos(step / 5.0)
    flat_returns = 0.0001 * np.sin(step / 4.0)

    nvda = pd.Series(100.0 * np.cumprod(1.0 + nvda_returns), index=dates)
    nvd_return = (2.0 * pd.Series(nvda_returns, index=dates)).clip(lower=-0.999999)
    nvdl = pd.Series(50.0 * np.cumprod(1.0 + nvd_return), index=dates)
    qqq = pd.Series(400.0 * np.cumprod(1.0 + qqq_returns), index=dates)
    msft = pd.Series(300.0 * np.cumprod(1.0 + flat_returns), index=dates)
    meta = pd.Series(250.0 * np.cumprod(1.0 + flat_returns), index=dates)
    aapl = pd.Series(180.0 * np.cumprod(1.0 + flat_returns), index=dates)
    amzn = pd.Series(140.0 * np.cumprod(1.0 + flat_returns), index=dates)
    googl = pd.Series(120.0 * np.cumprod(1.0 + flat_returns), index=dates)
    tsla = pd.Series(240.0 * np.cumprod(1.0 + flat_returns), index=dates)

    signal = compute_grouped_tool_choice_signal(
        {
            "QQQ": qqq,
            "AAPL": aapl,
            "AMZN": amzn,
            "GOOGL": googl,
            "NVDA": nvda,
            "NVDL": nvdl,
            "MSFT": msft,
            "META": meta,
            "TSLA": tsla,
        },
        groups=(GROUP_MAGS7,),
    )

    assert signal.target_weights == {"NVDL": 0.60}
    snapshot = build_grouped_tool_choice_snapshot(signal)
    nvda_stock = next(
        item for item in snapshot["asset_signals"] if item["underlying_symbol"] == "NVDA" and item["tool"] == "stock_long"
    )
    assert nvda_stock["portfolio_excluded_reason"] == "same_underlying_tactical_active"
    assert nvda_stock["account_allocation"] == 0.0


def test_compute_mags7_global_regime_gate_is_diagnostic_when_qqq_bearish():
    dates = pd.bdate_range("2025-01-02", periods=260)
    msft_returns = np.full(len(dates), 0.003)
    msft = pd.Series(300.0 * np.cumprod(1.0 + msft_returns), index=dates)
    qqq = pd.Series(np.r_[np.linspace(400.0, 420.0, 80), np.linspace(420.0, 300.0, 180)], index=dates)

    signal = compute_grouped_tool_choice_signal(
        {
            "QQQ": qqq,
            "MSFT": msft,
        },
        groups=(GROUP_MAGS7,),
        mags7_universe=("MSFT",),
    )

    assert signal.diagnostics["mags7_regime_gate"]["risk_on"] is False
    assert signal.diagnostics["mags7_regime_gate"]["reason"] == "qqq_below_sma150"
    assert signal.diagnostics["portfolio_policy"]["mags7_regime_gate"]["bear_action"] == "diagnostic_only"
    assert signal.target_weights == {"MSFU": 0.60}
    msft_leverage = next(asset for asset in signal.asset_signals if asset.underlying_symbol == "MSFT" and asset.tool == "long2")
    assert msft_leverage.side == "long"
    assert msft_leverage.diagnostics["mags7_regime_warning"] == "qqq_below_regime_sma"
    assert "mags7_regime_bear" not in msft_leverage.diagnostics["decision_reasons"]


def test_compute_mags7_momentum_overlay_blocks_active_routes_outside_top3():
    dates = pd.bdate_range("2025-01-02", periods=260)
    qqq = pd.Series(400.0 * np.cumprod(1.0 + np.full(len(dates), 0.0010)), index=dates)
    nvda = pd.Series(100.0 * np.cumprod(1.0 + np.full(len(dates), 0.0050)), index=dates)
    meta = pd.Series(250.0 * np.cumprod(1.0 + np.full(len(dates), 0.0040)), index=dates)
    googl = pd.Series(120.0 * np.cumprod(1.0 + np.full(len(dates), 0.0035)), index=dates)
    msft = pd.Series(300.0 * np.cumprod(1.0 + np.full(len(dates), 0.0020)), index=dates)

    signal = compute_grouped_tool_choice_signal(
        {
            "QQQ": qqq,
            "NVDA": nvda,
            "META": meta,
            "GOOGL": googl,
            "MSFT": msft,
        },
        groups=(GROUP_MAGS7,),
        mags7_universe=("NVDA", "META", "GOOGL", "MSFT"),
    )

    overlay = signal.diagnostics["mags7_momentum_overlay"]
    assert overlay["ready"] is True
    assert overlay["selected_underlyings"] == ["NVDA", "META", "GOOGL"]
    assert all(symbol not in signal.target_weights for symbol in ("MSFT", "MSFU"))
    msft_assets = [asset for asset in signal.asset_signals if asset.underlying_symbol == "MSFT"]
    assert msft_assets
    assert all(asset.side == "cash" for asset in msft_assets)
    assert any(asset.diagnostics["pre_momentum_overlay_side"] == "long" for asset in msft_assets)
    assert all(
        "mags7_momentum_overlay_not_top3" in asset.diagnostics["decision_reasons"]
        for asset in msft_assets
        if asset.diagnostics.get("pre_momentum_overlay_side") == "long"
    )


def test_compute_mags7_universe_intersects_current_members_with_configured_routes():
    dates = pd.bdate_range("2025-01-02", periods=260)
    step = np.arange(len(dates))
    nvda_returns = 0.0025 + 0.0004 * np.sin(step / 3.0)
    qqq_returns = 0.0010 + 0.0002 * np.cos(step / 5.0)
    flat_returns = 0.0001 * np.sin(step / 4.0)

    nvda = pd.Series(100.0 * np.cumprod(1.0 + nvda_returns), index=dates)
    nvd_return = (2.0 * pd.Series(nvda_returns, index=dates)).clip(lower=-0.999999)
    nvdl = pd.Series(50.0 * np.cumprod(1.0 + nvd_return), index=dates)
    qqq = pd.Series(400.0 * np.cumprod(1.0 + qqq_returns), index=dates)
    msft = pd.Series(300.0 * np.cumprod(1.0 + flat_returns), index=dates)
    meta = pd.Series(250.0 * np.cumprod(1.0 + flat_returns), index=dates)

    signal = compute_grouped_tool_choice_signal(
        {
            "QQQ": qqq,
            "NVDA": nvda,
            "NVDL": nvdl,
            "MSFT": msft,
            "META": meta,
        },
        groups=(GROUP_MAGS7,),
        mags7_universe=("MSFT", "META", "ORCL"),
    )

    assert signal.target_weights == {}
    assert all(asset.underlying_symbol != "NVDA" for asset in signal.asset_signals)
    policy = signal.diagnostics["mags7_universe_policy"]
    assert policy["eligible_underlyings"] == ["MSFT", "META"]
    assert "NVDA" in policy["excluded_implemented_underlyings"]
    assert policy["ignored_unconfigured_underlyings"] == ["ORCL"]


def test_parse_mags7_universe_normalizes_and_deduplicates_symbols():
    assert parse_mags7_universe(" nvda, MSFT, nvda, orcl ") == ("NVDA", "MSFT", "ORCL")
    assert parse_mags7_universe("") is None


def test_compute_crypto_short_signal_selects_coni_when_short_gate_triggers():
    dates = pd.bdate_range("2025-01-02", periods=260)
    coin = pd.Series(np.r_[np.full(210, 250.0), np.linspace(245.0, 130.0, 50)], index=dates)
    qqq = pd.Series(np.linspace(400.0, 410.0, len(dates)), index=dates)
    btc = pd.Series(np.r_[np.full(210, 90000.0), np.linspace(88000.0, 60000.0, 50)], index=dates)
    conl = pd.Series(100.0 * (1.0 + (2.0 * coin.pct_change(fill_method=None)).fillna(0.0)).cumprod(), index=dates)
    coni = pd.Series(100.0 * (1.0 + (-2.0 * coin.pct_change(fill_method=None)).clip(lower=-0.999999).fillna(0.0)).cumprod(), index=dates)

    signal = compute_grouped_tool_choice_signal(
        {
            "QQQ": qqq,
            "COIN": coin,
            "BTC-USD": btc,
            "CONL": conl,
            "CONI": coni,
        },
        groups=(GROUP_CRYPTO_ZH,),
    )

    assert len(signal.asset_signals) == 1
    coin_signal = signal.asset_signals[0]
    assert coin_signal.underlying_symbol == "COIN"
    assert coin_signal.side == "short"
    assert coin_signal.target_symbol == "CONI"
    assert coin_signal.gross_exposure > 0.0
