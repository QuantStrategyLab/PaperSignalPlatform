#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/cloud_run_incident_review_actions_job.env.example}"

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
  REVIEW_JOB_NAME
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

action_backend="${ACTION_BACKEND:-gcs}"
action_period="${ACTION_PERIOD:-daily}"
action_region_code="${ACTION_REGION_CODE:-sg}"
action_max_triggers="${ACTION_MAX_TRIGGERS:-15}"
action_min_severity="${ACTION_MIN_SEVERITY:-critical}"
action_max_reviews="${ACTION_MAX_REVIEWS:-2}"
action_execute="${ACTION_EXECUTE:-false}"
review_backend="${REVIEW_BACKEND:-${action_backend}}"
review_send_telegram="${REVIEW_SEND_TELEGRAM:-true}"
notify_lang="${NOTIFY_LANG:-en}"
python_command="${PYTHON_COMMAND:-python}"
action_script_path="${ACTION_SCRIPT_PATH:-scripts/execute_incident_review_actions.py}"

if [[ "${action_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when ACTION_BACKEND=gcs" >&2
  exit 1
fi
if [[ "${review_backend}" == "gcs" && -z "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  echo "PAPER_SIGNAL_GCS_BUCKET is required when REVIEW_BACKEND=gcs" >&2
  exit 1
fi
if [[ "${action_period}" == "custom" ]]; then
  if [[ -z "${ACTION_START_DATE:-}" || -z "${ACTION_END_DATE:-}" ]]; then
    echo "ACTION_START_DATE and ACTION_END_DATE are required when ACTION_PERIOD=custom" >&2
    exit 1
  fi
fi

env_vars=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "NOTIFY_LANG=${notify_lang}"
)

job_args=(
  "${action_script_path}"
  "--backend" "${action_backend}"
  "--project-id" "${PROJECT_ID}"
  "--region" "${REGION}"
  "--review-job-name" "${REVIEW_JOB_NAME}"
  "--review-backend" "${review_backend}"
  "--review-script-path" "${REVIEW_SCRIPT_PATH:-scripts/print_operator_review_pack.py}"
  "--period" "${action_period}"
  "--region-code" "${action_region_code}"
  "--max-triggers" "${action_max_triggers}"
  "--min-severity" "${action_min_severity}"
  "--max-reviews" "${action_max_reviews}"
  "--review-max-books" "${REVIEW_MAX_BOOKS:-10}"
  "--review-max-events" "${REVIEW_MAX_EVENTS:-20}"
  "--lang" "${notify_lang}"
)

if [[ "${action_backend}" == "gcs" ]]; then
  job_args+=("--bucket" "${PAPER_SIGNAL_GCS_BUCKET}")
  if [[ -n "${ACTION_GCS_PREFIX:-}" ]]; then
    job_args+=("--prefix" "${ACTION_GCS_PREFIX}")
  fi
else
  action_artifact_dir="${ACTION_ARTIFACT_DIR:-.paper_signal/artifacts}"
  job_args+=("--artifact-dir" "${action_artifact_dir}")
fi

if [[ -n "${ACTION_STRATEGY_PROFILE:-}" ]]; then
  job_args+=("--strategy-profile" "${ACTION_STRATEGY_PROFILE}")
fi
if [[ -n "${ACTION_PAPER_ACCOUNT_GROUP:-}" ]]; then
  job_args+=("--paper-account-group" "${ACTION_PAPER_ACCOUNT_GROUP}")
fi

if [[ "${action_period}" == "custom" ]]; then
  job_args+=("--start-date" "${ACTION_START_DATE}" "--end-date" "${ACTION_END_DATE}")
elif [[ -n "${ACTION_AS_OF:-}" ]]; then
  job_args+=("--as-of" "${ACTION_AS_OF}")
fi

if [[ "${review_backend}" == "gcs" ]]; then
  job_args+=("--review-bucket" "${PAPER_SIGNAL_GCS_BUCKET}")
  if [[ -n "${REVIEW_GCS_PREFIX:-}" ]]; then
    job_args+=("--review-prefix" "${REVIEW_GCS_PREFIX}")
  fi
else
  job_args+=("--review-artifact-dir" "${REVIEW_ARTIFACT_DIR:-.paper_signal/artifacts}")
fi

if [[ "${review_send_telegram}" != "true" ]]; then
  job_args+=("--no-review-send-telegram")
fi
if [[ -n "${REVIEW_TELEGRAM_CHAT_ID:-}" ]]; then
  job_args+=("--review-telegram-chat-id" "${REVIEW_TELEGRAM_CHAT_ID}")
fi
if [[ "${action_execute}" == "true" ]]; then
  job_args+=("--execute")
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

"${command[@]}"
