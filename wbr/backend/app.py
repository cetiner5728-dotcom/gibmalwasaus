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
PUNTERSEDGE_KEY = os.environ.get("PUNTERSEDGE_API_KEY", "")
APIFOOTBALL_KEY = os.environ.get("APIFOOTBALL_API_KEY", "")
SPORTSCORE_KEY = os.environ.get("SPORTSCORE_API_KEY", "")
STATSHAWK_KEY = os.environ.get("STATSHAWK_API_KEY", "")
FOOTBALL_DATA_KEY = os.environ.get("FOOTBALL_DATA_ORG_API_KEY", "")
SPORTMONKS_TOKEN = os.environ.get("SPORTMONKS_API_TOKEN", "")
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
    catalog = json.loads((Path(__file__).parent / "provider_catalog.json").read_text(encoding="utf-8"))
    items = []
    for p in catalog["providers"]:
        env = p.get("secret_env")
        configured = bool(os.environ.get(env, "")) if env else None
        integration = p.get("integration_status")
        if integration == "verified":
            status = "VERIFIED"
        elif integration == "website_reference_only":
            status = "WEBSITE_REFERENCE_ONLY"
        elif integration == "importer_pending":
            status = "IMPORTER_PENDING"
        elif integration == "verify_docs":
            status = "DOCUMENTATION_REVIEW_REQUIRED"
        elif integration == "adapter_pending":
            status = "PENDING_IMPLEMENTATION"
        elif integration in ("adapter_present_unverified", "adapter_present_catalogue_test_only", "adapter_present"):
            if env and not configured:
                status = "MISSING_SERVER_SECRET"
            elif integration == "adapter_present_catalogue_test_only":
                status = "CATALOGUE_TEST_READY"
            else:
                status = "READY_TO_TEST" if env else "READY_TO_TEST_NO_KEY"
        else:
            status = "UNKNOWN_INTEGRATION_STATE"
        items.append({"provider":p["name"],"configured":configured,"scope":p["scope"],"integration_status":integration,"status":status})
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
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/api/v1/moviodds/odds":
            if not MOVIODDS_KEY:
                return self._send(503,{"provider":"MoviOdds","status":"MISSING_SERVER_SECRET","required_env":"MOVIODDS_API_KEY"})
            sport=(query.get("sport",["soccer"])[0] or "soccer").strip().lower()
            groups=(query.get("groups",["40"])[0] or "40").strip()
            in_play=(query.get("in_play",[""])[0] or "").strip()
            allowed_sports={"soccer","tennis","basketball","american_football","ice_hockey","baseball","cricket","rugby_union","rugby_league","australian_rules","table_tennis","volleyball","handball","badminton","esports","darts","snooker","boxing","mma","futsal","bandy","floorball","field_hockey","gaelic_games","all"}
            if sport not in allowed_sports:
                return self._send(400,{"provider":"MoviOdds","status":"INVALID_SPORT","allowed":sorted(allowed_sports)})
            if groups and (not all(part.strip().isdigit() for part in groups.split(",")) or len(groups)>120):
                return self._send(400,{"provider":"MoviOdds","status":"INVALID_GROUPS","note":"Comma-separated numeric market group IDs expected."})
            if in_play not in ("","0","1"):
                return self._send(400,{"provider":"MoviOdds","status":"INVALID_IN_PLAY","allowed":["0","1"]})
            from urllib.parse import urlencode
            params={"sport":sport}
            if groups: params["groups"]=groups
            if in_play: params["in_play"]=in_play
            endpoint="https://moviodds.com/odds?"+urlencode(params)
            try:
                payload,headers=fetch_json(endpoint,{"X-API-Key":MOVIODDS_KEY,"Accept":"application/json","User-Agent":"WBR/1.0"})
                raw_matches=payload.get("matches",[]) if isinstance(payload,dict) else []
                if not isinstance(raw_matches,list):
                    return self._send(502,{"provider":"MoviOdds","status":"UNEXPECTED_RESPONSE","note":"Expected matches array; no data was imported."})
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for item in raw_matches:
                    if not isinstance(item,dict): continue
                    quotes=item.get("quotes") if isinstance(item.get("quotes"),list) else []
                    clean_quotes=[]
                    for q in quotes:
                        if not isinstance(q,dict): continue
                        price=q.get("odds_dec")
                        try: price=float(price) if price is not None else None
                        except (ValueError,TypeError): price=None
                        clean_quotes.append({"fixture_id":q.get("fixture_id") or item.get("id"),"group_id":q.get("group_id"),"market_id":q.get("market_id"),"selection_id":q.get("sel_id"),"selection":q.get("label"),"odds_decimal":price,"suspended":bool(q.get("suspended",False)),"price_timestamp":q.get("ts")})
                    matches.append({"provider_match_id":str(item.get("id")) if item.get("id") is not None else None,"sport":item.get("sport") or sport,"competition":item.get("league"),"homeTeam":item.get("home"),"awayTeam":item.get("away"),"kickoff_utc":item.get("kickoff_utc"),"in_play":bool(item.get("in_play",False)),"score":item.get("score"),"polled_at":item.get("polled_at"),"market_count":item.get("market_count"),"group_status":item.get("group_status"),"quotes":clean_quotes,"source":"MoviOdds","bookmaker":"bet365"})
                return self._send(200,{"provider":"MoviOdds","status":"OK","sport":sport,"groups":groups or None,"in_play_filter":in_play or "all","count":len(matches),"quote_count":sum(len(m["quotes"]) for m in matches),"matches":matches,"source_bookmaker":"bet365","retrieved_at_utc":stamp,"server_time":payload.get("server_time") if isinstance(payload,dict) else None,"warming":bool(payload.get("warming",False)) if isinstance(payload,dict) else False,"note":"bet365 prices only. Check polled_at, group_status.stale and suspended before treating a price as current. Free plan limits and market coverage are set by MoviOdds."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"MoviOdds","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"MoviOdds","status":"ERROR","message":str(e)[:300]})
        if path == "/api/v1/open-matchday/matches":
            import re,csv,io
            folder=(query.get("league",["ENG_1_premier-league"])[0] or "").strip()
            kind=(query.get("kind",["fixtures"])[0] or "fixtures").strip().lower()
            season=(query.get("season",["2627"])[0] or "2627").strip()
            if not re.fullmatch(r"[A-Z0-9_]+_[a-z0-9-]+",folder) or kind not in ("fixtures","results","goals") or season!="2627":
                return self._send(400,{"provider":"Open-Matchday","status":"INVALID_PARAMETERS","allowed_kinds":["fixtures","results","goals"],"season":"2627"})
            url="https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/"+folder+"/"+kind+"_"+season+".csv"
            try:
                req=urllib.request.Request(url,headers={"Accept":"text/csv","User-Agent":"WBR/1.0"})
                with urllib.request.urlopen(req,timeout=25) as response: raw=response.read().decode("utf-8-sig"); source_status=response.status
                rows=list(csv.DictReader(io.StringIO(raw)))
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for row in rows:
                    def num(k):
                        v=row.get(k)
                        try: return int(v) if v not in (None,"") else None
                        except (ValueError,TypeError): return None
                    home=row.get("home"); away=row.get("away")
                    matches.append({"provider_match_id":None,"sport":"Football","competition":folder,"round":num("gw"),"date":row.get("date") or None,"time":row.get("time") or None,"homeTeam":home or None,"awayTeam":away or None,"home_score":num("ft_home"),"away_score":num("ft_away"),"halftime_home":num("ht_home"),"halftime_away":num("ht_away"),"home_shots":num("home_shots"),"away_shots":num("away_shots"),"home_corners":num("home_corners"),"away_corners":num("away_corners"),"home_yellow":num("home_yellow"),"away_yellow":num("away_yellow"),"goal_minutes":row.get("goal_minutes") or None,"status":"finished" if kind=="results" else "scheduled","source":"Open-Matchday","retrieved_at_utc":stamp})
                return self._send(200,{"provider":"Open-Matchday","status":"OK","league":folder,"kind":kind,"season":season,"count":len(matches),"matches":matches,"license":"Informational/non-commercial only","attribution_url":"https://github.com/oladeeayo/open-matchday","source_http_status":source_status,"retrieved_at_utc":stamp,"note":"Daily snapshot, not live. Blank values remain null. Use only for non-commercial personal/research purposes; upstream provider rights also apply."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"Open-Matchday","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"Open-Matchday","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/espn/scoreboard":
            sport=(query.get("sport",["soccer"])[0] or "soccer").strip().lower()
            league=(query.get("league",["eng.1"])[0] or "eng.1").strip().lower()
            day=(query.get("date",[""])[0] or "").strip()
            allowed={"soccer":{"eng.1","esp.1","ger.1","ita.1","fra.1","ned.1","por.1","uefa.champions","uefa.europa","usa.1","aut.1"},"basketball":{"nba","wnba","mens-college-basketball"},"hockey":{"nhl"},"football":{"nfl","college-football"},"baseball":{"mlb"}}
            if sport not in allowed or league not in allowed[sport]:
                return self._send(400,{"provider":"ESPN","status":"INVALID_SPORT_OR_LEAGUE","allowed":allowed})
            if day and (not day.isdigit() or len(day)!=8):
                return self._send(400,{"provider":"ESPN","status":"INVALID_DATE","expected":"YYYYMMDD"})
            endpoint="https://site.api.espn.com/apis/site/v2/sports/"+sport+"/"+league+"/scoreboard"+("?dates="+day if day else "")
            try:
                payload,headers=fetch_json(endpoint,{"Accept":"application/json","User-Agent":"Mozilla/5.0 WBR/1.0"})
                events=payload.get("events",[]) if isinstance(payload,dict) else []
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for ev in events:
                    comps=ev.get("competitions") or [{}]
                    comp=comps[0] if comps else {}
                    competitors=comp.get("competitors") or []
                    home=next((x for x in competitors if x.get("homeAway")=="home"),{})
                    away=next((x for x in competitors if x.get("homeAway")=="away"),{})
                    status=((comp.get("status") or {}).get("type") or {})
                    matches.append({"provider_match_id":ev.get("id"),"sport":sport,"competition":league,"kickoff_utc":ev.get("date"),"homeTeam":(home.get("team") or {}).get("displayName"),"awayTeam":(away.get("team") or {}).get("displayName"),"home_score":home.get("score"),"away_score":away.get("score"),"status":status.get("name"),"status_detail":status.get("detail"),"source":"ESPN","retrieved_at_utc":stamp})
                return self._send(200,{"provider":"ESPN","status":"OK","sport":sport,"league":league,"date":day or None,"count":len(matches),"matches":matches,"live_feed":False,"note":"Public ESPN site scoreboard endpoint, undocumented and subject to change. No odds. Verify ESPN terms before commercial reuse.","retrieved_at_utc":stamp})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"ESPN","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"ESPN","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openfootball/matches":
            league=(query.get("league",["de.1"])[0] or "de.1").strip().lower()
            season=(query.get("season",["2026-27"])[0] or "2026-27").strip()
            import re
            if not re.fullmatch(r"[a-z]{2}\.[0-9]{1,2}",league) or season not in ("2026-27","2026"):
                return self._send(400,{"provider":"OpenFootball","status":"INVALID_PARAMETERS","allowed_seasons":["2026-27","2026"]})
            try:
                payload,headers=fetch_json("https://raw.githubusercontent.com/openfootball/football.json/master/"+season+"/"+league+".json",{"Accept":"application/json","User-Agent":"WBR/1.0"})
                raw=payload.get("matches",[]) if isinstance(payload,dict) else []
                if not isinstance(raw,list): return self._send(502,{"provider":"OpenFootball","status":"UNEXPECTED_RESPONSE"})
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for x in raw:
                    if not isinstance(x,dict): continue
                    score=x.get("score") if isinstance(x.get("score"),dict) else {}
                    ft=score.get("ft") if isinstance(score,dict) else None
                    ht=score.get("ht") if isinstance(score,dict) else None
                    kickoff=(x.get("date") or "")+("T"+x.get("time") if x.get("time") else "")
                    matches.append({"provider_match_id":None,"sport":"Football","competition_name":payload.get("name"),"season":season,"round":x.get("round"),"kickoff_local":kickoff or None,"homeTeam":x.get("team1"),"awayTeam":x.get("team2"),"home_score":ft[0] if isinstance(ft,list) and len(ft)>1 else None,"away_score":ft[1] if isinstance(ft,list) and len(ft)>1 else None,"halftime_score":str(ht[0])+":"+str(ht[1]) if isinstance(ht,list) and len(ht)>1 else None,"status":"finished" if isinstance(ft,list) and len(ft)>1 else "scheduled","source":"OpenFootball","retrieved_at_utc":stamp})
                return self._send(200,{"provider":"OpenFootball","status":"OK","league":league,"season":season,"competition":payload.get("name"),"count":len(matches),"matches":matches,"license":"CC0-1.0","retrieved_at_utc":stamp,"note":"Public-domain fixture/results data; no live scores, odds, lineups or injuries. Match IDs are not supplied by this dataset."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenFootball","status":"HTTP_ERROR","http_status":e.code,"message":e.read(400).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenFootball","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/sporting-events/matches":
            dataset=(query.get("dataset",["football"])[0] or "football").strip().lower()
            allowed={"football","basketball","nba","ice-hockey","nhl-ice-hockey","american-football","college-football","nfl","mlb","baseball","premier-league","la-liga","serie-a","bundesliga","ligue-1","nations-league","champions-league","europa-league","fifa-world-cup","tennis","golf","mma","rugby-union","motorsport","winter-sports","cricket","formula-1","athletics","cycling","nascar","six-nations","darts","snooker","boxing","motogp","fa-cup","esports","march-madness","the-ashes","wrc","conference-league","indycar","ipl","pdc-world-championship","wimbledon","le-mans","swimming","rugby-league","super-bowl","cheltenham-festival","grand-national","vuelta-a-espana","tour-de-france","australian-open","the-masters","world-athletics-championships","premier-league-darts"}
            if dataset not in allowed: return self._send(400,{"provider":"Sporting Events","status":"INVALID_DATASET","allowed":sorted(allowed)})
            try:
                payload,headers=fetch_json("https://sporting-events.org/data/"+dataset+".json",{"Accept":"application/json","User-Agent":"WBR/1.0"})
                raw=payload.get("events",payload.get("matches",payload.get("data",[]))) if isinstance(payload,dict) else payload
                if not isinstance(raw,list): return self._send(502,{"provider":"Sporting Events","status":"UNEXPECTED_RESPONSE","message":"Expected events array"})
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for x in raw:
                    if not isinstance(x,dict): continue
                    home=x.get("home_team") or x.get("homeTeam")
                    away=x.get("away_team") or x.get("awayTeam")
                    matches.append({"provider_match_id":x.get("match") or x.get("id"),"sport":dataset,"competition_name":x.get("competition") or x.get("league") or dataset,"kickoff_utc":(x.get("date_utc") or "")+("T"+x.get("time_utc")+"Z" if x.get("time_utc") else "Z") if x.get("date_utc") else None,"homeTeam":home,"awayTeam":away,"fixture":x.get("fixture"),"city":x.get("city"),"country":x.get("country"),"status":x.get("status"),"event_url":x.get("url"),"source":"Sporting Events","retrieved_at_utc":stamp})
                return self._send(200,{"provider":"Sporting Events","status":"OK","dataset":dataset,"count":len(matches),"matches":matches,"license":"Free personal and commercial use with attribution","attribution_url":"https://sporting-events.org/data/","retrieved_at_utc":stamp,"note":"Fixture/context dataset; not a live-score or odds feed. Blank team fields are retained as null."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"Sporting Events","status":"HTTP_ERROR","http_status":e.code,"message":e.read(400).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"Sporting Events","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/sportsevents24/events":
            # Public multi-sport fixtures source. One country + sport (or one tournament) per request.
            from urllib.parse import urlencode
            country=(query.get("country",[""])[0] or "").strip().upper()
            sport_id=(query.get("sport_id",["1"])[0] or "1").strip()
            tournament_id=(query.get("tournament_id",[""])[0] or "").strip()
            limit=(query.get("limit",["100"])[0] or "100").strip()
            cursor=(query.get("cursor",[""])[0] or "").strip()
            if not tournament_id and (len(country)!=2 or not country.isalpha()):
                return self._send(400,{"provider":"SportsEvents24","status":"INVALID_SCOPE","required":"country=2-letter ISO code and sport_id, or tournament_id"})
            if not sport_id.isdigit() or not limit.isdigit() or int(limit)<1 or int(limit)>100:
                return self._send(400,{"provider":"SportsEvents24","status":"INVALID_PARAMETERS","allowed_sport_ids":{"football":1,"basketball":2,"ice_hockey":3,"volleyball":4,"rugby":5,"handball":6,"floorball":7,"baseball":8,"american_football":9,"cricket":11,"field_hockey":13,"water_polo":14,"netball":20,"australian_rules":21,"lacrosse":22,"inline_hockey":25,"futsal":27,"softball":42,"bandy":66,"beach_soccer":68},"max_limit":100})
            params={"sport_id":sport_id,"limit":limit}
            if tournament_id: params["tournament_id"]=tournament_id
            else: params["country"]=country
            for key in ("from","to","updated_since"):
                value=(query.get(key,[""])[0] or "").strip()
                if value: params[key]=value
            if cursor: params["cursor"]=cursor
            try:
                payload,headers=fetch_json("https://sportsevents24.com/api/v1/events?"+urlencode(params),{"Accept":"application/json","User-Agent":"WBR/1.0"})
                raw=payload.get("data",[]) if isinstance(payload,dict) else []
                if not isinstance(raw,list):
                    return self._send(502,{"provider":"SportsEvents24","status":"UNEXPECTED_RESPONSE"})
                stamp=datetime.now(timezone.utc).isoformat()
                sport_names={"1":"Football","2":"Basketball","3":"Ice Hockey","4":"Volleyball","5":"Rugby","6":"Handball","7":"Floorball","8":"Baseball","9":"American Football","11":"Cricket","13":"Field Hockey","14":"Water Polo","20":"Netball","21":"Australian Rules Football","22":"Lacrosse","25":"Inline Hockey","27":"Futsal","42":"Softball","66":"Bandy","68":"Beach Soccer"}
                normalized=[]
                for x in raw:
                    if not isinstance(x,dict): continue
                    result=x.get("result")
                    normalized.append({
                        "id":x.get("id"),"provider_match_id":x.get("id"),
                        "sport":sport_names.get(str(x.get("sportId") or sport_id)),
                        "sport_id":x.get("sportId") or int(sport_id),
                        "competition_name":x.get("tournament"),
                        "tournament_id":x.get("tournamentId"),
                        "country":x.get("country"),
                        "homeTeam":x.get("teamHome"),"awayTeam":x.get("teamAway"),
                        "kickoff_utc":x.get("startsAt"),
                        "local_kickoff":x.get("localStartsAt"),
                        "timezone":x.get("timeZone"),
                        "venue":x.get("location"),
                        "score":result if result else None,
                        "status":x.get("category"),
                        "updated_at":x.get("updatedAt"),
                        "source":"SportsEvents24","retrieved_at_utc":stamp
                    })
                existing=read_json("sportsevents24_matches.json",{"matches":[]})
                old=existing.get("matches",[]) if isinstance(existing,dict) else []
                by_id={str(m.get("provider_match_id")):m for m in old if isinstance(m,dict) and m.get("provider_match_id") is not None}
                for m in normalized: by_id[str(m["provider_match_id"])]=m
                saved=list(by_id.values())
                write_json("sportsevents24_matches.json",{"provider":"SportsEvents24","retrieved_at_utc":stamp,"matches":saved})
                usage=payload.get("usage",{}) if isinstance(payload,dict) else {}
                return self._send(200,{"provider":"SportsEvents24","status":"OK","scope":{"country":country or None,"sport_id":int(sport_id),"tournament_id":int(tournament_id) if tournament_id.isdigit() else None},"count":len(normalized),"saved_total":len(saved),"events":normalized,"nextCursor":payload.get("nextCursor"),"usage":usage,"retrieved_at_utc":stamp,"note":"This source requires country+sport or tournament scope; this response is not a complete worldwide event census."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"SportsEvents24","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"SportsEvents24","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/sportsevents24/tournaments":
            from urllib.parse import urlencode
            country=(query.get("country",[""])[0] or "").strip().upper()
            sport_id=(query.get("sport_id",["1"])[0] or "1").strip()
            if len(country)!=2 or not country.isalpha() or not sport_id.isdigit():
                return self._send(400,{"provider":"SportsEvents24","status":"INVALID_SCOPE","required":"country=2-letter ISO code and numeric sport_id"})
            try:
                payload,headers=fetch_json("https://sportsevents24.com/api/v1/tournaments?"+urlencode({"country":country,"sport_id":sport_id,"limit":100}),{"Accept":"application/json","User-Agent":"WBR/1.0"})
                items=payload.get("data",[]) if isinstance(payload,dict) else []
                return self._send(200,{"provider":"SportsEvents24","status":"OK","country":country,"sport_id":int(sport_id),"count":len(items) if isinstance(items,list) else None,"tournaments":items,"usage":payload.get("usage") if isinstance(payload,dict) else None})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"SportsEvents24","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"SportsEvents24","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/leagues/catalog":
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not season.isdigit() or len(season)!=4:
                return self._send(400,{"error":"invalid_season"})
            stamp=datetime.now(timezone.utc).isoformat()
            catalog=[]
            sources=[]
            # OpenLigaDB: public football league catalogue for the requested calendar season.
            try:
                leagues, _=fetch_json("https://api.openligadb.de/getavailableleagues/"+season,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                if isinstance(leagues,list):
                    for x in leagues:
                        if isinstance(x,dict):
                            catalog.append({"provider":"OpenLigaDB","provider_id":x.get("leagueId"),"name":x.get("leagueName"),"slug":x.get("leagueShortcut"),"season":x.get("leagueSeason"),"sport":(x.get("sport") or {}).get("sportName","Football"),"country":None,"coverage":"catalogue_listed"})
                    sources.append({"provider":"OpenLigaDB","status":"OK","count":len(leagues)})
                else: sources.append({"provider":"OpenLigaDB","status":"UNEXPECTED_RESPONSE"})
            except urllib.error.HTTPError as e:
                sources.append({"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code})
            except Exception as e:
                sources.append({"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:200]})
            # StatsHawk: cross-sport global competition index; requires a server-side key.
            if STATSHAWK_KEY:
                try:
                    payload, headers=fetch_json("https://api.statshawk.ai/v1/competitions?page=0&per_page=1000",{"X-API-Key":STATSHAWK_KEY,"Accept":"application/json"})
                    data=payload.get("data",{}) if isinstance(payload,dict) else {}
                    items=data.get("items",[]) if isinstance(data,dict) else []
                    if isinstance(items,list):
                        for x in items:
                            if isinstance(x,dict):
                                catalog.append({"provider":"StatsHawk","provider_id":x.get("id"),"name":x.get("name"),"slug":x.get("slug"),"season":season,"sport":x.get("sport"),"kind":x.get("kind"),"country":None,"coverage":"catalogue_listed"})
                        sources.append({"provider":"StatsHawk","status":"OK","count":len(items),"total":data.get("total"),"page":data.get("page"),"per_page":data.get("per_page"),"quota_remaining":headers.get("X-RateLimit-Remaining")})
                    else: sources.append({"provider":"StatsHawk","status":"UNEXPECTED_RESPONSE"})
                except urllib.error.HTTPError as e:
                    sources.append({"provider":"StatsHawk","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
                except Exception as e:
                    sources.append({"provider":"StatsHawk","status":"ERROR","message":str(e)[:200]})
            else:
                sources.append({"provider":"StatsHawk","status":"MISSING_SERVER_SECRET","required_env":"STATSHAWK_API_KEY"})
            # API-Football: season-filtered catalogue. One request per catalogue refresh.
            if APIFOOTBALL_KEY:
                try:
                    payload, headers=fetch_json("https://v3.football.api-sports.io/leagues?season="+season,{"x-apisports-key":APIFOOTBALL_KEY,"Accept":"application/json"})
                    errors=payload.get("errors") if isinstance(payload,dict) else None
                    if errors:
                        sources.append({"provider":"API-Football","status":"API_ERROR","message":str(errors)[:200]})
                    else:
                        raw=payload.get("response",[]) if isinstance(payload,dict) else []
                        added=0
                        for x in raw if isinstance(raw,list) else []:
                            if not isinstance(x,dict): continue
                            league=x.get("league") or {}; country=x.get("country") or {}
                            catalog.append({"provider":"API-Football","provider_id":league.get("id"),"name":league.get("name"),"slug":str(league.get("id")) if league.get("id") is not None else None,"season":season,"sport":"Football","country":country.get("name"),"kind":league.get("type"),"logo":league.get("logo"),"coverage":(x.get("seasons") or [{}])[-1].get("coverage") if x.get("seasons") else None})
                            added+=1
                        sources.append({"provider":"API-Football","status":"OK","count":added,"requests_remaining":headers.get("x-ratelimit-requests-remaining"),"minute_requests_remaining":headers.get("x-ratelimit-remaining")})
                except urllib.error.HTTPError as e:
                    sources.append({"provider":"API-Football","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
                except Exception as e:
                    sources.append({"provider":"API-Football","status":"ERROR","message":str(e)[:200]})
            else:
                sources.append({"provider":"API-Football","status":"MISSING_SERVER_SECRET","required_env":"APIFOOTBALL_API_KEY"})
            # football-data.org: competitions visible to this account/plan.
            if FOOTBALL_DATA_KEY:
                try:
                    payload, headers=fetch_json("https://api.football-data.org/v4/competitions",{"X-Auth-Token":FOOTBALL_DATA_KEY,"Accept":"application/json"})
                    raw=payload.get("competitions",[]) if isinstance(payload,dict) else []
                    added=0
                    for x in raw if isinstance(raw,list) else []:
                        if not isinstance(x,dict): continue
                        area=x.get("area") or {}; current=x.get("currentSeason") or {}
                        start=str(current.get("startDate") or "")
                        if start and start[:4]!=season: continue
                        catalog.append({"provider":"football-data.org","provider_id":x.get("id"),"name":x.get("name"),"slug":x.get("code"),"season":season if start else None,"sport":"Football","country":area.get("name"),"kind":x.get("type"),"logo":x.get("emblem"),"coverage":"account_accessible"})
                        added+=1
                    sources.append({"provider":"football-data.org","status":"OK","count":added,"account_competitions":len(raw) if isinstance(raw,list) else None,"note":"Only competitions visible to this API account are listed."})
                except urllib.error.HTTPError as e:
                    sources.append({"provider":"football-data.org","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
                except Exception as e:
                    sources.append({"provider":"football-data.org","status":"ERROR","message":str(e)[:200]})
            else:
                sources.append({"provider":"football-data.org","status":"MISSING_SERVER_SECRET","required_env":"FOOTBALL_DATA_ORG_API_KEY"})
            # Sportmonks: first catalogue page only to avoid unbounded quota usage.
            if SPORTMONKS_TOKEN:
                try:
                    payload, headers=fetch_json("https://api.sportmonks.com/v3/football/leagues?api_token="+SPORTMONKS_TOKEN+"&per_page=100",{"Accept":"application/json"})
                    raw=payload.get("data",[]) if isinstance(payload,dict) else []
                    added=0
                    for x in raw if isinstance(raw,list) else []:
                        if not isinstance(x,dict): continue
                        catalog.append({"provider":"Sportmonks","provider_id":x.get("id"),"name":x.get("name"),"slug":str(x.get("id")) if x.get("id") is not None else None,"season":season,"sport":"Football","country":None,"kind":None,"logo":None,"coverage":"subscription_accessible"})
                        added+=1
                    pagination=payload.get("pagination",{}) if isinstance(payload,dict) else {}
                    sources.append({"provider":"Sportmonks","status":"OK","count":added,"has_more":pagination.get("has_more") if isinstance(pagination,dict) else None,"note":"First page only; additional pages are not yet fetched."})
                except urllib.error.HTTPError as e:
                    sources.append({"provider":"Sportmonks","status":"HTTP_ERROR","http_status":e.code,"message":e.read(300).decode("utf-8","replace")})
                except Exception as e:
                    sources.append({"provider":"Sportmonks","status":"ERROR","message":str(e)[:200]})
            else:
                sources.append({"provider":"Sportmonks","status":"MISSING_SERVER_SECRET","required_env":"SPORTMONKS_API_TOKEN"})
            # Canonicalize same competition across providers; preserve every provider identity.
            import re, unicodedata
            unique={}
            for x in catalog:
                raw_name=str(x.get("name") or x.get("slug") or x.get("provider_id") or "")
                norm=unicodedata.normalize("NFKD",raw_name).encode("ascii","ignore").decode().lower()
                norm=re.sub(r"[^a-z0-9]+","",norm)
                country=str(x.get("country") or "").strip().lower()
                sport=str(x.get("sport") or "").strip().lower()
                comp_season=str(x.get("season") or season)
                key=(norm,country,sport,comp_season) if norm else (x.get("provider"),str(x.get("provider_id")))
                if key not in unique:
                    unique[key]={**x,"providers":[x.get("provider")],"provider_ids":{x.get("provider"):x.get("provider_id")},"provider_slugs":{x.get("provider"):x.get("slug")}}
                else:
                    item=unique[key]
                    provider=x.get("provider")
                    if provider not in item["providers"]: item["providers"].append(provider)
                    item["provider_ids"][provider]=x.get("provider_id")
                    item["provider_slugs"][provider]=x.get("slug")
                    if provider=="StatsHawk" and x.get("slug"): item["statshawk_slug"]=x.get("slug")
                    if not item.get("country") and x.get("country"): item["country"]=x.get("country")
                    if not item.get("logo") and x.get("logo"): item["logo"]=x.get("logo")
            items=list(unique.values())
            for item in items:
                if "StatsHawk" in item.get("providers",[]) and item.get("provider")!="StatsHawk":
                    item["statshawk_slug"]=item.get("provider_slugs",{}).get("StatsHawk")
            return self._send(200,{"status":"OK","season":season,"count":len(items),"competitions":items,"sources":sources,"retrieved_at_utc":stamp,"note":"Catalogue coverage is limited to competitions listed by the responding providers; absence does not mean a league does not exist. Availability of fixtures/stats is a separate check."})
        if path == "/api/v1/statshawk/contests":
            competition=(query.get("competition",[""])[0] or "").strip().lower()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not STATSHAWK_KEY:
                return self._send(503,{"provider":"StatsHawk","status":"MISSING_SERVER_SECRET","required_env":"STATSHAWK_API_KEY"})
            import re
            if not re.fullmatch(r"[a-z0-9_-]{2,80}",competition) or not season.isdigit() or len(season)!=4:
                return self._send(400,{"provider":"StatsHawk","status":"INVALID_COMPETITION_OR_SEASON","required":"competition slug and four-digit season"})
            try:
                endpoint="https://api.statshawk.ai/v1/competitions/"+competition+"/editions/"+season+"/contests"
                payload,headers=fetch_json(endpoint,{"X-API-Key":STATSHAWK_KEY,"Accept":"application/json"})
                data=payload.get("data",{}) if isinstance(payload,dict) else {}
                raw=data.get("items",[]) if isinstance(data,dict) else []
                if not isinstance(raw,list):
                    return self._send(502,{"provider":"StatsHawk","status":"UNEXPECTED_RESPONSE","message":"Expected data.items array"})
                stamp=datetime.now(timezone.utc).isoformat()
                # Resolve team IDs from the season roster (one extra API call, not one call per match).
                team_names={}
                try:
                    team_payload,team_headers=fetch_json("https://api.statshawk.ai/v1/competitions/"+competition+"/editions/"+season+"/teams",{"X-API-Key":STATSHAWK_KEY,"Accept":"application/json"})
                    team_data=team_payload.get("data",{}) if isinstance(team_payload,dict) else {}
                    for team in team_data.get("items",[]) if isinstance(team_data,dict) else []:
                        if isinstance(team,dict) and team.get("id") and team.get("name"):
                            team_names[team["id"]]=team["name"]
                except Exception:
                    team_headers={}
                contests=[]
                for x in raw:
                    if not isinstance(x,dict): continue
                    score=x.get("score") if isinstance(x.get("score"),dict) else {}
                    home_id=x.get("home_team") or x.get("homeTeam") or x.get("home")
                    away_id=x.get("away_team") or x.get("awayTeam") or x.get("away")
                    home_name=x.get("home_team_name") or x.get("home_name") or team_names.get(home_id)
                    away_name=x.get("away_team_name") or x.get("away_name") or team_names.get(away_id)
                    contests.append({
                        "id":x.get("id"),"provider_match_id":x.get("id"),
                        "competition_id":x.get("competition"),"edition_id":x.get("edition"),
                        "sport":x.get("sport"),"competition":competition,
                        "kickoff_utc":x.get("kickoff") or x.get("starts_at"),
                        "home_team_id":home_id,"away_team_id":away_id,
                        "homeTeam":home_name,"awayTeam":away_name,
                        "home_score":score.get("home"),"away_score":score.get("away"),
                        "score":str(score.get("home"))+":"+str(score.get("away")) if score.get("home") is not None and score.get("away") is not None else None,
                        "status":x.get("status"),"source":"StatsHawk","retrieved_at_utc":stamp
                    })
                return self._send(200,{"provider":"StatsHawk","status":"OK","competition":competition,"season":season,"count":len(contests),"total":data.get("total") if isinstance(data,dict) else None,"contests":contests,"quota_remaining":headers.get("X-RateLimit-Remaining"),"retrieved_at_utc":stamp,"note":"An empty list means this edition returned no contests; it does not prove the competition is unsupported."})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"StatsHawk","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"StatsHawk","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/sportscore/live":
            sport = (query.get("sport", ["football"])[0] or "football").lower()
            if sport not in ("football", "basketball", "cricket", "tennis"):
                return self._send(400, {"error":"invalid_sport","allowed":["football","basketball","cricket","tennis"]})
            requested_date = query.get("date", [datetime.now(timezone.utc).date().isoformat()])[0]
            status_filter = (query.get("status", ["live"])[0] or "live").lower()
            if status_filter not in ("live", "finished", "upcoming"):
                return self._send(400, {"error":"invalid_status","allowed":["live","finished","upcoming"]})
            try:
                from urllib.parse import urlencode
                params = {"sport":sport,"date":requested_date,"status":status_filter,"limit":50}
                payload, headers = fetch_json("https://sportscore.com/api/v1/fixtures/?" + urlencode(params), {"Accept":"application/json","User-Agent":"WBR/1.0"})
                raw = payload.get("matches", payload.get("data", [])) if isinstance(payload,dict) else payload
                if not isinstance(raw,list):
                    return self._send(502, {"provider":"SportScore","status":"UNEXPECTED_RESPONSE","message":"Expected matches array","response_type":type(payload).__name__})
                stamp = datetime.now(timezone.utc).isoformat()
                matches = []
                for x in raw:
                    if not isinstance(x,dict): continue
                    hs=x.get("home_score"); aw=x.get("away_score")
                    slug=x.get("slug") or x.get("match_slug")
                    match_status=(x.get("status") or "unknown").lower()
                    # Strictly enforce the requested status; never label recent finished games as live.
                    if status_filter == "live" and match_status not in ("live","in_play","in-play","1h","2h","ht","extra_time","penalties"):
                        continue
                    matches.append({"id":slug,"provider_match_id":slug,"slug":slug,"sport":sport,"competition":x.get("competition"),"homeTeam":x.get("home"),"awayTeam":x.get("away"),"home_score":hs,"away_score":aw,"score":str(hs)+":"+str(aw) if hs is not None and aw is not None else None,"status":match_status,"status_text":x.get("status_text"),"kickoff_utc":x.get("time"),"home_logo":x.get("home_logo"),"away_logo":x.get("away_logo"),"source":"SportScore","retrieved_at_utc":stamp})
                return self._send(200, {"provider":"SportScore","status":"OK","sport":sport,"date":requested_date,"status_filter":status_filter,"count":len(matches),"retrieved_at_utc":stamp,"attribution_required":True,"attribution_url":"https://sportscore.com/","matches":matches,"note":"Only matches matching the requested status are returned. Empty live list means no live matches were reported for this UTC date."})
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"SportScore","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"SportScore","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/leagues":
            try:
                season = query.get("season", ["2026"])[0]
                payload, headers = fetch_json("https://api.openligadb.de/getavailableleagues/" + season, {"Accept":"application/json","User-Agent":"WBR/1.0"})
                if not isinstance(payload,list): return self._send(502, {"provider":"OpenLigaDB","status":"UNEXPECTED_RESPONSE"})
                return self._send(200, {"provider":"OpenLigaDB","status":"OK","season":season,"count":len(payload),"leagues":payload,"auth_required":False,"rate_limit_note":"60 requests/minute per IP; use last-change polling."})
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/matchday":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            group=(query.get("group",["1"])[0] or "1").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4 or not group.isdigit():
                return self._send(400,{"error":"invalid_league_season_or_group"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getmatchdata/"+league+"/"+season+"/"+group,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                if not isinstance(payload,list): return self._send(502,{"provider":"OpenLigaDB","status":"UNEXPECTED_RESPONSE"})
                stamp=datetime.now(timezone.utc).isoformat()
                matches=[]
                for x in payload:
                    if not isinstance(x,dict): continue
                    t1=x.get("team1") or {}; t2=x.get("team2") or {}; results=x.get("matchResults") or []
                    ft=next((z for z in reversed(results) if z.get("resultTypeID")==2),None)
                    ht=next((z for z in reversed(results) if z.get("resultTypeID")==1),None)
                    matches.append({"id":x.get("matchID"),"provider_match_id":x.get("matchID"),"sport":"Football","competition_name":x.get("leagueName"),"league_shortcut":x.get("leagueShortcut"),"season":x.get("leagueSeason"),"round":(x.get("group") or {}).get("groupName"),"group_order_id":(x.get("group") or {}).get("groupOrderID"),"kickoff_utc":x.get("matchDateTimeUTC") or x.get("matchDateTime"),"homeTeam":t1.get("teamName"),"awayTeam":t2.get("teamName"),"home_team_id":t1.get("teamId"),"away_team_id":t2.get("teamId"),"home_logo":t1.get("teamIconUrl"),"away_logo":t2.get("teamIconUrl"),"score":str(ft.get("pointsTeam1"))+":"+str(ft.get("pointsTeam2")) if ft else None,"halftime_score":str(ht.get("pointsTeam1"))+":"+str(ht.get("pointsTeam2")) if ht else None,"status":"finished" if x.get("matchIsFinished") else "scheduled","source":"OpenLigaDB","retrieved_at_utc":stamp})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"group":group,"count":len(matches),"matches":matches,"retrieved_at_utc":stamp})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/last-changed":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            group=(query.get("group",["1"])[0] or "1").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4 or not group.isdigit():
                return self._send(400,{"error":"invalid_league_season_or_group"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getlastchangedate/"+league+"/"+season+"/"+group,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"group":group,"last_changed":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/matches":
            league = (query.get("league", ["bl1"])[0] or "bl1").strip()
            season = (query.get("season", ["2026"])[0] or "2026").strip()
            match_filter = (query.get("filter", ["all"])[0] or "all").lower()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4:
                return self._send(400, {"error":"invalid_league_or_season"})
            if match_filter not in ("all","upcoming","finished"):
                return self._send(400, {"error":"invalid_filter","allowed":["all","upcoming","finished"]})
            try:
                payload, headers = fetch_json("https://api.openligadb.de/getmatchdata/"+league+"/"+season, {"Accept":"application/json","User-Agent":"WBR/1.0"})
                if not isinstance(payload,list): return self._send(502, {"provider":"OpenLigaDB","status":"UNEXPECTED_RESPONSE"})
                stamp = datetime.now(timezone.utc).isoformat()
                now = datetime.now(timezone.utc)
                matches=[]
                for x in payload:
                    if not isinstance(x,dict): continue
                    t1=x.get("team1") or {}; t2=x.get("team2") or {}
                    results=x.get("matchResults") or []
                    ft=next((r for r in reversed(results) if r.get("resultTypeID")==2),None)
                    ht=next((r for r in reversed(results) if r.get("resultTypeID")==1),None)
                    kickoff=x.get("matchDateTimeUTC") or x.get("matchDateTime")
                    finished=bool(x.get("matchIsFinished"))
                    try:
                        dt=datetime.fromisoformat(kickoff.replace("Z","+00:00")) if kickoff else None
                    except Exception: dt=None
                    status="finished" if finished else "scheduled"  # OpenLigaDB does not expose reliable in-play state; never infer live from kickoff time.
                    if match_filter=="upcoming" and (finished or not dt or dt<=now): continue
                    if match_filter=="finished" and not finished: continue
                    matches.append({"id":x.get("matchID"),"provider_match_id":x.get("matchID"),"sport":"Football","competition_name":x.get("leagueName"),"league_shortcut":x.get("leagueShortcut"),"season":x.get("leagueSeason"),"round":(x.get("group") or {}).get("groupName"),"kickoff_utc":kickoff,"homeTeam":t1.get("teamName"),"awayTeam":t2.get("teamName"),"home_team_id":t1.get("teamId"),"away_team_id":t2.get("teamId"),"home_logo":t1.get("teamIconUrl"),"away_logo":t2.get("teamIconUrl"),"score":str(ft.get("pointsTeam1"))+":"+str(ft.get("pointsTeam2")) if ft else None,"halftime_score":str(ht.get("pointsTeam1"))+":"+str(ht.get("pointsTeam2")) if ht else None,"status":status,"source":"OpenLigaDB","retrieved_at_utc":stamp})
                matches.sort(key=lambda m: m.get("kickoff_utc") or "")
                return self._send(200, {"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"filter":match_filter,"count":len(matches),"retrieved_at_utc":stamp,"matches":matches,"auth_required":False})
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/table":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4:
                return self._send(400, {"error":"invalid_league_or_season"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getbltable/"+league+"/"+season,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"count":len(payload) if isinstance(payload,list) else None,"table":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/current-group":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            if not league.replace("_","").isalnum(): return self._send(400,{"error":"invalid_league"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getcurrentgroup/"+league,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"current_group":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/groups":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4: return self._send(400,{"error":"invalid_league_or_season"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getavailablegroups/"+league+"/"+season,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"count":len(payload) if isinstance(payload,list) else None,"groups":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/goalscorers":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4: return self._send(400,{"error":"invalid_league_or_season"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getgoalgetters/"+league+"/"+season,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"count":len(payload) if isinstance(payload,list) else None,"goalscorers":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/next-match":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            if not league.replace("_","").isalnum(): return self._send(400,{"error":"invalid_league"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getnextmatchbyleagueshortcut/"+league,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"match":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})
        if path == "/api/v1/openligadb/teams":
            league=(query.get("league",["bl1"])[0] or "bl1").strip()
            season=(query.get("season",["2026"])[0] or "2026").strip()
            if not league.replace("_","").isalnum() or not season.isdigit() or len(season)!=4: return self._send(400,{"error":"invalid_league_or_season"})
            try:
                payload, headers=fetch_json("https://api.openligadb.de/getavailableteams/"+league+"/"+season,{"Accept":"application/json","User-Agent":"WBR/1.0"})
                return self._send(200,{"provider":"OpenLigaDB","status":"OK","league":league,"season":season,"count":len(payload) if isinstance(payload,list) else None,"teams":payload,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()})
            except urllib.error.HTTPError as e:
                return self._send(e.code,{"provider":"OpenLigaDB","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502,{"provider":"OpenLigaDB","status":"ERROR","message":str(e)[:250]})

        if path == "/api-check":
            raw = "<!doctype html><html lang='de'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>WBR API-Prüfung</title><style>body{font:16px system-ui;background:#08111f;color:#eef;padding:20px;max-width:850px;margin:auto}section{background:#132238;border:1px solid #29405e;border-radius:12px;padding:16px;margin:14px 0}button{padding:12px 18px;background:#27d4c5;border:0;border-radius:8px;font-weight:bold}pre{white-space:pre-wrap;overflow-wrap:anywhere}.ok{color:#a7e66f}.bad{color:#ff8585}</style><h1>WBR · API-Prüfung</h1><p>Diese Seite läuft direkt auf demselben Backend. Kein Cross-Origin-Aufruf von GitHub Pages.</p><section><button onclick='run()'>Jetzt prüfen</button><p id='health'>Warte auf Prüfung.</p></section><section><h2>Provider-Status</h2><pre id='out'>Noch keine Daten.</pre></section><script>async function run(){let h=document.getElementById('health'),o=document.getElementById('out');h.textContent='Prüfe Health …';o.textContent='Lade Provider …';try{let a=await fetch('/health',{cache:'no-store'});let at=await a.text();if(!a.ok)throw Error('Health HTTP '+a.status+': '+at);h.innerHTML='<span class=ok>Backend erreichbar · HTTP '+a.status+'</span>';let b=await fetch('/api/v1/providers',{cache:'no-store'});let bt=await b.text();if(!b.ok)throw Error('Provider HTTP '+b.status+': '+bt);let d=JSON.parse(bt);o.textContent=JSON.stringify(d,null,2)}catch(e){h.innerHTML='<span class=bad>Fehler: '+e.message+'</span>';o.textContent='Provider-Prüfung fehlgeschlagen.'}}run();</script></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return
        routes = {
            "/": lambda: {"status":"ok","service":"wbr-backend","message":"WBR backend is running","checks":{"health":"/health","providers":"/api/v1/providers","matches":"/api/v1/matches","odds":"/api/v1/odds","sportscore_matches":"/api/v1/sportscore/matches"}},
            "/health": lambda: {"status":"ok","service":"wbr-backend","mode":"provider-ready","data_dir_exists":DATA.exists()},
            "/api/v1/health": lambda: {"status":"ok","service":"wbr-backend","mode":"provider-ready","data_dir_exists":DATA.exists()},
            "/api/v1/sources": lambda: read_json("sources.json", []),
            "/api/v1/matches": lambda: read_json("matches.json", []),
            "/api/v1/odds": lambda: read_json("odds.json", []),
            "/api/v1/forecasts": lambda: read_json("forecasts.json", []),
            "/api/v1/providers": lambda: provider_status(),
            "/api/v1/provider-status": lambda: provider_status(),
            "/api/v1/puntersedge/sports": lambda: read_json("puntersedge_sports.json", {"status":"NOT_IMPORTED","sports":[]}),
            "/api/v1/sportscore/matches": lambda: read_json("sportscore_matches.json", {"status":"NOT_IMPORTED","matches":[]}),
            "/api/v1/matches/canonical": lambda: read_json("canonical_matches.json", []),
            "/api/v1/odds/matched": lambda: {"odds":read_json("matched_odds.json", []),"matched_count":0,"unmatched_count":0,"status":"NO_IMPORTED_DATA"},
        }
        if path not in routes: return self._send(404, {"error":"not_found","path":path})
        return self._send(200, routes[path]())

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/api/v1/sportscore/sync":
            if not SYNC_TOKEN: return self._send(503, {"error":"sync_disabled"})
            if self.headers.get("X-WBR-Sync-Token","") != SYNC_TOKEN: return self._send(401, {"error":"unauthorized"})
            try:
                length = min(int(self.headers.get("Content-Length","0")), 4096)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return self._send(400, {"error":"invalid_json"})
            mode = str(body.get("mode","date")).lower()
            sport = str(body.get("sport","football")).lower()
            if mode not in ("date","live"): return self._send(400, {"error":"invalid_mode","allowed":["date","live"]})
            if sport not in ("football","basketball","cricket","tennis"):
                return self._send(400, {"error":"invalid_sport","allowed":["football","basketball","cricket","tennis"]})
            target = str(body.get("date") or date.today().isoformat())
            if mode == "date":
                try: date.fromisoformat(target)
                except ValueError: return self._send(400, {"error":"invalid_date"})
            from urllib.parse import urlencode
            params = {"sport":sport,"limit":200}
            if mode == "date":
                params["date"] = target
            else:
                params["status"] = "live"
            endpoint = "https://sportscore.com/api/v1/fixtures/?" + urlencode(params)
            headers_in = {"Accept":"application/json","User-Agent":"WBR/1.0 (sports data integration)"}
            if SPORTSCORE_KEY: headers_in["X-Api-Key"] = SPORTSCORE_KEY
            try:
                payload, headers = fetch_json(endpoint, headers_in)
                raw_matches = payload.get("matches", payload.get("data", [])) if isinstance(payload,dict) else payload
                if not isinstance(raw_matches,list):
                    return self._send(502, {"provider":"SportScore","status":"UNEXPECTED_RESPONSE","message":"Expected a list of fixtures; raw response was not imported."})
                stamp = datetime.now(timezone.utc).isoformat()
                normalized = []
                def pick(obj, *keys):
                    for key in keys:
                        value = obj.get(key) if isinstance(obj,dict) else None
                        if value is not None: return value
                    return None
                for item in raw_matches:
                    if not isinstance(item,dict): continue
                    home = pick(item,"home","home_team","homeTeam","home_name")
                    away = pick(item,"away","away_team","awayTeam","away_name")
                    home_score = pick(item,"home_score","homeScore")
                    away_score = pick(item,"away_score","awayScore")
                    status_value = pick(item,"status","status_text","state")
                    normalized.append({
                        "id":pick(item,"id","fixture_id","match_id","slug"),
                        "provider_match_id":pick(item,"id","fixture_id","match_id","slug"),
                        "sport":sport,"homeTeam":home,"awayTeam":away,
                        "home_score":home_score,"away_score":away_score,
                        "score":str(home_score)+":"+str(away_score) if home_score is not None and away_score is not None else None,
                        "status":status_value,"kickoff_utc":pick(item,"time","kickoff","kickoff_utc","start_time"),
                        "competition_name":pick(item,"competition","league","tournament"),
                        "source":"SportScore","retrieved_at_utc":stamp,"raw":item
                    })
                result = {"provider":"SportScore","status":"OK","mode":mode,"sport":sport,"date":target if mode=="date" else None,
                          "fixtures":len(normalized),"retrieved_at_utc":stamp,"attribution_required":True,
                          "api_key_configured":bool(SPORTSCORE_KEY)}
                write_json("sportscore_matches.json",{"status":"OK","provider":"SportScore","retrieved_at_utc":stamp,"mode":mode,"sport":sport,"matches":normalized,"attribution":"Powered by SportScore"})
                write_json("sportscore_last_sync.json",result)
                return self._send(200,result)
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"SportScore","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"SportScore","status":"ERROR","message":str(e)[:300]})
        if path == "/api/v1/apifootball/sync":
            if not APIFOOTBALL_KEY: return self._send(503, {"error":"provider_not_configured","provider":"API-Football"})
            if not SYNC_TOKEN: return self._send(503, {"error":"sync_disabled"})
            if self.headers.get("X-WBR-Sync-Token","") != SYNC_TOKEN: return self._send(401, {"error":"unauthorized"})
            try:
                length = min(int(self.headers.get("Content-Length","0")), 4096)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return self._send(400, {"error":"invalid_json"})
            mode = str(body.get("mode","date")).lower()
            if mode not in ("date","live","status"): return self._send(400, {"error":"invalid_mode"})
            if mode == "status":
                endpoint = "https://v3.football.api-sports.io/status"
            elif mode == "live":
                endpoint = "https://v3.football.api-sports.io/fixtures?live=all"
            else:
                target = str(body.get("date") or date.today().isoformat())
                try: date.fromisoformat(target)
                except ValueError: return self._send(400, {"error":"invalid_date"})
                endpoint = "https://v3.football.api-sports.io/fixtures?date=" + target + "&timezone=Europe%2FVienna"
            try:
                payload, headers = fetch_json(endpoint, {"x-apisports-key":APIFOOTBALL_KEY})
                errors = payload.get("errors") if isinstance(payload,dict) else None
                if errors:
                    return self._send(502, {"provider":"API-Football","status":"API_ERROR","errors":errors})
                response = payload.get("response",[]) if isinstance(payload,dict) else []
                stamp = datetime.now(timezone.utc).isoformat()
                if mode in ("date","live"):
                    normalized = []
                    for item in response if isinstance(response,list) else []:
                        fixture = item.get("fixture",{}) or {}
                        teams = item.get("teams",{}) or {}
                        goals = item.get("goals",{}) or {}
                        league = item.get("league",{}) or {}
                        status_obj = fixture.get("status",{}) or {}
                        normalized.append({
                            "id":fixture.get("id"),"fixture_id":fixture.get("id"),
                            "kickoff_utc":fixture.get("date"),
                            "sport":"Football","competition_name":league.get("name"),
                            "league_id":league.get("id"),"season":league.get("season"),
                            "country":league.get("country"),"round":league.get("round"),
                            "homeTeam":(teams.get("home") or {}).get("name"),
                            "home_team_id":(teams.get("home") or {}).get("id"),
                            "awayTeam":(teams.get("away") or {}).get("name"),
                            "away_team_id":(teams.get("away") or {}).get("id"),
                            "score":str(goals.get("home"))+":"+str(goals.get("away")) if goals.get("home") is not None and goals.get("away") is not None else None,
                            "status":status_obj.get("short"),"elapsed":status_obj.get("elapsed"),
                            "source":"API-Football","provider_match_id":fixture.get("id"),
                            "retrieved_at_utc":stamp
                        })
                    write_json("matches.json",normalized)
                result = {"provider":"API-Football","status":"OK","mode":mode,"fixtures":len(response) if isinstance(response,list) else None,
                          "requests_remaining":headers.get("x-ratelimit-requests-remaining"),
                          "minute_requests_remaining":headers.get("x-ratelimit-remaining"),
                          "account":payload.get("response") if mode=="status" and isinstance(payload,dict) else None,
                          "retrieved_at_utc":stamp}
                write_json("apifootball_last_sync.json",result)
                return self._send(200,result)
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"API-Football","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"API-Football","status":"ERROR","message":str(e)[:300]})
        if path == "/api/v1/puntersedge/odds":
            if not PUNTERSEDGE_KEY: return self._send(503, {"error":"provider_not_configured"})
            if not SYNC_TOKEN: return self._send(503, {"error":"sync_disabled"})
            if self.headers.get("X-WBR-Sync-Token","") != SYNC_TOKEN: return self._send(401, {"error":"unauthorized"})
            try:
                length = min(int(self.headers.get("Content-Length","0")), 4096)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return self._send(400, {"error":"invalid_json"})
            sport_key = str(body.get("sport_key","")).strip().lower()
            import re
            if not re.fullmatch(r"[a-z0-9_]{2,40}", sport_key):
                return self._send(400, {"error":"invalid_sport_key"})
            raw_markets = body.get("markets", ["h2h"])
            if isinstance(raw_markets, str): markets = [x.strip().lower() for x in raw_markets.split(",") if x.strip()]
            elif isinstance(raw_markets, list): markets = [str(x).strip().lower() for x in raw_markets]
            else: markets = []
            allowed = {"h2h","spreads","totals"}
            if not markets or len(set(markets)) != len(markets) or any(x not in allowed for x in markets):
                return self._send(400, {"error":"invalid_markets","allowed":sorted(allowed)})
            from urllib.parse import urlencode
            query = urlencode({"markets":",".join(markets)})
            url = "https://api.puntersedge.online/v1/sports/" + sport_key + "/odds?" + query
            try:
                payload, headers = fetch_json(url, {"X-API-Key":PUNTERSEDGE_KEY,"Accept":"application/json"})
                stamp = datetime.now(timezone.utc).isoformat()
                events = payload if isinstance(payload,list) else []
                write_json("puntersedge_odds_" + sport_key + ".json", {"retrieved_at_utc":stamp,"sport_key":sport_key,"markets":markets,"events":payload})
                return self._send(200, {"provider":"PuntersEdge","status":"OK","sport_key":sport_key,"markets":markets,"event_count":len(events),"credits_cost":headers.get("X-Credits-Cost"),"credits_used":headers.get("X-Credits-Used"),"credits_remaining":headers.get("X-Credits-Remaining"),"data":payload})
            except urllib.error.HTTPError as e:
                return self._send(e.code, {"provider":"PuntersEdge","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
            except Exception as e:
                return self._send(502, {"provider":"PuntersEdge","status":"ERROR","message":str(e)[:300]})
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
        if body.get("puntersedge", True):
            if not PUNTERSEDGE_KEY:
                result["providers"].append({"provider":"PuntersEdge","status":"MISSING_SERVER_SECRET"})
            else:
                try:
                    payload, headers = fetch_json("https://api.puntersedge.online/v1/sports", {"X-API-Key":PUNTERSEDGE_KEY,"Accept":"application/json"})
                    if not isinstance(payload,list): raise ValueError("Unexpected sports catalogue response")
                    write_json("puntersedge_sports.json",{"retrieved_at_utc":result["retrieved_at_utc"],"sports":payload})
                    result["providers"].append({"provider":"PuntersEdge","status":"OK","sports_count":len(payload),"credits_remaining":headers.get("X-Credits-Remaining"),"credits_used":headers.get("X-Credits-Used"),"note":"Catalogue only; no odds markets requested, no credits spent beyond catalogue endpoint."})
                except urllib.error.HTTPError as e:
                    result["providers"].append({"provider":"PuntersEdge","status":"HTTP_ERROR","http_status":e.code,"message":e.read(500).decode("utf-8","replace")})
                except Exception as e:
                    result["providers"].append({"provider":"PuntersEdge","status":"ERROR","message":str(e)[:300]})
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
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("WBR backend listening on 0.0.0.0:%s" % port, flush=True)
    server.serve_forever()
