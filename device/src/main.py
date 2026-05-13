#!/usr/bin/env python3
"""
IoT Device Enrollment — Flask + Rich TUI (single process)

- Flask  on port 5001  →  POST /start  triggers enrollment
- Rich TUI            →  left: device info + log   right: QR code

States:  IDLE → AWAITING_TOKEN → PROVISIONING → ONLINE
"""

from __future__ import annotations

import json
import logging
import select
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path

import requests
from flask import Flask
from flask_cors import CORS
from rich.align import Align
from rich.box import ROUNDED, HEAVY
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
DEVICE_ID       = "IOT-DEV-0001"
DEVICE_PORT     = 5001
SERVER_URL      = "http://localhost:5000"
PROVISIONED_FILE = Path(__file__).resolve().parent.parent / "provisioned.json"

TOKEN_TTL_SEC       = 5 * 60
REFRESH_MARGIN_SEC  = 30
POLL_INTERVAL_SEC   = 2
RETRY_INTERVAL_SEC  = 5

# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------
class State(Enum):
    IDLE             = auto()
    AWAITING_TOKEN   = auto()
    PROVISIONING     = auto()
    ONLINE           = auto()

STATE_LABEL = {
    State.IDLE:             "Waiting for App trigger (POST /start)",
    State.AWAITING_TOKEN:   "Requesting token from Server …",
    State.PROVISIONING:     "Scan QR Code to approve",
    State.ONLINE:           "Provisioned — Online",
}

STATE_COLOR = {
    State.IDLE:             "cyan",
    State.AWAITING_TOKEN:   "blue",
    State.PROVISIONING:     "magenta",
    State.ONLINE:           "green",
}

# ---------------------------------------------------------------------------
# QR generation — builds a Rich Text object directly (styled spans, no markup)
# ---------------------------------------------------------------------------
def _qr_render(content: str, scale: int = 2, border: int = 0) -> Text:
    """Return a Rich Text with black-on-white block modules — square and non‑wrapping."""
    import qrcode
    from PIL import Image

    from rich.style import Style

    DARK  = Style(bgcolor="white", color="black")
    LIGHT = Style()

    qr = qrcode.QRCode(version=None, box_size=scale, border=border)
    qr.add_data(content)
    qr.make(fit=True)
    img: Image.Image = qr.make_image(fill_color="black", back_color="white")
    img = img.convert("1")

    result = Text(no_wrap=True)
    w, h = img.size
    for y in range(0, h, 2):
        row = Text(no_wrap=True)
        for x in range(w):
            top    = img.getpixel((x, y))
            bottom = img.getpixel((x, y + 1)) if y + 1 < h else 1
            if top == 0 and bottom == 0:
                ch, st = "█", DARK
            elif top == 0 and bottom == 1:
                ch, st = "▀", DARK
            elif top == 1 and bottom == 0:
                ch, st = "▄", DARK
            else:
                ch, st = " ", LIGHT
            row.append(ch, style=st)
        result.append(row)
        result.append("\n")
    return result


# ---------------------------------------------------------------------------
# main application
# ---------------------------------------------------------------------------
class DeviceApp:
    def __init__(self):
        self.console = Console()
        self.state   = State.IDLE
        self._lk     = threading.Lock()

        self._token: str | None = None
        self._token_exp: datetime | None = None
        self._retry_sec: int = 0

        self._log_lines: list[tuple[str, str]] = []

        self._start_ev = threading.Event()    # signaled by POST /start
        self._stop_ev  = threading.Event()
        self._done_ev  = threading.Event()

        self._enroll_thr: threading.Thread | None = None

        # Flask app (created in run())
        self._flask = Flask(__name__)
        CORS(self._flask)
        self._flask.add_url_rule("/start", "start", self._flask_start, methods=["POST"])
        self._flask.add_url_rule("/shutdown", "shutdown", self._flask_shutdown, methods=["POST"])

    # ------ Flask endpoint ------
    def _flask_start(self):
        self._start_ev.set()
        return {"status": "enrollment triggered", "device_id": DEVICE_ID}

    def _flask_shutdown(self):
        self._stop_ev.set()
        return {"status": "shutting down"}

    # ------ logging ------
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append((ts, msg))
        self._log_lines = self._log_lines[-50:]

    # ------ state ------
    def _set_state(self, s: State):
        with self._lk:
            self.state = s
        self._log(STATE_LABEL.get(s, str(s)))

    # ==================================================================
    # enrollment logic  (runs in background thread)
    # ==================================================================
    def _enrollment_loop(self):
        while not self._stop_ev.is_set():
            self._start_ev.wait()
            if self._stop_ev.is_set():
                return
            self._start_ev.clear()

            self._log("Enrollment triggered via POST /start")
            self._run_enrollment()

    def _run_enrollment(self):
        # -- request token --
        self._set_state(State.AWAITING_TOKEN)
        while not self._stop_ev.is_set():
            self._retry_sec = 0
            try:
                resp = requests.get(
                    f"{SERVER_URL}/v1/device/token",
                    params={"id": DEVICE_ID},
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tok = data.get("token")
                    if tok:
                        self._token = tok
                        self._token_exp = datetime.now() + timedelta(seconds=TOKEN_TTL_SEC)
                        self._log(f"Token received: {self._token}")
                        self._set_state(State.PROVISIONING)
                        break
                self._log(f"Server HTTP {resp.status_code}")
            except (requests.ConnectionError, requests.Timeout):
                pass
            except Exception as e:
                self._log(f"Token error: {e}")

            # retry countdown
            for r in range(RETRY_INTERVAL_SEC, 0, -1):
                if self._stop_ev.is_set():
                    return
                self._retry_sec = r
                time.sleep(1)

        if self._token is None:
            return

        # -- poll approval --
        while not self._stop_ev.is_set():
            # token expiry → refresh
            if self._token_exp and datetime.now() > self._token_exp - timedelta(seconds=REFRESH_MARGIN_SEC):
                self._log("Token expiring — refreshing …")
                self._run_enrollment()
                return

            try:
                resp = requests.get(
                    f"{SERVER_URL}/v1/device/status/{DEVICE_ID}",
                    timeout=5,
                )
                if resp.status_code == 200 and resp.json().get("approved"):
                    self._on_provisioned()
                    return
            except (requests.ConnectionError, requests.Timeout):
                for r in range(RETRY_INTERVAL_SEC, 0, -1):
                    if self._stop_ev.is_set():
                        return
                    self._retry_sec = r
                    time.sleep(1)
            except Exception:
                pass

            time.sleep(POLL_INTERVAL_SEC)

    def _on_provisioned(self):
        self._set_state(State.ONLINE)
        self._log("Device provisioned ✓")
        data = {
            "device_id": DEVICE_ID,
            "provisioned_at": datetime.now().isoformat(),
        }
        try:
            PROVISIONED_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROVISIONED_FILE.write_text(json.dumps(data, indent=2))
            self._log(f"Saved {PROVISIONED_FILE}")
        except Exception as e:
            self._log(f"Failed to save provisioned.json: {e}")
        self._done_ev.set()

    # ==================================================================
    # Rich TUI
    # ==================================================================
    def _build_layout(self) -> Layout:
        root = Layout()
        root.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        root["body"].split_row(
            Layout(name="left",  ratio=2),
            Layout(name="right", ratio=3, minimum_size=55),
        )
        return root

    def _render_header(self) -> Panel:
        label = STATE_LABEL.get(self.state, "")
        color = STATE_COLOR.get(self.state, "white")
        return Panel(
            Text(f"IoT Device Enrollment  │  {label}", style=f"bold {color}"),
            box=HEAVY, style=color,
        )

    def _render_left(self) -> Panel:
        tbl = Table(box=None, show_header=False, show_edge=False, padding=(0, 1))
        tbl.add_column("", style="bold cyan", width=14)
        tbl.add_column("", style="white")
        tbl.add_row("Device ID:",  DEVICE_ID)
        tbl.add_row("Device Port:", str(DEVICE_PORT))
        tbl.add_row("Server URL:",  SERVER_URL)
        tbl.add_row("State:",       STATE_LABEL.get(self.state, str(self.state)))

        tbl.add_row("", "")
        tbl.add_row("API Endpoint:", "[bold]POST /start[/bold]")

        if self.state == State.IDLE:
            tbl.add_row("", "")
            tbl.add_row("Instructions:", "[bold cyan]Send POST /start to begin enrollment[/bold cyan]")

        if self._retry_sec > 0:
            tbl.add_row("", "")
            tbl.add_row("Retry in:", f"[yellow]{self._retry_sec}s[/yellow]")

        return Panel(tbl, title="Device Info", border_style="cyan", box=ROUNDED)

    def _render_right(self) -> Panel:
        if self.state == State.PROVISIONING and self._token:
            qr_json = json.dumps({"token": self._token, "device_id": DEVICE_ID})
            try:
                qr_text = _qr_render(qr_json)
            except Exception:
                qr_text = Text(f"[QR Error]\n{self._token}", no_wrap=True)

            expires = ""
            if self._token_exp:
                rem = int((self._token_exp - datetime.now()).total_seconds())
                if rem > 0:
                    m, s = divmod(rem, 60)
                    expires = f"Expires in {m:02d}:{s:02d}"

            hint = Text.from_markup(
                f"\n\nToken: [bold yellow]{self._token}[/bold yellow]\n{expires}",
                justify="center",
            )
            body = Align.center(Text.assemble(qr_text, hint))
            return Panel(body, title="Scan QR to Approve", border_style="magenta", box=ROUNDED)

        if self.state == State.ONLINE:
            success = Align.center(
                Text("✓ Device Provisioned Successfully", style="bold green")
            )
            return Panel(success, title="Online", border_style="green", box=ROUNDED)

        blank = Align.center(Text("(QR will appear here during provisioning)", style="dim"))
        return Panel(blank, title="QR Code", border_style="dim", box=ROUNDED)

    def _render_footer(self) -> Panel:
        hints = Text("q: Quit  │  Ctrl+C: Quit  │  POST /shutdown", style="dim")
        events = self._log_lines[-1:]
        log = "  ".join(f"[dim]{ts}[/dim] {msg}" for ts, msg in events)
        body = Text()
        body.append(hints)
        body.append("  │  ")
        body.append(Text.from_markup(log or "Ready …"))
        return Panel(body, box=ROUNDED, style="dim")

    def _render_all(self) -> Layout:
        layout = self._build_layout()
        layout["header"].update(self._render_header())
        layout["left"].update(self._render_left())
        layout["right"].update(self._render_right())
        layout["footer"].update(self._render_footer())
        return layout

    # ==================================================================
    # lifecycle
    # ==================================================================
    def run(self):
        self._log("Device starting …")

        # start enrollment background thread
        self._enroll_thr = threading.Thread(target=self._enrollment_loop, daemon=True)
        self._enroll_thr.start()

        # start Flask in daemon thread
        def _run_flask():
            self._flask.run(host="0.0.0.0", port=DEVICE_PORT, debug=False, use_reloader=False)
        flask_thr = threading.Thread(target=_run_flask, daemon=True)
        flask_thr.start()
        self._log(f"Flask listening on :{DEVICE_PORT}  (POST /start | POST /shutdown)")

        # Rich TUI main loop
        layout = self._build_layout()
        with Live(layout, console=self.console, screen=True, refresh_per_second=4) as live:

            def _refresh():
                while not self._stop_ev.is_set():
                    try:
                        live.update(self._render_all())
                    except Exception:
                        pass
                    self._stop_ev.wait(0.25)

            threading.Thread(target=_refresh, daemon=True).start()

            # use select() with timeout so we can also react to stop_event
            while True:
                if self._stop_ev.is_set():
                    break
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.25)
                except (KeyboardInterrupt, InterruptedError):
                    self._log("Interrupted — shutting down …")
                    break
                if not r:
                    continue
                try:
                    ch = sys.stdin.read(1)
                except (EOFError, OSError):
                    break
                if not ch:
                    break
                if ch.lower() == "q" or ch == "\x03":
                    self._log("Shutting down …")
                    break

        self._stop_ev.set()
        self._log("Device stopped.")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.WARNING)

    app = DeviceApp()
    signal.signal(signal.SIGINT,  lambda *_: app._stop_ev.set())
    signal.signal(signal.SIGTERM, lambda *_: app._stop_ev.set())
    app.run()


if __name__ == "__main__":
    main()