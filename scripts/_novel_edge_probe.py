"""DEV research probe (not a build step): test the PORTFOLIO-LEVEL edges that are more
likely to be real than single-name direction prediction. On the deep-history names +
SPY (survivor-biased — treat as directional, not gospel):

 1. VOL-MANAGED SIZING (Moreira-Muir 2017): scale exposure by inverse trailing vol.
    Does it lift the Sharpe of a buy-and-hold market with ZERO directional alpha?
 2. SHORT-TERM REVERSAL (cross-sectional): rank names weekly by prior-month return,
    long the losers / short the winners, hold 1 week. Spread + rank-IC, by VIX regime.
 3. SIGNAL DECORRELATION: pairwise corr of 12-1 momentum vs 1-month reversal — are they
    decorrelated enough to STACK (fundamental law: composite IC ~ ρ·√N_decorrelated)?
"""
from __future__ import annotations
import sys, glob, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from lib import config


def _ann_sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else float("nan")


def load_panel():
    """Wide daily close panel of the deep names + SPY + VIX."""
    closes = {}
    for f in sorted(glob.glob(str(config.data_dir() / "stocks" / "*.parquet"))):
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        s = df["close"].dropna()
        if len(s) > 800:
            closes[Path(f).stem] = s
    px = pd.DataFrame(closes).sort_index()
    try:
        spy = pd.read_parquet(config.data_dir() / "yahoo" / "SPY.parquet")["close"].dropna()
    except Exception:
        spy = px.mean(axis=1)
    try:
        vix = pd.read_parquet(config.data_dir() / "yahoo" / "_VIX.parquet")["close"].dropna()
    except Exception:
        vix = None
    return px, spy, vix


def test_vol_managed(spy, eqw_ret):
    print("\n=== 1) VOL-MANAGED SIZING (Moreira-Muir) — Sharpe uplift with NO directional alpha ===")
    for name, r in (("SPY", spy.pct_change()), ("EqualWeight-deep", eqw_ret)):
        r = r.dropna()
        rv = r.rolling(21).std()                      # trailing realized vol (the forecast)
        tgt = rv.median()
        scale = (tgt / rv).clip(upper=3.0).shift(1)   # size inversely to vol, lag 1 (causal)
        managed = (scale * r).dropna()
        base = r.loc[managed.index]
        print(f"  {name:18s} buy&hold Sharpe {_ann_sharpe(base):.2f}  ->  vol-managed "
              f"{_ann_sharpe(managed):.2f}   (uplift {_ann_sharpe(managed)-_ann_sharpe(base):+.2f})")


def test_reversal(px, vix):
    print("\n=== 2) SHORT-TERM REVERSAL (cross-sectional, weekly, long losers/short winners) ===")
    wk = px.resample("W-FRI").last()
    ret1m = wk.pct_change(4)                           # prior ~1 month
    fwd1w = wk.pct_change().shift(-1)                  # next week
    ics, spreads = [], []
    hi_vix_sp, lo_vix_sp = [], []
    vixw = vix.resample("W-FRI").last() if vix is not None else None
    vmed = vixw.median() if vixw is not None else None
    for dt in ret1m.index:
        s = ret1m.loc[dt].dropna()
        f = fwd1w.loc[dt].dropna() if dt in fwd1w.index else None
        common = s.index.intersection(f.index) if f is not None else []
        if len(common) < 30:
            continue
        s, f = s[common], f[common]
        ic = -s.rank().corr(f.rank())            # reversal => NEGATIVE corr of past->future
        ics.append(ic)
        q = s.rank(pct=True)
        spread = f[q <= 0.2].mean() - f[q >= 0.8].mean()   # losers minus winners
        spreads.append(spread)
        if vixw is not None and dt in vixw.index and pd.notna(vixw.loc[dt]):
            (hi_vix_sp if vixw.loc[dt] >= vmed else lo_vix_sp).append(spread)
    ics, spreads = np.array(ics), np.array(spreads)
    print(f"  reversal rank-IC: mean {np.nanmean(ics):+.4f}  t-stat "
          f"{np.nanmean(ics)/(np.nanstd(ics)/np.sqrt(len(ics))):+.2f}  (n={len(ics)} weeks)")
    print(f"  L/S weekly spread: mean {100*np.nanmean(spreads):+.3f}%  "
          f"ann {100*np.nanmean(spreads)*52:+.1f}%  hit {100*np.mean(spreads>0):.0f}%")
    if hi_vix_sp and lo_vix_sp:
        print(f"  by regime: HIGH-VIX spread {100*np.nanmean(hi_vix_sp):+.3f}%/wk  vs "
              f"LOW-VIX {100*np.nanmean(lo_vix_sp):+.3f}%/wk")


def test_decorrelation(px):
    print("\n=== 3) SIGNAL DECORRELATION — can momentum + reversal STACK? ===")
    wk = px.resample("W-FRI").last()
    mom = wk.pct_change(52) - wk.pct_change(4)         # 12-1 momentum (skip last month)
    rev = -wk.pct_change(4)                            # short-term reversal (loser = +)
    fwd = wk.pct_change(4).shift(-4)                   # next month
    mom_ic, rev_ic, both_ic, corrs = [], [], [], []
    for dt in mom.index:
        m, rv = mom.loc[dt].dropna(), rev.loc[dt].dropna()
        f = fwd.loc[dt].dropna() if dt in fwd.index else None
        if f is None:
            continue
        c = m.index.intersection(rv.index).intersection(f.index)
        if len(c) < 30:
            continue
        m, rv, f = m[c], rv[c], f[c]
        mz, rz = (m - m.mean()) / m.std(), (rv - rv.mean()) / rv.std()
        corrs.append(mz.corr(rz))
        mom_ic.append(mz.rank().corr(f.rank()))
        rev_ic.append(rz.rank().corr(f.rank()))
        both_ic.append(((mz + rz) / 2).rank().corr(f.rank()))
    print(f"  mean cross-sectional corr(momentum, reversal): {np.nanmean(corrs):+.2f}  "
          "(near 0 = decorrelated = they stack)")
    print(f"  monthly rank-IC:  momentum {np.nanmean(mom_ic):+.4f}  reversal {np.nanmean(rev_ic):+.4f}  "
          f"50/50 blend {np.nanmean(both_ic):+.4f}")
    print(f"  blend IC / best-single: {np.nanmean(both_ic)/max(abs(np.nanmean(mom_ic)),abs(np.nanmean(rev_ic)),1e-9):.2f}x")


def main():
    px, spy, vix = load_panel()
    print(f"panel: {px.shape[1]} deep names x {len(px)} bars ({px.index[0].date()}..{px.index[-1].date()})")
    eqw_ret = px.pct_change().mean(axis=1)
    test_vol_managed(spy, eqw_ret)
    test_reversal(px, vix)
    test_decorrelation(px)


if __name__ == "__main__":
    main()
