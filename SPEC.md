# SPEC.md: IoT Provisioning Demo (Enrollment-Only Flow)

## 1. Project Overview
A simplified demonstration of an IoT device enrollment flow. All components run on localhost with direct REST communication — no BLE, no WiFi passthrough, no LXD VM. The App triggers enrollment on the Device, which obtains a token from the Server, displays a QR code, and waits for App-based approval.

## 2. System Components & Environment
| Component | Environment | Tech Stack |
| :--- | :--- | :--- |
| **SERVER** | localhost:5000 | Python (FastAPI) |
| **DEVICE** | localhost:5001 | Python (Flask + Rich TUI) |
| **APP** | Browser (localhost) | Single HTML file + JS (html5-qrcode CDN) |

### Connectivity:
All three components run on the same machine with full network visibility to localhost.

## 3. The Provisioning State Machine
The DEVICE must implement and report the following states via the Rich TUI:

| # | State | Description |
|---|-------|-------------|
| 1 | **IDLE** | TUI running, waiting for App to send `POST /start` |
| 2 | **AWAITING_TOKEN** | App triggered; Device requesting token from Server |
| 3 | **PROVISIONING** | QR code displayed in terminal; polling Server for approval |
| 4 | **ONLINE** | Provisioning approved; `provisioned.json` saved; steady state |

## 4. Communication Protocols & Schemas

### A. Device REST API (App → Device, port 5001)
* **`POST /start`**
    * App calls this to trigger provisioning. No payload needed.

### B. Server API (REST, port 5000)
* **`GET /v1/device/token?id={device_id}`**
    * Device calls this. Server returns `{"token": "<6-digit numeric>"}` with 5-minute TTL.
* **`POST /v1/app/approve`**
    * App calls this. Payload: `{"token": "...", "device_id": "..."}`.
* **`GET /v1/device/status/{device_id}`**
    * Device polls this. Returns `{"approved": true/false}`.

## 5. Implementation Details

### Enrollment Flow
1. **App** → `POST /start` → **Device** triggers the flow.
2. **Device** → `GET /v1/device/token?id=IOT-DEV-0001` → **Server** returns token.
3. **Device** displays a QR Code containing the JSON string `{"token":"123456","device_id":"IOT-DEV-0001"}` in the Rich TUI.
4. **App** scans the terminal QR (via `html5-qrcode` camera JS library).
5. **App** → `POST /v1/app/approve` → **Server** approves the token.
6. **Device** polls `GET /v1/device/status/IOT-DEV-0001` → receives `approved: true`.
7. **Device** saves `provisioned.json` locally and transitions to **ONLINE**.

## 6. Folder Structure
```text
.
├── archive/
│   └── SPEC-v1.md            # Original BLE/WiFi spec (archived)
├── .agents/
├── device/
│   ├── src/main.py           # Rich TUI + Flask REST endpoint
│   └── requirements.txt      # rich, flask, qrcode, requests, pillow
├── server/
│   ├── main.py               # FastAPI app entry point
│   ├── store.py              # In-memory token store (dict + Lock)
│   └── requirements.txt      # fastapi, uvicorn
├── app/
│   └── index.html            # Browser client: trigger button + QR scanner
└── docs/                     # Technical documentation

7. Error Handling Requirements
Server Offline: Device TUI must show a "Retry in Ns" countdown if the Server is unreachable.

Token Timeout: If the QR is not scanned within 5 minutes, the Device must auto-refresh the token and update the QR code.

Approval Denied: If the Server returns any error on approve, the App must display it.

8. Decisions
Device ID for the demo is statically set to "IOT-DEV-0001". The App/server_url defaults to http://localhost:5000. The Device device_url defaults to http://localhost:5001.