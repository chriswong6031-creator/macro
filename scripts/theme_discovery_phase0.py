"""Phase-0 for the theme-discovery radar — is a flagged candidate cluster (a) a REAL,
persistent theme, and (b) does flagging it early carry any forward-return edge?

Honest priors (research + our own rotation Phase-0): detection works but is noisy; early
ENTRY edge ≈ 0 and is negatively skewed if you buy the stretched names. This script
confirms that on our data so the live radar can cite a measured verdict, not a vibe.

Method (PIT walk, no look-ahead): at monthly steps over the cache, re-run
engine.theme_discovery.discover_candidates(asof=date) on data up to that date only, then
measure for each flagged candidate over the next `fwd_d` days:
  * PERSISTENCE — does the cluster's mean pairwise correlation stay elevated (cohesion at
    t+fwd ≥ 0.8 × cohesion at t)?  → is it a real theme or noise?
  * FORWARD EDGE — the cluster's equal-weight return minus SPY over the window (expect ~0;
    a positive-skew front-run edge would be the surprise).

Writes data/theme_discovery/phase0.json. Usage: python -m scripts.theme_discovery_phase0
Additive / never fatal.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("theme_discovery_phase0")

STEP_D = 21
FWD_D = 63
MIN_HISTORY = 300       # need enough cache before the first as-of


def _mean_offdiag(c: np.ndarray) -> float:
    n = c.shape[0]
    return float((np.nansum(c) - np.trace(c)) / (n * (n - 1))) if n >= 2 else float("nan")


def main() -> int:
    from engine.equity_factors import _closes
    from engine.theme_discovery import discover_candidates
    closes = _closes()
    if closes is None or closes.empty:
        log.warning("no closes — skipping")
        return 0
    spy = store.read("yahoo", "SPY")
    spy = spy["close"].astype(float) if spy is not None and "close" in spy.columns else None
    idx = closes.index
    rets = closes.pct_change(fill_method=None)

    persist, fwd_rel, n_flagged = [], [], 0
    starts = range(MIN_HISTORY, len(idx) - FWD_D, STEP_D)
    for i in starts:
        asof = idx[i]
        d = discover_candidates("us", asof=asof)
        if not d or not d.get("candidates"):
            continue
        fwd_end = idx[i + FWD_D]
        for cand in d["candidates"]:
            tk = [m["ticker"] for m in cand["constituents"] if m["ticker"] in rets.columns]
            if len(tk) < 4:
                continue
            n_flagged += 1
            # forward window starts the day AFTER discovery (idx[i+1]) so the EW cluster
            # return spans price[asof]→price[fwd_end] — ALIGNED with the SPY benchmark
            # window below (no extra entry-day return leaking into the relative number).
            fwd_win = rets.loc[idx[i + 1]:fwd_end, tk]
            coh_fwd = _mean_offdiag(fwd_win.corr().to_numpy()) if len(fwd_win) > 20 else np.nan
            if np.isfinite(coh_fwd) and cand["cohesion"]:
                persist.append(1.0 if coh_fwd >= 0.8 * cand["cohesion"] else 0.0)
            # forward EW rel return vs SPY
            ew = float((1.0 + fwd_win.mean(axis=1)).prod() - 1.0)
            if spy is not None:
                s = spy.reindex(idx).ffill()
                b = float(s.loc[fwd_end] / s.loc[asof] - 1.0)
                fwd_rel.append(ew - b)

    def _summ(a):
        a = np.asarray(a, float)
        a = a[np.isfinite(a)]
        if len(a) == 0:
            return {"n": 0}
        return {"n": int(len(a)), "mean": round(float(a.mean()), 4),
                "median": round(float(np.median(a)), 4),
                "p25": round(float(np.percentile(a, 25)), 4),
                "p75": round(float(np.percentile(a, 75)), 4),
                "skew": round(float(pd.Series(a).skew()), 3)}

    pr = round(float(np.mean(persist)), 3) if persist else None
    rel = _summ(fwd_rel)
    out = {
        "schema": "theme_discovery_phase0.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_d": STEP_D, "fwd_d": FWD_D, "n_flags": n_flagged,
        "persistence_rate": pr,          # fraction of flags whose cohesion held over fwd
        "fwd_rel_return": rel,           # cluster EW minus SPY over fwd (expect ~0)
        "verdict": ("display_only_candidate_radar — flags are coherent ~"
                    f"{int((pr or 0)*100)}% persist, but forward EW-vs-SPY mean "
                    f"{rel.get('mean')} (skew {rel.get('skew')}) shows NO front-run edge. "
                    "Use as a watchlist / avoid-the-peak / diversification radar, never a "
                    "buy signal; never feeds a score."),
    }
    p = config.data_dir() / "theme_discovery" / "phase0.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", p)
    print(f"\nn_flags {n_flagged} | persistence {pr} | fwd_rel {rel}")
    print(out["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
