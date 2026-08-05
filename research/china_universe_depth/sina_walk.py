"""Live Sina market-cap walk -> ranked A-share list down past rank 2500.
Emits data the option arithmetic needs: rank -> (ticker, mktcap_yi)."""
import sys, json, time
sys.path.insert(0, ".")
import requests
from collectors.china_universe import _to_ticker
from lib import config

scfg = config.load()["china"]["search_universe"]["sina"]
URL, NODE, REF = scfg["url"], scfg["node"], scfg["referer"]
PAGE = int(scfg["page_size"])
FLOOR_WAN = 30 * 1e4

rows, seen = [], set()
s = requests.Session()
for page in range(1, 60):
    params = {"page": page, "num": PAGE, "sort": "mktcap", "asc": 0,
              "node": NODE, "symbol": "", "_s_r_a": "page"}
    try:
        r = s.get(URL, params=params, headers={"Referer": REF}, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"page {page} failed: {e}", file=sys.stderr); break
    if not data:
        print(f"page {page}: empty -> stop", file=sys.stderr); break
    added = 0
    for d in data:
        t = _to_ticker(str(d.get("symbol", "")))
        if not t or t in seen: continue
        w = float(d.get("mktcap") or 0)
        if w < FLOOR_WAN: continue
        seen.add(t); rows.append({"ticker": t, "mktcap_yi": round(w/1e4, 1)}); added += 1
    if added == 0 and page > 3:
        print(f"page {page}: 0 above floor -> stop", file=sys.stderr); break
    time.sleep(0.35)

out = "/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-beautiful-aryabhata-abc6d9/cfd1afe1-995a-430d-9d79-e84f37b380d9/scratchpad/sina_rank.json"
json.dump(rows, open(out, "w"))
print(f"RESULT sina walk: {len(rows)} names above 30亿")
for k in (800, 1000, 1200, 1500, 2000, 2500):
    if len(rows) >= k:
        print(f"  rank {k:5d}: {rows[k-1]['ticker']}  mktcap {rows[k-1]['mktcap_yi']}亿")
    else:
        print(f"  rank {k:5d}: beyond walk (only {len(rows)} collected)")
