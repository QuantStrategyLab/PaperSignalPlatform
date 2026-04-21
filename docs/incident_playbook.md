# Incident Playbook

`PaperSignalPlatform` keeps incident handling brokerless as well. An incident
review is an operator-only replay of reconciliation artifacts that produces one
focused Telegram pack and one auditable incident label.

## Trigger rules

Open an incident review when any of the following is true:

1. A reconciliation artifact shows a non-normal `queue_status` or
   `execution.status`.
   Normal statuses today are:
   - `queued_pending_plan`
   - `no_actionable_allocation`
   - `no_pending_plan`
   - `executed_pending_plan`
2. A scheduled paper run did not produce the expected Telegram signal or
   reconciliation artifact for the trading day.
3. An operator had to intervene manually after a config, deployment, or data
   issue.
4. A single strategy or account group needs a narrow replay window before
   broader monthly review.

Before opening the incident review, operators should first inspect the trigger
dashboard:

```bash
python scripts/print_incident_trigger_dashboard.py --period daily --as-of 2026-04-22 --region-code sg
```

The dashboard only surfaces abnormal books and suggests one incident window and
incident identifier per affected `strategy_profile x paper_account_group`.

For routine operations, this dashboard can also be scheduled as its own Cloud
Run Job. See
[docs/gcp_deployment.md](/home/ubuntu/Projects/PaperSignalPlatform/docs/gcp_deployment.md)
for the incident dashboard deployment template.

## Optional auto-open path

`PaperSignalPlatform` can optionally convert dashboard findings into incident
review-pack job runs automatically. This should stay conservative:

1. first deploy the action job in preview mode with `ACTION_EXECUTE=false`
2. review the planned actions in Cloud Run logs for a few trading days
3. only then turn on `ACTION_EXECUTE=true`
4. keep the first live threshold at `ACTION_MIN_SEVERITY=critical`

The action job does not build a second review implementation. It reuses the
deployed review-pack Cloud Run Job through run-time argument overrides, so the
same artifact readers and Telegram rendering stay in one place.

## Incident naming

Use one canonical incident identifier:

`psp-<region>-<scope>-<yyyymmdd>-<seq>`

Examples:

- `psp-sg-core-20260422-001`
- `psp-us-soxl-20260422-001`
- `psp-sg-dynamic-mega-20260422-002`

Guidelines:

- `region`: deployment or operator region, for example `sg` or `us`
- `scope`: `core` for multi-book incidents, otherwise the affected strategy or
  book alias
- `yyyymmdd`: first day the incident was observed
- `seq`: two or three digit sequence for same-day repeats

## Time window rules

- `INCIDENT_START_DATE`: first impacted trading day included in the replay
- `INCIDENT_END_DATE`: last impacted trading day included in the replay
- For a single-day event, set both dates to the same value.
- For unresolved issues, run a same-day incident pack first, then rerun with a
  wider window once the impact boundary is known.

## Telegram routing

- Default receiver: the job's configured `GLOBAL_TELEGRAM_CHAT_ID`
- If the incident should go to a different bridge or escalation room, set
  `INCIDENT_TELEGRAM_CHAT_ID` in the incident env file
- Keep strategy-level filters empty for cross-book incidents
- Set `INCIDENT_STRATEGY_PROFILE` and/or `INCIDENT_PAPER_ACCOUNT_GROUP` only
  when the incident is intentionally narrowed

## Standard execution flow

1. Copy [deploy/operator_incident_review.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/operator_incident_review.env.example) to a local env file.
2. Fill in:
   - `PROJECT_ID`
   - `REGION`
   - `JOB_NAME`
   - `INCIDENT_ID`
   - `INCIDENT_START_DATE`
   - `INCIDENT_END_DATE`
3. Optionally narrow the scope with:
   - `INCIDENT_STRATEGY_PROFILE`
   - `INCIDENT_PAPER_ACCOUNT_GROUP`
4. Optionally override Telegram routing with `INCIDENT_TELEGRAM_CHAT_ID`
5. Optionally copy the suggested incident identifier from
   `scripts/print_incident_trigger_dashboard.py`
6. Execute the incident review:

```bash
./scripts/execute_operator_incident_review_pack.sh deploy/operator_incident_review.env
```

The script reuses the deployed review-pack Cloud Run Job, but overrides the
execution arguments for:

- `--review-type incident`
- the incident date window
- the incident label
- optional strategy/account filters
- optional Telegram chat override

For scheduled auto-open instead of manual execution, use:

- [deploy/cloud_run_incident_review_actions_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_incident_review_actions_job.env.example)
- [scripts/deploy_incident_review_actions_job.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_incident_review_actions_job.sh)
- [scripts/deploy_incident_review_actions_scheduler.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_incident_review_actions_scheduler.sh)

## Output convention

The review pack title defaults to:

`PaperSignal | Operator Review incident <INCIDENT_ID>`

If an alternate operator-facing label is needed, set `INCIDENT_PERIOD_LABEL`.
Otherwise keep the identifier stable and reuse it across follow-up reruns.
