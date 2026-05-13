#!/usr/bin/env python3
import subprocess
import logging
import time
import os

logger = logging.getLogger(__name__)

NMCLI_BIN = "/usr/bin/nmcli"


def _is_mock_env():
    return not os.path.exists(NMCLI_BIN)


def _run(*args, check=True, capture=True, timeout=30):
    cmd = [NMCLI_BIN, *args]
    logger.debug("Running: %s", " ".join(cmd))
    if _is_mock_env():
        return MockWiFiManager._mock_nmcli(args)
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result


class WiFiManager:
    def __init__(self, force_mock=False):
        self._force_mock = force_mock
        self._connected_ssid = None
        self._last_error: str | None = None
        self._interface = self._detect_wifi_interface()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _is_mock(self):
        return self._force_mock or not os.path.exists(NMCLI_BIN)

    def _detect_wifi_interface(self):
        if self._is_mock():
            return "wlan0"
        try:
            result = subprocess.run(
                [NMCLI_BIN, "-t", "-f", "DEVICE,TYPE", "device"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                if ":wifi" in line:
                    iface = line.split(":")[0]
                    logger.info("Detected WiFi interface: %s", iface)
                    return iface
        except Exception as e:
            logger.warning("Could not detect WiFi interface: %s", e)
        return "wlan0"

    @property
    def interface(self):
        return self._interface

    @property
    def connected_ssid(self):
        return self._connected_ssid

    def radio_on(self):
        logger.info("Enabling WiFi radio...")
        if self._is_mock():
            return
        _run("radio", "wifi", "on")

    def radio_off(self):
        logger.info("Disabling WiFi radio...")
        if self._is_mock():
            return
        _run("radio", "wifi", "off")

    def ensure_wifi_down(self):
        logger.info("Bringing WiFi interface '%s' down...", self._interface)
        if self._is_mock():
            return
        subprocess.run(
            ["ip", "link", "set", self._interface, "down"],
            capture_output=True, timeout=10,
        )

    def ensure_wifi_up(self):
        logger.info("Bringing WiFi interface '%s' up...", self._interface)
        if self._is_mock():
            return
        subprocess.run(
            ["ip", "link", "set", self._interface, "up"],
            capture_output=True, timeout=10,
        )

    def scan(self):
        logger.info("Scanning for WiFi networks...")
        if self._is_mock():
            return []
        _run("device", "wifi", "rescan", check=False, timeout=15)
        time.sleep(3)
        result = _run("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", check=False)
        networks = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3:
                networks.append({
                    "ssid": parts[0],
                    "signal": parts[1],
                    "security": parts[2],
                })
        return networks

    def connect(self, ssid: str, password: str) -> bool:
        """Connect to a WiFi network. Returns True on success, False on failure."""
        logger.info("Connecting to WiFi: SSID='%s'", ssid)
        self._connected_ssid = None
        self._last_error = None

        if self._is_mock():
            if password == "wrongpassword":
                self._last_error = f"Authentication failed for SSID '{ssid}'"
                return False
            self._connected_ssid = ssid
            return True

        self.ensure_wifi_up()

        try:
            result = _run(
                "device", "wifi", "connect", ssid,
                "password", password,
                "ifname", self._interface,
                timeout=45,
            )
            if result.returncode != 0:
                self._last_error = f"nmcli connect failed: {result.stderr.strip()}"
                return False
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            if "Secrets were required" in stderr or "activation failed" in stderr.lower():
                self._last_error = f"Authentication failed for SSID '{ssid}'"
            else:
                self._last_error = f"nmcli error: {e}"
            return False

        if self._verify_connection(ssid):
            self._connected_ssid = ssid
            logger.info("Successfully connected to '%s'", ssid)
            return True

        self._last_error = f"Connected but could not verify SSID '{ssid}'"
        return False

    def _verify_connection(self, expected_ssid):
        if self._is_mock():
            return self._connected_ssid == expected_ssid

        try:
            result = _run("-t", "-f", "GENERAL.CONNECTION", "device", "show", self._interface, check=False)
            current = result.stdout.strip()
            return expected_ssid in current
        except Exception:
            pass
        return False

    def is_connected(self):
        if self._is_mock():
            return self._connected_ssid is not None
        try:
            result = _run("-t", "-f", "GENERAL.STATE", "device", "show", self._interface, check=False)
            state = result.stdout.strip()
            return "connected" in state.lower()
        except Exception:
            return False

    def get_ip_address(self):
        if self._is_mock():
            return "10.0.0.99"
        try:
            result = _run("-t", "-f", "IP4.ADDRESS", "device", "show", self._interface, check=False)
            lines = result.stdout.strip().splitlines()
            for line in lines:
                if line.strip():
                    parts = line.split("/")
                    if parts:
                        return parts[0]
        except Exception as e:
            logger.warning("Could not get IP address: %s", e)
        return None

    def disconnect(self):
        logger.info("Disconnecting WiFi...")
        if self._is_mock():
            self._connected_ssid = None
            return
        try:
            _run("device", "disconnect", self._interface, check=False)
        except Exception as e:
            logger.warning("Error disconnecting: %s", e)
        self._connected_ssid = None

    def forget_connection(self, ssid):
        logger.info("Forgetting WiFi connection '%s'...", ssid)
        if self._is_mock():
            return
        try:
            _run("connection", "delete", "id", ssid, check=False)
        except Exception:
            _run("connection", "delete", ssid, check=False)

    def list_saved_connections(self):
        if self._is_mock():
            return []
        try:
            result = _run("-t", "-f", "NAME,TYPE", "connection", check=False)
            connections = []
            for line in result.stdout.strip().splitlines():
                if ":wifi" in line.lower() or ":802-11-wireless" in line.lower():
                    connections.append(line.split(":")[0])
            return connections
        except Exception:
            return []


class WiFiAuthError(Exception):
    pass


class MockWiFiManager:
    @staticmethod
    def _mock_nmcli(args):
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""
        result = MockResult()

        if args[0] == "radio" and "on" in args:
            result.stdout = ""
        elif args[0] == "radio" and "off" in args:
            result.stdout = ""
        elif args[0] == "device" and "wifi" in args and "connect" in args:
            result.stdout = "Device 'wlan0' successfully activated."
        elif args[0] == "-t" and "device" in args and "show" in args:
            result.stdout = "connected\nwlan0\n"
        elif args[0] == "device" and "disconnect" in args:
            result.stdout = "Device 'wlan0' successfully disconnected."
        else:
            result.returncode = 0
            result.stdout = ""
        return result