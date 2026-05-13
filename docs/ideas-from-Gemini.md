This is a sophisticated IoT orchestration demo. Using **Zed** with **OpenRouter** (likely leveraging Claude 3.5 Sonnet or GPT-4o) provides a high-performance environment for this type of multi-component development.

Below is the technical specification, agent definitions, and architecture designed for an automated "Agentic Workflow."

---

## 1. Technical Specification: IoT Provisioning Demo

### System Architecture

The system utilizes a **three-way handshake** between a constrained device, a mobile controller, and a central authority.

### Component Requirements

* **DEVICE (Linux VM/LXD):** * **Runtime:** Python or Go (recommended for TUI and system-level networking).
* **Bluetooth Stack:** `BlueZ` over DBus.
* **WiFi Management:** `NetworkManager` (nmcli) or `wpa_supplicant`.
* **TUI:** `urwid` or `bubbletea` (Go) for terminal QR rendering.


* **SERVER (Backend):**
* **Stack:** Node.js (Fastify) or Python (FastAPI).
* **Features:** WebSocket or Long-polling for real-time Device-Server-App sync.


* **APP (Mobile):**
* **Framework:** Flutter or React Native (best for BLE/WiFi libraries).
* **Features:** QR Scanner, BLE Manager, REST Client.



---

## 2. Multi-Agent Definition & Skills

To develop this in Zed via OpenRouter, you should initialize your agents with these specific "Personas."

### Agent A: The System Architect & DevOps (Lead)

* **Skillset:** LXD/Linux internals, Networking (IP tables, BT/WiFi passthrough), GitHub Actions.
* **Task:** Setup the LXD environment, handle host-to-guest hardware passthrough, and manage the CI/CD repo structure.

### Agent B: The Device Firmware Engineer

* **Skillset:** Python/Go, BlueZ API, Linux Network Stack, TUI development.
* **Task:** Build the `DEVICE` application, implement the Bluetooth listening service, and the WiFi connection logic.

### Agent C: The Full-Stack Engineer

* **Skillset:** FastAPI/Node.js, React Native/Flutter, API Design (REST/WebSockets).
* **Task:** Develop the `SERVER` logic and the `APP` interface, ensuring the token exchange flow is secure.

---

## 3. Proposed Folder Structure

```text
/iot-provisioning-demo
├── .github/workflows       # CI/CD for testing and deployment
├── scripts/                # LXD setup and hardware passthrough scripts
│   └── setup_lxd.sh        # Automates VM creation and BT/WiFi bridging
├── device/                 # DEVICE Component (Linux-based)
│   ├── src/                # TUI and Logic
│   ├── bluetooth/          # BT Advertisement & Service scripts
│   └── network/            # WiFi connection handlers
├── server/                 # SERVER Component
│   ├── src/                # API Endpoints
│   └── database/           # Mock DB for token storage
├── app/                    # MOBILE APP Component
│   ├── src/                # React Native / Flutter code
│   └── assets/             # Icons and styles
├── docs/                   # Specs and diagrams
└── docker-compose.yml      # For running the Server locally

```

---

## 4. Development Roadmap for Agents

### Phase 1: Environment (Agent A)

* Configure LXD to allow the container access to `/dev/bluez` and the physical WiFi interface.
* Initialize the GitHub Repo.

### Phase 2: Connectivity (Agent B & C)

* **Agent B** creates the BT GATT service on the Device to receive SSID/Password.
* **Agent C** creates the Mobile UI to scan for that BT service and send credentials.

### Phase 3: Provisioning (Agent B, C, & Architect)

* **Server** generates the token.
* **Device** fetches token and renders QR in TUI using ASCII/ANSI.
* **App** scans QR and posts to Server.
* **Server** validates and notifies Device.

---

## 5. Implementation Notes for OpenCode/Zed

1. **Hardware Passthrough:** Since you are emulating on Linux, ensure your user is in the `lp` or `bluetooth` group. Use `lxc config device add <container> hci0 unix-char path=/dev/hci0` to give the DEVICE access to the host Bluetooth.
2. **QR in TUI:** For the Device terminal, I recommend using a library that supports **ANSI 256 colors** to ensure the QR code is readable by the mobile camera.
3. **Mutual Trust:** To ensure true "Mutual Trust," Agent A should generate a self-signed Root CA and issue certificates for both the Server and the Device during the provisioning step.
