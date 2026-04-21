#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/cloud_run_summary_job.env.example}"

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

summary_backend="${SUMMARY_BACKEND:-gcs}"
summary_period="${SUMMARY_PERIOD:-daily}"
summary_max_books="${SUMMARY_MAX_BOOKS:-10}"
notify_lang="${NOTIFY_LANG:-en}"
summary_send_telegram="${SUMMARY_SEND_TELEGRAM:-true}"
python_command="${PYTHON_COMMAND:-python}"
summary_script_path="${SUMMARY_SCRIPT_PATH:-scripts/print_operator_summary.py}"

if [[ "${summary_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when SUMMARY_BACKEND=gcs" >&2
  exit 1
fi

if [[ "${summary_period}" == "custom" ]]; then
  if [[ -z "${SUMMARY_START_DATE:-}" || -z "${SUMMARY_END_DATE:-}" ]]; then
    echo "SUMMARY_START_DATE and SUMMARY_END_DATE are required when SUMMARY_PERIOD=custom" >&2
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
  "${summary_script_path}"
  "--backend" "${summary_backend}"
  "--period" "${summary_period}"
  "--max-books" "${summary_max_books}"
  "--lang" "${notify_lang}"
)

if [[ "${summary_backend}" == "gcs" ]]; then
  job_args+=("--bucket" "${PAPER_SIGNAL_GCS_BUCKET}" "--project-id" "${PROJECT_ID}")
  if [[ -n "${SUMMARY_GCS_PREFIX:-}" ]]; then
    job_args+=("--prefix" "${SUMMARY_GCS_PREFIX}")
  fi
else
  summary_artifact_dir="${SUMMARY_ARTIFACT_DIR:-.paper_signal/artifacts}"
  job_args+=("--artifact-dir" "${summary_artifact_dir}")
fi

if [[ -n "${SUMMARY_STRATEGY_PROFILE:-}" ]]; then
  job_args+=("--strategy-profile" "${SUMMARY_STRATEGY_PROFILE}")
fi
if [[ -n "${SUMMARY_PAPER_ACCOUNT_GROUP:-}" ]]; then
  job_args+=("--paper-account-group" "${SUMMARY_PAPER_ACCOUNT_GROUP}")
fi

if [[ "${summary_period}" == "custom" ]]; then
  job_args+=("--start-date" "${SUMMARY_START_DATE}" "--end-date" "${SUMMARY_END_DATE}")
elif [[ -n "${SUMMARY_AS_OF:-}" ]]; then
  job_args+=("--as-of" "${SUMMARY_AS_OF}")
fi

if [[ "${summary_send_telegram}" == "true" ]]; then
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

if [[ "${summary_send_telegram}" == "true" && -n "${TELEGRAM_TOKEN_SECRET_NAME:-}" ]]; then
  command+=(--set-secrets "TELEGRAM_TOKEN=${TELEGRAM_TOKEN_SECRET_NAME}:latest")
fi

"${command[@]}"
