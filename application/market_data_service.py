from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import pandas as pd
from quant_platform_kit import build_semiconductor_rotation_inputs_from_history


class DailyBarProvider(Protocol):
    def fetch_daily_bars(
        self,
        symbols: tuple[str, ...],
        *,
        as_of_date: pd.Timestamp,
        lookback_days: int,
    ) -> dict[str, pd.DataFrame]:
        """Return daily OHLCV bars keyed by symbol."""


@dataclass(frozen=True)
class YFinanceDailyBarProvider(DailyBarProvider):
    auto_adjust: bool = False

    def fetch_daily_bars(
        self,
        symbols: tuple[str, ...],
        *,
        as_of_date: pd.Timestamp,
        lookback_days: int,
    ) -> dict[str, pd.DataFrame]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is required for PAPER_SIGNAL_MARKET_DATA_PROVIDER=yfinance"
            ) from exc

        start_date = pd.Timestamp(as_of_date).normalize() - pd.Timedelta(days=int(lookback_days))
        end_date = pd.Timestamp(as_of_date).normalize() + pd.Timedelta(days=2)
        bars_by_symbol: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            frame = yf.download(
                tickers=symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=self.auto_adjust,
                progress=False,
                threads=False,
            )
            bars_by_symbol[symbol] = normalize_daily_bars(frame)
        return bars_by_symbol


def normalize_daily_bars(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None).normalize()
    for column in ("open", "high", "low", "close", "volume"):
        if column not in normalized.columns:
            normalized[column] = pd.NA
    return normalized[["open", "high", "low", "close", "volume"]].sort_index()


def build_close_history_loader(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    bar_provider: DailyBarProvider | None = None,
    as_of_date: pd.Timestamp | None = None,
    lookback_days: int | None = None,
) -> Callable[..., pd.Series]:
    def _load_close_series(*args, **kwargs):
        symbol = _extract_history_symbol(args, kwargs)
        if not symbol:
            return pd.Series(dtype=float)

        frame = bars_by_symbol.get(symbol)
        if (
            (frame is None or frame.empty)
            and bar_provider is not None
            and as_of_date is not None
            and lookback_days is not None
        ):
            fetched = bar_provider.fetch_daily_bars(
                (symbol,),
                as_of_date=pd.Timestamp(as_of_date).normalize(),
                lookback_days=int(lookback_days),
            )
            frame = fetched.get(symbol)
            if frame is not None:
                bars_by_symbol[symbol] = frame.copy()
        if frame is None or frame.empty:
            return pd.Series(dtype=float)
        return frame["close"].dropna().astype(float)

    return _load_close_series


def build_ohlcv_history_records(frame: pd.DataFrame) -> list[dict[str, float | str]]:
    if frame is None or frame.empty:
        return []
    normalized = normalize_daily_bars(frame)
    payload = normalized.reset_index().rename(columns={"index": "as_of"})
    payload["as_of"] = pd.to_datetime(payload["as_of"]).dt.strftime("%Y-%m-%d")
    return payload.to_dict("records")


def build_semiconductor_indicator_inputs(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    trend_ma_window: int,
) -> dict[str, dict[str, dict[str, float]]]:
    soxl_frame = bars_by_symbol.get("SOXL")
    soxx_frame = bars_by_symbol.get("SOXX")
    if soxl_frame is None or soxl_frame.empty or soxx_frame is None or soxx_frame.empty:
        raise ValueError("Semiconductor indicator inputs require SOXL and SOXX daily bars")
    return build_semiconductor_rotation_inputs_from_history(
        soxl_history=soxl_frame["close"],
        soxx_history=soxx_frame["close"],
        trend_ma_window=trend_ma_window,
    )


def latest_available_session(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.Timestamp:
    sessions = [frame.index[-1] for frame in bars_by_symbol.values() if frame is not None and not frame.empty]
    if not sessions:
        raise ValueError("No market data sessions available")
    return max(pd.Timestamp(value).normalize() for value in sessions)


def resolve_effective_session(
    *,
    effective_date: str | pd.Timestamp,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.Timestamp | None:
    target = pd.Timestamp(effective_date).normalize()
    candidate_dates: set[pd.Timestamp] = set()
    for frame in bars_by_symbol.values():
        if frame is None or frame.empty:
            continue
        candidate_dates.update(pd.Timestamp(index).normalize() for index in frame.index)
    eligible = sorted(value for value in candidate_dates if value >= target)
    if not eligible:
        return None
    return eligible[0]


def _extract_history_symbol(args, kwargs) -> str:
    raw_symbol = kwargs.get("symbol")
    if raw_symbol is None:
        if len(args) >= 2:
            raw_symbol = args[1]
        elif len(args) >= 1:
            raw_symbol = args[0]
    return str(raw_symbol or "").strip().upper()
