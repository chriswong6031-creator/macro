"""DEV measurement (not a build step): re-run engine.cycles.analyze() over the live
universe and compare the NEW urgency vs the OLD urgency stamped in site/stockdata,
to quantify the cycle-top fix. Reports flip counts + the late/stretched share of
'now' calls (the headline buy-high metric, 62% before)."""
from __future__ import annotations
import sys, json, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from lib import config, store
from engine import cycles

ROOT = Path(__file__).resolve().parent.parent


def closes_map():
    """ticker -> (close, high|None) from breadth caches + deep store (US universe)."""
    out = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        cache = config.data_dir() / grp / "_closes_cache.parquet"
        if cache.exists():
            c = pd.read_parquet(cache)
            for t in c.columns:
                s = c[t].dropna()
                if len(s) >= 260 and t not in out:
                    out[t] = (s, None)
    d = config.data_dir() / "stocks"
    if d.exists():
        for p in d.glob("*.parquet"):
            t = p.stem
            try:
                df = pd.read_parquet(p)
            except Exception:
                continue
            if "close" in df and len(df["close"].dropna()) >= 260:
                out[t] = (df["close"].dropna(), df.get("high"))
    return out


def old_urgency():
    out = {}
    for fp in glob.glob(str(ROOT / "site/stockdata/*.json")):
        try:
            d = json.load(open(fp))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        lad = d.get("ladder") if isinstance(d.get("ladder"), dict) else {}
        e = lad.get("entry") if isinstance(lad.get("entry"), dict) else {}
        out[d.get("ticker")] = e.get("urgency")
    return out


def main():
    cmap = closes_map()
    old = old_urgency()
    rows = []
    for t, (close, high) in cmap.items():
        try:
            res = cycles.analyze(close, high, "equity")
        except Exception:
            continue
        cyc, lad = res["cycle"], res["ladder"]
        if not lad:
            continue
        e = lad.get("entry") or {}
        rows.append({"t": t, "new": e.get("urgency"), "old": old.get(t),
                     "phase": cyc.get("dc_phase"), "dc_day": cyc.get("dc_day"),
                     "band": cyc.get("dc_band"), "state": lad.get("state")})
    n = len(rows)
    new_now = [r for r in rows if r["new"] == "now"]
    old_now = [r for r in rows if r["old"] == "now"]

    def late_share(group):
        if not group:
            return 0, 0
        late = [r for r in group if r["dc_day"] is not None and r["band"]
                and r["dc_day"] >= r["band"][0] - 8]
        return len(late), round(100 * len(late) / len(group))

    print(f"universe analyzed: {n}")
    ln, lp = late_share(new_now)
    lo, lop = late_share(old_now)
    print(f"OLD 'now': {len(old_now)}  | late/stretched: {lo} ({lop}%)")
    print(f"NEW 'now': {len(new_now)}  | late/stretched: {ln} ({lp}%)")
    flipped_off = [r for r in rows if r["old"] == "now" and r["new"] != "now"]
    flipped_on = [r for r in rows if r["old"] != "now" and r["new"] == "now"]
    print(f"flipped now->not: {len(flipped_off)}  | not->now: {len(flipped_on)}")
    # new 'now' names by phase (should be dominated by early/new, not stretched)
    import collections
    print("NEW 'now' by phase:", dict(collections.Counter(r["phase"] for r in new_now)))
    print("NEW 'now' still stretched (sample):",
          [(r["t"], r["dc_day"]) for r in new_now if r["phase"] == "stretched"][:15])
    # sanity: genuine early-cycle fresh buys still fire?
    early_now = [r for r in new_now if r["phase"] in ("new", "mid")]
    print(f"NEW 'now' that are early/mid (healthy fresh buys preserved): {len(early_now)}")


if __name__ == "__main__":
    main()
