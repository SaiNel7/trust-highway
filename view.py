#!/usr/bin/env python3
"""Serve a simple browser view of redhat.db.

    python view.py
    open http://127.0.0.1:8765
"""
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "redhat.db"
HTML_PATH = ROOT / "view.html"
HOST = "127.0.0.1"
PORT = 8765

QUERIES = {
    "repos": """
        SELECT full_name, org, description, language, topics, stars, langs, done
        FROM repos
        ORDER BY stars DESC, full_name
    """,
    "users": """
        SELECT login, name, company, location, bio, blog, email, html_url
        FROM users
        ORDER BY login COLLATE NOCASE
    """,
    "contributions": """
        SELECT login, repo, n
        FROM contributions
        ORDER BY n DESC, login
    """,
}


def load_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    payload = {
        name: [dict(row) for row in conn.execute(sql)]
        for name, sql in QUERIES.items()
    }
    conn.close()
    return payload


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api":
            body = json.dumps(load_db()).encode()
            self._send(200, "application/json", body)
            return
        if path in ("/", "/view.html"):
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
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Viewing {DB_PATH.name} at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
