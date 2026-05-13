#!/usr/bin/env python3
"""
IoT Provisioning Demo — Device Entry Point / TUI

Launches the BLE Agent and renders a Rich-based terminal UI.
Provisioning flow:

  WAITING_FOR_APP  — BLE advertising; show "Scan for Device"
  CONNECTING_WIFI  — credentials received; join WiFi via nmcli
  FETCHING_TOKEN   — WiFi up; request token from server
  PROVISIONING     — display QR code; wait for App approval
  SUCCESS           — provisioned; idle
"""

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid as uuid_mod
from datetime import datetime, timedelta
from pathlib import Path

import requests

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.layout import Layout
from rich.box import ROUNDED, HEAVY

from ble_agent import BLEAgent, MockBLEAgent, ProvisioningState
from wifi_manager import WiFiManager

logger = logging.getLogger(__name__)

DEVICE_CONFIG = Path(__file__).resolve().parent.parent / "device_config.json"

TOKEN_LIFETIME_SEC      = 5 * 60
TOKEN_REFRESH_MARGIN    = 30
POLL_INTERVAL_SEC       = 3
RETRY_INTERVAL_SEC      = 5
DEFAULT_SERVER_PORT     = 8080


# ====================================================================
# helpers
# ====================================================================
def _load_or_create_device_id() -> str:
    if DEVICE_CONFIG.exists():
        try:
            data = json.loads(DEVICE_CONFIG.read_text())
            if "device_id" in data:
                return data["device_id"]
        except Exception:
            pass
    did = "UUID-" + str(uuid_mod.uuid4())[:8].upper()
    DEVICE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_CONFIG.write_text(json.dumps({"device_id": did}))
    return did


def _detect_host_ip() -> str:
    """Best‑effort detection of the LXD host bridge / gateway IP."""
    for cmd in (
        ["ip", "route", "show", "default"],
        ["ip", "route", "show", "default", "table", "main"],
    ):
        try:
            out = subprocess.check_output(cmd, text=True, timeout=5)
            m = re.search(r"via\s+(\S+)", out)
            if m:
                return m.group(1)
        except Exception:
            continue
    return "10.0.0.1"


def _resolve_server_url(env_var="PROVISIONING_SERVER") -> str:
    explicit = os.environ.get(env_var, "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = _detect_host_ip()
    return f"http://{host}:{DEFAULT_SERVER_PORT}"


# ====================================================================
# QR Code
# ====================================================================
def generate_qr(content: str) -> str:
    """High‑contrast terminal QR via segno (fallback to qrcode)."""
    try:
        import segno
        qr = segno.make(content, micro=False)
        rows = []
        for row in qr.matrix_iter(scale=2):
            rows.append("".join("\u2588\u2588" if c else "  " for c in row))
        return "\n".join(rows)
    except ImportError:
        pass
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=1, border=2)
        qr.add_data(content)
        qr.make(fit=True)
        rows = []
        for row in qr.modules:
            rows.append("".join("\u2588\u2588" if c else "  " for c in row))
        return "\n".join(rows)
    except ImportError:
        return f"[QR lib missing]\n{content}"


# ====================================================================
# TUI colour / label maps
# ====================================================================
STATE_LABELS = {
    ProvisioningState.WAITING_FOR_APP: "Waiting for App (BLE advertising)",
    ProvisioningState.CONNECTING_WIFI: "Connecting to WiFi …",
    ProvisioningState.FETCHING_TOKEN:  "Fetching Token from Server …",
    ProvisioningState.PROVISIONING:    "Scan QR Code to Approve",
    ProvisioningState.SUCCESS:         "Device Provisioned ✓",
    ProvisioningState.ERROR:           "Error",
}

STATE_COLORS = {
    ProvisioningState.WAITING_FOR_APP: "cyan",
    ProvisioningState.CONNECTING_WIFI: "bright_yellow",
    ProvisioningState.FETCHING_TOKEN:  "blue",
    ProvisioningState.PROVISIONING:    "magenta",
    ProvisioningState.SUCCESS:         "green",
    ProvisioningState.ERROR:           "red",
}


# ====================================================================
# Main application
# ====================================================================
class ProvisioningApp:
    def __init__(self, mock_ble=False, mock_wifi=False, server_url=None):
        self.console    = Console()
        self.mock_ble   = mock_ble
        self.mock_wifi  = mock_wifi

        self.state      = ProvisioningState.WAITING_FOR_APP
        self._state_lk  = threading.Lock()

        self.device_id  = _load_or_create_device_id()
        self.wifi       = WiFiManager(force_mock=mock_wifi)
        self.ble: BLEAgent | MockBLEAgent | None = None

        self._server_url = server_url or _resolve_server_url()
        self._ssid       : str | None = None
        self._password   : str | None = None
        self._token      : str | None = None
        self._token_exp  : datetime | None = None
        self._error_msg  : str | None = None
        self._retry_sec  : int = 0

        self._log_lines: list[tuple[str, str]] = []

        self._stop_ev  = threading.Event()
        self._poll_thr : threading.Thread | None = None

    # ---------- state / logging ----------
    def _set_state(self, s: ProvisioningState):
        with self._state_lk:
            old = self.state
            self.state = s
        if old != s:
            label = STATE_LABELS.get(s, s.value)
            self._log(label)
            if self.ble:
                self.ble.update_connection_status(s.value)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append((ts, msg))
        self._log_lines = self._log_lines[-50:]
        logger.info(msg)

    # ---------- BLE credentials callback ----------
    def _on_credentials(self, ssid: str, password: str):
        self._log(f"BLE credentials → SSID='{ssid}'")
        self._ssid     = ssid
        self._password = password
        threading.Thread(target=self._wifi_connect, daemon=True).start()

    # ---------- WiFi ----------
    def _wifi_connect(self):
        self._set_state(ProvisioningState.CONNECTING_WIFI)
        try:
            ok = self.wifi.connect(self._ssid, self._password)
        except Exception as e:
            self._set_state(ProvisioningState.ERROR)
            self._error_msg = f"WiFi error: {e}"
            self._log(self._error_msg)
            return

        if not ok:
            self._set_state(ProvisioningState.ERROR)
            self._error_msg = self.wifi.last_error or "WiFi connection failed"
            self._log(self._error_msg)
            return

        ip = self.wifi.get_ip_address()
        self._log(f"WiFi connected — IP: {ip}")
        threading.Thread(target=self._fetch_token, daemon=True).start()

    # ---------- server interaction ----------
    def _fetch_token(self):
        self._set_state(ProvisioningState.FETCHING_TOKEN)
        base = self._server_url.rstrip("/")

        while not self._stop_ev.is_set():
            try:
                url = f"{base}/v1/enroll/token/{self.device_id}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    tok = data.get("token")
                    if not tok:
                        self._set_state(ProvisioningState.ERROR)
                        self._error_msg = "Server returned empty token"
                        return
                    self._token = tok
                    self._token_exp = datetime.now() + timedelta(seconds=TOKEN_LIFETIME_SEC)
                    self._log(f"Token: {self._token}")
                    self._set_state(ProvisioningState.PROVISIONING)
                    self._start_polling()
                    return
                else:
                    self._log(f"Token endpoint HTTP {resp.status_code}")
            except (requests.ConnectionError, requests.Timeout):
                pass
            except Exception as e:
                self._log(f"Token request error: {e}")

            self._countdown(RETRY_INTERVAL_SEC)

    def _start_polling(self):
        if self._poll_thr and self._poll_thr.is_alive():
            return
        self._poll_thr = threading.Thread(target=self._poll_status, daemon=True)
        self._poll_thr.start()

    def _poll_status(self):
        base = self._server_url.rstrip("/")

        while not self._stop_ev.is_set():
            if self._token is None:
                time.sleep(1)
                continue

            # token expiry
            if self._token_exp and \
               datetime.now() > self._token_exp - timedelta(seconds=TOKEN_REFRESH_MARGIN):
                self._log("Token expiring — refreshing …")
                self._set_state(ProvisioningState.FETCHING_TOKEN)
                self._fetch_token()
                return

            try:
                url = f"{base}/v1/enroll/status/{self.device_id}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200 and resp.json().get("approved"):
                    self._on_success()
                    return
            except (requests.ConnectionError, requests.Timeout):
                self._countdown(RETRY_INTERVAL_SEC)
            except Exception:
                pass

            time.sleep(POLL_INTERVAL_SEC)

    def _countdown(self, seconds: int):
        for r in range(seconds, 0, -1):
            if self._stop_ev.is_set():
                return
            self._retry_sec = r
            time.sleep(1)
        self._retry_sec = 0

    def _on_success(self):
        self._set_state(ProvisioningState.SUCCESS)
        self._log("Device Provisioned ✓")

        data = {
            "device_id":    self.device_id,
            "ssid":         self._ssid,
            "password":     self._password,
            "server_url":   self._server_url,
            "provisioned_at": datetime.now().isoformat(),
        }
        try:
            DEVICE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            DEVICE_CONFIG.write_text(json.dumps(data, indent=2))
            self._log(f"Saved {DEVICE_CONFIG}")
        except Exception as e:
            self._log(f"Failed to save config: {e}")

    # ---------- TUI ----------
    def _build_layout(self) -> Layout:
        root = Layout()
        root.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        root["body"].split_row(
            Layout(name="log", ratio=2),
            Layout(name="main", ratio=3),
        )
        return root

    def _render_header(self) -> Panel:
        label = STATE_LABELS.get(self.state, self.state.value)
        color = STATE_COLORS.get(self.state, "white")
        return Panel(
            Text(f"IoT Provisioning Device  │  {label}", style=f"bold {color}"),
            box=HEAVY, style=color,
        )

    def _render_log(self) -> Panel:
        tbl = Table(box=None, show_header=False, show_edge=False, padding=(0, 1))
        tbl.add_column("Time", style="dim", width=9)
        tbl.add_column("Message", style="white")
        for ts, msg in self._log_lines[-20:]:
            tbl.add_row(ts, msg)
        if not self._log_lines:
            tbl.add_row("--:--:--", "Starting …")
        return Panel(tbl, title="Event Log", border_style="blue", box=ROUNDED)

    def _render_main(self) -> Panel:
        if self.state == ProvisioningState.PROVISIONING and self._token:
            return self._render_qr()

        tbl = Table(box=None, show_header=False, show_edge=False, padding=(0, 1))
        tbl.add_column("", style="bold cyan", width=17)
        tbl.add_column("", style="white")

        tbl.add_row("Device ID:",  self.device_id)
        bt_mac = self.ble.mac_address if self.ble else "N/A"
        tbl.add_row("Bluetooth MAC:", bt_mac)
        tbl.add_row("BLE Name:",    f"IOT_DEMO_{self.device_id[-4:]}")
        tbl.add_row("Server URL:",  self._server_url)
        tbl.add_row("WiFi SSID:",   self._ssid or "(waiting)")
        tbl.add_row("BLE Mode:",    "Mock" if self.mock_ble else "Real")
        tbl.add_row("WiFi Mode:",   "Mock" if self.mock_wifi else "Real")

        ip = self.wifi.get_ip_address()
        tbl.add_row("IP Address:",  ip or "N/A")

        if self._error_msg:
            tbl.add_row("Error:",   f"[red]{self._error_msg}[/red]")
        if self._retry_sec > 0:
            tbl.add_row("Retry in:", f"[yellow]{self._retry_sec}s[/yellow]")

        if self.state == ProvisioningState.WAITING_FOR_APP:
            tbl.add_row("", "")
            tbl.add_row("Instructions:", "[bold cyan]Open the mobile app and scan for BLE devices[/bold cyan]")
            tbl.add_row("", "[bold cyan]named IOT_DEMO_XXXX to begin provisioning.[/bold cyan]")

        return Panel(tbl, title="Device Info", border_style="cyan", box=ROUNDED)

    def _render_qr(self) -> Panel:
        try:
            qr = generate_qr(f"{self._token}|{self.device_id}")
        except Exception:
            qr = f"[QR Error]\nToken: {self._token}"

        expires = ""
        if self._token_exp:
            rem = int((self._token_exp - datetime.now()).total_seconds())
            if rem > 0:
                m, s = divmod(rem, 60)
                expires = f"Expires in {m:02d}:{s:02d}"

        body = f"{qr}\n\nToken: [bold yellow]{self._token}[/bold yellow]\n{expires}"
        return Panel(
            Align.center(Text.from_markup(body)),
            title="Scan QR Code to Approve",
            border_style="magenta", box=ROUNDED,
        )

    def _render_footer(self) -> Panel:
        ble = "Advertising" if (self.ble and not self.mock_ble) else ("Mock" if self.mock_ble else "Stopped")
        return Panel(
            Text(f"q: Quit  │  r: Reset  │  BLE: {ble}", style="dim"),
            box=ROUNDED, style="dim",
        )

    def _render_all(self) -> Layout:
        layout = self._build_layout()
        layout["header"].update(self._render_header())
        layout["log"].update(self._render_log())
        layout["main"].update(self._render_main())
        layout["footer"].update(self._render_footer())
        return layout

    # ---------- lifecycle ----------
    def reset(self):
        self._stop_ev.set()
        if self._poll_thr and self._poll_thr.is_alive():
            self._poll_thr.join(timeout=2)
        self._stop_ev.clear()

        self._ssid = self._password = self._token = None
        self._token_exp = None
        self._error_msg  = None
        self._retry_sec  = 0
        self._poll_thr   = None

        self.wifi.disconnect()
        self._set_state(ProvisioningState.WAITING_FOR_APP)
        self._log("Reset — advertising …")

    def run(self):
        self._log(f"Server URL: {self._server_url}")
        self._log(f"Device ID:  {self.device_id}")

        self._set_state(ProvisioningState.WAITING_FOR_APP)

        name = f"IOT_DEMO_{self.device_id[-4:]}"

        if self.mock_ble:
            self.ble = MockBLEAgent(
                device_name=name,
                device_id=self.device_id,
                on_credentials=self._on_credentials,
            )
        else:
            self.ble = BLEAgent(
                device_name=name,
                device_id=self.device_id,
                on_credentials=self._on_credentials,
            )

        try:
            self.ble.start()
            self._log(f"BLE {'mock ' if self.mock_ble else ''}started — {name}")
        except Exception as e:
            self._log(f"BLE start failed: {e}")
            self._log("Falling back to mock BLE …")
            self.mock_ble = True
            self.ble = MockBLEAgent(device_name=name, device_id=self.device_id,
                                    on_credentials=self._on_credentials)
            self.ble.start()

        layout = self._build_layout()
        with Live(layout, console=self.console, screen=True, refresh_per_second=4) as live:

            def refresher():
                while not self._stop_ev.is_set():
                    try:
                        live.update(self._render_all())
                    except Exception:
                        pass
                    self._stop_ev.wait(0.25)

            threading.Thread(target=refresher, daemon=True).start()

            # non‑blocking key reader
            try:
                import termios, tty
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                restored = True
            except (ImportError, termios.error):
                restored = False

            try:
                while True:
                    try:
                        ch = sys.stdin.read(1)
                    except (EOFError, OSError):
                        break
                    if not ch:
                        break
                    if ch.lower() == "q":
                        self._log("Quitting …")
                        break
                    if ch.lower() == "r":
                        self.reset()
            finally:
                if restored:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)

        self._stop_ev.set()
        if self.ble:
            self.ble.stop()
        self._log("Shutdown.")


# ====================================================================
# entry point
# ====================================================================
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    import argparse
    ap = argparse.ArgumentParser(description="IoT Device Provisioning")
    ap.add_argument("--debug",      action="store_true")
    ap.add_argument("--mock-wifi",  action="store_true")
    ap.add_argument("--mock-ble",   action="store_true")
    ap.add_argument("--server-url", default=None,
                    help="Override server URL (default: detect host gateway)")
    args = ap.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    app = ProvisioningApp(
        mock_ble=args.mock_ble,
        mock_wifi=args.mock_wifi,
        server_url=args.server_url,
    )
    signal.signal(signal.SIGINT,  lambda *_: app._stop_ev.set())
    signal.signal(signal.SIGTERM, lambda *_: app._stop_ev.set())
    app.run()


if __name__ == "__main__":
    main()