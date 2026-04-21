# GCP Deployment

## Recommendation

Deploy `PaperSignalPlatform` into a dedicated GCP project instead of sharing the
same project with live trading runtimes.

Suggested project boundary:

- one paper-only GCP project
- one artifact bucket for reconciliation JSON
- one Firestore database for latest paper-account state
- one or more Cloud Run Jobs
- one Cloud Scheduler job per runtime job
- optional separate Cloud Run Jobs for daily or weekly operator summaries
- optional separate Cloud Run Jobs for monthly or incident-oriented operator review packs
- optional separate Cloud Run Jobs for daily or weekly incident trigger dashboards
- no broker secrets
- no broker gateway connectivity
- no live trading IAM roles

## Minimum services

Enable these APIs in the paper-only project:

- `run.googleapis.com`
- `cloudscheduler.googleapis.com`
- `secretmanager.googleapis.com`
- `firestore.googleapis.com`
- `storage.googleapis.com`
- `artifactregistry.googleapis.com`

## Service accounts

Recommended split:

- runtime service account
  - used by the Cloud Run Job
  - grant `roles/secretmanager.secretAccessor`
  - grant a Firestore role that includes document read/write, such as `roles/datastore.user`
  - grant bucket-scoped `roles/storage.objectAdmin` on the artifact bucket
  - if scheduled incident auto-open is enabled, also grant `roles/run.invoker`
    on the deployed review-pack Cloud Run Job that will be executed
- scheduler service account
  - used by Cloud Scheduler to call the Cloud Run Jobs API
  - grant a role that includes `run.jobs.run`, typically `roles/run.invoker`

## Runtime config

The default production-like backend combination is:

- `PAPER_SIGNAL_STATE_STORE_BACKEND=firestore`
- `PAPER_SIGNAL_FIRESTORE_COLLECTION=paper_signal_states`
- `PAPER_SIGNAL_ARTIFACT_STORE_BACKEND=gcs`
- `PAPER_SIGNAL_GCS_BUCKET=<paper-artifact-bucket>`

Use Secret Manager for:

- `PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME`
- `TELEGRAM_TOKEN`

Keep `artifact_bucket_prefix` inside the account-group config as an object
prefix only, for example:

- `paper-signal/sg/coin`
- `paper-signal/sg/soxl`

## Deployment flow

1. Copy [deploy/cloud_run_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_job.env.example) to a local env file and fill in the real values.
2. Deploy or update the Cloud Run Job:

```bash
./scripts/deploy_cloud_run_job.sh deploy/cloud_run_job.env
```

3. Deploy or update the Cloud Scheduler trigger:

```bash
./scripts/deploy_cloud_scheduler_job.sh deploy/cloud_run_job.env
```

## Operator summary jobs

Use a separate env file for operator summaries:

1. Copy [deploy/cloud_run_summary_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_summary_job.env.example) to a local env file and fill in the real values.
2. Deploy or update the summary Cloud Run Job:

```bash
./scripts/deploy_operator_summary_job.sh deploy/cloud_run_summary_job.env
```

3. Deploy or update the summary Cloud Scheduler trigger:

```bash
./scripts/deploy_operator_summary_scheduler.sh deploy/cloud_run_summary_job.env
```

Recommended usage:

- one daily summary job per operating region or account cluster
- use `SUMMARY_GCS_PREFIX` to scope to one artifact subtree
- use `SUMMARY_STRATEGY_PROFILE` or `SUMMARY_PAPER_ACCOUNT_GROUP` only when a narrower summary is needed
- if the production image does not start in the repo root, override `SUMMARY_SCRIPT_PATH` with the in-container absolute path
- keep the summary job separate from the per-strategy paper signal jobs

## Operator review pack jobs

Use a separate env file for monthly or incident-oriented review packs:

1. Copy [deploy/cloud_run_review_pack_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_review_pack_job.env.example) to a local env file and fill in the real values.
2. Deploy or update the review-pack Cloud Run Job:

```bash
./scripts/deploy_operator_review_pack_job.sh deploy/cloud_run_review_pack_job.env
```

3. Deploy or update the review-pack Cloud Scheduler trigger:

```bash
./scripts/deploy_operator_review_pack_scheduler.sh deploy/cloud_run_review_pack_job.env
```

Recommended usage:

- one monthly review-pack job per operating region or account cluster
- set `REVIEW_TYPE=incident` only for ad hoc or incident-specific windows
- use `REVIEW_GCS_PREFIX` to scope to one artifact subtree
- use `REVIEW_STRATEGY_PROFILE` or `REVIEW_PAPER_ACCOUNT_GROUP` only when a narrower review is needed
- if the production image does not start in the repo root, override `REVIEW_SCRIPT_PATH` with the in-container absolute path
- keep the review-pack job separate from the per-strategy paper signal jobs and from the daily summary jobs

For ad hoc incident execution, keep one deployed review-pack job per region and
reuse it with [docs/incident_playbook.md](/home/ubuntu/Projects/PaperSignalPlatform/docs/incident_playbook.md) plus
[scripts/execute_operator_incident_review_pack.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/execute_operator_incident_review_pack.sh).

## Incident auto-open jobs

Use a separate env file for optional scheduled auto-open from dashboard findings:

1. Copy [deploy/cloud_run_incident_review_actions_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_incident_review_actions_job.env.example) to a local env file and fill in the real values.
2. Deploy or update the incident-action Cloud Run Job:

```bash
./scripts/deploy_incident_review_actions_job.sh deploy/cloud_run_incident_review_actions_job.env
```

3. Deploy or update the incident-action Cloud Scheduler trigger:

```bash
./scripts/deploy_incident_review_actions_scheduler.sh deploy/cloud_run_incident_review_actions_job.env
```

Recommended usage:

- start with `ACTION_EXECUTE=false` so the scheduled job only prints the planned incident actions to logs
- once validated, switch to `ACTION_EXECUTE=true`
- keep `ACTION_MIN_SEVERITY=critical` in the first production rollout
- reuse the same `REVIEW_JOB_NAME` as the deployed review-pack job for that region
- keep `ACTION_GCS_PREFIX` and `REVIEW_GCS_PREFIX` aligned with the same artifact subtree
- the incident-action job does not need Telegram secrets; it reuses the review-pack job, which already owns Telegram delivery
- if the production image does not start in the repo root, override `ACTION_SCRIPT_PATH` and `REVIEW_SCRIPT_PATH` with in-container absolute paths

## Incident trigger dashboard jobs

Use a separate env file for scheduled trigger dashboards:

1. Copy [deploy/cloud_run_incident_dashboard_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_incident_dashboard_job.env.example) to a local env file and fill in the real values.
2. Deploy or update the incident dashboard Cloud Run Job:

```bash
./scripts/deploy_incident_trigger_dashboard_job.sh deploy/cloud_run_incident_dashboard_job.env
```

3. Deploy or update the incident dashboard Cloud Scheduler trigger:

```bash
./scripts/deploy_incident_trigger_dashboard_scheduler.sh deploy/cloud_run_incident_dashboard_job.env
```

Recommended usage:

- one daily dashboard job per operating region or account cluster
- keep `DASHBOARD_GCS_PREFIX` aligned with the same artifact subtree used by the paper jobs in that region
- keep `DASHBOARD_REGION_CODE` short and stable because it feeds the suggested incident ids
- use `DASHBOARD_STRATEGY_PROFILE` or `DASHBOARD_PAPER_ACCOUNT_GROUP` only when an intentionally narrower dashboard is needed
- if the production image does not start in the repo root, override `DASHBOARD_SCRIPT_PATH` with the in-container absolute path
- keep the dashboard job separate from the review-pack jobs so operators can inspect triggers before opening an incident replay
- if auto-open is enabled, still keep the dashboard job because it remains the operator-facing source of truth for why an incident review was opened

## Notes

- `PaperSignalPlatform` stays brokerless even in production deployment.
- The recommended deployment unit is one Cloud Run Job per `strategy_profile x paper_account_group`.
- If multiple strategies share one paper-only project, isolate them by job name,
  scheduler job name, and `artifact_bucket_prefix`.
