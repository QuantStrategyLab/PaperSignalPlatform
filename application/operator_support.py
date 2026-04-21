from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from application.state_store_service import PaperAccountState


def format_paper_account_state(
    state: PaperAccountState,
    *,
    lang: str = "en",
) -> str:
    labels = _labels(lang)
    lines = [
        f"{labels['account']}: {state.paper_account_group}",
        f"{labels['nav']}: {_format_money(state.nav)}",
        f"{labels['cash']}: {_format_money(state.cash)}",
    ]

    pending_plan = dict((state.metadata or {}).get("pending_plan") or {})
    if pending_plan.get("effective_date"):
        lines.append(f"{labels['pending_effective_date']}: {pending_plan.get('effective_date')}")

    lines.append(labels["positions_header"])
    if state.positions:
        for symbol, payload in sorted(state.positions.items()):
            quantity = float((payload or {}).get("quantity", 0.0) or 0.0)
            average_cost = (payload or {}).get("average_cost")
            line = f"- {symbol}: {labels['quantity']}={quantity:.4f}"
            if average_cost is not None:
                line += f", {labels['average_cost']}={_format_money(average_cost)}"
            lines.append(line)
    else:
        lines.append(labels["none"])

    metadata = dict(state.metadata or {})
    if metadata:
        lines.append(labels["metadata_header"])
        for key in (
            "last_run_as_of",
            "last_strategy_profile",
        ):
            if metadata.get(key) is not None:
                lines.append(f"- {key}: {metadata.get(key)}")
    return "\n".join(lines)


def load_latest_local_reconciliation_record(
    root_dir: str,
    *,
    strategy_profile: str | None = None,
    paper_account_group: str | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    matches = list_local_reconciliation_records(
        root_dir,
        strategy_profile=strategy_profile,
        paper_account_group=paper_account_group,
    )
    if not matches:
        return None
    return matches[-1]


def load_latest_gcs_reconciliation_record(
    *,
    bucket_name: str,
    prefix: str = "",
    project_id: str | None = None,
    strategy_profile: str | None = None,
    paper_account_group: str | None = None,
    storage_client: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    matches = list_gcs_reconciliation_records(
        bucket_name=bucket_name,
        prefix=prefix,
        project_id=project_id,
        strategy_profile=strategy_profile,
        paper_account_group=paper_account_group,
        storage_client=storage_client,
    )
    if not matches:
        return None
    return matches[-1]


def list_local_reconciliation_records(
    root_dir: str,
    *,
    strategy_profile: str | None = None,
    paper_account_group: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    root = Path(root_dir)
    if not root.exists():
        return []

    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in root.glob("*/*.json"):
        if not path.is_file():
            continue
        artifact_date = path.parent.name
        if start_date and artifact_date < start_date:
            continue
        if end_date and artifact_date > end_date:
            continue
        if strategy_profile and not path.name.startswith(f"{strategy_profile}__"):
            continue
        if paper_account_group and not path.name.endswith(f"__{paper_account_group}.json"):
            continue
        matches.append((path, json.loads(path.read_text(encoding="utf-8"))))

    return sorted(
        matches,
        key=lambda item: (
            item[0].parent.name,
            item[0].name,
        ),
    )


def list_gcs_reconciliation_records(
    *,
    bucket_name: str,
    prefix: str = "",
    project_id: str | None = None,
    strategy_profile: str | None = None,
    paper_account_group: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    storage_client: Any | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    if storage_client is None:
        from google.cloud import storage

        storage_client = storage.Client(project=project_id) if project_id else storage.Client()

    matches: list[tuple[str, dict[str, Any]]] = []
    normalized_prefix = prefix.strip("/") or None
    for blob in storage_client.list_blobs(bucket_name, prefix=normalized_prefix):
        if not getattr(blob, "name", "").endswith(".json"):
            continue
        blob_date, file_name = _extract_blob_date_and_file_name(str(blob.name))
        if start_date and blob_date and blob_date < start_date:
            continue
        if end_date and blob_date and blob_date > end_date:
            continue
        if strategy_profile and not file_name.startswith(f"{strategy_profile}__"):
            continue
        if paper_account_group and not file_name.endswith(f"__{paper_account_group}.json"):
            continue
        matches.append((str(blob.name), json.loads(blob.download_as_text())))

    return sorted(
        matches,
        key=lambda item: (
            _extract_blob_date_and_file_name(item[0])[0],
            Path(item[0]).name,
        ),
    )


def _extract_blob_date_and_file_name(blob_name: str) -> tuple[str, str]:
    path = Path(blob_name)
    if len(path.parts) < 2:
        return "", path.name
    return path.parts[-2], path.name


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${amount:,.2f}"


def _labels(lang: str) -> Mapping[str, str]:
    normalized = str(lang or "en").strip().lower()
    if normalized.startswith("zh"):
        return {
            "account": "账户组",
            "nav": "净值",
            "cash": "现金",
            "pending_effective_date": "待执行生效日",
            "positions_header": "当前持仓",
            "metadata_header": "运行元数据",
            "quantity": "数量",
            "average_cost": "成本",
            "none": "无",
        }
    return {
        "account": "Account Group",
        "nav": "NAV",
        "cash": "Cash",
        "pending_effective_date": "Pending Effective Date",
        "positions_header": "Positions",
        "metadata_header": "Metadata",
        "quantity": "qty",
        "average_cost": "avg_cost",
        "none": "none",
    }
