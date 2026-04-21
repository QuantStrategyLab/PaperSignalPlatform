from __future__ import annotations

from typing import Any, Mapping

from application.notification_service import NotificationMessage

MAX_RENDERED_TARGETS = 12
MAX_RENDERED_POSITIONS = 12


def build_cycle_notification_message(
    summary: Mapping[str, Any],
    *,
    lang: str = "en",
) -> NotificationMessage:
    labels = _labels(lang)
    strategy_profile = str(summary.get("strategy_profile") or "paper_signal").strip() or "paper_signal"
    paper_account_group = str(summary.get("paper_account_group") or "").strip()
    title_parts = [labels["title_prefix"], strategy_profile]
    if paper_account_group:
        title_parts.append(paper_account_group)
    return NotificationMessage(
        title=" | ".join(title_parts),
        body=render_cycle_notification_body(summary, lang=lang),
        metadata={
            "strategy_profile": strategy_profile,
            "paper_account_group": paper_account_group,
        },
    )


def render_cycle_notification_body(
    summary: Mapping[str, Any],
    *,
    lang: str = "en",
) -> str:
    labels = _labels(lang)
    allocation = dict(summary.get("allocation") or {})
    decision = dict(summary.get("decision") or {})
    execution = dict(summary.get("execution") or {})
    last_execution = dict(summary.get("last_execution") or {})
    pending_plan = dict(summary.get("pending_plan") or {})

    lines: list[str] = []
    lines.extend(
        [
            _section(labels["overview"]),
            f"{labels['strategy']}: {summary.get('strategy_profile')}",
            f"{labels['account']}: {summary.get('paper_account_group')}",
            f"{labels['as_of']}: {summary.get('as_of')}",
            f"{labels['nav']}: {_format_money(summary.get('nav'))}",
            f"{labels['cash']}: {_format_money(summary.get('cash'))}",
            f"{labels['queue']}: {summary.get('queue_status') or labels['none']}",
        ]
    )

    status_text = _extract_status_text(decision)
    signal_text = _extract_signal_text(decision)
    if status_text or signal_text:
        lines.append("")
        lines.append(_section(labels["signal_section"]))
        if status_text:
            lines.append(f"{labels['status']}: {status_text}")
        if signal_text:
            lines.append(f"{labels['signal']}: {signal_text}")

    if allocation:
        lines.append("")
        lines.append(_section(labels["targets_section"]))
        lines.extend(_format_target_lines(allocation, labels=labels))

    positions = list(summary.get("positions") or ())
    lines.append("")
    lines.append(_section(labels["positions_section"]))
    if positions:
        lines.extend(_format_position_lines(positions, labels=labels))
    else:
        lines.append(labels["none"])

    lines.append("")
    lines.append(_section(labels["execution_section"]))
    lines.extend(_format_execution_lines(execution, last_execution=last_execution, labels=labels))

    if pending_plan:
        lines.append("")
        lines.append(_section(labels["pending_section"]))
        lines.extend(_format_pending_plan_lines(pending_plan, labels=labels))

    dashboard_text = _extract_dashboard_text(decision)
    if dashboard_text:
        lines.append("")
        lines.append(_section(labels["notes_section"]))
        lines.extend(_indent_block(dashboard_text))

    return "\n".join(str(line).rstrip() for line in lines if str(line).strip())


def _format_target_lines(
    allocation: Mapping[str, Any],
    *,
    labels: Mapping[str, str],
) -> list[str]:
    target_mode = str(allocation.get("target_mode") or "").strip().lower()
    targets = dict(allocation.get("targets") or {})
    if not targets:
        return [labels["none"]]
    lines = [f"{labels['target_mode']}: {target_mode or labels['unknown']}"]
    rendered = 0
    for symbol, value in _sorted_target_items(targets):
        if target_mode == "weight":
            lines.append(f"- {symbol}: {float(value):.2%}")
        else:
            lines.append(f"- {symbol}: {_format_money(value)}")
        rendered += 1
        if rendered >= MAX_RENDERED_TARGETS:
            break
    remaining = len(targets) - rendered
    if remaining > 0:
        lines.append(labels["more_items"].format(count=remaining))
    return lines


def _format_position_lines(
    positions: list[Mapping[str, Any]],
    *,
    labels: Mapping[str, str],
) -> list[str]:
    lines: list[str] = []
    rendered = 0
    for row in _sorted_positions(positions):
        symbol = str(row.get("symbol") or "").strip() or labels["unknown"]
        quantity = float(row.get("quantity") or 0.0)
        market_value = _format_money(row.get("market_value"))
        average_cost = row.get("average_cost")
        line = (
            f"- {symbol}: {labels['quantity']}={quantity:.4f}, "
            f"{labels['market_value']}={market_value}"
        )
        if average_cost is not None:
            line += f", {labels['average_cost']}={_format_money(average_cost)}"
        lines.append(line)
        rendered += 1
        if rendered >= MAX_RENDERED_POSITIONS:
            break
    remaining = len(positions) - rendered
    if remaining > 0:
        lines.append(labels["more_items"].format(count=remaining))
    return lines


def _format_execution_lines(
    execution: Mapping[str, Any],
    *,
    last_execution: Mapping[str, Any],
    labels: Mapping[str, str],
) -> list[str]:
    lines = [
        f"{labels['execution_status']}: {execution.get('status') or labels['none']}",
    ]
    if execution.get("effective_session"):
        lines.append(f"{labels['effective_session']}: {execution.get('effective_session')}")
    if execution.get("trade_count") is not None:
        lines.append(f"{labels['trade_count']}: {int(execution.get('trade_count') or 0)}")
    if execution.get("turnover_value") is not None:
        lines.append(f"{labels['turnover']}: {_format_money(execution.get('turnover_value'))}")
    if execution.get("commission_paid") is not None:
        lines.append(f"{labels['commission']}: {_format_money(execution.get('commission_paid'))}")
    if execution.get("slippage_cost") is not None:
        lines.append(f"{labels['slippage']}: {_format_money(execution.get('slippage_cost'))}")
    if last_execution.get("effective_session"):
        lines.append(f"{labels['last_execution']}: {last_execution.get('effective_session')}")
    return lines


def _format_pending_plan_lines(
    pending_plan: Mapping[str, Any],
    *,
    labels: Mapping[str, str],
) -> list[str]:
    lines = []
    if pending_plan.get("effective_date"):
        lines.append(f"{labels['effective_date']}: {pending_plan.get('effective_date')}")
    if pending_plan.get("created_as_of"):
        lines.append(f"{labels['created_as_of']}: {pending_plan.get('created_as_of')}")
    target_mode = str(pending_plan.get("target_mode") or "").strip().lower()
    if target_mode:
        lines.append(f"{labels['target_mode']}: {target_mode}")
    targets = dict(pending_plan.get("targets") or {})
    rendered = 0
    for symbol, value in _sorted_target_items(targets):
        if target_mode == "weight":
            lines.append(f"- {symbol}: {float(value):.2%}")
        else:
            lines.append(f"- {symbol}: {_format_money(value)}")
        rendered += 1
        if rendered >= MAX_RENDERED_TARGETS:
            break
    remaining = len(targets) - rendered
    if remaining > 0:
        lines.append(labels["more_items"].format(count=remaining))
    return lines or [labels["none"]]


def _extract_status_text(decision: Mapping[str, Any]) -> str:
    execution_annotations = dict(decision.get("execution_annotations") or {})
    return str(
        execution_annotations.get("status_display")
        or decision.get("status_display")
        or decision.get("status_description")
        or ""
    ).strip()


def _extract_signal_text(decision: Mapping[str, Any]) -> str:
    execution_annotations = dict(decision.get("execution_annotations") or {})
    return str(
        execution_annotations.get("signal_display")
        or decision.get("signal_display")
        or decision.get("signal_description")
        or ""
    ).strip()


def _extract_dashboard_text(decision: Mapping[str, Any]) -> str:
    execution_annotations = dict(decision.get("execution_annotations") or {})
    return str(
        execution_annotations.get("dashboard_text")
        or decision.get("dashboard")
        or ""
    ).strip()


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${amount:,.2f}"


def _indent_block(text: str) -> list[str]:
    return [f"  {line}".rstrip() for line in str(text).splitlines() if str(line).strip()]


def _section(title: str) -> str:
    return f"[{title}]"


def _sorted_target_items(targets: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return sorted(
        targets.items(),
        key=lambda item: (-abs(_coerce_float(item[1])), str(item[0])),
    )


def _sorted_positions(positions: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        positions,
        key=lambda row: (
            -abs(_coerce_float(row.get("market_value"))),
            str(row.get("symbol") or ""),
        ),
    )


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _labels(lang: str) -> Mapping[str, str]:
    normalized = str(lang or "en").strip().lower()
    if normalized.startswith("zh"):
        return {
            "title_prefix": "PaperSignal",
            "overview": "概览",
            "signal_section": "信号",
            "targets_section": "目标持仓",
            "positions_section": "当前持仓",
            "execution_section": "执行摘要",
            "pending_section": "待执行计划",
            "notes_section": "策略摘要",
            "strategy": "策略",
            "account": "账户组",
            "as_of": "日期",
            "nav": "净值",
            "cash": "现金",
            "queue": "排队状态",
            "status": "状态",
            "signal": "信号",
            "target_mode": "目标模式",
            "quantity": "数量",
            "market_value": "市值",
            "average_cost": "成本",
            "execution_status": "执行状态",
            "effective_session": "执行交易日",
            "trade_count": "成交笔数",
            "turnover": "换手额",
            "commission": "手续费",
            "slippage": "滑点成本",
            "last_execution": "上次执行日",
            "effective_date": "生效日",
            "created_as_of": "创建日",
            "none": "无",
            "unknown": "未知",
            "more_items": "... 其余 {count} 项",
        }
    return {
        "title_prefix": "PaperSignal",
        "overview": "Overview",
        "signal_section": "Signal",
        "targets_section": "Targets",
        "positions_section": "Positions",
        "execution_section": "Execution",
        "pending_section": "Pending Plan",
        "notes_section": "Notes",
        "strategy": "Strategy",
        "account": "Account Group",
        "as_of": "As Of",
        "nav": "NAV",
        "cash": "Cash",
        "queue": "Queue Status",
        "status": "Status",
        "signal": "Signal",
        "target_mode": "Target Mode",
        "quantity": "qty",
        "market_value": "market_value",
        "average_cost": "avg_cost",
        "execution_status": "Execution Status",
        "effective_session": "Effective Session",
        "trade_count": "Trade Count",
        "turnover": "Turnover",
        "commission": "Commission",
        "slippage": "Slippage",
        "last_execution": "Last Execution",
        "effective_date": "Effective Date",
        "created_as_of": "Created As Of",
        "none": "none",
        "unknown": "unknown",
        "more_items": "... and {count} more",
    }
