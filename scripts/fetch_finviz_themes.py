"""Fetch the Finviz *themes* map snapshot (structure + per-timeframe performance).

Finviz's themes treemap (https://finviz.com/map?t=themes) is a curated
narrative-basket hierarchy: **theme → subsector → member tickers**. None of it
is a documented API, so this collector pulls the two feeds the page itself uses
and freezes them into a committed snapshot so the *build* (and CI) stays fully
offline:

* **Structure** — ``data/themes_heatmap/themes_tree.json`` (theme → subsector →
  members + descriptions). Lives in the repo; refreshed here only with
  ``--refresh-tree`` (it changes rarely and the source is a hash-rotated webpack
  chunk; see [[finviz-themes-map-extraction]]).
* **Performance** — ``/api/map_perf`` gives every subsector's % move for a given
  timeframe (the colour of each tile); ``/api/map_perf_screener`` gives the same
  per *member* ticker (the colour of each row in the hover popup). Both are
  pulled for all eight daily-group timeframes and written to
  ``data/themes_heatmap/perf_snapshot.json``.

The pure assembly (snapshot → the JSON the frontend reads) lives in
``engine/themes_heatmap.py``; the build wrapper is
``scripts/build_themes_heatmap.py``. This module is the only one that touches the
network.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "themes_heatmap"
TREE_PATH = OUT_DIR / "themes_tree.json"
PERF_PATH = OUT_DIR / "perf_snapshot.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Finviz subtype code -> our timeframe key (matches the sp500 heatmap contract).
ST_TO_TF: dict[str, str] = {
    "d1": "1D", "w1": "1W", "w4": "1M", "mtd": "MTD",
    "w13": "3M", "w26": "6M", "w52": "1Y", "ytd": "YTD",
}


def _get(url: str, retries: int = 3, pause: float = 0.8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - network is best-effort
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET failed after {retries}: {url} ({last})")


def fetch_subsector_perf() -> dict[str, dict[str, float]]:
    """{subsector_key: {tf: pct}} for every subsector, all timeframes."""
    out: dict[str, dict[str, float]] = {}
    for st, tf in ST_TO_TF.items():
        d = _get(f"https://finviz.com/api/map_perf?t=themes&st={st}")
        if d.get("subtype") != st:  # Finviz falls back to d1 on a bad code
            raise RuntimeError(f"subtype mismatch for {st!r}: got {d.get('subtype')!r}")
        for k, v in (d.get("nodes") or {}).items():
            out.setdefault(k, {})[tf] = round(float(v), 2)
        time.sleep(0.4)
    return out


def fetch_member_perf(tickers: list[str], chunk: int = 120) -> dict[str, dict[str, float]]:
    """{ticker: {tf: pct}} via the screener perf feed, batched by ticker."""
    out: dict[str, dict[str, float]] = {}
    uniq = sorted(set(tickers))
    batches = [uniq[i:i + chunk] for i in range(0, len(uniq), chunk)]
    for st, tf in ST_TO_TF.items():
        for batch in batches:
            q = urllib.parse.urlencode({"st": st, "t": ",".join(batch)})
            d = _get(f"https://finviz.com/api/map_perf_screener?{q}")
            for k, v in (d.get("nodes") or {}).items():
                if v is None:
                    continue
                out.setdefault(k, {})[tf] = round(float(v), 2)
            time.sleep(0.25)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Finviz themes snapshot")
    ap.add_argument("--refresh-tree", action="store_true",
                    help="(reserved) re-pull the theme→subsector→member structure")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.refresh_tree or not TREE_PATH.exists():
        # The structure is a hash-rotated webpack data chunk; refreshing it is a
        # manual, traced extraction (see the memory note). The committed
        # themes_tree.json is the source of record — fail loudly if it is gone
        # rather than silently shipping an empty map.
        if not TREE_PATH.exists():
            raise SystemExit(f"missing structure seed {TREE_PATH}; cannot proceed")

    tree = json.loads(TREE_PATH.read_text())
    members = sorted({m for t in tree for s in t["subsectors"] for m in s["members"]})
    print(f"tree: {len(tree)} themes, "
          f"{sum(len(t['subsectors']) for t in tree)} subsectors, {len(members)} members")

    print("fetching subsector perf …")
    sub_perf = fetch_subsector_perf()
    print(f"  {len(sub_perf)} subsectors × {len(ST_TO_TF)} timeframes")

    print("fetching member perf …")
    mem_perf = fetch_member_perf(members)
    print(f"  {len(mem_perf)}/{len(members)} members covered")

    snap = {
        "source": "finviz-themes",
        # Finviz themes perf is end-of-day; stamp the fetch date so the rotation
        # build + its forward track-record date each call by the true data day
        # (build_subsector_rotation reads snap["asof"]).
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timeframes": list(ST_TO_TF.values()),
        "subsector_perf": sub_perf,
        "member_perf": mem_perf,
    }
    PERF_PATH.write_text(json.dumps(snap, separators=(",", ":")))
    print(f"wrote {PERF_PATH} ({PERF_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
