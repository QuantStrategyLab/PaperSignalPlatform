"""Grouped tool-choice strategy signal.

The signal layer is based on the accepted research gate:
- MAGS7 keeps specialist long-only routes for the current stock/2x tool set.
- Crypto uses the stateful COIN short-hold route for CONL/CONI.
- Weak short routes for NVDA, MSFT, and META are intentionally disabled.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from signal_notifier.coin_short_hold_notify import (
    DEFAULT_CONL_START,
    DEFAULT_IPO_START,
    download_coinbase_daily_close,
    download_nasdaq_close,
)
from signal_notifier.coin_short_hold_vt50 import CoinShortHoldVT50Config, compute_coin_short_hold_vt50_signal
from signal_notifier.nvdl_long_notify import DEFAULT_NVDL_START, DEFAULT_NVDA_START
from signal_notifier.signal_notifier_core import (
    DEFAULT_HTTP_TIMEOUT,
    read_json_snapshot,
    send_telegram_message,
    write_json_snapshot,
)


DEFAULT_LOOKBACK_DAYS = 900
DEFAULT_SIGNAL_SOURCE = "grouped_tool_choice_eod"
DEFAULT_STRATEGY_NAME = "grouped_tool_choice"
DEFAULT_EXECUTION_MODE = "user_configured"
DEFAULT_STRATEGY_DISPLAY_NAME_ZH = "分组工具选择策略"
DEFAULT_STRATEGY_DISPLAY_NAME_EN = "Grouped Tool Choice Strategy"
DEFAULT_CONI_2X_START = "2025-05-05"
GROUP_MAGS7 = "MAGS7"
GROUP_CRYPTO_ZH = "加密货币"
GROUP_CRYPTO_EN = "Crypto"
RECOMMENDATION_BUCKET_MAGS7_TACTICAL = "mags7_tactical_leveraged"
RECOMMENDATION_BUCKET_CRYPTO_TACTICAL = "crypto_tactical_leveraged"
RECOMMENDATION_BUCKET_TACTICAL = RECOMMENDATION_BUCKET_MAGS7_TACTICAL
RECOMMENDATION_BUCKET_CORE_STOCK = "core_stock_momentum"
ORDERED_RECOMMENDATION_BUCKETS = (
    RECOMMENDATION_BUCKET_MAGS7_TACTICAL,
    RECOMMENDATION_BUCKET_CRYPTO_TACTICAL,
    RECOMMENDATION_BUCKET_CORE_STOCK,
)
RECOMMENDATION_BUCKET_BUDGETS = {
    RECOMMENDATION_BUCKET_MAGS7_TACTICAL: 0.60,
    RECOMMENDATION_BUCKET_CRYPTO_TACTICAL: 0.10,
    RECOMMENDATION_BUCKET_CORE_STOCK: 0.30,
}
DYNAMIC_RANKING_MODE = "sqrt_base_score_x_dynamic_strength"
DYNAMIC_STRENGTH_MIN = 0.50
DYNAMIC_STRENGTH_MAX = 1.50
MAGS7_REGIME_GATE_NAME = "qqq_above_sma150"
MAGS7_REGIME_QQQ_SMA_WINDOW = 150
MAGS7_MOMENTUM_OVERLAY_NAME = "mags7_cross_sectional_momentum_top3"
MAGS7_MOMENTUM_OVERLAY_TOP_N = 3
MAGS7_MOMENTUM_OVERLAY_TREND_SMA_WINDOW = 150
GROUPED_COIN_SHORT_HOLD_CONFIG = CoinShortHoldVT50Config()
GROUPED_COIN_SHORT_HOLD_SCORE = 0.6265
MAGS7_ETF_STARTS = {
    "AAPU": pd.Timestamp("2022-09-07"),
    "AMZU": pd.Timestamp("2022-09-07"),
    "GGLL": pd.Timestamp("2022-09-07"),
    "NVDL": pd.Timestamp(DEFAULT_NVDL_START),
    "MSFU": pd.Timestamp("2024-01-02"),
    "FBL": pd.Timestamp("2024-01-02"),
    "TSLL": pd.Timestamp("2022-08-09"),
}


@dataclass(frozen=True)
class ToolChoiceRouteConfig:
    group: str
    underlying_symbol: str
    side: str
    tool: str
    tool_label_zh: str
    tool_label_en: str
    target_symbol: str
    vol_target: float
    sma_window: int | None = None
    momentum_lookback: int | None = None
    momentum_threshold: float | None = None
    ema_fast_window: int | None = None
    ema_slow_window: int | None = None
    qqq_sma_window: int | None = None
    btc_sma_window: int | None = None
    underlying_rv_cap: float | None = None
    max_weight: float = 1.0
    enabled: bool = True
    description: str = ""
    recommendation_score: float = 0.0
    recommendation_bucket: str = RECOMMENDATION_BUCKET_TACTICAL


@dataclass(frozen=True)
class ToolChoiceAssetSignal:
    group: str
    underlying_symbol: str
    as_of: pd.Timestamp
    ready: bool
    side: str
    target_symbol: str | None
    tool: str
    tool_label_zh: str
    tool_label_en: str
    gross_exposure: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroupedToolChoiceSignal:
    as_of: pd.Timestamp
    effective_after_trading_days: int
    ready: bool
    asset_signals: tuple[ToolChoiceAssetSignal, ...]
    target_weights: dict[str, float]
    diagnostics: dict[str, Any] = field(default_factory=dict)


ROUTES: tuple[ToolChoiceRouteConfig, ...] = (
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="AAPL",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="AAPU",
        sma_window=100,
        momentum_lookback=40,
        momentum_threshold=0.05,
        qqq_sma_window=150,
        vol_target=0.60,
        description="AAPL > SMA100, 40d momentum > 5%, QQQ > SMA150; AAPU/2x vt 60%.",
        recommendation_score=0.2241,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="AAPL",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="AAPL",
        sma_window=100,
        momentum_lookback=40,
        momentum_threshold=0.05,
        qqq_sma_window=150,
        vol_target=0.40,
        description="AAPL > SMA100, 40d momentum > 5%, QQQ > SMA150; stock vt 40%.",
        recommendation_score=0.1554,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="AMZN",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="AMZU",
        sma_window=200,
        momentum_lookback=40,
        momentum_threshold=0.08,
        qqq_sma_window=150,
        vol_target=0.60,
        description="AMZN > SMA200, 40d momentum > 8%, QQQ > SMA150; AMZU/2x vt 60%.",
        recommendation_score=0.0100,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="AMZN",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="AMZN",
        sma_window=200,
        momentum_lookback=60,
        momentum_threshold=0.03,
        qqq_sma_window=150,
        vol_target=0.40,
        description="AMZN > SMA200, 60d momentum > 3%, QQQ > SMA150; stock vt 40%.",
        recommendation_score=0.0733,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="GOOGL",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="GGLL",
        sma_window=100,
        momentum_lookback=60,
        momentum_threshold=0.08,
        qqq_sma_window=150,
        vol_target=0.60,
        description="GOOGL > SMA100, 60d momentum > 8%, QQQ > SMA150; GGLL/2x vt 60%.",
        recommendation_score=0.4595,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="GOOGL",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="GOOGL",
        sma_window=100,
        momentum_lookback=60,
        momentum_threshold=0.08,
        qqq_sma_window=150,
        vol_target=0.40,
        description="GOOGL > SMA100, 60d momentum > 8%, QQQ > SMA150; stock vt 40%.",
        recommendation_score=0.3354,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="NVDA",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="NVDL",
        sma_window=200,
        momentum_lookback=60,
        momentum_threshold=0.05,
        qqq_sma_window=150,
        vol_target=0.60,
        description="NVDA > SMA200, 60d momentum > 5%, QQQ > SMA150; NVDL/2x vt 60%.",
        recommendation_score=1.0614,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="MSFT",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="MSFU",
        sma_window=200,
        momentum_lookback=40,
        momentum_threshold=0.05,
        qqq_sma_window=None,
        vol_target=0.50,
        description="MSFT > SMA200, 40d momentum > 5%; MSFU/2x vt 50%.",
        recommendation_score=0.0100,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="MSFT",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="MSFT",
        sma_window=200,
        momentum_lookback=40,
        momentum_threshold=0.05,
        qqq_sma_window=None,
        vol_target=0.40,
        description="MSFT > SMA200, 40d momentum > 5%; stock vt 40%.",
        recommendation_score=0.0138,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="NVDA",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="NVDA",
        ema_fast_window=50,
        ema_slow_window=150,
        vol_target=0.35,
        description="NVDA EMA50 > EMA150; stock vt 35%.",
        recommendation_score=0.7910,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="META",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="META",
        sma_window=100,
        momentum_lookback=180,
        momentum_threshold=0.08,
        qqq_sma_window=200,
        vol_target=0.40,
        description="META > SMA100, 180d momentum > 8%, QQQ > SMA200; stock vt 40%.",
        recommendation_score=0.2746,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="META",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="FBL",
        sma_window=100,
        momentum_lookback=40,
        momentum_threshold=0.03,
        vol_target=0.60,
        description="META > SMA100, 40d momentum > 3%; FBL/2x vt 60%.",
        recommendation_score=0.3159,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="TSLA",
        side="long",
        tool="long2",
        tool_label_zh="2x",
        tool_label_en="2x",
        target_symbol="TSLL",
        sma_window=100,
        momentum_lookback=120,
        momentum_threshold=0.03,
        qqq_sma_window=200,
        vol_target=0.50,
        description="TSLA > SMA100, 120d momentum > 3%, QQQ > SMA200; TSLL/2x vt 50%.",
        recommendation_score=0.4347,
    ),
    ToolChoiceRouteConfig(
        group=GROUP_MAGS7,
        underlying_symbol="TSLA",
        side="long",
        tool="stock_long",
        tool_label_zh="正股",
        tool_label_en="stock",
        target_symbol="TSLA",
        sma_window=100,
        momentum_lookback=60,
        momentum_threshold=0.05,
        qqq_sma_window=200,
        vol_target=0.40,
        description="TSLA > SMA100, 60d momentum > 5%, QQQ > SMA200; stock vt 40%.",
        recommendation_score=0.3458,
        recommendation_bucket=RECOMMENDATION_BUCKET_CORE_STOCK,
    ),
)


def parse_mags7_universe(raw: str | None) -> tuple[str, ...] | None:
    if not raw:
        return None
    symbols: list[str] = []
    for item in raw.split(","):
        symbol = item.strip().upper()
        if not symbol:
            continue
        symbols.append(symbol)
    return tuple(dict.fromkeys(symbols)) or None


def _normalize_symbol_universe(symbols: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, ...] | None:
    if symbols is None:
        return None
    normalized = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    return tuple(dict.fromkeys(normalized))


def _implemented_mags7_underlyings() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            route.underlying_symbol
            for route in ROUTES
            if route.enabled and route.group == GROUP_MAGS7
        )
    )


def _allowed_mags7_underlyings(
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None,
) -> tuple[str, ...]:
    implemented = _implemented_mags7_underlyings()
    universe = _normalize_symbol_universe(mags7_universe)
    if universe is None:
        return implemented
    universe_set = set(universe)
    return tuple(symbol for symbol in implemented if symbol in universe_set)


def _mags7_universe_policy(
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None,
) -> dict[str, Any]:
    universe = _normalize_symbol_universe(mags7_universe)
    implemented = _implemented_mags7_underlyings()
    implemented_set = set(implemented)
    allowed = _allowed_mags7_underlyings(universe)
    allowed_set = set(allowed)
    return {
        "mode": "static_implemented_routes" if universe is None else "current_universe_intersection_implemented_routes",
        "input_universe": list(universe) if universe is not None else None,
        "implemented_underlyings": list(implemented),
        "eligible_underlyings": list(allowed),
        "excluded_implemented_underlyings": (
            [symbol for symbol in implemented if symbol not in allowed_set]
            if universe is not None
            else []
        ),
        "ignored_unconfigured_underlyings": (
            [symbol for symbol in universe if symbol not in implemented_set]
            if universe is not None
            else []
        ),
    }


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


def _normalize_as_of(
    as_of: str | pd.Timestamp | None,
    *,
    fallback: pd.Timestamp,
) -> pd.Timestamp:
    if as_of is None:
        return pd.Timestamp(fallback).tz_localize(None).normalize()
    timestamp = pd.Timestamp(as_of)
    return timestamp.tz_localize(None).normalize()


def _mags7_regime_gate(
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None,
) -> dict[str, Any]:
    qqq_close = _normalize_close_series(market_data["QQQ"], name="QQQ")
    requested_as_of = _normalize_as_of(as_of, fallback=qqq_close.index.max())
    qqq_close = qqq_close.loc[:requested_as_of]
    qqq_sma = qqq_close.rolling(MAGS7_REGIME_QQQ_SMA_WINDOW).mean()
    ready_frame = pd.DataFrame({"qqq_close": qqq_close, "qqq_sma": qqq_sma}).dropna()
    if ready_frame.empty:
        return {
            "name": MAGS7_REGIME_GATE_NAME,
            "ready": False,
            "risk_on": False,
            "reason": "qqq_sma_not_ready",
            "sma_window": MAGS7_REGIME_QQQ_SMA_WINDOW,
            "as_of": qqq_close.index.max().date().isoformat(),
            "ready_bars": int(len(qqq_close)),
        }

    row = ready_frame.iloc[-1]
    risk_on = bool(float(row["qqq_close"]) > float(row["qqq_sma"]))
    return {
        "name": MAGS7_REGIME_GATE_NAME,
        "ready": True,
        "risk_on": risk_on,
        "reason": f"qqq_above_sma{MAGS7_REGIME_QQQ_SMA_WINDOW}"
        if risk_on
        else f"qqq_below_sma{MAGS7_REGIME_QQQ_SMA_WINDOW}",
        "sma_window": MAGS7_REGIME_QQQ_SMA_WINDOW,
        "as_of": ready_frame.index[-1].date().isoformat(),
        "qqq_close": float(row["qqq_close"]),
        "qqq_sma": float(row["qqq_sma"]),
    }


def _cross_sectional_percentile_rank(row: pd.Series) -> pd.Series:
    valid = row.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=row.index)
    if len(valid) == 1:
        out = pd.Series(np.nan, index=row.index)
        out.loc[valid.index] = 0.5
        return out
    return (row.rank(method="average") - 1.0) / (valid.count() - 1.0)


def _mags7_momentum_overlay(
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None,
    allowed_underlyings: set[str],
) -> dict[str, Any]:
    symbols = tuple(symbol for symbol in _implemented_mags7_underlyings() if symbol in allowed_underlyings)
    if not symbols:
        return {
            "name": MAGS7_MOMENTUM_OVERLAY_NAME,
            "ready": True,
            "selected_underlyings": [],
            "scores": {},
            "reason": "no_eligible_mags7_underlyings",
        }

    close = pd.DataFrame(
        {
            symbol: _normalize_close_series(market_data[symbol], name=symbol)
            for symbol in symbols
            if symbol in market_data
        }
    ).sort_index()
    qqq_close = _normalize_close_series(market_data["QQQ"], name="QQQ")
    requested_as_of = _normalize_as_of(as_of, fallback=qqq_close.index.max())
    index = close.index.intersection(qqq_close.index)
    close = close.reindex(index).ffill().loc[:requested_as_of]
    qqq_close = qqq_close.reindex(index).ffill().loc[:requested_as_of]
    if close.empty:
        return {
            "name": MAGS7_MOMENTUM_OVERLAY_NAME,
            "ready": False,
            "selected_underlyings": [],
            "scores": {},
            "reason": "no_mags7_price_history",
            "top_n": MAGS7_MOMENTUM_OVERLAY_TOP_N,
        }

    stock_return = close.pct_change(fill_method=None)
    ret20 = close.pct_change(20)
    ret60 = close.pct_change(60)
    ret120 = close.pct_change(120)
    qqq_ret60 = qqq_close.pct_change(60)
    rv20 = stock_return.rolling(20).std() * np.sqrt(252.0)
    trend_sma = close.rolling(MAGS7_MOMENTUM_OVERLAY_TREND_SMA_WINDOW).mean()
    risk_adj60 = ret60 / rv20.replace(0.0, np.nan)
    relative60 = ret60.sub(qqq_ret60, axis=0)
    score = (
        0.30 * ret20.apply(_cross_sectional_percentile_rank, axis=1)
        + 0.30 * ret60.apply(_cross_sectional_percentile_rank, axis=1)
        + 0.20 * ret120.apply(_cross_sectional_percentile_rank, axis=1)
        + 0.10 * risk_adj60.apply(_cross_sectional_percentile_rank, axis=1)
        + 0.10 * relative60.apply(_cross_sectional_percentile_rank, axis=1)
    )
    eligible = (close > trend_sma) & (ret60 > 0.0) & (ret120 > 0.0)
    score = score.where(eligible)
    ready_score = score.dropna(how="all")
    if ready_score.empty:
        return {
            "name": MAGS7_MOMENTUM_OVERLAY_NAME,
            "ready": False,
            "selected_underlyings": [],
            "scores": {},
            "reason": "momentum_score_not_ready",
            "top_n": MAGS7_MOMENTUM_OVERLAY_TOP_N,
            "trend_sma_window": MAGS7_MOMENTUM_OVERLAY_TREND_SMA_WINDOW,
            "ready_bars": int(len(close)),
        }

    latest = ready_score.iloc[-1].dropna().sort_values(ascending=False)
    selected = tuple(latest.head(MAGS7_MOMENTUM_OVERLAY_TOP_N).index)
    return {
        "name": MAGS7_MOMENTUM_OVERLAY_NAME,
        "ready": True,
        "as_of": ready_score.index[-1].date().isoformat(),
        "top_n": MAGS7_MOMENTUM_OVERLAY_TOP_N,
        "trend_sma_window": MAGS7_MOMENTUM_OVERLAY_TREND_SMA_WINDOW,
        "selected_underlyings": list(selected),
        "scores": {symbol: float(value) for symbol, value in latest.items()},
        "criteria": {
            "trend": f"stock close > SMA{MAGS7_MOMENTUM_OVERLAY_TREND_SMA_WINDOW}",
            "momentum": "60d momentum > 0 and 120d momentum > 0",
            "score_weights": {
                "20d_momentum_rank": 0.30,
                "60d_momentum_rank": 0.30,
                "120d_momentum_rank": 0.20,
                "risk_adjusted_60d_momentum_rank": 0.10,
                "60d_relative_strength_vs_qqq_rank": 0.10,
            },
        },
    }


def _apply_mags7_regime_gate(
    signal: ToolChoiceAssetSignal,
    regime: dict[str, Any],
) -> ToolChoiceAssetSignal:
    diagnostics = dict(signal.diagnostics)
    diagnostics["mags7_regime_gate"] = regime
    if not bool(regime.get("ready")):
        diagnostics["mags7_regime_warning"] = "qqq_regime_not_ready"
    elif not bool(regime.get("risk_on")):
        diagnostics["mags7_regime_warning"] = "qqq_below_regime_sma"
    return ToolChoiceAssetSignal(
        **{
            **signal.__dict__,
            "diagnostics": diagnostics,
        }
    )


def _apply_mags7_momentum_overlay(
    signal: ToolChoiceAssetSignal,
    overlay: dict[str, Any],
) -> ToolChoiceAssetSignal:
    diagnostics = dict(signal.diagnostics)
    diagnostics["mags7_momentum_overlay"] = overlay
    if not _is_active_portfolio_signal(signal):
        return ToolChoiceAssetSignal(
            **{
                **signal.__dict__,
                "diagnostics": diagnostics,
            }
        )

    if not bool(overlay.get("ready")):
        selected = set()
    else:
        selected = set(overlay.get("selected_underlyings") or [])
    if signal.underlying_symbol in selected:
        return ToolChoiceAssetSignal(
            **{
                **signal.__dict__,
                "diagnostics": diagnostics,
            }
        )

    reasons = tuple(diagnostics.get("decision_reasons", ()))
    reason = "mags7_momentum_overlay_not_ready" if not overlay.get("ready") else "mags7_momentum_overlay_not_top3"
    diagnostics["decision_reasons"] = (*reasons, reason)
    diagnostics["pre_momentum_overlay_side"] = signal.side
    diagnostics["pre_momentum_overlay_target_symbol"] = signal.target_symbol
    diagnostics["pre_momentum_overlay_gross_exposure"] = signal.gross_exposure
    return ToolChoiceAssetSignal(
        group=signal.group,
        underlying_symbol=signal.underlying_symbol,
        as_of=signal.as_of,
        ready=bool(signal.ready and overlay.get("ready")),
        side="cash",
        target_symbol=None,
        tool=signal.tool,
        tool_label_zh=signal.tool_label_zh,
        tool_label_en=signal.tool_label_en,
        gross_exposure=0.0,
        diagnostics=diagnostics,
    )


def _tool_return(underlying_return: pd.Series, tool: str) -> pd.Series:
    if tool == "stock_long":
        return underlying_return
    if tool == "stock_short":
        return (-1.0 * underlying_return).clip(lower=-0.999999)
    if tool == "long2":
        return (2.0 * underlying_return).clip(lower=-0.999999)
    if tool == "short2":
        return (-2.0 * underlying_return).clip(lower=-0.999999)
    raise ValueError(f"Unsupported tool: {tool}")


def _build_route_frame(
    route: ToolChoiceRouteConfig,
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None,
) -> pd.DataFrame:
    underlying_close = _normalize_close_series(
        market_data[route.underlying_symbol],
        name=route.underlying_symbol,
    )
    qqq_close = _normalize_close_series(market_data["QQQ"], name="QQQ")
    index = underlying_close.index.intersection(qqq_close.index)
    frame = pd.DataFrame(index=index)
    frame["underlying_close"] = underlying_close.reindex(index)
    frame["underlying_return"] = frame["underlying_close"].pct_change(fill_method=None)
    frame["qqq_close"] = qqq_close.reindex(index)
    frame["underlying_sma"] = (
        frame["underlying_close"].rolling(int(route.sma_window)).mean()
        if route.sma_window is not None
        else np.nan
    )
    frame["underlying_momentum"] = (
        frame["underlying_close"].pct_change(int(route.momentum_lookback))
        if route.momentum_lookback is not None
        else np.nan
    )
    frame["underlying_momentum_20"] = frame["underlying_close"].pct_change(20)
    frame["underlying_momentum_60"] = frame["underlying_close"].pct_change(60)
    frame["qqq_momentum_20"] = frame["qqq_close"].pct_change(20)
    frame["qqq_momentum_60"] = frame["qqq_close"].pct_change(60)
    frame["underlying_ema_fast"] = (
        frame["underlying_close"].ewm(
            span=int(route.ema_fast_window),
            adjust=False,
            min_periods=int(route.ema_fast_window),
        ).mean()
        if route.ema_fast_window is not None
        else np.nan
    )
    frame["underlying_ema_slow"] = (
        frame["underlying_close"].ewm(
            span=int(route.ema_slow_window),
            adjust=False,
            min_periods=int(route.ema_slow_window),
        ).mean()
        if route.ema_slow_window is not None
        else np.nan
    )
    frame["underlying_rv20"] = frame["underlying_return"].rolling(20).std() * np.sqrt(252.0)
    frame["proxy_return"] = _tool_return(frame["underlying_return"], route.tool)
    frame["proxy_rv20_prev"] = frame["proxy_return"].rolling(20).std().shift(1) * np.sqrt(252.0)
    frame["instrument_close"] = np.nan
    frame["instrument_return"] = frame["proxy_return"]
    frame["instrument_rv20_prev"] = frame["proxy_rv20_prev"]
    frame["uses_actual_instrument"] = False

    if route.target_symbol in market_data:
        instrument_close = _normalize_close_series(
            market_data[route.target_symbol],
            name=route.target_symbol,
        ).reindex(index)
        instrument_return = instrument_close.pct_change(fill_method=None)
        instrument_rv = instrument_return.rolling(20).std().shift(1) * np.sqrt(252.0)
        frame["instrument_close"] = instrument_close.combine_first(frame["instrument_close"])
        frame["instrument_return"] = instrument_return.combine_first(frame["proxy_return"])
        frame["instrument_rv20_prev"] = instrument_rv.combine_first(frame["proxy_rv20_prev"])
        frame["uses_actual_instrument"] = instrument_close.notna()

    if route.qqq_sma_window is not None:
        frame["qqq_sma"] = frame["qqq_close"].rolling(route.qqq_sma_window).mean()
    else:
        frame["qqq_sma"] = np.nan

    if route.btc_sma_window is not None:
        btc_close = _normalize_close_series(market_data["BTC-USD"], name="BTC-USD")
        frame["btc_close_lagged"] = btc_close.shift(1).reindex(index).ffill()
        frame["btc_sma"] = frame["btc_close_lagged"].rolling(route.btc_sma_window).mean()
    else:
        frame["btc_close_lagged"] = np.nan
        frame["btc_sma"] = np.nan

    requested_as_of = pd.Timestamp(as_of).tz_localize(None).normalize() if as_of is not None else frame.index.max()
    return frame.loc[:requested_as_of].copy()


def _route_signal_on(route: ToolChoiceRouteConfig, row: pd.Series) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if route.sma_window is not None:
        if route.side == "long" and row["underlying_close"] <= row["underlying_sma"]:
            reasons.append("underlying_below_sma")
            return False, reasons
        if route.side == "short" and row["underlying_close"] >= row["underlying_sma"]:
            reasons.append("underlying_above_sma")
            return False, reasons
    if route.ema_fast_window is not None and route.ema_slow_window is not None:
        if route.side == "long" and row["underlying_ema_fast"] <= row["underlying_ema_slow"]:
            reasons.append("underlying_ema_not_bullish")
            return False, reasons
        if route.side == "short" and row["underlying_ema_fast"] >= row["underlying_ema_slow"]:
            reasons.append("underlying_ema_not_bearish")
            return False, reasons
    if route.momentum_lookback is not None and route.momentum_threshold is not None:
        if route.side == "long" and row["underlying_momentum"] <= route.momentum_threshold:
            reasons.append("momentum_below_threshold")
            return False, reasons
        if route.side == "short" and row["underlying_momentum"] >= route.momentum_threshold:
            reasons.append("momentum_above_short_threshold")
            return False, reasons
    if route.side not in {"long", "short"}:
        raise ValueError(f"Unsupported side: {route.side}")

    if route.qqq_sma_window is not None:
        if pd.isna(row["qqq_sma"]):
            reasons.append("qqq_sma_not_ready")
            return False, reasons
        if route.side == "long" and row["qqq_close"] <= row["qqq_sma"]:
            reasons.append("qqq_filter_blocked_long")
            return False, reasons
        if route.side == "short" and row["qqq_close"] >= row["qqq_sma"]:
            reasons.append("qqq_filter_blocked_short")
            return False, reasons

    if route.btc_sma_window is not None:
        if pd.isna(row["btc_sma"]):
            reasons.append("btc_sma_not_ready")
            return False, reasons
        if route.side == "long" and row["btc_close_lagged"] <= row["btc_sma"]:
            reasons.append("btc_filter_blocked_long")
            return False, reasons
        if route.side == "short" and row["btc_close_lagged"] >= row["btc_sma"]:
            reasons.append("btc_filter_blocked_short")
            return False, reasons

    if route.underlying_rv_cap is not None:
        if pd.isna(row["underlying_rv20"]) or row["underlying_rv20"] > route.underlying_rv_cap:
            reasons.append("underlying_rv_blocked")
            return False, reasons

    reasons.append(f"{route.underlying_symbol.lower()}_{route.side}_signal")
    return True, reasons


def _compute_route_signal(
    route: ToolChoiceRouteConfig,
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None,
) -> ToolChoiceAssetSignal:
    frame = _build_route_frame(route, market_data, as_of=as_of)
    required = [
        "underlying_close",
        "instrument_rv20_prev",
    ]
    if route.sma_window is not None:
        required.append("underlying_sma")
    if route.momentum_lookback is not None:
        required.append("underlying_momentum")
    if route.ema_fast_window is not None and route.ema_slow_window is not None:
        required.extend(["underlying_ema_fast", "underlying_ema_slow"])
    if route.qqq_sma_window is not None:
        required.append("qqq_sma")
    if route.btc_sma_window is not None:
        required.extend(["btc_close_lagged", "btc_sma"])
    ready_frame = frame.dropna(subset=required)
    if ready_frame.empty:
        as_of_ts = frame.index.max()
        return ToolChoiceAssetSignal(
            group=route.group,
            underlying_symbol=route.underlying_symbol,
            as_of=as_of_ts,
            ready=False,
            side="cash",
            target_symbol=None,
            tool=route.tool,
            tool_label_zh=route.tool_label_zh,
            tool_label_en=route.tool_label_en,
            gross_exposure=0.0,
            diagnostics={
                "reason": "insufficient_history",
                "route_config": asdict(route),
                "ready_bars": int(len(frame)),
            },
        )

    row = ready_frame.iloc[-1]
    signal_on, reasons = _route_signal_on(route, row)
    weight = 0.0
    if signal_on and pd.notna(row["instrument_rv20_prev"]) and float(row["instrument_rv20_prev"]) > 0:
        weight = max(0.0, min(route.max_weight, route.vol_target / float(row["instrument_rv20_prev"])))
    elif signal_on:
        reasons.append("instrument_rv_not_ready")

    side = route.side if weight > 0 else "cash"
    target_symbol = route.target_symbol if weight > 0 else None
    diagnostics = {
        "signal_source": DEFAULT_SIGNAL_SOURCE,
        "route_config": asdict(route),
        "decision_reasons": tuple(reasons),
        "target_symbol": route.target_symbol,
        "underlying_close": float(row["underlying_close"]),
        "underlying_sma": float(row["underlying_sma"]) if pd.notna(row["underlying_sma"]) else None,
        "underlying_momentum": float(row["underlying_momentum"]) if pd.notna(row["underlying_momentum"]) else None,
        "underlying_momentum_20": float(row["underlying_momentum_20"]) if pd.notna(row["underlying_momentum_20"]) else None,
        "underlying_momentum_60": float(row["underlying_momentum_60"]) if pd.notna(row["underlying_momentum_60"]) else None,
        "underlying_ema_fast": float(row["underlying_ema_fast"]) if pd.notna(row["underlying_ema_fast"]) else None,
        "underlying_ema_slow": float(row["underlying_ema_slow"]) if pd.notna(row["underlying_ema_slow"]) else None,
        "underlying_rv20": float(row["underlying_rv20"]) if pd.notna(row["underlying_rv20"]) else None,
        "instrument_rv20_prev": float(row["instrument_rv20_prev"]),
        "instrument_close": float(row["instrument_close"]) if pd.notna(row["instrument_close"]) else None,
        "uses_actual_instrument": bool(row["uses_actual_instrument"]),
        "vol_scale": float(weight),
        "qqq_close": float(row["qqq_close"]),
        "qqq_momentum_20": float(row["qqq_momentum_20"]) if pd.notna(row["qqq_momentum_20"]) else None,
        "qqq_momentum_60": float(row["qqq_momentum_60"]) if pd.notna(row["qqq_momentum_60"]) else None,
        "qqq_sma": float(row["qqq_sma"]) if pd.notna(row["qqq_sma"]) else None,
        "btc_close_lagged": float(row["btc_close_lagged"]) if pd.notna(row["btc_close_lagged"]) else None,
        "btc_sma": float(row["btc_sma"]) if pd.notna(row["btc_sma"]) else None,
    }
    return ToolChoiceAssetSignal(
        group=route.group,
        underlying_symbol=route.underlying_symbol,
        as_of=ready_frame.index[-1],
        ready=True,
        side=side,
        target_symbol=target_symbol,
        tool=route.tool,
        tool_label_zh=route.tool_label_zh,
        tool_label_en=route.tool_label_en,
        gross_exposure=float(weight),
        diagnostics=diagnostics,
    )


def _select_coin_signal(signals: list[ToolChoiceAssetSignal]) -> ToolChoiceAssetSignal:
    long_signal = next(signal for signal in signals if signal.underlying_symbol == "COIN" and signal.diagnostics["route_config"]["side"] == "long")
    short_signal = next(signal for signal in signals if signal.underlying_symbol == "COIN" and signal.diagnostics["route_config"]["side"] == "short")
    if long_signal.side == "long":
        return long_signal
    if short_signal.side == "short":
        return short_signal
    diagnostics = dict(long_signal.diagnostics)
    diagnostics["long_decision_reasons"] = long_signal.diagnostics.get("decision_reasons", ())
    diagnostics["short_decision_reasons"] = short_signal.diagnostics.get("decision_reasons", ())
    diagnostics["short_route_config"] = short_signal.diagnostics.get("route_config")
    return ToolChoiceAssetSignal(
        group=GROUP_CRYPTO_ZH,
        underlying_symbol="COIN",
        as_of=max(long_signal.as_of, short_signal.as_of),
        ready=bool(long_signal.ready and short_signal.ready),
        side="cash",
        target_symbol=None,
        tool="long2_or_short2",
        tool_label_zh="2x",
        tool_label_en="2x",
        gross_exposure=0.0,
        diagnostics=diagnostics,
    )


def _compute_coin_short_hold_asset_signal(
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None,
) -> ToolChoiceAssetSignal:
    config = GROUPED_COIN_SHORT_HOLD_CONFIG
    signal = compute_coin_short_hold_vt50_signal(
        market_data["COIN"],
        market_data["BTC-USD"],
        as_of=as_of,
        config=config,
        long_close=market_data.get(config.long_symbol),
        short_close=market_data.get(config.short_symbol),
    )
    diagnostics = dict(signal.diagnostics)
    strategy_config = dict(diagnostics.get("strategy_config") or {})
    route_config = {
        "group": GROUP_CRYPTO_ZH,
        "underlying_symbol": "COIN",
        "side": "dual",
        "tool": "long2_or_short2",
        "tool_label_zh": "2x",
        "tool_label_en": "2x",
        "target_symbol": signal.target_symbol,
        "vol_target": strategy_config.get("vol_target", config.vol_target),
        "sma_window": strategy_config.get("coin_sma", config.coin_sma),
        "momentum_lookback": strategy_config.get("momentum_lookback", config.momentum_lookback),
        "momentum_threshold": strategy_config.get("momentum_threshold", config.momentum_threshold),
        "btc_sma_window": strategy_config.get("btc_ma", config.btc_ma),
        "underlying_rv_cap": strategy_config.get("coin_rv_cap", config.coin_rv_cap),
        "max_hold_days": strategy_config.get("max_hold_days", config.max_hold_days),
        "take_profit": strategy_config.get("take_profit", config.take_profit),
        "position_sizing": strategy_config.get("position_sizing", config.position_sizing),
        "fixed_weight": strategy_config.get("fixed_weight", config.fixed_weight),
        "exit_reminder_trading_days": strategy_config.get(
            "exit_reminder_trading_days",
            config.exit_reminder_trading_days,
        ),
        "description": (
            f"COIN short-hold: SMA{config.coin_sma}, {config.momentum_lookback}d momentum "
            f"> +/-{config.momentum_threshold:.0%}, BTC MA{config.btc_ma}, RV20 < "
            f"{config.coin_rv_cap:.0%}, max hold {config.max_hold_days}d, TP "
            f"{config.take_profit:.0%}; CONL/CONI fixed {config.fixed_weight:.0%}."
        ),
        "recommendation_score": GROUPED_COIN_SHORT_HOLD_SCORE,
        "recommendation_bucket": RECOMMENDATION_BUCKET_CRYPTO_TACTICAL,
    }
    diagnostics.update(
        {
            "route_config": route_config,
            "decision_reasons": tuple(diagnostics.get("decision_reasons", ())),
            "target_symbol": signal.target_symbol or (config.long_symbol if signal.side == "long" else config.short_symbol if signal.side == "short" else None),
            "underlying_close": diagnostics.get("coin_close"),
            "underlying_sma": diagnostics.get("coin_sma"),
            "underlying_momentum": diagnostics.get("coin_momentum"),
            "underlying_rv20": diagnostics.get("coin_rv_20"),
            "instrument_rv20_prev": diagnostics.get("dual_rv_20_prev"),
            "btc_sma": diagnostics.get("btc_ma"),
            "uses_stateful_short_hold": True,
        }
    )
    tool = "long2" if signal.side == "long" else "short2" if signal.side == "short" else "long2_or_short2"
    return ToolChoiceAssetSignal(
        group=GROUP_CRYPTO_ZH,
        underlying_symbol="COIN",
        as_of=signal.as_of,
        ready=signal.ready,
        side=signal.side,
        target_symbol=signal.target_symbol,
        tool=tool,
        tool_label_zh="2x",
        tool_label_en="2x",
        gross_exposure=signal.gross_exposure,
        diagnostics=diagnostics,
    )


def compute_grouped_tool_choice_signal(
    market_data: dict[str, pd.Series],
    *,
    as_of: str | pd.Timestamp | None = None,
    groups: tuple[str, ...] | None = None,
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> GroupedToolChoiceSignal:
    requested_groups = set(groups or (GROUP_MAGS7, GROUP_CRYPTO_ZH))
    allowed_mags7_underlyings = set(_allowed_mags7_underlyings(mags7_universe))
    route_signals = [
        _compute_route_signal(route, market_data, as_of=as_of)
        for route in ROUTES
        if route.enabled
        and route.group in requested_groups
        and (route.group != GROUP_MAGS7 or route.underlying_symbol in allowed_mags7_underlyings)
        and not (route.group == GROUP_CRYPTO_ZH and route.underlying_symbol == "COIN")
    ]

    asset_signals: list[ToolChoiceAssetSignal] = []
    mags7_regime = None
    mags7_momentum_overlay = None
    if GROUP_MAGS7 in requested_groups:
        mags7_regime = _mags7_regime_gate(market_data, as_of=as_of)
        mags7_momentum_overlay = _mags7_momentum_overlay(
            market_data,
            as_of=as_of,
            allowed_underlyings=allowed_mags7_underlyings,
        )
    for group in (GROUP_MAGS7, GROUP_CRYPTO_ZH):
        if group not in requested_groups:
            continue
        if group == GROUP_CRYPTO_ZH:
            asset_signals.append(_compute_coin_short_hold_asset_signal(market_data, as_of=as_of))
            continue
        asset_signals.extend(
            _apply_mags7_momentum_overlay(
                _apply_mags7_regime_gate(signal, mags7_regime),
                mags7_momentum_overlay,
            )
            for signal in route_signals
            if signal.group == group
        )

    target_weights = _portfolio_target_weights(asset_signals)
    as_of_ts = max(
        (signal.as_of for signal in asset_signals),
        default=pd.Timestamp.now(tz="UTC").tz_localize(None).normalize(),
    )
    diagnostics = {
        "signal_source": DEFAULT_SIGNAL_SOURCE,
        "portfolio_policy": {
            "bucket_budgets": dict(RECOMMENDATION_BUCKET_BUDGETS),
            "same_underlying_rule": "prefer_tactical_leverage_over_core_stock",
            "ranking_mode": DYNAMIC_RANKING_MODE,
            "dynamic_strength_range": [DYNAMIC_STRENGTH_MIN, DYNAMIC_STRENGTH_MAX],
            "mags7_regime_gate": {
                "name": MAGS7_REGIME_GATE_NAME,
                "rule": f"QQQ close > SMA{MAGS7_REGIME_QQQ_SMA_WINDOW}",
                "bear_action": "diagnostic_only",
            },
            "mags7_momentum_overlay": {
                "name": MAGS7_MOMENTUM_OVERLAY_NAME,
                "top_n": MAGS7_MOMENTUM_OVERLAY_TOP_N,
                "rule": "only top-ranked MAGS7 underlyings may receive allocation",
            },
        },
        "disabled_short_routes": {
            "NVDA": "proxy_cagr_below_5pct",
            "MSFT": "proxy_cagr_below_5pct",
            "META": "proxy_cagr_below_5pct",
        },
        "mags7_universe_policy": _mags7_universe_policy(mags7_universe),
        "mags7_regime_gate": mags7_regime,
        "mags7_momentum_overlay": mags7_momentum_overlay,
    }
    return GroupedToolChoiceSignal(
        as_of=as_of_ts,
        effective_after_trading_days=1,
        ready=all(signal.ready for signal in asset_signals),
        asset_signals=tuple(asset_signals),
        target_weights=target_weights,
        diagnostics=diagnostics,
    )


def fetch_grouped_tool_choice_market_data(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    groups: tuple[str, ...] | None = None,
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> dict[str, pd.Series]:
    requested_groups = set(groups or (GROUP_MAGS7, GROUP_CRYPTO_ZH))
    as_of_ts = (
        pd.Timestamp(as_of).tz_localize(None).normalize()
        if as_of is not None
        else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    )
    start_ts = as_of_ts - pd.Timedelta(days=lookback_days)
    start = start_ts.date().isoformat()
    end = as_of_ts.date().isoformat()

    market_data: dict[str, pd.Series] = {
        "QQQ": download_nasdaq_close("QQQ", assetclass="etf", start=start, end=end),
    }
    if GROUP_MAGS7 in requested_groups:
        stock_starts = {
            symbol: max(pd.Timestamp(DEFAULT_NVDA_START), start_ts) if symbol == "NVDA" else start_ts
            for symbol in _allowed_mags7_underlyings(mags7_universe)
        }
        for symbol, symbol_start_ts in stock_starts.items():
            market_data[symbol] = download_nasdaq_close(
                symbol,
                assetclass="stocks",
                start=symbol_start_ts.date().isoformat(),
                end=end,
            )
        etf_symbols = tuple(
            dict.fromkeys(
                route.target_symbol
                for route in ROUTES
                if route.enabled
                and route.group == GROUP_MAGS7
                and route.underlying_symbol in stock_starts
                and route.target_symbol not in stock_starts
            )
        )
        for symbol in etf_symbols:
            listed_start_ts = MAGS7_ETF_STARTS.get(symbol, start_ts)
            market_data[symbol] = download_nasdaq_close(
                symbol,
                assetclass="etf",
                start=max(listed_start_ts, start_ts).date().isoformat(),
                end=end,
            )
    if GROUP_CRYPTO_ZH in requested_groups:
        coin_start = max(pd.Timestamp(DEFAULT_IPO_START), start_ts).date().isoformat()
        market_data["COIN"] = download_nasdaq_close("COIN", assetclass="stocks", start=coin_start, end=end)
        market_data["BTC-USD"] = download_coinbase_daily_close("BTC-USD", start=start, end=end)
        market_data["CONL"] = download_nasdaq_close(
            "CONL",
            assetclass="etf",
            start=max(pd.Timestamp(DEFAULT_CONL_START), start_ts).date().isoformat(),
            end=end,
        )
        market_data["CONI"] = download_nasdaq_close(
            "CONI",
            assetclass="etf",
            start=max(pd.Timestamp(DEFAULT_CONI_2X_START), start_ts).date().isoformat(),
            end=end,
        )
    return market_data


def compute_live_grouped_tool_choice_signal(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    groups: tuple[str, ...] | None = None,
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> GroupedToolChoiceSignal:
    market_data = fetch_grouped_tool_choice_market_data(
        as_of=as_of,
        lookback_days=lookback_days,
        groups=groups,
        mags7_universe=mags7_universe,
    )
    return compute_grouped_tool_choice_signal(
        market_data,
        as_of=as_of,
        groups=groups,
        mags7_universe=mags7_universe,
    )


def _display_group(group: str, *, lang: str) -> str:
    if group == GROUP_CRYPTO_ZH and lang != "zh":
        return GROUP_CRYPTO_EN
    return group


def _display_recommendation_bucket(bucket: str, *, lang: str) -> str:
    if lang == "zh":
        labels = {
            RECOMMENDATION_BUCKET_MAGS7_TACTICAL: "杠杆 / MAG7科技龙头",
            RECOMMENDATION_BUCKET_CRYPTO_TACTICAL: "杠杆 / 加密货币",
            RECOMMENDATION_BUCKET_CORE_STOCK: "正股长期动量",
        }
    else:
        labels = {
            RECOMMENDATION_BUCKET_MAGS7_TACTICAL: "Leverage / MAG7 tech leaders",
            RECOMMENDATION_BUCKET_CRYPTO_TACTICAL: "Leverage / crypto",
            RECOMMENDATION_BUCKET_CORE_STOCK: "Core stock momentum",
        }
    return labels.get(bucket, bucket)


def _format_compact_percent(value: float) -> str:
    pct = float(value) * 100.0
    if abs(pct - round(pct)) < 0.005:
        return f"{pct:.0f}%"
    return f"{pct:.2f}%"


def _unique_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _route_config(signal: ToolChoiceAssetSignal) -> dict[str, Any]:
    config = signal.diagnostics.get("route_config") or {}
    return dict(config) if isinstance(config, dict) else {}


def _recommendation_score(signal: ToolChoiceAssetSignal) -> float:
    score = _coerce_optional_float(_route_config(signal).get("recommendation_score"))
    if score is not None:
        return score
    short_config = signal.diagnostics.get("short_route_config") or {}
    if isinstance(short_config, dict):
        short_score = _coerce_optional_float(short_config.get("recommendation_score"))
        if short_score is not None:
            return short_score
    return 0.0


def _dynamic_metric_values(signal: ToolChoiceAssetSignal) -> dict[str, float]:
    if signal.group != GROUP_MAGS7:
        return {}

    metrics: dict[str, float] = {}
    underlying_momentum_20 = _coerce_optional_float(signal.diagnostics.get("underlying_momentum_20"))
    underlying_momentum_60 = _coerce_optional_float(signal.diagnostics.get("underlying_momentum_60"))
    qqq_momentum_20 = _coerce_optional_float(signal.diagnostics.get("qqq_momentum_20"))
    qqq_momentum_60 = _coerce_optional_float(signal.diagnostics.get("qqq_momentum_60"))
    if underlying_momentum_20 is not None and qqq_momentum_20 is not None:
        metrics["rs20"] = underlying_momentum_20 - qqq_momentum_20
    if underlying_momentum_60 is not None and qqq_momentum_60 is not None:
        metrics["rs60"] = underlying_momentum_60 - qqq_momentum_60

    underlying_rv20 = _coerce_optional_float(signal.diagnostics.get("underlying_rv20"))
    if underlying_momentum_60 is not None and underlying_rv20 is not None and underlying_rv20 > 0:
        metrics["risk_adj_mom60"] = underlying_momentum_60 / underlying_rv20

    close = _coerce_optional_float(signal.diagnostics.get("underlying_close"))
    sma = _coerce_optional_float(signal.diagnostics.get("underlying_sma"))
    if close is not None and sma is not None and sma > 0:
        metrics["trend_distance"] = close / sma - 1.0
        return metrics

    ema_fast = _coerce_optional_float(signal.diagnostics.get("underlying_ema_fast"))
    ema_slow = _coerce_optional_float(signal.diagnostics.get("underlying_ema_slow"))
    if ema_fast is not None and ema_slow is not None and ema_slow > 0:
        metrics["trend_distance"] = ema_fast / ema_slow - 1.0
    return metrics


def _percentile_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [0.5]
    ranked = pd.Series(values, dtype=float).rank(method="average")
    return ((ranked - 1.0) / (len(values) - 1.0)).tolist()


def _dynamic_strength_by_id(signals: list[ToolChoiceAssetSignal]) -> dict[int, float]:
    active_signals = [signal for signal in signals if _is_active_portfolio_signal(signal)]
    strengths = {id(signal): 1.0 for signal in signals}
    metric_names = ("rs20", "rs60", "risk_adj_mom60", "trend_distance")
    percentile_by_metric: dict[str, dict[int, float]] = {}

    for metric_name in metric_names:
        present = [
            (signal, metrics[metric_name])
            for signal in active_signals
            if (metrics := _dynamic_metric_values(signal))
            and metric_name in metrics
            and np.isfinite(metrics[metric_name])
        ]
        if not present:
            continue
        percentiles = _percentile_scores([value for _, value in present])
        percentile_by_metric[metric_name] = {
            id(signal): percentile
            for (signal, _value), percentile in zip(present, percentiles, strict=True)
        }

    for signal in active_signals:
        values = [
            percentiles[id(signal)]
            for percentiles in percentile_by_metric.values()
            if id(signal) in percentiles
        ]
        if not values:
            continue
        percentile = sum(values) / len(values)
        strengths[id(signal)] = max(
            DYNAMIC_STRENGTH_MIN,
            min(DYNAMIC_STRENGTH_MAX, DYNAMIC_STRENGTH_MIN + percentile),
        )
    return strengths


def _dynamic_ranking_score(
    signal: ToolChoiceAssetSignal,
    bucket_context: list[ToolChoiceAssetSignal],
) -> float:
    base_score = max(0.0, _recommendation_score(signal))
    if base_score <= 0:
        return 0.0
    strength = _dynamic_strength_by_id(bucket_context).get(id(signal), 1.0)
    return (base_score ** 0.5) * strength


def _recommendation_bucket(signal: ToolChoiceAssetSignal) -> str:
    bucket = str(_route_config(signal).get("recommendation_bucket") or "").strip()
    if bucket:
        return bucket
    if signal.group == GROUP_CRYPTO_ZH:
        return RECOMMENDATION_BUCKET_CRYPTO_TACTICAL
    if signal.tool == "stock_long":
        return RECOMMENDATION_BUCKET_CORE_STOCK
    return RECOMMENDATION_BUCKET_MAGS7_TACTICAL


def _ranked_bucket_signals(
    bucket_signals: list[ToolChoiceAssetSignal],
) -> list[tuple[int, ToolChoiceAssetSignal]]:
    indexed = list(enumerate(bucket_signals))
    active_context = [signal for signal in bucket_signals if _is_active_portfolio_signal(signal)]
    indexed.sort(
        key=lambda item: (
            -_dynamic_ranking_score(item[1], active_context),
            -_recommendation_score(item[1]),
            str(item[1].underlying_symbol),
            item[0],
        )
    )
    return [(rank, signal) for rank, (_, signal) in enumerate(indexed, start=1)]


def _grouped_ranked_signals(
    signal: GroupedToolChoiceSignal,
) -> list[tuple[int, ToolChoiceAssetSignal]]:
    ranked: list[tuple[int, ToolChoiceAssetSignal]] = []
    for bucket in ORDERED_RECOMMENDATION_BUCKETS:
        bucket_signals = [
            asset for asset in signal.asset_signals if _recommendation_bucket(asset) == bucket
        ]
        ranked.extend(_ranked_bucket_signals(bucket_signals))
    return ranked


def _should_show_in_notification(signal: ToolChoiceAssetSignal) -> bool:
    if signal.side != "cash" or signal.gross_exposure > 0:
        return True
    if not signal.diagnostics.get("uses_stateful_short_hold"):
        return False
    previous_side = str(signal.diagnostics.get("previous_side") or "cash")
    reasons = tuple(signal.diagnostics.get("decision_reasons", ()))
    if previous_side in {"long", "short"} or "take_profit_exit" in reasons or "max_hold_exit" in reasons:
        return True
    days_since_exit = signal.diagnostics.get("trading_days_since_exit")
    reminder_days = signal.diagnostics.get("exit_reminder_trading_days")
    try:
        return (
            days_since_exit is not None
            and reminder_days is not None
            and int(days_since_exit) <= int(reminder_days)
            and signal.diagnostics.get("last_exit_reason") is not None
        )
    except (TypeError, ValueError):
        return False


def _is_active_portfolio_signal(signal: ToolChoiceAssetSignal) -> bool:
    return bool(signal.side in {"long", "short"} and signal.target_symbol and signal.gross_exposure > 0)


def _portfolio_excluded_reason(
    signal: ToolChoiceAssetSignal,
    all_signals: list[ToolChoiceAssetSignal],
) -> str | None:
    if not _is_active_portfolio_signal(signal):
        return None
    if _recommendation_bucket(signal) != RECOMMENDATION_BUCKET_CORE_STOCK:
        return None
    active_tactical_underlyings = {
        item.underlying_symbol
        for item in all_signals
        if _is_active_portfolio_signal(item)
        and _recommendation_bucket(item) != RECOMMENDATION_BUCKET_CORE_STOCK
    }
    if signal.underlying_symbol in active_tactical_underlyings:
        return "same_underlying_tactical_active"
    return None


def _allocation_hints(signals: list[ToolChoiceAssetSignal]) -> list[float]:
    positive_scores = [max(0.0, _dynamic_ranking_score(signal, signals)) for signal in signals]
    total_score = sum(positive_scores)
    if total_score > 0:
        return [score / total_score for score in positive_scores]
    if not signals:
        return []
    equal = 1.0 / len(signals)
    return [equal for _ in signals]


def _portfolio_allocation_plan(
    signals: list[ToolChoiceAssetSignal] | tuple[ToolChoiceAssetSignal, ...],
) -> dict[int, dict[str, Any]]:
    signal_list = list(signals)
    plan: dict[int, dict[str, Any]] = {}
    for item in signal_list:
        excluded_reason = _portfolio_excluded_reason(item, signal_list)
        if excluded_reason:
            plan[id(item)] = {
                "bucket_budget": RECOMMENDATION_BUCKET_BUDGETS.get(_recommendation_bucket(item), 0.0),
                "sleeve_allocation": 0.0,
                "account_allocation": 0.0,
                "dynamic_strength": 1.0,
                "dynamic_score": 0.0,
                "excluded_reason": excluded_reason,
            }

    for bucket in ORDERED_RECOMMENDATION_BUCKETS:
        active_bucket_signals = [
            item
            for item in signal_list
            if _recommendation_bucket(item) == bucket
            and _is_active_portfolio_signal(item)
            and _portfolio_excluded_reason(item, signal_list) is None
        ]
        ranked_signals = _ranked_bucket_signals(active_bucket_signals)
        ranked_assets = [item for _, item in ranked_signals]
        sleeve_allocations = _allocation_hints(ranked_assets)
        bucket_budget = RECOMMENDATION_BUCKET_BUDGETS.get(bucket, 0.0)
        dynamic_strengths = _dynamic_strength_by_id(ranked_assets)
        for asset, sleeve_allocation in zip(ranked_assets, sleeve_allocations, strict=True):
            sleeve_target = max(0.0, bucket_budget) * max(0.0, sleeve_allocation)
            strategy_cap = max(0.0, float(asset.gross_exposure))
            account_allocation = min(sleeve_target, strategy_cap)
            dynamic_strength = dynamic_strengths.get(id(asset), 1.0)
            dynamic_score = _dynamic_ranking_score(asset, ranked_assets)
            plan[id(asset)] = {
                "bucket_budget": bucket_budget,
                "sleeve_allocation": sleeve_allocation,
                "account_allocation": account_allocation,
                "dynamic_strength": dynamic_strength,
                "dynamic_score": dynamic_score,
                "excluded_reason": None,
            }
    return plan


def _format_no_allocation_bucket_summary(
    bucket: str,
    bucket_signals: list[ToolChoiceAssetSignal],
    allocation_plan: dict[int, dict[str, Any]],
    *,
    lang: str,
) -> str | None:
    if bucket != RECOMMENDATION_BUCKET_CORE_STOCK:
        return None

    ranked_assets = [asset for _, asset in _ranked_bucket_signals(bucket_signals)]
    replaced_symbols = _unique_symbols(
        [
            asset.underlying_symbol
            for asset in ranked_assets
            if allocation_plan.get(id(asset), {}).get("excluded_reason") == "same_underlying_tactical_active"
        ]
    )
    if not replaced_symbols:
        return None

    has_inactive_routes = any(not _is_active_portfolio_signal(asset) for asset in bucket_signals)
    replaced_text = "/".join(replaced_symbols)
    if lang == "zh":
        if has_inactive_routes:
            return f"本轮无账户建议：{replaced_text} 已由同标的杠杆替代，其他正股未触发"
        return f"本轮无账户建议：{replaced_text} 已由同标的杠杆替代"
    verb = "are" if len(replaced_symbols) > 1 else "is"
    if has_inactive_routes:
        return (
            f"No account allocation this cycle: {replaced_text} {verb} replaced by same-underlying "
            "leverage; other stock routes are inactive"
        )
    return f"No account allocation this cycle: {replaced_text} {verb} replaced by same-underlying leverage"


def _portfolio_target_weights(
    signals: list[ToolChoiceAssetSignal] | tuple[ToolChoiceAssetSignal, ...],
) -> dict[str, float]:
    signal_list = list(signals)
    plan = _portfolio_allocation_plan(signal_list)
    target_weights: dict[str, float] = {}
    for asset in signal_list:
        if not asset.target_symbol:
            continue
        account_allocation = _coerce_optional_float(plan.get(id(asset), {}).get("account_allocation"))
        if account_allocation is None or account_allocation <= 0:
            continue
        target_weights[asset.target_symbol] = target_weights.get(asset.target_symbol, 0.0) + account_allocation
    return target_weights


def _format_asset_line(
    signal: ToolChoiceAssetSignal,
    *,
    lang: str,
    rank: int | None = None,
    allocation_hint: float | None = None,
    account_allocation: float | None = None,
    dynamic_strength: float | None = None,
    dynamic_score: float | None = None,
    reference_capital_usd: float | None = None,
) -> str:
    config = _route_config(signal)
    score = _coerce_optional_float(config.get("recommendation_score"))
    indicator = _format_asset_indicator(signal, lang=lang)
    stateful_status = _format_stateful_short_hold_status(signal, lang=lang)
    if lang == "zh":
        action = {"long": "做多", "short": "做空", "cash": "空仓"}.get(signal.side, "空仓")
        parts = [f"{signal.underlying_symbol}: {action}", signal.tool_label_zh, f"仓位 {signal.gross_exposure:.2%}"]
        if rank is not None:
            parts.insert(1, f"推荐#{rank}")
        if score is not None:
            parts.append(f"基础分 {score:.2f}")
        if dynamic_score is not None:
            dynamic_text = f"动态分 {dynamic_score:.2f}"
            if dynamic_strength is not None:
                dynamic_text += f" / 强度 {dynamic_strength:.2f}x"
            parts.append(dynamic_text)
        if allocation_hint is not None:
            parts.append(f"组内分配 {allocation_hint:.2%}")
        if account_allocation is not None:
            account_text = f"账户建议 {account_allocation:.2%}"
            if reference_capital_usd is not None:
                account_text += f" (${account_allocation * reference_capital_usd:,.0f})"
            parts.append(account_text)
        if indicator:
            parts.append(indicator)
        if stateful_status:
            parts.append(stateful_status)
        return " / ".join(parts)
    action = {"long": "long", "short": "short", "cash": "cash"}.get(signal.side, "cash")
    parts = [f"{signal.underlying_symbol}: {action}", signal.tool_label_en, f"position {signal.gross_exposure:.2%}"]
    if rank is not None:
        parts.insert(1, f"rec #{rank}")
    if score is not None:
        parts.append(f"base score {score:.2f}")
    if dynamic_score is not None:
        dynamic_text = f"dynamic score {dynamic_score:.2f}"
        if dynamic_strength is not None:
            dynamic_text += f" / strength {dynamic_strength:.2f}x"
        parts.append(dynamic_text)
    if allocation_hint is not None:
        parts.append(f"sleeve allocation {allocation_hint:.2%}")
    if account_allocation is not None:
        account_text = f"account allocation {account_allocation:.2%}"
        if reference_capital_usd is not None:
            account_text += f" (${account_allocation * reference_capital_usd:,.0f})"
        parts.append(account_text)
    if indicator:
        parts.append(indicator)
    if stateful_status:
        parts.append(stateful_status)
    return " / ".join(parts)


def build_grouped_tool_choice_notification(
    signal: GroupedToolChoiceSignal,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    sections: list[str] = []
    allocation_plan = _portfolio_allocation_plan(signal.asset_signals)
    for bucket in ORDERED_RECOMMENDATION_BUCKETS:
        all_bucket_signals = [
            asset
            for asset in signal.asset_signals
            if _recommendation_bucket(asset) == bucket
        ]
        bucket_label = _display_recommendation_bucket(bucket, lang=lang)
        bucket_budget = RECOMMENDATION_BUCKET_BUDGETS.get(bucket, 0.0)
        header = (
            f"【{bucket_label}】资金池 {_format_compact_percent(bucket_budget)}"
            if lang == "zh"
            else f"[{bucket_label}] sleeve {_format_compact_percent(bucket_budget)}"
        )
        bucket_signals = [
            asset
            for asset in all_bucket_signals
            if _should_show_in_notification(asset)
            and allocation_plan.get(id(asset), {}).get("excluded_reason") is None
        ]
        if not bucket_signals:
            no_allocation_summary = _format_no_allocation_bucket_summary(
                bucket,
                all_bucket_signals,
                allocation_plan,
                lang=lang,
            )
            if no_allocation_summary:
                sections.append("\n".join([header, no_allocation_summary]))
            continue
        ranked_signals = _ranked_bucket_signals(bucket_signals)
        sections.append(
            "\n".join(
                [
                    header,
                    *[
                        _format_asset_line(
                            asset,
                            lang=lang,
                            rank=rank,
                            allocation_hint=allocation_plan.get(id(asset), {}).get("sleeve_allocation"),
                            account_allocation=allocation_plan.get(id(asset), {}).get("account_allocation"),
                            dynamic_strength=allocation_plan.get(id(asset), {}).get("dynamic_strength"),
                            dynamic_score=allocation_plan.get(id(asset), {}).get("dynamic_score"),
                            reference_capital_usd=reference_capital_usd,
                        )
                        for rank, asset in ranked_signals
                    ],
                ]
            )
        )
    if sections:
        return "\n\n".join(sections)
    return "今日无持仓信号" if lang == "zh" else "No active signals today"


def _format_optional_percent(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2%}"


def _format_optional_number(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _format_stateful_short_hold_status(signal: ToolChoiceAssetSignal, *, lang: str) -> str | None:
    if not signal.diagnostics.get("uses_stateful_short_hold"):
        return None
    previous_side = str(signal.diagnostics.get("previous_side") or "cash")
    reasons = tuple(signal.diagnostics.get("decision_reasons", ()))
    held_days = int(signal.diagnostics.get("held_days") or 0)
    entry_price = _coerce_optional_float(signal.diagnostics.get("entry_reference_price"))
    if signal.side in {"long", "short"}:
        if previous_side != signal.side or held_days == 0:
            status = "新开仓" if lang == "zh" else "new entry"
        else:
            status = f"持有第{held_days}天" if lang == "zh" else f"held {held_days}d"
        if entry_price is not None:
            suffix = f"参考入场 {entry_price:.2f}" if lang == "zh" else f"entry ref {entry_price:.2f}"
            return f"{status} / {suffix}"
        return status
    if "take_profit_exit" in reasons:
        return "止盈退出" if lang == "zh" else "take-profit exit"
    if "max_hold_exit" in reasons:
        return "到期退出" if lang == "zh" else "max-hold exit"
    days_since_exit = signal.diagnostics.get("trading_days_since_exit")
    reminder_days = signal.diagnostics.get("exit_reminder_trading_days")
    last_exit_reason = str(signal.diagnostics.get("last_exit_reason") or "")
    try:
        recent_exit = (
            days_since_exit is not None
            and reminder_days is not None
            and int(days_since_exit) <= int(reminder_days)
            and last_exit_reason
        )
    except (TypeError, ValueError):
        recent_exit = False
    if recent_exit:
        days = int(days_since_exit)
        if last_exit_reason == "take_profit_exit":
            reason = "止盈退出" if lang == "zh" else "take-profit exit"
        elif last_exit_reason == "max_hold_exit":
            reason = "到期退出" if lang == "zh" else "max-hold exit"
        else:
            reason = "信号退出" if lang == "zh" else "signal exit"
        if days == 0:
            return reason
        return f"{reason}后第{days}天" if lang == "zh" else f"{reason} {days}d ago"
    if previous_side in {"long", "short"}:
        return "退出/不同步先看日志" if lang == "zh" else "exit/check log"
    return "等待新触发" if lang == "zh" else "waiting for trigger"


def _format_asset_indicator(signal: ToolChoiceAssetSignal, *, lang: str) -> str | None:
    config = _route_config(signal)
    momentum_lookback = _coerce_optional_float(config.get("momentum_lookback"))
    momentum = _coerce_optional_float(signal.diagnostics.get("underlying_momentum"))
    if momentum is not None and momentum_lookback is not None:
        if lang == "zh":
            return f"{int(momentum_lookback)}日动量 {momentum:.2%}"
        return f"mom{int(momentum_lookback)} {momentum:.2%}"

    ema_fast_window = _coerce_optional_float(config.get("ema_fast_window"))
    ema_slow_window = _coerce_optional_float(config.get("ema_slow_window"))
    ema_fast = _coerce_optional_float(signal.diagnostics.get("underlying_ema_fast"))
    ema_slow = _coerce_optional_float(signal.diagnostics.get("underlying_ema_slow"))
    if (
        ema_fast_window is not None
        and ema_slow_window is not None
        and ema_fast is not None
        and ema_slow is not None
    ):
        return f"EMA{int(ema_fast_window)}/{int(ema_slow_window)} {ema_fast:.2f}/{ema_slow:.2f}"

    sma_window = _coerce_optional_float(config.get("sma_window"))
    sma = _coerce_optional_float(signal.diagnostics.get("underlying_sma"))
    if sma_window is not None and sma is not None:
        return f"SMA{int(sma_window)} {sma:.2f}"
    return None


def _indicator_log_lines(asset: ToolChoiceAssetSignal, *, lang: str) -> list[str]:
    config = _route_config(asset)
    lines: list[str] = []
    close = asset.diagnostics.get("underlying_close")

    sma_window = config.get("sma_window")
    if sma_window is not None:
        if lang == "zh":
            lines.append(
                f"收盘/SMA{sma_window}: {_format_optional_number(close)} / "
                f"{_format_optional_number(asset.diagnostics.get('underlying_sma'))}"
            )
        else:
            lines.append(
                f"close/SMA{sma_window}: {_format_optional_number(close)} / "
                f"{_format_optional_number(asset.diagnostics.get('underlying_sma'))}"
            )

    ema_fast_window = config.get("ema_fast_window")
    ema_slow_window = config.get("ema_slow_window")
    if ema_fast_window is not None and ema_slow_window is not None:
        lines.append(
            f"EMA{ema_fast_window}/{ema_slow_window}: "
            f"{_format_optional_number(asset.diagnostics.get('underlying_ema_fast'))} / "
            f"{_format_optional_number(asset.diagnostics.get('underlying_ema_slow'))}"
        )

    momentum_lookback = config.get("momentum_lookback")
    if momentum_lookback is not None:
        momentum = _format_optional_percent(asset.diagnostics.get("underlying_momentum"))
        if lang == "zh":
            lines.append(f"{momentum_lookback}日动量: {momentum}")
        else:
            lines.append(f"momentum{momentum_lookback}: {momentum}")
    return lines


def build_grouped_tool_choice_log(
    signal: GroupedToolChoiceSignal,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    if lang != "zh":
        lines = [
            DEFAULT_STRATEGY_DISPLAY_NAME_EN,
            f"date: {signal.as_of.date().isoformat()}",
            f"ready: {signal.ready}",
        ]
        allocation_plan = _portfolio_allocation_plan(signal.asset_signals)
        for rank, asset in _grouped_ranked_signals(signal):
            config = asset.diagnostics.get("route_config") or {}
            bucket_label = _display_recommendation_bucket(_recommendation_bucket(asset), lang=lang)
            portfolio_plan = allocation_plan.get(id(asset), {})
            excluded_reason = portfolio_plan.get("excluded_reason")
            lines.extend(
                [
                    "",
                    f"{bucket_label} / rec #{rank} {asset.underlying_symbol}",
                    f"asset group: {_display_group(asset.group, lang=lang)}",
                    f"target: {asset.target_symbol or 'CASH'} / {asset.side} / {asset.gross_exposure:.2%}",
                    f"base score: {_recommendation_score(asset):.2f}",
                    f"dynamic score: {portfolio_plan.get('dynamic_score', 0.0):.2f}",
                    f"dynamic strength: {portfolio_plan.get('dynamic_strength', 1.0):.2f}x",
                    f"sleeve budget: {portfolio_plan.get('bucket_budget', RECOMMENDATION_BUCKET_BUDGETS.get(_recommendation_bucket(asset), 0.0)):.2%}",
                    f"sleeve allocation: {portfolio_plan.get('sleeve_allocation', 0.0):.2%}",
                    f"account allocation: {portfolio_plan.get('account_allocation', 0.0):.2%}",
                    f"tool: {asset.tool_label_en}",
                    f"rule: {config.get('description') or config.get('side')}",
                    *_indicator_log_lines(asset, lang=lang),
                    f"instrument RV20(prev): {asset.diagnostics.get('instrument_rv20_prev', 0.0):.2%}",
                    f"reasons: {', '.join(asset.diagnostics.get('decision_reasons', ())) }",
                ]
            )
            if excluded_reason == "same_underlying_tactical_active":
                lines.append("portfolio status: skipped because tactical leverage is active for the same underlying")
        return "\n".join(lines)

    lines = [
        DEFAULT_STRATEGY_DISPLAY_NAME_ZH,
        f"日期: {signal.as_of.date().isoformat()}",
        f"ready: {signal.ready}",
    ]
    allocation_plan = _portfolio_allocation_plan(signal.asset_signals)
    for rank, asset in _grouped_ranked_signals(signal):
        config = asset.diagnostics.get("route_config") or {}
        qqq_sma_window = config.get("qqq_sma_window")
        btc_sma_window = config.get("btc_sma_window")
        bucket_label = _display_recommendation_bucket(_recommendation_bucket(asset), lang=lang)
        portfolio_plan = allocation_plan.get(id(asset), {})
        excluded_reason = portfolio_plan.get("excluded_reason")
        lines.extend(
            [
                "",
                f"{bucket_label} / 推荐#{rank} {asset.underlying_symbol}",
                f"资产组: {_display_group(asset.group, lang=lang)}",
                f"目标: {asset.target_symbol or 'CASH'} / {asset.side} / {asset.gross_exposure:.2%}",
                f"基础分: {_recommendation_score(asset):.2f}",
                f"动态分: {portfolio_plan.get('dynamic_score', 0.0):.2f}",
                f"动态强度: {portfolio_plan.get('dynamic_strength', 1.0):.2f}x",
                f"资金池: {portfolio_plan.get('bucket_budget', RECOMMENDATION_BUCKET_BUDGETS.get(_recommendation_bucket(asset), 0.0)):.2%}",
                f"组内分配: {portfolio_plan.get('sleeve_allocation', 0.0):.2%}",
                f"账户建议: {portfolio_plan.get('account_allocation', 0.0):.2%}",
                f"工具: {asset.tool_label_zh}",
                f"规则: {config.get('description') or config.get('side')}",
                *_indicator_log_lines(asset, lang=lang),
                f"标的RV20: {_format_optional_percent(asset.diagnostics.get('underlying_rv20'))}",
                f"工具RV20(前值): {asset.diagnostics.get('instrument_rv20_prev', 0.0):.2%}",
                f"vol scale: {asset.diagnostics.get('vol_scale', 0.0):.2%}",
            ]
        )
        if qqq_sma_window:
            lines.append(
                f"QQQ/SMA{qqq_sma_window}: {asset.diagnostics.get('qqq_close', 0.0):.2f} / "
                f"{asset.diagnostics.get('qqq_sma', 0.0):.2f}"
            )
        if btc_sma_window:
            lines.append(
                f"BTC(滞后1日)/SMA{btc_sma_window}: {asset.diagnostics.get('btc_close_lagged', 0.0):.2f} / "
                f"{asset.diagnostics.get('btc_sma', 0.0):.2f}"
            )
        if (
            asset.underlying_symbol == "COIN"
            and asset.side == "cash"
            and (
                "long_decision_reasons" in asset.diagnostics
                or "short_decision_reasons" in asset.diagnostics
            )
        ):
            lines.append(f"做多原因: {', '.join(asset.diagnostics.get('long_decision_reasons', ())) }")
            lines.append(f"做空原因: {', '.join(asset.diagnostics.get('short_decision_reasons', ())) }")
        else:
            lines.append(f"原因: {', '.join(asset.diagnostics.get('decision_reasons', ())) }")
        if excluded_reason == "same_underlying_tactical_active":
            lines.append("组合状态: 同标的杠杆信号已触发，正股不重复持有")
    return "\n".join(lines)


def build_grouped_tool_choice_snapshot(signal: GroupedToolChoiceSignal) -> dict[str, Any]:
    allocation_plan = _portfolio_allocation_plan(signal.asset_signals)
    return {
        "strategy_name": DEFAULT_STRATEGY_NAME,
        "strategy_display_name_zh": DEFAULT_STRATEGY_DISPLAY_NAME_ZH,
        "strategy_display_name_en": DEFAULT_STRATEGY_DISPLAY_NAME_EN,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "as_of": signal.as_of.date().isoformat(),
        "effective_after_trading_days": signal.effective_after_trading_days,
        "ready": bool(signal.ready),
        "target_weights": dict(signal.target_weights),
        "bucket_budgets": dict(RECOMMENDATION_BUCKET_BUDGETS),
        "ranking_mode": DYNAMIC_RANKING_MODE,
        "asset_signals": [
            {
                "group": asset.group,
                "underlying_symbol": asset.underlying_symbol,
                "recommendation_rank": int(rank),
                "recommendation_score": float(_recommendation_score(asset)),
                "recommendation_bucket": _recommendation_bucket(asset),
                "dynamic_strength": float(allocation_plan.get(id(asset), {}).get("dynamic_strength", 1.0)),
                "dynamic_score": float(allocation_plan.get(id(asset), {}).get("dynamic_score", 0.0)),
                "sleeve_allocation": float(allocation_plan.get(id(asset), {}).get("sleeve_allocation", 0.0)),
                "account_allocation": float(allocation_plan.get(id(asset), {}).get("account_allocation", 0.0)),
                "portfolio_excluded_reason": allocation_plan.get(id(asset), {}).get("excluded_reason"),
                "as_of": asset.as_of.date().isoformat(),
                "ready": bool(asset.ready),
                "side": asset.side,
                "target_symbol": asset.target_symbol,
                "tool": asset.tool,
                "tool_label_zh": asset.tool_label_zh,
                "tool_label_en": asset.tool_label_en,
                "gross_exposure": float(asset.gross_exposure),
                "diagnostics": dict(asset.diagnostics),
            }
            for rank, asset in _grouped_ranked_signals(signal)
        ],
        "diagnostics": dict(signal.diagnostics),
    }


def read_grouped_tool_choice_snapshot(snapshot_path: str) -> dict[str, Any] | None:
    return read_json_snapshot(snapshot_path)


def _notification_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "as_of": snapshot.get("as_of"),
        "ready": bool(snapshot.get("ready")),
        "target_weights": [
            [str(symbol), round(float(weight or 0.0), 6)]
            for symbol, weight in sorted(dict(snapshot.get("target_weights") or {}).items())
        ],
        "bucket_budgets": [
            [str(bucket), round(float(weight or 0.0), 6)]
            for bucket, weight in sorted(dict(snapshot.get("bucket_budgets") or {}).items())
        ],
        "ranking_mode": snapshot.get("ranking_mode"),
        "asset_signals": [
            {
                "group": item.get("group"),
                "underlying_symbol": item.get("underlying_symbol"),
                "recommendation_rank": int(item.get("recommendation_rank") or 0),
                "recommendation_score": round(float(item.get("recommendation_score") or 0.0), 4),
                "recommendation_bucket": item.get("recommendation_bucket"),
                "dynamic_strength": round(float(item.get("dynamic_strength") or 1.0), 6),
                "dynamic_score": round(float(item.get("dynamic_score") or 0.0), 6),
                "sleeve_allocation": round(float(item.get("sleeve_allocation") or 0.0), 6),
                "account_allocation": round(float(item.get("account_allocation") or 0.0), 6),
                "portfolio_excluded_reason": item.get("portfolio_excluded_reason"),
                "side": item.get("side"),
                "target_symbol": item.get("target_symbol"),
                "tool": item.get("tool"),
                "gross_exposure": round(float(item.get("gross_exposure") or 0.0), 6),
                "ready": bool(item.get("ready")),
            }
            for item in snapshot.get("asset_signals", [])
        ],
    }


def should_send_grouped_tool_choice_notification(
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
) -> bool:
    if previous_snapshot is None:
        return True
    return _notification_identity(snapshot) != _notification_identity(previous_snapshot)


def write_grouped_tool_choice_snapshot(snapshot: dict[str, Any], output_path: str) -> str:
    return write_json_snapshot(snapshot, output_path)


def send_grouped_tool_choice_telegram_message(
    message: str,
    *,
    token: str,
    chat_id: str,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> None:
    send_telegram_message(message, token=token, chat_id=chat_id, timeout=timeout)
