"""Measure how rev_z / deepest_quintile move when the panel widens.

Proxy for a universe expansion: compare reversal_watch computed on
(A) the top-800-by-mktcap subset  vs  (B) the full ~1.5k committed panel.
The delta on the names COMMON to both is what a deeper universe does to
every already-covered name's signal.
"""
import sys, pandas as pd, numpy as np
sys.path.insert(0, ".")
from engine.china_reversal import reversal_watch

closes = pd.read_parquet("data/china_search/closes.parquet")
m = pd.read_parquet("data/china_search/members.parquet")
live = [t for t in m.index if t in closes.columns]
closes = closes[live]
sector = m["sector"].to_dict(); name = m["name"].to_dict()
zh = m["name_zh"].to_dict(); mcap = m["mktcap_yi"].to_dict()

# (A) narrow panel: top-800 by REAL mktcap (placeholder 30.0 names excluded from the rank)
real = m[m["mktcap_yi"] > 30.0].sort_values("mktcap_yi", ascending=False)
narrow = [t for t in real.index[:800] if t in closes.columns]
print(f"narrow panel n={len(narrow)}   full panel n={len(closes.columns)}")

def run(cols):
    return reversal_watch(closes[cols], sector, name, tkr_name_zh=zh, tkr_mktcap=mcap, top_n=16)

A = run(narrow); B = run(list(closes.columns))
print(f"A(n={A['n']}) screened={A['screened']}   B(n={B['n']}) screened={B['screened']}")

ra, rb = A["reversal_all"], B["reversal_all"]
common = sorted(set(ra) & set(rb))
dz = pd.Series({t: rb[t]["rev_z"] - ra[t]["rev_z"] for t in common})
print(f"\ncommon names: {len(common)}")
print(f"rev_z shift  mean={dz.mean():+.4f}  median={dz.median():+.4f}  "
      f"p05={dz.quantile(.05):+.3f} p95={dz.quantile(.95):+.3f}  max|d|={dz.abs().max():.3f}")
print(f"|rev_z shift| > 0.25 : {int((dz.abs()>0.25).sum())} / {len(common)} "
      f"({100*(dz.abs()>0.25).mean():.1f}%)")
print(f"|rev_z shift| > 0.50 : {int((dz.abs()>0.50).sum())} / {len(common)} "
      f"({100*(dz.abs()>0.50).mean():.1f}%)")

qa = {t for t in common if ra[t]["deepest_quintile"]}
qb = {t for t in common if rb[t]["deepest_quintile"]}
print(f"\ndeepest_quintile (common names only): narrow={len(qa)} full={len(qb)} "
      f"stable={len(qa & qb)}  flipped_in={len(qb-qa)}  flipped_out={len(qa-qb)}")
if qa | qb:
    print(f"Jaccard continuity = {len(qa & qb)/len(qa | qb):.3f}")

wa = [w["ticker"] for w in A["watch"]]; wb = [w["ticker"] for w in B["watch"]]
print(f"\ntop-16 WATCH list overlap: {len(set(wa)&set(wb))}/16")
print("  narrow:", ", ".join(wa[:8]), "...")
print("  full  :", ", ".join(wb[:8]), "...")
