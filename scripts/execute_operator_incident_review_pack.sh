#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/operator_incident_review.env.example}"

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
  INCIDENT_ID
  INCIDENT_START_DATE
  INCIDENT_END_DATE
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

python_command="${PYTHON_COMMAND:-python}"
review_script_path="${REVIEW_SCRIPT_PATH:-scripts/print_operator_review_pack.py}"
review_backend="${REVIEW_BACKEND:-gcs}"
incident_max_books="${INCIDENT_MAX_BOOKS:-10}"
incident_max_events="${INCIDENT_MAX_EVENTS:-20}"
incident_send_telegram="${INCIDENT_SEND_TELEGRAM:-true}"
incident_wait="${INCIDENT_WAIT:-true}"
notify_lang="${NOTIFY_LANG:-en}"
incident_period_label="${INCIDENT_PERIOD_LABEL:-incident ${INCIDENT_ID}}"

if [[ "${review_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when REVIEW_BACKEND=gcs" >&2
  exit 1
fi

job_args=(
  "${review_script_path}"
  "--backend" "${review_backend}"
  "--review-type" "incident"
  "--start-date" "${INCIDENT_START_DATE}"
  "--end-date" "${INCIDENT_END_DATE}"
  "--period-label" "${incident_period_label}"
  "--max-books" "${incident_max_books}"
  "--max-events" "${incident_max_events}"
  "--lang" "${notify_lang}"
)

if [[ "${review_backend}" == "gcs" ]]; then
  job_args+=("--bucket" "${PAPER_SIGNAL_GCS_BUCKET}" "--project-id" "${PROJECT_ID}")
  if [[ -n "${REVIEW_GCS_PREFIX:-}" ]]; then
    job_args+=("--prefix" "${REVIEW_GCS_PREFIX}")
  fi
else
  review_artifact_dir="${REVIEW_ARTIFACT_DIR:-.paper_signal/artifacts}"
  job_args+=("--artifact-dir" "${review_artifact_dir}")
fi

if [[ -n "${INCIDENT_STRATEGY_PROFILE:-}" ]]; then
  job_args+=("--strategy-profile" "${INCIDENT_STRATEGY_PROFILE}")
fi
if [[ -n "${INCIDENT_PAPER_ACCOUNT_GROUP:-}" ]]; then
  job_args+=("--paper-account-group" "${INCIDENT_PAPER_ACCOUNT_GROUP}")
fi
if [[ "${incident_send_telegram}" == "true" ]]; then
  job_args+=("--send-telegram")
fi

env_vars=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "NOTIFY_LANG=${notify_lang}"
)
if [[ -n "${INCIDENT_TELEGRAM_CHAT_ID:-}" ]]; then
  env_vars+=("GLOBAL_TELEGRAM_CHAT_ID=${INCIDENT_TELEGRAM_CHAT_ID}")
fi

command=(
  gcloud
  run
  jobs
  execute "${JOB_NAME}"
  --project "${PROJECT_ID}"
  --region "${REGION}"
)

if [[ -n "${GCLOUD_ENDPOINT_MODE:-}" ]]; then
  command+=(--endpoint-mode "${GCLOUD_ENDPOINT_MODE}")
fi

command+=(
  --args "$(IFS=,; echo "${job_args[*]}")"
  --update-env-vars "$(IFS=,; echo "${env_vars[*]}")"
)

if [[ "${incident_wait}" == "true" ]]; then
  command+=(--wait)
else
  command+=(--async)
fi

"${command[@]}"
