"""Backward-compatible MAGS7 adapter for the signal notifier pattern.

The old entrypoint was NVDL-only. It now delegates to the MAGS7 slice of the
grouped tool-choice strategy so the deployed MAGS job uses the specialist
per-underlying entry rules plus stock/leveraged tool selection.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from signal_notifier.signal_notifier_core import (
    DEFAULT_HTTP_TIMEOUT,
    fetch_json,
    read_json_snapshot,
    send_telegram_message,
    write_json_snapshot,
)


NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

DEFAULT_NVDA_START = "2015-01-02"
DEFAULT_NVDL_START = "2022-12-13"
DEFAULT_LOOKBACK_DAYS = 900
DEFAULT_SIGNAL_GROUP_ZH = "MAGS7"
DEFAULT_SIGNAL_GROUP_EN = "MAGS7"


def _clean_price(value: object) -> float:
    return float(str(value).replace("$", "").replace(",", "").strip())


def download_nasdaq_close(symbol: str, *, assetclass: str, start: str, end: str) -> pd.Series:
    url = (
        f"https://api.nasdaq.com/api/quote/{symbol.upper()}/historical"
        f"?assetclass={assetclass}&fromdate={start}&limit=9999&todate={end}"
    )
    payload = fetch_json(url, headers=NASDAQ_HEADERS)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    if not rows:
        raise RuntimeError(f"No Nasdaq historical rows returned for {symbol}")

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime([row["date"] for row in rows], format="%m/%d/%Y"),
            "close": [_clean_price(row["close"]) for row in rows],
        }
    )
    return frame.sort_values("date").set_index("date")["close"]


def fetch_nvdl_long_market_data(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> dict[str, pd.Series]:
    from signal_notifier.grouped_tool_choice_notify import GROUP_MAGS7, fetch_grouped_tool_choice_market_data

    market_data = fetch_grouped_tool_choice_market_data(
        as_of=as_of,
        lookback_days=lookback_days,
        groups=(GROUP_MAGS7,),
        mags7_universe=mags7_universe,
    )
    if "NVDA" in market_data:
        market_data["nvda_close"] = market_data["NVDA"]
    if "NVDL" in market_data:
        market_data["nvdl_close"] = market_data["NVDL"]
    return market_data


def compute_live_nvdl_long_signal(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    mags7_universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> Any:
    from signal_notifier.grouped_tool_choice_notify import GROUP_MAGS7, compute_live_grouped_tool_choice_signal

    return compute_live_grouped_tool_choice_signal(
        as_of=as_of,
        lookback_days=lookback_days,
        groups=(GROUP_MAGS7,),
        mags7_universe=mags7_universe,
    )


def build_nvdl_long_notification(
    signal: Any,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    from signal_notifier.grouped_tool_choice_notify import build_grouped_tool_choice_notification

    return build_grouped_tool_choice_notification(
        signal,
        lang=lang,
        reference_capital_usd=reference_capital_usd,
    )


def build_nvdl_long_log(
    signal: Any,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    from signal_notifier.grouped_tool_choice_notify import build_grouped_tool_choice_log

    return build_grouped_tool_choice_log(
        signal,
        lang=lang,
        reference_capital_usd=reference_capital_usd,
    )


def build_nvdl_long_snapshot(signal: Any) -> dict[str, Any]:
    from signal_notifier.grouped_tool_choice_notify import build_grouped_tool_choice_snapshot

    snapshot = build_grouped_tool_choice_snapshot(signal)
    snapshot["strategy_name"] = "mags7_tool_choice"
    snapshot["strategy_display_name_zh"] = "MAGS7工具选择策略"
    snapshot["strategy_display_name_en"] = "MAGS7 Tool Choice Strategy"
    return snapshot


def read_nvdl_long_snapshot(snapshot_path: str) -> dict[str, Any] | None:
    return read_json_snapshot(snapshot_path)


def _notification_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    from signal_notifier.grouped_tool_choice_notify import _notification_identity as grouped_identity

    return grouped_identity(snapshot)


def should_send_nvdl_long_notification(
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
) -> bool:
    from signal_notifier.grouped_tool_choice_notify import should_send_grouped_tool_choice_notification

    return should_send_grouped_tool_choice_notification(snapshot, previous_snapshot)


def write_nvdl_long_snapshot(snapshot: dict[str, Any], output_path: str) -> str:
    return write_json_snapshot(snapshot, output_path)


def send_nvdl_long_telegram_message(
    message: str,
    *,
    token: str,
    chat_id: str,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> None:
    send_telegram_message(
        message,
        token=token,
        chat_id=chat_id,
        timeout=timeout,
    )
