"""Phase-0 evidence gate for the China Sector pathway engine.

Question: for each of the four GS-style sectors (Banks / Consumption / Real Estate /
Auto), which China-specific drivers actually LEAD the sector's major tops & bottoms —
robustly enough to put in a forward-looking pathway view — and which merely coincide?

Discipline (house rule, mirrors CLAIMS_RECESSION_VALIDATION / DISLOCATION_VALIDATION):
  • leak-free monthly panel (macro publication-lagged; engine.china_sector_index.driver_panel)
  • forward-return rank-IC at 3m & 6m horizons
  • train (pre-2020) / test (2020+) split — a driver must keep its SIGN out of sample
  • circular-permutation p-value (preserves driver autocorrelation), Benjamini-Hochberg
    FWER control across the whole sector×driver×horizon family
  • event study: driver own-history percentile at detected tops vs bottoms (the "reasons")

Run:  python -m scripts.china_sector_pathway_phase0
Prints a structured report; paste the verdict block into research/CHINA_SECTOR_PATHWAY_PHASE0.md.
This is research, not site output — it imports the SAME data layer the live engine uses.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_sector_index as csi  # noqa: E402

SPLIT = pd.Timestamp("2020-01-01")
HORIZONS = [3, 6]            # months
N_PERM = 2000
RNG = np.random.default_rng(20260626)
ZIGZAG_PCT = 0.25           # a "major" turn = 25% reversal


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman via Pearson on ranks."""
    if len(a) < 8:
        return np.nan
    ra = pd.Series(a).rank().values
    rb = pd.Series(b).rank().values
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / d) if d > 0 else np.nan


def _circular_perm_p(driver: np.ndarray, fwd: np.ndarray, obs_ic: float) -> float:
    """Circular-rotation permutation: preserves the driver's autocorrelation, breaks
    the cross-relationship. p = P(|null IC| >= |obs IC|)."""
    n = len(driver)
    if n < 12 or not np.isfinite(obs_ic):
        return np.nan
    rd = pd.Series(driver).rank().values
    rf = pd.Series(fwd).rank().values
    rf = rf - rf.mean()
    denom_f = rf @ rf
    hits = 0
    offsets = RNG.integers(1, n, size=N_PERM)
    for off in offsets:
        rr = np.roll(rd, off)
        rr = rr - rr.mean()
        d = np.sqrt((rr @ rr) * denom_f)
        ic = (rr @ rf / d) if d > 0 else 0.0
        if abs(ic) >= abs(obs_ic):
            hits += 1
    return (1 + hits) / (N_PERM + 1)


def _bh(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg: returns survive[] aligned to pvals (NaN p -> False)."""
    idx = [i for i, p in enumerate(pvals) if np.isfinite(p)]
    m = len(idx)
    survive = [False] * len(pvals)
    if m == 0:
        return survive
    order = sorted(idx, key=lambda i: pvals[i])
    thresh_rank = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            thresh_rank = rank
    for rank, i in enumerate(order, start=1):
        if rank <= thresh_rank:
            survive[i] = True
    return survive


def _build_panel(key: str) -> tuple[pd.DataFrame, pd.Series, list[dict]]:
    """Per-sector merged driver panel + forward returns + detected turns."""
    px = csi.gs_index(key)
    bench = csi.benchmark_close()
    grid = pd.date_range("2008-01-31", px.index.max(), freq="ME")
    panel = csi.driver_panel(grid).join(csi.sector_technicals(px, bench, grid))
    mpx = px.resample("ME").last().reindex(grid, method="ffill")
    panel["_px"] = mpx
    turns = csi.zigzag_turns(px, ZIGZAG_PCT)
    return panel, mpx, turns


def _ic_tests(panel: pd.DataFrame, mpx: pd.Series) -> list[dict]:
    drivers = [c for c in panel.columns if not c.startswith("_")]
    rows = []
    for h in HORIZONS:
        fwd = mpx.shift(-h) / mpx - 1.0
        for d in drivers:
            sub = pd.concat([panel[d], fwd], axis=1).dropna()
            sub = sub[sub.index <= mpx.index.max() - pd.offsets.MonthEnd(h)]
            if len(sub) < 24:
                continue
            dv, fv = sub.iloc[:, 0].values, sub.iloc[:, 1].values
            ic = _spearman(dv, fv)
            tr = sub[sub.index < SPLIT]; te = sub[sub.index >= SPLIT]
            ic_tr = _spearman(tr.iloc[:, 0].values, tr.iloc[:, 1].values) if len(tr) >= 12 else np.nan
            ic_te = _spearman(te.iloc[:, 0].values, te.iloc[:, 1].values) if len(te) >= 12 else np.nan
            p = _circular_perm_p(dv, fv, ic)
            rows.append({"driver": d, "h": h, "ic": ic, "ic_train": ic_tr,
                         "ic_test": ic_te, "n": len(sub), "p": p,
                         "sign_stable": bool(np.isfinite(ic_tr) and np.isfinite(ic_te)
                                             and np.sign(ic_tr) == np.sign(ic_te))})
    return rows


def _event_study(panel: pd.DataFrame, turns: list[dict]) -> dict:
    """Driver own-history percentile at tops vs bottoms (descriptive 'reasons')."""
    drivers = [c for c in panel.columns if not c.startswith("_")]
    pct = panel[drivers].rank(pct=True)
    grid = panel.index
    def at(kind):
        out = {d: [] for d in drivers}
        for t in turns:
            if t["kind"] != kind:
                continue
            m = grid[grid <= t["date"]]
            if len(m) == 0:
                continue
            row = pct.loc[m[-1]]
            for d in drivers:
                if np.isfinite(row[d]):
                    out[d].append(row[d])
        return {d: (round(float(np.median(v)), 2), len(v)) for d, v in out.items() if v}
    return {"bottoms": at("bottom"), "tops": at("top")}


def main() -> int:
    print("=" * 78)
    print("CHINA SECTOR PATHWAY — PHASE 0 EVIDENCE GATE")
    print("=" * 78)

    all_p, all_meta = [], []
    per_sector = {}
    for key in csi.GS_BASKETS:
        panel, mpx, turns = _build_panel(key)
        rows = _ic_tests(panel, mpx)
        es = _event_study(panel, turns)
        per_sector[key] = {"rows": rows, "turns": turns, "es": es,
                           "span": (mpx.first_valid_index(), mpx.index.max())}
        for r in rows:
            all_p.append(r["p"]); all_meta.append((key, r))

    survive = _bh(all_p, q=0.10)
    for s, (key, r) in zip(survive, all_meta):
        r["bh_survive"] = s

    for key, b in csi.GS_BASKETS.items():
        d = per_sector[key]
        s0, s1 = d["span"]
        print(f"\n{'─'*78}\n■ {b['en']}  ({b['bbg']})   span {s0.date()}..{s1.date()}")
        tt = d["turns"]
        tops = [t for t in tt if t["kind"] == "top"]
        bots = [t for t in tt if t["kind"] == "bottom"]
        print(f"  major turns (≥{int(ZIGZAG_PCT*100)}% zigzag): {len(bots)} bottoms, {len(tops)} tops")
        print("   " + ", ".join(f"{t['kind'][0].upper()}{t['date'].date()}" for t in tt[-8:]))
        rows = sorted(d["rows"], key=lambda x: -abs(x["ic"]) if np.isfinite(x["ic"]) else 0)
        print(f"  {'driver':<16}{'h':>2}{'IC':>7}{'train':>7}{'test':>7}{'n':>5}{'p':>7}  flags")
        for r in rows[:14]:
            flags = []
            if r["sign_stable"]:
                flags.append("sign✓")
            if r.get("bh_survive"):
                flags.append("BH✓")
            strong = abs(r["ic"]) >= 0.15 and r["sign_stable"] and r.get("bh_survive")
            mark = "★" if strong else " "
            print(f" {mark}{r['driver']:<16}{r['h']:>2}{r['ic']:>7.3f}"
                  f"{r['ic_train']:>7.3f}{r['ic_test']:>7.3f}{r['n']:>5}{r['p']:>7.3f}  {' '.join(flags)}")
        # reasons (event study): drivers most extreme at bottoms vs tops
        es = d["es"]
        print("  reasons @ BOTTOMS (median own-pctile, n):")
        bm = sorted(es["bottoms"].items(), key=lambda kv: abs(kv[1][0] - 0.5), reverse=True)
        print("    " + " · ".join(f"{k}={v[0]:.2f}(n{v[1]})" for k, v in bm[:7]))
        print("  reasons @ TOPS:")
        tm = sorted(es["tops"].items(), key=lambda kv: abs(kv[1][0] - 0.5), reverse=True)
        print("    " + " · ".join(f"{k}={v[0]:.2f}(n{v[1]})" for k, v in tm[:7]))

    # ---- consolidated verdict --------------------------------------------------
    print(f"\n{'='*78}\nVERDICT — drivers eligible for the pathway engine (★ = IC≥0.15, sign-stable, BH✓)")
    print("="*78)
    elig = {}
    for key, r in all_meta:
        if abs(r["ic"]) >= 0.15 and r["sign_stable"] and r.get("bh_survive"):
            elig.setdefault(key, []).append(r)
    if not elig:
        print("  NONE clear the strict bar. Pathway must be CONDITIONAL/display-only — no point forecast.")
    for key, rs in elig.items():
        print(f"  {csi.GS_BASKETS[key]['en']}:")
        for r in sorted(rs, key=lambda x: -abs(x["ic"])):
            print(f"     {r['driver']} (h={r['h']}m IC={r['ic']:+.2f} test={r['ic_test']:+.2f} p={r['p']:.3f})")
    n_total = len(all_meta)
    n_sign = sum(1 for _, r in all_meta if r["sign_stable"])
    n_bh = sum(1 for _, r in all_meta if r.get("bh_survive"))
    print(f"\n  family: {n_total} tests · {n_sign} sign-stable · {n_bh} BH-survive · "
          f"{sum(len(v) for v in elig.values())} fully eligible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
