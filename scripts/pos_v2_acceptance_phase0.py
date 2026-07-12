"""
W4.7 — Position-v2 Axis Acceptance Phase-0 Study (D1-W5 acceptance study)
=========================================================================

Decides the M3 axis flip (D1_ONTOLOGY.md §7): does the canonical z/CDF position
`pos_v2` (100·Φ(z), `engine.cycle_ontology.canonical_position`) mean the SAME thing
at every confirmed turn across every instrument — i.e. does ">=68" read as "late/high"
everywhere — where the legacy range-stochastic oscillator `pos` does NOT?

The audit's defect: the DISPLAYED legacy `pos` spanned ~17.6-99.7 at CONFIRMED PEAKS,
so a single numeric position threshold cannot mean the same thing across instruments.
This study measures whether pos_v2 tightens that at confirmed peaks AND troughs.

Method (PIT-safe; NO live-engine recompute)
-------------------------------------------
1. Confirmed turns per instrument are detected with `cycle_ontology.detect_turns`
   on the SAME structure-math basis the backfill used (close_price for yahoo, the
   custodian close for Shenwan CN; ZigZag pct per TURN_DETECTOR_DEFAULTS).  A turn is
   a CONFIRMED peak (k='peak') or trough (k='trough') — provisional turns dropped.
2. The position AT each confirmed turn is read from the committed
   `data/<engine>/backfill.parquet` (the same monthly PIT stamps the pages display),
   by mapping the turn EXTREMUM date to the nearest backfill month-end (|gap| <= 45d;
   turns before the 2010-12 backfill window are dropped).  This reads the EXACT `pos`
   and `pos_v2` numbers a page would show at that turn — no re-derivation, no drift.
3. For pos and pos_v2 we report min / p25 / median / p75 / max / IQR at peaks and at
   troughs, per family (us_sector, country) and pooled, and the maturation-gate metrics
   from D1_ONTOLOGY.md §6 (cycle-pos-v2-turn-coherence):
       PEAKS   : IQR(pos_v2) <= 25 AND median(pos_v2) >= 70
       TROUGHS : IQR(pos_v2) <= 25 AND median(pos_v2) <= 30   (mirror)
       on n >= 100 confirmed turns per side.

Scope note (load-bearing for the flip)
--------------------------------------
The China sector backfill (`data/china_sector_cycles/backfill.parquet`) does NOT carry
a `pos_v2` column (the CN engine emits legacy fields only).  So pos_v2 CANNOT be assessed
for the CN family from committed PIT data.  We still report the CN LEGACY spread (to
show the same defect exists there) and flag CN as UN-ASSESSED for pos_v2 — a fact the
verdict must weigh, because the flip touches china_sector_cycles.html too.

Outputs
-------
data/cycle_ontology/pos_v2_acceptance_phase0.json  — machine-readable metrics
(stdout)                                           — human summary table

Run:  python3 scripts/pos_v2_acceptance_phase0.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.cycle_ontology import (  # noqa: E402
    TURN_DETECTOR_DEFAULTS,
    TurnParams,
    detect_turns,
)

# ── Universe (matches the hazard-panel / backfill IDs exactly) ───────────────────────
US_SECTOR_IDS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
COUNTRY_IDS = [
    "AAXJ", "ECH", "EEM", "EFA", "EIDO", "EPOL", "EWA", "EWC", "EWD", "EWG",
    "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP", "EWQ", "EWS", "EWT", "EWU",
    "EWW", "EWY", "EWZ", "EZA", "FXI", "ILF", "INDA", "TUR", "VGK", "VPL", "VXUS",
]
CN_SECTOR_IDS = [
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
]

ZZ_SECTOR = TURN_DETECTOR_DEFAULTS["pct_sector"]     # 14.0
ZZ_COUNTRY = TURN_DETECTOR_DEFAULTS["pct_country"]   # 14.0
ZZ_CN = TURN_DETECTOR_DEFAULTS["pct_cn"]             # 18.0

MAX_GAP_DAYS = 45          # turn extremum → nearest backfill month-end tolerance
YAHOO_DIR = _REPO / "data" / "yahoo"
CN_DIR = _REPO / "data" / "china_sectors"

BF = {
    "us_sector": _REPO / "data" / "sector_cycles" / "backfill.parquet",
    "country":   _REPO / "data" / "country_cycles" / "backfill.parquet",
    "cn_sector": _REPO / "data" / "china_sector_cycles" / "backfill.parquet",
}


# ── Price loaders (mirror build_hazard_panel structure-math basis) ───────────────────
def _load_yahoo_price(ticker: str) -> pd.Series | None:
    path = YAHOO_DIR / f"{ticker.upper()}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    col = "close_price" if "close_price" in df.columns else ("close" if "close" in df.columns else None)
    if col is None:
        return None
    s = df[col].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def _load_cn_close(code: str) -> pd.Series | None:
    path = CN_DIR / f"{code}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def _confirmed_turns(close: pd.Series, series_id: str, pct: float) -> list[dict]:
    params = TurnParams(pct=pct, basis="close_price", version=2)
    turns = detect_turns(close, series_id=series_id, params=params)
    return [t for t in turns if not t.get("provisional", False)]


def _five_num(vals: np.ndarray) -> dict:
    vals = np.asarray(vals, dtype=float)
    vals = vals[~np.isnan(vals)]
    if len(vals) == 0:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "iqr": None}
    p25, p50, p75 = np.percentile(vals, [25, 50, 75])
    return {
        "n": int(len(vals)),
        "min": round(float(vals.min()), 1),
        "p25": round(float(p25), 1),
        "median": round(float(p50), 1),
        "p75": round(float(p75), 1),
        "max": round(float(vals.max()), 1),
        "iqr": round(float(p75 - p25), 1),
    }


def _collect_family(family: str, ids: list[str], pct: float, load_fn) -> pd.DataFrame:
    """Return one row per confirmed turn: {family,id,k,major,ext_date,me_date,gap_days,pos,pos_v2}."""
    bf = pd.read_parquet(BF[family])
    bf["date"] = pd.to_datetime(bf["date"])
    has_v2 = "pos_v2" in bf.columns
    rows: list[dict] = []
    for iid in ids:
        close = load_fn(iid)
        if close is None or len(close) < 100:
            continue
        sub = bf[bf["id"] == iid.lower()].set_index("date").sort_index()
        if sub.empty:
            continue
        me = sub.index
        for t in _confirmed_turns(close, iid, pct):
            ext = pd.Timestamp(t["date"])
            idx = int(me.searchsorted(ext))
            cands = [i for i in (idx - 1, idx) if 0 <= i < len(me)]
            if not cands:
                continue
            best = min(cands, key=lambda i: abs((me[i] - ext).days))
            gap = (me[best] - ext).days
            if abs(gap) > MAX_GAP_DAYS:
                continue  # turn outside the backfill window (pre-2010-12)
            d = me[best]
            rows.append({
                "family": family,
                "id": iid,
                "k": t["k"],
                "major": bool(t.get("major", False)),
                "ext_date": str(ext.date()),
                "me_date": str(d.date()),
                "gap_days": int(gap),
                "pos": float(sub.loc[d, "pos"]) if pd.notna(sub.loc[d, "pos"]) else np.nan,
                "pos_v2": (float(sub.loc[d, "pos_v2"]) if has_v2 and pd.notna(sub.loc[d, "pos_v2"]) else np.nan),
            })
    return pd.DataFrame(rows)


def _spread_block(df: pd.DataFrame, side: str) -> dict:
    """side ∈ {peak, trough}. Returns {pos:{...}, pos_v2:{...}}."""
    d = df[df["k"] == side]
    return {"pos": _five_num(d["pos"].values), "pos_v2": _five_num(d["pos_v2"].values)}


def main() -> int:
    fams = [
        ("us_sector", US_SECTOR_IDS, ZZ_SECTOR, _load_yahoo_price),
        ("country",   COUNTRY_IDS,   ZZ_COUNTRY, _load_yahoo_price),
        ("cn_sector", CN_SECTOR_IDS, ZZ_CN,      _load_cn_close),
    ]
    per_family = {f[0]: _collect_family(*f) for f in fams}
    # Pooled pos_v2-bearing families only (us_sector + country) for the gate.
    v2_pool = pd.concat([per_family["us_sector"], per_family["country"]], ignore_index=True)
    all_pool = pd.concat(list(per_family.values()), ignore_index=True)

    report: dict = {"gap_tolerance_days": MAX_GAP_DAYS, "families": {}, "pooled_v2": {}, "legacy_pooled_all": {}}

    for fam, df in per_family.items():
        report["families"][fam] = {
            "n_turns": int(len(df)),
            "n_peaks": int((df["k"] == "peak").sum()),
            "n_troughs": int((df["k"] == "trough").sum()),
            "pos_v2_available": bool(df["pos_v2"].notna().any()),
            "peak": _spread_block(df, "peak"),
            "trough": _spread_block(df, "trough"),
            "gap_days_abs_median": (int(df["gap_days"].abs().median()) if len(df) else None),
        }

    report["pooled_v2"] = {  # us_sector + country (the families with pos_v2)
        "families": ["us_sector", "country"],
        "n_peaks": int((v2_pool["k"] == "peak").sum()),
        "n_troughs": int((v2_pool["k"] == "trough").sum()),
        "peak": _spread_block(v2_pool, "peak"),
        "trough": _spread_block(v2_pool, "trough"),
    }
    report["legacy_pooled_all"] = {  # legacy pos across ALL 3 families (CN legacy exists)
        "families": ["us_sector", "country", "cn_sector"],
        "peak": {"pos": _five_num(all_pool[all_pool["k"] == "peak"]["pos"].values)},
        "trough": {"pos": _five_num(all_pool[all_pool["k"] == "trough"]["pos"].values)},
    }

    # ── Maturation gate (D1_ONTOLOGY §6 cycle-pos-v2-turn-coherence) ──────────────────
    pk = report["pooled_v2"]["peak"]["pos_v2"]
    tr = report["pooled_v2"]["trough"]["pos_v2"]
    gate = {
        "peak": {
            "n": pk["n"], "n_ok": pk["n"] >= 100,
            "iqr": pk["iqr"], "iqr_ok": (pk["iqr"] is not None and pk["iqr"] <= 25),
            "median": pk["median"], "median_ok": (pk["median"] is not None and pk["median"] >= 70),
        },
        "trough": {
            "n": tr["n"], "n_ok": tr["n"] >= 100,
            "iqr": tr["iqr"], "iqr_ok": (tr["iqr"] is not None and tr["iqr"] <= 25),
            "median": tr["median"], "median_ok": (tr["median"] is not None and tr["median"] <= 30),
        },
    }
    gate["peak"]["pass"] = bool(gate["peak"]["n_ok"] and gate["peak"]["iqr_ok"] and gate["peak"]["median_ok"])
    gate["trough"]["pass"] = bool(gate["trough"]["n_ok"] and gate["trough"]["iqr_ok"] and gate["trough"]["median_ok"])
    gate["pass"] = bool(gate["peak"]["pass"] and gate["trough"]["pass"])
    gate["population"] = "all_confirmed_turns (pre-registered)"
    report["maturation_gate"] = gate

    # ── Diagnostic: MAJOR-only turns (detector's cyclical-significance flag) ──────────
    # NOT the pre-registered population — reported to explain the peak miss and to size
    # the proposed remediation (re-scope gate to major turns). Does NOT change the verdict.
    v2_major = v2_pool[v2_pool["major"]]
    report["diagnostic_major_only"] = {
        "note": ("major=True filters ZigZag lower-highs / higher-lows (directional pivots "
                 "far from cyclical extremes). Exploratory, not the prereg gate."),
        "peak": _spread_block(v2_major, "peak"),
        "trough": _spread_block(v2_major, "trough"),
    }

    out = _REPO / "data" / "cycle_ontology" / "pos_v2_acceptance_phase0.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    # ── Human summary ────────────────────────────────────────────────────────────────
    def fmt(b):
        if b["n"] == 0:
            return "n=0"
        return (f"n={b['n']:<4} min={b['min']:<5} p25={b['p25']:<5} med={b['median']:<5} "
                f"p75={b['p75']:<5} max={b['max']:<5} IQR={b['iqr']}")

    print("\n" + "=" * 78)
    print("W4.7 POS_V2 AXIS ACCEPTANCE — comparability at CONFIRMED turns")
    print("=" * 78)
    for fam, df in per_family.items():
        v2 = report["families"][fam]["pos_v2_available"]
        print(f"\n── {fam}  ({report['families'][fam]['n_peaks']} peaks / "
              f"{report['families'][fam]['n_troughs']} troughs; "
              f"pos_v2={'YES' if v2 else 'ABSENT'}) ──")
        for side in ("peak", "trough"):
            b = report["families"][fam][side]
            print(f"  {side:<7} legacy pos : {fmt(b['pos'])}")
            if v2:
                print(f"  {side:<7} pos_v2     : {fmt(b['pos_v2'])}")

    print("\n" + "─" * 78)
    print("POOLED (us_sector + country — the families that carry pos_v2)")
    for side in ("peak", "trough"):
        b = report["pooled_v2"][side]
        print(f"  {side:<7} legacy pos : {fmt(b['pos'])}")
        print(f"  {side:<7} pos_v2     : {fmt(b['pos_v2'])}")

    print("\n" + "─" * 78)
    print("MATURATION GATE (cycle-pos-v2-turn-coherence, D1_ONTOLOGY §6)")
    for side in ("peak", "trough"):
        g = gate[side]
        tgt = ">=70" if side == "peak" else "<=30"
        print(f"  {side:<7} n={g['n']} (>=100 {'OK' if g['n_ok'] else 'FAIL'}) | "
              f"IQR={g['iqr']} (<=25 {'OK' if g['iqr_ok'] else 'FAIL'}) | "
              f"median={g['median']} ({tgt} {'OK' if g['median_ok'] else 'FAIL'}) "
              f"=> {'PASS' if g['pass'] else 'FAIL'}")
    print(f"\n  GATE VERDICT: {'PASS' if gate['pass'] else 'FAIL/HOLD'}")
    print(f"\n  Written: {out.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
