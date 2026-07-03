#!/usr/bin/env python3
"""C1 — Commodity→Sector transmission phase-0 (HK/CA masterplan §4.1 W2).

Episode-honest event study per research/C1_COMMODITY_SECTOR_PREREG.md. NO wiring.

Regime-episode definition (frozen in pre-reg):
  slope_z of log(close) over 63d window, standardized over 252d; +0.5/-0.5 hysteresis
  dead-band; >=20 trading-day min-duration debounce. A POSITIVE flip = first day of a
  new confirmed BULL episode. Forward 2/4/6/8w sector-ETF excess vs _GSPTSE, NEXT-BAR
  fill, NON-OVERLAPPING episodes (greedy), suspension-honest (drop windows past data end).

Stats: HAC t (newey_west_tstat), BH-FDR within the gated family, bootstrap_effective_t,
DSR at program n_trials=30 (deflated_sharpe), block_bootstrap_ci, split-half at 2013.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import (  # noqa: E402
    newey_west_tstat, benjamini_hochberg, bootstrap_effective_t,
    deflated_sharpe,
)
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402

# ---- frozen pre-reg constants -------------------------------------------------
SLOPE_WIN = 63          # trend slope window (~13wk)
Z_WIN = 252             # standardization window
Z_MINP = 200
HYST = 0.5              # +/- dead-band
MIN_DUR = 20            # min-duration debounce (trading days, ~4wk)
HORIZONS = {"2w": 10, "4w": 20, "6w": 30, "8w": 40}
PRIMARY_H = "4w"
SPLIT_DATE = pd.Timestamp("2013-01-01")
N_TRIALS = 30           # program-level DSR n_trials (masterplan §6), ledger-declared floor
FAMILY = "c1_commodity_sector_phase0"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)
DSR_BLOCK = 21

DATA_C = ROOT / "data" / "canada"
DATA_Y = ROOT / "data" / "yahoo"


def _load(path: Path) -> pd.Series:
    df = pd.read_parquet(path)
    s = df["close"].astype(float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index().dropna()


def slope_z(logp: pd.Series) -> pd.Series:
    """Rolling OLS slope of logp on a 0..W-1 index, then rolling z over Z_WIN."""
    x = np.arange(SLOPE_WIN, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())

    def _slope(win):
        y = win - win.mean()
        return float((x * y).sum() / denom)

    slope = logp.rolling(SLOPE_WIN).apply(_slope, raw=True)
    mu = slope.rolling(Z_WIN, min_periods=Z_MINP).mean()
    sd = slope.rolling(Z_WIN, min_periods=Z_MINP).std(ddof=0)
    return (slope - mu) / sd.replace(0.0, np.nan)


def regime_state(sz: pd.Series) -> pd.Series:
    """Hysteresis dead-band state machine: +1 bull / -1 bear / 0 neutral.
    Enter bull when sz>+HYST; leave bull only when sz<-HYST (then enter bear); symmetric."""
    state = pd.Series(0, index=sz.index, dtype=int)
    cur = 0
    for i, v in enumerate(sz.values):
        if np.isnan(v):
            state.iloc[i] = cur
            continue
        if cur == 1:
            cur = -1 if v < -HYST else 1
        elif cur == -1:
            cur = 1 if v > HYST else -1
        else:  # neutral (only at the very start before first threshold cross)
            if v > HYST:
                cur = 1
            elif v < -HYST:
                cur = -1
        state.iloc[i] = cur
    return state


def confirmed_flips(state: pd.Series, target: int) -> list[pd.Timestamp]:
    """First day of each NEW `target`-signed episode that holds >= MIN_DUR days.
    Debounce: a run of the target state shorter than MIN_DUR does not count."""
    vals = state.values
    idx = state.index
    flips = []
    n = len(vals)
    i = 0
    prev_kept = None  # previous confirmed episode sign
    while i < n:
        j = i
        while j < n and vals[j] == vals[i]:
            j += 1
        run_sign = vals[i]
        run_len = j - i
        if run_sign == target and run_len >= MIN_DUR and prev_kept != target:
            flips.append(idx[i])
            prev_kept = target
        elif run_sign != 0 and run_len >= MIN_DUR:
            # a confirmed opposite/neutral episode resets prev_kept so the NEXT
            # target episode counts as a fresh flip
            prev_kept = run_sign
        i = j
    return flips


def raw_flip_count(state: pd.Series, target: int) -> int:
    """Count of state transitions INTO target (no min-duration debounce) — the
    inflated raw count the critic warned about; reported for contrast."""
    prev = state.shift(1)
    return int(((state == target) & (prev != target)).sum())


def fwd_excess(etf: pd.Series, bench: pd.Series, entry_dates, H: int):
    """Non-overlapping (greedy) episode excess returns, next-bar fill, suspension-honest.
    Returns (episode_returns list of (entry_fill_date, excess), daily_excess_in_window Series)."""
    eidx = etf.index
    # map each flip day -> next available ETF bar (next-bar fill)
    pos = eidx.searchsorted(pd.DatetimeIndex(entry_dates), side="right")
    eps = []
    daily = []  # daily excess returns while inside a claimed window (for t_eff)
    claimed_until = -1  # positional index in eidx up to which we're inside a window
    r_etf = etf.pct_change()
    r_bench = bench.reindex(etf.index).pct_change()
    for p in pos:
        if p >= len(eidx):
            continue  # flip too late, no next bar
        if p <= claimed_until:
            continue  # overlaps a prior claimed window -> drop (non-overlap filter)
        end = p + H
        if end >= len(eidx):
            continue  # window runs past data end -> drop (suspension-honest, no partial)
        fill_date = eidx[p]
        end_date = eidx[end]
        # cumulative total return over [fill, end] using present bars only (no ffill through gaps)
        etf_ret = etf.loc[fill_date:end_date]
        bch = bench.reindex(etf.loc[fill_date:end_date].index)
        # align on intersection of present (non-NaN) bars on BOTH legs
        pair = pd.concat([etf_ret, bch], axis=1).dropna()
        if len(pair) < 2:
            continue
        etf_cum = pair.iloc[-1, 0] / pair.iloc[0, 0] - 1.0
        bch_cum = pair.iloc[-1, 1] / pair.iloc[0, 1] - 1.0
        eps.append((fill_date, etf_cum - bch_cum))
        # daily excess inside the window for t_eff
        de = (r_etf.iloc[p + 1:end + 1] - r_bench.iloc[p + 1:end + 1]).dropna()
        daily.append(de)
        claimed_until = end
    ep_ret = pd.Series({d: v for d, v in eps}).sort_index() if eps else pd.Series(dtype=float)
    daily_ex = pd.concat(daily) if daily else pd.Series(dtype=float)
    return ep_ret, daily_ex


def analyse_trial(name, commodity, etf, bench, target=1):
    logp = np.log(commodity)
    sz = slope_z(logp)
    state = regime_state(sz)
    flips = confirmed_flips(state, target)
    raw = raw_flip_count(state, target)
    out = {"name": name, "target": target, "raw_flips": raw,
           "confirmed_flips": len(flips), "horizons": {}}
    for hlabel, H in HORIZONS.items():
        ep, daily = fwd_excess(etf, bench, flips, H)
        n = len(ep)
        row = {"n_episodes": n}
        if n >= 3:
            nw = newey_west_tstat(ep.values, lags=4)
            row.update(mean=nw["mean"], hac_se=nw["se"], hac_t=nw["t"], hac_p=nw["p"])
            row["hit"] = round(float((ep > 0).mean()), 3)
            # bootstrap effective t on daily in-window excess
            teff = bootstrap_effective_t(daily, block=DSR_BLOCK) if len(daily) >= 60 else {}
            row["t_eff"] = teff.get("t_eff")
            row["t_eff_raw"] = teff.get("t_raw")
            # DSR on episode returns (per-episode Sharpe), n_trials=30
            m, sd = float(ep.mean()), float(ep.std(ddof=1))
            if sd > 0 and n >= 4:
                from scipy.stats import skew as _sk, kurtosis as _ku
                sr = m / sd
                dsr = deflated_sharpe(sr, float(_sk(ep.values)), float(_ku(ep.values, fisher=False)),
                                      T=n, ledger=_LED, family=FAMILY,
                                      t_eff=teff.get("t_eff") if teff else None)
                row["sr_episode"] = round(sr, 4)
                row["dsr"] = dsr["dsr"] if dsr else None
            # bootstrap 90% CI on the MEAN episode return (episodes ~independent by
            # non-overlap construction, so an iid resample of the mean is appropriate;
            # block_bootstrap_ci targets long DAILY series and would return {} at n~10).
            if n >= 6:
                rng = np.random.default_rng(11)
                boots = np.array([rng.choice(ep.values, n, replace=True).mean()
                                  for _ in range(5000)])
                row["mean_ci90"] = [round(float(np.percentile(boots, 5)), 5),
                                    round(float(np.percentile(boots, 95)), 5)]
                row["mean_gt0_prob"] = round(float((boots > 0).mean()), 3)
            # split-half sign
            pre = ep[ep.index < SPLIT_DATE]
            post = ep[ep.index >= SPLIT_DATE]
            row["split"] = {
                "pre_n": len(pre), "pre_mean": round(float(pre.mean()), 5) if len(pre) else None,
                "post_n": len(post), "post_mean": round(float(post.mean()), 5) if len(post) else None,
                "same_sign": (len(pre) > 0 and len(post) > 0 and
                              np.sign(pre.mean()) == np.sign(post.mean()) and pre.mean() != 0),
            }
            row["episodes"] = [(str(d.date()), round(float(v), 4)) for d, v in ep.items()]
        out["horizons"][hlabel] = row
    return out


def verdict(row):
    """Per-trial verdict at primary horizon per pre-reg §5."""
    if row.get("n_episodes", 0) < 3 or row.get("hac_t") is None:
        return "NO-GO (insufficient episodes)"
    t = row["hac_t"]; dsr = row.get("dsr"); m = row["mean"]
    same = row.get("split", {}).get("same_sign", False)
    n = row["n_episodes"]
    if t is not None and t <= -2.0:
        return "KILL (significantly negative)"
    if m <= 0:
        return "NO-GO (non-positive mean)"
    if not same:
        return "NO-GO (split-half sign flip)"
    go = (t >= 2.0 and (dsr is not None and dsr >= 0.90) and same and n >= 8)
    if go:
        return "GO"
    if (m > 0) and (t >= 1.0 or (dsr is not None and dsr >= 0.50)):
        return "ACCRUE"
    return "NO-GO"


@register_trials("c1_commodity_sector_phase0", budget=N_TRIALS, basis="estimated",
                 reason="masterplan §6 program-level DSR budget (both markets)")
def main():
    cl = _load(DATA_Y / "CL_F.parquet")
    gc = _load(DATA_Y / "GC_F.parquet")
    hg = _load(DATA_Y / "HG_F.parquet")
    bench = _load(DATA_C / "_GSPTSE.parquet")
    xeg = _load(DATA_C / "XEG.TO.parquet")
    xgd = _load(DATA_C / "XGD.TO.parquet")
    xbm = _load(DATA_C / "XBM.TO.parquet")
    xma = _load(DATA_C / "XMA.TO.parquet")

    gated = [
        analyse_trial("T1 oil->XEG", cl, xeg, bench, +1),
        analyse_trial("T2 gold->XGD", gc, xgd, bench, +1),
        analyse_trial("T3 copper->XBM", hg, xbm, bench, +1),
    ]
    secondary = analyse_trial("T3b copper->XMA", hg, xma, bench, +1)
    # exploratory negative-flip side
    neg = [
        analyse_trial("T1n oil->XEG NEG", cl, xeg, bench, -1),
        analyse_trial("T2n gold->XGD NEG", gc, xgd, bench, -1),
        analyse_trial("T3n copper->XBM NEG", hg, xbm, bench, -1),
    ]

    # BH-FDR across the 3 gated trials at primary horizon
    pvals = {}
    for t in gated:
        r = t["horizons"][PRIMARY_H]
        if r.get("hac_p") is not None:
            # one-sided positive p = p/2 if mean>0 else 1-p/2
            two = r["hac_p"]
            one = two / 2 if (r.get("mean", 0) or 0) > 0 else 1 - two / 2
            pvals[t["name"]] = one
    bh = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    import json
    print(json.dumps({
        "gated": gated, "secondary": secondary, "negative_exploratory": neg,
        "bh_fdr_primary": bh, "pvals_onesided": pvals,
        "verdicts": {t["name"]: verdict(t["horizons"][PRIMARY_H]) for t in gated},
        "secondary_verdict": verdict(secondary["horizons"][PRIMARY_H]),
        "params": {"slope_win": SLOPE_WIN, "z_win": Z_WIN, "hyst": HYST,
                   "min_dur": MIN_DUR, "primary_h": PRIMARY_H, "n_trials": N_TRIALS,
                   "split_date": str(SPLIT_DATE.date())},
    }, indent=2, default=str))


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    main()
