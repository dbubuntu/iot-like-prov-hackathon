#!/usr/bin/env python3
"""
BLE Agent — IoT Device Provisioning

Implements a BLE peripheral using the `bleak` library.
Exposes Service 0xFF01 with individual characteristics:
  - WiFi_SSID    (Write) — receive WiFi network name
  - WiFi_PWD     (Write) — receive WiFi password
  - Conn_Status  (Read / Notify) — report provision state to App
  - Device_Info  (Read) — device identity
"""

import asyncio
import json
import logging
import subprocess
import threading
import uuid as uuid_mod
from enum import Enum, auto

from bleak import BleakServer, BleakGATTCharacteristic, BleakGATTService
from bleak.uuids import uuid16_to_uuid

logger = logging.getLogger(__name__)

# ---------- UUIDs ----------
SERVICE_UUID            = uuid16_to_uuid(0xFF01)
CHAR_WIFI_SSID_UUID     = uuid16_to_uuid(0xFF02)
CHAR_WIFI_PWD_UUID      = uuid16_to_uuid(0xFF03)
CHAR_CONN_STATUS_UUID   = uuid16_to_uuid(0xFF04)
CHAR_DEVICE_INFO_UUID   = uuid16_to_uuid(0xFF05)

BLE_READ        = ["read"]
BLE_WRITE       = ["write"]
BLE_READ_NOTIFY = ["read", "notify"]


# ---------- Provisioning State ----------
class ProvisioningState(Enum):
    WAITING_FOR_APP  = "Idle"
    CONNECTING_WIFI  = "Connecting"
    FETCHING_TOKEN   = "Connected"
    PROVISIONING     = "Provisioning"
    SUCCESS          = "Online"
    ERROR            = "Error"


# ====================================================================
# BLE Agent  (real Bluetooth / bleak)
# ====================================================================
class BLEAgent:
    def __init__(
        self,
        device_name  = "IOT_DEMO_0001",
        device_id    = None,
        on_credentials = None,
    ):
        self.device_name = device_name
        self.device_id   = device_id or str(uuid_mod.uuid4())
        self.mac_address = self._get_mac_address()

        self._on_credentials = on_credentials or (lambda ssid, pwd: None)

        # partial credential accumulator
        self._ssid_buf: str | None = None
        self._pwd_buf:  str | None = None

        self._connection_status = ProvisioningState.WAITING_FOR_APP.value

        self._server   : BleakServer | None = None
        self._loop     : asyncio.AbstractEventLoop | None = None
        self._thread   : threading.Thread | None = None
        self._stop_ev  = threading.Event()
        self._notifying = False

    # ---- MAC address ----
    @staticmethod
    def _get_mac_address() -> str:
        try:
            out = subprocess.check_output(["hcitool", "dev"]).decode()
            for line in out.splitlines():
                if "hci0" in line:
                    parts = line.strip().split()
                    if len(parts) > 2:
                        return parts[1]
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["cat", "/sys/class/bluetooth/hci0/address"]
            ).decode().strip()
            if out:
                return out
        except Exception:
            pass
        return "00:00:00:00:00:00"

    # ---- properties ----
    @property
    def connection_status(self) -> str:
        return self._connection_status

    def update_connection_status(self, status: str):
        self._connection_status = status
        if self._notifying and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._push_notify(), self._loop)

    # ---- GATT service builder ----
    def _build_service(self) -> BleakGATTService:
        svc = BleakGATTService(SERVICE_UUID)

        # -- WiFi SSID (Write) --
        ch_ssid = BleakGATTCharacteristic(
            uuid=CHAR_WIFI_SSID_UUID,
            properties=BLE_WRITE,
            permissions=["write"],
            value=b"",
        )
        ch_ssid.set_write_handler(self._on_ssid_write)

        # -- WiFi Password (Write) --
        ch_pwd = BleakGATTCharacteristic(
            uuid=CHAR_WIFI_PWD_UUID,
            properties=BLE_WRITE,
            permissions=["write"],
            value=b"",
        )
        ch_pwd.set_write_handler(self._on_pwd_write)

        # -- Connection Status (Read + Notify) --
        ch_status = BleakGATTCharacteristic(
            uuid=CHAR_CONN_STATUS_UUID,
            properties=BLE_READ_NOTIFY,
            permissions=["read"],
            value=self._connection_status.encode(),
        )
        ch_status.set_read_handler(self._on_status_read)
        ch_status.set_notify_handler(self._on_status_notify)

        # -- Device Info (Read) --
        info = json.dumps({"device_id": self.device_id, "mac": self.mac_address})
        ch_info = BleakGATTCharacteristic(
            uuid=CHAR_DEVICE_INFO_UUID,
            properties=BLE_READ,
            permissions=["read"],
            value=info.encode(),
        )
        ch_info.set_read_handler(self._on_info_read)

        svc.add_characteristic(ch_ssid)
        svc.add_characteristic(ch_pwd)
        svc.add_characteristic(ch_status)
        svc.add_characteristic(ch_info)
        return svc

    # ---- characteristic handlers ----
    async def _on_ssid_write(self, characteristic, data: bytes):
        self._ssid_buf = data.decode().strip()
        logger.info("WiFi_SSID written: '%s'", self._ssid_buf)
        self._maybe_fire_credentials()

    async def _on_pwd_write(self, characteristic, data: bytes):
        self._pwd_buf = data.decode().strip()
        logger.info("WiFi_PWD written  (len=%d)", len(self._pwd_buf))
        self._maybe_fire_credentials()

    def _maybe_fire_credentials(self):
        if self._ssid_buf is not None and self._pwd_buf is not None:
            logger.info("Both SSID and password received — firing callback")
            ssid, pwd = self._ssid_buf, self._pwd_buf
            self._ssid_buf = self._pwd_buf = None
            threading.Thread(target=self._on_credentials, args=(ssid, pwd), daemon=True).start()

    async def _on_status_read(self, characteristic):
        return self._connection_status.encode()

    async def _on_info_read(self, characteristic):
        return json.dumps({"device_id": self.device_id, "mac": self.mac_address}).encode()

    async def _on_status_notify(self, characteristic, notify: bool):
        self._notifying = notify
        state = "started" if notify else "stopped"
        logger.info("BLE notify %s for Connection_Status", state)

    async def _push_notify(self):
        for ch in self._server.services.characteristics:
            if ch.uuid == str(CHAR_CONN_STATUS_UUID) and self._notifying:
                ch.value = self._connection_status.encode()
                self._server.update_characteristic(ch.uuid, ch.value)

    # ---- server lifecycle ----
    async def _run_server(self):
        self._loop = asyncio.get_running_loop()
        svc = self._build_service()
        self._server = BleakServer(svc, name=self.device_name)
        await self._server.start()
        logger.info("BLE advertising as '%s'", self.device_name)
        while not self._stop_ev.is_set():
            await asyncio.sleep(0.5)
        await self._server.stop()
        logger.info("BLE server stopped")

    def _thread_main(self):
        try:
            asyncio.run(self._run_server())
        except Exception as e:
            logger.error("BLE server error: %s", e)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_ev.set()
        if self._thread:
            self._thread.join(timeout=3)


# ====================================================================
# Mock BLE Agent  (no Bluetooth hardware needed)
# ====================================================================
class MockBLEAgent(BLEAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def start(self):
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._mock_loop, daemon=True)
        self._thread.start()
        logger.info("Mock BLE agent started")

    def _mock_loop(self):
        while not self._stop_ev.is_set():
            self._stop_ev.wait(1.0)

    def inject_credentials(self, ssid: str, password: str):
        """Manually inject credentials for testing."""
        self._on_credentials(ssid, password)