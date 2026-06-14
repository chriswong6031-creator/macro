"""Phase-0 sniff test (NOT production): does standardized market-residual momentum
beat raw price momentum at ranking forward stock returns, on the ~3y S&P 1500 closes?

Honest + comparative. Same sample for every signal. Leans on rank-IC with a
Newey-West t (handles overlap); the long-short deflated-Sharpe is secondary because
the non-overlapping holding grid is tiny on 3y of data. No look-ahead:
  - betas use a trailing window and are lagged one day,
  - momentum skips the most recent 21d (t-1),
  - forward returns are shift(-H).

Run: .venv/bin/python -m scripts.research_residual_momentum
"""
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from engine.equity_factors import _closes
from lib import store
from engine.validation import rank_ic, ic_summary, ret_moments, deflated_sharpe, dsr_verdict

PRICE_FLOOR = 5.0          # liquidity/clean filter
SKIP = 21                  # skip most-recent month (t-1)
BETA_WIN = 126             # trailing window for market beta
SHRINK = 0.40              # Vasicek-style shrink of beta toward 1.0
MIN_NAMES = 100            # need a real cross-section to score a date


def load():
    P = _closes().sort_index()
    P = P.dropna(axis=1, how="all")
    spy = store.read("yahoo", "SPY")
    spy_c = spy["close"].reindex(P.index).ffill()
    R = P.pct_change(fill_method=None)
    m = spy_c.pct_change(fill_method=None)
    return P, R, m


def signals(P, R, m, F):
    """Return (raw_mom, resid_mom_standardized, resid_mom_raw) cross-sections."""
    # raw 12-1: price ratio from F days ago to SKIP days ago
    raw = P.shift(SKIP) / P.shift(F) - 1.0

    # vectorized trailing market beta, shrunk toward 1, lagged 1d (causal)
    rm = R.rolling(BETA_WIN).mean()
    mm = m.rolling(BETA_WIN).mean()
    rmm = R.mul(m, axis=0).rolling(BETA_WIN).mean()
    cov = rmm.sub(rm.mul(mm, axis=0))
    var = (m * m).rolling(BETA_WIN).mean() - mm * mm
    beta = cov.div(var, axis=0)
    beta = (1 - SHRINK) * beta + SHRINK * 1.0
    resid = R.sub(beta.shift(1).mul(m, axis=0))

    # cumulative residual over [t-F, t-SKIP]
    cum = resid.rolling(F).sum() - resid.rolling(SKIP).sum()
    rstd = resid.rolling(F).std()
    resid_std = cum / rstd          # info-ratio transform (Blitz standardization)
    return raw, resid_std, cum


def fwd_ret(P, H):
    return P.shift(-H) / P - 1.0


def first_valid_pos(sig, idx):
    cnt = sig.notna().sum(axis=1)
    ok = cnt >= MIN_NAMES
    if not ok.any():
        return len(idx)
    return idx.get_loc(ok.idxmax())


def eval_ic(P, sig, H, idx, step=10):
    fwd = fwd_ret(P, H)
    start = max(first_valid_pos(sig, idx), SKIP + 1)
    ics = []
    for d in idx[start:len(idx) - H:step]:
        liq = P.loc[d] >= PRICE_FLOOR
        ic = rank_ic(sig.loc[d][liq], fwd.loc[d][liq])
        if not np.isnan(ic):
            ics.append(ic)
    return pd.Series(ics)


def eval_ls(P, sig, H, idx):
    """Non-overlapping H-spaced long/short top-vs-bottom-decile holding returns."""
    fwd = fwd_ret(P, H)
    start = max(first_valid_pos(sig, idx), SKIP + 1)
    rets = []
    for d in idx[start:len(idx) - H:H]:
        liq = P.loc[d] >= PRICE_FLOOR
        df = pd.DataFrame({"s": sig.loc[d][liq], "f": fwd.loc[d][liq]}).dropna()
        if len(df) < MIN_NAMES:
            continue
        lo, hi = df["s"].quantile([0.1, 0.9])
        rets.append(df[df["s"] >= hi]["f"].mean() - df[df["s"] <= lo]["f"].mean())
    return pd.Series(rets)


def main():
    P, R, m = load()
    idx = P.index
    print(f"universe: {P.shape[1]} tickers | dates {idx.min().date()}..{idx.max().date()} "
          f"(n={len(idx)} trading days, ~{len(idx)/252:.1f}y)")

    variants = []
    for F in (126, 252):
        raw, res_std, res_raw = signals(P, R, m, F)
        variants += [(f"raw_F{F}", raw), (f"resid_std_F{F}", res_std), (f"resid_raw_F{F}", res_raw)]
    n_trials = len(variants)
    print(f"n_trials (signal variants) = {n_trials}  |  beta_win={BETA_WIN} shrink={SHRINK} skip={SKIP}\n")

    rows = []
    for H in (21, 63):
        for label, sig in variants:
            ics = eval_ic(P, sig, H, idx)
            s = ic_summary(ics, periods_per_year=25)
            ls = eval_ls(P, sig, H, idx)
            mom = ret_moments(ls)
            if mom:
                sr, sk, ku, T = mom
                ppy = 252.0 / H
                d = deflated_sharpe(sr, sk, ku, T, n_trials=n_trials, trading_year=ppy)
                sr_ann = sr * np.sqrt(ppy)
                dsr = d["dsr"] if d else float("nan")
            else:
                sr_ann, dsr, T = float("nan"), float("nan"), 0
            rows.append(dict(H=H, signal=label, n_ic=len(ics),
                             mean_ic=s["mean_ic"], ic_ir=s["ic_ir"], t_hac=s.get("t_hac"),
                             hit=s["hit"], ls_sharpe=sr_ann, ls_T=T, dsr=dsr))

    out = pd.DataFrame(rows)
    for c in ("mean_ic", "ic_ir", "t_hac", "hit", "ls_sharpe", "dsr"):
        out[c] = out[c].astype(float).round(3)
    print(out.to_string(index=False))

    print("\nsanity flags:")
    flagged = False
    for r in rows:
        if abs(r["mean_ic"]) > 0.12 or (not np.isnan(r["ls_sharpe"]) and abs(r["ls_sharpe"]) > 3):
            flagged = True
            print(f"  !! {r['signal']} H={r['H']}: IC={r['mean_ic']:.3f} Sharpe={r['ls_sharpe']:.2f}"
                  f" — implausibly large, suspect look-ahead/alignment")
    if not flagged:
        print("  none — IC magnitudes in the plausible (<0.12) range.")


if __name__ == "__main__":
    main()
