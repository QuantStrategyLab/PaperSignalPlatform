"""COIN-specific adapter for the generic brokerless signal notifier pattern."""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from typing import Any

import pandas as pd

from signal_notifier.coin_short_hold_vt50 import (
    CoinShortHoldVT50Signal,
    compute_coin_short_hold_vt50_signal,
)
from signal_notifier.signal_notifier_core import (
    DEFAULT_HTTP_TIMEOUT,
    build_notification_identity,
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

DEFAULT_IPO_START = "2021-04-14"
DEFAULT_CONL_START = "2022-08-09"
DEFAULT_CONI_START = "2024-09-01"
DEFAULT_LOOKBACK_DAYS = 900
DEFAULT_SIGNAL_GROUP_ZH = "加密货币"
DEFAULT_SIGNAL_GROUP_EN = "Crypto"


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


def download_coinbase_daily_close(product: str, *, start: str, end: str) -> pd.Series:
    start_dt = pd.Timestamp(start).tz_localize("UTC")
    end_dt = pd.Timestamp(end).tz_localize("UTC")
    chunk = timedelta(days=300)
    parts: list[pd.DataFrame] = []
    cursor = start_dt

    while cursor < end_dt:
        chunk_end = min(cursor + chunk, end_dt)
        params = urllib.parse.urlencode(
            {
                "granularity": 86400,
                "start": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        url = f"https://api.exchange.coinbase.com/products/{product}/candles?{params}"
        payload = fetch_json(url, headers={"User-Agent": "Mozilla/5.0"})
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected Coinbase payload for {product}: {payload}")
        if not payload:
            cursor = chunk_end
            continue

        frame = pd.DataFrame(payload, columns=["time", "low", "high", "open", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["time"], unit="s", utc=True).dt.tz_convert(None).dt.normalize()
        parts.append(frame[["date", "close"]].sort_values("date").drop_duplicates("date"))
        cursor = chunk_end

    if not parts:
        raise RuntimeError(f"No Coinbase candle rows returned for {product}")
    return pd.concat(parts).drop_duplicates("date").sort_values("date").set_index("date")["close"]


def fetch_coin_short_hold_market_data(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, pd.Series]:
    as_of_ts = (
        pd.Timestamp(as_of).tz_localize(None).normalize()
        if as_of is not None
        else pd.Timestamp.utcnow().tz_localize(None).normalize()
    )
    start_ts = max(pd.Timestamp(DEFAULT_IPO_START), as_of_ts - pd.Timedelta(days=lookback_days))
    start = start_ts.date().isoformat()
    end = as_of_ts.date().isoformat()
    coin = download_nasdaq_close("COIN", assetclass="stocks", start=start, end=end)
    btc = download_coinbase_daily_close("BTC-USD", start=start, end=end)

    conl_start = max(pd.Timestamp(DEFAULT_CONL_START), start_ts).date().isoformat()
    coni_start = max(pd.Timestamp(DEFAULT_CONI_START), start_ts).date().isoformat()
    conl = download_nasdaq_close("CONL", assetclass="etf", start=conl_start, end=end)
    coni = download_nasdaq_close("CONI", assetclass="etf", start=coni_start, end=end)
    return {
        "coin_close": coin,
        "btc_close": btc,
        "long_close": conl,
        "short_close": coni,
    }


def compute_live_coin_short_hold_signal(
    *,
    as_of: str | pd.Timestamp | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> CoinShortHoldVT50Signal:
    market_data = fetch_coin_short_hold_market_data(as_of=as_of, lookback_days=lookback_days)
    return compute_coin_short_hold_vt50_signal(
        market_data["coin_close"],
        market_data["btc_close"],
        as_of=as_of,
        long_close=market_data["long_close"],
        short_close=market_data["short_close"],
    )


def build_coin_short_hold_notification(
    signal: CoinShortHoldVT50Signal,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    payload = build_coin_short_hold_snapshot(signal)
    group = DEFAULT_SIGNAL_GROUP_ZH if lang == "zh" else DEFAULT_SIGNAL_GROUP_EN
    if lang == "zh":
        action = {"long": "做多", "short": "做空", "cash": "空仓"}.get(payload["side"], "空仓")
        target_detail = f" {payload['target_symbol']}" if payload["target_symbol"] else ""
        return (
            f"【{group}】\n"
            f"COIN: {action}{target_detail} / 仓位 {payload['gross_exposure']:.2%}"
        )

    action = {"long": "long", "short": "short", "cash": "cash"}.get(payload["side"], "cash")
    target_detail = f" {payload['target_symbol']}" if payload["target_symbol"] else ""
    return (
        f"[{group}]\n"
        f"COIN: {action}{target_detail} / position {payload['gross_exposure']:.2%}"
    )


def build_coin_short_hold_log(
    signal: CoinShortHoldVT50Signal,
    *,
    lang: str = "zh",
    reference_capital_usd: float | None = None,
) -> str:
    payload = build_coin_short_hold_snapshot(signal)
    strategy_config = payload["diagnostics"].get("strategy_config") or {}
    coin_sma_window = int(strategy_config.get("coin_sma") or 150)
    btc_ma_window = int(strategy_config.get("btc_ma") or 50)
    group = DEFAULT_SIGNAL_GROUP_ZH if lang == "zh" else DEFAULT_SIGNAL_GROUP_EN
    if lang == "zh":
        if not signal.ready:
            return (
                "COIN 短持双向 vt_50 策略日志\n"
                f"分组: {group}\n"
                f"日期: {payload['as_of']}\n"
                f"原因: {payload['diagnostics'].get('reason', 'insufficient_history')}\n"
                f"已准备K线: {payload['diagnostics'].get('ready_bars', 0)}"
            )
        return (
            "COIN 短持双向 vt_50 策略日志\n"
            f"分组: {group}\n"
            f"日期: {payload['as_of']}\n"
            f"目标: {payload['target_symbol'] or 'CASH'} / {payload['side']} / {payload['gross_exposure']:.2%}\n"
            f"目标仓位: {payload['gross_exposure']:.2%}\n"
            f"标的: {payload['target_symbol'] or 'CASH'}\n"
            f"COIN 收盘/SMA{coin_sma_window}: {payload['diagnostics'].get('coin_close', 0.0):.2f} / "
            f"{payload['diagnostics'].get('coin_sma', 0.0):.2f}\n"
            f"COIN 5日动量: {payload['diagnostics'].get('coin_momentum', 0.0):.2%}\n"
            f"COIN RV20: {payload['diagnostics'].get('coin_rv_20', 0.0):.2%}\n"
            f"BTC(滞后1日)/MA{btc_ma_window}: {payload['diagnostics'].get('btc_close_lagged', 0.0):.2f} / "
            f"{payload['diagnostics'].get('btc_ma', 0.0):.2f}\n"
            f"双向RV20(前值): {payload['diagnostics'].get('dual_rv_20_prev', 0.0):.2%}\n"
            f"vol scale: {payload['diagnostics'].get('vol_scale', 0.0):.2%}"
        )

    if not signal.ready:
        return (
            "COIN short-hold vt_50 strategy log\n"
            f"group: {group}\n"
            f"date: {payload['as_of']}\n"
            f"reason: {payload['diagnostics'].get('reason', 'insufficient_history')}\n"
            f"ready_bars: {payload['diagnostics'].get('ready_bars', 0)}"
        )
    return (
        "COIN short-hold vt_50 strategy log\n"
        f"group: {group}\n"
        f"date: {payload['as_of']}\n"
        f"target: {payload['target_symbol'] or 'CASH'} / {payload['side']} / {payload['gross_exposure']:.2%}\n"
        f"target position: {payload['gross_exposure']:.2%}\n"
        f"symbol: {payload['target_symbol'] or 'CASH'}\n"
        f"COIN close/SMA{coin_sma_window}: {payload['diagnostics'].get('coin_close', 0.0):.2f} / "
        f"{payload['diagnostics'].get('coin_sma', 0.0):.2f}\n"
        f"COIN 5d momentum: {payload['diagnostics'].get('coin_momentum', 0.0):.2%}\n"
        f"COIN RV20: {payload['diagnostics'].get('coin_rv_20', 0.0):.2%}\n"
        f"BTC(lagged 1d)/MA{btc_ma_window}: {payload['diagnostics'].get('btc_close_lagged', 0.0):.2f} / "
        f"{payload['diagnostics'].get('btc_ma', 0.0):.2f}\n"
        f"dual RV20(prev): {payload['diagnostics'].get('dual_rv_20_prev', 0.0):.2%}\n"
        f"vol scale: {payload['diagnostics'].get('vol_scale', 0.0):.2%}"
    )


def build_coin_short_hold_snapshot(signal: CoinShortHoldVT50Signal) -> dict[str, Any]:
    diagnostics = dict(signal.diagnostics)
    snapshot = {
        "as_of": signal.as_of.date().isoformat(),
        "effective_after_trading_days": signal.effective_after_trading_days,
        "ready": bool(signal.ready),
        "target_weights": dict(signal.target_weights),
        "side": signal.side,
        "target_symbol": signal.target_symbol,
        "gross_exposure": float(signal.gross_exposure),
        "state_position": int(signal.state_position),
        "held_days": int(signal.held_days),
        "entry_reference_price": signal.entry_reference_price,
        "diagnostics": diagnostics,
        "strategy_config": diagnostics.get("strategy_config") or {},
    }
    return snapshot


def read_coin_short_hold_snapshot(snapshot_path: str) -> dict[str, Any] | None:
    return read_json_snapshot(snapshot_path)


def _notification_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(snapshot.get("diagnostics") or {})
    return build_notification_identity(
        snapshot,
        extra_keys={"reason": diagnostics.get("reason")},
    )


def should_send_coin_short_hold_notification(
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
) -> bool:
    if previous_snapshot is None:
        return True
    return _notification_identity(snapshot) != _notification_identity(previous_snapshot)


def write_coin_short_hold_snapshot(snapshot: dict[str, Any], output_path: str) -> str:
    return write_json_snapshot(snapshot, output_path)


def send_coin_short_hold_telegram_message(
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
