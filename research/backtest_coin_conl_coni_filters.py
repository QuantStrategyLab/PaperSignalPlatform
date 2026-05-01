#!/usr/bin/env python3
"""Research-only COIN/CONL/CONI filter sweep.

This script keeps the COIN research path separate from the notifier runtime.
It reuses the production signal function so follow-up research stays aligned
with the currently deployed COIN short-hold rule shape.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_notifier.coin_short_hold_notify import (  # noqa: E402
    DEFAULT_CONI_START,
    DEFAULT_CONL_START,
    DEFAULT_IPO_START,
    download_coinbase_daily_close,
    download_nasdaq_close,
)
from signal_notifier.coin_short_hold_vt50 import (  # noqa: E402
    CoinShortHoldVT50Config,
    _build_signal_frame,
)


DEFAULT_RESULTS_DIR = CURRENT_DIR / "results"
DEFAULT_START = "2022-08-09"
DEFAULT_END = pd.Timestamp.now(tz="UTC").date().isoformat()
DEFAULT_COST_BPS = 15.0


@dataclass(frozen=True)
class BacktestResult:
    name: str
    config: CoinShortHoldVT50Config
    returns: pd.Series
    sides: pd.Series
    weights: pd.Series
    switches: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument(
        "--grid",
        action="store_true",
        help="Run a broader parameter grid instead of the compact retained candidate set.",
    )
    return parser.parse_args()


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def frame_to_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in frame.iterrows():
        values = [str(row[column]) for column in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _download_market_data(*, end: str) -> dict[str, pd.Series]:
    coin = download_nasdaq_close("COIN", assetclass="stocks", start=DEFAULT_IPO_START, end=end)
    btc = download_coinbase_daily_close("BTC-USD", start=DEFAULT_IPO_START, end=end)
    conl = download_nasdaq_close("CONL", assetclass="etf", start=DEFAULT_CONL_START, end=end)
    coni = download_nasdaq_close("CONI", assetclass="etf", start=DEFAULT_CONI_START, end=end)
    return {
        "coin": coin,
        "btc": btc,
        "conl": conl,
        "coni": coni,
    }


def _compact_configs() -> tuple[tuple[str, CoinShortHoldVT50Config], ...]:
    base = CoinShortHoldVT50Config()
    return (
        ("production_fixed50", base),
        ("mom5_thr5", CoinShortHoldVT50Config(momentum_threshold=0.05)),
        ("mom5_thr12", CoinShortHoldVT50Config(momentum_threshold=0.12)),
        ("sma100_mom5_thr8", CoinShortHoldVT50Config(coin_sma=100)),
        ("sma200_mom5_thr8", CoinShortHoldVT50Config(coin_sma=200)),
        ("mom10_thr8", CoinShortHoldVT50Config(momentum_lookback=10)),
        ("rv_cap80", CoinShortHoldVT50Config(coin_rv_cap=0.80)),
        ("rv_cap120", CoinShortHoldVT50Config(coin_rv_cap=1.20)),
        ("hold5_tp40", CoinShortHoldVT50Config(max_hold_days=5)),
        ("hold15_tp40", CoinShortHoldVT50Config(max_hold_days=15)),
        ("hold10_tp30", CoinShortHoldVT50Config(take_profit=0.30)),
        ("hold10_tp60", CoinShortHoldVT50Config(take_profit=0.60)),
    )


def _grid_configs() -> tuple[tuple[str, CoinShortHoldVT50Config], ...]:
    configs: list[tuple[str, CoinShortHoldVT50Config]] = []
    for sma in (100, 150, 200):
        for lookback in (5, 10):
            for threshold in (0.05, 0.08, 0.12):
                for rv_cap in (0.80, 0.90, 1.20):
                    for max_hold in (5, 10, 15):
                        for take_profit in (0.30, 0.40, 0.60):
                            name = (
                                f"sma{sma}_mom{lookback}_{threshold:.2f}_"
                                f"rv{rv_cap:.2f}_hold{max_hold}_tp{take_profit:.2f}"
                            )
                            configs.append(
                                (
                                    name,
                                    CoinShortHoldVT50Config(
                                        coin_sma=sma,
                                        momentum_lookback=lookback,
                                        momentum_threshold=threshold,
                                        coin_rv_cap=rv_cap,
                                        max_hold_days=max_hold,
                                        take_profit=take_profit,
                                    ),
                                )
                            )
    return tuple(configs)


def _state_frame(frame: pd.DataFrame, *, config: CoinShortHoldVT50Config) -> pd.DataFrame:
    required = [
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
    ready = frame.dropna(subset=required)
    if ready.empty:
        return pd.DataFrame()

    position = 0
    entry_price: float | None = None
    held_days = 0
    rows: list[dict[str, Any]] = []

    for date, row in ready.iterrows():
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
            if desired == 1 and row["btc_close"] <= row["btc_ma"]:
                desired = 0
                decision_reasons.append("btc_filter_blocked_long")
            elif desired == -1 and row["btc_close"] >= row["btc_ma"]:
                desired = 0
                decision_reasons.append("btc_filter_blocked_short")

        if desired != 0 and row["coin_rv_20"] > config.coin_rv_cap:
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
        target_symbol: str | None = None
        side = "cash"
        if position == 1 and gross_exposure > 0:
            target_symbol = config.long_symbol
            side = "long"
        elif position == -1 and gross_exposure > 0:
            target_symbol = config.short_symbol
            side = "short"

        rows.append(
            {
                "date": date,
                "position": position,
                "side": side,
                "target_symbol": target_symbol,
                "gross_exposure": float(gross_exposure),
                "held_days": held_days,
                "entry_price": entry_price,
                "decision_reasons": tuple(decision_reasons),
            }
        )

    out = pd.DataFrame(rows).set_index("date")
    return out


def _run_backtest(
    name: str,
    config: CoinShortHoldVT50Config,
    *,
    market_data: dict[str, pd.Series],
    start: str,
    cost_rate: float,
) -> BacktestResult:
    coin = market_data["coin"]
    btc = market_data["btc"]
    conl = market_data["conl"]
    coni = market_data["coni"]
    frame = _build_signal_frame(coin, btc, config=config, long_close=conl, short_close=coni)
    states = _state_frame(frame, config=config)
    dates = states.index[states.index >= pd.Timestamp(start)]

    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    sides: list[str] = []
    weights: list[float] = []
    previous_targets: dict[str, float] = {}
    switches = 0
    for idx in range(len(dates) - 1):
        date = dates[idx]
        next_date = dates[idx + 1]
        state = states.loc[date]
        target_symbol = state["target_symbol"]
        gross_exposure = float(state["gross_exposure"])
        targets = {target_symbol: gross_exposure} if target_symbol and gross_exposure > 0 else {}
        weighted_return = 0.0
        if target_symbol == config.long_symbol:
            weighted_return = gross_exposure * float(frame.loc[next_date, "long_return"])
        elif target_symbol == config.short_symbol:
            weighted_return = gross_exposure * float(frame.loc[next_date, "short_return"])

        symbols = set(previous_targets) | set(targets)
        turnover = sum(abs(targets.get(symbol, 0.0) - previous_targets.get(symbol, 0.0)) for symbol in symbols)
        if turnover > 1e-9:
            switches += 1
        returns.append(weighted_return - turnover * cost_rate)
        return_dates.append(next_date)
        sides.append(str(state["side"]))
        weights.append(gross_exposure)
        previous_targets = targets

    return BacktestResult(
        name=name,
        config=config,
        returns=pd.Series(returns, index=return_dates, dtype=float),
        sides=pd.Series(sides, index=return_dates, dtype=str),
        weights=pd.Series(weights, index=return_dates, dtype=float),
        switches=switches,
    )


def _performance_row(result: BacktestResult) -> dict[str, Any]:
    returns = result.returns.dropna()
    equity = (1.0 + returns).cumprod()
    years = (returns.index[-1] - returns.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1.0 / years) - 1.0
    drawdown = equity / equity.cummax() - 1.0
    volatility = returns.std()
    sharpe = returns.mean() / volatility * math.sqrt(252.0) if volatility > 0 else float("nan")
    side_counts = result.sides.value_counts(normalize=True)
    return {
        "name": result.name,
        "cagr": format_percent(float(cagr)),
        "total_return": format_percent(float(equity.iloc[-1] - 1.0)),
        "max_drawdown": format_percent(float(drawdown.min())),
        "sharpe": f"{float(sharpe):.2f}",
        "avg_weight": format_percent(float(result.weights.mean())),
        "long_days": format_percent(float(side_counts.get("long", 0.0))),
        "short_days": format_percent(float(side_counts.get("short", 0.0))),
        "cash_days": format_percent(float(side_counts.get("cash", 0.0))),
        "rebalance_days": result.switches,
        "first_return_date": returns.index[0].date().isoformat(),
        "latest_return_date": returns.index[-1].date().isoformat(),
        "observations": len(returns),
        "config": asdict(result.config),
    }


def _score_row(row: dict[str, Any]) -> tuple[float, float, float]:
    cagr = float(str(row["cagr"]).rstrip("%")) / 100.0
    drawdown = abs(float(str(row["max_drawdown"]).rstrip("%")) / 100.0)
    sharpe = float(row["sharpe"])
    return (sharpe, cagr, -drawdown)


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    cost_rate = args.cost_bps / 10_000.0
    end = pd.Timestamp(args.end).date().isoformat()

    market_data = _download_market_data(end=end)
    configs = _grid_configs() if args.grid else _compact_configs()
    results = [
        _run_backtest(name, config, market_data=market_data, start=args.start, cost_rate=cost_rate)
        for name, config in configs
    ]
    rows = [_performance_row(result) for result in results if not result.returns.empty]
    comparison = pd.DataFrame(rows).sort_values(
        by=["sharpe", "cagr", "max_drawdown"],
        ascending=[False, False, False],
    )
    best = max(rows, key=_score_row) if rows else {}

    comparison_path = results_dir / "coin_conl_coni_filters_comparison.csv"
    recommendation_path = results_dir / "coin_conl_coni_filters_recommendation.json"
    summary_path = results_dir / "coin_conl_coni_filters_summary.md"
    comparison.to_csv(comparison_path, index=False)
    recommendation_path.write_text(json.dumps(best, indent=2, default=str), encoding="utf-8")

    summary_lines = [
        "# COIN/CONL/CONI Filter Sweep",
        "",
        f"Window: `{args.start}` to requested `{end}`.",
        f"Trading cost: {args.cost_bps:.1f} bps per unit turnover.",
        "Signals reuse `CoinShortHoldVT50Config` and `compute_coin_short_hold_vt50_signal`.",
        "",
        "## Best Candidate",
        "",
        frame_to_markdown_table(pd.DataFrame([best]) if best else pd.DataFrame()),
        "",
        "## Comparison",
        "",
        frame_to_markdown_table(comparison.drop(columns=["config"], errors="ignore")),
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote comparison: {comparison_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote summary: {summary_path}")
    print(comparison.drop(columns=["config"], errors="ignore").head(12).to_string(index=False))


if __name__ == "__main__":
    main()
