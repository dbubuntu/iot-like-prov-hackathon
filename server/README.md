# IoT Provisioning Server

FastAPI-based provisioning server for the Mutual Trust Flow demo.

## Quick Start

```bash
cd server
pip install -r requirements.txt

# Default: http://0.0.0.0:8000
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8000` | Bind port |
| `CLEANUP_INTERVAL` | `60` | Expired enrollment cleanup interval (seconds) |

### Using env vars with uvicorn

```bash
SERVER_PORT=9000 uvicorn server.main:app --host 0.0.0.0 --port 9000 --reload
```

## Run on the Host Machine (for the full demo)

The Server must be reachable by the **Device VM** and the **Mobile App**. Run it on your host:

```bash
cd server
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Note the host's LAN IP (e.g. `192.168.1.100`). The App will relay this URL to the Device via BLE so the Device knows where to call for tokens.

## API Documentation

Auto-generated docs available at:

- **Swagger UI:** http://localhost:8000/docs
- **OpenAPI JSON:** http://localhost:8000/openapi.json

## Endpoints

### `POST /v1/enroll/init`
Initialize enrollment. Called by the **App** after BLE pairing.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `device_id` | string | Unique device identifier (UUID) |

**Response `200`:**
```json
{
  "device_id": "UUID-1234",
  "token": "AB12CD",
  "status": "pending",
  "expires_in": 300
}
```

---

### `GET /v1/enroll/token/{device_id}`
Fetch the assigned token. Called by the **Device** after connecting to WiFi.

If the token has expired (>5 min), a new one is auto-generated and returned.

**Response `200`:**
```json
{
  "device_id": "UUID-1234",
  "token": "AB12CD",
  "status": "pending",
  "expires_in": 285
}
```

**Response `404`:** No enrollment found — call `/init` first.

---

### `POST /v1/enroll/approve`
Approve a device. Called by the **App** after scanning the QR code.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `token` | string | The 6-character token from the QR code |
| `device_id` | string | The device identifier |

**Response `200`:**
```json
{
  "device_id": "UUID-1234",
  "status": "approved"
}
```

**Response `404`:** Invalid or expired token/device combination.

---

### `GET /v1/enroll/status/{device_id}`
Poll provisioning status. Called by the **Device** in a loop.

**Response `200`:**
```json
{
  "device_id": "UUID-1234",
  "status": "pending",
  "approved": false,
  "token_expired": false
}
```

When approved:
```json
{
  "device_id": "UUID-1234",
  "status": "approved",
  "approved": true,
  "token_expired": false
}
```

---

### `GET /health`
Health check.

**Response `200`:**
```json
{"status": "ok"}
```

## Provisioning Flow

```
App                    Server                Device
 │                        │                     │
 │── POST /init ────────▶│                     │
 │◀── {token} ───────────│                     │
 │                        │                     │
 │                        │◀── GET /token/{id} ─│ (after WiFi connect)
 │                        │── {token} ─────────▶│
 │                        │                     │
 │   [scan QR from Device display]              │
 │                        │                     │
 │── POST /approve ─────▶│                     │
 │◀── {approved} ────────│                     │
 │                        │                     │
 │                        │◀── GET /status/{id} ─│ (polling)
 │                        │── {approved:true} ──▶│
```

## Token Lifecycle

- Tokens are **6-character alphanumeric** (A-Z, 0-9).
- TTL: **5 minutes** (300 seconds).
- Expired tokens are **auto-refreshed** when the Device calls `GET /token/{id}`.
- Expired enrollments are **cleaned up** every 60 seconds.
