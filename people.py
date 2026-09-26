#!/usr/bin/env python3
"""Serve a simple browser view of boston_people.csv.

    python people.py
    open http://127.0.0.1:8766
"""
import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "boston_people.csv"
HTML_PATH = ROOT / "people.html"
HOST = "127.0.0.1"
PORT = 8766


def load_csv():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api":
            body = json.dumps(load_csv()).encode()
            self._send(200, "application/json", body)
            return
        if path in ("/", "/people.html"):
            self._send(200, "text/html; charset=utf-8", HTML_PATH.read_bytes())
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Viewing {CSV_PATH.name} at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
