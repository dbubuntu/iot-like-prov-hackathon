#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run.sh — IoT Device Provisioning Quick‑Start
# =============================================================================
# Installs Python dependencies then launches the device TUI.
#
# Usage:
#   ./run.sh                  # real BLE + real WiFi
#   ./run.sh --mock-ble       # mock BLE, real WiFi
#   ./run.sh --mock-all       # fully mocked (no hardware needed)
#   SERVER_URL=http://10.0.0.1:8080 ./run.sh   # explicit server URL
#
# Environment variables:
#   PROVISIONING_SERVER   full server URL   (e.g. http://10.0.0.1:8080)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- install deps ----
echo "==> Installing Python dependencies …"
pip3 install --break-system-packages -r "${SCRIPT_DIR}/requirements.txt" 2>/dev/null || \
    pip3 install -r "${SCRIPT_DIR}/requirements.txt"
echo ""

# ---- resolve args ----
PY_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --mock-all)  PY_ARGS+=(--mock-ble --mock-wifi) ;;
        --mock-ble)  PY_ARGS+=(--mock-ble) ;;
        --mock-wifi) PY_ARGS+=(--mock-wifi) ;;
        *)           PY_ARGS+=("$arg") ;;
    esac
done

# ---- start ----
echo "==> Launching device TUI …"
echo ""
exec python3 "${SCRIPT_DIR}/src/main.py" "${PY_ARGS[@]}"