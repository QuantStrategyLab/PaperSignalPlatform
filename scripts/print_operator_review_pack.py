from __future__ import annotations

import argparse
import json
import os
import sys
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.operator_review_pack import (
    build_operator_review_pack_message,
    summarize_operator_review_pack,
)
from application.operator_support import list_gcs_reconciliation_records, list_local_reconciliation_records
from notifications.telegram import TelegramNotificationPort


def main() -> None:
    parser = argparse.ArgumentParser(description="Print or send one monthly or incident operator review pack.")
    parser.add_argument("--backend", choices=("local_json", "gcs"), default="local_json")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / ".paper_signal" / "artifacts"))
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--project-id")
    parser.add_argument("--strategy-profile")
    parser.add_argument("--paper-account-group")
    parser.add_argument("--review-type", choices=("monthly", "incident"), default="monthly")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--max-books", type=int, default=10)
    parser.add_argument("--max-events", type=int, default=15)
    parser.add_argument("--lang", default=os.getenv("NOTIFY_LANG", "en"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--tg-token", default=os.getenv("TELEGRAM_TOKEN"))
    parser.add_argument("--tg-chat-id", default=os.getenv("GLOBAL_TELEGRAM_CHAT_ID"))
    args = parser.parse_args()

    start_date, end_date, period_label = _resolve_window(
        review_type=args.review_type,
        as_of=args.as_of,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if args.backend == "local_json":
        loaded = list_local_reconciliation_records(
            args.artifact_dir,
            strategy_profile=args.strategy_profile,
            paper_account_group=args.paper_account_group,
            start_date=start_date,
            end_date=end_date,
        )
        source = args.artifact_dir
    else:
        if not args.bucket:
            raise SystemExit("--bucket is required when --backend=gcs")
        loaded = list_gcs_reconciliation_records(
            bucket_name=args.bucket,
            prefix=args.prefix,
            project_id=args.project_id,
            strategy_profile=args.strategy_profile,
            paper_account_group=args.paper_account_group,
            start_date=start_date,
            end_date=end_date,
        )
        source = args.bucket

    records = [payload for _, payload in loaded]
    message = build_operator_review_pack_message(
        records,
        review_type=args.review_type,
        period_label=period_label,
        start_date=start_date,
        end_date=end_date,
        lang=args.lang,
        max_books=args.max_books,
        max_events=args.max_events,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "source": source,
                    "review_type": args.review_type,
                    "period": period_label,
                    "start_date": start_date,
                    "end_date": end_date,
                    "pack": summarize_operator_review_pack(
                        records,
                        review_type=args.review_type,
                        start_date=start_date,
                        end_date=end_date,
                        max_books=args.max_books,
                        max_events=args.max_events,
                    ),
                    "title": message.title,
                    "body": message.body,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"source: {source}")
        print(f"window: {start_date} -> {end_date}")
        print("")
        print(message.title)
        print("")
        print(message.body)

    if args.send_telegram:
        if not args.tg_token or not args.tg_chat_id:
            raise SystemExit("--send-telegram requires --tg-token and --tg-chat-id (or env fallbacks)")
        TelegramNotificationPort(token=args.tg_token, chat_id=args.tg_chat_id).publish(message)


def _resolve_window(
    *,
    review_type: str,
    as_of: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str, str]:
    as_of_date = _parse_date(as_of)
    if review_type == "monthly":
        if start_date or end_date:
            resolved_start = start_date or as_of_date.replace(day=1).isoformat()
            resolved_end = end_date or as_of_date.isoformat()
        else:
            resolved_start = as_of_date.replace(day=1).isoformat()
            resolved_end = as_of_date.isoformat()
        return resolved_start, resolved_end, f"monthly {as_of_date:%Y-%m}"

    if start_date and end_date:
        return start_date, end_date, f"incident {start_date} -> {end_date}"
    resolved = as_of_date.isoformat()
    return resolved, resolved, f"incident {resolved}"


def _parse_date(value: str) -> date:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    last_day = monthrange(parsed.year, parsed.month)[1]
    if parsed.day > last_day:
        return parsed.replace(day=last_day)
    return parsed


if __name__ == "__main__":
    main()
