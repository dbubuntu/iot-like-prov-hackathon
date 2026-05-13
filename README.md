# IoT Provisioning Demo (Enrollment-Only Flow)

A demonstration of smart device out-of-box provisioning — the moment a new IoT-like device arrives, establishes trust, and gets onboarded. The initial scope focuses on the enrollment process: the device already has network connectivity and all components (device, server, and mobile app) share full visibility of each other. 

*Note: No Bluetooth pairing or WiFi setup is involved in this iteration. This will be part of future work.*

## Architecture

> Detailed Mermaid diagram: [docs/architecture-components.md](docs/architecture-components.md)

Three components interact to complete the enrollment:

```
                ┌──────────────────────┐
                │        SERVER        │
                │   Provisioning API   │
                │       :5000          │
                │                      │
                │  Issues tokens       │
                │  Validates approvals │
                └──┬──────────────┬───┘
                   │              │
      token/status │              │ approve
                   │              │
       ┌───────────▼──┐      ┌───┴──────────┐
       │    DEVICE    │      │     APP       │
       │  IoT Client  │◀─────│  Mobile UI    │
       │    :5001     │start │    :9443      │
       │              │      │               │
       │  Rich TUI    │      │  Scan QR      │
       │  QR display  │      │  Approve      │
       │  State mgmt  │      │               │
       └──────────────┘      └───────────────┘
```

### Components

**SERVER** — The provisioning authority. It issues short-lived enrollment tokens to devices, tracks approval state, and validates scan confirmations from the app. Acts as the trust anchor between device and app.

**DEVICE** — The IoT device being provisioned. It exposes a REST endpoint for the app to trigger enrollment, contacts the server to obtain a token, renders it as a QR code in a terminal-based TUI, and polls the server until approval is granted.

**APP** — The user's mobile companion. It runs in a browser, sends the start command to the device, scans the QR code using the phone's camera, and forwards the scanned token to the server for final approval.

The App (`app/serve.py`) proxies all traffic through an HTTPS server on port **9443**, mapping `/server/*` → `:5000` and `/device/*` → `:5001` to avoid CORS issues and enable mobile camera access.

## Workflow

> Detailed Mermaid diagram: [docs/architecture-workflow.md](docs/architecture-workflow.md)

When a user unboxes a new IoT device, they open the companion mobile app and tap **Start Provisioning**. This triggers the device to contact a central provisioning server and obtain a unique enrollment token. The device displays this token as a scannable QR code. The user points their phone at the QR — the app reads it and forwards the approval to the server. The server validates the match and confirms the device's identity. The device receives the confirmation, stores its credentials locally, and transitions to **ONLINE**. The entire process takes under a minute with zero manual configuration.

```
     APP (Browser)            DEVICE (Flask)          SERVER (FastAPI)
     :9443                    :5001                   :5000
        │                         │                       │
        │──①  POST /start────────▶│                       │
        │                         │──②  GET /token────────▶│
        │                         │◀─────────token─────────│
        │                         │                       │
        │                         │──③  GET /status───────▶│  (poll every 2s)
        │                         │◀──────{approved}───────│
        │                         │                       │
        │                      [QR shown]                │
        │◀──scan QR──────────────│                       │
        │                         │                       │
        │──────④  POST /approve──────────────────────────▶│
        │◀─────────{ok}───────────────────────────────────│
        │                         │──③  GET /status───────▶│
        │                         │◀────approved: true─────│
        │                         │                       │
        │                      [ONLINE]                  │
```

## Quick Start

### 1. Server (FastAPI — port 5000)

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 5000 --reload
```

### 2. Device (Flask + Rich TUI — port 5001)

```bash
cd device
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

### 3. App Proxy (HTTPS — port 9443)

```bash
cd app
python serve.py
```

The proxy auto-generates a self-signed certificate and prints the access URL:

```
App:            https://192.168.1.50:9443/
Server proxy:   /server/* → http://localhost:5000/*
Device proxy:   /device/* → http://localhost:5001/*
```

Open the URL on your phone (or any browser with a camera). Accept the self-signed certificate warning.

The App URL fields are pre-filled with:
- **Server URL**: `/server`
- **Device URL**: `/device`

These relative paths are proxied by `serve.py`.

## Demo Flow

1. Start **Server** (`:5000`) and **Device** (`:5001`) in separate terminals.
2. Start **App Proxy** (`serve.py` on `:9443`).
3. Open the HTTPS URL on your phone.
4. Accept the certificate warning.
5. Click **"Start Provisioning"**.
6. The Device TUI shows the QR code in the terminal.
7. Point your phone's camera at the terminal QR.
8. The App automatically scans and approves via the Server proxy `/server/v1/app/approve`.
9. The Device polls `/server/v1/device/status/X` until approved, then shows **ONLINE**.

### Manual Token Entry

If the camera can't scan the terminal QR, type the 6-digit token from the Device TUI into the **"Or enter token manually"** field and click **Submit Token**.

## Project Structure

```
.
├── SPEC.md                   # Source of Truth
├── README.md                 # This file
├── archive/SPEC-v1.md        # Original BLE/WiFi spec (archived)
├── server/                   # Provisioning Server (FastAPI)
│   ├── main.py               # Entry point
│   ├── store.py              # In-memory token store
│   └── requirements.txt
├── device/                   # IoT Device simulator (Flask + Rich)
│   ├── src/main.py           # TUI + REST endpoint
│   └── requirements.txt
├── app/                      # Browser client + HTTPS proxy
│   ├── index.html            # Web UI with QR scanner
│   └── serve.py              # HTTPS server + proxy
└── docs/                     # Technical documentation

8. Success Criteria
[✓] App triggers "Start Provisioning" — Device transitions through states.

[✓] Device QR code displayed in terminal and scannable by phone camera.

[✓] App sends approval to Server via proxy path /server/v1/app/approve.

[✓] Device polls until approved, saves provisioned.json, shows ONLINE.

[✓] All communication through HTTPS proxy — no CORS issues, mobile camera works.

## Original Implementation

The full BLE + WiFi hardware passthrough implementation is archived on the `original-hardware-flow` branch:

```bash
git checkout original-hardware-flow
```

## Troubleshooting

- **Port conflicts**: If port 5000, 5001, or 9443 is in use, kill the conflicting process.
- **Camera not working**: The browser must be on HTTPS or localhost. The proxy runs on HTTPS.
- **Certificate warning**: After starting `serve.py`, on your phone browser tap **Advanced → Proceed** or accept the risk.
- **Device TUI QR not scannable**: Ensure the terminal has high contrast (white background, black text) and the QR size is large enough.
- **Server/Device not reachable**: Check `serve.py` terminal for proxy logs (`→ PROXY SERVER/DEVICE`).
