from __future__ import annotations

from application.operator_incident_dashboard import (
    build_incident_trigger_dashboard_message,
    summarize_incident_trigger_dashboard,
)


def test_summarize_incident_trigger_dashboard_groups_abnormal_books_and_suggests_ids():
    records = [
        {
            "strategy_profile": "global_etf_rotation",
            "paper_account_group": "sg_alpha",
            "payload": {
                "as_of": "2026-04-21",
                "queue_status": "queued_pending_plan",
                "execution": {"status": "executed_pending_plan"},
                "decision": {"execution_annotations": {"status_display": "Hold", "signal_display": "Stay allocated"}},
            },
        },
        {
            "strategy_profile": "tqqq_growth_income",
            "paper_account_group": "sg_beta",
            "payload": {
                "as_of": "2026-04-22",
                "queue_status": "manual_review",
                "execution": {"status": "skipped_risk_gate"},
                "decision": {"execution_annotations": {"status_display": "Risk gate", "signal_display": "Stay in cash"}},
            },
        },
        {
            "strategy_profile": "tqqq_growth_income",
            "paper_account_group": "sg_beta",
            "payload": {
                "as_of": "2026-04-23",
                "queue_status": "manual_review",
                "execution": {"status": "skipped_risk_gate"},
                "decision": {"execution_annotations": {"status_display": "Risk gate", "signal_display": "Stay in cash"}},
            },
        },
        {
            "strategy_profile": "soxl_soxx_trend_income",
            "paper_account_group": "sg_semis",
            "payload": {
                "as_of": "2026-04-23",
                "queue_status": "manual_review",
                "execution": {"status": "executed_pending_plan"},
                "decision": {"execution_annotations": {"status_display": "Review", "signal_display": "Check allocations"}},
            },
        },
    ]

    dashboard = summarize_incident_trigger_dashboard(
        records,
        start_date="2026-04-22",
        end_date="2026-04-23",
        region_code="sg",
    )

    assert dashboard["record_count"] == 4
    assert dashboard["incident_record_count"] == 3
    assert dashboard["trigger_count"] == 2
    assert dashboard["critical_trigger_count"] == 1
    assert dashboard["warning_trigger_count"] == 1
    assert dashboard["abnormal_queue_counts"]["manual_review"] == 3
    assert dashboard["abnormal_execution_counts"]["skipped_risk_gate"] == 2
    assert dashboard["triggers"][0]["severity"] == "critical"
    assert dashboard["triggers"][0]["strategy_profile"] == "tqqq_growth_income"
    assert dashboard["triggers"][0]["suggested_incident_id"] == "psp-sg-tqqq-growth-income-20260422-001"
    assert dashboard["triggers"][0]["suggested_start_date"] == "2026-04-22"
    assert dashboard["triggers"][0]["suggested_end_date"] == "2026-04-23"
    assert dashboard["triggers"][1]["severity"] == "warning"


def test_build_incident_trigger_dashboard_message_renders_english_dashboard():
    records = [
        {
            "strategy_profile": "dynamic_mega_leveraged_pullback",
            "paper_account_group": "sg_dynamic_mega",
            "payload": {
                "as_of": "2026-04-22",
                "queue_status": "manual_review",
                "execution": {"status": "skipped_risk_gate"},
                "decision": {
                    "execution_annotations": {
                        "status_display": "Risk gate",
                        "signal_display": "Stay in cash",
                    }
                },
            },
        }
    ]

    message = build_incident_trigger_dashboard_message(
        records,
        period_label="daily 2026-04-22",
        start_date="2026-04-22",
        end_date="2026-04-22",
        region_code="sg",
        lang="en",
    )

    assert message.title == "PaperSignal | Incident Trigger Dashboard daily 2026-04-22"
    assert "[Overview]" in message.body
    assert "Region: sg" in message.body
    assert "[Suggested Incidents]" in message.body
    assert "psp-sg-dynamic-mega-leveraged-pullback-20260422-001" in message.body
    assert "execution=skipped_risk_gate" in message.body


def test_build_incident_trigger_dashboard_message_renders_zh_when_no_triggers():
    message = build_incident_trigger_dashboard_message(
        [],
        period_label="daily 2026-04-22",
        start_date="2026-04-22",
        end_date="2026-04-22",
        region_code="sg",
        lang="zh-CN",
    )

    assert message.title == "PaperSignal | 事件触发看板 daily 2026-04-22"
    assert "[概览]" in message.body
    assert "触发项数: 0" in message.body
    assert "[建议开单]" in message.body
    assert "\n无" in message.body
