"""Phase-1.5: point-in-time robustness of the claims->recession_risk leg.

The Phase-0 harness (scripts/validate_claims_recession.py) used STORED (latest-
revised) series. Two look-ahead sources could in principle have manufactured the
claims leg's incremental AUC:
  (1) REVISION look-ahead — latest-revised legs (esp. RECPROUSM156N, the Chauvet-
      Piger recession prob) "know" recessions better than their real-time prints.
  (2) TIMING look-ahead — a value stamped on its reference month was not actually
      published until weeks later.

This script re-measures the claims leg's incremental ΔAUC under both fixes:
  • REVISED-FULL  : original (stored, no lag), 1967-2026, 8 recessions — baseline.
  • LAGGED-FULL   : stored + realistic publication lags, 1967-2026, 8 recessions —
                    removes TIMING look-ahead while keeping power.
  • ALFRED-PIT    : sahm/recession_prob from the ALFRED initial-release archive,
                    realtime-TIMED (revision + timing honest), 1997-2026, 3 recessions
                    — removes REVISION look-ahead (low power; the dominant rigor).

Claims barely revise (~3%) and publish within days, so claims uses stored values in
all modes; the PIT-ness is applied to the OTHER legs. If the real-time base legs are
WEAKER (they are), claims has MORE room to add — so PIT, if anything, should help the
claims case. EBP has no ALFRED series (not a FRED series); it is the one leg without
revision-PIT (lagged-stored in PIT mode) — noted, and ΔAUC(claims) is robust to it
since base and +claims share the same EBP leg.

Run: .venv/bin/python -m scripts.validate_claims_recession_pit
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.fred import load_vintages  # noqa: E402
from lib import config  # noqa: E402
from scripts.validate_claims_recession import (  # noqa: E402
    EXIST, WEIGHTS, _monthly, _pctile, _usrec, auc, composite, fwd,
)

RC = config.load()["engine"]["conditions"]["recession"]
# publication lags (months) for the LAGGED-FULL mode
LAGS = {"claims": 0, "sahm": 1, "rprob": 2, "curve": 0, "ebp": 1}


def _legs_from_levels(ic4, sahm, rprob, dgs10, dgs2, tp, ebp, est, idx) -> pd.DataFrame:
    """Map raw monthly LEVELS -> the conditions.py 0..1 leg columns on `idx`."""
    P = pd.DataFrame(index=idx)
    def put(n, s): P[n] = (s.reindex(idx) if s is not None else np.nan)
    put("_ic4", ic4)
    P["leg_sahm"] = (sahm.reindex(idx) / RC["sahm_full"]).clip(0, 1) if sahm is not None else np.nan
    P["leg_rprob"] = (rprob.reindex(idx) / 100.0).clip(0, 1) if rprob is not None else np.nan
    P["leg_ebp_prob"] = est.reindex(idx).clip(0, 1) if est is not None else np.nan
    if dgs10 is not None and dgs2 is not None and tp is not None:
        curve = (dgs10 - dgs2) + tp
        lo, full = RC["curve_invert_level"], RC["curve_full_invert"]
        P["leg_curve"] = ((lo - curve.reindex(idx)) / (lo - full)).clip(0, 1)
    else:
        P["leg_curve"] = np.nan
    P["leg_ebp_level"] = _pctile(ebp.reindex(idx)).clip(0, 1) if ebp is not None else np.nan
    yoy = P["_ic4"].pct_change(12)
    P["leg_claims_yoy"] = (yoy / RC.get("claims_yoy_full", 0.40)).clip(0, 1)
    return P


def _rt_series(V, name, idx) -> pd.Series:
    """Real-time series from ALFRED initial releases: value first published, available
    at its realtime_start, asof-joined to each month in idx (last pub on/before)."""
    sub = V[V["series"] == name]
    if sub.empty:
        return pd.Series(np.nan, index=idx)
    s = sub.set_index("realtime_start")["value"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)


def panel_revised(start="1967-01", lag=False) -> pd.DataFrame:
    idx = pd.period_range(start, "2026-05", freq="M").to_timestamp()
    ic4 = _monthly("fred", "IC4WSA"); sahm = _monthly("fred", "SAHMREALTIME")
    rprob = _monthly("fred", "RECPROUSM156N")
    dgs10 = _monthly("fred", "DGS10"); dgs2 = _monthly("fred", "DGS2"); tp = _monthly("fred", "THREEFYTP10")
    e = None; est = None
    edf = __import__("lib.store", fromlist=["store"]).read("fedboard", "ebp")
    if edf is not None:
        edf = edf.copy(); edf.index = pd.to_datetime(edf.index)
        e = edf["ebp"].resample("MS").last(); est = edf["est_prob"].resample("MS").last()
    if lag:
        def L(s, k): return None if s is None else s.shift(LAGS[k])
        ic4, sahm, rprob = L(ic4, "claims"), L(sahm, "sahm"), L(rprob, "rprob")
        e = L(e, "ebp"); est = L(est, "ebp")
    P = _legs_from_levels(ic4, sahm, rprob, dgs10, dgs2, tp, e, est, idx)
    P["usrec"] = _usrec().reindex(idx).ffill(limit=1)
    return P


def panel_pit(start="1997-01") -> pd.DataFrame:
    """sahm/recession_prob from ALFRED (revision+timing honest); curve stored (rates
    don't revise); EBP stored+lag (no ALFRED); claims stored (barely revises)."""
    idx = pd.period_range(start, "2026-05", freq="M").to_timestamp()
    V = load_vintages()
    sahm = _rt_series(V, "SAHMREALTIME", idx)
    rprob = _rt_series(V, "RECPROUSM156N", idx)
    tp = _rt_series(V, "THREEFYTP10", idx)               # ACM term premium (in archive)
    ic4 = _monthly("fred", "IC4WSA")
    dgs10 = _monthly("fred", "DGS10"); dgs2 = _monthly("fred", "DGS2")
    edf = __import__("lib.store", fromlist=["store"]).read("fedboard", "ebp")
    e = est = None
    if edf is not None:
        edf = edf.copy(); edf.index = pd.to_datetime(edf.index)
        e = edf["ebp"].resample("MS").last().shift(LAGS["ebp"])
        est = edf["est_prob"].resample("MS").last().shift(LAGS["ebp"])
    P = _legs_from_levels(ic4, sahm, rprob, dgs10, dgs2, tp.reindex(idx), e, est, idx)
    P["usrec"] = _usrec().reindex(idx).ffill(limit=1)
    return P


def evaluate(P: pd.DataFrame, label: str):
    ys = {"concurrent": fwd(P["usrec"], 0), "6m": fwd(P["usrec"], 6), "12m": fwd(P["usrec"], 12)}
    base = composite(P)
    wc = composite(P, {"claims": (P["leg_claims_yoy"], 0.5)})
    onsets = int((P["usrec"].diff() == 1).sum())
    print(f"\n=== {label}  ({P.index.min().date()}..{P.index.max().date()}, {onsets} onsets) ===")
    print(f"{'':<22}" + "".join(f"{h:>12}" for h in ys))
    print(f"{'claims leg (solo)':<22}" + "".join(f"{auc(P['leg_claims_yoy'],ys[h])[0]:>12.3f}" for h in ys))
    print(f"{'base composite':<22}" + "".join(f"{auc(base,ys[h])[0]:>12.3f}" for h in ys))
    print(f"{'base + claims (0.5)':<22}" + "".join(f"{auc(wc,ys[h])[0]:>12.3f}" for h in ys))
    d = {h: auc(wc, ys[h])[0] - auc(base, ys[h])[0] for h in ys}
    print(f"{'ΔAUC (claims)':<22}" + "".join(f"{d[h]:>+12.3f}" for h in ys))
    return d


def main() -> int:
    print("Point-in-time robustness of the claims -> recession_risk leg (ΔAUC at w=0.5)")
    d_rev = evaluate(panel_revised(lag=False), "REVISED-FULL (stored, no lag) — Phase-0 baseline")
    d_lag = evaluate(panel_revised(lag=True), "LAGGED-FULL (stored + publication lags)")
    d_pit = evaluate(panel_pit(), "ALFRED-PIT (real-time sahm/prob; 1997+)")

    print("\n" + "=" * 64)
    pos = lambda d: (d["6m"] > 0 and d["12m"] > 0)
    survives = pos(d_lag) and (d_pit["6m"] > -0.01 and d_pit["12m"] > -0.01)
    print(f"VERDICT: claims leg {'SURVIVES point-in-time' if survives else 'WEAKENS under PIT — reconsider'}")
    print(f"  revised-full ΔAUC 6m/12m {d_rev['6m']:+.3f}/{d_rev['12m']:+.3f}")
    print(f"  lagged-full  ΔAUC 6m/12m {d_lag['6m']:+.3f}/{d_lag['12m']:+.3f}  (timing-honest, 8 recessions)")
    print(f"  alfred-pit   ΔAUC 6m/12m {d_pit['6m']:+.3f}/{d_pit['12m']:+.3f}  (revision-honest, 3 recessions, low power)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
