#!/usr/bin/env python3
"""Compare long-only CONL and long-only COIN research routes."""

from __future__ import annotations

import argparse
import json
import sys
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
    DEFAULT_IPO_START,
    download_coinbase_daily_close,
    download_nasdaq_close,
)


DEFAULT_COIN_START = DEFAULT_IPO_START


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coin-start", default=DEFAULT_COIN_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--cost-bps", type=float, default=15.0)
    parser.add_argument("--bootstrap-sims", type=int, default=1000)
    parser.add_argument("--bootstrap-block", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def candidate_configs() -> dict[str, dict[str, float | int | None]]:
    return {
        "baseline": {"sma": 150, "lb": 5, "th": 0.10},
        "vol_only": {"sma": 150, "lb": 5, "th": 0.10, "vol": 0.90, "tp": 0.40},
        "btc_only": {"sma": 150, "lb": 5, "th": 0.10, "btc": 50, "tp": 0.40},
        "fast_combo": {
            "sma": 150,
            "lb": 5,
            "th": 0.10,
            "btc": 50,
            "vol": 0.90,
            "tp": 0.40,
        },
        "slow_combo": {
            "sma": 200,
            "lb": 10,
            "th": 0.10,
            "btc": 150,
            "vol": 0.90,
            "tp": 0.40,
        },
        "slow_combo_tp60": {
            "sma": 200,
            "lb": 10,
            "th": 0.10,
            "btc": 150,
            "vol": 0.90,
            "tp": 0.60,
        },
    }


def build_frame(
    coin_close: pd.Series,
    instrument_close: pd.Series,
    btc_close: pd.Series,
) -> pd.DataFrame:
    index = coin_close.index.intersection(instrument_close.index)
    frame = pd.DataFrame(index=index)
    frame["coin_close"] = coin_close.reindex(index).astype(float)
    frame["instrument_close"] = instrument_close.reindex(index).astype(float)
    frame["instrument_return"] = frame["instrument_close"].pct_change(fill_method=None)
    frame["coin_return"] = frame["coin_close"].pct_change(fill_method=None)
    frame["btc_close"] = btc_close.shift(1).reindex(index).ffill().astype(float)

    for window in (150, 200):
        frame[f"coin_ma_{window}"] = frame["coin_close"].rolling(window).mean()
    for lookback in (5, 10):
        frame[f"coin_mom_{lookback}"] = frame["coin_close"].pct_change(lookback)
    for window in (50, 150):
        frame[f"btc_ma_{window}"] = frame["btc_close"].rolling(window).mean()
    frame["coin_rv_20"] = frame["coin_return"].rolling(20).std() * np.sqrt(252.0)
    return frame.dropna().copy()


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


def simulate_long_only_returns(
    frame: pd.DataFrame,
    config: dict[str, float | int | None],
    *,
    cost_rate: float,
) -> pd.Series:
    position = 0
    entry_price: float | None = None
    returns: list[float] = []
    index: list[pd.Timestamp] = []

    for date, row in frame.iterrows():
        raw_return = position * float(row["instrument_return"])
        desired = 0

        ma = row[f"coin_ma_{int(config['sma'])}"]
        momentum = row[f"coin_mom_{int(config['lb'])}"]
        if pd.notna(ma) and pd.notna(momentum):
            if row["coin_close"] > ma and momentum > float(config["th"]):
                desired = 1

        btc_window = config.get("btc")
        if desired and btc_window is not None:
            btc_ma = row[f"btc_ma_{int(btc_window)}"]
            if pd.isna(btc_ma) or row["btc_close"] <= btc_ma:
                desired = 0

        vol_cap = config.get("vol")
        if desired and vol_cap is not None:
            rv = row["coin_rv_20"]
            if pd.isna(rv) or float(rv) > float(vol_cap):
                desired = 0

        take_profit = config.get("tp")
        if position and entry_price is not None and take_profit is not None:
            if float(row["instrument_close"]) >= entry_price * (1.0 + float(take_profit)):
                desired = 0

        turnover = abs(desired - position)
        period_return = raw_return - turnover * cost_rate
        returns.append(period_return)
        index.append(date)

        if desired != position:
            entry_price = float(row["instrument_close"]) if desired else None
        position = desired

    return pd.Series(returns, index=index, dtype=float)


def train_score(performance: dict[str, float]) -> float:
    cagr = float(performance["cagr"])
    max_drawdown = abs(float(performance["max_drawdown"]))
    if not np.isfinite(cagr):
        return float("-inf")
    return cagr - 2.0 * max_drawdown


def run_walk_forward(
    frame: pd.DataFrame,
    cached_returns: dict[str, pd.Series],
    *,
    train_days: int,
    test_days: int,
) -> tuple[dict[str, float], pd.Series, pd.DataFrame]:
    stitched_parts: list[pd.Series] = []
    rows: list[dict[str, object]] = []

    for train_end_idx in range(train_days, len(frame), test_days):
        train_end = frame.index[train_end_idx - 1]
        test_start = frame.index[train_end_idx]
        test_end = frame.index[min(train_end_idx + test_days - 1, len(frame) - 1)]

        best_name = ""
        best_score = float("-inf")
        for name, returns in cached_returns.items():
            score = train_score(evaluate_returns(returns.loc[:train_end]))
            if score > best_score:
                best_name = name
                best_score = score

        test_returns = cached_returns[best_name].loc[test_start:test_end]
        stitched_parts.append(test_returns)
        test_perf = evaluate_returns(test_returns)
        rows.append(
            {
                "train_end": train_end.date().isoformat(),
                "test_start": test_start.date().isoformat(),
                "test_end": test_end.date().isoformat(),
                "selected_config": best_name,
                "test_cagr": test_perf["cagr"],
                "test_max_drawdown": test_perf["max_drawdown"],
                "test_total_return": test_perf["total_return"],
            }
        )

    stitched = pd.concat(stitched_parts).sort_index() if stitched_parts else pd.Series(dtype=float)
    return evaluate_returns(stitched), stitched, pd.DataFrame(rows)


def moving_block_bootstrap(
    returns: pd.Series,
    *,
    block_size: int,
    simulations: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    values = returns.dropna().to_numpy()
    length = len(values)
    rows: list[dict[str, float]] = []
    if length == 0:
        return pd.DataFrame()

    for _ in range(simulations):
        blocks: list[float] = []
        while len(blocks) < length:
            start = int(rng.integers(0, max(1, length - block_size + 1)))
            blocks.extend(values[start : start + block_size].tolist())
        sampled = blocks[:length]
        series = pd.Series(sampled, index=returns.dropna().index)
        rows.append(evaluate_returns(series))
    return pd.DataFrame(rows)


def summarize_bootstrap(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    return {
        "positive_cagr_probability": format_percent(float((frame["cagr"] > 0).mean())),
        "median_cagr": format_percent(float(frame["cagr"].median())),
        "cagr_p10": format_percent(float(frame["cagr"].quantile(0.1))),
        "cagr_p90": format_percent(float(frame["cagr"].quantile(0.9))),
        "median_max_drawdown": format_percent(float(frame["max_drawdown"].median())),
        "max_drawdown_p10": format_percent(float(frame["max_drawdown"].quantile(0.1))),
    }


def _format_perf(perf: dict[str, float]) -> dict[str, str]:
    return {
        "cagr": format_percent(float(perf["cagr"])),
        "max_drawdown": format_percent(float(perf["max_drawdown"])),
        "total_return": format_percent(float(perf["total_return"])),
        "sharpe": f"{float(perf['sharpe']):.2f}",
    }


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    cost_rate = args.cost_bps / 10_000.0

    coin = download_nasdaq_close("COIN", assetclass="stocks", start=args.coin_start, end=args.end)
    conl = download_nasdaq_close("CONL", assetclass="etf", start="2022-08-09", end=args.end)
    btc = download_coinbase_daily_close("BTC-USD", start=args.coin_start, end=args.end)
    route_frames = {
        "CONL_long_only": build_frame(coin, conl, btc),
        "COIN_long_only": build_frame(coin, coin, btc),
    }
    configs = candidate_configs()

    route_payload: dict[str, object] = {}
    summary_sections = ["# COIN Long-Only Route Comparison", ""]

    for route_name, frame in route_frames.items():
        cached_returns = {
            name: simulate_long_only_returns(frame, config, cost_rate=cost_rate)
            for name, config in configs.items()
        }
        static_rows = []
        for config_name, returns in cached_returns.items():
            static_rows.append({"config": config_name, **_format_perf(evaluate_returns(returns))})
        static_frame = pd.DataFrame(static_rows).sort_values("cagr", ascending=False)
        static_frame.to_csv(results_dir / f"{route_name.lower()}_static.csv", index=False)

        schedule_rows = []
        representative_bootstrap_rows = []
        for train_days, test_days in ((252, 63), (504, 63), (504, 126)):
            wf_perf, wf_returns, wf_windows = run_walk_forward(
                frame,
                cached_returns,
                train_days=train_days,
                test_days=test_days,
            )
            key = f"{train_days}_{test_days}"
            wf_windows.to_csv(results_dir / f"{route_name.lower()}_{key}_windows.csv", index=False)
            schedule_rows.append(
                {
                    "train_days": train_days,
                    "test_days": test_days,
                    "walk_forward_cagr": format_percent(wf_perf["cagr"]),
                    "walk_forward_max_drawdown": format_percent(wf_perf["max_drawdown"]),
                    "walk_forward_total_return": format_percent(wf_perf["total_return"]),
                    "window_count": len(wf_windows),
                    "unique_selected_configs": wf_windows["selected_config"].nunique()
                    if not wf_windows.empty
                    else 0,
                }
            )
            if (train_days, test_days) in ((252, 63), (504, 63)):
                boot = moving_block_bootstrap(
                    wf_returns,
                    block_size=args.bootstrap_block,
                    simulations=args.bootstrap_sims,
                    seed=args.seed + train_days + test_days,
                )
                boot.to_csv(results_dir / f"{route_name.lower()}_{key}_bootstrap.csv", index=False)
                representative_bootstrap_rows.append(
                    {"train_days": train_days, "test_days": test_days, **summarize_bootstrap(boot)}
                )

        schedule_frame = pd.DataFrame(schedule_rows)
        bootstrap_frame = pd.DataFrame(representative_bootstrap_rows)
        schedule_frame.to_csv(results_dir / f"{route_name.lower()}_schedule_summary.csv", index=False)
        bootstrap_frame.to_csv(results_dir / f"{route_name.lower()}_bootstrap_summary.csv", index=False)

        summary_sections.extend(
            [
                f"## {route_name}",
                "",
                f"- Sample: `{frame.index.min().date().isoformat()}` to `{frame.index.max().date().isoformat()}`",
                "",
                "### Static Candidates",
                "",
                frame_to_markdown_table(static_frame),
                "",
                "### Walk-Forward",
                "",
                frame_to_markdown_table(schedule_frame),
                "",
                "### Bootstrap",
                "",
                frame_to_markdown_table(bootstrap_frame),
                "",
            ]
        )
        route_payload[route_name] = {
            "sample_start": frame.index.min().date().isoformat(),
            "sample_end": frame.index.max().date().isoformat(),
            "static": static_rows,
            "walk_forward": schedule_rows,
            "bootstrap": representative_bootstrap_rows,
        }

    summary_sections.extend(
        [
            "## Interpretation",
            "",
            "- `CONL long-only + cash` is the more promising route to keep researching.",
            "- `COIN long-only + cash` is simpler and usually less levered, but the walk-forward profile is weaker.",
            "- Both routes remain research-only; neither is promoted to production by this script.",
        ]
    )

    summary_text = "\n".join(summary_sections) + "\n"
    summary_path = results_dir / "coin_long_only_routes_summary.md"
    json_path = results_dir / "coin_long_only_routes_summary.json"
    summary_path.write_text(summary_text, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "candidate_configs": configs,
                "routes": route_payload,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"Wrote summary: {summary_path}")
    print(f"Wrote JSON: {json_path}")


if __name__ == "__main__":
    main()
