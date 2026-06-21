"""Net-liquidity (WALCL - TGA - RRP) regime gate on the long book.

SELF-CONTAINED research script. Does NOT edit any engine/scripts file.

Question: does the US NET LIQUIDITY regime (expanding vs contracting) condition
equity forward returns of an equal-weight book of the 114 deep-history mega-caps,
and of a 200dma trend sleeve?

Construction (matches engine D10 / scripts.research_liquidity_gate.net_liquidity):
  net_liq = WALCL/1000 - RRP - TGA/1000   ($bn)
  WALCL weekly (Wed, released Thu) -> ffill to daily; RRP/TGA daily.
  Whole series LAGGED 3 business days (release delay + safety) => CAUSAL.
  Signal = 13-week (65bd) rate-of-change of net_liq.
  EXPANDING = roc13 > 0 ; CONTRACTING = roc13 < 0  (also a banded variant).

HONESTY:
  - Every signal value at t uses only data <= t (ffill of last-known + 3bd lag).
  - Positions act next bar via backtest_core's internal shift(1).
  - Forward windows strictly future (close.shift(-h)/close - 1).
  - NET-OF-COST 5bps one-way on the daily-traded gated strategy.
  - HAC (Newey-West) t-stat on the regime difference (forward windows overlap).
  - DSR with honest n_trials declared.
  - SURVIVORSHIP: data/stocks = 114 CURRENT survivors => cross-sectional book
    returns are an optimistic CONTEXT bound, not proven tradable alpha.
"""
from __future__ import annotations
import os
import tempfile
import numpy as np
import pandas as pd

import lib.store as store
from engine.trial_ledger import TrialLedger
from engine.validation import (
    backtest_core, deflated_sharpe, dsr_verdict, newey_west_tstat,
    block_bootstrap_ci,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
LAG_BD = 3
ROC13 = 65          # ~13 trading weeks
START = "2010-01-01"
COST_BPS = 5.0
TRADING_YEAR = 252


def _col(df):
    return df.iloc[:, 0]


def net_liquidity() -> pd.Series:
    walcl = _col(pd.read_parquet(f"{DATA}/fred/WALCL.parquet")) / 1000.0   # $mn->$bn
    rrp_fred = _col(pd.read_parquet(f"{DATA}/fred/RRPONTSYD.parquet"))     # $bn
    rrp_ny = pd.read_parquet(f"{DATA}/nyfed/rrp.parquet")["rrp_bn"]
    tga = pd.read_parquet(f"{DATA}/treasury/tga.parquet")["tga_mn"] / 1000.0
    idx = pd.bdate_range(START, pd.Timestamp.utcnow().tz_localize(None).normalize())
    walcl_bn = walcl.reindex(walcl.index.union(idx)).ffill(limit=7).reindex(idx)
    rrp_bn = rrp_ny.combine_first(rrp_fred)
    rrp_bn = rrp_bn.reindex(rrp_bn.index.union(idx)).ffill(limit=5).reindex(idx).fillna(0)
    tga_bn = tga.reindex(tga.index.union(idx)).ffill(limit=5).reindex(idx)
    nl = (walcl_bn - rrp_bn - tga_bn).dropna()
    return nl.shift(LAG_BD)   # anti-look-ahead lag


def load_book():
    """Equal-weight daily return of the 114-stock book, and a 200dma trend sleeve."""
    files = sorted(f[:-8] for f in os.listdir(f"{DATA}/stocks") if f.endswith(".parquet"))
    closes = {}
    for t in files:
        try:
            s = store.read("stocks", t)["close"].dropna()
        except Exception:
            continue
        if len(s) > 300:
            closes[t] = s
    px = pd.DataFrame(closes).sort_index()
    px = px[px.index >= START]
    rets = px.pct_change()

    # EW book daily return: mean of available single-name returns
    ew = rets.mean(axis=1)

    # 200dma trend sleeve: each day hold only names with close > its own 200dma
    ma200 = px.rolling(200, min_periods=200).mean()
    above = (px > ma200).shift(1)           # decision uses yesterday's close vs ma => causal
    trend_ret = (rets.where(above)).mean(axis=1)   # EW over names currently above 200dma

    # synthetic EW book PRICE level (for backtest_core / forward windows)
    ew_lvl = (1.0 + ew.fillna(0)).cumprod()
    trend_lvl = (1.0 + trend_ret.fillna(0)).cumprod()
    return ew, ew_lvl, trend_ret, trend_lvl, px.shape[1]


def fwd_return(level: pd.Series, h: int) -> pd.Series:
    return level.shift(-h) / level - 1.0


def regime_stats(fwd: pd.Series, mask: pd.Series, label: str, h: int):
    """Mean fwd return + annualized Sharpe (of the fwd-window returns) per regime."""
    f = fwd[mask].dropna()
    if len(f) < 30:
        return {"label": label, "n": len(f), "mean_pct": None, "sharpe": None}
    mean = f.mean()
    # Sharpe of h-day forward returns, annualized by sqrt(252/h)
    sd = f.std(ddof=1)
    sharpe = (mean / sd) * np.sqrt(TRADING_YEAR / h) if sd > 0 else np.nan
    return {"label": label, "n": int(len(f)),
            "mean_pct": round(100 * mean, 3),
            "sharpe": round(float(sharpe), 3)}


def hac_diff(fwd: pd.Series, exp_mask: pd.Series, con_mask: pd.Series, h: int):
    """Difference-in-means (expanding - contracting) with two HONEST tests.

    (A) HAC: regress fwd on a +1/-1 regime dummy via OLS with the proper
        Newey-West sandwich SE (Var(b)=(X'X)^-1 S (X'X)^-1, S = Bartlett-weighted
        long-run var of the score x_t*resid_t, lags=h). diff = 2*slope.
    (B) Non-overlapping subsample: take every h-th observation so forward windows
        DON'T overlap, then a plain Welch t on the diff = honest effective-N test.
    """
    idx = fwd.index
    code = pd.Series(np.nan, index=idx)
    code[exp_mask] = 1.0
    code[con_mask] = -1.0
    df = pd.DataFrame({"y": fwd, "d": code}).dropna()
    if len(df) < 50 or df["d"].nunique() < 2:
        return None
    y = df["y"].values
    d = df["d"].values
    # OLS with intercept: y = a + b*d ; design X = [1, d]
    X = np.column_stack([np.ones_like(d), d])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    T = len(y)
    # NW long-run covariance of the score u_t = X_t * resid_t
    u = X * resid[:, None]                       # (T,2)
    S = (u.T @ u)                                # gamma_0 * T
    for L in range(1, h + 1):
        w = 1.0 - L / (h + 1.0)
        gL = u[L:].T @ u[:-L]
        S += w * (gL + gL.T)
    cov_beta = XtX_inv @ S @ XtX_inv
    slope = beta[1]
    se_slope = np.sqrt(cov_beta[1, 1])
    diff = 2.0 * slope                           # dummy spans -1..+1
    t_hac = (slope / se_slope) if se_slope > 0 else np.nan

    # (B) non-overlapping subsample Welch t
    sub = df.iloc[::h]
    es = sub.loc[sub["d"] == 1, "y"]
    cs = sub.loc[sub["d"] == -1, "y"]
    if len(es) >= 8 and len(cs) >= 8:
        from scipy import stats as _st
        t_no, p_no = _st.ttest_ind(es, cs, equal_var=False)
        diff_no = es.mean() - cs.mean()
        t_no, p_no, n_no = round(float(t_no), 3), round(float(p_no), 4), int(len(es) + len(cs))
    else:
        t_no = p_no = None
        diff_no = np.nan
        n_no = 0
    return {"diff_pct": round(100 * diff, 3), "t_hac": round(float(t_hac), 3),
            "n": int(T), "nw_lags": h,
            "diff_noverlap_pct": (round(100 * diff_no, 3) if not np.isnan(diff_no) else None),
            "t_noverlap": t_no, "p_noverlap": p_no, "n_noverlap": n_no}


def gated_strategy(level: pd.Series, regime_long: pd.Series, name: str, n_trials: int):
    """Long the book only when regime_long is True (else flat), NET of 5bps cost."""
    alloc = regime_long.reindex(level.index).fillna(False).astype(float)
    bt = backtest_core(level, alloc, cost_bps=COST_BPS)
    net = bt["net"].dropna()
    if len(net) < 252:
        return None
    mean_d = net.mean()
    sd_d = net.std(ddof=1)
    sr_d = mean_d / sd_d if sd_d > 0 else 0.0
    sr_ann = sr_d * np.sqrt(TRADING_YEAR)
    cagr = (1 + net).prod() ** (TRADING_YEAR / len(net)) - 1
    skew = net.skew()
    kurt = net.kurt()
    _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                       family="net_liquidity_gate")
    _led.log_grid([{"trial": i} for i in range(int(n_trials))], family="net_liquidity_gate")
    dsr = deflated_sharpe(sr_d, skew, kurt, len(net), ledger=_led, family="net_liquidity_gate", trading_year=TRADING_YEAR)
    # buy-and-hold benchmark on same level
    bh = level.pct_change().dropna()
    bh_sr_ann = (bh.mean() / bh.std(ddof=1)) * np.sqrt(TRADING_YEAR) if bh.std(ddof=1) > 0 else 0
    bh_cagr = (1 + bh).prod() ** (TRADING_YEAR / len(bh)) - 1
    return {"name": name, "n_days": len(net), "exposure": round(float(alloc.reindex(net.index).mean()), 3),
            "sharpe_net_ann": round(float(sr_ann), 3), "cagr_net": round(float(cagr), 4),
            "turnover_yr": round(float(bt["turnover"].reindex(net.index).sum() / bt["years"]), 1),
            "dsr": (round(dsr["dsr"], 4) if dsr else None),
            "dsr_verdict": (dsr_verdict(dsr["dsr"]) if dsr else "n/a"),
            "bh_sharpe_ann": round(float(bh_sr_ann), 3), "bh_cagr": round(float(bh_cagr), 4)}


def main():
    nl = net_liquidity().dropna()
    roc = nl.diff(ROC13)
    print(f"net-liquidity: {nl.index.min().date()}..{nl.index.max().date()} "
          f"(lagged {LAG_BD}bd) last={nl.iloc[-1]:.0f}bn")
    print(f"roc13 (>0 expanding): coverage {roc.dropna().index.min().date()}..{roc.dropna().index.max().date()}")

    ew, ew_lvl, trend_ret, trend_lvl, n_names = load_book()
    print(f"book: {n_names} names, EW daily ret {ew.dropna().index.min().date()}..{ew.dropna().index.max().date()}")

    # align regime to book trading days
    roc_d = roc.reindex(ew_lvl.index).ffill()
    exp_mask = roc_d > 0
    con_mask = roc_d < 0
    # banded variant (clear expansion/contraction; $bn/quarter threshold)
    THR = 100.0
    exp_b = roc_d > THR
    con_b = roc_d < -THR

    print(f"\nregime split (daily, EW book days): expanding={int(exp_mask.sum())} "
          f"contracting={int(con_mask.sum())}  | banded(±{THR:.0f}bn): "
          f"exp={int(exp_b.sum())} con={int(con_b.sum())}")

    out = {"horizons": {}, "strategies": [], "n_trials": None}
    # honest n_trials: 2 books x 2 horizons x 2 regime defs (sign / banded) x
    #                  2 (gate-long, gate-and-overlay) ~ count what we actually scan
    N_TRIALS = 16
    out["n_trials"] = N_TRIALS

    for label, fwdL, lvl in (("EW_book", ew_lvl, ew_lvl), ("trend200_sleeve", trend_lvl, trend_lvl)):
        for h in (21, 63):
            fwd = fwd_return(fwdL, h)
            es = regime_stats(fwd, exp_mask, "expanding(roc13>0)", h)
            cs = regime_stats(fwd, con_mask, "contracting(roc13<0)", h)
            esb = regime_stats(fwd, exp_b, f"expanding(>+{THR:.0f})", h)
            csb = regime_stats(fwd, con_b, f"contracting(<-{THR:.0f})", h)
            hac = hac_diff(fwd, exp_mask, con_mask, h)
            hac_b = hac_diff(fwd, exp_b, con_b, h)
            key = f"{label}_{h}d"
            out["horizons"][key] = {"exp": es, "con": cs, "exp_band": esb,
                                    "con_band": csb, "hac_sign": hac, "hac_band": hac_b}
            print(f"\n=== {label}  fwd {h}d ===")
            for s in (es, cs, esb, csb):
                print(f"  {s['label']:<26} n={s['n']:>5} mean={s['mean_pct']}%  Sharpe={s['sharpe']}")
            if hac:
                print(f"  DIFF(exp-con) sign-split: {hac['diff_pct']}%  HAC t={hac['t_hac']} (lags={hac['nw_lags']}, n={hac['n']})  "
                      f"| non-overlap t={hac['t_noverlap']} p={hac['p_noverlap']} (n={hac['n_noverlap']})")
            if hac_b:
                print(f"  DIFF(exp-con) banded:     {hac_b['diff_pct']}%  HAC t={hac_b['t_hac']}  "
                      f"| non-overlap t={hac_b['t_noverlap']} p={hac_b['p_noverlap']}")

    # ---- net-of-cost gated long strategies ----
    print("\n--- NET-OF-COST gated long strategies (5bps one-way) ---")
    for label, lvl, reg in (("EW_book / gate-long-when-expanding", ew_lvl, exp_mask),
                            ("trend200 / gate-long-when-expanding", trend_lvl, exp_mask),
                            ("EW_book / gate-long-when-roc>+100", ew_lvl, exp_b)):
        st = gated_strategy(lvl, reg, label, N_TRIALS)
        if st:
            out["strategies"].append(st)
            print(f"  {st['name']}")
            print(f"    exposure={st['exposure']} netSharpe={st['sharpe_net_ann']} "
                  f"netCAGR={st['cagr_net']} turnover/yr={st['turnover_yr']} "
                  f"DSR={st['dsr']} ({st['dsr_verdict']})  vs B&H Sharpe={st['bh_sharpe_ann']} CAGR={st['bh_cagr']}")

    # block-bootstrap CI on the headline regime difference (EW book, 63d sign-split fwd)
    fwd63 = fwd_return(ew_lvl, 63)
    e = fwd63[exp_mask].dropna()
    c = fwd63[con_mask].dropna()
    print(f"\nheadline (EW book 63d): mean fwd  expanding={100*e.mean():.3f}%  "
          f"contracting={100*c.mean():.3f}%  gap={100*(e.mean()-c.mean()):.3f}%")

    return out


if __name__ == "__main__":
    main()
