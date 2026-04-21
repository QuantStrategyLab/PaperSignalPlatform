from __future__ import annotations

from application.operator_summary import build_operator_summary_message, summarize_reconciliation_records


def test_summarize_reconciliation_records_aggregates_latest_books_and_totals():
    records = [
        {
            "strategy_profile": "global_etf_rotation",
            "paper_account_group": "sg_alpha",
            "payload": {
                "as_of": "2026-04-21",
                "nav": 100000.0,
                "cash": 5000.0,
                "queue_status": "queued_pending_plan",
                "execution": {
                    "status": "no_pending_plan",
                    "trade_count": 0,
                    "turnover_value": 0.0,
                    "commission_paid": 0.0,
                    "slippage_cost": 0.0,
                },
                "decision": {
                    "execution_annotations": {
                        "status_display": "Risk-on",
                        "signal_display": "Rotate into equities",
                    }
                },
                "pending_plan": {"effective_date": "2026-04-22"},
            },
        },
        {
            "strategy_profile": "global_etf_rotation",
            "paper_account_group": "sg_alpha",
            "payload": {
                "as_of": "2026-04-22",
                "nav": 101250.0,
                "cash": 4200.0,
                "queue_status": "no_actionable_allocation",
                "execution": {
                    "status": "executed_pending_plan",
                    "trade_count": 2,
                    "turnover_value": 12000.0,
                    "commission_paid": 4.0,
                    "slippage_cost": 1.5,
                },
                "decision": {
                    "execution_annotations": {
                        "status_display": "Hold",
                        "signal_display": "Stay allocated",
                    }
                },
                "pending_plan": {},
            },
        },
        {
            "strategy_profile": "tqqq_growth_income",
            "paper_account_group": "sg_beta",
            "payload": {
                "as_of": "2026-04-22",
                "nav": 98000.0,
                "cash": 1800.0,
                "queue_status": "queued_pending_plan",
                "execution": {
                    "status": "executed_pending_plan",
                    "trade_count": 3,
                    "turnover_value": 25000.0,
                    "commission_paid": 6.0,
                    "slippage_cost": 2.0,
                },
                "decision": {
                    "execution_annotations": {
                        "status_display": "Risk-on",
                        "signal_display": "Lean growth",
                    }
                },
                "pending_plan": {"effective_date": "2026-04-23"},
            },
        },
    ]

    summary = summarize_reconciliation_records(
        records,
        start_date="2026-04-21",
        end_date="2026-04-22",
    )

    assert summary["record_count"] == 3
    assert summary["book_count"] == 2
    assert summary["aggregate_nav"] == 199250.0
    assert summary["aggregate_cash"] == 6000.0
    assert summary["total_trade_count"] == 5
    assert summary["total_turnover"] == 37000.0
    assert summary["total_commission"] == 10.0
    assert summary["total_slippage"] == 3.5
    assert summary["queue_counts"]["queued_pending_plan"] == 2
    assert summary["execution_counts"]["executed_pending_plan"] == 2
    assert summary["books"][0]["strategy_profile"] == "tqqq_growth_income"
    assert summary["books"][1]["signal"] == "Stay allocated"


def test_build_operator_summary_message_renders_english_summary():
    records = [
        {
            "strategy_profile": "soxl_soxx_trend_income",
            "paper_account_group": "sg_semis",
            "payload": {
                "as_of": "2026-04-22",
                "nav": 125500.0,
                "cash": 3200.0,
                "queue_status": "queued_pending_plan",
                "execution": {
                    "status": "executed_pending_plan",
                    "trade_count": 4,
                    "turnover_value": 28000.0,
                    "commission_paid": 7.5,
                    "slippage_cost": 3.1,
                },
                "decision": {
                    "execution_annotations": {
                        "status_display": "Trend up",
                        "signal_display": "Keep SOXL sleeve on",
                    }
                },
                "pending_plan": {"effective_date": "2026-04-23"},
            },
        }
    ]

    message = build_operator_summary_message(
        records,
        period_label="daily 2026-04-22",
        start_date="2026-04-22",
        end_date="2026-04-22",
        lang="en",
    )

    assert message.title == "PaperSignal | Operator Summary daily 2026-04-22"
    assert "[Overview]" in message.body
    assert "Window: 2026-04-22 -> 2026-04-22" in message.body
    assert "Total Trades: 4" in message.body
    assert "[Books]" in message.body
    assert "- soxl_soxx_trend_income | sg_semis | 2026-04-22" in message.body
    assert "signal=Keep SOXL sleeve on" in message.body
    assert "pending=2026-04-23" in message.body


def test_build_operator_summary_message_renders_zh_when_no_records():
    message = build_operator_summary_message(
        [],
        period_label="weekly 2026-04-22",
        start_date="2026-04-16",
        end_date="2026-04-22",
        lang="zh-CN",
    )

    assert message.title == "PaperSignal | 运维摘要 weekly 2026-04-22"
    assert "[概览]" in message.body
    assert "记录数: 0" in message.body
    assert "[账户摘要]" in message.body
    assert "\n无" in message.body
