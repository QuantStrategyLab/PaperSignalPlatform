#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/cloud_run_job.env.example}"

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
  STRATEGY_PROFILE
  PAPER_ACCOUNT_GROUP
  PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

state_store_backend="${PAPER_SIGNAL_STATE_STORE_BACKEND:-firestore}"
artifact_store_backend="${PAPER_SIGNAL_ARTIFACT_STORE_BACKEND:-gcs}"
firestore_collection="${PAPER_SIGNAL_FIRESTORE_COLLECTION:-paper_signal_states}"
market_data_provider="${PAPER_SIGNAL_MARKET_DATA_PROVIDER:-yfinance}"
history_lookback_days="${PAPER_SIGNAL_HISTORY_LOOKBACK_DAYS:-420}"
notify_lang="${NOTIFY_LANG:-en}"

env_vars=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "STRATEGY_PROFILE=${STRATEGY_PROFILE}"
  "PAPER_ACCOUNT_GROUP=${PAPER_ACCOUNT_GROUP}"
  "PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME=${PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME}"
  "PAPER_SIGNAL_STATE_STORE_BACKEND=${state_store_backend}"
  "PAPER_SIGNAL_FIRESTORE_COLLECTION=${firestore_collection}"
  "PAPER_SIGNAL_ARTIFACT_STORE_BACKEND=${artifact_store_backend}"
  "PAPER_SIGNAL_MARKET_DATA_PROVIDER=${market_data_provider}"
  "PAPER_SIGNAL_HISTORY_LOOKBACK_DAYS=${history_lookback_days}"
  "NOTIFY_LANG=${notify_lang}"
)

if [[ -n "${PAPER_SIGNAL_GCS_BUCKET:-}" ]]; then
  env_vars+=("PAPER_SIGNAL_GCS_BUCKET=${PAPER_SIGNAL_GCS_BUCKET}")
fi
if [[ -n "${GLOBAL_TELEGRAM_CHAT_ID:-}" ]]; then
  env_vars+=("GLOBAL_TELEGRAM_CHAT_ID=${GLOBAL_TELEGRAM_CHAT_ID}")
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
  --set-env-vars "$(IFS=,; echo "${env_vars[*]}")"
)

if [[ -n "${TELEGRAM_TOKEN_SECRET_NAME:-}" ]]; then
  command+=(--set-secrets "TELEGRAM_TOKEN=${TELEGRAM_TOKEN_SECRET_NAME}:latest")
fi

"${command[@]}"
