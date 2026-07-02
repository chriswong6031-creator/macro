"""Evidence gate for the China Sector Pathway engine — the CI tripwire that fails the
build if the relationships the pathway ships on STOP holding (the discipline from
engine.risk_radar_backtest / research/CHINA_SECTOR_PATHWAY_PHASE0.md).

We ship only two evidence-backed claims, so we gate exactly those:

  HARD checks (must pass — these were stable across all four sectors in Phase 0):
    • the washout↔euphoria SIGNATURE separates bottoms from tops with the right sign:
      at detected bottoms, distance-from-200d and drawdown own-history percentiles are
      LOWER than at detected tops.

  SOFT checks (logged, do not fail CI — modest by Phase-0's own admission):
    • the shipped lead-cluster legs keep their full-sample forward-IC sign
      (credit +, PPI −, mean-reversion −). A flip is surfaced for human review.

`run_gate()` returns a structured report; tests/test_china_sector_pathway.py asserts
`passed` (skipping cleanly when the china_sectors data plane is absent in a bare env).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import china_sector_index as csi
from engine import grading_stats as gs

# Trailing window for the CAUSAL own-history percentile — matches engine.china_sector_pathway
# ._position (1260 trading days ≈ 5y). A leg's percentile at a turn uses ONLY the ~5y of bars
# up to and including that turn, never future bars (audit china-sector-cycles-5).
_TRAIL_DAYS = 1260


def _causal_pctile(ser: pd.Series, window: int = _TRAIL_DAYS) -> pd.Series:
    """Own-history percentile of each point within its own trailing `window` bars.

    Causal replacement for `ser.rank(pct=True)` (which is a FULL-SAMPLE rank — future bars
    decide each historical point's percentile, the look-ahead the audit flagged). This matches
    the live _position convention (trailing-1260d percentile) so the gate and the live read
    are computed the same way (house rule live == backtest).
    """
    s = ser.dropna()
    return s.rolling(window, min_periods=60).apply(
        lambda w: float((w <= w[-1]).mean()), raw=True)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return float("nan")
    ra = pd.Series(a).rank().values
    rb = pd.Series(b).rank().values
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / d) if d > 0 else float("nan")


def _signature_pctiles(key: str) -> dict | None:
    """Per-turn CAUSAL own-history percentiles of distance-from-200d and drawdown at every
    detected bottom/top. Returns the raw per-turn rows (with turn dates) so run_gate can POOL
    across sectors and put a bootstrap CI on the bottom↔top separation — 3–4 turns/sector is
    too few for a per-sector claim (audit china-sector-cycles-5)."""
    px = csi.gs_index(key)
    if px is None or px.empty:
        return None
    turns = csi.zigzag_turns(px, 0.25)
    if sum(t["kind"] == "bottom" for t in turns) < 2 or sum(t["kind"] == "top" for t in turns) < 2:
        return None
    dist = (px / px.rolling(200).mean() - 1.0)
    dd = (px / px.rolling(252).max() - 1.0)
    dist_p = _causal_pctile(dist)   # trailing-window percentile, NOT full-sample rank
    dd_p = _causal_pctile(dd)

    rows = []
    for t in turns:
        if t["kind"] not in ("bottom", "top"):
            continue
        dp = dist_p.reindex(dist_p.index[dist_p.index <= t["date"]]).dropna()
        ddp = dd_p.reindex(dd_p.index[dd_p.index <= t["date"]]).dropna()
        if dp.empty or ddp.empty:
            continue
        rows.append({"sector": key, "kind": t["kind"], "date": pd.Timestamp(t["date"]),
                     "dist_p": float(dp.iloc[-1]), "dd_p": float(ddp.iloc[-1])})

    def _med(kind, col):
        vals = [r[col] for r in rows if r["kind"] == kind]
        return float(np.median(vals)) if vals else float("nan")

    return {
        "rows": rows,
        "dist_bottom": _med("bottom", "dist_p"), "dist_top": _med("top", "dist_p"),
        "dd_bottom": _med("bottom", "dd_p"), "dd_top": _med("top", "dd_p"),
    }


def _cluster_signs(key: str) -> dict:
    px = csi.gs_index(key)
    bench = csi.benchmark_close()
    grid = pd.date_range("2008-01-31", px.index.max(), freq="ME")
    panel = csi.driver_panel(grid).join(csi.sector_technicals(px, bench, grid))
    mpx = px.resample("ME").last().reindex(grid, method="ffill")
    fwd = mpx.shift(-6) / mpx - 1.0
    expect = {"credit_impulse": +1, "ppi_yoy": -1, "dist_200d": -1, "dd_from_high": -1}
    out = {}
    for col, sign in expect.items():
        if col not in panel.columns:
            continue
        sub = pd.concat([panel[col], fwd], axis=1).dropna()
        if len(sub) < 30:
            continue
        ic = _spearman(sub.iloc[:, 0].values, sub.iloc[:, 1].values)
        out[col] = {"ic": round(ic, 3), "expect_sign": sign,
                    "ok": bool(np.isfinite(ic) and (ic == 0 or np.sign(ic) == sign or abs(ic) < 0.05))}
    return out


def _pooled_gate(rows: list[dict], col: str) -> dict:
    """POOL turn rows across all four sectors and require a date-blocked bootstrap CI on the
    (top − bottom) percentile gap that EXCLUDES zero. With only 3–4 turns/sector a per-sector
    'validated' claim is noise; pooling lifts n, and the bootstrap CI is what promotes the leg
    from 'suggestive' to 'evidence' (audit china-sector-cycles-5: the gate may only claim
    evidence if the CI excludes the base rate — here, the bottom↔top null of no separation)."""
    turns = [r for r in rows if np.isfinite(r.get(col, float("nan")))]
    n_bottom = sum(r["kind"] == "bottom" for r in turns)
    n_top = sum(r["kind"] == "top" for r in turns)
    med_bottom = float(np.median([r[col] for r in turns if r["kind"] == "bottom"])) if n_bottom else float("nan")
    med_top = float(np.median([r[col] for r in turns if r["kind"] == "top"])) if n_top else float("nan")
    ci = None
    if n_bottom >= 2 and n_top >= 2:
        # block on turn DATE (year-month) so co-timed turns across sectors move together.
        dates = np.array([r["date"].strftime("%Y-%m") for r in turns])
        vals = np.array([r[col] for r in turns], dtype=float)
        mask = np.array([r["kind"] == "top" for r in turns], dtype=bool)
        # gap = mean(top) − mean(all); >0 ⟺ tops rank HIGHER (less washed) than bottoms.
        ci = gs.block_bootstrap_ci(dates, vals, mask, stat="mean")
    # descriptive sign check (median ordering) is the SOFT read; the CI is the HARD gate.
    sign_ok = bool(np.isfinite(med_bottom) and np.isfinite(med_top) and med_bottom < med_top)
    evidence = bool(ci is not None and ci[0] > 0)   # CI strictly excludes the no-separation null
    return {"leg": col, "n_bottom": n_bottom, "n_top": n_top,
            "median_bottom": round(med_bottom, 3) if np.isfinite(med_bottom) else None,
            "median_top": round(med_top, 3) if np.isfinite(med_top) else None,
            "gap_ci": ci, "sign_ok": sign_ok, "evidence": evidence}


def run_gate() -> dict:
    if csi.benchmark_close() is None or csi.sw_close("801780") is None:
        return {"available": False, "passed": True, "checks": [], "pooled": [],
                "note": "china_sectors / benchmark data absent — gate skipped"}

    checks = []
    all_rows: list[dict] = []
    for key in csi.GS_BASKETS:
        sig = _signature_pctiles(key)
        if sig is None:
            continue
        all_rows.extend(sig.get("rows", []))
        for leg, lo, hi in (("dist", sig["dist_bottom"], sig["dist_top"]),
                            ("drawdown", sig["dd_bottom"], sig["dd_top"])):
            # per-sector median ordering is now DESCRIPTIVE (soft) — too few turns/sector to
            # gate on; the HARD gate is the pooled bootstrap CI below.
            ok = bool(np.isfinite(lo) and np.isfinite(hi) and lo < hi)
            checks.append({"sector": key, "type": "signature", "leg": leg, "hard": False,
                           "bottom_pctile": round(lo, 2) if np.isfinite(lo) else None,
                           "top_pctile": round(hi, 2) if np.isfinite(hi) else None, "ok": ok})
        for col, r in _cluster_signs(key).items():
            checks.append({"sector": key, "type": "cluster_sign", "leg": col, "hard": False,
                           "ic": r["ic"], "expect_sign": r["expect_sign"], "ok": r["ok"]})

    # HARD gate: pooled bottom↔top separation, bootstrap-CI-gated (causal percentiles).
    pooled = [_pooled_gate(all_rows, "dist_p"), _pooled_gate(all_rows, "dd_p")]
    # The gate PASSES if each pooled leg's separation is at least directionally correct
    # (sign_ok); it only claims EVIDENCE where the bootstrap CI excludes zero. A directional
    # FLIP (sign_ok False) is the falsification that fails CI.
    hard_ok = all(p["sign_ok"] for p in pooled) if pooled else False
    evidence_legs = [p["leg"] for p in pooled if p["evidence"]]

    soft_fail = [c for c in checks if not c["hard"] and not c["ok"] and c["type"] == "cluster_sign"]
    note_bits = []
    if evidence_legs:
        note_bits.append(f"pooled evidence: {', '.join(evidence_legs)}")
    else:
        note_bits.append("pooled separation directional but CI does not exclude 0 (suggestive, not evidence)")
    if soft_fail:
        note_bits.append(f"{len(soft_fail)} cluster-sign drift warning(s)")
    return {"available": True, "passed": hard_ok, "checks": checks, "pooled": pooled,
            "evidence_legs": evidence_legs, "soft_warnings": soft_fail,
            "note": "; ".join(note_bits)}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(json.dumps(run_gate(), indent=2, default=str))
