#!/usr/bin/env python3
"""Base-scanner Phase-0 — does a constructive-base / breakout-proximity signal add
predictive value, as a standalone OR (more likely) as a confirmer on a price/alpha
signal?

The competitor's "Base Scanner" flags tight consolidations near a breakout pivot
(IBD / Minervini). We are skeptical: a base/pivot signal is a TIMING flavour, and a
parallel session already found the setups engine's OTHER timing leg (cycle-entry +
reversal) has IC<0 / is cosmetic on this universe (setup_score_phase0). So the prior
is that this validates weakly too — a clean NO-GO would say "don't build the IBD
pattern zoo," and a GO would justify a *lightweight* confirmer chip (never the zoo).

Signals (price-only — no volume needed, so this is NOT data-blocked like RVOL):
  * tight       = -(40d realized vol)            consolidation tightness (higher=tighter)
  * pivot_prox  = close / 60d-high              near 1.0 = sitting under the pivot
  * base        = z(tight) + z(pivot_prox)      the scanner's own "constructive base" score
  * mom         = 12-1 momentum                 the base signal a scanner would confirm

Universe: data/stocks/*.parquet (110 deep-history names; curated survivors — fair for
an interaction test, discount any standalone result for survivorship). Same gates as
the insider/factor/RVOL phase-0s (engine/validation.py): rank IC + Newey-West t,
Benjamini-Hochberg FDR, Deflated Sharpe + block-bootstrap on the L/S.

Run:  python3 scripts/base_scanner_phase0.py [--start 1995]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402
from engine.validation import (  # noqa: E402
    benjamini_hochberg, block_bootstrap_ci, deflated_sharpe, dsr_verdict,
    ic_summary, rank_ic, ret_moments)

COST_BPS = 5.0
HORIZONS = (21, 63)


def load_closes() -> pd.DataFrame:
    sdir = config.data_dir() / "stocks"
    cols = {}
    for p in sorted(sdir.glob("*.parquet")):
        df = pd.read_parquet(p).sort_index()
        if "close" in df.columns:
            cols[p.stem] = df["close"]
    return pd.DataFrame(cols).sort_index()


def signals(close: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    R = close.pct_change(fill_method=None)
    mom = R.shift(21).rolling(252, min_periods=200).sum()              # 12-1 momentum
    tight = -R.rolling(40, min_periods=30).std()                       # higher = tighter base
    hi60 = close.rolling(60, min_periods=45).max()
    pivot_prox = close / hi60                                          # near 1 = under the pivot

    def _xz(df):                                                       # daily cross-sectional z
        return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)

    base = _xz(tight) + _xz(pivot_prox)                               # the scanner's own score
    return R, {"mom": mom, "tight": tight, "pivot_prox": pivot_prox, "base": base}


def month_grid(index, warmup, horizon):
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc >= warmup and loc + horizon < len(index):
            out.append(d[-1])
    return out


def conditional_split_ic(base, cond, fwd, min_total=30, min_side=10):
    """IC of `base` vs `fwd` WITHIN the high- vs low-`cond` half of the cross-section.
    The paired diff is the confirmer test: does the base-pattern condition sharpen the
    base signal's predictive power? (nan, nan) if too few names."""
    j = pd.concat([pd.Series(cond).rename("c"), pd.Series(base).rename("b"),
                   pd.Series(fwd).rename("f")], axis=1).dropna()
    if len(j) < min_total:
        return float("nan"), float("nan")
    med = j["c"].median()
    hi_h, lo_h = j[j["c"] >= med], j[j["c"] < med]
    if len(hi_h) < min_side or len(lo_h) < min_side:
        return float("nan"), float("nan")
    return rank_ic(hi_h["b"], hi_h["f"]), rank_ic(lo_h["b"], lo_h["f"])


def ls_net(R, score, grid, long_filter=None):
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        s = score.loc[d].dropna() if d in score.index else pd.Series(dtype=float)
        if len(s) < 20:
            continue
        hi_q, lo_q = s.quantile(0.8), s.quantile(0.2)
        if not (hi_q > lo_q):
            continue
        top, bot = s[s >= hi_q].index, s[s <= lo_q].index
        if long_filter is not None and d in long_filter.index:
            ok = long_filter.loc[d].reindex(top).fillna(False)
            top = top[ok.values]
        if len(top) and len(bot):
            w.loc[d, top] = 1.0 / len(top)
            w.loc[d, bot] = -1.0 / len(bot)
    w = w.replace(0.0, np.nan).ffill().fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    return gross - (COST_BPS / 1e4) * turn


def bt_stats(net, n_trials):
    m = ret_moments(net)
    if not m:
        return None
    dsr = deflated_sharpe(m[0], m[1], m[2], m[3], n_trials=n_trials, trading_year=252)
    bc = block_bootstrap_ci(net, ann=252)
    return {"sharpe": round(float(m[0] * np.sqrt(252)), 2),
            "cum_pct": round(float(((1 + net).prod() - 1) * 100), 1),
            "dsr": dsr["dsr"] if dsr else None,
            "verdict": dsr_verdict(dsr["dsr"]) if dsr else None,
            "p_gt0": bc.get("sharpe_gt0_prob")}


def run_horizon(close, R, sig, H, start):
    fwd = close.pct_change(H, fill_method=None).shift(-H)
    grid = [d for d in month_grid(close.index, 280, H) if d.year >= start]
    standalone = {c: [] for c in ("mom", "tight", "pivot_prox", "base")}
    cond = {"tight": {"diff": []}, "pivot_prox": {"diff": []}}   # confirmer: condition mom on each
    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if len(fr) < 20:
            continue
        for c in standalone:
            if d in sig[c].index:
                standalone[c].append(rank_ic(sig[c].loc[d].reindex(fr.index), fr))
        mm = sig["mom"].loc[d].reindex(fr.index) if d in sig["mom"].index else None
        if mm is None:
            continue
        for cnd in ("tight", "pivot_prox"):
            cc = sig[cnd].loc[d].reindex(fr.index) if d in sig[cnd].index else None
            if cc is None:
                continue
            ih, il = conditional_split_ic(mm, cc, fr)
            if np.isfinite(ih) and np.isfinite(il):
                cond[cnd]["diff"].append(ih - il)

    ppy = 12
    out = {"horizon": H, "rebalances": len(grid),
           "span": f"{grid[0].date()}..{grid[-1].date()}" if grid else "n/a",
           "standalone": {}, "uplift": {}, "pvals": {}}
    for c, lst in standalone.items():
        s = ic_summary(pd.Series(lst).dropna(), periods_per_year=ppy)
        out["standalone"][c] = s
        if s.get("p_hac") is not None:
            out["pvals"][f"{c}_IC@{H}"] = s["p_hac"]
    for cnd, d in cond.items():
        s = ic_summary(pd.Series(d["diff"]).dropna(), periods_per_year=ppy)
        out["uplift"][cnd] = s
        if s.get("p_hac") is not None:
            out["pvals"][f"mom|{cnd}_uplift@{H}"] = s["p_hac"]

    # L/S: the base score itself, and base-confirmed momentum (long leg in a tight base
    # near pivot). NB the confirmed long leg is a SUBSET of the momentum long leg, so any
    # Sharpe lift is partly mechanical concentration — it is supporting colour, NOT a GO
    # gate. n_trials reflects the whole search (signals × horizons × L/S variants).
    N_TRIALS = 14
    tight_ok = sig["tight"].gt(sig["tight"].median(axis=1), axis=0)
    near_ok = sig["pivot_prox"].ge(0.92) & sig["pivot_prox"].le(1.001)
    confirmed = tight_ok & near_ok
    out["ls_base"] = bt_stats(ls_net(R, sig["base"], grid), n_trials=N_TRIALS)
    out["ls_mom_base"] = bt_stats(ls_net(R, sig["mom"], grid), n_trials=N_TRIALS)
    out["ls_mom_baseconfirmed"] = bt_stats(ls_net(R, sig["mom"], grid, long_filter=confirmed), n_trials=N_TRIALS)
    return out


def _fmt(x, p=4, sign=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "  n/a"
    return f"{x:+.{p}f}" if sign else f"{x:.{p}f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1995)
    args = ap.parse_args()
    close = load_closes()
    if close.empty:
        print("no data/stocks closes"); return 1
    close = close[close.index.year >= args.start - 2]
    R, sig = signals(close)

    results = {"universe": close.shape[1], "cost_bps": COST_BPS, "horizons": {}}
    pvals = {}
    for H in HORIZONS:
        r = run_horizon(close, R, sig, H, args.start)
        results["horizons"][str(H)] = r
        pvals.update(r["pvals"])
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    results["fdr_survivors"] = sorted([k for k, v in fdr.items() if v["reject"]])

    # Verdict rests on the CLEAN, size-controlled tests only: the base score's own IC
    # (positive + FDR) or the conditional-IC confirmer uplift (positive + FDR). The
    # base-confirmed L/S is NOT a GO gate — its long leg is a concentrated subset
    # (mechanical Sharpe lift) on a survivorship-biased universe. We also flag when the
    # base score is significantly NEGATIVE (anti-predictive — the scanner is wrong-signed).
    go_reasons, neg_flags = [], []
    for H in HORIZONS:
        r = results["horizons"][str(H)]
        bic = r["standalone"]["base"]
        if (bic.get("mean_ic") or 0) > 0 and fdr.get(f"base_IC@{H}", {}).get("reject"):
            go_reasons.append(f"base IC positive & survives FDR @ {H}d")
        if (bic.get("mean_ic") or 0) < 0 and fdr.get(f"base_IC@{H}", {}).get("reject"):
            neg_flags.append(f"base IC significantly NEGATIVE @ {H}d ({bic.get('mean_ic'):+.3f})")
        for cnd in ("tight", "pivot_prox"):
            u = r["uplift"][cnd]
            if (u.get("mean_ic") or 0) > 0 and fdr.get(f"mom|{cnd}_uplift@{H}", {}).get("reject"):
                go_reasons.append(f"mom|{cnd} uplift positive & survives FDR @ {H}d")
    results["caveats"] = ("data/stocks = 110 survivorship-biased names (inflates momentum L/S); "
                          "base-confirmed long leg is a concentrated subset (mechanical Sharpe lift) "
                          "→ the L/S 'win' is supporting colour, not evidence.")
    results["verdict"] = {
        "go": bool(go_reasons),
        "reason": ("; ".join(go_reasons) if go_reasons else
                   "the scanner's base score and the size-controlled confirmer add NO "
                   "FDR-surviving value — NO-GO"
                   + (" — and " + "; ".join(neg_flags) + " (near-pivot = extended = the "
                      "short-term reversal effect, the OPPOSITE of the IBD thesis)"
                      if neg_flags else "")),
        "negative_flags": neg_flags,
    }

    outp = config.ROOT / "reports" / "base-scanner-phase0.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(results, indent=2, default=str))

    print(f"\n=== Base-scanner Phase-0 — {results['universe']} names, cost {COST_BPS}bps ===")
    for H in HORIZONS:
        r = results["horizons"][str(H)]
        print(f"\n— horizon {H}d · {r['rebalances']} rebalances · {r['span']} —")
        for c in ("base", "tight", "pivot_prox", "mom"):
            s = r["standalone"][c]
            print(f"  standalone IC  {c:11} = {_fmt(s.get('mean_ic'))}  t={_fmt(s.get('t_hac'),2)}  n={s.get('n')}")
        for cnd in ("tight", "pivot_prox"):
            s = r["uplift"][cnd]
            print(f"  CONFIRM mom|{cnd:10} uplift = {_fmt(s.get('mean_ic'))} (t={_fmt(s.get('t_hac'),2)})")
        for k in ("ls_base", "ls_mom_base", "ls_mom_baseconfirmed"):
            b = r.get(k)
            if b:
                print(f"  {k:22} Sharpe={b['sharpe']}  DSR={b['dsr']}  cum={b['cum_pct']}%")
    print(f"\nFDR(10%) survivors: {results['fdr_survivors'] or 'NONE'}")
    print(f"VERDICT: {'GO' if results['verdict']['go'] else 'NO-GO'} — {results['verdict']['reason']}")
    print(f"(wrote {outp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
