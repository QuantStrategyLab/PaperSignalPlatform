#!/usr/bin/env python3
"""Search fast COIN burst routes for CONL/CONI.

The grouped notifier is intentionally conservative. This research script keeps
the short-hold COIN route family available for follow-up experiments that enter
only after fast momentum or breakout triggers, then exit quickly on max-hold,
take-profit, stop-loss, or signal reversal.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backtest_coin_conl_coni_filters import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_RESULTS_DIR,
    format_percent,
    frame_to_markdown_table,
)
from signal_notifier.coin_short_hold_notify import (  # noqa: E402
    DEFAULT_CONL_START,
    DEFAULT_IPO_START,
    download_coinbase_daily_close,
    download_nasdaq_close,
)


DEFAULT_COIN_START = DEFAULT_IPO_START
DEFAULT_SYNTHETIC_START = DEFAULT_CONL_START
DEFAULT_ACTUAL_START = "2024-09-01"


@dataclass(frozen=True)
class BurstConfig:
    trend_sma: int | None = None
    momentum_lookback: int = 3
    momentum_threshold: float = 0.10
    breakout_window: int | None = None
    trigger_mode: str = "momentum"
    btc_ma: int | None = 20
    vol_floor: float | None = None
    vol_cap: float | None = 0.90
    max_hold_days: int = 3
    stop_loss: float | None = None
    take_profit: float | None = 0.25
    allow_short: bool = True

    @property
    def name(self) -> str:
        trend = "trend_off" if self.trend_sma is None else f"sma{self.trend_sma}"
        breakout = "boff" if self.breakout_window is None else f"bo{self.breakout_window}"
        btc = "btcoff" if self.btc_ma is None else f"btc{self.btc_ma}"
        floor = "vflooroff" if self.vol_floor is None else f"vfloor{self.vol_floor:.2f}"
        cap = "vcapoff" if self.vol_cap is None else f"vcap{self.vol_cap:.2f}"
        stop = "sloff" if self.stop_loss is None else f"sl{self.stop_loss:.2f}"
        take = "tpoff" if self.take_profit is None else f"tp{self.take_profit:.2f}"
        side = "dual" if self.allow_short else "longonly"
        return (
            f"{side}_mom{self.momentum_lookback}_{self.momentum_threshold:.2f}_"
            f"{self.trigger_mode}_{trend}_{breakout}_{btc}_{floor}_{cap}_"
            f"h{self.max_hold_days}_{stop}_{take}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coin-start", default=DEFAULT_COIN_START)
    parser.add_argument("--synthetic-start", default=DEFAULT_SYNTHETIC_START)
    parser.add_argument("--actual-start", default=DEFAULT_ACTUAL_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--cost-bps", type=float, default=15.0)
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    return parser.parse_args()


def add_burst_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for window in (20, 50, 100, 150):
        out[f"coin_sma_{window}"] = out["coin_close"].rolling(window).mean()
    for lookback in (2, 3, 5, 10):
        out[f"coin_mom_{lookback}"] = out["coin_close"].pct_change(lookback)
    for window in (10, 20, 40):
        out[f"coin_prev_high_{window}"] = out["coin_close"].shift(1).rolling(window).max()
        out[f"coin_prev_low_{window}"] = out["coin_close"].shift(1).rolling(window).min()
    out["coin_return"] = out["coin_close"].pct_change(fill_method=None)
    out["coin_rv_20"] = out["coin_return"].rolling(20).std() * np.sqrt(252.0)
    for window in (20, 50, 100):
        out[f"btc_ma_{window}"] = out["btc_close"].rolling(window).mean()
    return out


def build_config_grid() -> list[BurstConfig]:
    configs: list[BurstConfig] = []
    for trend_sma in (None, 20):
        for momentum_lookback in (2, 3, 5):
            for momentum_threshold in (0.08, 0.10, 0.15):
                for breakout_window in (None, 10):
                    for trigger_mode in ("momentum", "either"):
                        if breakout_window is None and trigger_mode == "either":
                            continue
                        for btc_ma in (20, 50):
                            for vol_floor in (None,):
                                for vol_cap in (0.90, 1.20):
                                    for max_hold_days in (3, 5):
                                        for stop_loss in (None,):
                                            for take_profit in (0.25, 0.40):
                                                for allow_short in (False, True):
                                                    configs.append(
                                                        BurstConfig(
                                                            trend_sma=trend_sma,
                                                            momentum_lookback=momentum_lookback,
                                                            momentum_threshold=momentum_threshold,
                                                            breakout_window=breakout_window,
                                                            trigger_mode=trigger_mode,
                                                            btc_ma=btc_ma,
                                                            vol_floor=vol_floor,
                                                            vol_cap=vol_cap,
                                                            max_hold_days=max_hold_days,
                                                            stop_loss=stop_loss,
                                                            take_profit=take_profit,
                                                            allow_short=allow_short,
                                                        )
                                                    )
    return configs


def entry_signal(row: pd.Series, config: BurstConfig) -> int:
    mom = row[f"coin_mom_{config.momentum_lookback}"]
    long_momentum = pd.notna(mom) and float(mom) > config.momentum_threshold
    short_momentum = pd.notna(mom) and float(mom) < -config.momentum_threshold

    long_breakout = False
    short_breakout = False
    if config.breakout_window is not None:
        high = row[f"coin_prev_high_{config.breakout_window}"]
        low = row[f"coin_prev_low_{config.breakout_window}"]
        long_breakout = pd.notna(high) and float(row["coin_close"]) > float(high)
        short_breakout = pd.notna(low) and float(row["coin_close"]) < float(low)

    if config.trigger_mode == "momentum":
        long_trigger = long_momentum
        short_trigger = short_momentum
    elif config.trigger_mode == "breakout":
        long_trigger = long_breakout
        short_trigger = short_breakout
    elif config.trigger_mode == "either":
        long_trigger = long_momentum or long_breakout
        short_trigger = short_momentum or short_breakout
    else:
        raise ValueError(f"Unsupported trigger_mode={config.trigger_mode!r}")

    if config.trend_sma is not None:
        sma = row[f"coin_sma_{config.trend_sma}"]
        if pd.isna(sma):
            return 0
        long_trigger = long_trigger and float(row["coin_close"]) > float(sma)
        short_trigger = short_trigger and float(row["coin_close"]) < float(sma)

    if config.btc_ma is not None:
        btc_ma = row[f"btc_ma_{config.btc_ma}"]
        if pd.isna(btc_ma):
            return 0
        long_trigger = long_trigger and float(row["btc_close"]) > float(btc_ma)
        short_trigger = short_trigger and float(row["btc_close"]) < float(btc_ma)

    rv = row["coin_rv_20"]
    if pd.isna(rv):
        return 0
    if config.vol_floor is not None and float(rv) < config.vol_floor:
        return 0
    if config.vol_cap is not None and float(rv) > config.vol_cap:
        return 0

    if long_trigger:
        return 1
    if config.allow_short and short_trigger:
        return -1
    return 0


def entry_signal_series(frame: pd.DataFrame, config: BurstConfig) -> pd.Series:
    return frame.apply(lambda row: entry_signal(row, config), axis=1).astype(int)


def simulate_burst_returns(
    frame: pd.DataFrame,
    config: BurstConfig,
    *,
    cost_rate: float,
) -> tuple[pd.Series, int, float]:
    position = 0
    entry_price: float | None = None
    held_days = 0
    switches = 0
    days_in_market = 0
    returns: list[float] = []

    signals = entry_signal_series(frame, config).to_numpy()
    long_returns = frame["long_return"].fillna(0.0).to_numpy()
    short_returns = frame["short_return"].fillna(0.0).to_numpy()
    long_closes = frame["long_close"].to_numpy()
    short_closes = frame["short_close"].to_numpy()

    for i in range(len(frame)):
        raw_return = 0.0
        if position == 1:
            raw_return = float(long_returns[i])
        elif position == -1:
            raw_return = float(short_returns[i])

        fresh_signal = int(signals[i])
        desired = position
        if fresh_signal != 0:
            desired = fresh_signal
        elif position == 0:
            desired = 0

        exit_now = False
        if position != 0 and entry_price is not None:
            held_days += 1
            current_close = float(long_closes[i] if position == 1 else short_closes[i])
            if config.stop_loss is not None and current_close <= entry_price * (1.0 - config.stop_loss):
                exit_now = True
            if config.take_profit is not None and current_close >= entry_price * (1.0 + config.take_profit):
                exit_now = True
            if held_days >= config.max_hold_days:
                exit_now = True
        if exit_now:
            desired = 0

        turnover = abs(desired - position)
        if turnover > 1e-9:
            switches += 1
        returns.append(raw_return - turnover * cost_rate)

        if desired != position:
            if desired == 1:
                entry_price = float(long_closes[i])
                held_days = 0
            elif desired == -1:
                entry_price = float(short_closes[i])
                held_days = 0
            else:
                entry_price = None
                held_days = 0
        position = desired
        if position != 0:
            days_in_market += 1

    series = pd.Series(returns, index=frame.index, dtype=float)
    time_in_market = days_in_market / max(1, len(frame))
    return series, switches, time_in_market


def evaluate_returns(returns: pd.Series) -> dict[str, float]:
    clean = returns.dropna()
    if clean.empty:
        return {
            "total_return": float("nan"),
            "cagr": float("nan"),
            "max_drawdown": float("nan"),
            "sharpe": float("nan"),
        }
    equity = (1.0 + clean).cumprod()
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1 / 252.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    volatility = clean.std()
    sharpe = float(clean.mean() / volatility * np.sqrt(252.0)) if volatility > 0 else float("nan")
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()),
        "sharpe": sharpe,
    }


def score_row(row: dict[str, object]) -> float:
    synthetic_cagr = float(row["synthetic_cagr"])
    actual_cagr = float(row["actual_cagr"])
    synthetic_mdd = abs(float(row["synthetic_max_drawdown"]))
    actual_mdd = abs(float(row["actual_max_drawdown"]))
    synthetic_sharpe = float(row["synthetic_sharpe"])
    actual_sharpe = float(row["actual_sharpe"])
    time_in_market = float(row["synthetic_time_in_market"])
    dd_penalty = max(0.0, synthetic_mdd - 0.42) * 2.0
    actual_dd_penalty = max(0.0, actual_mdd - 0.35) * 2.0
    overtrade_penalty = max(0.0, time_in_market - 0.30) * 0.50
    return (
        synthetic_cagr * 1.20
        + actual_cagr * 0.55
        + synthetic_sharpe * 0.20
        + actual_sharpe * 0.25
        - dd_penalty
        - actual_dd_penalty
        - overtrade_penalty
    )


def summarize_perf(prefix: str, perf: dict[str, float]) -> dict[str, object]:
    return {
        f"{prefix}_total_return": perf["total_return"],
        f"{prefix}_cagr": perf["cagr"],
        f"{prefix}_max_drawdown": perf["max_drawdown"],
        f"{prefix}_sharpe": perf["sharpe"],
    }


def latest_signal(frame: pd.DataFrame, config: BurstConfig) -> dict[str, object]:
    row = frame.iloc[-1]
    signal = int(entry_signal_series(frame, config).iloc[-1])
    return {
        "date": row.name.date().isoformat(),
        "entry_signal": {1: "long_CONL", -1: "short_CONI", 0: "cash"}[signal],
        "coin_close": float(row["coin_close"]),
        f"coin_mom_{config.momentum_lookback}": float(row[f"coin_mom_{config.momentum_lookback}"]),
        "coin_rv_20": float(row["coin_rv_20"]),
        "btc_close": float(row["btc_close"]),
        "strategy": config.name,
    }


def formatted_rows(frame: pd.DataFrame, *, limit: int = 20) -> pd.DataFrame:
    percent_cols = tuple(
        column
        for column in frame.columns
        if column.endswith(("cagr", "max_drawdown", "total_return", "time_in_market"))
    )
    display = frame.head(limit).copy()
    for column in display.columns:
        if column.endswith("sharpe"):
            display[column] = display[column].map(lambda value: f"{float(value):.2f}")
        elif column in percent_cols:
            display[column] = display[column].map(lambda value: format_percent(float(value)))
    return display


def build_synthetic_period(
    coin_close: pd.Series,
    btc_close: pd.Series,
    *,
    start: str,
) -> pd.DataFrame:
    frame = pd.DataFrame(index=coin_close.index)
    frame["coin_close"] = coin_close
    frame["btc_close"] = btc_close.shift(1).reindex(frame.index).ffill()
    coin_return = frame["coin_close"].pct_change(fill_method=None).fillna(0.0)
    frame["long_close"] = 100.0 * (1.0 + (2.0 * coin_return).clip(lower=-0.999999)).cumprod()
    frame["short_close"] = 100.0 * (1.0 + (-2.0 * coin_return).clip(lower=-0.999999)).cumprod()
    frame["long_return"] = frame["long_close"].pct_change(fill_method=None)
    frame["short_return"] = frame["short_close"].pct_change(fill_method=None)
    return add_burst_indicators(frame).loc[pd.Timestamp(start) :].dropna().copy()


def build_actual_period(
    coin_close: pd.Series,
    conl_close: pd.Series,
    coni_close: pd.Series,
    btc_close: pd.Series,
    *,
    start: str,
) -> pd.DataFrame:
    index = coin_close.index.union(conl_close.index).union(coni_close.index)
    frame = pd.DataFrame(index=index)
    frame["coin_close"] = coin_close.reindex(index).ffill()
    frame["btc_close"] = btc_close.shift(1).reindex(index).ffill()
    frame["long_close"] = conl_close.reindex(index)
    frame["short_close"] = coni_close.reindex(index)
    frame["long_return"] = frame["long_close"].pct_change(fill_method=None)
    frame["short_return"] = frame["short_close"].pct_change(fill_method=None)
    return add_burst_indicators(frame).loc[pd.Timestamp(start) :].dropna().copy()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    cost_rate = args.cost_bps / 10_000.0

    coin = download_nasdaq_close("COIN", assetclass="stocks", start=args.coin_start, end=args.end)
    conl = download_nasdaq_close("CONL", assetclass="etf", start=args.synthetic_start, end=args.end)
    coni = download_nasdaq_close("CONI", assetclass="etf", start=DEFAULT_ACTUAL_START, end=args.end)
    btc = download_coinbase_daily_close("BTC-USD", start=args.coin_start, end=args.end)
    synthetic = build_synthetic_period(coin, btc, start=args.synthetic_start)
    actual = build_actual_period(coin, conl, coni, btc, start=args.actual_start)

    rows: list[dict[str, object]] = []
    for config in build_config_grid():
        synthetic_returns, synthetic_switches, synthetic_tim = simulate_burst_returns(
            synthetic,
            config,
            cost_rate=cost_rate,
        )
        actual_returns, actual_switches, actual_tim = simulate_burst_returns(
            actual,
            config,
            cost_rate=cost_rate,
        )
        synthetic_perf = evaluate_returns(synthetic_returns)
        actual_perf = evaluate_returns(actual_returns)
        row = {
            "strategy": config.name,
            **asdict(config),
            **summarize_perf("synthetic", synthetic_perf),
            "synthetic_switches": synthetic_switches,
            "synthetic_time_in_market": synthetic_tim,
            **summarize_perf("actual", actual_perf),
            "actual_switches": actual_switches,
            "actual_time_in_market": actual_tim,
        }
        row["score"] = score_row(row)
        row["drawdown_ok"] = bool(
            float(row["synthetic_max_drawdown"]) >= -0.42
            and float(row["actual_max_drawdown"]) >= -0.35
        )
        rows.append(row)

    search = pd.DataFrame(rows).sort_values("score", ascending=False)
    qualified = search[search["drawdown_ok"]].copy()
    ranked = qualified if not qualified.empty else search
    recommendation = ranked.iloc[0].to_dict()
    recommended_config = BurstConfig(
        **{
            key: recommendation[key]
            for key in (
                "trend_sma",
                "momentum_lookback",
                "momentum_threshold",
                "breakout_window",
                "trigger_mode",
                "btc_ma",
                "vol_floor",
                "vol_cap",
                "max_hold_days",
                "stop_loss",
                "take_profit",
                "allow_short",
            )
        }
    )

    top_path = results_dir / "coin_burst_routes_top_search.csv"
    rec_path = results_dir / "coin_burst_routes_recommendation.csv"
    latest_path = results_dir / "coin_burst_routes_latest.csv"
    summary_path = results_dir / "coin_burst_routes_summary.md"
    json_path = results_dir / "coin_burst_routes_summary.json"
    search.head(200).to_csv(top_path, index=False)
    pd.DataFrame([recommendation]).to_csv(rec_path, index=False)
    latest = latest_signal(actual, recommended_config)
    pd.DataFrame([latest]).to_csv(latest_path, index=False)

    rec_display = formatted_rows(pd.DataFrame([recommendation]), limit=1)
    top_display = formatted_rows(search, limit=20)
    summary = "\n".join(
        [
            "# COIN Burst Route Search",
            "",
            f"Synthetic window: `{synthetic.index.min().date().isoformat()}` to `{synthetic.index.max().date().isoformat()}`.",
            f"Actual CONL/CONI window: `{actual.index.min().date().isoformat()}` to `{actual.index.max().date().isoformat()}`.",
            f"Trading cost: {args.cost_bps:.1f} bps per unit turnover.",
            "",
            "## Recommendation",
            "",
            frame_to_markdown_table(rec_display),
            "",
            "## Latest Signal",
            "",
            frame_to_markdown_table(pd.DataFrame([latest])),
            "",
            "## Top Search Rows",
            "",
            frame_to_markdown_table(top_display),
        ]
    )
    summary_path.write_text(summary + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "recommendation": recommendation,
                "latest_signal": latest,
                "synthetic_window": [
                    synthetic.index.min().date().isoformat(),
                    synthetic.index.max().date().isoformat(),
                ],
                "actual_window": [
                    actual.index.min().date().isoformat(),
                    actual.index.max().date().isoformat(),
                ],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"Wrote top search: {top_path}")
    print(f"Wrote recommendation: {rec_path}")
    print(f"Wrote latest signal: {latest_path}")
    print(f"Wrote summary: {summary_path}")
    print(f"Wrote JSON: {json_path}")


if __name__ == "__main__":
    main()
