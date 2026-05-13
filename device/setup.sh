#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# setup.sh — Install Device Application Dependencies
# =============================================================================
# Run this inside the LXD VM (iot-device-vm) or on the host for testing.
#
# Prerequisites:
#   - Python 3.11+
#   - bluetooth stack (bluez + bluez-hcidump)
#   - network-manager (nmcli)
#
# Usage:
#   ./setup.sh             # install deps only
#   ./setup.sh --full      # install deps + system packages
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

# ---- system packages ----
install_system_deps() {
    log "Installing system packages..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            python3 python3-pip python3-venv \
            bluez bluez-hcidump \
            network-manager \
            rfkill iw
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip bluez NetworkManager rfkill iw
    else
        warn "Unsupported package manager. Install manually: python3, bluez, network-manager"
    fi
    log "System packages installed."
}

# ---- Python dependencies ----
install_python_deps() {
    log "Installing Python dependencies from ${REQUIREMENTS}..."

    if [ ! -f "${REQUIREMENTS}" ]; then
        warn "${REQUIREMENTS} not found — creating default..."
        cat >"${REQUIREMENTS}" <<'EOF'
rich>=13.0.0
segno>=1.6.0
qrcode>=7.4.0
requests>=2.28.0
bleak>=0.21.0
dbus-python>=1.3.0
PyGObject>=3.42.0
EOF
    fi

    pip3 install --break-system-packages -r "${REQUIREMENTS}" 2>/dev/null || \
    pip3 install -r "${REQUIREMENTS}"

    log "Python dependencies installed."
}

# ---- verify ----
verify() {
    log "Verifying installation..."
    echo ""

    python3 -c "import bleak; print('  bleak:', bleak.__version__)" 2>/dev/null || warn "bleak  MISSING"
    python3 -c "import segno; print('  segno:', segno.__version__)" 2>/dev/null || warn "segno  MISSING"
    python3 -c "import rich;  print('  rich:  OK')" 2>/dev/null || warn "rich   MISSING"
    python3 -c "import requests; print('  requests:', requests.__version__)" 2>/dev/null || warn "requests MISSING"

    command -v nmcli &>/dev/null && echo "  nmcli: OK" || warn "nmcli  MISSING (WiFi will use mock)"
    command -v bluetoothctl &>/dev/null && echo "  bluetoothctl: OK" || warn "bluetoothctl  MISSING (BLE will use mock)"

    echo ""
    log "Verification complete."
}

# ---- main ----
main() {
    echo ""
    echo "========================================="
    echo "  IoT Device — Dependency Setup"
    echo "========================================="
    echo ""

    case "${1:-}" in
        --full)
            install_system_deps
            install_python_deps
            ;;
        *)
            install_python_deps
            ;;
    esac

    verify

    echo ""
    echo "Run: python3 src/main.py"
    echo "========================================="
}

main "${@}"