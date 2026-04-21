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

from application.operator_incident_actions import (
    build_google_authorized_session,
    execute_incident_review_action,
    plan_incident_review_actions,
)
from application.operator_incident_dashboard import summarize_incident_trigger_dashboard
from application.operator_support import list_gcs_reconciliation_records, list_local_reconciliation_records


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute incident review-pack job runs from incident trigger dashboard findings."
        )
    )
    parser.add_argument("--backend", choices=("local_json", "gcs"), default="local_json")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / ".paper_signal" / "artifacts"))
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--project-id", default=os.getenv("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--strategy-profile")
    parser.add_argument("--paper-account-group")
    parser.add_argument("--period", choices=("daily", "weekly", "custom"), default="daily")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--region-code", default=os.getenv("INCIDENT_REGION", "sg"))
    parser.add_argument("--max-triggers", type=int, default=15)
    parser.add_argument("--min-severity", choices=("all", "warning", "critical"), default="critical")
    parser.add_argument("--max-reviews", type=int, default=3)
    parser.add_argument("--region", default=os.getenv("REGION"))
    parser.add_argument("--review-job-name", default=os.getenv("INCIDENT_REVIEW_JOB_NAME"))
    parser.add_argument("--review-backend", choices=("local_json", "gcs"))
    parser.add_argument("--review-bucket")
    parser.add_argument("--review-prefix")
    parser.add_argument("--review-artifact-dir")
    parser.add_argument("--review-script-path", default=os.getenv("REVIEW_SCRIPT_PATH", "scripts/print_operator_review_pack.py"))
    parser.add_argument("--review-max-books", type=int, default=10)
    parser.add_argument("--review-max-events", type=int, default=20)
    parser.add_argument("--review-telegram-chat-id", default=os.getenv("GLOBAL_TELEGRAM_CHAT_ID"))
    parser.add_argument("--lang", default=os.getenv("NOTIFY_LANG", "en"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--no-review-send-telegram", action="store_true")
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not str(args.project_id or "").strip():
        raise SystemExit("--project-id is required")
    if not str(args.region or "").strip():
        raise SystemExit("--region is required")
    if not str(args.review_job_name or "").strip():
        raise SystemExit("--review-job-name is required")

    start_date, end_date, default_period_label = _resolve_window(
        period=args.period,
        as_of=args.as_of,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    loaded, source = _load_records(
        backend=args.backend,
        artifact_dir=args.artifact_dir,
        bucket=args.bucket,
        prefix=args.prefix,
        project_id=args.project_id,
        strategy_profile=args.strategy_profile,
        paper_account_group=args.paper_account_group,
        start_date=start_date,
        end_date=end_date,
    )
    records = [payload for _, payload in loaded]
    dashboard_summary = summarize_incident_trigger_dashboard(
        records,
        start_date=start_date,
        end_date=end_date,
        region_code=args.region_code,
        max_triggers=args.max_triggers,
    )

    normalized_review_backend = args.review_backend or args.backend
    actions = plan_incident_review_actions(
        dashboard_summary,
        project_id=str(args.project_id).strip(),
        region=str(args.region).strip(),
        review_job_name=str(args.review_job_name).strip(),
        min_severity=args.min_severity,
        max_reviews=args.max_reviews,
        review_backend=normalized_review_backend,
        review_bucket=args.review_bucket or args.bucket,
        review_prefix=args.review_prefix if args.review_prefix is not None else args.prefix,
        review_artifact_dir=args.review_artifact_dir or args.artifact_dir,
        review_script_path=args.review_script_path,
        review_max_books=args.review_max_books,
        review_max_events=args.review_max_events,
        review_send_telegram=not args.no_review_send_telegram,
        review_telegram_chat_id=args.review_telegram_chat_id,
        notify_lang=args.lang,
    )

    executed_actions: list[dict[str, object]] = []
    if args.execute and actions:
        session = build_google_authorized_session()
        for action in actions:
            executed_actions.append(
                execute_incident_review_action(
                    action,
                    authorized_session=session,
                    timeout_sec=args.timeout_sec,
                )
            )

    payload = {
        "source": source,
        "period": default_period_label,
        "start_date": start_date,
        "end_date": end_date,
        "region_code": args.region_code,
        "dashboard": dashboard_summary,
        "planned_actions": actions,
        "executed_actions": executed_actions,
        "executed": bool(args.execute),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"source: {source}")
    print(f"window: {start_date} -> {end_date}")
    print(f"dashboard_period: {default_period_label}")
    print(
        "triggers: "
        f"{dashboard_summary.get('trigger_count', 0)} total / "
        f"{dashboard_summary.get('critical_trigger_count', 0)} critical / "
        f"{dashboard_summary.get('warning_trigger_count', 0)} warning"
    )
    print("")
    if actions:
        print("planned_actions:")
        for action in actions:
            print(
                "- "
                f"{action.get('incident_id')} | {action.get('severity')} | "
                f"{action.get('strategy_profile')} | {action.get('paper_account_group')} | "
                f"{action.get('start_date')} -> {action.get('end_date')}"
            )
    else:
        print("planned_actions: none")

    if args.execute:
        print("")
        if executed_actions:
            print("executed_actions:")
            for item in executed_actions:
                print(f"- {item.get('incident_id')}: {item.get('operation_name')}")
        else:
            print("executed_actions: none")


def _load_records(
    *,
    backend: str,
    artifact_dir: str,
    bucket: str | None,
    prefix: str,
    project_id: str | None,
    strategy_profile: str | None,
    paper_account_group: str | None,
    start_date: str,
    end_date: str,
):
    if backend == "local_json":
        loaded = list_local_reconciliation_records(
            artifact_dir,
            strategy_profile=strategy_profile,
            paper_account_group=paper_account_group,
            start_date=start_date,
            end_date=end_date,
        )
        return loaded, artifact_dir

    if not bucket:
        raise SystemExit("--bucket is required when --backend=gcs")
    loaded = list_gcs_reconciliation_records(
        bucket_name=bucket,
        prefix=prefix,
        project_id=project_id,
        strategy_profile=strategy_profile,
        paper_account_group=paper_account_group,
        start_date=start_date,
        end_date=end_date,
    )
    return loaded, bucket


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
