# IoT Device Enrollment

Runs a Rich TUI + Flask server (single process) that simulates an IoT device
going through an enrollment/provisioning flow.

## Prerequisites

- Python **3.11+** with `python3-venv` (`apt install python3-full` on Ubuntu)

## Quick Start

```bash
cd device/

# 1. Create virtual environment
python3 -m venv .venv

# 2. Activate it
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the device
python src/main.py
```

> The Server component must be running on **localhost:5000** before triggering
> enrollment (see `../server/`).

## One-liner (skip activation)

```bash
python3 -m venv device/.venv && \
./device/.venv/bin/pip install -r device/requirements.txt && \
./device/.venv/bin/python device/src/main.py
```

## What it does

| Port  | Endpoint        | Purpose                          |
|-------|-----------------|----------------------------------|
| 5001  | `POST /start`   | Trigger enrollment (App → Device) |
| 5001  | `POST /shutdown`| Gracefully stop the Device       |

The Device polls the Server (`localhost:5000`) at:

The Device polls the Server (`localhost:5000`) at:

| Endpoint                                     | Purpose                  |
|----------------------------------------------|--------------------------|
| `GET  /v1/device/token?id=IOT-DEV-0001`     | Request enrollment token |
| `GET  /v1/device/status/IOT-DEV-0001`       | Poll approval status     |

## TUI Layout

- **Left panel:** device ID, current state, server URL, instructions
- **Right panel:** QR code (during provisioning) — scannable by phone camera
- **Footer:** last 3 log lines

## States

1. **IDLE** — waiting for `POST /start`
2. **AWAITING_TOKEN** — requesting token from server
3. **PROVISIONING** — QR code displayed, polling for approval
4. **ONLINE** — provisioned, `provisioned.json` saved

## Error Recovery

- **Server offline:** 5-second countdown retry displayed in TUI
- **Token expiry:** auto-refreshes token and QR at 4.5 minutes

## Exiting

| Action            | Effect                              |
|-------------------|-------------------------------------|
| Press **`q`**     | Quit the TUI and stop the device    |
| **`Ctrl+C`**      | Interrupt and shut down             |
| `POST /shutdown`  | Graceful shutdown via API           |

The footer always shows the available key bindings.