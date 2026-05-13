#!/usr/bin/env python3
"""HTTPS server that serves the app + proxies Server/Device API calls."""

import http.server
import json
import os
import socket
import socketserver
import ssl
import subprocess
import traceback
import urllib.request
from pathlib import Path

PORT = 9443
APP_DIR = Path(__file__).resolve().parent
CERT_FILE = APP_DIR / "cert.pem"
KEY_FILE = APP_DIR / "key.pem"

MIME = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def generate_cert():
    if CERT_FILE.exists() and KEY_FILE.exists():
        return
    print("Generating self-signed certificate ...")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(KEY_FILE),
            "-out",
            str(CERT_FILE),
            "-days",
            "365",
            "-nodes",
            "-subj",
            f"/CN={get_lan_ip()}",
        ],
        check=True,
    )


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def log_message(self, fmt, *args):
        msg = fmt % args
        print(f"  [{self.client_address[0]}] {self.command} {self.path} → {msg}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        print(f"  [{self.client_address[0]}] OPTIONS {self.path}")
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _proxy(self, upstream):
        path = self.path
        label = ""
        if path.startswith("/server"):
            path = path[len("/server") :] or "/"
            label = "SERVER"
        elif path.startswith("/device"):
            path = path[len("/device") :] or "/"
            label = "DEVICE"

        body_bytes = None
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body_bytes = self.rfile.read(content_length)

        url = upstream + path
        print(f"  [{self.client_address[0]}] → PROXY {label} {self.command} {url}")

        req = urllib.request.Request(url, data=body_bytes, method=self.command)

        for hdr in ("Content-Type", "Accept"):
            val = self.headers.get(hdr)
            if val:
                req.add_header(hdr, val)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                print(
                    f"  [{self.client_address[0]}] ← PROXY {label} {resp.status} ({len(data)} bytes)"
                )
                self.send_response(resp.status)
                self._cors()
                ct = resp.headers.get_content_type() or "application/json"
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            print(
                f"  [{self.client_address[0]}] ← PROXY {label} HTTPError {e.code}: {data[:200]}"
            )
            self.send_response(e.code)
            self._cors()
            ct = e.headers.get_content_type() or "application/json"
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            print(f"  [{self.client_address[0]}] ← PROXY {label} ERROR: {e}")
            traceback.print_exc()
            self.send_response(502)
            self._cors()
            body = json.dumps({"error": str(e)}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/server/"):
            return self._proxy("http://localhost:5000")
        if self.path.startswith("/device/"):
            return self._proxy("http://localhost:5001")
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/server/"):
            return self._proxy("http://localhost:5000")
        if self.path.startswith("/device/"):
            return self._proxy("http://localhost:5001")
        self.send_response(405)
        self.end_headers()


def main():
    os.chdir(str(APP_DIR))
    generate_cert()

    ip = get_lan_ip()

    httpd = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"App:            https://{ip}:{PORT}/")
    print(f"Server proxy:   /server/* → http://localhost:5000/*")
    print(f"Device proxy:   /device/* → http://localhost:5001/*")
    print()
    print("On your phone, accept cert warning (Advanced → Proceed).")
    print(f"Fields in app:  Server URL=/server   Device URL=/device")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
