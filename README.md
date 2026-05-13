# IoT Provisioning Demo (Enrollment-Only Flow)

A simplified demonstration of IoT device enrollment. All components run on localhost with direct REST communication — no BLE, no WiFi passthrough, no LXD VM.

## Architecture

```
┌──────────┐  POST /start      ┌──────────┐
│   APP    │ ─────────────────▶│  DEVICE   │
│ (browser)│                   │ :5001     │
│ HTTPS    │                   │ Flask TUI │
│ :9443    │                   │           │
└────┬─────┘                   └────┬─────┘
     │                              │
     │ POST /v1/app/approve         │ GET /v1/device/token?id=X
     │                              │ GET /v1/device/status/X
     │              ┌──────────┐    │
     │      /server │  SERVER  │◀───┘
     └─────────────▶│ :5000    │
                    │ FastAPI  │
                    └──────────┘
```

The **App** (`app/serve.py`) runs an HTTPS server on port **9443** that:
- Serves `app/index.html`
- Proxies `/server/*` → `http://localhost:5000/*` (Server API)
- Proxies `/device/*` → `http://localhost:5001/*` (Device API)

This avoids CORS issues and allows mobile browser camera access (requires HTTPS).

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