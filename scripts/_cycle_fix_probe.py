"""DEV probe (not a build step): load real close series for a set of tickers and
print engine.cycles.analyze() state/urgency so we can see the cycle-top fix before
vs after. Usage: python scripts/_cycle_fix_probe.py [TICKER ...]"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from lib import config, store
from engine import cycles

DEFAULT = ["HWM", "OFG", "EWBC", "ECG", "MYRG", "FIX", "TXN", "AIZ", "BALL",
           "NVDA", "AAPL", "TTWO", "WSC", "MCHP", "IREN"]


def load_close(t: str):
    # deep-history store first
    df = None
    try:
        df = store.read("stocks", t)
    except Exception:
        df = None
    if df is not None and "close" in df:
        return df["close"].dropna(), df.get("high")
    # breadth close caches (~3y)
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        cache = config.data_dir() / grp / "_closes_cache.parquet"
        if cache.exists():
            c = pd.read_parquet(cache)
            if t in c.columns:
                return c[t].dropna(), None
    return None, None


def probe(t: str):
    close, high = load_close(t)
    if close is None or len(close) < 260:
        print(f"{t:6s}  no/thin data")
        return
    res = cycles.analyze(close, high, kind="equity")
    cyc, mtf, lad = res["cycle"], res["mtf"], res["ladder"]
    d = mtf.get("D", {})
    d3 = mtf.get("3D", {})
    w = mtf.get("W", {})
    e = lad.get("entry", {})
    def flags(s):
        bits = []
        if s.get("macd_cross_dn"): bits.append("Xdn")
        if s.get("macd_curl_dn"): bits.append("curl_dn")
        if s.get("macd_approaching_dn"): bits.append("appr_dn")
        if s.get("macd_pos"): bits.append("pos")
        return ",".join(bits) or "-"
    print(f"{t:6s} px={close.iloc[-1]:8.2f} dc_day={cyc.get('dc_day'):>3} "
          f"band={cyc.get('dc_band')} phase={cyc.get('dc_phase'):<15} "
          f"rsiD={d.get('rsi14')} | STATE={lad.get('state'):<18} "
          f"urg={e.get('urgency'):<9} tag={e.get('tag')}")
    print(f"        D[{flags(d)}] 3D[{flags(d3)}] W[{flags(w)}] "
          f"cand_age={cyc.get('cand_age')} cand_swing={cyc.get('cand_swing')} "
          f"above_ma10={cyc.get('above_ma10')} ic_phase={cyc.get('ic_phase')}")


if __name__ == "__main__":
    tickers = sys.argv[1:] or DEFAULT
    for t in tickers:
        probe(t)
