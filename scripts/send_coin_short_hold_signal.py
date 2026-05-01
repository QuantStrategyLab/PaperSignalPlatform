#!/usr/bin/env python3
"""Fetch the COIN short-hold vt_50 next-session signal and optionally send Telegram."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_notifier.coin_short_hold_notify import (  # noqa: E402
    build_coin_short_hold_log,
    build_coin_short_hold_notification,
    build_coin_short_hold_snapshot,
    compute_live_coin_short_hold_signal,
    read_coin_short_hold_snapshot,
    send_coin_short_hold_telegram_message,
    should_send_coin_short_hold_notification,
    write_coin_short_hold_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="Signal date in YYYY-MM-DD. Defaults to today UTC-normalized.")
    parser.add_argument("--lookback-days", type=int, default=900)
    parser.add_argument(
        "--lang",
        default=os.getenv("COIN_NOTIFY_LANG") or os.getenv("SIGNAL_NOTIFY_LANG") or os.getenv("NOTIFY_LANG") or "zh",
    )
    parser.add_argument(
        "--reference-capital-usd",
        type=float,
        default=(
            float(os.getenv("COIN_NOTIFY_REFERENCE_CAPITAL_USD") or os.getenv("SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD"))
            if (os.getenv("COIN_NOTIFY_REFERENCE_CAPITAL_USD") or os.getenv("SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD"))
            else None
        ),
        help="Optional reference capital for translating target weight into buy/sell dollar hints.",
    )
    parser.add_argument("--json-out", default=os.getenv("COIN_NOTIFY_OUTPUT_PATH") or os.getenv("SIGNAL_NOTIFY_OUTPUT_PATH"))
    parser.add_argument("--state-file", default=os.getenv("COIN_NOTIFY_STATE_PATH") or os.getenv("SIGNAL_NOTIFY_STATE_PATH"))
    parser.add_argument("--skip-unchanged", action="store_true", help="Skip Telegram send if the signal snapshot has not changed.")
    parser.add_argument("--force-send", action="store_true", help="Send Telegram even when --skip-unchanged would suppress it.")
    parser.add_argument("--stdout-only", action="store_true", help="Print only; do not send Telegram even if env vars exist.")
    return parser.parse_args()


def resolve_telegram_settings() -> tuple[str | None, str | None]:
    token = (
        os.getenv("COIN_NOTIFY_TELEGRAM_TOKEN")
        or os.getenv("SIGNAL_NOTIFY_TELEGRAM_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
        or os.getenv("TG_TOKEN")
    )
    chat_id = (
        os.getenv("COIN_NOTIFY_TELEGRAM_CHAT_ID")
        or os.getenv("SIGNAL_NOTIFY_TELEGRAM_CHAT_ID")
        or os.getenv("GLOBAL_TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID")
    )
    return token, chat_id


def main() -> None:
    args = parse_args()
    signal = compute_live_coin_short_hold_signal(as_of=args.as_of, lookback_days=args.lookback_days)
    analysis_log = build_coin_short_hold_log(
        signal,
        lang=args.lang,
        reference_capital_usd=args.reference_capital_usd,
    )
    message = build_coin_short_hold_notification(
        signal,
        lang=args.lang,
        reference_capital_usd=args.reference_capital_usd,
    )
    snapshot = build_coin_short_hold_snapshot(signal)
    snapshot["notification_text"] = message
    snapshot["analysis_log"] = analysis_log
    previous_snapshot = read_coin_short_hold_snapshot(args.state_file) if args.state_file else None
    notification_changed = should_send_coin_short_hold_notification(snapshot, previous_snapshot)
    snapshot["notification_changed"] = notification_changed

    print(analysis_log, flush=True)
    print("telegram_notification:", flush=True)
    print(message, flush=True)

    if args.json_out:
        output_path = write_coin_short_hold_snapshot(snapshot, args.json_out)
        print(f"snapshot_written={output_path}", flush=True)
    if args.state_file:
        state_path = write_coin_short_hold_snapshot(snapshot, args.state_file)
        print(f"state_written={state_path}", flush=True)

    token, chat_id = resolve_telegram_settings()
    if args.stdout_only:
        print("telegram_send=skipped:stdout_only", flush=True)
        return
    if args.skip_unchanged and not args.force_send and not notification_changed:
        print("telegram_send=skipped:unchanged_signal", flush=True)
        return
    if not token or not chat_id:
        print("telegram_send=skipped:missing_token_or_chat_id", flush=True)
        return

    send_coin_short_hold_telegram_message(
        message,
        token=token,
        chat_id=chat_id,
    )
    print("telegram_send=ok", flush=True)


if __name__ == "__main__":
    main()
