"""Phase-0 (RESEARCH-ONLY) for the offshore-attention chip (P2).

Gate: does abnormal Wikipedia attention add cross-sectional return-predictive
information INCREMENTALLY over the named incumbents — momentum (residual-alpha) and
the VIX regime — net of multiple-testing and a DSR haircut?

Honest prior = FAIL -> display-only. Da-Engelberg-Gao (2011): retail attention
precedes SHORT-HORIZON REVERSAL, concentrated in small/illiquid names and decayed
post-GME. The 5d horizon is the key test and the reversal prior predicts a NEGATIVE
IC there (a fade caution, not a tradable long). Cross-sectional test; imports the
validation primitives + the insider_phase0 helpers; WIRES NOTHING.

API-window caveat: /per-article serves from 2015-07 only, so the backtest span is
materially shorter than the insider panel (2006->) -> limited DSR power. NDI has no
per-ticker series in this repo, so the incremental test is vs momentum + VIX only
(stated, not invented).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402
from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from lib import config  # noqa: E402
from scripts.insider_phase0 import month_grid, quintile_ls, _split_half_ic  # noqa: E402

HORIZONS = [5, 21, 63]
Z_WINDOW = 90


def _z_panel() -> pd.DataFrame:
    """Causal daily abnormal-attention z per ticker (cols=tickers) from
    data/attention/*.parquet. Baseline is shifted off the trailing 5d window so
    there is no look-ahead."""
    adir = config.data_dir() / "attention"
    cols = {}
    for p in sorted(adir.glob("*.parquet")):
        try:
            v = pd.read_parquet(p)["views"].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(v) < Z_WINDOW:
            continue
        s = np.log1p(v.astype(float))
        recent = s.rolling(5, min_periods=3).mean()
        prior = s.shift(5)                                   # strictly prior baseline -> causal
        z = (recent - prior.rolling(Z_WINDOW, min_periods=Z_WINDOW // 2).mean()) \
            / prior.rolling(Z_WINDOW, min_periods=Z_WINDOW // 2).std()
        cols[p.stem] = z.clip(-3, 6)
    return pd.DataFrame(cols) if cols else pd.DataFrame()


def _alpha_z() -> pd.Series:
    """Per-ticker momentum incumbent = the residual-alpha z (alpha.json per_ticker)."""
    ap = config.ROOT / config.load()["storage"]["site_dir"] / "factordata" / "alpha.json"
    if not ap.exists():
        return pd.Series(dtype=float)
    import json
    pt = (json.loads(ap.read_text()) or {}).get("per_ticker", {})
    return pd.Series({k: v.get("alpha") for k, v in pt.items() if v.get("alpha") is not None})


def main() -> int:
    z_panel = _z_panel()
    if z_panel.empty:
        print("no attention data on disk (collectors/wiki_pageviews not run yet) — "
              "cannot run Phase-0.\nVERDICT: DISPLAY (honest prior; revisit once "
              "data/attention/*.parquet exists, API window 2015-07->).")
        return 0

    closes = _closes()
    ns = _names_sectors()
    sec = pd.Series({t: (ns.get(t, (t, None))[1]) for t in closes.columns})
    mom = _alpha_z()                                         # cross-sectional momentum incumbent
    vix = closes["^VIX"] if "^VIX" in closes.columns else None

    rows, pvals = {}, {}
    for h in HORIZONS:
        grid = [d for d in month_grid(closes.index, h) if d in z_panel.index]
        fwd = closes.pct_change(h, fill_method=None).shift(-h)
        raw_ic, sn_ic, res_ic, vlo_ic, vhi_ic = [], [], [], [], []
        vthi = vix.quantile(0.66) if vix is not None else None
        vtlo = vix.quantile(0.33) if vix is not None else None
        for d in grid:
            if d not in fwd.index:
                continue
            fr = fwd.loc[d].dropna()
            z = z_panel.loc[d].reindex(fr.index).dropna()
            if len(z) < 10:
                continue
            f2 = fr.reindex(z.index)
            raw_ic.append(V.rank_ic(z, f2))
            snz = z - z.groupby(sec.reindex(z.index)).transform("mean")
            sn_ic.append(V.rank_ic(snz, f2))
            # incremental vs momentum: residual of attention-z on momentum-z, per date
            m = mom.reindex(z.index)
            j = pd.concat([z.rename("z"), m.rename("m")], axis=1).dropna()
            if len(j) >= 10:
                b = np.polyfit(j["m"], j["z"], 1)
                resid = j["z"] - (b[0] * j["m"] + b[1])
                res_ic.append(V.rank_ic(resid, f2.reindex(resid.index)))
            # VIX regime buckets
            if vix is not None and d in vix.index and pd.notna(vix.loc[d]):
                (vhi_ic if vix.loc[d] >= vthi else vlo_ic if vix.loc[d] <= vtlo else []).append(
                    V.rank_ic(z, f2))
        for label, ics in (("raw", raw_ic), ("SN", sn_ic), ("resid_vs_mom", res_ic),
                           ("vix_lo", vlo_ic), ("vix_hi", vhi_ic)):
            summ = V.ic_summary([x for x in ics if pd.notna(x)], periods_per_year=12)
            if summ.get("n", 0) >= 6:
                summ.update(_split_half_ic(pd.Series([x for x in ics if pd.notna(x)])))
                rows[f"{label}@{h}"] = summ
                if label in ("raw", "SN", "resid_vs_mom") and summ.get("p_hac") is not None:
                    pvals[f"{label}@{h}"] = summ["p_hac"]

    bh = V.benjamini_hochberg(pvals, alpha=0.10)
    for k, q in bh.items():
        rows[k]["q_fdr"] = q["q"]
        rows[k]["survives_fdr"] = q["reject"]

    # honest L/S DSR on the raw z (top vs bottom quintile), n_trials = all configs tried
    R = closes.pct_change(fill_method=None)
    grid63 = month_grid(closes.index, 63)
    ls = quintile_ls(R, z_panel.reindex(R.index), grid63, n_trials=max(len(pvals), 1))

    print(f"span tickers={z_panel.shape[1]} dates={z_panel.shape[0]} | "
          f"momentum names={len(mom)} | VIX={'yes' if vix is not None else 'NO'}")
    print(f"{'signal':18s} {'mean_ic':>8} {'t_hac':>7} {'p':>7} {'q':>6} {'fdr':>5}")
    for k, s in rows.items():
        print(f"{k:18s} {str(s.get('mean_ic')):>8} {str(s.get('t_hac')):>7} "
              f"{str(s.get('p_hac')):>7} {str(s.get('q_fdr')):>6} {str(s.get('survives_fdr')):>5}")
    survivors = [k for k in pvals if bh.get(k, {}).get("reject")]
    pos_surv = [k for k in survivors if (rows[k].get("mean_ic") or 0) > 0]
    print(f"\nL/S quintile (raw z): sharpe={ls.get('sharpe')} dsr={ls.get('dsr')} "
          f"({ls.get('verdict')}) | n_trials={max(len(pvals),1)}")
    print("FDR survivors:", survivors or "none", "| positive-IC survivors:", pos_surv or "none")

    go = bool(pos_surv) and ls.get("dsr", 0.0) >= 0.90
    print("\nVERDICT:", "PROMOTE-CANDIDATE (follow-up, never auto-wire): " + ", ".join(pos_surv)
          if go else "DISPLAY (no POSITIVE incremental edge survives FDR+DSR — "
                     "attention is a short-horizon fade caution, not a tradable long)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
