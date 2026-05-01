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
  SOURCE_DIR
  DOCKERFILE_PATH
  IMAGE
  SCRIPT_PATH
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required variable: ${name}" >&2
    exit 1
  fi
done

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

cp "${SOURCE_DIR}/${DOCKERFILE_PATH}" "${BUILD_DIR}/Dockerfile"
cp "${SOURCE_DIR}/requirements.signal-notifier.txt" "${BUILD_DIR}/requirements.signal-notifier.txt"
cp -R "${SOURCE_DIR}/signal_notifier" "${BUILD_DIR}/signal_notifier"

script_dir="$(dirname "${SCRIPT_PATH}")"
mkdir -p "${BUILD_DIR}/${script_dir}"
cp "${SOURCE_DIR}/${SCRIPT_PATH}" "${BUILD_DIR}/${SCRIPT_PATH}"

if [[ -n "${EXTRA_COPY_PATHS:-}" ]]; then
  IFS=',' read -r -a extra_paths <<< "${EXTRA_COPY_PATHS}"
  for extra_path in "${extra_paths[@]}"; do
    extra_path="${extra_path#"${extra_path%%[![:space:]]*}"}"
    extra_path="${extra_path%"${extra_path##*[![:space:]]}"}"
    if [[ -z "${extra_path}" ]]; then
      continue
    fi
    mkdir -p "${BUILD_DIR}/$(dirname "${extra_path}")"
    cp -R "${SOURCE_DIR}/${extra_path}" "${BUILD_DIR}/${extra_path}"
  done
fi

gcloud builds submit "${BUILD_DIR}" \
  --project "${PROJECT_ID}" \
  --tag "${IMAGE}"
