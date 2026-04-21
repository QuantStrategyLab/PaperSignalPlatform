#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/cloud_run_review_pack_job.env.example}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "env file not found: ${ENV_FILE}" >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

required_vars=(
  PROJECT_ID
  REGION
  JOB_NAME
  SCHEDULER_JOB_NAME
  CRON_SCHEDULE
  TIME_ZONE
  SCHEDULER_SERVICE_ACCOUNT
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

run_uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run"

command=(
  gcloud
  scheduler
  jobs
)

if gcloud scheduler jobs describe "${SCHEDULER_JOB_NAME}" --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
  command+=(update http "${SCHEDULER_JOB_NAME}")
else
  command+=(create http "${SCHEDULER_JOB_NAME}")
fi

command+=(
  --project "${PROJECT_ID}"
  --location "${REGION}"
  --schedule "${CRON_SCHEDULE}"
  --time-zone "${TIME_ZONE}"
  --uri "${run_uri}"
  --http-method POST
  --oauth-service-account-email "${SCHEDULER_SERVICE_ACCOUNT}"
  --oauth-token-scope https://www.googleapis.com/auth/cloud-platform
)

"${command[@]}"
