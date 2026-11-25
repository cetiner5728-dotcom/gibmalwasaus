#!/usr/bin/env python3
"""WBR backend bridge with server-side provider sync. No synthetic data."""
import json, os, urllib.request, urllib.error
from datetime import datetime, timezone, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DATA = Path(os.environ.get("WBR_DATA_DIR", "data"))
SPORTAPI_KEY = os.environ.get("SPORTAPI_API_KEY", "")
MOVIODDS_KEY = os.environ.get("MOVIODDS_API_KEY", "")
SYNC_TOKEN = os.environ.get("WBR_SYNC_TOKEN", "")

def read_json(name, default):
    try:
        with (DATA / name).open("r", encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError): return default

def write_json(name, value):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DATA / name)

def fetch_json(url, headers):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=25) as response:
        body = response.read()
        return json.loads(body.decode("utf-8")), dict(response.headers)

def provider_status():
    return {
      "providers": [
        {"provider":"SportAPI.ai","configured":bool(SPORTAPI_KEY),"auth_header":"X-Api-Key","coverage":"Football and basketball","status":"READY_TO_TEST" if SPORTAPI_KEY else "MISSING_SERVER_SECRET"},
        {"provider":"MoviOdds","configured":bool(MOVIODDS_KEY),"auth_header":"X-API-Key","coverage":"bet365 odds feed","status":"READY_TO_TEST" if MOVIODDS_KEY else "MISSING_SERVER_SECRET"}
      ],
      "sync_protected":bool(SYNC_TOKEN),
      "storage":"ephemeral_render_filesystem",
      "note":"Render Free storage is not persistent; export or add durable storage before relying on retained snapshots."
    }

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WBR-Sync-Token")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WBR-Sync-Token")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        routes = {
            "/health": lambda: {"status":"ok","service":"wbr-backend","mode":"provider-ready","data_dir_exists":DATA.exists()},
            "/api/v1/health": lambda: {"status":"ok","service":"wbr-backend","mode":"provider-ready","data_dir_exists":DATA.exists()},
            "/api/v1/sources": lambda: read_json("sources.json", []),
            "/api/v1/matches": lambda: read_json("matches.json", []),
            "/api/v1/odds": lambda: read_json("odds.json", []),
            "/api/v1/forecasts": lambda: read_json("forecasts.json", []),
            "/api/v1/providers": lambda: provider_status(),
            "/api/v1/provider-status": lambda: provider_status(),
            "/api/v1/matches/canonical": lambda: read_json("canonical_matches.json", []),
            "/api/v1/odds/matched": lambda: {"odds":read_json("matched_odds.json", []),"matched_count":0,"unmatched_count":0,"status":"NO_IMPORTED_DATA"},
        }
        if path not in routes: return self._send(404, {"error":"not_found","path":path})
        return self._send(200, routes[path]())

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path != "/api/v1/sync": return self._send(404, {"error":"not_found","path":path})
        if not SYNC_TOKEN: return self._send(503, {"error":"sync_disabled","message":"Set WBR_SYNC_TOKEN in Render first."})
        if self.headers.get("X-WBR-Sync-Token","") != SYNC_TOKEN:
            return self._send(401, {"error":"unauthorized"})
        try:
            length = min(int(self.headers.get("Content-Length","0")), 4096)
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"error":"invalid_json"})
        target_date = str(body.get("date") or date.today().isoformat())
        try: date.fromisoformat(target_date)
        except ValueError: return self._send(400, {"error":"invalid_date"})
        result = {"date":target_date,"retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"providers":[]}
        if body.get("sportapi", True):
            if not SPORTAPI_KEY:
                result["providers"].append({"provider":"SportAPI.ai","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload, headers = fetch_json("https://sportapi.ai/api/fixtures/date/"+target_date, {"X-Api-Key":SPORTAPI_KEY,"Accept":"application/json"})
                    fixtures = payload.get("data") if isinstance(payload,dict) else payload
                    if fixtures is None and isinstance(payload,dict): fixtures = payload.get("fixtures", [])
                    if not isinstance(fixtures,list): fixtures = []
                    for item in fixtures:
                        if isinstance(item,dict):
                            item.setdefault("source","SportAPI.ai")
                            item.setdefault("retrieved_at_utc",result["retrieved_at_utc"])
                            item.setdefault("provider_match_id",item.get("id"))
                    write_json("matches.json",fixtures)
                    result["providers"].append({"provider":"SportAPI.ai","status":"OK","fixtures":len(fixtures),"rate_limit_remaining":headers.get("X-RateLimit-Remaining")})
                except urllib.error.HTTPError as e:
                    result["providers"].append({"provider":"SportAPI.ai","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e:
                    result["providers"].append({"provider":"SportAPI.ai","status":"ERROR","message":str(e)[:300]})
        if body.get("moviodds", True):
            if not MOVIODDS_KEY:
                result["providers"].append({"provider":"MoviOdds","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload, headers = fetch_json("https://moviodds.com/odds?sport=soccer", {"X-API-Key":MOVIODDS_KEY,"Accept":"application/json"})
                    write_json("moviodds_raw.json",{"retrieved_at_utc":result["retrieved_at_utc"],"payload":payload})
                    result["providers"].append({"provider":"MoviOdds","status":"OK_RAW_ARCHIVED","note":"Raw payload archived; market normalization pending."})
                except urllib.error.HTTPError as e:
                    result["providers"].append({"provider":"MoviOdds","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e:
                    result["providers"].append({"provider":"MoviOdds","status":"ERROR","message":str(e)[:300]})
        write_json("last_sync.json",result)
        return self._send(200,result)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT","10000"))), Handler).serve_forever()
