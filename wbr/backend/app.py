#!/usr/bin/env python3
"""WBR read-only backend bridge. Empty data stays empty; no synthetic live data."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("WBR_DATA_DIR", "data"))

def read_json(name, default):
    try:
        with (DATA / name).open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        routes = {
            "/health": lambda: {"status":"ok","service":"wbr-backend","mode":"read-only","data_dir_exists":DATA.exists()},
            "/api/v1/health": lambda: {"status":"ok","service":"wbr-backend","mode":"read-only","data_dir_exists":DATA.exists()},
            "/api/v1/sources": lambda: read_json("sources.json", []),
            "/api/v1/matches": lambda: read_json("matches.json", []),
            "/api/v1/odds": lambda: read_json("odds.json", []),
            "/api/v1/forecasts": lambda: read_json("forecasts.json", []),
            "/api/v1/providers": lambda: read_json("provider_registry.json", []),
            "/api/v1/matches/canonical": lambda: read_json("canonical_matches.json", []),
            "/api/v1/odds/matched": lambda: {"odds":read_json("matched_odds.json", []),"matched_count":0,"unmatched_count":0,"status":"NO_IMPORTED_DATA"},
        }
        if path not in routes:
            return self._send(404, {"error":"not_found","path":path})
        return self._send(200, routes[path]())

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
