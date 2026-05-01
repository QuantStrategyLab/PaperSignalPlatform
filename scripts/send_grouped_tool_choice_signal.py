#!/usr/bin/env python3
"""Fetch grouped tool-choice strategy signals and optionally send Telegram."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_notifier.grouped_tool_choice_notify import (  # noqa: E402
    GROUP_CRYPTO_EN,
    GROUP_CRYPTO_ZH,
    GROUP_MAGS7,
    build_grouped_tool_choice_log,
    build_grouped_tool_choice_notification,
    build_grouped_tool_choice_snapshot,
    compute_live_grouped_tool_choice_signal,
    parse_mags7_universe,
    read_grouped_tool_choice_snapshot,
    send_grouped_tool_choice_telegram_message,
    should_send_grouped_tool_choice_notification,
    write_grouped_tool_choice_snapshot,
)


def _parse_groups(raw: str | None) -> tuple[str, ...] | None:
    if not raw:
        return None
    groups: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if value.lower() == "crypto" or value == GROUP_CRYPTO_ZH:
            groups.append(GROUP_CRYPTO_ZH)
        elif value.upper() == GROUP_MAGS7:
            groups.append(GROUP_MAGS7)
        else:
            raise ValueError(f"Unsupported group: {value}")
    return tuple(dict.fromkeys(groups)) or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="Signal date in YYYY-MM-DD. Defaults to today UTC-normalized.")
    parser.add_argument("--lookback-days", type=int, default=900)
    parser.add_argument(
        "--groups",
        default=os.getenv("GROUPED_NOTIFY_GROUPS") or os.getenv("SIGNAL_NOTIFY_GROUPS"),
        help=f"Comma-separated groups. Supported: {GROUP_MAGS7}, {GROUP_CRYPTO_ZH}/{GROUP_CRYPTO_EN}. Defaults to all.",
    )
    parser.add_argument(
        "--mags7-universe",
        default=os.getenv("GROUPED_NOTIFY_MAGS7_UNIVERSE") or os.getenv("MAGS7_NOTIFY_UNIVERSE") or os.getenv("MAGS7_UNIVERSE"),
        help="Comma-separated current MAGS7 constituents. Only symbols with configured routes are eligible.",
    )
    parser.add_argument(
        "--lang",
        default=(
            os.getenv("GROUPED_NOTIFY_LANG")
            or os.getenv("SIGNAL_NOTIFY_LANG")
            or os.getenv("NOTIFY_LANG")
            or "zh"
        ),
    )
    parser.add_argument(
        "--reference-capital-usd",
        type=float,
        default=(
            float(os.getenv("GROUPED_NOTIFY_REFERENCE_CAPITAL_USD") or os.getenv("SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD"))
            if (os.getenv("GROUPED_NOTIFY_REFERENCE_CAPITAL_USD") or os.getenv("SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD"))
            else None
        ),
        help="Optional reference capital for future dollar hints. Current notification remains weight-only.",
    )
    parser.add_argument(
        "--json-out",
        default=os.getenv("GROUPED_NOTIFY_OUTPUT_PATH") or os.getenv("SIGNAL_NOTIFY_OUTPUT_PATH"),
    )
    parser.add_argument(
        "--state-file",
        default=os.getenv("GROUPED_NOTIFY_STATE_PATH") or os.getenv("SIGNAL_NOTIFY_STATE_PATH"),
    )
    parser.add_argument("--skip-unchanged", action="store_true", help="Skip Telegram send if the grouped signal has not changed.")
    parser.add_argument("--force-send", action="store_true", help="Send Telegram even when --skip-unchanged would suppress it.")
    parser.add_argument("--stdout-only", action="store_true", help="Print only; do not send Telegram even if env vars exist.")
    return parser.parse_args()


def resolve_telegram_settings() -> tuple[str | None, str | None]:
    token = (
        os.getenv("GROUPED_NOTIFY_TELEGRAM_TOKEN")
        or os.getenv("SIGNAL_NOTIFY_TELEGRAM_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
        or os.getenv("TG_TOKEN")
    )
    chat_id = (
        os.getenv("GROUPED_NOTIFY_TELEGRAM_CHAT_ID")
        or os.getenv("SIGNAL_NOTIFY_TELEGRAM_CHAT_ID")
        or os.getenv("GLOBAL_TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID")
    )
    return token, chat_id


def main() -> None:
    args = parse_args()
    groups = _parse_groups(args.groups)
    signal = compute_live_grouped_tool_choice_signal(
        as_of=args.as_of,
        lookback_days=args.lookback_days,
        groups=groups,
        mags7_universe=parse_mags7_universe(args.mags7_universe),
    )
    analysis_log = build_grouped_tool_choice_log(
        signal,
        lang=args.lang,
        reference_capital_usd=args.reference_capital_usd,
    )
    message = build_grouped_tool_choice_notification(
        signal,
        lang=args.lang,
        reference_capital_usd=args.reference_capital_usd,
    )
    snapshot = build_grouped_tool_choice_snapshot(signal)
    snapshot["notification_text"] = message
    snapshot["analysis_log"] = analysis_log
    previous_snapshot = read_grouped_tool_choice_snapshot(args.state_file) if args.state_file else None
    notification_changed = should_send_grouped_tool_choice_notification(snapshot, previous_snapshot)
    snapshot["notification_changed"] = notification_changed

    print(analysis_log, flush=True)
    print("telegram_notification:", flush=True)
    print(message, flush=True)

    if args.json_out:
        output_path = write_grouped_tool_choice_snapshot(snapshot, args.json_out)
        print(f"snapshot_written={output_path}", flush=True)
    if args.state_file:
        state_path = write_grouped_tool_choice_snapshot(snapshot, args.state_file)
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

    send_grouped_tool_choice_telegram_message(message, token=token, chat_id=chat_id)
    print("telegram_send=ok", flush=True)


if __name__ == "__main__":
    main()
