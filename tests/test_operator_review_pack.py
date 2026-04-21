from __future__ import annotations

from application.operator_review_pack import (
    build_operator_review_pack_message,
    summarize_operator_review_pack,
)


def test_summarize_operator_review_pack_aggregates_book_pnl_and_events():
    records = [
        {
            "strategy_profile": "global_etf_rotation",
            "paper_account_group": "sg_alpha",
            "payload": {
                "as_of": "2026-04-01",
                "nav": 100000.0,
                "cash": 10000.0,
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
                "pending_plan": {"effective_date": "2026-04-02"},
            },
        },
        {
            "strategy_profile": "global_etf_rotation",
            "paper_account_group": "sg_alpha",
            "payload": {
                "as_of": "2026-04-30",
                "nav": 105500.0,
                "cash": 4500.0,
                "queue_status": "no_actionable_allocation",
                "execution": {
                    "status": "executed_pending_plan",
                    "trade_count": 2,
                    "turnover_value": 15000.0,
                    "commission_paid": 5.0,
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
                "as_of": "2026-04-15",
                "nav": 98000.0,
                "cash": 2500.0,
                "queue_status": "manual_review",
                "execution": {
                    "status": "skipped_risk_gate",
                    "trade_count": 0,
                    "turnover_value": 0.0,
                    "commission_paid": 0.0,
                    "slippage_cost": 0.0,
                },
                "decision": {
                    "execution_annotations": {
                        "status_display": "Risk gate",
                        "signal_display": "Stay in cash",
                    }
                },
                "pending_plan": {},
            },
        },
    ]

    pack = summarize_operator_review_pack(
        records,
        review_type="monthly",
        start_date="2026-04-01",
        end_date="2026-04-30",
    )

    assert pack["record_count"] == 3
    assert pack["book_count"] == 2
    assert pack["aggregate_nav_start"] == 198000.0
    assert pack["aggregate_nav_end"] == 203500.0
    assert pack["aggregate_nav_change"] == 5500.0
    assert pack["total_trade_count"] == 2
    assert pack["incident_count"] == 1
    assert pack["incident_book_count"] == 1
    assert pack["books"][0]["strategy_profile"] == "tqqq_growth_income"
    assert pack["books"][0]["incident_count"] == 1
    assert pack["books"][1]["nav_change"] == 5500.0
    assert pack["events"][0]["event_type"] == "incident"
    assert pack["events"][1]["event_type"] == "execution"
    assert pack["events"][2]["event_type"] == "queue"


def test_build_operator_review_pack_message_renders_english_timeline():
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

    message = build_operator_review_pack_message(
        records,
        review_type="incident",
        period_label="incident 2026-04-22",
        start_date="2026-04-22",
        end_date="2026-04-22",
        lang="en",
    )

    assert message.title == "PaperSignal | Operator Review incident 2026-04-22"
    assert "[Overview]" in message.body
    assert "Review Type: incident" in message.body
    assert "[Book Changes]" in message.body
    assert "- soxl_soxx_trend_income | sg_semis | 2026-04-22 -> 2026-04-22" in message.body
    assert "[Event Timeline]" in message.body
    assert "executed 4 trade(s)" in message.body
    assert "signal=Keep SOXL sleeve on" in message.body


def test_build_operator_review_pack_message_renders_zh_when_empty():
    message = build_operator_review_pack_message(
        [],
        review_type="monthly",
        period_label="monthly 2026-04",
        start_date="2026-04-01",
        end_date="2026-04-30",
        lang="zh-CN",
    )

    assert message.title == "PaperSignal | 运维复盘 monthly 2026-04"
    assert "[概览]" in message.body
    assert "记录数: 0" in message.body
    assert "[账户变化]" in message.body
    assert "[事件时间线]" in message.body
    assert "\n无" in message.body
