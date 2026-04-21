from __future__ import annotations

from typing import Any, Mapping

MIN_SEVERITY_RANK = {
    "all": 0,
    "warning": 1,
    "critical": 2,
}
TRIGGER_SEVERITY_RANK = {
    "warning": 1,
    "critical": 2,
}


def plan_incident_review_actions(
    dashboard_summary: Mapping[str, Any],
    *,
    project_id: str,
    region: str,
    review_job_name: str,
    min_severity: str = "critical",
    max_reviews: int = 3,
    review_backend: str = "gcs",
    review_bucket: str | None = None,
    review_prefix: str = "",
    review_artifact_dir: str = ".paper_signal/artifacts",
    review_script_path: str = "scripts/print_operator_review_pack.py",
    review_max_books: int = 10,
    review_max_events: int = 20,
    review_send_telegram: bool = True,
    review_telegram_chat_id: str | None = None,
    notify_lang: str = "en",
) -> list[dict[str, Any]]:
    """Convert dashboard triggers into Cloud Run Job execution plans."""

    normalized_min_severity = str(min_severity or "critical").strip().lower()
    if normalized_min_severity not in MIN_SEVERITY_RANK:
        expected = ", ".join(sorted(MIN_SEVERITY_RANK))
        raise ValueError(
            f"Unsupported min severity {min_severity!r}; expected one of {expected}"
        )

    normalized_backend = str(review_backend or "gcs").strip().lower()
    if normalized_backend not in {"gcs", "local_json"}:
        raise ValueError("review_backend must be 'gcs' or 'local_json'")
    if normalized_backend == "gcs" and not str(review_bucket or "").strip():
        raise ValueError("review_bucket is required when review_backend='gcs'")

    selected_triggers = [
        dict(trigger)
        for trigger in dashboard_summary.get("triggers") or ()
        if TRIGGER_SEVERITY_RANK.get(str(trigger.get("severity") or "").strip().lower(), 0)
        >= MIN_SEVERITY_RANK[normalized_min_severity]
    ]
    if max_reviews > 0:
        selected_triggers = selected_triggers[:max_reviews]

    actions: list[dict[str, Any]] = []
    for trigger in selected_triggers:
        review_args = [
            str(review_script_path or "scripts/print_operator_review_pack.py"),
            "--backend",
            normalized_backend,
            "--review-type",
            "incident",
            "--start-date",
            str(trigger.get("suggested_start_date") or ""),
            "--end-date",
            str(trigger.get("suggested_end_date") or ""),
            "--period-label",
            str(trigger.get("suggested_period_label") or ""),
            "--max-books",
            str(int(review_max_books)),
            "--max-events",
            str(int(review_max_events)),
            "--lang",
            str(notify_lang or "en"),
        ]
        if normalized_backend == "gcs":
            review_args.extend(
                [
                    "--bucket",
                    str(review_bucket),
                    "--project-id",
                    str(project_id),
                ]
            )
            if str(review_prefix or "").strip():
                review_args.extend(["--prefix", str(review_prefix).strip()])
        else:
            review_args.extend(["--artifact-dir", str(review_artifact_dir or ".paper_signal/artifacts")])

        trigger_profile = str(trigger.get("strategy_profile") or "").strip()
        trigger_group = str(trigger.get("paper_account_group") or "").strip()
        if trigger_profile:
            review_args.extend(["--strategy-profile", trigger_profile])
        if trigger_group:
            review_args.extend(["--paper-account-group", trigger_group])
        if review_send_telegram:
            review_args.append("--send-telegram")

        env_vars = [
            {"name": "GOOGLE_CLOUD_PROJECT", "value": str(project_id)},
            {"name": "NOTIFY_LANG", "value": str(notify_lang or "en")},
        ]
        if str(review_telegram_chat_id or "").strip():
            env_vars.append(
                {
                    "name": "GLOBAL_TELEGRAM_CHAT_ID",
                    "value": str(review_telegram_chat_id).strip(),
                }
            )

        actions.append(
            {
                "incident_id": str(trigger.get("suggested_incident_id") or ""),
                "severity": str(trigger.get("severity") or ""),
                "strategy_profile": trigger_profile,
                "paper_account_group": trigger_group,
                "start_date": str(trigger.get("suggested_start_date") or ""),
                "end_date": str(trigger.get("suggested_end_date") or ""),
                "period_label": str(trigger.get("suggested_period_label") or ""),
                "review_job_name": review_job_name,
                "review_job_uri": (
                    f"https://run.googleapis.com/v2/projects/{project_id}/locations/{region}/jobs/{review_job_name}:run"
                ),
                "review_args": review_args,
                "review_env": env_vars,
                "request_body": {
                    "overrides": {
                        "containerOverrides": [
                            {
                                "args": review_args,
                                "env": env_vars,
                            }
                        ]
                    }
                },
            }
        )
    return actions


def execute_incident_review_action(
    action: Mapping[str, Any],
    *,
    authorized_session: Any,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    """Execute one pre-planned Cloud Run Job action."""

    response = authorized_session.post(
        str(action["review_job_uri"]),
        json=dict(action["request_body"]),
        timeout=timeout_sec,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "incident_id": action.get("incident_id"),
        "review_job_name": action.get("review_job_name"),
        "operation_name": payload.get("name"),
        "response": payload,
    }


def build_google_authorized_session():
    """Build an authorized HTTP session for Cloud Run Jobs API calls."""

    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return AuthorizedSession(credentials)
