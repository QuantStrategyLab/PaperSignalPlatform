from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from application.notification_service import NotificationMessage

MAX_REVIEW_BOOKS = 10
MAX_REVIEW_EVENTS = 15
NORMAL_QUEUE_STATUSES = frozenset({"", "none", "queued_pending_plan", "no_actionable_allocation"})
NORMAL_EXECUTION_STATUSES = frozenset({"", "none", "no_pending_plan", "executed_pending_plan"})


def summarize_operator_review_pack(
    records: Sequence[Mapping[str, Any]],
    *,
    review_type: str,
    start_date: str,
    end_date: str,
    max_books: int = MAX_REVIEW_BOOKS,
    max_events: int = MAX_REVIEW_EVENTS,
) -> dict[str, Any]:
    records_by_book: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    queue_counts: dict[str, int] = {}
    execution_counts: dict[str, int] = {}
    total_trade_count = 0
    total_turnover = 0.0
    total_commission = 0.0
    total_slippage = 0.0
    event_rows: list[dict[str, Any]] = []

    for raw_record in records:
        payload = dict(raw_record.get("payload") or {})
        strategy_profile = str(raw_record.get("strategy_profile") or payload.get("strategy_profile") or "").strip()
        paper_account_group = str(
            raw_record.get("paper_account_group") or payload.get("paper_account_group") or ""
        ).strip()
        if not strategy_profile or not paper_account_group:
            continue

        normalized_record = {
            "strategy_profile": strategy_profile,
            "paper_account_group": paper_account_group,
            "payload": payload,
        }
        records_by_book[(strategy_profile, paper_account_group)].append(normalized_record)

        execution = dict(payload.get("execution") or {})
        queue_status = str(payload.get("queue_status") or "").strip()
        execution_status = str(execution.get("status") or "").strip()
        queue_counts[queue_status or "none"] = queue_counts.get(queue_status or "none", 0) + 1
        execution_counts[execution_status or "none"] = execution_counts.get(execution_status or "none", 0) + 1
        total_trade_count += int(execution.get("trade_count") or 0)
        total_turnover += _coerce_float(execution.get("turnover_value"))
        total_commission += _coerce_float(execution.get("commission_paid"))
        total_slippage += _coerce_float(execution.get("slippage_cost"))

        event = _build_event_row(normalized_record)
        if event is not None:
            event_rows.append(event)

    books = [
        _build_book_review(records_for_book)
        for records_for_book in records_by_book.values()
        if records_for_book
    ]
    books.sort(
        key=lambda item: (
            item["incident_count"],
            abs(_coerce_float(item["nav_change_pct"])),
            abs(_coerce_float(item["nav_change"])),
            item["last_as_of"],
            item["strategy_profile"],
            item["paper_account_group"],
        ),
        reverse=True,
    )
    events = sorted(
        event_rows,
        key=lambda item: (
            item["severity_rank"],
            item["as_of"],
            item["strategy_profile"],
            item["paper_account_group"],
        ),
        reverse=True,
    )

    return {
        "review_type": review_type,
        "start_date": start_date,
        "end_date": end_date,
        "record_count": len(records),
        "book_count": len(books),
        "aggregate_nav_start": sum(_coerce_float(book["start_nav"]) for book in books),
        "aggregate_nav_end": sum(_coerce_float(book["end_nav"]) for book in books),
        "aggregate_nav_change": sum(_coerce_float(book["nav_change"]) for book in books),
        "aggregate_cash_end": sum(_coerce_float(book["end_cash"]) for book in books),
        "total_trade_count": total_trade_count,
        "total_turnover": total_turnover,
        "total_commission": total_commission,
        "total_slippage": total_slippage,
        "queue_counts": dict(sorted(queue_counts.items())),
        "execution_counts": dict(sorted(execution_counts.items())),
        "incident_count": sum(int(book["incident_count"]) for book in books),
        "incident_book_count": sum(1 for book in books if int(book["incident_count"]) > 0),
        "execution_record_count": sum(1 for event in events if event["event_type"] == "execution"),
        "queue_record_count": sum(1 for event in events if event["event_type"] == "queue"),
        "books": books[:max_books],
        "events": events[:max_events],
        "truncated_book_count": max(0, len(books) - max_books),
        "truncated_event_count": max(0, len(events) - max_events),
    }


def build_operator_review_pack_message(
    records: Sequence[Mapping[str, Any]],
    *,
    review_type: str,
    period_label: str,
    start_date: str,
    end_date: str,
    lang: str = "en",
    max_books: int = MAX_REVIEW_BOOKS,
    max_events: int = MAX_REVIEW_EVENTS,
) -> NotificationMessage:
    labels = _labels(lang)
    summary = summarize_operator_review_pack(
        records,
        review_type=review_type,
        start_date=start_date,
        end_date=end_date,
        max_books=max_books,
        max_events=max_events,
    )
    title = f"{labels['title_prefix']} | {labels['review_prefix']} {period_label}"
    body = render_operator_review_pack_body(summary, lang=lang)
    return NotificationMessage(
        title=title,
        body=body,
        metadata={
            "review_type": review_type,
            "period_label": period_label,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


def render_operator_review_pack_body(summary: Mapping[str, Any], *, lang: str = "en") -> str:
    labels = _labels(lang)
    lines = [
        _section(labels["overview"]),
        f"{labels['window']}: {summary.get('start_date')} -> {summary.get('end_date')}",
        f"{labels['review_type']}: {summary.get('review_type')}",
        f"{labels['records']}: {int(summary.get('record_count') or 0)}",
        f"{labels['books']}: {int(summary.get('book_count') or 0)}",
        f"{labels['nav_start']}: {_format_money(summary.get('aggregate_nav_start'))}",
        f"{labels['nav_end']}: {_format_money(summary.get('aggregate_nav_end'))}",
        f"{labels['nav_change']}: {_format_signed_money(summary.get('aggregate_nav_change'))}",
        f"{labels['cash_end']}: {_format_money(summary.get('aggregate_cash_end'))}",
        f"{labels['trade_count']}: {int(summary.get('total_trade_count') or 0)}",
        f"{labels['turnover']}: {_format_money(summary.get('total_turnover'))}",
        f"{labels['commission']}: {_format_money(summary.get('total_commission'))}",
        f"{labels['slippage']}: {_format_money(summary.get('total_slippage'))}",
        f"{labels['incident_count']}: {int(summary.get('incident_count') or 0)}",
        f"{labels['incident_books']}: {int(summary.get('incident_book_count') or 0)}",
    ]

    queue_counts = dict(summary.get("queue_counts") or {})
    execution_counts = dict(summary.get("execution_counts") or {})
    if queue_counts or execution_counts:
        lines.extend(["", _section(labels["status_breakdown"])])
        if queue_counts:
            lines.append(f"{labels['queue']}: {_format_status_counts(queue_counts)}")
        if execution_counts:
            lines.append(f"{labels['execution']}: {_format_status_counts(execution_counts)}")

    books = list(summary.get("books") or ())
    lines.extend(["", _section(labels["books_section"])])
    if books:
        for book in books:
            lines.extend(_format_book_lines(book, labels=labels))
    else:
        lines.append(labels["none"])

    events = list(summary.get("events") or ())
    lines.extend(["", _section(labels["events_section"])])
    if events:
        for event in events:
            lines.extend(_format_event_lines(event, labels=labels))
    else:
        lines.append(labels["none"])

    truncated_books = int(summary.get("truncated_book_count") or 0)
    truncated_events = int(summary.get("truncated_event_count") or 0)
    if truncated_books > 0:
        lines.append(labels["more_books"].format(count=truncated_books))
    if truncated_events > 0:
        lines.append(labels["more_events"].format(count=truncated_events))

    return "\n".join(line.rstrip() for line in lines if line.strip())


def _build_book_review(records_for_book: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        records_for_book,
        key=lambda item: (
            str((item.get("payload") or {}).get("as_of") or ""),
            str((item.get("payload") or {}).get("queue_status") or ""),
            str((((item.get("payload") or {}).get("execution") or {}).get("status") or "")),
        ),
    )
    first_payload = dict(ordered[0].get("payload") or {})
    latest_payload = dict(ordered[-1].get("payload") or {})
    latest_execution = dict(latest_payload.get("execution") or {})
    start_nav = _coerce_float(first_payload.get("nav"))
    end_nav = _coerce_float(latest_payload.get("nav"))
    nav_change = end_nav - start_nav
    nav_change_pct = (nav_change / start_nav * 100.0) if start_nav else 0.0
    total_trades = sum(int(((record.get("payload") or {}).get("execution") or {}).get("trade_count") or 0) for record in ordered)
    total_turnover = sum(
        _coerce_float(((record.get("payload") or {}).get("execution") or {}).get("turnover_value"))
        for record in ordered
    )
    total_commission = sum(
        _coerce_float(((record.get("payload") or {}).get("execution") or {}).get("commission_paid"))
        for record in ordered
    )
    total_slippage = sum(
        _coerce_float(((record.get("payload") or {}).get("execution") or {}).get("slippage_cost"))
        for record in ordered
    )
    incident_count = sum(1 for record in ordered if _is_incident_record(record))

    return {
        "strategy_profile": ordered[-1]["strategy_profile"],
        "paper_account_group": ordered[-1]["paper_account_group"],
        "first_as_of": str(first_payload.get("as_of") or ""),
        "last_as_of": str(latest_payload.get("as_of") or ""),
        "start_nav": start_nav,
        "end_nav": end_nav,
        "nav_change": nav_change,
        "nav_change_pct": nav_change_pct,
        "start_cash": _coerce_float(first_payload.get("cash")),
        "end_cash": _coerce_float(latest_payload.get("cash")),
        "execution_day_count": sum(
            1 for record in ordered if int((((record.get("payload") or {}).get("execution") or {}).get("trade_count") or 0)) > 0
        ),
        "queue_day_count": sum(
            1 for record in ordered if str((record.get("payload") or {}).get("queue_status") or "").strip() == "queued_pending_plan"
        ),
        "incident_count": incident_count,
        "trade_count": total_trades,
        "turnover": total_turnover,
        "commission": total_commission,
        "slippage": total_slippage,
        "latest_signal": _extract_signal_text(latest_payload),
        "latest_status": _extract_status_text(latest_payload),
        "latest_execution_status": str(latest_execution.get("status") or "").strip(),
        "latest_queue_status": str(latest_payload.get("queue_status") or "").strip(),
        "pending_effective_date": str((latest_payload.get("pending_plan") or {}).get("effective_date") or "").strip(),
    }


def _build_event_row(record: Mapping[str, Any]) -> dict[str, Any] | None:
    payload = dict(record.get("payload") or {})
    execution = dict(payload.get("execution") or {})
    queue_status = str(payload.get("queue_status") or "").strip()
    execution_status = str(execution.get("status") or "").strip()
    trade_count = int(execution.get("trade_count") or 0)
    incident = _is_incident_record(record)
    if incident:
        event_type = "incident"
        severity_rank = 3
    elif trade_count > 0:
        event_type = "execution"
        severity_rank = 2
    elif queue_status == "queued_pending_plan":
        event_type = "queue"
        severity_rank = 1
    else:
        return None

    headline = _build_event_headline(
        event_type=event_type,
        trade_count=trade_count,
        queue_status=queue_status,
        execution_status=execution_status,
    )
    return {
        "as_of": str(payload.get("as_of") or ""),
        "strategy_profile": str(record.get("strategy_profile") or ""),
        "paper_account_group": str(record.get("paper_account_group") or ""),
        "event_type": event_type,
        "severity_rank": severity_rank,
        "headline": headline,
        "status": _extract_status_text(payload),
        "signal": _extract_signal_text(payload),
        "queue_status": queue_status or "none",
        "execution_status": execution_status or "none",
        "trade_count": trade_count,
        "turnover": _coerce_float(execution.get("turnover_value")),
        "nav": _coerce_float(payload.get("nav")),
    }


def _build_event_headline(
    *,
    event_type: str,
    trade_count: int,
    queue_status: str,
    execution_status: str,
) -> str:
    if event_type == "incident":
        return f"queue={queue_status or 'none'} | execution={execution_status or 'none'}"
    if event_type == "execution":
        return f"executed {trade_count} trade(s)"
    return f"queued next session plan ({queue_status})"


def _format_book_lines(book: Mapping[str, Any], *, labels: Mapping[str, str]) -> list[str]:
    line = (
        f"- {book.get('strategy_profile')} | {book.get('paper_account_group')} | "
        f"{book.get('first_as_of')} -> {book.get('last_as_of')}"
    )
    details = [
        f"{labels['nav_change_short']}={_format_signed_money(book.get('nav_change'))}",
        f"{labels['nav_change_pct_short']}={_format_signed_pct(book.get('nav_change_pct'))}",
        f"{labels['end_nav_short']}={_format_money(book.get('end_nav'))}",
        f"{labels['trades_short']}={int(book.get('trade_count') or 0)}",
    ]
    if _coerce_float(book.get("turnover")) > 0.0:
        details.append(f"{labels['turnover_short']}={_format_money(book.get('turnover'))}")
    if int(book.get("incident_count") or 0) > 0:
        details.append(f"{labels['incidents_short']}={int(book.get('incident_count') or 0)}")
    if book.get("latest_status"):
        details.append(f"{labels['status_short']}={book.get('latest_status')}")
    if book.get("latest_signal"):
        details.append(f"{labels['signal_short']}={book.get('latest_signal')}")
    if book.get("pending_effective_date"):
        details.append(f"{labels['pending_short']}={book.get('pending_effective_date')}")
    return [line, f"  {' | '.join(details)}"]


def _format_event_lines(event: Mapping[str, Any], *, labels: Mapping[str, str]) -> list[str]:
    line = (
        f"- {event.get('as_of')} | {event.get('strategy_profile')} | "
        f"{event.get('paper_account_group')} | {event.get('event_type')}"
    )
    details = [str(event.get("headline") or labels["none"])]
    if event.get("status"):
        details.append(f"{labels['status_short']}={event.get('status')}")
    if event.get("signal"):
        details.append(f"{labels['signal_short']}={event.get('signal')}")
    if int(event.get("trade_count") or 0) > 0:
        details.append(f"{labels['trades_short']}={int(event.get('trade_count') or 0)}")
    if _coerce_float(event.get("turnover")) > 0.0:
        details.append(f"{labels['turnover_short']}={_format_money(event.get('turnover'))}")
    return [line, f"  {' | '.join(details)}"]


def _is_incident_record(record: Mapping[str, Any]) -> bool:
    payload = dict(record.get("payload") or {})
    queue_status = str(payload.get("queue_status") or "").strip().lower()
    execution_status = str(((payload.get("execution") or {}).get("status") or "")).strip().lower()
    return queue_status not in NORMAL_QUEUE_STATUSES or execution_status not in NORMAL_EXECUTION_STATUSES


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


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${amount:,.2f}"


def _format_signed_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    if amount > 0:
        return f"+${amount:,.2f}"
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return "$0.00"


def _format_signed_pct(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "0.00%"
    sign = "+" if amount > 0 else ""
    return f"{sign}{amount:.2f}%"


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _section(title: str) -> str:
    return f"[{title}]"


def _labels(lang: str) -> Mapping[str, str]:
    normalized = str(lang or "en").strip().lower()
    if normalized.startswith("zh"):
        return {
            "title_prefix": "PaperSignal",
            "review_prefix": "运维复盘",
            "overview": "概览",
            "window": "窗口",
            "review_type": "复盘类型",
            "records": "记录数",
            "books": "账户数",
            "nav_start": "期初净值",
            "nav_end": "期末净值",
            "nav_change": "净值变化",
            "cash_end": "期末现金",
            "trade_count": "总成交笔数",
            "turnover": "总换手金额",
            "commission": "总手续费",
            "slippage": "总滑点",
            "incident_count": "事件数",
            "incident_books": "涉事件账户数",
            "status_breakdown": "状态分布",
            "queue": "排队状态",
            "execution": "执行状态",
            "books_section": "账户变化",
            "events_section": "事件时间线",
            "nav_change_short": "净值变化",
            "nav_change_pct_short": "变化率",
            "end_nav_short": "期末净值",
            "trades_short": "成交",
            "turnover_short": "换手",
            "incidents_short": "事件",
            "status_short": "状态",
            "signal_short": "信号",
            "pending_short": "待执行",
            "more_books": "... 其余 {count} 个账户未展开",
            "more_events": "... 其余 {count} 条事件未展开",
            "none": "无",
        }
    return {
        "title_prefix": "PaperSignal",
        "review_prefix": "Operator Review",
        "overview": "Overview",
        "window": "Window",
        "review_type": "Review Type",
        "records": "Records",
        "books": "Books",
        "nav_start": "Start NAV",
        "nav_end": "End NAV",
        "nav_change": "NAV Change",
        "cash_end": "End Cash",
        "trade_count": "Total Trades",
        "turnover": "Turnover",
        "commission": "Commission",
        "slippage": "Slippage",
        "incident_count": "Events",
        "incident_books": "Books With Events",
        "status_breakdown": "Status Breakdown",
        "queue": "Queue",
        "execution": "Execution",
        "books_section": "Book Changes",
        "events_section": "Event Timeline",
        "nav_change_short": "pnl",
        "nav_change_pct_short": "pnl_pct",
        "end_nav_short": "end_nav",
        "trades_short": "trades",
        "turnover_short": "turnover",
        "incidents_short": "events",
        "status_short": "status",
        "signal_short": "signal",
        "pending_short": "pending",
        "more_books": "... {count} more books omitted",
        "more_events": "... {count} more events omitted",
        "none": "none",
    }
