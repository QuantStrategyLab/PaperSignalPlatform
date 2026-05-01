"""EOD next-day signal helper for the COIN short-hold dual-direction vt_50 route.

This module packages the current research lead into a pure function that can be
called after the U.S. equity close. The signal uses COIN and BTC daily closes to
decide whether the next session should hold CONL, hold CONI, or stay in cash.

Timing convention:
- Inputs are daily closes through `as_of`
- The returned target is intended for the next trading session
- BTC is lagged by one UTC daily close to match the research backtests
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_LONG_SYMBOL = "CONL"
DEFAULT_SHORT_SYMBOL = "CONI"
DEFAULT_SIGNAL_SOURCE = "coin_short_hold_fixed50_eod"


@dataclass(frozen=True)
class CoinShortHoldVT50Config:
    long_symbol: str = DEFAULT_LONG_SYMBOL
    short_symbol: str = DEFAULT_SHORT_SYMBOL
    coin_sma: int = 150
    momentum_lookback: int = 5
    momentum_threshold: float = 0.08
    btc_ma: int = 150
    coin_rv_cap: float = 0.90
    max_hold_days: int = 10
    take_profit: float = 0.40
    exit_reminder_trading_days: int = 3
    position_sizing: str = "fixed"
    fixed_weight: float = 0.50
    vol_target: float = 0.50
    signal_effective_after_trading_days: int = 1
    signal_source: str = DEFAULT_SIGNAL_SOURCE


@dataclass(frozen=True)
class CoinShortHoldVT50Signal:
    as_of: pd.Timestamp
    effective_after_trading_days: int
    ready: bool
    target_weights: dict[str, float]
    side: str
    target_symbol: str | None
    gross_exposure: float
    state_position: int
    held_days: int
    entry_reference_price: float | None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_execution_payload(self) -> tuple[dict[str, float], dict[str, Any]]:
        managed_symbols = tuple(
            dict.fromkeys(
                symbol
                for symbol in (
                    self.diagnostics.get("long_symbol"),
                    self.diagnostics.get("short_symbol"),
                )
                if symbol
            )
        )
        allocation = {
            "target_mode": "weight",
            "strategy_symbols": managed_symbols,
            "risk_symbols": managed_symbols,
            "income_symbols": (),
            "safe_haven_symbols": (),
            "targets": dict(self.target_weights),
        }
        metadata = {
            "trade_date": self.as_of.date().isoformat(),
            "snapshot_as_of": self.as_of.date().isoformat(),
            "signal_effective_after_trading_days": self.effective_after_trading_days,
            "signal_source": self.diagnostics.get("signal_source"),
            "managed_symbols": managed_symbols,
            "status_icon": "🐤",
            "actionable": bool(self.ready),
            "dashboard_text": self.diagnostics.get("dashboard_text", ""),
            "allocation": allocation,
            **self.diagnostics,
        }
        return dict(self.target_weights), metadata


def _normalize_close_series(series: pd.Series, *, name: str) -> pd.Series:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if series.empty:
        raise ValueError(f"{name} is empty")
    normalized = series.copy()
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None).normalize()
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.astype(float)


def _exact_two_x_close(coin_close: pd.Series) -> tuple[pd.Series, pd.Series]:
    coin_return = coin_close.pct_change(fill_method=None)
    long_close = 100.0 * (1.0 + (2.0 * coin_return).clip(lower=-0.999999)).cumprod()
    short_close = 100.0 * (1.0 + (-2.0 * coin_return).clip(lower=-0.999999)).cumprod()
    return long_close, short_close


def _build_signal_frame(
    coin_close: pd.Series,
    btc_close: pd.Series,
    *,
    config: CoinShortHoldVT50Config,
    long_close: pd.Series | None = None,
    short_close: pd.Series | None = None,
) -> pd.DataFrame:
    coin_close = _normalize_close_series(coin_close, name="coin_close")
    btc_close = _normalize_close_series(btc_close, name="btc_close")

    synthetic_long, synthetic_short = _exact_two_x_close(coin_close)
    if long_close is None:
        resolved_long = synthetic_long
    else:
        normalized_long = _normalize_close_series(long_close, name="long_close")
        resolved_long = normalized_long.reindex(coin_close.index).combine_first(synthetic_long)
    if short_close is None:
        resolved_short = synthetic_short
    else:
        normalized_short = _normalize_close_series(short_close, name="short_close")
        resolved_short = normalized_short.reindex(coin_close.index).combine_first(synthetic_short)

    frame = pd.DataFrame(index=coin_close.index)
    frame["coin_close"] = coin_close
    frame["coin_return"] = frame["coin_close"].pct_change(fill_method=None)
    frame["long_close"] = resolved_long.reindex(frame.index)
    frame["short_close"] = resolved_short.reindex(frame.index)
    frame["long_return"] = frame["long_close"].pct_change(fill_method=None)
    frame["short_return"] = frame["short_close"].pct_change(fill_method=None)
    frame["btc_close"] = btc_close.shift(1).reindex(frame.index).ffill()
    frame["coin_ma"] = frame["coin_close"].rolling(config.coin_sma).mean()
    frame["coin_mom"] = frame["coin_close"].pct_change(config.momentum_lookback)
    frame["btc_ma"] = frame["btc_close"].rolling(config.btc_ma).mean()
    frame["coin_rv_20"] = frame["coin_return"].rolling(20).std() * np.sqrt(252.0)
    dual_rv = pd.concat(
        [
            frame["long_return"].rolling(20).std() * np.sqrt(252.0),
            frame["short_return"].rolling(20).std() * np.sqrt(252.0),
        ],
        axis=1,
    ).max(axis=1)
    frame["dual_rv_20_prev"] = dual_rv.shift(1)
    return frame


def compute_coin_short_hold_vt50_signal(
    coin_close: pd.Series,
    btc_close: pd.Series,
    *,
    as_of: str | pd.Timestamp | None = None,
    config: CoinShortHoldVT50Config | None = None,
    long_close: pd.Series | None = None,
    short_close: pd.Series | None = None,
) -> CoinShortHoldVT50Signal:
    config = config or CoinShortHoldVT50Config()
    frame = _build_signal_frame(
        coin_close,
        btc_close,
        config=config,
        long_close=long_close,
        short_close=short_close,
    )
    requested_as_of = pd.Timestamp(as_of).tz_localize(None).normalize() if as_of is not None else frame.index.max()
    available = frame.loc[:requested_as_of].copy()
    if available.empty:
        raise ValueError("No market data available at or before as_of")

    required_columns = [
        "coin_close",
        "coin_ma",
        "coin_mom",
        "btc_close",
        "btc_ma",
        "coin_rv_20",
        "long_close",
        "short_close",
        "dual_rv_20_prev",
    ]
    ready_frame = available.dropna(subset=required_columns).copy()
    if ready_frame.empty:
        as_of_ts = available.index.max()
        diagnostics = {
            "signal_source": config.signal_source,
            "long_symbol": config.long_symbol,
            "short_symbol": config.short_symbol,
            "reason": "insufficient_history",
            "ready_bars": int(len(available)),
            "required_lookback_bars": int(max(config.coin_sma, config.btc_ma) + 21),
            "dashboard_text": "COIN short-hold vt_50 not ready: insufficient history",
        }
        return CoinShortHoldVT50Signal(
            as_of=as_of_ts,
            effective_after_trading_days=config.signal_effective_after_trading_days,
            ready=False,
            target_weights={},
            side="cash",
            target_symbol=None,
            gross_exposure=0.0,
            state_position=0,
            held_days=0,
            entry_reference_price=None,
            diagnostics=diagnostics,
        )

    position = 0
    entry_price: float | None = None
    held_days = 0
    states: list[dict[str, Any]] = []

    for date, row in ready_frame.iterrows():
        previous_position = position
        desired = 0
        decision_reasons: list[str] = []
        if row["coin_close"] > row["coin_ma"] and row["coin_mom"] > config.momentum_threshold:
            desired = 1
            decision_reasons.append("coin_trend_long")
        elif row["coin_close"] < row["coin_ma"] and row["coin_mom"] < -config.momentum_threshold:
            desired = -1
            decision_reasons.append("coin_trend_short")
        else:
            decision_reasons.append("no_trend_signal")

        if desired != 0:
            if pd.isna(row["btc_ma"]):
                desired = 0
                decision_reasons.append("btc_ma_not_ready")
            elif desired == 1 and row["btc_close"] <= row["btc_ma"]:
                desired = 0
                decision_reasons.append("btc_filter_blocked_long")
            elif desired == -1 and row["btc_close"] >= row["btc_ma"]:
                desired = 0
                decision_reasons.append("btc_filter_blocked_short")

        if desired != 0:
            if pd.isna(row["coin_rv_20"]) or row["coin_rv_20"] > config.coin_rv_cap:
                desired = 0
                decision_reasons.append("coin_rv_blocked")

        if position != 0 and entry_price is not None:
            held_days += 1
            current_close = row["long_close"] if position == 1 else row["short_close"]
            if current_close >= entry_price * (1.0 + config.take_profit):
                desired = 0
                decision_reasons.append("take_profit_exit")
            if held_days >= config.max_hold_days:
                desired = 0
                decision_reasons.append("max_hold_exit")

        if desired != position:
            if desired == 1:
                entry_price = float(row["long_close"])
                held_days = 0
            elif desired == -1:
                entry_price = float(row["short_close"])
                held_days = 0
            else:
                entry_price = None
                held_days = 0
        position = desired
        exit_reasons = tuple(
            reason
            for reason in decision_reasons
            if reason in {"take_profit_exit", "max_hold_exit", "no_trend_signal", "btc_filter_blocked_long", "btc_filter_blocked_short", "coin_rv_blocked"}
        )
        exited_to_cash = previous_position != 0 and position == 0

        vol_scale = 0.0
        if position != 0:
            if config.position_sizing == "fixed":
                vol_scale = min(1.0, max(0.0, config.fixed_weight))
            elif config.position_sizing == "vol_target":
                reference_vol = row["dual_rv_20_prev"]
                if pd.notna(reference_vol) and float(reference_vol) > 0:
                    vol_scale = min(1.0, config.vol_target / float(reference_vol))
            else:
                raise ValueError(f"Unsupported position_sizing: {config.position_sizing}")
        gross_exposure = abs(position) * vol_scale
        target_weights: dict[str, float] = {}
        target_symbol: str | None = None
        side = "cash"
        if position == 1 and gross_exposure > 0:
            target_symbol = config.long_symbol
            target_weights[target_symbol] = gross_exposure
            side = "long"
        elif position == -1 and gross_exposure > 0:
            target_symbol = config.short_symbol
            target_weights[target_symbol] = gross_exposure
            side = "short"

        states.append(
            {
                "date": date,
                "previous_position": previous_position,
                "position": position,
                "side": side,
                "target_symbol": target_symbol,
                "target_weights": target_weights,
                "gross_exposure": gross_exposure,
                "held_days": held_days,
                "entry_price": entry_price,
                "coin_close": float(row["coin_close"]),
                "coin_ma": float(row["coin_ma"]),
                "coin_mom": float(row["coin_mom"]),
                "coin_rv_20": float(row["coin_rv_20"]),
                "btc_close_lagged": float(row["btc_close"]),
                "btc_ma": float(row["btc_ma"]),
                "dual_rv_20_prev": float(row["dual_rv_20_prev"]),
                "vol_scale": float(vol_scale),
                "long_close": float(row["long_close"]),
                "short_close": float(row["short_close"]),
                "decision_reasons": tuple(decision_reasons),
                "exited_to_cash": exited_to_cash,
                "exit_reasons": exit_reasons if exited_to_cash else (),
            }
        )

    latest = states[-1]
    previous = (
        states[-2]
        if len(states) >= 2
        else {
            "position": 0,
            "side": "cash",
            "target_symbol": None,
            "gross_exposure": 0.0,
            "held_days": 0,
            "entry_price": None,
        }
    )
    dashboard_text = (
        f"COIN short-hold {config.position_sizing} | side={latest['side']} "
        f"symbol={latest['target_symbol'] or 'CASH'} "
        f"gross={latest['gross_exposure']:.2%} mom5={latest['coin_mom']:.2%} "
        f"coin_rv20={latest['coin_rv_20']:.2%} dual_rv20_prev={latest['dual_rv_20_prev']:.2%} "
        f"held_days={latest['held_days']}"
    )
    last_exit = next((state for state in reversed(states) if state.get("exited_to_cash")), None)
    trading_days_since_exit: int | None = None
    last_exit_reason: str | None = None
    last_exit_date: str | None = None
    if last_exit is not None:
        last_exit_date = last_exit["date"].date().isoformat()
        trading_days_since_exit = max(0, len(ready_frame.loc[last_exit["date"] : latest["date"]]) - 1)
        reasons = tuple(last_exit.get("exit_reasons") or ())
        if "take_profit_exit" in reasons:
            last_exit_reason = "take_profit_exit"
        elif "max_hold_exit" in reasons:
            last_exit_reason = "max_hold_exit"
        elif reasons:
            last_exit_reason = str(reasons[0])
        else:
            last_exit_reason = "signal_exit"
    diagnostics = {
        "signal_source": config.signal_source,
        "long_symbol": config.long_symbol,
        "short_symbol": config.short_symbol,
        "strategy_config": asdict(config),
        "side": latest["side"],
        "target_symbol": latest["target_symbol"],
        "gross_exposure": latest["gross_exposure"],
        "previous_side": previous["side"],
        "previous_target_symbol": previous["target_symbol"],
        "previous_gross_exposure": previous["gross_exposure"],
        "previous_state_position": previous["position"],
        "vol_scale": latest["vol_scale"],
        "state_position": latest["position"],
        "held_days": latest["held_days"],
        "entry_reference_price": latest["entry_price"],
        "last_exit_date": last_exit_date,
        "last_exit_reason": last_exit_reason,
        "trading_days_since_exit": trading_days_since_exit,
        "exit_reminder_trading_days": config.exit_reminder_trading_days,
        "coin_close": latest["coin_close"],
        "coin_sma": latest["coin_ma"],
        "coin_momentum": latest["coin_mom"],
        "coin_rv_20": latest["coin_rv_20"],
        "btc_close_lagged": latest["btc_close_lagged"],
        "btc_ma": latest["btc_ma"],
        "dual_rv_20_prev": latest["dual_rv_20_prev"],
        "decision_reasons": latest["decision_reasons"],
        "dashboard_text": dashboard_text,
        "actionable": True,
    }
    return CoinShortHoldVT50Signal(
        as_of=latest["date"],
        effective_after_trading_days=config.signal_effective_after_trading_days,
        ready=True,
        target_weights=dict(latest["target_weights"]),
        side=str(latest["side"]),
        target_symbol=latest["target_symbol"],
        gross_exposure=float(latest["gross_exposure"]),
        state_position=int(latest["position"]),
        held_days=int(latest["held_days"]),
        entry_reference_price=latest["entry_price"],
        diagnostics=diagnostics,
    )
