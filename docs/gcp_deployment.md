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

## Notes

- `PaperSignalPlatform` stays brokerless even in production deployment.
- The recommended deployment unit is one Cloud Run Job per `strategy_profile x paper_account_group`.
- If multiple strategies share one paper-only project, isolate them by job name,
  scheduler job name, and `artifact_bucket_prefix`.
