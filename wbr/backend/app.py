#!/usr/bin/env python3
"""WBR backend bridge with server-side provider sync. No synthetic data."""
import json, os, csv, io, urllib.request, urllib.error
from datetime import datetime, timezone, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import zipfile

# Load the small runtime bundle uploaded beside app.py. Only known backend
# module paths are extracted; no archive paths can escape this directory.
_BACKEND_DIR = Path(__file__).resolve().parent
_MODULE_BUNDLE = _BACKEND_DIR / "wbr_backend_modules.zip"
if _MODULE_BUNDLE.is_file():
    with zipfile.ZipFile(_MODULE_BUNDLE) as _bundle:
        for _name in _bundle.namelist():
            _target = Path(_name)
            if _target.is_absolute() or ".." in _target.parts:
                raise RuntimeError("Unsafe path in WBR module bundle")
            if not (_name.startswith("wbr_sources/") or (_target.name.startswith("wbr_") and _target.suffix == ".py") or _name == "provider_registry.json"):
                raise RuntimeError("Unexpected file in WBR module bundle: " + _name)
            _dest = _BACKEND_DIR / _target
            _dest.parent.mkdir(parents=True, exist_ok=True)
            _dest.write_bytes(_bundle.read(_name))
from wbr_sync_coordinator import apply_provider_batches
from wbr_sources.espn import normalize_response as normalize_espn_response
from wbr_sources.fixture_csv import normalize_csv
from wbr_moviodds_pipeline import process_moviodds_payload
from wbr_odds_radar import build_odds_radar

DATA = Path(os.environ.get("WBR_DATA_DIR", "data"))
SPORTAPI_KEY = os.environ.get("SPORTAPI_API_KEY", "")
MOVIODDS_KEY = os.environ.get("MOVIODDS_API_KEY", "")
PUNTERSEDGE_KEY = os.environ.get("PUNTERSEDGE_API_KEY", "")
SYNC_TOKEN = os.environ.get("WBR_SYNC_TOKEN", "")
ESPN_LEAGUES = [x.strip() for x in os.environ.get("WBR_ESPN_LEAGUES", "eng.1,esp.1,ger.1,ita.1,fra.1,usa.1").split(",") if x.strip()]
MAX_IMPORT_BYTES = 4 * 1024 * 1024

def rebuild_canonical(matches):
    from wbr_canonical_schedule import build_canonical_schedule
    return build_canonical_schedule(matches)

def persist_fixture_batches(batches, stamp):
    existing = read_json("matches.json", [])
    applied = apply_provider_batches(existing, batches)
    matches = applied["matches"]
    canonical = applied["canonical_schedule"]
    write_json("matches.json", matches)
    write_json("canonical_matches.json", canonical.get("matches", []))
    write_json("canonical_schedule_report.json", canonical)
    return applied

def fetch_espn_day(target_date):
    batches=[]; reports=[]
    date_compact=target_date.replace("-", "")
    for league in ESPN_LEAGUES:
        url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={date_compact}"
        try:
            payload, headers=fetch_json(url, {"Accept":"application/json", "User-Agent":"WBR/1.0"})
            normalized=normalize_espn_response(payload)
            batches.append({"provider":f"ESPN:{league}","matches":normalized["matches"]})
            reports.append({"provider":f"ESPN:{league}","status":"OK","fixtures":normalized["count"],"rejected":len(normalized["rejected"])})
        except urllib.error.HTTPError as e:
            reports.append({"provider":f"ESPN:{league}","status":"HTTP_ERROR","http_status":e.code})
        except Exception as e:
            reports.append({"provider":f"ESPN:{league}","status":"ERROR","message":str(e)[:250]})
    return batches,reports

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
    # Use the registry shipped with this backend. Older builds referenced a
    # provider_catalog.json file that is not part of the current package.
    registry_path = Path(__file__).parent / "provider_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    items = []
    for p in registry.get("providers", []):
        env = p.get("secret_env")
        configured = bool(os.environ.get(env, "")) if env else None
        adapter = p.get("adapter_status", "unknown")
        declared = p.get("status", "NOT_TESTED")
        if env and not configured:
            status = "MISSING_SERVER_SECRET"
        elif adapter in ("existing_user_integration_to_reuse", "payload_normalizer_implemented_transport_not_configured"):
            status = declared
        else:
            status = declared
        items.append({
            "provider": p.get("provider_name", "Unknown"),
            "configured": configured,
            "scope": ",".join(p.get("supported_sports", [])) or "not_declared",
            "integration_status": adapter,
            "status": status,
            "enabled": bool(p.get("enabled", False)),
            "notes": p.get("notes")
        })
    return {"providers":items,"sync_protected":bool(SYNC_TOKEN),"storage":"ephemeral_render_filesystem","note":"Registration does not imply a working API adapter. Render Free data files are not persistent."}

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
            "/api/v1/odds/matched": lambda: read_json("matched_odds.json", {"odds":[],"matched_count":0,"unmatched_count":0,"status":"NO_IMPORTED_DATA"}),
            "/api/v1/odds/radar": lambda: read_json("odds_radar.json", {"markets":[],"quote_count":0,"status":"NO_IMPORTED_DATA"}),
            "/api/v1/sync/status": lambda: read_json("last_sync.json", {"status":"NO_SYNC_YET"}),
        }
        if path not in routes: return self._send(404, {"error":"not_found","path":path})
        return self._send(200, routes[path]())

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path not in ("/api/v1/sync", "/api/v1/import/csv"):
            return self._send(404, {"error":"not_found","path":path})
        if not SYNC_TOKEN:
            return self._send(503, {"error":"sync_disabled","message":"Set WBR_SYNC_TOKEN in Render first."})
        if self.headers.get("X-WBR-Sync-Token","") != SYNC_TOKEN:
            return self._send(401, {"error":"unauthorized"})
        try:
            length = int(self.headers.get("Content-Length","0"))
            if length < 0 or length > MAX_IMPORT_BYTES:
                return self._send(413, {"error":"payload_too_large","max_bytes":MAX_IMPORT_BYTES})
            raw = self.rfile.read(length)
            if path == "/api/v1/import/csv":
                csv_text=raw.decode("utf-8-sig")
                qs=parse_qs(urlparse(self.path).query)
                provider=(qs.get("provider") or ["OpenFootball"])[0]
                season=(qs.get("season") or [None])[0]
                competition=(qs.get("competition") or [None])[0]
                normalized=normalize_csv(csv_text, provider=provider, season=season, competition=competition)
                batch={"provider":provider,"matches":normalized["matches"]}
                applied=persist_fixture_batches([batch], datetime.now(timezone.utc).isoformat())
                result={"provider":provider,"status":"IMPORTED","received":normalized["count"],"rejected":normalized["rejected"],"merge_report":applied["provider_reports"],"canonical_count":applied["canonical_schedule"]["count"]}
                write_json("last_csv_import.json",result)
                return self._send(200,result)
            body=json.loads(raw or b"{}")
        except UnicodeDecodeError:
            return self._send(400,{"error":"csv_must_be_utf8"})
        except Exception as e:
            return self._send(400,{"error":"invalid_request","message":str(e)[:200]})
        target_date = str(body.get("date") or date.today().isoformat())
        try: date.fromisoformat(target_date)
        except ValueError: return self._send(400, {"error":"invalid_date"})
        stamp=datetime.now(timezone.utc).isoformat()
        result={"date":target_date,"retrieved_at_utc":stamp,"providers":[]}
        batches=[]
        if body.get("sportapi", True):
            if not SPORTAPI_KEY:
                result["providers"].append({"provider":"SportAPI.ai","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload,headers=fetch_json("https://sportapi.ai/api/fixtures/date/"+target_date,{"X-Api-Key":SPORTAPI_KEY,"Accept":"application/json"})
                    fixtures=payload.get("data") if isinstance(payload,dict) else payload
                    if fixtures is None and isinstance(payload,dict): fixtures=payload.get("fixtures",[])
                    if not isinstance(fixtures,list): fixtures=[]
                    normalized=[]
                    for item in fixtures:
                        if isinstance(item,dict):
                            row=dict(item); row.setdefault("provider","SportAPI.ai"); row.setdefault("source","SportAPI.ai")
                            row.setdefault("retrieved_at_utc",stamp); row.setdefault("provider_match_id",row.get("id")); row.setdefault("provider_match_key",str(row.get("id")) if row.get("id") is not None else None)
                            normalized.append(row)
                    batches.append({"provider":"SportAPI.ai","matches":normalized})
                    result["providers"].append({"provider":"SportAPI.ai","status":"OK","fixtures":len(normalized),"rate_limit_remaining":headers.get("X-RateLimit-Remaining")})
                except urllib.error.HTTPError as e: result["providers"].append({"provider":"SportAPI.ai","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e: result["providers"].append({"provider":"SportAPI.ai","status":"ERROR","message":str(e)[:300]})
        if body.get("espn", True):
            espn_batches,espn_reports=fetch_espn_day(target_date)
            batches.extend(espn_batches); result["providers"].extend(espn_reports)
        if body.get("puntersedge", True):
            if not PUNTERSEDGE_KEY:
                result["providers"].append({"provider":"PuntersEdge","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload,headers=fetch_json("https://api.puntersedge.online/v1/sports",{"X-API-Key":PUNTERSEDGE_KEY,"Accept":"application/json"})
                    if not isinstance(payload,list): raise ValueError("Unexpected sports catalogue response")
                    write_json("puntersedge_sports.json",{"retrieved_at_utc":stamp,"sports":payload})
                    result["providers"].append({"provider":"PuntersEdge","status":"OK","sports_count":len(payload),"credits_remaining":headers.get("X-Credits-Remaining"),"credits_used":headers.get("X-Credits-Used"),"note":"Catalogue only; no odds markets requested."})
                except urllib.error.HTTPError as e: result["providers"].append({"provider":"PuntersEdge","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e: result["providers"].append({"provider":"PuntersEdge","status":"ERROR","message":str(e)[:300]})
        # Apply every successful fixture batch without replacing other providers' rows.
        if batches:
            try:
                applied=persist_fixture_batches(batches,stamp)
                result["fixture_merge"]={"provider_count":applied["provider_count"],"reports":applied["provider_reports"],"total_source_matches":len(applied["matches"]),"canonical_matches":applied["canonical_schedule"]["count"]}
            except Exception as e:
                result["fixture_merge"]={"status":"ERROR","message":str(e)[:300]}
        if body.get("moviodds", True):
            if not MOVIODDS_KEY:
                result["providers"].append({"provider":"MoviOdds","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload,headers=fetch_json("https://moviodds.com/odds?sport=soccer",{"X-API-Key":MOVIODDS_KEY,"Accept":"application/json"})
                    existing_matches=read_json("matches.json",[]); existing_odds=read_json("odds.json",[])
                    processed=process_moviodds_payload(payload,existing_matches,existing_odds,retrieved_at_utc=stamp)
                    write_json("moviodds_raw.json",processed["raw_archive"])
                    write_json("odds.json",processed["odds"])
                    write_json("matched_odds.json",processed["matched_odds"])
                    write_json("moviodds_ingest_report.json",processed["ingest_report"])
                    result["providers"].append({"provider":"MoviOdds","status":"OK_NORMALIZED","matched_quotes":processed["matched_odds"]["matched_count"],"unmatched_quotes":processed["matched_odds"]["unmatched_count"]})
                except urllib.error.HTTPError as e: result["providers"].append({"provider":"MoviOdds","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e: result["providers"].append({"provider":"MoviOdds","status":"ERROR","message":str(e)[:300]})
        odds=read_json("odds.json",[])
        radar=build_odds_radar(odds)
        write_json("odds_radar.json",radar)
        write_json("last_sync.json",result)
        return self._send(200,result)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT","10000"))), Handler).serve_forever()
