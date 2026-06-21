"""Incremental-IC scorecard — the institutional honesty test (research/INSTITUTIONAL_ROADMAP.md).

Raw rank-IC conflates genuine information with repackaged common-factor exposure: a
"selection" signal can score well simply because it IS momentum / low-vol / size. This
measures, for each price-only selection signal, the RAW cross-sectional IC vs the
INCREMENTAL IC after neutralizing the cross-section against the style factors we already
own (market beta, size proxy, 12-1 momentum, low-vol) — excluding a signal's own factor
so the test is not trivially zero. The share that survives neutralization is the only part
that is independent information.

Honest caveats it stamps: the panel is data/stocks = 114 currently-listed survivor
mega-caps, so even the incremental IC is an OPTIMISTIC bound; the trustworthy content is
the RELATIVE collapse (raw -> incremental). Multiple-testing N is logged at generation to
the canonical data/trial_ledger.jsonl (standing up the persistent ledger), and the per-date
IC series is HAC-t'd + BH-FDR'd across signals.

Run: .venv/bin/python -m scripts.measure_incremental_ic
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from lib import store  # noqa: E402
from engine import validation as V  # noqa: E402
from engine import predictive_signals as PS  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

REBAL = 21          # monthly rebalance
FWD = [21, 63]      # forward horizons (1m, 3m)
FORM, SKIP = 252, 21


def load_panel():
    tics = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/stocks/*.parquet"))
    close, vol = {}, {}
    for t in tics:
        df = store.read("stocks", t)
        if df is None or df.empty or "close" not in df:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if len(df) < FORM + 60:
            continue
        close[t] = df["close"]
        vol[t] = df["close"] * df.get("volume", np.nan)   # dollar volume
    closes = pd.DataFrame(close).sort_index()
    dvol = pd.DataFrame(vol).reindex(closes.index)
    mkt = store.read("yahoo", "_GSPC")
    mkt = (mkt["close"] if mkt is not None else closes.mean(axis=1)).reindex(closes.index).ffill()
    return closes, dvol, mkt


def factor_loadings(closes, dvol, mkt, pos):
    """Causal style-factor loadings at integer index `pos` (as-of that date)."""
    w = closes.iloc[max(0, pos - FORM):pos + 1]
    if len(w) < 120:
        return None
    rets = w.pct_change()
    mret = mkt.iloc[max(0, pos - FORM):pos + 1].pct_change().reindex(rets.index)
    mvar = mret.var()
    beta = rets.apply(lambda c: c.cov(mret)) / (mvar if mvar else np.nan)     # market beta
    size = np.log(dvol.iloc[max(0, pos - 60):pos + 1].median().replace(0, np.nan))  # liquidity/size proxy
    mom = w.iloc[-(SKIP + 1)] / w.iloc[0] - 1.0 if len(w) >= SKIP + 2 else pd.Series(dtype=float)  # 12-1
    lowvol = -(rets.iloc[-126:].std() * np.sqrt(252))                          # low-vol (higher=calmer)
    return pd.DataFrame({"beta": beta, "size": size, "mom": mom, "lowvol": lowvol})


def signals_at(closes, asof, pos):
    """Cross-sectional selection signals as-of a date (causal)."""
    return {
        "mom_12_1": (PS.mom_12_1(closes, asof), {"mom"}),        # exclude self-factor
        "near_52w_high": (PS.near_52w_high(closes, asof), set()),
        "fip_continuity": (PS.fip_continuity(closes, asof), set()),
    }


def main():
    closes, dvol, mkt = load_panel()
    idx = closes.index
    print(f"[incr-ic] panel {closes.shape[1]} names x {len(idx)} days "
          f"({idx.min().date()}..{idx.max().date()})")
    grid = list(range(FORM, len(idx) - max(FWD) - 1, REBAL))

    ledger = TrialLedger()      # canonical data/trial_ledger.jsonl (stand it up)
    results = {}
    for h in FWD:
        # accumulate per-signal date->cross-sections
        sig_by = {}; fwd_by = {}; load_by = {}
        for pos in grid:
            d = idx[pos]
            load = factor_loadings(closes, dvol, mkt, pos)
            if load is None:
                continue
            fwd = closes.iloc[pos + h] / closes.iloc[pos] - 1.0
            for key, (sig, excl) in signals_at(closes, d, pos).items():
                if sig is None or sig.empty:
                    continue
                use = load.drop(columns=[c for c in excl if c in load.columns], errors="ignore")
                sig_by.setdefault(key, {})[d] = sig
                fwd_by.setdefault(key, {})[d] = fwd
                load_by.setdefault(key, {})[d] = use
        for key in sig_by:
            ledger.log_grid([{"signal": key, "h": h, "fwd": f} for f in FWD],
                            family=f"incremental_ic:{key}")
            r = V.incremental_ic(sig_by[key], fwd_by[key], load_by[key], periods_per_year=12)
            results.setdefault(key, {})[f"h{h}"] = r
            raw, inc = r["raw"], r["incremental"]
            print(f"  [{key:16s} h{h:>2}] raw IC {raw.get('mean_ic')} (t {raw.get('t_hac')}) "
                  f"-> incremental {inc.get('mean_ic')} (t {inc.get('t_hac')})  "
                  f"survives={r.get('surviving_frac')}")

    # BH-FDR across (signal,horizon) on the INCREMENTAL p-values (the harder bar)
    pvals = {f"{k}:{hk}": (v[hk]["incremental"].get("p_hac"))
             for k, v in results.items() for hk in v if v[hk]["incremental"].get("p_hac") is not None}
    fdr = V.benjamini_hochberg(pvals, alpha=0.10)

    payload = {
        "schema": "incremental_ic.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": {"n_names": int(closes.shape[1]), "source": "data/stocks (survivor mega-caps)",
                     "survivorship": "BIASED — incremental IC is itself an OPTIMISTIC bound; "
                                     "the trustworthy content is the RELATIVE raw->incremental collapse"},
        "neutralized_against": ["market_beta", "size(log $vol)", "mom_12_1", "low_vol"],
        "fwd_horizons": FWD, "rebalance_days": REBAL,
        "results": results, "incremental_fdr": fdr,
        "trial_ledger": "data/trial_ledger.jsonl",
    }
    os.makedirs("data/strategies", exist_ok=True)
    with open("data/strategies/incremental_ic.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print("[incr-ic] wrote data/strategies/incremental_ic.json")
    _report(payload)


def _report(p):
    L = ["# Incremental IC — how much of our selection edge is real (vs repackaged factors)\n",
         f"_Generated {p['generated_utc']}_ · universe {p['universe']['n_names']} survivor mega-caps · "
         f"neutralized against {', '.join(p['neutralized_against'])}\n",
         "> Even the incremental IC is an **optimistic survivor bound**; the signal is the **relative collapse** "
         "raw→incremental. Multiple-testing N logged to `data/trial_ledger.jsonl`; incremental p-values BH-FDR'd.\n",
         "\n| signal | h | raw IC | raw t(HAC) | incremental IC | incr t(HAC) | survives | FDR reject |",
         "|---|--:|--:|--:|--:|--:|--:|:--:|"]
    for k, v in p["results"].items():
        for hk, r in v.items():
            raw, inc = r["raw"], r["incremental"]
            fdr = p["incremental_fdr"].get(f"{k}:{hk}", {})
            L.append(f"| {k} | {hk[1:]} | {raw.get('mean_ic')} | {raw.get('t_hac')} | "
                     f"{inc.get('mean_ic')} | {inc.get('t_hac')} | {r.get('surviving_frac')} | "
                     f"{'✓' if fdr.get('reject') else '·'} |")
    L.append("\n**Read:** a signal whose incremental IC collapses toward 0 (low `survives`, no FDR-✓) carries little "
             "information beyond the style factors we already own — its raw IC was mostly repackaged beta/size/"
             "momentum/low-vol. That de-biasing is the institutional point: rank on what *survives*, not raw IC.\n")
    os.makedirs("reports", exist_ok=True)
    with open("reports/incremental-ic.md", "w") as f:
        f.write("\n".join(L) + "\n")
    print("[incr-ic] wrote reports/incremental-ic.md")


if __name__ == "__main__":
    main()
