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
  IMAGE
  SERVICE_ACCOUNT
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

review_backend="${REVIEW_BACKEND:-gcs}"
review_type="${REVIEW_TYPE:-monthly}"
review_max_books="${REVIEW_MAX_BOOKS:-10}"
review_max_events="${REVIEW_MAX_EVENTS:-15}"
notify_lang="${NOTIFY_LANG:-en}"
review_send_telegram="${REVIEW_SEND_TELEGRAM:-true}"
python_command="${PYTHON_COMMAND:-python}"
review_script_path="${REVIEW_SCRIPT_PATH:-scripts/print_operator_review_pack.py}"

if [[ "${review_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when REVIEW_BACKEND=gcs" >&2
  exit 1
fi

if [[ "${review_type}" == "incident" ]]; then
  if [[ -n "${REVIEW_START_DATE:-}" && -z "${REVIEW_END_DATE:-}" ]]; then
    echo "REVIEW_END_DATE is required when REVIEW_START_DATE is set" >&2
    exit 1
  fi
  if [[ -z "${REVIEW_START_DATE:-}" && -n "${REVIEW_END_DATE:-}" ]]; then
    echo "REVIEW_START_DATE is required when REVIEW_END_DATE is set" >&2
    exit 1
  fi
fi

env_vars=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "NOTIFY_LANG=${notify_lang}"
)

if [[ -n "${GLOBAL_TELEGRAM_CHAT_ID:-}" ]]; then
  env_vars+=("GLOBAL_TELEGRAM_CHAT_ID=${GLOBAL_TELEGRAM_CHAT_ID}")
fi

job_args=(
  "${review_script_path}"
  "--backend" "${review_backend}"
  "--review-type" "${review_type}"
  "--max-books" "${review_max_books}"
  "--max-events" "${review_max_events}"
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

if [[ -n "${REVIEW_STRATEGY_PROFILE:-}" ]]; then
  job_args+=("--strategy-profile" "${REVIEW_STRATEGY_PROFILE}")
fi
if [[ -n "${REVIEW_PAPER_ACCOUNT_GROUP:-}" ]]; then
  job_args+=("--paper-account-group" "${REVIEW_PAPER_ACCOUNT_GROUP}")
fi

if [[ -n "${REVIEW_START_DATE:-}" && -n "${REVIEW_END_DATE:-}" ]]; then
  job_args+=("--start-date" "${REVIEW_START_DATE}" "--end-date" "${REVIEW_END_DATE}")
elif [[ -n "${REVIEW_AS_OF:-}" ]]; then
  job_args+=("--as-of" "${REVIEW_AS_OF}")
fi

if [[ "${review_send_telegram}" == "true" ]]; then
  job_args+=("--send-telegram")
fi

command=(
  gcloud
  run
  jobs
)

if gcloud run jobs describe "${JOB_NAME}" --project "${PROJECT_ID}" --region "${REGION}" >/dev/null 2>&1; then
  command+=(update "${JOB_NAME}")
else
  command+=(create "${JOB_NAME}")
fi

command+=(
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --image "${IMAGE}"
  --service-account "${SERVICE_ACCOUNT}"
  --tasks 1
  --max-retries 1
  --command "${python_command}"
  --args "$(IFS=,; echo "${job_args[*]}")"
  --set-env-vars "$(IFS=,; echo "${env_vars[*]}")"
)

if [[ "${review_send_telegram}" == "true" && -n "${TELEGRAM_TOKEN_SECRET_NAME:-}" ]]; then
  command+=(--set-secrets "TELEGRAM_TOKEN=${TELEGRAM_TOKEN_SECRET_NAME}:latest")
fi

"${command[@]}"
