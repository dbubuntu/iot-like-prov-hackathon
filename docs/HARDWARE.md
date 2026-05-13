# Hardware Requirements — IoT Provisioning Demo

This document describes the host system requirements for passing Bluetooth and WiFi hardware through to an LXD VM.

## Host Prerequisites

### Kernel Modules

The following kernel modules must be loaded on the **host**:

| Module | Purpose |
|--------|---------|
| `btusb` | Bluetooth USB driver (for `hci0`) |
| `bluetooth` | Core Bluetooth stack |
| `mac80211` | WiFi stack (required for physical NIC passthrough) |
| `cfg80211` | WiFi configuration layer |

Load them if not already active:

```bash
sudo modprobe btusb
sudo modprobe bluetooth
```

### Required Groups

The user running `lxc` must be a member of these groups for device passthrough:

| Group | Purpose |
|-------|---------|
| `lxd` | LXD management |
| `bluetooth` | Access to Bluetooth resources |

Verify membership:

```bash
groups $USER
# Output should include 'lxd' and 'bluetooth'
```

### Hardware State

- **Bluetooth**: The host Bluetooth adapter must be unblocked and powered on:
  ```bash
  rfkill unblock bluetooth
  bluetoothctl power on
  ```
- **WiFi**: The wireless interface must exist (`iw dev`).  
  *Note*: The VM takes exclusive control of the passed-through WiFi interface — the host will lose connectivity through it.

### LXD Configuration

- LXD should be installed via snap and initialized with VM support:
  ```bash
  sudo snap install lxd
  lxd init
  ```
- The `lxd` snap must have access to the `:bluetooth` interface for `/dev/hci0` passthrough. By default this should auto-connect; verify with:
  ```bash
  snap connections lxd | grep bluetooth
  ```

### Known Limitations

1. **WiFi access control**: `lxc config device add` with `nictype=physical` removes the interface from the host kernel's control and attaches it to the VM. The interface will not be usable on the host while the VM is running.
2. **USB Bluetooth passthrough**: The script passes the Intel AX201 Bluetooth via USB (`vendorid=8087 productid=0026`). The host's `bluetoothd` service will release the controller when the VM starts.
3. **VM restart**: If the VM is stopped and restarted, passed-through devices (`nic`, `usb`) are automatically re-attached. The `setup_vm.sh` script is idempotent and re-runnable.
