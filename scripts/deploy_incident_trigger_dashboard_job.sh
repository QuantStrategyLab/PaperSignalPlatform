#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/cloud_run_incident_dashboard_job.env.example}"

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

dashboard_backend="${DASHBOARD_BACKEND:-gcs}"
dashboard_period="${DASHBOARD_PERIOD:-daily}"
dashboard_max_triggers="${DASHBOARD_MAX_TRIGGERS:-15}"
dashboard_region_code="${DASHBOARD_REGION_CODE:-sg}"
notify_lang="${NOTIFY_LANG:-en}"
dashboard_send_telegram="${DASHBOARD_SEND_TELEGRAM:-true}"
python_command="${PYTHON_COMMAND:-python}"
dashboard_script_path="${DASHBOARD_SCRIPT_PATH:-scripts/print_incident_trigger_dashboard.py}"

if [[ "${dashboard_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when DASHBOARD_BACKEND=gcs" >&2
  exit 1
fi

if [[ "${dashboard_period}" == "custom" ]]; then
  if [[ -z "${DASHBOARD_START_DATE:-}" || -z "${DASHBOARD_END_DATE:-}" ]]; then
    echo "DASHBOARD_START_DATE and DASHBOARD_END_DATE are required when DASHBOARD_PERIOD=custom" >&2
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
  "${dashboard_script_path}"
  "--backend" "${dashboard_backend}"
  "--period" "${dashboard_period}"
  "--region-code" "${dashboard_region_code}"
  "--max-triggers" "${dashboard_max_triggers}"
  "--lang" "${notify_lang}"
)

if [[ "${dashboard_backend}" == "gcs" ]]; then
  job_args+=("--bucket" "${PAPER_SIGNAL_GCS_BUCKET}" "--project-id" "${PROJECT_ID}")
  if [[ -n "${DASHBOARD_GCS_PREFIX:-}" ]]; then
    job_args+=("--prefix" "${DASHBOARD_GCS_PREFIX}")
  fi
else
  dashboard_artifact_dir="${DASHBOARD_ARTIFACT_DIR:-.paper_signal/artifacts}"
  job_args+=("--artifact-dir" "${dashboard_artifact_dir}")
fi

if [[ -n "${DASHBOARD_STRATEGY_PROFILE:-}" ]]; then
  job_args+=("--strategy-profile" "${DASHBOARD_STRATEGY_PROFILE}")
fi
if [[ -n "${DASHBOARD_PAPER_ACCOUNT_GROUP:-}" ]]; then
  job_args+=("--paper-account-group" "${DASHBOARD_PAPER_ACCOUNT_GROUP}")
fi

if [[ "${dashboard_period}" == "custom" ]]; then
  job_args+=("--start-date" "${DASHBOARD_START_DATE}" "--end-date" "${DASHBOARD_END_DATE}")
elif [[ -n "${DASHBOARD_AS_OF:-}" ]]; then
  job_args+=("--as-of" "${DASHBOARD_AS_OF}")
fi

if [[ -n "${DASHBOARD_PERIOD_LABEL:-}" ]]; then
  job_args+=("--period-label" "${DASHBOARD_PERIOD_LABEL}")
fi

if [[ "${dashboard_send_telegram}" == "true" ]]; then
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

if [[ "${dashboard_send_telegram}" == "true" && -n "${TELEGRAM_TOKEN_SECRET_NAME:-}" ]]; then
  command+=(--set-secrets "TELEGRAM_TOKEN=${TELEGRAM_TOKEN_SECRET_NAME}:latest")
fi

"${command[@]}"
