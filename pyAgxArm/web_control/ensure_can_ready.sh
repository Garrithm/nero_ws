#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/nero-can.env"
ACTIVATE_SCRIPT="${REPO_ROOT}/pyAgxArm/scripts/linux/can_activate.sh"

if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
fi

CAN_PORT="${CAN_PORT:-can1}"
BITRATE="${BITRATE:-1000000}"
USB_ADDRESS="${USB_ADDRESS:-}"
RETRY_INTERVAL="${RETRY_INTERVAL:-2}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-90}"

deadline=$((SECONDS + MAX_WAIT_SECONDS))
attempt=1

is_can_up() {
    ip link show "${CAN_PORT}" 2>/dev/null | head -n 1 | grep -q "UP"
}

while (( SECONDS < deadline )); do
    echo "[ensure_can_ready] attempt ${attempt}: activating ${CAN_PORT}"
    if [[ -n "${USB_ADDRESS}" ]]; then
        /bin/bash "${ACTIVATE_SCRIPT}" "${CAN_PORT}" "${BITRATE}" "${USB_ADDRESS}" || true
    else
        /bin/bash "${ACTIVATE_SCRIPT}" "${CAN_PORT}" "${BITRATE}" || true
    fi

    if is_can_up; then
        echo "[ensure_can_ready] ${CAN_PORT} is UP"
        exit 0
    fi

    echo "[ensure_can_ready] ${CAN_PORT} not ready yet, retrying in ${RETRY_INTERVAL}s"
    sleep "${RETRY_INTERVAL}"
    attempt=$((attempt + 1))
done

echo "[ensure_can_ready] timed out waiting for ${CAN_PORT} to become UP"
ip link show "${CAN_PORT}" || true
exit 1
