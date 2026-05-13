#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# setup_vm.sh — IoT Provisioning Demo VM Initialization
# =============================================================================
# Creates an Ubuntu LXD VM with Intel AX201 Bluetooth (USB passthrough)
# and WiFi passthrough, then installs required packages inside the VM.
#
# Usage:
#   sudo ./setup_vm.sh            # Full setup
#   sudo ./setup_vm.sh --check    # Dry-run: validate host prereqs only
# =============================================================================

VM_NAME="iot-device-vm"
VM_IMAGE="ubuntu:24.04"
VM_CPU="2"
VM_MEM="2GiB"
VM_DISK="4GiB"
STORAGE_POOL="data-zpool"
LXD_PROJECT="hackathon"
BT_USB_VENDOR="8087"
BT_USB_PRODUCT="0026"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[X]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    log "Running pre-flight checks..."

    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (sudo)."
    fi

    if ! command -v lxc &>/dev/null; then
        err "lxc not found. Install via: sudo snap install lxd && lxd init"
    fi

    # Verify LXD is initialized
    if ! lxc info &>/dev/null; then
        err "LXD not initialized. Run: lxd init"
    fi

    # Verify storage pool exists
    if ! lxc storage info "${STORAGE_POOL}" &>/dev/null; then
        err "Storage pool '${STORAGE_POOL}' not found. Create it with: lxc storage create ${STORAGE_POOL} zfs"
    fi
    log "Storage pool '${STORAGE_POOL}' found."

    # Ensure LXD project exists
    if ! lxc project list --format csv | cut -d, -f1 | grep -qx "${LXD_PROJECT}"; then
        log "Creating LXD project '${LXD_PROJECT}'..."
        lxc project create "${LXD_PROJECT}"
        lxc project switch "${LXD_PROJECT}"
    fi

    # Check Bluetooth USB controller (Intel AX201)
    if ! lsusb -d "${BT_USB_VENDOR}:" 2>/dev/null | grep -q . ; then
        err "Intel AX201 Bluetooth USB device (${BT_USB_VENDOR}:${BT_USB_PRODUCT}) not found via lsusb."
    fi
    log "Bluetooth USB controller found: $(lsusb -d "${BT_USB_VENDOR}:" | head -1)"

    # Detect primary WiFi interface
    WIFI_IFACE=$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')
    if [[ -z "${WIFI_IFACE}" ]]; then
        err "No WiFi interface found via 'iw dev'."
    fi
    log "WiFi interface detected: ${WIFI_IFACE}"

    # Kernel modules check (non-fatal warnings)
    for mod in btusb bluetooth mac80211 cfg80211; do
        if ! lsmod | grep -q "^${mod}"; then
            warn "Kernel module '${mod}' not loaded. Attempting modprobe..."
            modprobe "${mod}" 2>/dev/null || warn "Could not load ${mod}. Passthrough may fail."
        fi
    done

    log "Pre-flight checks passed."
}

# ---------------------------------------------------------------------------
# Create VM if it doesn't exist
# ---------------------------------------------------------------------------
create_vm() {
    if lxc info --project "${LXD_PROJECT}" "${VM_NAME}" &>/dev/null; then
        warn "VM '${VM_NAME}' already exists in project '${LXD_PROJECT}'. Skipping creation."
        return 0
    fi

    log "Launching LXD VM '${VM_NAME}' with ${VM_IMAGE} on pool '${STORAGE_POOL}'..."
    lxc init --project "${LXD_PROJECT}" "${VM_IMAGE}" "${VM_NAME}" --vm \
        --storage "${STORAGE_POOL}" \
        --config limits.cpu="${VM_CPU}" \
        --config limits.memory="${VM_MEM}" \
        --verbose 2>&1 || {
        err "Failed to create VM. Cleaning up orphaned ZFS volumes..."
        zfs destroy -r "data-zpool/virtual-machines/${LXD_PROJECT}_${VM_NAME}" 2>/dev/null || true
        zfs destroy -r "data-zpool/virtual-machines/${LXD_PROJECT}_${VM_NAME}.block" 2>/dev/null || true
        exit 1
    }

    lxc config --project "${LXD_PROJECT}" device override "${VM_NAME}" root size="${VM_DISK}"

    log "VM '${VM_NAME}' created (not yet started)."
}

# ---------------------------------------------------------------------------
# Attach host hardware
# ---------------------------------------------------------------------------
attach_devices() {
    local wifi_iface="${WIFI_IFACE}"

    # --- Bluetooth (USB passthrough) ---
    if lxc config --project "${LXD_PROJECT}" device get "${VM_NAME}" bluetooth-usb name &>/dev/null; then
        warn "Device 'bluetooth-usb' already attached to VM. Skipping Bluetooth attach."
    else
        log "Passing through Bluetooth USB device (${BT_USB_VENDOR}:${BT_USB_PRODUCT})..."
        lxc config --project "${LXD_PROJECT}" device add "${VM_NAME}" bluetooth-usb usb \
            vendorid="${BT_USB_VENDOR}" \
            productid="${BT_USB_PRODUCT}"
        log "Bluetooth USB passthrough configured."
    fi

    # --- WiFi ---
    if lxc config --project "${LXD_PROJECT}" device get "${VM_NAME}" wifi-nic name &>/dev/null; then
        warn "Device 'wifi-nic' already attached to VM. Skipping WiFi attach."
    else
        log "Passing through WiFi interface: ${wifi_iface}..."
        lxc config --project "${LXD_PROJECT}" device add "${VM_NAME}" wifi-nic nic \
            nictype=physical \
            parent="${wifi_iface}"
        log "WiFi passthrough configured."
    fi
}

# ---------------------------------------------------------------------------
# Start VM and install packages
# ---------------------------------------------------------------------------
install_packages() {
    case "$(lxc info --project "${LXD_PROJECT}" "${VM_NAME}" 2>/dev/null | awk '/Status:/{print $2}')" in
        Running)
            log "VM is already running."
            ;;
        Stopped|Created)
            log "Starting VM..."
            lxc start --project "${LXD_PROJECT}" "${VM_NAME}"
            log "Waiting for cloud-init and networking (30s)..."
            sleep 30
            ;;
        *)
            err "Unknown VM state."
            ;;
    esac

    log "Installing packages inside VM..."
    lxc exec --project "${LXD_PROJECT}" "${VM_NAME}" -- bash -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq python3 python3-pip bluez network-manager rfkill iw
    '

    # Ensure nmcli and bluetoothctl are available
    lxc exec --project "${LXD_PROJECT}" "${VM_NAME}" -- bash -c '
        command -v nmcli &>/dev/null && echo "  nmcli: OK" || echo "  nmcli: MISSING"
        command -v bluetoothctl &>/dev/null && echo "  bluetoothctl: OK" || echo "  bluetoothctl: MISSING"
        python3 --version && echo "  python3: OK"
    '

    log "Package installation complete."
}

# ---------------------------------------------------------------------------
# Post-setup info
# ---------------------------------------------------------------------------
post_info() {
    local vm_ip
    vm_ip=$(lxc info --project "${LXD_PROJECT}" "${VM_NAME}" 2>/dev/null | awk '/eth0.*inet /{print $3}' || echo "N/A")

    echo ""
    echo "========================================="
    echo "  VM Setup Complete: ${VM_NAME}"
    echo "========================================="
    echo "  IP Address:   ${vm_ip}"
    echo "  Bluetooth:    USB ${BT_USB_VENDOR}:${BT_USB_PRODUCT} (passthrough)"
    echo "  WiFi:         ${WIFI_IFACE} (exclusive to VM)"
    echo "  Storage Pool: ${STORAGE_POOL}"
    echo "  LXD Project:  ${LXD_PROJECT}"
    echo ""
    echo "  Access VM:    lxc shell --project ${LXD_PROJECT} ${VM_NAME}"
    echo "  Stop VM:      lxc stop --project ${LXD_PROJECT} ${VM_NAME}"
    echo "  Delete VM:    lxc delete --project ${LXD_PROJECT} ${VM_NAME} --force"
    echo ""
    echo "  NOTE: Host WiFi is now controlled by the VM."
    echo "        The host has lost connectivity on ${WIFI_IFACE}."
    echo "========================================="
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "========================================="
    echo "  IoT Provisioning Demo — VM Setup"
    echo "========================================="
    echo ""

    if [[ "${1:-}" == "--check" ]]; then
        preflight
        log "All host prerequisites met. Ready to run: sudo ./setup_vm.sh"
        return 0
    fi

    preflight
    create_vm
    attach_devices
    install_packages
    post_info
}

WIFI_IFACE=""
main "${@}"
