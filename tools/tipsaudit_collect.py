import json, os, datetime, pathlib, urllib.request
BASE = pathlib.Path("tipsaudit/data")
now = datetime.datetime.now(datetime.timezone.utc)
stamp = now.strftime("%Y%m%dT%H%M%SZ")
urls = {
    "predictions": "https://tipsaudit.com/api/v1/predictions",
    "margins": "https://tipsaudit.com/api/v1/margins",
}
snapshot = {"retrieved_at_utc": now.isoformat(), "source": "TipsAudit", "endpoints": {}}
for name, url in urls.items():
    req = urllib.request.Request(url, headers={"User-Agent": "WBR-TipsAudit-Collector/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"{name}: HTTP {response.status}")
        snapshot["endpoints"][name] = json.loads(response.read().decode("utf-8"))
BASE.mkdir(parents=True, exist_ok=True)
path = BASE / f"{stamp}.json"
path.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(f"Saved {path}")
print(f"Prediction count: {snapshot['endpoints']['predictions'].get('count', 'n/a')}")
