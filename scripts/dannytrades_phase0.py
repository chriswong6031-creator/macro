"""scripts/dannytrades_phase0.py — phase-0 validation of the reconstructed
DannyTrades composite (engine/dannytrades.py).

Answers two questions, honestly, through the repo's standard machinery
(engine.validation + engine.forward_dist):

  PRONG 1 — STANDALONE: does the 0–100 composite (and each leg) rank winners
            above losers? Cross-sectional rank IC (Newey-West HAC) + BH-FDR across
            legs, plus an event study of the discrete BUY states (P(up), median
            forward return, drawdown tail) vs the unconditional base rate.

  PRONG 2 — CONFIRMATION LIFT (the actual ask): used as a *filter* on top of a
            base entry (12–1 momentum, a trend-pullback, a breakout), does requiring
            DannyTrades agreement improve the forward outcome — and does its SELL
            state work as a veto? Incremental cross-sectional IC of momentum⊕Danny
            vs momentum alone. A random placebo runs the same gauntlet; split-half
            and pre/post-2015 sub-periods check stability.

Runs on a local yfinance OHLCV cache (real historical VOLUME — the data/stocks
parquets only carry recent volume). Display/research only; never a price target.

Run: python3 -m scripts.dannytrades_phase0 [--cache DIR] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
import sys
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dannytrades as dt  # noqa: E402
from engine.forward_dist import forward_paths  # noqa: E402
from engine.technicals import rsi  # noqa: E402
from engine.validation import (  # noqa: E402
    benjamini_hochberg, ic_summary, rank_ic,
)

HORIZONS = [10, 21, 63, 126]
PRIMARY_H = 63
WEEKLY_STEP = 5
MIN_NAMES = 20          # min cross-section for an IC date
SPLIT_DATE = "2015-01-01"


# --------------------------------------------------------------------------- #
# data + per-name feature table
# --------------------------------------------------------------------------- #
def _load(cache: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(glob(str(cache / "*.parquet"))):
        t = Path(p).stem
        df = pd.read_parquet(p)
        if {"close", "high", "low", "volume"} <= set(df.columns) and len(df) > 300:
            out[t] = df.sort_index()
    return out


def _base_signals(close: pd.Series) -> pd.DataFrame:
    """Reproducible 'other models' to combine Danny WITH (all causal)."""
    sma200 = close.rolling(200).mean()
    above200 = close > sma200
    r = rsi(close)
    # B1: trend pullback — uptrend, RSI recovering up through 40 from below
    pullback = above200 & (r > 40) & (r.shift(3) < 40) & (r.diff() > 0)
    # B2: breakout — fresh 20-day high inside an uptrend
    hi20 = close.rolling(20).max()
    breakout = above200 & (close >= hi20) & (close.shift(1) < hi20.shift(1))
    # 12-1 momentum (cross-sectional factor; the classic 'other signal')
    mom = close.shift(21) / close.shift(252) - 1.0
    return pd.DataFrame({"above200": above200, "base_pullback": pullback.fillna(False),
                         "base_breakout": breakout.fillna(False), "mom12_1": mom},
                        index=close.index)


def build_pool(data: dict[str, pd.DataFrame], cfg: dict | None = None) -> pd.DataFrame:
    """Master long table: one row per (ticker, date) with Danny legs, base signals,
    and forward outcomes. The single source for every downstream test."""
    frames = []
    for t, df in data.items():
        if t == "SPY":
            continue
        close = df["close"].astype(float)
        sig = dt.signals(close, df["high"].astype(float), df["low"].astype(float),
                         df["volume"].astype(float), cfg)
        base = _base_signals(close)
        fwd = {f"fwd_{h}": close.pct_change(h, fill_method=None).shift(-h) * 100
               for h in HORIZONS}
        paths = forward_paths(close, PRIMARY_H)        # ret / mae / mfe at primary H
        tab = pd.concat([sig, base, pd.DataFrame(fwd, index=close.index),
                         paths.rename(columns={"ret": "p_ret", "mae": "p_mae",
                                               "mfe": "p_mfe"})], axis=1)
        tab["ticker"] = t
        tab["date"] = tab.index
        frames.append(tab)
    pool = pd.concat(frames, ignore_index=True)
    return pool


# --------------------------------------------------------------------------- #
# prong 1a — cross-sectional rank IC
# --------------------------------------------------------------------------- #
def _wide(pool: pd.DataFrame, col: str) -> pd.DataFrame:
    """date × ticker matrix for one column (computed once, reused per IC)."""
    return pool.pivot_table(index="date", columns="ticker", values=col)


def _xs_ic_wide(wsig: pd.DataFrame, wfwd: pd.DataFrame, dates) -> pd.Series:
    """Cross-sectional rank IC per date from pre-pivoted wide panels (fast)."""
    ics = []
    for d in dates:
        if d not in wsig.index or d not in wfwd.index:
            continue
        s, f = wsig.loc[d], wfwd.loc[d]
        j = pd.concat([s.rename("s"), f.rename("f")], axis=1).dropna()
        if len(j) >= MIN_NAMES:
            ics.append(rank_ic(j["s"], j["f"]))
    return pd.Series(ics, dtype=float).dropna()


def _xs_ic(pool: pd.DataFrame, sig_col: str, horizon: int, dates) -> pd.Series:
    return _xs_ic_wide(_wide(pool, sig_col), _wide(pool, f"fwd_{horizon}"), dates)


def cross_sectional_ic(pool: pd.DataFrame) -> dict:
    all_dates = np.sort(pool["date"].unique())
    grid = all_dates[::WEEKLY_STEP]
    legs = {"composite_score": "score", "whale": "whale", "ribbon": "ribbon",
            "momentum_leg": "momentum_ok", "mom12_1": "mom12_1"}
    # signed numeric versions for IC
    pool = pool.copy()
    pool["momentum_ok"] = pool["momentum_ok"].astype(float)
    out = {}
    pvals = {}
    for name, col in legs.items():
        per_h = {}
        for h in HORIZONS:
            ics = _xs_ic(pool, col, h, grid)
            s = ic_summary(ics, periods_per_year=52)
            per_h[h] = s
            if h == PRIMARY_H and s.get("p_hac") is not None:
                pvals[name] = s["p_hac"]
        out[name] = per_h
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for name in out:
        if name in fdr:
            out[name][PRIMARY_H]["q_fdr"] = fdr[name]["q"]
            out[name][PRIMARY_H]["survives_fdr"] = fdr[name]["reject"]
    return out


# --------------------------------------------------------------------------- #
# prong 1b — event study of the discrete states
# --------------------------------------------------------------------------- #
def _event_stats(mask: pd.Series, pool: pd.DataFrame) -> dict:
    sel = pool[mask.values]
    r = sel["p_ret"].dropna()
    mae = sel["p_mae"].dropna()
    mfe = sel["p_mfe"].dropna()
    if len(r) < 30:
        return {"n": int(len(r))}
    return {"n": int(len(r)),
            "p_up": round(float((r > 0).mean()), 3),
            "ret_med": round(float(r.median()), 2),
            "ret_mean": round(float(r.mean()), 2),
            "dd_tail_p05": round(float(mae.quantile(0.05)), 2),
            "dd_avg": round(float(mae.mean()), 2),
            "mfe_med": round(float(mfe.median()), 2)}


def event_study(pool: pd.DataFrame) -> dict:
    base = _event_stats(pool["p_ret"].notna(), pool)
    states = ["danny_buy", "danny_buy_strong", "whale_entering", "breakout_up", "danny_sell"]
    out = {"unconditional": base}
    for st in states:
        out[st] = _event_stats(pool[st] & pool["p_ret"].notna(), pool)
        if out[st].get("n", 0) >= 30:
            out[st]["lift_p_up"] = round(out[st]["p_up"] - base["p_up"], 3)
            out[st]["lift_ret_med"] = round(out[st]["ret_med"] - base["ret_med"], 2)
    return out


# --------------------------------------------------------------------------- #
# prong 2 — confirmation lift on a base entry
# --------------------------------------------------------------------------- #
def confirm_mask(pool: pd.DataFrame, wm: float | None = None) -> pd.Series:
    """Danny's bullish confluence used as a filter: whale ≥ momentum threshold,
    ribbon not down, momentum not curling."""
    wm = dt.CFG["whale_momentum"] if wm is None else wm
    return (pool["whale"] >= wm) & (pool["ribbon"] >= 0) & pool["momentum_ok"].astype(bool)


def confirmation_lift(pool: pd.DataFrame, wm: float | None = None) -> dict:
    confirm = confirm_mask(pool, wm)
    veto = pool["danny_sell"].astype(bool)
    out = {}
    for bname in ["base_pullback", "base_breakout"]:
        b = pool[bname].astype(bool) & pool["p_ret"].notna()
        s_base = _event_stats(b, pool)
        s_conf = _event_stats(b & confirm, pool)
        s_veto = _event_stats(b & veto, pool)
        s_noconf = _event_stats(b & ~confirm, pool)
        row = {"base": s_base, "base_and_confirm": s_conf,
               "base_and_NOconfirm": s_noconf, "base_and_veto": s_veto}
        if s_base.get("n", 0) >= 30 and s_conf.get("n", 0) >= 30:
            row["lift_p_up"] = round(s_conf["p_up"] - s_base["p_up"], 3)
            row["lift_ret_med"] = round(s_conf["ret_med"] - s_base["ret_med"], 2)
            row["lift_dd_tail"] = round(s_conf["dd_tail_p05"] - s_base["dd_tail_p05"], 2)
        out[bname] = row
    return out


def lift_inference(pool: pd.DataFrame, base_col: str, confirm: pd.Series,
                   n_boot: int = 1000, seed: int = 11) -> dict:
    """Honest error bars on a confirmation lift. (1) Ticker-CLUSTER bootstrap CI —
    resample the 114 names with replacement (the dominant clustering; overlapping
    63d windows + cross-sectional correlation mean naive n hugely overstates DoF).
    (2) A FULL placebo distribution — permute the confirm flag within each ticker
    `n_boot` times — so 'beats placebo' is P(placebo ≥ real), not one lucky seed."""
    m = (pool[base_col].astype(bool) & pool["p_ret"].notna()).values
    up = (pool["p_ret"].values[m] > 0).astype(float)
    conf = np.asarray(confirm.values[m], dtype=float)
    tick = pool["ticker"].values[m]
    if len(up) < 50 or conf.sum() < 30:
        return {"n": int(len(up)), "n_confirm": int(conf.sum())}
    base_up = up.mean()
    real_lift = up[conf > 0].mean() - base_up
    g = pd.DataFrame({"t": tick, "up": up, "c": conf, "upc": up * conf})
    agg = g.groupby("t").agg(n=("up", "size"), su=("up", "sum"),
                             nc=("c", "sum"), suc=("upc", "sum"))
    n, su, nc, suc = (agg[c].values for c in ("n", "su", "nc", "suc"))
    rng = np.random.default_rng(seed)
    T = len(agg)
    lifts = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, T, T)
        N, SU, NC, SUC = n[s].sum(), su[s].sum(), nc[s].sum(), suc[s].sum()
        lifts[b] = (SUC / NC - SU / N) if (NC > 0 and N > 0) else np.nan
    lifts = lifts[np.isfinite(lifts)]
    # placebo: within-ticker permutation of the confirm flag
    by = {t: (g["up"].values[g["t"].values == t], int(k))
          for t, k in zip(agg.index, nc.astype(int))}
    plac = np.empty(n_boot)
    for b in range(n_boot):
        s_uc = s_nc = 0.0
        for u, k in by.values():
            if k <= 0 or k > len(u):
                continue
            sel = rng.choice(len(u), k, replace=False)
            s_uc += u[sel].sum(); s_nc += k
        plac[b] = s_uc / s_nc - base_up if s_nc > 0 else np.nan
    plac = plac[np.isfinite(plac)]
    return {
        "n": int(len(up)), "n_confirm": int(conf.sum()),
        "real_lift": round(float(real_lift), 4),
        "ci95": [round(float(np.percentile(lifts, 2.5)), 4),
                 round(float(np.percentile(lifts, 97.5)), 4)],
        "p_lift_gt0": round(float((lifts > 0).mean()), 3),
        "placebo_mean": round(float(plac.mean()), 4),
        "placebo_p95": round(float(np.percentile(plac, 95)), 4),
        "p_placebo_ge_real": round(float((plac >= real_lift).mean()), 3),
    }


def whale_ablation(pool: pd.DataFrame) -> dict:
    """Decompose the confirm mask (whale≥50 & ribbon≥0 & momentum_ok): does the
    whale gate carry the lift, or is it the ribbon/momentum (trend) half? And is the
    whale gate just momentum in disguise?"""
    base = pool["base_pullback"].astype(bool) & pool["p_ret"].notna()
    up = pool["p_ret"] > 0
    ribmom = (pool["ribbon"] >= 0) & pool["momentum_ok"].astype(bool)
    whi = pool["whale"] >= dt.CFG["whale_momentum"]
    base_up = float(up[base].mean())

    def lift(mask):
        sel = base & mask
        return (round(float(up[sel].mean()) - base_up, 4), int(sel.sum())) \
            if sel.sum() >= 30 else (None, int(sel.sum()))
    # is the whale gate momentum-in-disguise?
    bm = pool[base][["whale", "mom12_1"]].dropna()
    corr = float(bm["whale"].corr(bm["mom12_1"])) if len(bm) > 50 else None
    hi, lo = bm[bm["whale"] >= dt.CFG["whale_momentum"]], bm[bm["whale"] < dt.CFG["whale_momentum"]]
    return {"base_pup": round(base_up, 3),
            "lift_ribbon_mom_NO_whale": lift(ribmom & ~whi),
            "lift_whale_only": lift(whi),
            "lift_whale_within_ribbon_mom": lift(ribmom & whi),
            "lift_ribbon_mom_all": lift(ribmom),
            "corr_whale_mom12_1": round(corr, 3) if corr is not None else None,
            "mom_median_whale_hi": round(float(hi["mom12_1"].median()), 3) if len(hi) else None,
            "mom_median_whale_lo": round(float(lo["mom12_1"].median()), 3) if len(lo) else None}


def incremental_ic(pool: pd.DataFrame) -> dict:
    """Does momentum ⊕ Danny beat momentum alone, cross-sectionally? z-score each
    within-date, average, IC vs fwd_63. If the combo IC > momentum IC and Danny's
    own IC > 0, Danny carries orthogonal information worth combining."""
    grid = np.sort(pool["date"].unique())[::WEEKLY_STEP]
    rows_mom, rows_dan, rows_combo = [], [], []
    for d in grid:
        sub = pool[pool["date"] == d][["mom12_1", "score", f"fwd_{PRIMARY_H}"]].dropna()
        if len(sub) < MIN_NAMES:
            continue
        zm = (sub["mom12_1"] - sub["mom12_1"].mean()) / (sub["mom12_1"].std() or 1)
        zd = (sub["score"] - sub["score"].mean()) / (sub["score"].std() or 1)
        f = sub[f"fwd_{PRIMARY_H}"]
        rows_mom.append(rank_ic(zm, f))
        rows_dan.append(rank_ic(zd, f))
        rows_combo.append(rank_ic(0.5 * zm + 0.5 * zd, f))
    return {"momentum": ic_summary(pd.Series(rows_mom).dropna(), 52),
            "danny": ic_summary(pd.Series(rows_dan).dropna(), 52),
            "momentum_plus_danny": ic_summary(pd.Series(rows_combo).dropna(), 52)}


# --------------------------------------------------------------------------- #
# robustness — placebo, split-half, sub-periods
# --------------------------------------------------------------------------- #
def placebo(pool: pd.DataFrame, seed: int = 7) -> dict:
    """Shuffle the confirm flag within each ticker (preserve its rate) → the lift
    should collapse to ~0 if the real lift is signal, not a base-rate artifact."""
    rng = np.random.default_rng(seed)
    p = pool.copy()
    confirm = ((p["whale"] >= dt.CFG["whale_momentum"]) & (p["ribbon"] >= 0)
               & p["momentum_ok"].astype(bool))
    p["_conf"] = confirm.values
    p["_conf_shuf"] = p.groupby("ticker")["_conf"].transform(
        lambda s: rng.permutation(s.values))
    out = {}
    for bname in ["base_pullback", "base_breakout"]:
        b = p[bname].astype(bool) & p["p_ret"].notna()
        s_base = _event_stats(b, p)
        s_real = _event_stats(b & p["_conf"].astype(bool), p)
        s_plac = _event_stats(b & p["_conf_shuf"].astype(bool), p)
        out[bname] = {
            "real_lift_p_up": round(s_real.get("p_up", 0) - s_base.get("p_up", 0), 3)
            if s_real.get("n", 0) >= 30 else None,
            "placebo_lift_p_up": round(s_plac.get("p_up", 0) - s_base.get("p_up", 0), 3)
            if s_plac.get("n", 0) >= 30 else None}
    return out


def subperiods(pool: pd.DataFrame) -> dict:
    out = {}
    for label, sub in [("pre_2015", pool[pool["date"] < SPLIT_DATE]),
                       ("post_2015", pool[pool["date"] >= SPLIT_DATE])]:
        grid = np.sort(sub["date"].unique())[::WEEKLY_STEP]
        ics = _xs_ic(sub, "score", PRIMARY_H, grid)
        s = ic_summary(ics, periods_per_year=52)
        confirm = ((sub["whale"] >= dt.CFG["whale_momentum"]) & (sub["ribbon"] >= 0)
                   & sub["momentum_ok"].astype(bool))
        b = sub["base_pullback"].astype(bool) & sub["p_ret"].notna()
        sb, sc = _event_stats(b, sub), _event_stats(b & confirm, sub)
        out[label] = {"score_ic": s.get("mean_ic"), "ic_n": s.get("n"),
                      "pullback_lift_p_up": (round(sc.get("p_up", 0) - sb.get("p_up", 0), 3)
                                             if sc.get("n", 0) >= 30 and sb.get("n", 0) >= 30 else None)}
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/dtcache")
    ap.add_argument("--out", default="/tmp/dt_results.json")
    args = ap.parse_args()

    data = _load(Path(args.cache))
    print(f"loaded {len(data)} tickers", file=sys.stderr)
    pool = build_pool(data)
    print(f"pool rows: {len(pool):,}", file=sys.stderr)

    results = {
        "n_tickers": len([t for t in data if t != "SPY"]),
        "pool_rows": int(len(pool)),
        "date_range": [str(pool['date'].min().date()), str(pool['date'].max().date())],
        "horizons": HORIZONS, "primary_h": PRIMARY_H,
        "cross_sectional_ic": cross_sectional_ic(pool),
        "event_study": event_study(pool),
        "confirmation_lift": confirmation_lift(pool),
        "lift_inference": {
            "pullback": lift_inference(pool, "base_pullback", confirm_mask(pool)),
            "breakout": lift_inference(pool, "base_breakout", confirm_mask(pool)),
        },
        "whale_ablation": whale_ablation(pool),
        "incremental_ic": incremental_ic(pool),
        "placebo": placebo(pool),
        "subperiods": subperiods(pool),
    }
    Path(args.out).write_text(json.dumps(results, indent=2, default=float))

    # ---- human-readable verdict ----
    ci = results["cross_sectional_ic"]
    sc = ci["composite_score"][PRIMARY_H]
    es = results["event_study"]
    cl = results["confirmation_lift"]
    inc = results["incremental_ic"]
    pl = results["placebo"]
    print("\n" + "=" * 72)
    print(f"DANNYTRADES COMPOSITE — phase-0  ({results['date_range'][0]}→{results['date_range'][1]}, "
          f"{results['n_tickers']} names)")
    print("=" * 72)
    print(f"\n[1] STANDALONE cross-sectional IC @ {PRIMARY_H}d (composite score):")
    print(f"    mean_IC={sc.get('mean_ic')}  t_HAC={sc.get('t_hac')}  p={sc.get('p_hac')}  "
          f"q_FDR={sc.get('q_fdr')}  survives_FDR={sc.get('survives_fdr')}  hit={sc.get('hit')}")
    print(f"    whale leg IC={ci['whale'][PRIMARY_H].get('mean_ic')}  "
          f"mom12-1 IC={ci['mom12_1'][PRIMARY_H].get('mean_ic')}")
    print(f"\n[2] EVENT STUDY @ {PRIMARY_H}d (P(up) vs unconditional {es['unconditional']['p_up']}):")
    for st in ["danny_buy", "danny_buy_strong", "whale_entering", "breakout_up", "danny_sell"]:
        s = es[st]
        if s.get("n", 0) >= 30:
            print(f"    {st:16s} n={s['n']:5d}  P(up)={s['p_up']}  med={s['ret_med']:+.1f}%  "
                  f"dd_tail={s['dd_tail_p05']:.1f}%  liftP(up)={s.get('lift_p_up')}")
    print(f"\n[3] CONFIRMATION LIFT (base entry → base ∧ Danny-confirm) + HONEST inference:")
    li = results["lift_inference"]
    for b, key in [("base_pullback", "pullback"), ("base_breakout", "breakout")]:
        row = cl[b]; sb, scf = row["base"], row["base_and_confirm"]
        inf = li[key]
        if sb.get("n", 0) >= 30 and scf.get("n", 0) >= 30:
            dd = row.get("lift_dd_tail")
            dd_word = "DEEPER/worse" if (dd is not None and dd < 0) else "shallower/better"
            print(f"    {b:15s} base P(up)={sb['p_up']} → +confirm P(up)={scf['p_up']}  "
                  f"ΔP(up)={row.get('lift_p_up')}  Δmed={row.get('lift_ret_med')}%  "
                  f"dd_tail {dd:+.2f}pp ({dd_word})")
            if inf.get("real_lift") is not None:
                print(f"    {'':15s} cluster-bootstrap 95% CI={inf['ci95']}  P(lift>0)={inf['p_lift_gt0']}  "
                      f"| placebo dist mean={inf['placebo_mean']} p95={inf['placebo_p95']}  "
                      f"P(placebo≥real)={inf['p_placebo_ge_real']}")
    wa = results["whale_ablation"]
    print(f"\n[3b] WHALE-LEG ABLATION (base P(up)={wa['base_pup']}):")
    print(f"    ribbon&mom WITHOUT whale: lift={wa['lift_ribbon_mom_NO_whale']}  "
          f"whale-only: lift={wa['lift_whale_only']}  whale WITHIN ribbon&mom: lift={wa['lift_whale_within_ribbon_mom']}")
    print(f"    momentum-in-disguise? corr(whale,mom12-1)={wa['corr_whale_mom12_1']}  "
          f"mom_median whale_hi={wa['mom_median_whale_hi']} vs whale_lo={wa['mom_median_whale_lo']}")
    print(f"\n[4] INCREMENTAL IC (combine with momentum):")
    print(f"    momentum alone IC={inc['momentum'].get('mean_ic')}  danny IC={inc['danny'].get('mean_ic')}  "
          f"momentum⊕danny IC={inc['momentum_plus_danny'].get('mean_ic')}")
    print(f"\n[5] STABILITY (sub-periods):")
    for k, v in results["subperiods"].items():
        print(f"    {k:10s} score_IC={v['score_ic']}  pullback_lift_P(up)={v['pullback_lift_p_up']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
