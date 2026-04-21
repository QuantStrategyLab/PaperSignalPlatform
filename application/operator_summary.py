from __future__ import annotations

from typing import Any, Mapping, Sequence

from application.notification_service import NotificationMessage

MAX_RENDERED_BOOKS = 10


def summarize_reconciliation_records(
    records: Sequence[Mapping[str, Any]],
    *,
    start_date: str,
    end_date: str,
    max_books: int = MAX_RENDERED_BOOKS,
) -> dict[str, Any]:
    latest_by_book: dict[tuple[str, str], Mapping[str, Any]] = {}
    total_trade_count = 0
    total_turnover = 0.0
    total_commission = 0.0
    total_slippage = 0.0
    queue_counts: dict[str, int] = {}
    execution_counts: dict[str, int] = {}

    for record in records:
        payload = dict(record.get("payload") or {})
        strategy_profile = str(record.get("strategy_profile") or payload.get("strategy_profile") or "").strip()
        paper_account_group = str(
            record.get("paper_account_group") or payload.get("paper_account_group") or ""
        ).strip()
        if not strategy_profile or not paper_account_group:
            continue

        key = (strategy_profile, paper_account_group)
        existing = latest_by_book.get(key)
        if existing is None or _sort_key(payload) >= _sort_key(dict(existing.get("payload") or {})):
            latest_by_book[key] = {
                "strategy_profile": strategy_profile,
                "paper_account_group": paper_account_group,
                "payload": payload,
            }

        execution = dict(payload.get("execution") or {})
        queue_status = str(payload.get("queue_status") or "").strip()
        execution_status = str(execution.get("status") or "").strip()
        queue_counts[queue_status or "none"] = queue_counts.get(queue_status or "none", 0) + 1
        execution_counts[execution_status or "none"] = execution_counts.get(execution_status or "none", 0) + 1
        total_trade_count += int(execution.get("trade_count") or 0)
        total_turnover += _coerce_float(execution.get("turnover_value"))
        total_commission += _coerce_float(execution.get("commission_paid"))
        total_slippage += _coerce_float(execution.get("slippage_cost"))

    books = sorted(
        (
            _build_book_summary(item["strategy_profile"], item["paper_account_group"], item["payload"])
            for item in latest_by_book.values()
        ),
        key=lambda item: (
            item["as_of"],
            item["strategy_profile"],
            item["paper_account_group"],
        ),
        reverse=True,
    )
    aggregate_nav = sum(_coerce_float(item["nav"]) for item in books)
    aggregate_cash = sum(_coerce_float(item["cash"]) for item in books)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "record_count": len(records),
        "book_count": len(books),
        "aggregate_nav": aggregate_nav,
        "aggregate_cash": aggregate_cash,
        "total_trade_count": total_trade_count,
        "total_turnover": total_turnover,
        "total_commission": total_commission,
        "total_slippage": total_slippage,
        "queue_counts": dict(sorted(queue_counts.items())),
        "execution_counts": dict(sorted(execution_counts.items())),
        "books": books[:max_books],
        "truncated_book_count": max(0, len(books) - max_books),
    }


def build_operator_summary_message(
    records: Sequence[Mapping[str, Any]],
    *,
    period_label: str,
    start_date: str,
    end_date: str,
    lang: str = "en",
    max_books: int = MAX_RENDERED_BOOKS,
) -> NotificationMessage:
    labels = _labels(lang)
    summary = summarize_reconciliation_records(
        records,
        start_date=start_date,
        end_date=end_date,
        max_books=max_books,
    )
    title = f"{labels['title_prefix']} | {labels['period_prefix']} {period_label}"
    body = render_operator_summary_body(summary, lang=lang)
    return NotificationMessage(
        title=title,
        body=body,
        metadata={
            "period_label": period_label,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


def render_operator_summary_body(summary: Mapping[str, Any], *, lang: str = "en") -> str:
    labels = _labels(lang)
    lines = [
        _section(labels["overview"]),
        f"{labels['window']}: {summary.get('start_date')} -> {summary.get('end_date')}",
        f"{labels['records']}: {int(summary.get('record_count') or 0)}",
        f"{labels['books']}: {int(summary.get('book_count') or 0)}",
        f"{labels['aggregate_nav']}: {_format_money(summary.get('aggregate_nav'))}",
        f"{labels['aggregate_cash']}: {_format_money(summary.get('aggregate_cash'))}",
        f"{labels['trade_count']}: {int(summary.get('total_trade_count') or 0)}",
        f"{labels['turnover']}: {_format_money(summary.get('total_turnover'))}",
        f"{labels['commission']}: {_format_money(summary.get('total_commission'))}",
        f"{labels['slippage']}: {_format_money(summary.get('total_slippage'))}",
    ]

    queue_counts = dict(summary.get("queue_counts") or {})
    execution_counts = dict(summary.get("execution_counts") or {})
    if queue_counts or execution_counts:
        lines.extend(
            [
                "",
                _section(labels["status_breakdown"]),
            ]
        )
        if queue_counts:
            lines.append(f"{labels['queue']}: {_format_status_counts(queue_counts)}")
        if execution_counts:
            lines.append(f"{labels['execution']}: {_format_status_counts(execution_counts)}")

    books = list(summary.get("books") or ())
    if books:
        lines.extend(
            [
                "",
                _section(labels["books_section"]),
            ]
        )
        for book in books:
            lines.extend(_format_book_lines(book, labels=labels))
    else:
        lines.extend(
            [
                "",
                _section(labels["books_section"]),
                labels["none"],
            ]
        )

    truncated = int(summary.get("truncated_book_count") or 0)
    if truncated > 0:
        lines.append(labels["more_books"].format(count=truncated))

    return "\n".join(line.rstrip() for line in lines if line.strip())


def _build_book_summary(
    strategy_profile: str,
    paper_account_group: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    execution = dict(payload.get("execution") or {})
    pending_plan = dict(payload.get("pending_plan") or {})
    return {
        "strategy_profile": strategy_profile,
        "paper_account_group": paper_account_group,
        "as_of": str(payload.get("as_of") or ""),
        "nav": _coerce_float(payload.get("nav")),
        "cash": _coerce_float(payload.get("cash")),
        "queue_status": str(payload.get("queue_status") or "").strip(),
        "execution_status": str(execution.get("status") or "").strip(),
        "trade_count": int(execution.get("trade_count") or 0),
        "turnover": _coerce_float(execution.get("turnover_value")),
        "signal": _extract_signal_text(payload),
        "status": _extract_status_text(payload),
        "pending_effective_date": str(pending_plan.get("effective_date") or "").strip(),
    }


def _format_book_lines(book: Mapping[str, Any], *, labels: Mapping[str, str]) -> list[str]:
    line = (
        f"- {book.get('strategy_profile')} | {book.get('paper_account_group')} | "
        f"{book.get('as_of') or labels['unknown']}"
    )
    details = [
        f"{labels['nav_short']}={_format_money(book.get('nav'))}",
        f"{labels['cash_short']}={_format_money(book.get('cash'))}",
    ]
    if book.get("status"):
        details.append(f"{labels['status_short']}={book.get('status')}")
    if book.get("signal"):
        details.append(f"{labels['signal_short']}={book.get('signal')}")
    if book.get("execution_status"):
        details.append(f"{labels['execution_short']}={book.get('execution_status')}")
    if book.get("queue_status"):
        details.append(f"{labels['queue_short']}={book.get('queue_status')}")
    if int(book.get("trade_count") or 0) > 0:
        details.append(f"{labels['trades_short']}={int(book.get('trade_count') or 0)}")
    if _coerce_float(book.get("turnover")) > 0.0:
        details.append(f"{labels['turnover_short']}={_format_money(book.get('turnover'))}")
    if book.get("pending_effective_date"):
        details.append(f"{labels['pending_short']}={book.get('pending_effective_date')}")
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


def _sort_key(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(payload.get("as_of") or ""),
        str(payload.get("queue_status") or ""),
        str((payload.get("execution") or {}).get("status") or ""),
    )


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${amount:,.2f}"


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
            "period_prefix": "运维摘要",
            "overview": "概览",
            "status_breakdown": "状态分布",
            "books_section": "账户摘要",
            "window": "区间",
            "records": "记录数",
            "books": "账户数",
            "aggregate_nav": "汇总净值",
            "aggregate_cash": "汇总现金",
            "trade_count": "总成交笔数",
            "turnover": "总换手额",
            "commission": "总手续费",
            "slippage": "总滑点",
            "queue": "排队状态",
            "execution": "执行状态",
            "nav_short": "净值",
            "cash_short": "现金",
            "status_short": "状态",
            "signal_short": "信号",
            "execution_short": "执行",
            "queue_short": "排队",
            "trades_short": "成交",
            "turnover_short": "换手",
            "pending_short": "待执行",
            "more_books": "... 其余 {count} 个账户",
            "none": "无",
            "unknown": "未知",
        }
    return {
        "title_prefix": "PaperSignal",
        "period_prefix": "Operator Summary",
        "overview": "Overview",
        "status_breakdown": "Status Breakdown",
        "books_section": "Books",
        "window": "Window",
        "records": "Records",
        "books": "Books",
        "aggregate_nav": "Aggregate NAV",
        "aggregate_cash": "Aggregate Cash",
        "trade_count": "Total Trades",
        "turnover": "Total Turnover",
        "commission": "Total Commission",
        "slippage": "Total Slippage",
        "queue": "Queue",
        "execution": "Execution",
        "nav_short": "nav",
        "cash_short": "cash",
        "status_short": "status",
        "signal_short": "signal",
        "execution_short": "execution",
        "queue_short": "queue",
        "trades_short": "trades",
        "turnover_short": "turnover",
        "pending_short": "pending",
        "more_books": "... and {count} more books",
        "none": "none",
        "unknown": "unknown",
    }
