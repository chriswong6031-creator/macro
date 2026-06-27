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


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return float("nan")
    ra = pd.Series(a).rank().values
    rb = pd.Series(b).rank().values
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / d) if d > 0 else float("nan")


def _signature_check(key: str) -> dict | None:
    px = csi.gs_index(key)
    if px is None or px.empty:
        return None
    turns = csi.zigzag_turns(px, 0.25)
    if sum(t["kind"] == "bottom" for t in turns) < 2 or sum(t["kind"] == "top" for t in turns) < 2:
        return None
    dist = (px / px.rolling(200).mean() - 1.0)
    dd = (px / px.rolling(252).max() - 1.0)
    dist_p = dist.rank(pct=True)
    dd_p = dd.rank(pct=True)

    def at(kind, ser):
        vals = []
        for t in turns:
            if t["kind"] != kind:
                continue
            v = ser.reindex(ser.index[ser.index <= t["date"]]).dropna()
            if not v.empty:
                vals.append(float(v.iloc[-1]))
        return float(np.median(vals)) if vals else float("nan")

    return {
        "dist_bottom": at("bottom", dist_p), "dist_top": at("top", dist_p),
        "dd_bottom": at("bottom", dd_p), "dd_top": at("top", dd_p),
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


def run_gate() -> dict:
    if csi.benchmark_close() is None or csi.sw_close("801780") is None:
        return {"available": False, "passed": True, "checks": [],
                "note": "china_sectors / benchmark data absent — gate skipped"}

    checks = []
    hard_ok = True
    for key in csi.GS_BASKETS:
        sig = _signature_check(key)
        if sig is None:
            continue
        for leg, lo, hi in (("dist", sig["dist_bottom"], sig["dist_top"]),
                            ("drawdown", sig["dd_bottom"], sig["dd_top"])):
            ok = bool(np.isfinite(lo) and np.isfinite(hi) and lo < hi)
            hard_ok = hard_ok and ok
            checks.append({"sector": key, "type": "signature", "leg": leg, "hard": True,
                           "bottom_pctile": round(lo, 2) if np.isfinite(lo) else None,
                           "top_pctile": round(hi, 2) if np.isfinite(hi) else None, "ok": ok})
        for col, r in _cluster_signs(key).items():
            checks.append({"sector": key, "type": "cluster_sign", "leg": col, "hard": False,
                           "ic": r["ic"], "expect_sign": r["expect_sign"], "ok": r["ok"]})

    soft_fail = [c for c in checks if not c["hard"] and not c["ok"]]
    return {"available": True, "passed": hard_ok, "checks": checks,
            "soft_warnings": soft_fail,
            "note": f"{len(soft_fail)} cluster-sign drift warning(s)" if soft_fail else "all clear"}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(json.dumps(run_gate(), indent=2, default=str))
