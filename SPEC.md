# SPEC.md: IoT Provisioning Demo (Mutual Trust Flow)

## 1. Project Overview
A technical demonstration of an "Out-of-Box Experience" (OOBE) for an IoT device. The project simulates a device with no initial network, which gains connectivity and identity through a mobile app and a central provisioning server.

## 2. System Components & Environment
| Component | Environment | Tech Stack |
| :--- | :--- | :--- |
| **DEVICE** | LXD Virtual Machine (Ubuntu) | Python 3.11+, BlueZ, nmcli, Rich (TUI) |
| **SERVER** | Localhost / Docker | Node.js (Fastify) or Python (FastAPI) |
| **APP** | Mobile Emulator / Physical | React Native or Flutter |

### Component Constraints:
* **Connectivity:** The DEVICE starts with its WiFi interface `down`. It only enables the Bluetooth (BLE) stack.
* **Hardware:** The LXD VM must have the host's Bluetooth controller (`hci0`) and WiFi card passed through.

## 3. The Provisioning State Machine
The DEVICE must implement and report the following states via the TUI:
1.  **IDLE:** BT listening, WiFi off.
2.  **PAIRING:** BT connection established with APP.
3.  **CONNECTING_WIFI:** SSID/PWD received; attempting network join.
4.  **AWAITING_TOKEN:** WiFi connected; requesting token from SERVER.
5.  **PROVISIONING:** QR Code displayed; waiting for App/Server approval.
6.  **ONLINE:** Provisioning successful; steady state.

## 4. Communication Protocols & Schemas

### A. BLE Interface (App → Device)
The Device exposes a GATT Service `0xFF01` with the following Characteristics:
* **Wifi_Config (Write):** JSON object: `{"ssid": "...", "password": "...", "server_url": "..."}`
* **Connection_Status (Read/Notify):** String: `IDLE`, `CONNECTING`, `CONNECTED`, `ERROR_AUTH`.
* **Device_Info (Read):** JSON object: `{"device_id": "UUID-1234", "mac": "..."}`

### B. Server API (REST)
* **`GET /v1/device/token?id={device_id}`**
    * *Device calls this.* Server returns a short-lived (5m) numeric or alphanumeric token.
* **`POST /v1/app/approve`**
    * *App calls this.* Payload: `{"token": "...", "device_id": "..."}`.
* **`GET /v1/device/status/{device_id}`**
    * *Device polls this (or uses WebSockets).* Returns `{"approved": true/false}`.

## 5. Implementation Details

### Phase 1: The "Handshake" (Out-of-Band)
1.  **App** scans for BLE devices named `IOT_DEMO_XXXX`.
2.  **App** connects and sends the **WiFi Credentials** AND the **Server URL**.
3.  **Device** uses `nmcli` to connect. Once it has an IP, it notifies the App via BLE.

### Phase 2: The "Trust Transfer" (QR Scan)
1.  **Device** reaches out to the **Server URL** it received in Phase 1.
2.  **Server** issues a Token.
3.  **Device** displays the Token as a **QR Code** in the TUI. 
    * *Note:* Use a high-contrast ANSI TUI library to ensure mobile cameras can focus on the terminal.
4.  **App** scans the QR and sends it to the **Server**.
5.  **Server** matches the Token to the `device_id`.
6.  **Device** receives an "Approved" status and saves a local `provisioned.json` flag.

## 6. Folder Structure
```text
.
├── .agents/               # Agent role definitions
├── infra/                 # LXD VM configuration and hardware scripts
│   └── setup_vm.sh        # Script to create VM and passthrough BT/WiFi
├── device/                # Device logic
│   ├── src/main.py        # Entry point / TUI
│   ├── ble_server.py      # BlueZ GATT implementation
│   └── wifi_manager.py    # Wrapper for nmcli
├── server/                # Provisioning Server logic
│   ├── routes/
│   └── store.js           # In-memory token management
├── app/                   # Mobile application
└── docs/                  # Sequence diagrams and API docs

7. Error Handling Requirements
Wrong WiFi PWD: Device must notify App via BLE characteristic Connection_Status = ERROR_AUTH.

Token Timeout: If the QR is not scanned within 5 mins, the Device must refresh the token and the QR code automatically.

Server Offline: Device TUI should show a "Retry" countdown if the Provisioning Server is unreachable.

8. Success Criteria
[ ] Device connects to a hidden/local WiFi network without manual CLI input.

[ ] Mobile App triggers a "Provisioning Successful" alert.

[ ] The final repository contains a README.md with instructions on how to bridge the host hardware to the LXD VM.
