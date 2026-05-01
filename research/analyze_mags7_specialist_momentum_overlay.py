#!/usr/bin/env python3
"""Overlay a unified MAG7 momentum top-N filter on specialist routes."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_notifier.coin_short_hold_notify import download_nasdaq_close  # noqa: E402
from signal_notifier.grouped_tool_choice_notify import (  # noqa: E402
    GROUP_MAGS7,
    MAGS7_ETF_STARTS,
    RECOMMENDATION_BUCKET_BUDGETS,
    RECOMMENDATION_BUCKET_CORE_STOCK,
    RECOMMENDATION_BUCKET_TACTICAL,
    ROUTES,
    ToolChoiceRouteConfig,
    _build_route_frame,
    _route_signal_on,
)


DEFAULT_RESULTS_DIR = CURRENT_DIR / "results"
DEFAULT_DOWNLOAD_START = "2015-01-01"
DEFAULT_START = "2022-01-03"
DEFAULT_END = pd.Timestamp.now(tz="UTC").date().isoformat()
DEFAULT_COST_BPS = 15.0
BACKTEST_MODES = ("static_score", "dynamic_score", "dynamic_sqrt_score")
OVERLAYS = ("none", "top2", "top3", "top4", "top5")
MAGS7_UNDERLYINGS = ("AAPL", "AMZN", "GOOGL", "NVDA", "MSFT", "META", "TSLA")


@dataclass(frozen=True)
class MomentumVariant:
    name: str
    top_leverage: int
    top_stock: int
    trend_sma: int = 150
    require_positive_120d: bool = True


@dataclass(frozen=True)
class DailyCandidate:
    route: ToolChoiceRouteConfig
    bucket: str
    date: pd.Timestamp
    target_symbol: str
    underlying_symbol: str
    instrument_return_next: float
    gross_exposure: float
    base_score: float
    dynamic_multiplier: float
    dynamic_score: float
    sqrt_dynamic_score: float
    metrics: dict[str, float]


@dataclass(frozen=True)
class BacktestResult:
    name: str
    returns: pd.Series
    weights: pd.DataFrame
    leader_counts: dict[str, int]
    avg_active_count: float
    avg_top_weight: float
    avg_cash: float
    switches: int


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-start", default=DEFAULT_DOWNLOAD_START)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--overlays", default=",".join(OVERLAYS))
    return parser.parse_args()


def _parse_overlays(raw: str) -> tuple[str, ...]:
    overlays = tuple(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    unsupported = [overlay for overlay in overlays if overlay not in OVERLAYS]
    if unsupported:
        raise ValueError(f"unsupported overlays: {', '.join(unsupported)}")
    return overlays


def _normalize_close(series: pd.Series) -> pd.Series:
    out = series.copy()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.astype(float)


def _close_frame(market_data: dict[str, pd.Series], symbols: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame({symbol: _normalize_close(market_data[symbol]) for symbol in symbols}).dropna(how="all")


def _percentile_rank(row: pd.Series) -> pd.Series:
    valid = row.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=row.index)
    if len(valid) == 1:
        out = pd.Series(np.nan, index=row.index)
        out.loc[valid.index] = 0.5
        return out
    return (row.rank(method="average") - 1.0) / (valid.count() - 1.0)


def _momentum_score_frame(close: pd.DataFrame, qqq: pd.Series, *, variant: MomentumVariant) -> pd.DataFrame:
    ret20 = close.pct_change(20)
    ret60 = close.pct_change(60)
    ret120 = close.pct_change(120)
    qqq_ret60 = qqq.pct_change(60)
    rv20 = close.pct_change(fill_method=None).rolling(20).std() * math.sqrt(252.0)
    trend = close / close.rolling(variant.trend_sma).mean() - 1.0
    risk_adj60 = ret60 / rv20.replace(0.0, np.nan)
    relative60 = ret60.sub(qqq_ret60, axis=0)

    score = (
        0.30 * ret20.apply(_percentile_rank, axis=1)
        + 0.30 * ret60.apply(_percentile_rank, axis=1)
        + 0.20 * ret120.apply(_percentile_rank, axis=1)
        + 0.10 * risk_adj60.apply(_percentile_rank, axis=1)
        + 0.10 * relative60.apply(_percentile_rank, axis=1)
    )

    eligible = close > close.rolling(variant.trend_sma).mean()
    eligible &= ret60 > 0.0
    if variant.require_positive_120d:
        eligible &= ret120 > 0.0
    eligible &= trend.notna()
    return score.where(eligible)


def _required_columns(route: ToolChoiceRouteConfig) -> list[str]:
    required = ["underlying_close", "instrument_rv20_prev"]
    if route.sma_window is not None:
        required.append("underlying_sma")
    if route.momentum_lookback is not None:
        required.append("underlying_momentum")
    if route.ema_fast_window is not None and route.ema_slow_window is not None:
        required.extend(["underlying_ema_fast", "underlying_ema_slow"])
    if route.qqq_sma_window is not None:
        required.append("qqq_sma")
    return required


def _bucket_for_route(route: ToolChoiceRouteConfig) -> str:
    if route.recommendation_bucket:
        return route.recommendation_bucket
    if route.tool == "stock_long":
        return RECOMMENDATION_BUCKET_CORE_STOCK
    return RECOMMENDATION_BUCKET_TACTICAL


def _base_score_for_route(route: ToolChoiceRouteConfig) -> float:
    return max(0.0, float(route.recommendation_score or 0.0))


def _percentile_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [0.5]
    series = pd.Series(values, dtype=float)
    return ((series.rank(method="average") - 1.0) / (len(values) - 1.0)).tolist()


def _dynamic_multipliers(candidates: list[DailyCandidate]) -> dict[int, float]:
    if not candidates:
        return {}
    metric_names = ("rs20", "rs60", "risk_adj_mom60", "trend_distance")
    rank_by_metric: dict[str, dict[int, float]] = {}
    for metric_name in metric_names:
        present = [
            (idx, candidate.metrics[metric_name])
            for idx, candidate in enumerate(candidates)
            if metric_name in candidate.metrics and math.isfinite(candidate.metrics[metric_name])
        ]
        if not present:
            continue
        percentiles = _percentile_scores([value for _, value in present])
        rank_by_metric[metric_name] = {
            idx: percentile for (idx, _), percentile in zip(present, percentiles, strict=True)
        }

    out: dict[int, float] = {}
    for idx, _candidate in enumerate(candidates):
        values = [ranks[idx] for ranks in rank_by_metric.values() if idx in ranks]
        out[idx] = 1.0 if not values else 0.5 + float(sum(values) / len(values))
    return out


def _dynamic_metrics(frame: pd.DataFrame, route: ToolChoiceRouteConfig, date: pd.Timestamp) -> dict[str, float]:
    row = frame.loc[date]
    metrics: dict[str, float] = {}
    underlying_close = float(row["underlying_close"])
    qqq_close = float(row["qqq_close"])
    idx = frame.index.get_loc(date)
    if isinstance(idx, slice):
        return metrics

    for lookback in (20, 60):
        if idx < lookback:
            continue
        prev_row = frame.iloc[idx - lookback]
        underlying_prev = float(prev_row["underlying_close"])
        qqq_prev = float(prev_row["qqq_close"])
        if underlying_prev > 0 and qqq_prev > 0:
            underlying_mom = underlying_close / underlying_prev - 1.0
            qqq_mom = qqq_close / qqq_prev - 1.0
            metrics[f"rs{lookback}"] = underlying_mom - qqq_mom
            if lookback == 60:
                rv20 = row.get("underlying_rv20")
                if pd.notna(rv20) and float(rv20) > 0:
                    metrics["risk_adj_mom60"] = underlying_mom / float(rv20)

    if route.sma_window is not None and pd.notna(row["underlying_sma"]) and float(row["underlying_sma"]) > 0:
        metrics["trend_distance"] = underlying_close / float(row["underlying_sma"]) - 1.0
    elif (
        route.ema_fast_window is not None
        and route.ema_slow_window is not None
        and pd.notna(row["underlying_ema_fast"])
        and pd.notna(row["underlying_ema_slow"])
        and float(row["underlying_ema_slow"]) > 0
    ):
        metrics["trend_distance"] = float(row["underlying_ema_fast"]) / float(row["underlying_ema_slow"]) - 1.0
    return metrics


def _active_candidates_for_date(
    *,
    date: pd.Timestamp,
    next_date: pd.Timestamp,
    route_frames: dict[ToolChoiceRouteConfig, pd.DataFrame],
) -> list[DailyCandidate]:
    active: list[DailyCandidate] = []
    for route, frame in route_frames.items():
        if date not in frame.index or next_date not in frame.index:
            continue
        row = frame.loc[date]
        required = _required_columns(route)
        if any(pd.isna(row[column]) for column in required):
            continue
        signal_on, _reasons = _route_signal_on(route, row)
        if not signal_on:
            continue
        instrument_rv = float(row["instrument_rv20_prev"])
        if instrument_rv <= 0:
            continue
        gross_exposure = max(0.0, min(float(route.max_weight), float(route.vol_target) / instrument_rv))
        if gross_exposure <= 0:
            continue
        next_return = frame.loc[next_date, "instrument_return"]
        if pd.isna(next_return):
            continue
        active.append(
            DailyCandidate(
                route=route,
                bucket=_bucket_for_route(route),
                date=date,
                target_symbol=route.target_symbol,
                underlying_symbol=route.underlying_symbol,
                instrument_return_next=float(next_return),
                gross_exposure=float(gross_exposure),
                base_score=_base_score_for_route(route),
                dynamic_multiplier=1.0,
                dynamic_score=_base_score_for_route(route),
                sqrt_dynamic_score=math.sqrt(max(_base_score_for_route(route), 0.0)),
                metrics=_dynamic_metrics(frame, route, date),
            )
        )

    by_bucket: dict[str, list[DailyCandidate]] = {}
    for candidate in active:
        by_bucket.setdefault(candidate.bucket, []).append(candidate)

    adjusted: list[DailyCandidate] = []
    for bucket_candidates in by_bucket.values():
        multipliers = _dynamic_multipliers(bucket_candidates)
        for idx, candidate in enumerate(bucket_candidates):
            multiplier = multipliers.get(idx, 1.0)
            dynamic_score = candidate.base_score * multiplier
            sqrt_dynamic_score = math.sqrt(max(candidate.base_score, 0.0)) * multiplier
            adjusted.append(
                DailyCandidate(
                    route=candidate.route,
                    bucket=candidate.bucket,
                    date=candidate.date,
                    target_symbol=candidate.target_symbol,
                    underlying_symbol=candidate.underlying_symbol,
                    instrument_return_next=candidate.instrument_return_next,
                    gross_exposure=candidate.gross_exposure,
                    base_score=candidate.base_score,
                    dynamic_multiplier=multiplier,
                    dynamic_score=dynamic_score,
                    sqrt_dynamic_score=sqrt_dynamic_score,
                    metrics=candidate.metrics,
                )
            )
    return adjusted


def _dedupe_same_underlying(candidates: list[DailyCandidate]) -> list[DailyCandidate]:
    tactical_underlyings = {
        candidate.underlying_symbol
        for candidate in candidates
        if candidate.bucket == RECOMMENDATION_BUCKET_TACTICAL
    }
    return [
        candidate
        for candidate in candidates
        if not (
            candidate.bucket == RECOMMENDATION_BUCKET_CORE_STOCK
            and candidate.underlying_symbol in tactical_underlyings
        )
    ]


def _score(candidate: DailyCandidate, mode: str) -> float:
    if mode == "static_score":
        return candidate.base_score
    if mode == "dynamic_score":
        return candidate.dynamic_score
    if mode == "dynamic_sqrt_score":
        return candidate.sqrt_dynamic_score
    raise ValueError(f"unsupported mode: {mode}")


def _target_weights(candidates: list[DailyCandidate], *, mode: str) -> dict[str, float]:
    candidates = _dedupe_same_underlying(candidates)
    weights: dict[str, float] = {}
    for bucket in (RECOMMENDATION_BUCKET_TACTICAL, RECOMMENDATION_BUCKET_CORE_STOCK):
        bucket_candidates = [candidate for candidate in candidates if candidate.bucket == bucket]
        scores = [max(0.0, _score(candidate, mode)) for candidate in bucket_candidates]
        total_score = sum(scores)
        if total_score <= 0:
            if not bucket_candidates:
                continue
            scores = [1.0 for _ in bucket_candidates]
            total_score = float(len(bucket_candidates))
        bucket_budget = float(RECOMMENDATION_BUCKET_BUDGETS[bucket])
        for candidate, score in zip(bucket_candidates, scores, strict=True):
            sleeve_target = bucket_budget * score / total_score
            account_weight = min(sleeve_target, candidate.gross_exposure)
            if account_weight <= 0:
                continue
            weights[candidate.target_symbol] = weights.get(candidate.target_symbol, 0.0) + account_weight
    return weights


def _performance_row(result: BacktestResult) -> dict[str, Any]:
    returns = result.returns.dropna()
    equity = (1.0 + returns).cumprod()
    years = (returns.index[-1] - returns.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1.0 / years) - 1.0
    drawdown = equity / equity.cummax() - 1.0
    volatility = returns.std()
    sharpe = returns.mean() / volatility * math.sqrt(252.0) if volatility > 0 else float("nan")
    return {
        "mode": result.name,
        "cagr": format_percent(float(cagr)),
        "max_drawdown": format_percent(float(drawdown.min())),
        "total_return": format_percent(float(equity.iloc[-1] - 1.0)),
        "sharpe": f"{float(sharpe):.2f}",
        "avg_cash": format_percent(result.avg_cash),
        "avg_top_weight": format_percent(result.avg_top_weight),
        "avg_tactical_active_count": f"{result.avg_active_count:.2f}",
        "rebalance_days": result.switches,
    }


def _leader_rows(result: BacktestResult) -> list[dict[str, Any]]:
    total = sum(result.leader_counts.values()) or 1
    return [
        {
            "mode": result.name,
            "leader": symbol,
            "days": days,
            "share": format_percent(days / total),
        }
        for symbol, days in sorted(result.leader_counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _current_mags7_routes() -> tuple[ToolChoiceRouteConfig, ...]:
    return tuple(
        route
        for route in ROUTES
        if route.group == GROUP_MAGS7 and route.side == "long" and route.tool in {"stock_long", "long2"}
    )


def _download_market_data(
    *,
    routes: tuple[ToolChoiceRouteConfig, ...],
    download_start: str,
    end: str,
) -> dict[str, pd.Series]:
    symbols = {"QQQ", *MAGS7_UNDERLYINGS}
    for route in routes:
        symbols.add(route.target_symbol)

    market_data: dict[str, pd.Series] = {}
    for symbol in sorted(symbols):
        if symbol == "QQQ":
            market_data[symbol] = download_nasdaq_close(symbol, assetclass="etf", start=download_start, end=end)
        elif symbol in MAGS7_UNDERLYINGS:
            market_data[symbol] = download_nasdaq_close(symbol, assetclass="stocks", start=download_start, end=end)
        else:
            start = MAGS7_ETF_STARTS.get(symbol, pd.Timestamp(download_start)).date().isoformat()
            market_data[symbol] = download_nasdaq_close(symbol, assetclass="etf", start=start, end=end)
    return market_data


def _build_route_frames(
    *,
    routes: tuple[ToolChoiceRouteConfig, ...],
    market_data: dict[str, pd.Series],
    as_of: str,
) -> dict[ToolChoiceRouteConfig, pd.DataFrame]:
    return {route: _build_route_frame(route, market_data, as_of=as_of) for route in routes}


def _common_dates(
    *,
    route_frames: dict[ToolChoiceRouteConfig, pd.DataFrame],
    start: str,
) -> pd.DatetimeIndex:
    common_dates = None
    for frame in route_frames.values():
        common_dates = frame.index if common_dates is None else common_dates.intersection(frame.index)
    if common_dates is None:
        raise RuntimeError("No common date index")
    common_dates = common_dates[common_dates >= pd.Timestamp(start)]
    if len(common_dates) < 2:
        raise RuntimeError(f"Not enough common dates from {start}")
    return common_dates


def _top_symbols_for_overlay(overlay: str, score_row: pd.Series) -> set[str] | None:
    if overlay == "none":
        return None
    top_n = int(overlay.removeprefix("top"))
    return set(score_row.dropna().sort_values(ascending=False).head(top_n).index)


def _run_backtest(
    *,
    overlay: str,
    mode: str,
    route_frames: dict[ToolChoiceRouteConfig, pd.DataFrame],
    dates: pd.DatetimeIndex,
    momentum_score: pd.DataFrame,
    cost_rate: float,
) -> BacktestResult:
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    weight_rows: list[dict[str, float]] = []
    previous_weights: dict[str, float] = {}
    leader_counts: dict[str, int] = {}
    active_counts: list[int] = []
    top_weights: list[float] = []
    cash_weights: list[float] = []
    switches = 0

    for idx in range(len(dates) - 1):
        date = dates[idx]
        next_date = dates[idx + 1]
        raw_candidates = _active_candidates_for_date(
            date=date,
            next_date=next_date,
            route_frames=route_frames,
        )
        allowed = _top_symbols_for_overlay(overlay, momentum_score.loc[date])
        if allowed is not None:
            raw_candidates = [
                candidate for candidate in raw_candidates if candidate.underlying_symbol in allowed
            ]
        candidates = _dedupe_same_underlying(raw_candidates)
        weights = _target_weights(candidates, mode=mode)

        weighted_return = 0.0
        by_symbol = {candidate.target_symbol: candidate for candidate in candidates}
        for symbol, weight in weights.items():
            weighted_return += weight * by_symbol[symbol].instrument_return_next

        all_symbols = set(previous_weights) | set(weights)
        turnover = sum(abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0)) for symbol in all_symbols)
        if turnover > 1e-9:
            switches += 1
        returns.append(weighted_return - turnover * cost_rate)
        return_dates.append(next_date)
        weight_rows.append(weights)
        previous_weights = weights

        tactical_candidates = [
            candidate for candidate in candidates if candidate.bucket != "core_stock_momentum"
        ]
        active_counts.append(len(tactical_candidates))
        if tactical_candidates:
            leader = max(tactical_candidates, key=lambda candidate: _score(candidate, mode))
            leader_counts[leader.underlying_symbol] = leader_counts.get(leader.underlying_symbol, 0) + 1
        top_weights.append(max(weights.values(), default=0.0))
        cash_weights.append(max(0.0, 1.0 - sum(weights.values())))

    return BacktestResult(
        name=mode,
        returns=pd.Series(returns, index=return_dates),
        weights=pd.DataFrame(weight_rows, index=return_dates).fillna(0.0),
        leader_counts=leader_counts,
        avg_active_count=float(np.mean(active_counts)) if active_counts else 0.0,
        avg_top_weight=float(np.mean(top_weights)) if top_weights else 0.0,
        avg_cash=float(np.mean(cash_weights)) if cash_weights else 1.0,
        switches=switches,
    )


def _calendar_rows(result: BacktestResult, *, overlay: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    returns = result.returns.dropna()
    for year, part in returns.groupby(returns.index.year):
        equity = (1.0 + part).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        volatility = part.std()
        sharpe = part.mean() / volatility * math.sqrt(252.0) if volatility > 0 else float("nan")
        rows.append(
            {
                "overlay": overlay,
                "mode": result.name,
                "year": int(year),
                "return": f"{float(equity.iloc[-1] - 1.0):.2%}",
                "max_drawdown": f"{float(drawdown.min()):.2%}",
                "sharpe": f"{float(sharpe):.2f}",
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    overlays = _parse_overlays(args.overlays)
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp(args.end).date().isoformat()
    cost_rate = args.cost_bps / 10_000.0

    routes = _current_mags7_routes()
    market_data = _download_market_data(routes=routes, download_start=args.download_start, end=end)
    route_frames = _build_route_frames(routes=routes, market_data=market_data, as_of=end)
    dates = _common_dates(route_frames=route_frames, start=args.start)

    close = _close_frame(market_data, MAGS7_UNDERLYINGS).reindex(dates).ffill()
    qqq = _normalize_close(market_data["QQQ"]).reindex(dates).ffill()
    momentum_score = _momentum_score_frame(
        close,
        qqq,
        variant=MomentumVariant("overlay_score", top_leverage=0, top_stock=0),
    )

    performance_rows: list[dict[str, Any]] = []
    calendar_rows: list[dict[str, Any]] = []
    leader_rows: list[dict[str, Any]] = []
    average_weight_frames: dict[str, pd.Series] = {}
    for overlay in overlays:
        for mode in BACKTEST_MODES:
            result = _run_backtest(
                overlay=overlay,
                mode=mode,
                route_frames=route_frames,
                dates=dates,
                momentum_score=momentum_score,
                cost_rate=cost_rate,
            )
            performance_row = {"overlay": overlay, **_performance_row(result)}
            returns = result.returns.dropna()
            performance_row["first_return_date"] = returns.index[0].date().isoformat()
            performance_row["latest_return_date"] = returns.index[-1].date().isoformat()
            performance_row["observations"] = len(returns)
            performance_rows.append(performance_row)
            calendar_rows.extend(_calendar_rows(result, overlay=overlay))
            leader_rows.extend({"overlay": overlay, **row} for row in _leader_rows(result))
            if mode == "dynamic_sqrt_score":
                average_weight_frames[overlay] = result.weights.mean().sort_values(ascending=False)

    performance_frame = pd.DataFrame(performance_rows)
    calendar_frame = pd.DataFrame(calendar_rows)
    leader_frame = pd.DataFrame(leader_rows)
    average_weight_frame = pd.concat(average_weight_frames, axis=1).fillna(0.0)
    average_weight_frame.index.name = "symbol"
    average_weight_frame = average_weight_frame.reset_index()
    for column in average_weight_frame.columns:
        if column != "symbol":
            average_weight_frame[column] = average_weight_frame[column].map(lambda value: f"{float(value):.2%}")

    paths = {
        "performance": results_dir / "mags7_specialist_momentum_overlay_performance.csv",
        "calendar_years": results_dir / "mags7_specialist_momentum_overlay_calendar_years.csv",
        "leaders": results_dir / "mags7_specialist_momentum_overlay_leaders.csv",
        "average_weights": results_dir / "mags7_specialist_momentum_overlay_average_weights.csv",
    }
    performance_frame.to_csv(paths["performance"], index=False)
    calendar_frame.to_csv(paths["calendar_years"], index=False)
    leader_frame.to_csv(paths["leaders"], index=False)
    average_weight_frame.to_csv(paths["average_weights"], index=False)

    summary_path = results_dir / "mags7_specialist_momentum_overlay_summary.md"
    summary_lines = [
        "# MAG7 Specialist + Unified Momentum Overlay",
        "",
        f"Window: `{args.start}` to requested `{end}`.",
        f"Trading cost: {args.cost_bps:.1f} bps per unit turnover.",
        "Overlay score is identical for every underlying: QQQ > SMA150, stock > SMA150, 60d momentum > 0, 120d momentum > 0, then rank by 20d/60d/120d momentum, risk-adjusted 60d momentum, and 60d relative strength vs QQQ.",
        "The overlay only decides which underlyings may receive allocation; tool choice and per-route volatility sizing still use the current specialist routes.",
        "",
        "## Performance",
        "",
        frame_to_markdown_table(performance_frame),
        "",
        "## Calendar Years",
        "",
        frame_to_markdown_table(calendar_frame),
        "",
        "## Tactical Leaders",
        "",
        frame_to_markdown_table(leader_frame),
        "",
        "## Average Weights",
        "",
        frame_to_markdown_table(average_weight_frame),
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    json_path = results_dir / "mags7_specialist_momentum_overlay_summary.json"
    json_path.write_text(
        json.dumps(
            {
                "requested_end": end,
                "performance": performance_frame.to_dict(orient="records"),
                "calendar_years": calendar_frame.to_dict(orient="records"),
                "leaders": leader_frame.to_dict(orient="records"),
                "average_weights": average_weight_frame.to_dict(orient="records"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    for label, path in paths.items():
        print(f"Wrote {label}: {path}")
    print(f"Wrote markdown summary: {summary_path}")
    print(f"Wrote json summary: {json_path}")
    print(performance_frame[performance_frame["mode"].eq("dynamic_sqrt_score")].to_string(index=False))


if __name__ == "__main__":
    main()
