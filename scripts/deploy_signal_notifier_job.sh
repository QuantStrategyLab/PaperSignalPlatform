#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-deploy/signal_notifier_job.env.example}"

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
  SERVICE_ACCOUNT
  SCRIPT_PATH
  STATE_URI
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

lookback_days="${LOOKBACK_DAYS:-900}"
notify_lang="${NOTIFY_LANG:-zh}"
snapshot_uri="${SNAPSHOT_URI:-}"
stdout_only="${STDOUT_ONLY:-true}"
skip_unchanged="${SKIP_UNCHANGED:-true}"
force_send="${FORCE_SEND:-false}"
script_path="${SCRIPT_PATH}"
if [[ "${script_path}" != /* ]]; then
  if [[ -n "${IMAGE:-}" ]]; then
    script_path="/app/${script_path}"
  else
    script_path="/workspace/${script_path}"
  fi
fi

job_args=(
  "${script_path}"
  "--lookback-days=${lookback_days}"
  "--lang=${notify_lang}"
  "--state-file=${STATE_URI}"
)

if [[ -n "${snapshot_uri}" ]]; then
  job_args+=("--json-out=${snapshot_uri}")
fi
if [[ "${stdout_only}" == "true" ]]; then
  job_args+=("--stdout-only")
fi
if [[ "${skip_unchanged}" == "true" ]]; then
  job_args+=("--skip-unchanged")
fi
if [[ "${force_send}" == "true" ]]; then
  job_args+=("--force-send")
fi

env_vars=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "SIGNAL_NOTIFY_LANG=${notify_lang}"
  "SIGNAL_NOTIFY_STATE_PATH=${STATE_URI}"
)

if [[ -n "${snapshot_uri}" ]]; then
  env_vars+=("SIGNAL_NOTIFY_OUTPUT_PATH=${snapshot_uri}")
fi
if [[ -n "${SIGNAL_NOTIFY_TELEGRAM_CHAT_ID:-}" ]]; then
  env_vars+=("SIGNAL_NOTIFY_TELEGRAM_CHAT_ID=${SIGNAL_NOTIFY_TELEGRAM_CHAT_ID}")
fi
if [[ -n "${SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD:-}" ]]; then
  env_vars+=("SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD=${SIGNAL_NOTIFY_REFERENCE_CAPITAL_USD}")
fi
if [[ -n "${SIGNAL_NOTIFY_GROUPS:-}" ]]; then
  env_vars+=("SIGNAL_NOTIFY_GROUPS=${SIGNAL_NOTIFY_GROUPS}")
fi
if [[ -n "${MAGS7_UNIVERSE:-}" ]]; then
  env_vars+=("MAGS7_UNIVERSE=${MAGS7_UNIVERSE}")
fi

command=(
  gcloud
  run
  jobs
  deploy
  "${JOB_NAME}"
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --service-account "${SERVICE_ACCOUNT}"
  --tasks 1
  --parallelism 1
  --max-retries 1
  --task-timeout 15m
  --command python3
  --args "$(IFS=,; echo "${job_args[*]}")"
  --set-env-vars "$(IFS=,; echo "${env_vars[*]}")"
)

if [[ -n "${IMAGE:-}" ]]; then
  command+=(--image "${IMAGE}")
else
  if [[ -z "${SOURCE_DIR:-}" ]]; then
    echo "missing required variable: SOURCE_DIR (or set IMAGE)" >&2
    exit 1
  fi
  command+=(--source "${SOURCE_DIR}")
fi

if [[ -n "${TELEGRAM_TOKEN_SECRET_NAME:-}" ]]; then
  command+=(--set-secrets "SIGNAL_NOTIFY_TELEGRAM_TOKEN=${TELEGRAM_TOKEN_SECRET_NAME}:latest")
fi

"${command[@]}"
