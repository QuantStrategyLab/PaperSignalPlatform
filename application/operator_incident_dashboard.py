from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from application.notification_service import NotificationMessage
from application.operator_review_pack import NORMAL_EXECUTION_STATUSES, NORMAL_QUEUE_STATUSES

MAX_TRIGGER_ROWS = 15


def summarize_incident_trigger_dashboard(
    records: Sequence[Mapping[str, Any]],
    *,
    start_date: str,
    end_date: str,
    region_code: str = "sg",
    max_triggers: int = MAX_TRIGGER_ROWS,
) -> dict[str, Any]:
    trigger_records_by_book: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    abnormal_queue_counts: dict[str, int] = {}
    abnormal_execution_counts: dict[str, int] = {}

    for raw_record in records:
        payload = dict(raw_record.get("payload") or {})
        strategy_profile = str(raw_record.get("strategy_profile") or payload.get("strategy_profile") or "").strip()
        paper_account_group = str(
            raw_record.get("paper_account_group") or payload.get("paper_account_group") or ""
        ).strip()
        if not strategy_profile or not paper_account_group:
            continue

        queue_status = str(payload.get("queue_status") or "").strip()
        execution_status = str(((payload.get("execution") or {}).get("status") or "")).strip()
        is_abnormal_queue = queue_status.lower() not in NORMAL_QUEUE_STATUSES
        is_abnormal_execution = execution_status.lower() not in NORMAL_EXECUTION_STATUSES
        if not (is_abnormal_queue or is_abnormal_execution):
            continue

        if is_abnormal_queue:
            abnormal_queue_counts[queue_status or "none"] = abnormal_queue_counts.get(queue_status or "none", 0) + 1
        if is_abnormal_execution:
            abnormal_execution_counts[execution_status or "none"] = (
                abnormal_execution_counts.get(execution_status or "none", 0) + 1
            )

        trigger_records_by_book[(strategy_profile, paper_account_group)].append(
            {
                "strategy_profile": strategy_profile,
                "paper_account_group": paper_account_group,
                "payload": payload,
            }
        )

    triggers = [
        _build_trigger_row(
            book_records,
            region_code=region_code,
        )
        for book_records in trigger_records_by_book.values()
    ]
    triggers.sort(
        key=lambda item: (
            item["severity_rank"],
            item["last_as_of"],
            item["incident_record_count"],
            item["strategy_profile"],
            item["paper_account_group"],
        ),
        reverse=True,
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "region_code": region_code,
        "record_count": len(records),
        "incident_record_count": sum(int(item["incident_record_count"]) for item in triggers),
        "trigger_count": len(triggers),
        "critical_trigger_count": sum(1 for item in triggers if item["severity"] == "critical"),
        "warning_trigger_count": sum(1 for item in triggers if item["severity"] == "warning"),
        "abnormal_queue_counts": dict(sorted(abnormal_queue_counts.items())),
        "abnormal_execution_counts": dict(sorted(abnormal_execution_counts.items())),
        "triggers": triggers[:max_triggers],
        "truncated_trigger_count": max(0, len(triggers) - max_triggers),
    }


def build_incident_trigger_dashboard_message(
    records: Sequence[Mapping[str, Any]],
    *,
    period_label: str,
    start_date: str,
    end_date: str,
    region_code: str = "sg",
    lang: str = "en",
    max_triggers: int = MAX_TRIGGER_ROWS,
) -> NotificationMessage:
    labels = _labels(lang)
    summary = summarize_incident_trigger_dashboard(
        records,
        start_date=start_date,
        end_date=end_date,
        region_code=region_code,
        max_triggers=max_triggers,
    )
    title = f"{labels['title_prefix']} | {labels['dashboard_prefix']} {period_label}"
    body = render_incident_trigger_dashboard_body(summary, lang=lang)
    return NotificationMessage(
        title=title,
        body=body,
        metadata={
            "period_label": period_label,
            "start_date": start_date,
            "end_date": end_date,
            "region_code": region_code,
        },
    )


def render_incident_trigger_dashboard_body(summary: Mapping[str, Any], *, lang: str = "en") -> str:
    labels = _labels(lang)
    lines = [
        _section(labels["overview"]),
        f"{labels['window']}: {summary.get('start_date')} -> {summary.get('end_date')}",
        f"{labels['region']}: {summary.get('region_code')}",
        f"{labels['records']}: {int(summary.get('record_count') or 0)}",
        f"{labels['incident_records']}: {int(summary.get('incident_record_count') or 0)}",
        f"{labels['triggers']}: {int(summary.get('trigger_count') or 0)}",
        f"{labels['critical']}: {int(summary.get('critical_trigger_count') or 0)}",
        f"{labels['warning']}: {int(summary.get('warning_trigger_count') or 0)}",
    ]

    abnormal_queue_counts = dict(summary.get("abnormal_queue_counts") or {})
    abnormal_execution_counts = dict(summary.get("abnormal_execution_counts") or {})
    if abnormal_queue_counts or abnormal_execution_counts:
        lines.extend(["", _section(labels["status_breakdown"])])
        if abnormal_queue_counts:
            lines.append(f"{labels['queue']}: {_format_status_counts(abnormal_queue_counts)}")
        if abnormal_execution_counts:
            lines.append(f"{labels['execution']}: {_format_status_counts(abnormal_execution_counts)}")

    lines.extend(["", _section(labels["triggers_section"])])
    trigger_rows = list(summary.get("triggers") or ())
    if trigger_rows:
        for row in trigger_rows:
            lines.extend(_format_trigger_lines(row, labels=labels))
    else:
        lines.append(labels["none"])

    truncated = int(summary.get("truncated_trigger_count") or 0)
    if truncated > 0:
        lines.append(labels["more_triggers"].format(count=truncated))

    return "\n".join(line.rstrip() for line in lines if line.strip())


def _build_trigger_row(
    book_records: Sequence[Mapping[str, Any]],
    *,
    region_code: str,
) -> dict[str, Any]:
    ordered = sorted(
        book_records,
        key=lambda item: (
            str((item.get("payload") or {}).get("as_of") or ""),
            str((item.get("payload") or {}).get("queue_status") or ""),
            str((((item.get("payload") or {}).get("execution") or {}).get("status") or "")),
        ),
    )
    first_payload = dict(ordered[0].get("payload") or {})
    latest_payload = dict(ordered[-1].get("payload") or {})
    abnormal_queue_statuses = sorted(
        {
            str((item.get("payload") or {}).get("queue_status") or "").strip()
            for item in ordered
            if str((item.get("payload") or {}).get("queue_status") or "").strip().lower()
            not in NORMAL_QUEUE_STATUSES
        }
    )
    abnormal_execution_statuses = sorted(
        {
            str((((item.get("payload") or {}).get("execution") or {}).get("status") or "")).strip()
            for item in ordered
            if str((((item.get("payload") or {}).get("execution") or {}).get("status") or "")).strip().lower()
            not in NORMAL_EXECUTION_STATUSES
        }
    )
    severity = "critical" if abnormal_execution_statuses else "warning"
    severity_rank = 2 if severity == "critical" else 1
    scope_slug = _build_scope_slug(
        strategy_profile=str(ordered[-1].get("strategy_profile") or ""),
        paper_account_group=str(ordered[-1].get("paper_account_group") or ""),
    )
    first_as_of = str(first_payload.get("as_of") or "")
    last_as_of = str(latest_payload.get("as_of") or "")
    suggested_incident_id = (
        f"psp-{_normalize_slug(region_code) or 'sg'}-{scope_slug}-{first_as_of.replace('-', '') or 'unknown'}-001"
    )
    return {
        "strategy_profile": str(ordered[-1].get("strategy_profile") or ""),
        "paper_account_group": str(ordered[-1].get("paper_account_group") or ""),
        "first_as_of": first_as_of,
        "last_as_of": last_as_of,
        "incident_record_count": len(ordered),
        "severity": severity,
        "severity_rank": severity_rank,
        "abnormal_queue_statuses": abnormal_queue_statuses,
        "abnormal_execution_statuses": abnormal_execution_statuses,
        "latest_status": _extract_status_text(latest_payload),
        "latest_signal": _extract_signal_text(latest_payload),
        "suggested_scope": scope_slug,
        "suggested_incident_id": suggested_incident_id,
        "suggested_period_label": f"incident {suggested_incident_id}",
        "suggested_start_date": first_as_of,
        "suggested_end_date": last_as_of,
    }


def _build_scope_slug(*, strategy_profile: str, paper_account_group: str) -> str:
    normalized_strategy = _normalize_slug(strategy_profile)
    normalized_group = _normalize_slug(paper_account_group)
    if normalized_strategy and normalized_group and normalized_strategy != normalized_group:
        if normalized_group.startswith("sg-") or normalized_group.startswith("us-"):
            return normalized_strategy
    return normalized_strategy or normalized_group or "core"


def _format_trigger_lines(row: Mapping[str, Any], *, labels: Mapping[str, str]) -> list[str]:
    line = (
        f"- {row.get('severity')} | {row.get('strategy_profile')} | "
        f"{row.get('paper_account_group')} | {row.get('first_as_of')} -> {row.get('last_as_of')}"
    )
    details = [
        f"{labels['incident_id_short']}={row.get('suggested_incident_id')}",
        f"{labels['records_short']}={int(row.get('incident_record_count') or 0)}",
    ]
    queue_statuses = ", ".join(str(value) for value in row.get("abnormal_queue_statuses") or ())
    execution_statuses = ", ".join(str(value) for value in row.get("abnormal_execution_statuses") or ())
    if queue_statuses:
        details.append(f"{labels['queue_short']}={queue_statuses}")
    if execution_statuses:
        details.append(f"{labels['execution_short']}={execution_statuses}")
    if row.get("latest_status"):
        details.append(f"{labels['status_short']}={row.get('latest_status')}")
    if row.get("latest_signal"):
        details.append(f"{labels['signal_short']}={row.get('latest_signal')}")
    details.append(
        f"{labels['window_short']}={row.get('suggested_start_date')}->{row.get('suggested_end_date')}"
    )
    return [line, f"  {' | '.join(details)}"]


def _extract_status_text(payload: Mapping[str, Any]) -> str:
    decision = dict(payload.get("decision") or {})
    execution_annotations = dict(decision.get("execution_annotations") or {})
    return str(
        execution_annotations.get("status_display")
        or decision.get("status_display")
        or decision.get("status_description")
        or ""
    ).strip()


def _extract_signal_text(payload: Mapping[str, Any]) -> str:
    decision = dict(payload.get("decision") or {})
    execution_annotations = dict(decision.get("execution_annotations") or {})
    return str(
        execution_annotations.get("signal_display")
        or decision.get("signal_display")
        or decision.get("signal_description")
        or ""
    ).strip()


def _format_status_counts(values: Mapping[str, Any]) -> str:
    parts = [f"{key}={int(count or 0)}" for key, count in values.items()]
    return ", ".join(parts) if parts else "none"


def _normalize_slug(value: str) -> str:
    cleaned = []
    previous_dash = False
    for char in str(value or "").strip().lower():
        if char.isalnum():
            cleaned.append(char)
            previous_dash = False
            continue
        if not previous_dash:
            cleaned.append("-")
            previous_dash = True
    return "".join(cleaned).strip("-")


def _section(title: str) -> str:
    return f"[{title}]"


def _labels(lang: str) -> Mapping[str, str]:
    normalized = str(lang or "en").strip().lower()
    if normalized.startswith("zh"):
        return {
            "title_prefix": "PaperSignal",
            "dashboard_prefix": "事件触发看板",
            "overview": "概览",
            "window": "窗口",
            "region": "区域",
            "records": "记录数",
            "incident_records": "异常记录数",
            "triggers": "触发项数",
            "critical": "严重项数",
            "warning": "预警项数",
            "status_breakdown": "异常状态分布",
            "queue": "异常排队状态",
            "execution": "异常执行状态",
            "triggers_section": "建议开单",
            "incident_id_short": "建议事件ID",
            "records_short": "记录数",
            "queue_short": "排队异常",
            "execution_short": "执行异常",
            "status_short": "状态",
            "signal_short": "信号",
            "window_short": "建议窗口",
            "more_triggers": "... 其余 {count} 个触发项未展开",
            "none": "无",
        }
    return {
        "title_prefix": "PaperSignal",
        "dashboard_prefix": "Incident Trigger Dashboard",
        "overview": "Overview",
        "window": "Window",
        "region": "Region",
        "records": "Records",
        "incident_records": "Incident Records",
        "triggers": "Triggers",
        "critical": "Critical",
        "warning": "Warning",
        "status_breakdown": "Abnormal Status Breakdown",
        "queue": "Queue",
        "execution": "Execution",
        "triggers_section": "Suggested Incidents",
        "incident_id_short": "incident_id",
        "records_short": "records",
        "queue_short": "queue",
        "execution_short": "execution",
        "status_short": "status",
        "signal_short": "signal",
        "window_short": "window",
        "more_triggers": "... {count} more triggers omitted",
        "none": "none",
    }
