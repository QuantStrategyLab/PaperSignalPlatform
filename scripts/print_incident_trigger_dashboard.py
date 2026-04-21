from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.operator_incident_dashboard import (
    build_incident_trigger_dashboard_message,
    summarize_incident_trigger_dashboard,
)
from application.operator_support import list_gcs_reconciliation_records, list_local_reconciliation_records
from notifications.telegram import TelegramNotificationPort


def main() -> None:
    parser = argparse.ArgumentParser(description="Print or send one incident trigger dashboard.")
    parser.add_argument("--backend", choices=("local_json", "gcs"), default="local_json")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / ".paper_signal" / "artifacts"))
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--project-id")
    parser.add_argument("--strategy-profile")
    parser.add_argument("--paper-account-group")
    parser.add_argument("--period", choices=("daily", "weekly", "custom"), default="daily")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--period-label")
    parser.add_argument("--region-code", default=os.getenv("INCIDENT_REGION", "sg"))
    parser.add_argument("--max-triggers", type=int, default=15)
    parser.add_argument("--lang", default=os.getenv("NOTIFY_LANG", "en"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--tg-token", default=os.getenv("TELEGRAM_TOKEN"))
    parser.add_argument("--tg-chat-id", default=os.getenv("GLOBAL_TELEGRAM_CHAT_ID"))
    args = parser.parse_args()

    start_date, end_date, default_period_label = _resolve_window(
        period=args.period,
        as_of=args.as_of,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    period_label = (args.period_label or "").strip() or default_period_label

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
    message = build_incident_trigger_dashboard_message(
        records,
        period_label=period_label,
        start_date=start_date,
        end_date=end_date,
        region_code=args.region_code,
        lang=args.lang,
        max_triggers=args.max_triggers,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "source": source,
                    "period": period_label,
                    "start_date": start_date,
                    "end_date": end_date,
                    "region_code": args.region_code,
                    "dashboard": summarize_incident_trigger_dashboard(
                        records,
                        start_date=start_date,
                        end_date=end_date,
                        region_code=args.region_code,
                        max_triggers=args.max_triggers,
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
    period: str,
    as_of: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str, str]:
    if period == "custom":
        if not start_date or not end_date:
            raise SystemExit("--period=custom requires --start-date and --end-date")
        return start_date, end_date, f"custom {start_date} -> {end_date}"

    as_of_date = _parse_date(as_of)
    if period == "daily":
        resolved = as_of_date.isoformat()
        return resolved, resolved, f"daily {resolved}"

    resolved_end = as_of_date.isoformat()
    resolved_start = (as_of_date - timedelta(days=6)).isoformat()
    return resolved_start, resolved_end, f"weekly {resolved_end}"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    main()
