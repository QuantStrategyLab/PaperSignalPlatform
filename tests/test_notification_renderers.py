from __future__ import annotations

from application.notification_renderers import build_cycle_notification_message


def test_build_cycle_notification_message_renders_zh_sections_and_truncates_lists():
    summary = {
        "strategy_profile": "russell_1000_multi_factor_defensive",
        "paper_account_group": "sg_russell_paper",
        "as_of": "2026-04-22",
        "nav": 125000.0,
        "cash": 4200.5,
        "queue_status": "queued_pending_plan",
        "decision": {
            "execution_annotations": {
                "status_display": "风险开启",
                "signal_display": "维持分散轮动",
                "dashboard_text": "成长因子回落，保持防御。",
            }
        },
        "allocation": {
            "target_mode": "weight",
            "targets": {f"SYM{i:02d}": i / 100 for i in range(1, 15)},
        },
        "positions": [
            {
                "symbol": f"POS{i:02d}",
                "quantity": float(i),
                "market_value": float(i * 1000),
                "average_cost": float(i * 10),
            }
            for i in range(1, 15)
        ],
        "execution": {
            "status": "executed_pending_plan",
            "effective_session": "2026-04-22",
            "trade_count": 4,
            "turnover_value": 15000.0,
            "commission_paid": 6.4,
            "slippage_cost": 3.2,
        },
        "last_execution": {"effective_session": "2026-04-21"},
        "pending_plan": {
            "effective_date": "2026-04-23",
            "created_as_of": "2026-04-22",
            "target_mode": "weight",
            "targets": {f"NEXT{i:02d}": i / 200 for i in range(1, 15)},
        },
    }

    message = build_cycle_notification_message(summary, lang="zh-CN")

    assert message.title == "PaperSignal | russell_1000_multi_factor_defensive | sg_russell_paper"
    assert "[概览]" in message.body
    assert "[目标持仓]" in message.body
    assert "[当前持仓]" in message.body
    assert "状态: 风险开启" in message.body
    assert "信号: 维持分散轮动" in message.body
    assert "- SYM14: 14.00%" in message.body
    assert "- SYM02: 2.00%" not in message.body
    assert "... 其余 2 项" in message.body
    assert "- POS14: 数量=14.0000, 市值=$14,000.00, 成本=$140.00" in message.body
    assert "- POS02: 数量=2.0000, 市值=$2,000.00, 成本=$20.00" not in message.body
    assert "成长因子回落，保持防御。" in message.body


def test_build_cycle_notification_message_renders_execution_and_pending_plan_in_english():
    summary = {
        "strategy_profile": "tqqq_growth_income",
        "paper_account_group": "sg_tqqq_paper",
        "as_of": "2026-04-22",
        "nav": 101500.0,
        "cash": 980.0,
        "queue_status": "queued_pending_plan",
        "decision": {
            "execution_annotations": {
                "status_display": "Risk-on",
                "signal_display": "Rotate toward growth sleeves",
                "dashboard_text": "TQQQ stays above its short trend filter.",
            }
        },
        "allocation": {
            "target_mode": "value",
            "targets": {
                "TQQQ": 50000.0,
                "QQQ": 25000.0,
                "BOXX": 15000.0,
            },
        },
        "positions": [],
        "execution": {
            "status": "executed_pending_plan",
            "effective_session": "2026-04-22",
            "trade_count": 3,
            "turnover_value": 25000.0,
            "commission_paid": 5.0,
            "slippage_cost": 2.5,
        },
        "last_execution": {"effective_session": "2026-04-21"},
        "pending_plan": {
            "effective_date": "2026-04-23",
            "created_as_of": "2026-04-22",
            "target_mode": "value",
            "targets": {
                "TQQQ": 52000.0,
                "QQQ": 20000.0,
            },
        },
    }

    message = build_cycle_notification_message(summary, lang="en")

    assert message.title == "PaperSignal | tqqq_growth_income | sg_tqqq_paper"
    assert "[Execution]" in message.body
    assert "Execution Status: executed_pending_plan" in message.body
    assert "Effective Session: 2026-04-22" in message.body
    assert "Trade Count: 3" in message.body
    assert "Turnover: $25,000.00" in message.body
    assert "Commission: $5.00" in message.body
    assert "Slippage: $2.50" in message.body
    assert "[Pending Plan]" in message.body
    assert "Effective Date: 2026-04-23" in message.body
    assert "- TQQQ: $52,000.00" in message.body
    assert "TQQQ stays above its short trend filter." in message.body
