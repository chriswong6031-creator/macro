"""Phase-0 for the BTC on-chain valuation DRAWDOWN gauge (trackB, candidate=confirmer).

QUESTION. Does a rolling-4y percentile composite of two BTC on-chain VALUATION metrics
(MVRV + Reserve Risk) carry forward content about *how deep the next drawdown gets* —
NOT about forward return (the return version FAILS) — and does a de-risk overlay that
trims exposure when the composite is rich actually REDUCE drawdown out-of-sample, over
and above the two DUMB baselines (200d-SMA trend-off, trailing-realized-vol-percentile
de-risk)?

DATA. data/coinmetrics/mvrv.parquet (15.9y) + data/checkonchain/reserve_risk.parquet
(15.8y) + coinmetrics price_usd.parquet (BTC USD close, dividend-irrelevant).

SIGNAL (no look-ahead). For each metric, a ROLLING-4y (1460d) percentile rank of the
value vs its own trailing 4y window (NOT an expanding window — expanding leaks the long
bull-era drift and is non-stationary). composite = mean(pct_mvrv, pct_rr). High composite
= richly valued = (hypothesis) deeper forward drawdown ahead.

TARGET. Forward 21/63/126d BTC MAX-DRAWDOWN measured from price[t] over (t, t+h]:
    fwd_mdd_h = min_{t<s<=t+h} price[s] / price[t] - 1   (a NEGATIVE number; more
    negative = worse). A positive Spearman(composite, fwd_mdd) means rich -> shallower
    (wrong sign); we EXPECT NEGATIVE (rich -> deeper, i.e. more negative mdd).

GATES (all from engine/validation.py + engine/active_alloc.py):
  - rank_ic per overlapping-sampled date + ic_summary + benjamini_hochberg q<=0.10
    across the 3 horizons (Spearman of composite vs fwd_mdd; NW-HAC t for overlap).
  - purged_folds (k=5, embargo=horizon) sign-consistency.
  - leave-one-crisis-out {2013, 2018, 2022} — drop each crash year, sign must hold.
  - split-half same-sign (and we report magnitude too — research claims same-magnitude).
  - de-risk overlay: alloc = floor (0.25) when composite>p80 (rolling-4y) else 1.0,
    backtested via active_alloc.backtest_lev / backtest_core; split_half_oos +
    deflated_sharpe of the (overlay - hodl) drawdown-reduction; block_bootstrap_ci on the
    dd-reduction must exclude 0.
  - BASELINES the overlay must BEAT on drawdown reduction: (a) 200d-SMA trend-off,
    (b) trailing realized-vol percentile de-risk (same floor/threshold mechanic). The
    on-chain leg has to ADD over trailing vol, else it is just a vol timer in disguise.

HONEST LENS. BTC has ~3 independent macro crash clusters in the sample (2014-15, 2018,
2022 — 2021 was a sharp but partial drawdown). So the EFFECTIVE N is a handful of cycles,
not ~5800 rows. Drawdown is heavily autocorrelated and overlapping; judge SIGN/ORDERING
consistency and whether it beats the dumb vol timer, never the raw t-stat magnitude.
READ-ONLY research: prints + writes reports/btc-onchain-dd-phase0.md.
"""
from __future__ import annotations

import sys
import warnings
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

import numpy as np
import pandas as pd

from engine.validation import (
    rank_ic, ic_summary, benjamini_hochberg, purged_folds, block_bootstrap_ci,
    deflated_sharpe, dsr_verdict, ret_moments, _maxdd, _sharpe, newey_west_tstat,
)
from engine import active_alloc as aa

DATA = Path("data")
ROLL = 1460          # rolling 4-yr percentile window (calendar-ish, daily bars)
MINP = 365           # need >=1y before a percentile is meaningful
HORIZONS = [21, 63, 126]
FLOOR = 0.25         # de-risk floor exposure when rich
P_HI = 80            # rich threshold (percentile of composite, rolling-4y)
CRISES = [2013, 2018, 2022]
SEED = 7


# --------------------------------------------------------------------------- #
def load() -> pd.DataFrame:
    px = pd.read_parquet(DATA / "coinmetrics" / "price_usd.parquet")["price_usd"].astype(float)
    mvrv = pd.read_parquet(DATA / "coinmetrics" / "mvrv.parquet")["mvrv"].astype(float)
    rr = pd.read_parquet(DATA / "checkonchain" / "reserve_risk.parquet")["reserve_risk"].astype(float)
    for s in (px, mvrv, rr):
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    rr = rr.replace([np.inf, -np.inf], np.nan)
    df = pd.concat({"px": px, "mvrv": mvrv, "rr": rr}, axis=1).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # forward-fill metric gaps a couple days; keep price authoritative
    df["mvrv"] = df["mvrv"].ffill(limit=3)
    df["rr"] = df["rr"].ffill(limit=3)
    df = df.dropna(subset=["px"])
    return df


def roll_pct(s: pd.Series, win: int = ROLL, minp: int = MINP) -> pd.Series:
    """Causal rolling percentile rank of the CURRENT value within its trailing window.
    Value in [0,1]; uses rows through t only (the current value is the last in the window
    so this is point-in-time, no look-ahead)."""
    def _last_pct(a):
        a = a[np.isfinite(a)]
        if len(a) < 2:
            return np.nan
        return float((a <= a[-1]).mean())
    return s.rolling(win, min_periods=minp).apply(_last_pct, raw=True)


def fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over (t, t+h]: worst price/price[t]-1. NEGATIVE. No look-ahead
    in the SIGNAL — this is the TARGET (label), computed from future bars by construction."""
    p = px.values
    n = len(p)
    out = np.full(n, np.nan)
    for i in range(n):
        j = min(i + h, n - 1)
        if j <= i:
            continue
        w = p[i + 1:j + 1]
        if len(w) == 0:
            continue
        out[i] = float(np.min(w) / p[i] - 1.0)
    return pd.Series(out, index=px.index)


# --------------------------------------------------------------------------- #
def main():
    df = load()
    px = df["px"]
    # rolling-4y percentiles -> composite
    df["pct_mvrv"] = roll_pct(df["mvrv"])
    df["pct_rr"] = roll_pct(df["rr"])
    # STRICT mean: require BOTH legs warmed up. pandas .mean(axis=1) skips NaN, which
    # silently degrades the composite to MVRV-alone (the WEAK leg) during the ~2mo where
    # Reserve Risk hasn't filled its own 365d floor — contaminating the early sample.
    df["composite"] = (df["pct_mvrv"] + df["pct_rr"]) / 2.0
    comp = df["composite"]
    span_years = (px.index[-1] - px.index[0]).days / 365.25
    valid = comp.dropna()
    print(f"[data] {len(df)} rows  {df.index[0].date()}->{df.index[-1].date()}  "
          f"{span_years:.1f}y; composite valid from {valid.index[0].date()} "
          f"({valid.notna().sum()} obs)")

    out_lines = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        out_lines.append(s)

    P("# BTC on-chain valuation DRAWDOWN gauge — Phase-0\n")
    P(f"- Sample: {df.index[0].date()} -> {df.index[-1].date()} ({span_years:.1f}y), "
      f"{len(df)} daily bars; composite valid {valid.notna().sum()} obs from "
      f"{valid.index[0].date()}.")
    P(f"- Signal: rolling-{ROLL}d ({ROLL/365:.1f}y) percentile of MVRV & Reserve Risk, "
      f"composite = mean. Target: forward {HORIZONS} max-drawdown.\n")

    # ----- 1. forward-MAXDD rank-IC + BH-FDR across horizons -----------------
    P("## 1. Forward max-drawdown IC (composite -> fwd_mdd), BH-FDR\n")
    P("Sign hypothesis: NEGATIVE Spearman (rich valuation -> deeper drawdown). "
      "Sampled every `h` days to limit overlap; ic_summary uses NW-HAC.\n")
    pvals = {}
    full_spear = {}
    ic_tables = {}
    for h in HORIZONS:
        mdd = fwd_maxdd(px, h)
        joint = pd.concat([comp.rename("c"), mdd.rename("m")], axis=1).dropna()
        # full-sample Spearman
        fs = float(joint["c"].rank().corr(joint["m"].rank()))
        full_spear[h] = fs
        # per-window IC: chop into non-overlapping h-blocks, rank-IC within each
        ics = []
        idx = joint.index
        for k in range(0, len(idx) - h, h):
            sub = joint.iloc[k:k + h]
            if len(sub) >= 10:
                ics.append(rank_ic(sub["c"], sub["m"]))
        summ = ic_summary([x for x in ics if np.isfinite(x)], periods_per_year=int(252 / h))
        ic_tables[h] = summ
        # p for FDR: use full-sample Spearman significance via NW on the per-block IC mean
        p = summ.get("p_hac")
        pvals[f"fwd{h}"] = p
        P(f"- fwd{h:>3}d: full-sample Spearman = **{fs:+.3f}** (n={len(joint)})  |  "
          f"per-block mean_ic={summ.get('mean_ic')}, IC-IR={summ.get('ic_ir')}, "
          f"t_HAC={summ.get('t_hac')}, p_HAC={summ.get('p_hac')}, "
          f"hit={summ.get('hit')}, blocks={summ.get('n')}")
    bh = benjamini_hochberg(pvals, alpha=0.10)
    P("\nBH-FDR (q<=0.10) across horizons:")
    for k, v in bh.items():
        P(f"  - {k}: p={v['p']}, q={v['q']}, reject_null={v['reject']}")
    bh_pass = any(v["reject"] for v in bh.values()) if bh else False
    sign_ok = all(fs < 0 for fs in full_spear.values())
    P(f"\n=> FDR any-horizon reject: {bh_pass}; all-horizons NEGATIVE sign: {sign_ok}")

    # ----- 2. split-half (sign AND magnitude) on fwd63 -----------------------
    P("\n## 2. Split-half stability (fwd63d, sign + magnitude)\n")
    h = 63
    mdd = fwd_maxdd(px, h)
    joint = pd.concat([comp.rename("c"), mdd.rename("m")], axis=1).dropna()
    n = len(joint)
    h1, h2 = joint.iloc[:n // 2], joint.iloc[n // 2:]
    s1 = float(h1["c"].rank().corr(h1["m"].rank()))
    s2 = float(h2["c"].rank().corr(h2["m"].rank()))
    same_sign = (np.sign(s1) == np.sign(s2)) and (s1 < 0)
    same_mag = abs(abs(s1) - abs(s2)) < 0.10  # within 0.10 = "same magnitude"
    P(f"- first half  ({h1.index[0].date()}->{h1.index[-1].date()}): Spearman {s1:+.3f}")
    P(f"- second half ({h2.index[0].date()}->{h2.index[-1].date()}): Spearman {s2:+.3f}")
    P(f"=> same-sign(&neg)={same_sign}; |Δmag|={abs(abs(s1)-abs(s2)):.3f} same-magnitude={same_mag}")

    # ----- 3. purged folds sign-consistency (fwd63) --------------------------
    P("\n## 3. Purged-fold sign consistency (fwd63d, k=5, embargo=63)\n")
    folds = purged_folds(joint.index, k=5, embargo=h)
    fold_signs = []
    for fn, fidx in folds.items():
        sub = joint.loc[joint.index.intersection(fidx)]
        if len(sub) < 30:
            P(f"  - {fn}: n={len(sub)} (too few)")
            fold_signs.append(0)
            continue
        sc = float(sub["c"].rank().corr(sub["m"].rank()))
        fold_signs.append(int(np.sign(sc)))
        P(f"  - {fn} ({sub.index[0].date()}->{sub.index[-1].date()}, n={len(sub)}): {sc:+.3f}")
    nzfold = [s for s in fold_signs if s != 0]
    folds_neg = bool(nzfold) and all(s < 0 for s in nzfold)
    P(f"=> all non-empty folds NEGATIVE: {folds_neg} ({sum(1 for s in nzfold if s<0)}/{len(nzfold)})")

    # ----- 4. leave-one-crisis-out -------------------------------------------
    P("\n## 4. Leave-one-crisis-out (drop each crash year, fwd63 Spearman holds)\n")
    loco_ok = True
    full63 = full_spear[63]
    P(f"- full-sample fwd63 Spearman: {full63:+.3f}")
    for yr in CRISES:
        mask = joint.index.year != yr
        sub = joint[mask]
        sc = float(sub["c"].rank().corr(sub["m"].rank()))
        held = sc < 0
        loco_ok = loco_ok and held
        P(f"  - drop {yr} (n={len(sub)}): {sc:+.3f}  sign-holds={held}")
    P(f"=> leave-one-crisis-out (all stay NEGATIVE): {loco_ok}")

    # honest-N: count independent drawdown clusters
    P("\n## 5. Honest-N (independent crash clusters)\n")
    # mark deep-drawdown episodes (fwd63 mdd < -0.30), cluster by >120d gaps
    deep = joint[joint["m"] < -0.30]
    if len(deep):
        gaps = deep.index.to_series().diff().dt.days.fillna(9999)
        clusters = (gaps > 120).cumsum()
        nclust = clusters.nunique()
    else:
        nclust = 0
    P(f"- deep (fwd63 mdd<-30%) obs: {len(deep)}; distinct clusters (>120d gap): {nclust}")
    P(f"- => EFFECTIVE independent stress episodes ~ {nclust}; raw n={n} is "
      f"massively overlapping. Judge sign/ordering, not t-magnitude.")

    # ----- 6. de-risk overlay vs baselines -----------------------------------
    P("\n## 6. De-risk overlay vs dumb baselines (drawdown reduction)\n")
    # positional read: the DTB3 column follows its config alias (us3m -> us3m_bill, 2026-07-30)
    bill = pd.read_parquet(DATA / "fred" / "DTB3.parquet").iloc[:, 0].reindex(px.index).ffill().fillna(0.0)

    # signal-based: rolling-4y p80 of composite -> rich
    comp_thr = comp.rolling(ROLL, min_periods=MINP).quantile(P_HI / 100.0)
    rich_sig = (comp > comp_thr)
    alloc_sig = pd.Series(np.where(rich_sig, FLOOR, 1.0), index=px.index)

    # baseline A: 200d SMA trend-off (price < 200dma -> floor)
    sma200 = px.rolling(200).mean()
    alloc_sma = pd.Series(np.where(px < sma200, FLOOR, 1.0), index=px.index)

    # baseline B: trailing realized-vol percentile de-risk (rich-vol -> floor), SAME mechanic
    rv = px.pct_change().rolling(21).std() * np.sqrt(365)
    rv_thr = rv.rolling(ROLL, min_periods=MINP).quantile(P_HI / 100.0)
    alloc_vol = pd.Series(np.where(rv > rv_thr, FLOOR, 1.0), index=px.index)

    # restrict all to the common valid window (composite needs warmup)
    start = comp.dropna().index[0]
    sub_px = px[px.index >= start]
    sub_bill = bill[bill.index >= start]

    def run(alloc, name):
        a = alloc.reindex(sub_px.index).ffill().fillna(1.0)
        bt = aa.backtest_lev(sub_px, a, sub_bill, cost_bps=5.0, borrow_spread=1.0)
        eq = bt["eq"]
        mdd = float((eq / eq.cummax() - 1).min())
        return bt, mdd

    bt_h, _ = run(pd.Series(1.0, index=px.index), "hodl")
    hodl_mdd = float((bt_h["hodl_eq"] / bt_h["hodl_eq"].cummax() - 1).min())
    bt_sig, sig_mdd = run(alloc_sig, "onchain")
    bt_sma, sma_mdd = run(alloc_sma, "sma200")
    bt_vol, vol_mdd = run(alloc_vol, "vol_pct")

    def line(nm, bt, mdd):
        P(f"- {nm:<12}: CAGR {bt['cagr']:>7}%  Sharpe {bt['sharpe']:>5}  "
          f"MaxDD {mdd*100:>6.1f}%  time_in_mkt {bt['time_in_market']:>5}%")

    P(f"- {'buy&hold':<12}: CAGR {bt_h['hodl_cagr']:>7}%  Sharpe {bt_h['hodl_sharpe']:>5}  "
      f"MaxDD {hodl_mdd*100:>6.1f}%  time_in_mkt 100.0%")
    line("onchain p80", bt_sig, sig_mdd)
    line("200dma", bt_sma, sma_mdd)
    line("vol p80", bt_vol, vol_mdd)

    dd_red_sig = hodl_mdd - sig_mdd     # positive = overlay SHALLOWER than hodl (good)
    dd_red_sma = hodl_mdd - sma_mdd
    dd_red_vol = hodl_mdd - vol_mdd
    P(f"\n- drawdown REDUCTION vs hodl (pp, +=shallower): "
      f"onchain {dd_red_sig*100:+.1f}  |  200dma {dd_red_sma*100:+.1f}  |  vol {dd_red_vol*100:+.1f}")
    beats_sma = sig_mdd > sma_mdd       # onchain mdd less deep than sma's mdd
    beats_vol = sig_mdd > vol_mdd
    P(f"- onchain MaxDD shallower than 200dma: {beats_sma}; than vol-timer: {beats_vol}")

    # ADDITIVITY: does the on-chain leg ADD over the dumb trend filter? trend-OR-onchain
    # (floor when EITHER rich-valuation or trend-off) vs trend-only. This is the real
    # confirmer test — not "does it beat trend alone" (it doesn't), but "does it add".
    trend_off = (px < sma200)
    alloc_or = pd.Series(np.where(rich_sig | trend_off, FLOOR, 1.0), index=px.index)
    bt_or, or_mdd = run(alloc_or, "trend_or_onchain")
    adds_to_trend = or_mdd > sma_mdd    # OR-overlay MaxDD shallower than trend-only
    P(f"- trend-only MaxDD {sma_mdd*100:.1f}%  vs  trend-OR-onchain MaxDD {or_mdd*100:.1f}% "
      f"(Sharpe {bt_or['sharpe']} vs trend {bt_sma['sharpe']})")
    P(f"  => on-chain ADDS drawdown protection on top of trend: {adds_to_trend} "
      f"(but at lower Sharpe — protection is not free)")

    # ----- 7. DSR + dd-reduction bootstrap CI on the overlay -----------------
    P("\n## 7. DSR + bootstrap CI of the overlay vs hodl\n")
    # DSR of the overlay's net return series (n_trials: ~2 metrics x 3 horizons x ~3 mechanics)
    rn = bt_sig["net"].dropna()
    mom = ret_moments(rn)
    n_trials = 18  # 2 metrics x 3 horizons x (floor + threshold + 200dma/vol baselines) ~ honest count
    dsr = deflated_sharpe(*mom, n_trials, trading_year=365) if mom else None
    if dsr:
        P(f"- overlay net Sharpe(ann365)={dsr['sr_annual']}  DSR={dsr['dsr']}  "
          f"sr0={dsr['sr0_annual']}  T={dsr['T']}  n_trials={n_trials}")
        P(f"  => {dsr_verdict(dsr['dsr'])}")
    else:
        P("- DSR: insufficient")

    # split_half_oos of overlay vs hodl
    sh = aa.split_half_oos(bt_sig["net"], bt_sig["ret"])
    if sh:
        P(f"- split-half overlay vs hodl: first beats_cagr={sh['first']['beats_cagr']} "
          f"(strat {sh['first']['cagr']} vs {sh['first']['hodl_cagr']}), "
          f"second beats_cagr={sh['second']['beats_cagr']} "
          f"(strat {sh['second']['cagr']} vs {sh['second']['hodl_cagr']}); robust={sh['robust']}")

    # bootstrap CI of the per-window dd-REDUCTION (overlay vs hodl). Build a series of
    # rolling 63d max-drawdowns for both and bootstrap the difference, CI must exclude 0.
    def roll_mdd_series(eq, w=63):
        out = []
        v = eq.values
        for i in range(len(v) - w):
            seg = v[i:i + w]
            out.append(float(np.min(seg) / seg[0] - 1.0))
        return np.array(out)
    eq_sig = bt_sig["eq"].reindex(sub_px.index)
    eq_h = (1 + bt_sig["ret"]).cumprod()
    dd_sig = roll_mdd_series(eq_sig)
    dd_hod = roll_mdd_series(eq_h)
    m = min(len(dd_sig), len(dd_hod))
    diff = dd_sig[:m] - dd_hod[:m]   # positive = overlay shallower that window
    rng = np.random.default_rng(SEED)
    block = 63
    n = len(diff)
    nb = int(np.ceil(n / block))
    boots = np.empty(4000)
    grid = np.arange(block)
    for b in range(4000):
        st = rng.integers(0, n, nb)
        idx = (st[:, None] + grid[None, :]).ravel()[:n] % n
        boots[b] = np.mean(diff[idx])
    lo, med, hi = [float(np.percentile(boots, p)) for p in (2.5, 50, 97.5)]
    ci_excl0 = lo > 0
    P(f"- rolling-63d dd-reduction bootstrap (overlay-hodl): "
      f"mean {np.mean(diff)*100:+.2f}pp  CI95 [{lo*100:+.2f}, {hi*100:+.2f}]pp  "
      f"excludes-0={ci_excl0}")

    # ----- VERDICT ------------------------------------------------------------
    P("\n## VERDICT — gate tally\n")
    gates = {
        "FDR any-horizon q<=0.10": bh_pass,
        "all-horizons NEGATIVE sign": sign_ok,
        "split-half same-sign(neg)": same_sign,
        "split-half same-magnitude(<0.10)": same_mag,
        "purged-folds all negative": folds_neg,
        "leave-one-crisis-out holds": loco_ok,
        "overlay beats 200dma (shallower MaxDD)": beats_sma,
        "overlay beats vol-timer (shallower MaxDD)": beats_vol,
        "overlay DSR>=0.90": bool(dsr and dsr["dsr"] >= 0.90),
        "dd-reduction CI excludes 0": ci_excl0,
    }
    for k, v in gates.items():
        P(f"  [{'PASS' if v else 'FAIL'}] {k}")
    P(f"\n- honest-N: ~{nclust} independent crash clusters (NOT {n} rows).")

    Path("reports").mkdir(exist_ok=True)
    Path("reports/btc-onchain-dd-phase0.md").write_text("\n".join(out_lines) + "\n")
    print("\n[written] reports/btc-onchain-dd-phase0.md")

    # machine-readable summary line
    print("\nSUMMARY_JSON", {
        "full_spear": {k: round(v, 3) for k, v in full_spear.items()},
        "split_half": [round(s1, 3), round(s2, 3)],
        "loco_ok": loco_ok, "folds_neg": folds_neg, "bh_pass": bh_pass,
        "hodl_mdd": round(hodl_mdd, 3), "onchain_mdd": round(sig_mdd, 3),
        "sma_mdd": round(sma_mdd, 3), "vol_mdd": round(vol_mdd, 3),
        "beats_sma": beats_sma, "beats_vol": beats_vol, "adds_to_trend": adds_to_trend,
        "or_mdd": round(or_mdd, 3),
        "dsr": dsr["dsr"] if dsr else None, "ci_excl0": ci_excl0, "nclust": int(nclust),
        "gates_passed": sum(gates.values()), "gates_total": len(gates),
    })


if __name__ == "__main__":
    main()
