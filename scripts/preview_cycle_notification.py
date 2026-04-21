from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.notification_renderers import build_cycle_notification_message
from application.operator_support import load_latest_local_reconciliation_record


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview the latest cycle notification.")
    parser.add_argument("--backend", choices=("local_json", "gcs"), default="local_json")
    parser.add_argument(
        "--artifact-dir",
        default=str(REPO_ROOT / ".paper_signal" / "artifacts"),
    )
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--strategy-profile")
    parser.add_argument("--paper-account-group")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.backend == "local_json":
        result = load_latest_local_reconciliation_record(
            args.artifact_dir,
            strategy_profile=args.strategy_profile,
            paper_account_group=args.paper_account_group,
        )
        if result is None:
            raise SystemExit("no local reconciliation artifact matched the filters")
        source_label = str(result[0])
        record = result[1]
    else:
        if not args.bucket:
            raise SystemExit("--bucket is required when --backend=gcs")
        source_label, record = _load_latest_gcs_reconciliation_record(
            bucket_name=args.bucket,
            prefix=args.prefix,
            strategy_profile=args.strategy_profile,
            paper_account_group=args.paper_account_group,
        )

    payload = dict(record.get("payload") or {})
    message = build_cycle_notification_message(payload, lang=args.lang)

    if args.json:
        print(
            json.dumps(
                {
                    "source": source_label,
                    "title": message.title,
                    "body": message.body,
                    "metadata": message.metadata,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    print(f"source: {source_label}")
    print("")
    print(message.title)
    print("")
    print(message.body)


def _load_latest_gcs_reconciliation_record(
    *,
    bucket_name: str,
    prefix: str,
    strategy_profile: str | None,
    paper_account_group: str | None,
) -> tuple[str, dict]:
    from google.cloud import storage

    client = storage.Client()
    candidates = []
    for blob in client.list_blobs(bucket_name, prefix=prefix.strip("/") or None):
        if not blob.name.endswith(".json"):
            continue
        file_name = Path(blob.name).name
        if strategy_profile and f"{strategy_profile}__" not in file_name:
            continue
        if paper_account_group and not file_name.endswith(f"__{paper_account_group}.json"):
            continue
        candidates.append(blob)

    if not candidates:
        raise SystemExit("no gcs reconciliation artifact matched the filters")

    latest_blob = max(
        candidates,
        key=lambda blob: (
            getattr(blob, "updated", None) or "",
            blob.name,
        ),
    )
    return latest_blob.name, json.loads(latest_blob.download_as_text())


if __name__ == "__main__":
    main()
