from __future__ import annotations

from application.operator_incident_actions import (
    execute_incident_review_action,
    plan_incident_review_actions,
)


def test_plan_incident_review_actions_filters_by_severity_and_builds_gcs_request():
    dashboard_summary = {
        "triggers": [
            {
                "suggested_incident_id": "psp-sg-tqqq-growth-income-20260422-001",
                "severity": "critical",
                "strategy_profile": "tqqq_growth_income",
                "paper_account_group": "sg_tqqq",
                "suggested_start_date": "2026-04-22",
                "suggested_end_date": "2026-04-23",
                "suggested_period_label": "incident psp-sg-tqqq-growth-income-20260422-001",
            },
            {
                "suggested_incident_id": "psp-sg-soxl-soxx-trend-income-20260422-001",
                "severity": "warning",
                "strategy_profile": "soxl_soxx_trend_income",
                "paper_account_group": "sg_semis",
                "suggested_start_date": "2026-04-22",
                "suggested_end_date": "2026-04-22",
                "suggested_period_label": "incident psp-sg-soxl-soxx-trend-income-20260422-001",
            },
        ]
    }

    actions = plan_incident_review_actions(
        dashboard_summary,
        project_id="quantstrategylab-paper-signal",
        region="asia-southeast1",
        review_job_name="paper-signal-ops-review-pack-sg",
        min_severity="critical",
        review_backend="gcs",
        review_bucket="quantstrategylab-paper-signal-artifacts",
        review_prefix="paper-signal/sg",
        review_script_path="/app/scripts/print_operator_review_pack.py",
        review_max_books=12,
        review_max_events=24,
        review_telegram_chat_id="-100123456",
        notify_lang="zh-CN",
    )

    assert len(actions) == 1
    action = actions[0]
    assert action["incident_id"] == "psp-sg-tqqq-growth-income-20260422-001"
    assert action["review_job_uri"] == (
        "https://run.googleapis.com/v2/projects/quantstrategylab-paper-signal/"
        "locations/asia-southeast1/jobs/paper-signal-ops-review-pack-sg:run"
    )
    assert action["review_args"] == [
        "/app/scripts/print_operator_review_pack.py",
        "--backend",
        "gcs",
        "--review-type",
        "incident",
        "--start-date",
        "2026-04-22",
        "--end-date",
        "2026-04-23",
        "--period-label",
        "incident psp-sg-tqqq-growth-income-20260422-001",
        "--max-books",
        "12",
        "--max-events",
        "24",
        "--lang",
        "zh-CN",
        "--bucket",
        "quantstrategylab-paper-signal-artifacts",
        "--project-id",
        "quantstrategylab-paper-signal",
        "--prefix",
        "paper-signal/sg",
        "--strategy-profile",
        "tqqq_growth_income",
        "--paper-account-group",
        "sg_tqqq",
        "--send-telegram",
    ]
    assert action["review_env"] == [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "quantstrategylab-paper-signal"},
        {"name": "NOTIFY_LANG", "value": "zh-CN"},
        {"name": "GLOBAL_TELEGRAM_CHAT_ID", "value": "-100123456"},
    ]
    assert action["request_body"]["overrides"]["containerOverrides"][0]["args"] == action["review_args"]


def test_plan_incident_review_actions_supports_local_json_without_telegram():
    dashboard_summary = {
        "triggers": [
            {
                "suggested_incident_id": "psp-sg-global-etf-rotation-20260422-001",
                "severity": "warning",
                "strategy_profile": "global_etf_rotation",
                "paper_account_group": "sg_core",
                "suggested_start_date": "2026-04-22",
                "suggested_end_date": "2026-04-22",
                "suggested_period_label": "incident psp-sg-global-etf-rotation-20260422-001",
            }
        ]
    }

    actions = plan_incident_review_actions(
        dashboard_summary,
        project_id="quantstrategylab-paper-signal",
        region="asia-southeast1",
        review_job_name="paper-signal-ops-review-pack-sg",
        min_severity="warning",
        review_backend="local_json",
        review_artifact_dir="/tmp/paper-artifacts",
        review_send_telegram=False,
        notify_lang="en",
    )

    assert len(actions) == 1
    action = actions[0]
    assert "--artifact-dir" in action["review_args"]
    assert "/tmp/paper-artifacts" in action["review_args"]
    assert "--send-telegram" not in action["review_args"]
    assert action["review_env"] == [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "quantstrategylab-paper-signal"},
        {"name": "NOTIFY_LANG", "value": "en"},
    ]


def test_execute_incident_review_action_posts_request_and_returns_operation():
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"name": "operations/run-123"}

    class _FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def post(self, url: str, *, json: dict[str, object], timeout: float):
            self.calls.append({"url": url, "json": json, "timeout": timeout})
            return _FakeResponse()

    action = {
        "incident_id": "psp-sg-dynamic-mega-20260422-001",
        "review_job_name": "paper-signal-ops-review-pack-sg",
        "review_job_uri": "https://run.googleapis.com/v2/projects/p/locations/r/jobs/j:run",
        "request_body": {"overrides": {"containerOverrides": [{"args": ["python", "demo.py"]}]}},
    }
    session = _FakeSession()

    result = execute_incident_review_action(
        action,
        authorized_session=session,
        timeout_sec=45.0,
    )

    assert session.calls == [
        {
            "url": "https://run.googleapis.com/v2/projects/p/locations/r/jobs/j:run",
            "json": {"overrides": {"containerOverrides": [{"args": ["python", "demo.py"]}]}},
            "timeout": 45.0,
        }
    ]
    assert result == {
        "incident_id": "psp-sg-dynamic-mega-20260422-001",
        "review_job_name": "paper-signal-ops-review-pack-sg",
        "operation_name": "operations/run-123",
        "response": {"name": "operations/run-123"},
    }
