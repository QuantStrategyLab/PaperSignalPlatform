from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.operator_summary import build_operator_summary_message, summarize_reconciliation_records
from application.operator_support import list_local_reconciliation_records
from notifications.telegram import TelegramNotificationPort


def main() -> None:
    parser = argparse.ArgumentParser(description="Print or send one daily/weekly operator summary.")
    parser.add_argument("--backend", choices=("local_json", "gcs"), default="local_json")
    parser.add_argument(
        "--artifact-dir",
        default=str(REPO_ROOT / ".paper_signal" / "artifacts"),
    )
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--project-id")
    parser.add_argument("--strategy-profile")
    parser.add_argument("--paper-account-group")
    parser.add_argument("--period", choices=("daily", "weekly", "custom"), default="daily")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--max-books", type=int, default=10)
    parser.add_argument("--lang", default=os.getenv("NOTIFY_LANG", "en"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--tg-token", default=os.getenv("TELEGRAM_TOKEN"))
    parser.add_argument("--tg-chat-id", default=os.getenv("GLOBAL_TELEGRAM_CHAT_ID"))
    args = parser.parse_args()

    start_date, end_date, period_label = _resolve_window(
        period=args.period,
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
        records = [payload for _, payload in loaded]
    else:
        if not args.bucket:
            raise SystemExit("--bucket is required when --backend=gcs")
        source = args.bucket
        records = _list_gcs_reconciliation_records(
            bucket_name=args.bucket,
            prefix=args.prefix,
            project_id=args.project_id,
            strategy_profile=args.strategy_profile,
            paper_account_group=args.paper_account_group,
            start_date=start_date,
            end_date=end_date,
        )

    message = build_operator_summary_message(
        records,
        period_label=period_label,
        start_date=start_date,
        end_date=end_date,
        lang=args.lang,
        max_books=args.max_books,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "source": source,
                    "period": period_label,
                    "start_date": start_date,
                    "end_date": end_date,
                    "summary": summarize_reconciliation_records(
                        records,
                        start_date=start_date,
                        end_date=end_date,
                        max_books=args.max_books,
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


def _list_gcs_reconciliation_records(
    *,
    bucket_name: str,
    prefix: str,
    project_id: str | None,
    strategy_profile: str | None,
    paper_account_group: str | None,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    from google.cloud import storage

    client = storage.Client(project=project_id) if project_id else storage.Client()
    records: list[tuple[str, str, dict[str, Any]]] = []
    for blob in client.list_blobs(bucket_name, prefix=prefix.strip("/") or None):
        if not blob.name.endswith(".json"):
            continue
        blob_date, file_name = _extract_blob_date_and_file_name(blob.name)
        if not blob_date:
            continue
        if blob_date < start_date or blob_date > end_date:
            continue
        if strategy_profile and not file_name.startswith(f"{strategy_profile}__"):
            continue
        if paper_account_group and not file_name.endswith(f"__{paper_account_group}.json"):
            continue
        records.append((blob_date, file_name, json.loads(blob.download_as_text())))

    records.sort(key=lambda item: (item[0], item[1]))
    return [payload for _, _, payload in records]


def _extract_blob_date_and_file_name(blob_name: str) -> tuple[str, str]:
    path = Path(blob_name)
    if len(path.parts) < 2:
        return "", path.name
    return path.parts[-2], path.name


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    main()
