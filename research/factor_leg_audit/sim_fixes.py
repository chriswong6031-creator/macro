"""Before/after simulation for the blue-chip quality/payout z repair proposal.

Companion to research/BLUECHIP_QUALITY_PAYOUT_Z_ADJUDICATION.md. Run from the
repo root:  python3 research/factor_leg_audit/sim_fixes.py

Panels:
  BEFORE : exact current construction on current inputs — validated against the
           shipped site/factordata/factors.json (asserts on MCD/KO/SBUX) so the
           simulation provably reproduces the live pipeline before it varies it
  A      : input repair only (adjudication D1) — dividends fillna(
           PaymentsOfDividends -> DividendsCommonStockCash), debt_lt fillna(
           LongTermDebt), equity fillna(StockholdersEquityIncludingPortion
           AttributableToNoncontrollingInterest); construction unchanged
  AB1    : A + guards (D2 fallback) — ratio winsorization [p1,p99] before z on
           every quality/payout leg; ROE denominator guard equity >= 2% assets;
           quality requires >= 2 legs
  AB2    : A + substitution (D2 recommended) — as AB1 but ROE -> ROA (ni/assets)

Inputs: data/edgar/fundamentals.parquet + breadth close caches (live snapshot),
fallback_frames_2026-08-06.json (frozen CY2025 EDGAR frames for the fallback
concepts). Output: evidence.json (S&P100 z panels + watch bucket outcomes).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from engine import equity_factors as ef  # noqa: E402
from lib import config  # noqa: E402

HERE = Path(__file__).parent
cap = config.load()["edgar"]["factors"]["winsor_z"]

fund = pd.read_parquet(config.data_dir() / "edgar" / "fundamentals.parquet")
frames = json.load(open(HERE / "fallback_frames_2026-08-06.json"))
closes = ef._closes("broad")
px = closes.reindex(columns=[t for t in fund.index if t in closes.columns])
last_px = px.ffill().iloc[-1]

d0 = fund[fund.index.isin(last_px.index)].copy()
d0["price"] = last_px.reindex(d0.index)
d0["shares"] = ef._reconcile_shares(d0["shares"])
d0["mktcap"] = d0["price"] * d0["shares"]

cik_str = d0["cik"].astype(int).astype(str)


def from_frame(concept):
    return cik_str.map(frames[concept])


dA = d0.copy()
div_fb = from_frame("PaymentsOfDividends").fillna(from_frame("DividendsCommonStockCash"))
dA["dividends"] = dA["dividends"].fillna(div_fb)
dA["debt_lt"] = dA["debt_lt"].fillna(from_frame("LongTermDebt"))
dA["equity"] = dA["equity"].fillna(
    from_frame("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))

WZ = ef._winsor_z


def wz_ratio(s, lo=0.01, hi=0.99):
    """Winsorize the RAW ratio at [p1,p99] first, then z. Fixes the M3 defect:
    _winsor_z clips z AFTER mean/sd are computed on the raw ratio, so fat-tailed
    denominators inflate sd ~6x and crush real cross-sectional variation."""
    s = s.replace([np.inf, -np.inf], np.nan)
    return WZ(s.clip(s.quantile(lo), s.quantile(hi)), cap)


def build(d, mode):
    """mode: 'current' | 'guard' | 'subst' -> dict of z-Series + leg receipts."""
    mc = d["mktcap"].where(d["mktcap"] > 0)
    avg_assets = (d["assets"] + d["assets_prior"]) / 2.0
    z = (lambda s: WZ(s, cap)) if mode == "current" else wz_ratio

    if mode == "subst":
        prof_raw = d["ni"] / d["assets"]                         # ROA
    elif mode == "guard":
        prof_raw = d["ni"] / d["equity"].where(d["equity"] >= 0.02 * d["assets"])
    else:
        prof_raw = d["ni"] / d["equity"].where(d["equity"] > 0)  # current ROE

    roe = z(prof_raw)
    accr = z((d["ni"] - d["cfo"]) / avg_assets)
    lev = z(d["debt_lt"] / d["assets"])
    legs = pd.concat([roe, -accr, -lev], axis=1)
    qual_raw = legs.mean(axis=1)
    if mode != "current":
        qual_raw[legs.notna().sum(axis=1) < 2] = np.nan          # min-2-legs guard
    qual = WZ(qual_raw, cap)

    pay_raw = (d["dividends"].fillna(0) + d["repurchases"].fillna(0)) / mc
    pay_raw[d["dividends"].isna() & d["repurchases"].isna()] = np.nan
    pay = WZ(z(pay_raw) if mode != "current" else WZ(pay_raw, cap), cap)

    return {"quality": qual, "payout": pay, "roe_z": roe, "maccr_z": -accr,
            "mlev_z": -lev, "prof_raw": prof_raw, "pay_raw": pay_raw,
            "nlegs": legs.notna().sum(axis=1)}


panels = {"BEFORE": build(d0, "current"), "A": build(dA, "current"),
          "AB1": build(dA, "guard"), "AB2": build(dA, "subst")}

ship = pd.DataFrame(json.load(open("site/factordata/factors.json"))["table"]).set_index("ticker")
for t in ("MCD", "KO", "SBUX"):
    assert abs(panels["BEFORE"]["quality"][t] - ship["quality"][t]) < 0.02, t
    assert abs(panels["BEFORE"]["payout"][t] - ship["payout"][t]) < 0.02, t
print("BEFORE panel matches shipped factors.json for MCD/KO/SBUX ✓\n")

sp100 = d0["mktcap"].sort_values(ascending=False).head(100).index
WATCH = ["MCD", "KO", "SBUX", "JNJ", "PG", "AAPL", "HD"]

print("Distribution stats (S&P100 = top-100 mktcap):")
for fac in ("quality", "payout"):
    for name, P in panels.items():
        s = P[fac].reindex(sp100)
        print(f"  {fac:8s} {name:7s} n={s.notna().sum():3d} mean={s.mean():+.3f} "
              f"sd={s.std():.3f} p10={s.quantile(.1):+.3f} p50={s.quantile(.5):+.3f} "
              f"p90={s.quantile(.9):+.3f} min={s.min():+.3f}")
    print()

print("Watch names (quality z | payout z) BEFORE -> A -> AB1 -> AB2:")
for t in WATCH:
    q = [panels[k]["quality"][t] for k in panels]
    p = [panels[k]["payout"][t] for k in panels]
    print(f"  {t:5s} q: " + " -> ".join(f"{v:+.2f}" if pd.notna(v) else "  NaN" for v in q)
          + "   pay: " + " -> ".join(f"{v:+.2f}" if pd.notna(v) else "  NaN" for v in p))

# archetype factor-z gates (v2 buckets 1-7 use non-factor inputs, unchanged here)
lv, lb, pz, vz = ship["low_vol"], ship["low_beta"], ship["profitability"], ship["value"]
net_margin = d0["ni"] / d0["revenue"] * 100
nm_thr = net_margin.quantile(2 / 3)
CYC = {"Industrials", "Materials", "Consumer Discretionary", "Energy"}
sect = ship["sector"]


def bucket(t, P):
    q, pay = P["quality"][t], P["payout"][t]
    _lv, _lb, _p, _v = lv.get(t), lb.get(t), pz.get(t), vz.get(t)
    nm_top = pd.notna(net_margin.get(t)) and net_margin[t] >= nm_thr

    def ge(x, thr):
        return pd.notna(x) and x >= thr

    if sect.get(t) in CYC and not (ge(pay, .5) and ge(_lv, .3)) and not ge(q, .6):
        return "cyclical"
    if pd.notna(_lb) and _lb <= -0.6 and pd.notna(_lv) and _lv <= -0.4:
        return "high_beta_momentum"
    if ge(pay, .5) and ge(_lv, .4) and ge(_lb, .3):
        return "dividend_defensive"
    if ge(q, .5) and (ge(_p, .3) or nm_top) and not ge(_v, .75):
        return "quality_compounder"
    if ge(_v, .75) and not ge(q, .5):
        return "deep_value"
    return "mixed"


print("\nArchetype-gate crossings (S&P100) vs BEFORE:")
for name in ("A", "AB1", "AB2"):
    P, B = panels[name], panels["BEFORE"]
    for gate, sb, sa, thr in (("quality>=0.5", B["quality"], P["quality"], .5),
                              ("quality>=0.6", B["quality"], P["quality"], .6),
                              ("payout>=0.5", B["payout"], P["payout"], .5)):
        b, a = sb.reindex(sp100) >= thr, sa.reindex(sp100) >= thr
        print(f"  {name:4s} {gate:14s} {int(b.sum()):2d} -> {int(a.sum()):2d} "
              f"(+{int((a & ~b).sum())}/-{int((b & ~a).sum())})")

print("\nFactor-z bucket outcome for watch names (BEFORE -> A -> AB1 -> AB2):")
for t in WATCH:
    print(f"  {t:5s}: " + " -> ".join(bucket(t, panels[k]) for k in panels))

ev = {"asof": "2026-08-06", "fy": 2025, "sp100_def": "top-100 mktcap of factor table",
      "panels": {}}
for name, P in panels.items():
    ev["panels"][name] = {
        "sp100_quality": {t: (None if pd.isna(P["quality"].get(t))
                              else round(float(P["quality"][t]), 3)) for t in sp100},
        "sp100_payout": {t: (None if pd.isna(P["payout"].get(t))
                             else round(float(P["payout"][t]), 3)) for t in sp100}}
ev["watch_buckets"] = {t: {k: bucket(t, panels[k]) for k in panels} for t in WATCH}
with open(HERE / "evidence.json", "w") as fh:
    json.dump(ev, fh, indent=1)
print("\nevidence.json written")
