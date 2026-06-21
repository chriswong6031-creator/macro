"""Phase-0: DIVERSIFIED cross-asset time-series momentum (TSMOM) — READ-ONLY research.

The repo already KILLED equity-only trend timing (SP_VECTOR_VIABILITY.md:66 —
Kaufman-ER gate negative on equities, "does not survive controlling for
net-liquidity"; net-liquidity subsumes trend). This tests the DIFFERENT construct
the literature actually supports and which the repo explicitly DEFERRED rather than
measured (SP_VECTOR_VIABILITY.md:129,172 — "Faber GTAA / GEM ... CAGR wins come from
diversification across uncorrelated sleeves / a futures structure, not from timing
one index"; Phase-4 "CAGR upgrade via diversification ... needs its own fresh OOS
proof; default to NOT building"):

  a DIVERSIFIED, vol-targeted, long/short 12-1 trend sleeve across
  equity / bonds / commodities / FX.

Its documented value is CRISIS ALPHA / convexity (positive in 8 of the 10 worst
60/40 drawdowns — QUANT_FACTOR_EXPANSION Family B), i.e. the drawdown-shaped payoff
the DSR gate can clear (cf. the S&P/Macro Vector). The honest bar:

  * net-of-cost annualized Sharpe + MaxDD vs a 60/40 and all-equity buy&hold
  * Deflated Sharpe (multiple-testing haircut over the lookbacks tried)
  * split-half (pre/post 2012) Sharpe SIGN consistency
  * a circular block-bootstrap CI on Sharpe + MaxDD
  * crisis-window convexity (does the sleeve PAY in 2008/2018Q4/2020/2022?)

No look-ahead: the signal/vol use data through t, backtest_core acts NEXT bar
(shift(1)); a one-way turnover cost is charged on |Δpos|.

Run:  ./.venv/bin/python scripts/tsmom_phase0.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.validation import (  # noqa: E402
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    block_bootstrap_ci, purged_folds, _maxdd, _sharpe,
)
from lib import store  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

# asset -> (yahoo store key, class). 4 classes = real diversification.
ASSETS: dict[str, tuple[str, str]] = {
    "SPY":    ("SPY",       "equity"),
    "TLT":    ("TLT",       "bond"),
    "gold":   ("GC=F",      "commodity"),
    "oil":    ("CL=F",      "commodity"),
    "copper": ("HG=F",      "commodity"),
    "dxy":    ("DX-Y.NYB",  "fx"),
}
# EXECUTABLE-TODAY variant: only liquid ETFs on disk (no DBC/UUP/GLD locally) —
# equity + duration + credit; NO commodity/FX leg (so weaker 2022 convexity expected).
ASSETS_ETF: dict[str, tuple[str, str]] = {
    "SPY": ("SPY", "equity"), "TLT": ("TLT", "bond"), "IEF": ("IEF", "bond"),
    "LQD": ("LQD", "credit"), "HYG": ("HYG", "credit"),
}
TARGET_VOL = 0.10        # per-leg annualized vol target
LEV_CAP = 3.0            # max per-leg leverage from the vol scaler
COST_BPS = 2.0           # one-way; liquid futures/ETFs
VOL_WIN = 63             # ~3m realized-vol window
ANN = 252
START = "2003-01-01"     # all 4 classes live; spans 4 independent SPY bears
SPLIT = "2012-01-01"
# the lookbacks we TRY -> the honest DSR trial count
GRID = {"3m": (63, 0), "6m": (126, 0), "12m": (252, 0), "12-1m": (252, 21)}
HEADLINE = "12-1m"
BLEND_WEIGHTS = (0.10, 0.15, 0.20, 0.30)   # overlay weights tried -> part of the DSR family
CRISES = [("2008 GFC", "2008-09-01", "2009-03-31"),
          ("2018Q4", "2018-10-01", "2018-12-31"),
          ("2020 COVID", "2020-02-19", "2020-03-31"),
          ("2022 bear", "2022-01-01", "2022-10-31")]


def load_px(assets: dict = ASSETS) -> pd.DataFrame:
    cols = {}
    for name, (tk, _cls) in assets.items():
        df = store.read("yahoo", tk)
        if df is None or "close" not in df.columns:
            print(f"  [skip] {name} ({tk}) — no data on disk")
            continue
        cols[name] = df["close"].rename(name)
    px = pd.DataFrame(cols).sort_index()
    px.index = pd.to_datetime(px.index)
    return px[~px.index.duplicated(keep="last")]


def sleeve_returns(px: pd.DataFrame, lb: int, skip: int) -> tuple[pd.Series, pd.DataFrame]:
    """Vol-targeted long/short 12-1 TSMOM, monthly rebalance, equal-risk aggregate."""
    mom = px.shift(skip) / px.shift(lb) - 1.0          # trailing return, recent `skip` days dropped
    sig = np.sign(mom)
    rets = px.pct_change()
    vol = rets.rolling(VOL_WIN).std() * np.sqrt(ANN)
    scale = (TARGET_VOL / vol).clip(upper=LEV_CAP)
    alloc = (sig * scale)                               # signed, vol-targeted, daily
    # monthly rebalance: hold the position fixed within a calendar month
    alloc_m = alloc.resample("MS").first().reindex(px.index).ffill()
    legs = {}
    for c in px.columns:
        bt = backtest_core(px[c], alloc_m[c], cost_bps=COST_BPS)   # next-bar, turnover cost
        legs[c] = bt["net"]
    L = pd.DataFrame(legs)
    port = L.mean(axis=1)                               # equal-risk weight (legs pre-vol-targeted)
    return port, L


def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 60:
        return {"n": len(r)}
    eq = (1.0 + r).cumprod()
    cagr = eq.iloc[-1] ** (ANN / len(r)) - 1.0
    return {"cagr": cagr * 100, "sharpe": _sharpe(r.to_numpy(), ANN),
            "maxdd": _maxdd(r.to_numpy()) * 100, "n": len(r)}


def fmt(label: str, m: dict, w: int = 24) -> str:
    if m.get("n", 0) < 60:
        return f"  {label:<{w}} (insufficient n={m.get('n', 0)})"
    return (f"  {label:<{w}} CAGR={m['cagr']:+6.2f}%  Sharpe={m['sharpe']:+5.2f}  "
            f"MaxDD={m['maxdd']:+7.1f}%  n={m['n']}")


def main() -> None:
    px = load_px()

    # Honest multiple-testing budget: log every config tried AT GENERATION, so each DSR
    # haircut below reads its N from the Trial Ledger instead of a hand-kept literal that
    # can silently desync from the grid (P3 keystone; research/SELF_IMPROVING_AI_SUITE.md).
    # Counts are identical to the old literals (sleeve=len(GRID)=4, overlay=4x4=16) — the
    # win is that they are now machine-derived, persisted, and auditable.
    led = TrialLedger()
    _cutoff = str(px.index.max().date())
    led.log_grid([{"lookback": nm, "lb": lb, "skip": skip} for nm, (lb, skip) in GRID.items()],
                 family="tsmom_diversified_sleeve", info_cutoff=_cutoff, source="tsmom_lookback_grid")
    led.log_grid([{"lookback": nm, "blend_w": w} for nm in GRID for w in BLEND_WEIGHTS],
                 family="tsmom_diversified_overlay", info_cutoff=_cutoff, source="tsmom_lookback_x_blend")

    print("=" * 96)
    print("DIVERSIFIED CROSS-ASSET TSMOM — Phase-0 (READ-ONLY)")
    print(f"  universe: {', '.join(px.columns)}  ({px.index.min().date()}..{px.index.max().date()})")
    print(f"  vol-target {TARGET_VOL:.0%}/leg, lev cap {LEV_CAP}x, cost {COST_BPS}bps one-way, "
          f"monthly rebal, analysis from {START}")
    print("=" * 96)

    # benchmarks ------------------------------------------------------------
    spy_bh = px["SPY"].pct_change()
    sixty40 = (0.6 * px["SPY"].pct_change() + 0.4 * px["TLT"].pct_change())
    bench = {"SPY buy&hold": spy_bh, "60/40 (SPY/TLT)": sixty40}

    # grid of lookbacks -----------------------------------------------------
    print("\n### LOOKBACK GRID (net of cost, from %s)" % START)
    ports = {}
    for nm, (lb, skip) in GRID.items():
        port, _L = sleeve_returns(px, lb, skip)
        ports[nm] = port.loc[START:]
        print(fmt(f"TSMOM {nm}", metrics(ports[nm])))
    for nm, b in bench.items():
        print(fmt(nm, metrics(b.loc[START:])))

    port = ports[HEADLINE]
    pm = metrics(port)

    # deflated sharpe (multiple-testing over the lookbacks tried) -----------
    print("\n### DEFLATED SHARPE — headline %s, n_trials=%d (the lookbacks tried, from the ledger)"
          % (HEADLINE, led.effective_n("tsmom_diversified_sleeve")))
    mom = ret_moments(port)
    if mom:
        sr_d, sk, ku, n = mom
        d = deflated_sharpe(sr_d, sk, ku, n, ledger=led, family="tsmom_diversified_sleeve",
                            trading_year=ANN)
        if d:
            print(f"  SR(annual)={d['sr_annual']:+.2f}  SR0(annual,haircut)={d['sr0_annual']:+.2f}  "
                  f"skew={d['skew']:+.2f}  kurt={d['kurt']:.1f}  T={d['T']}")
            print(f"  DSR = {d['dsr']:.4f}  -> {dsr_verdict(d['dsr'])}")

    # split-half sign consistency ------------------------------------------
    print("\n### SPLIT-HALF (OOS sign consistency) — headline %s" % HEADLINE)
    h1 = port.loc[START:SPLIT]
    h2 = port.loc[SPLIT:]
    s1, s2 = _sharpe(h1.dropna().to_numpy(), ANN), _sharpe(h2.dropna().to_numpy(), ANN)
    same = np.sign(s1) == np.sign(s2) and s1 != 0
    print(f"  2003-2011 Sharpe={s1:+.2f}   2012-2026 Sharpe={s2:+.2f}   "
          f"same-sign={'YES' if same else 'NO'}")

    # bootstrap CI ----------------------------------------------------------
    print("\n### BLOCK-BOOTSTRAP 95%% CI (block=21, B=5000) — headline %s" % HEADLINE)
    ci = block_bootstrap_ci(port, block=21, B=5000, ann=ANN)
    if ci:
        print(f"  Sharpe 95% CI {ci['sharpe_ci']}   MaxDD% 95% CI {ci['maxdd_ci_pct']}   "
              f"P(Sharpe>0)={ci['sharpe_gt0_prob']}")

    # crisis convexity ------------------------------------------------------
    print("\n### CRISIS CONVEXITY — cumulative return through each window (does the sleeve PAY?)")
    print(f"  {'window':<14}{'TSMOM':>10}{'60/40':>10}{'SPY':>10}")
    for nm, a, b in CRISES:
        def cum(r):
            w = r.loc[a:b].dropna()
            return (np.prod(1.0 + w.to_numpy()) - 1.0) * 100 if len(w) else float("nan")
        print(f"  {nm:<14}{cum(port):>9.1f}%{cum(sixty40):>9.1f}%{cum(spy_bh):>9.1f}%")

    # diversifying-overlay test: does adding the sleeve to 60/40 improve the BOOK? ---
    print("\n### OVERLAY TEST — blend headline %s into 60/40 (its scoreable form)" % HEADLINE)
    base = sixty40.loc[START:]
    print(fmt("60/40 alone", metrics(base)))
    best = None
    for w in BLEND_WEIGHTS:
        comb = ((1 - w) * base.reindex(port.index) + w * port).dropna()
        cm = metrics(comb)
        print(fmt(f"60/40 + {int(w * 100)}% TSMOM", cm))
        if best is None or cm["sharpe"] > best[1]["sharpe"]:
            best = (w, cm, comb)
    mom2 = ret_moments(best[2])
    if mom2:
        sr_d, sk, ku, n = mom2
        d2 = deflated_sharpe(sr_d, sk, ku, n, ledger=led, family="tsmom_diversified_overlay",
                             trading_year=ANN)
        if d2:
            ci2 = block_bootstrap_ci(best[2], block=21, B=5000, ann=ANN)
            print(f"  best blend = 60/40 + {int(best[0] * 100)}% TSMOM:  Sharpe={best[1]['sharpe']:+.2f} "
                  f"vs 60/40 {metrics(base)['sharpe']:+.2f}  MaxDD={best[1]['maxdd']:+.1f}% "
                  f"vs {metrics(base)['maxdd']:+.1f}%")
            print(f"  DSR={d2['dsr']:.4f} (n_trials={d2['n_trials']}) -> {dsr_verdict(d2['dsr'])}"
                  + (f"   Sharpe 95% CI {ci2['sharpe_ci']}" if ci2 else ""))

    # ============================ HARDEN ============================
    w = 0.30  # the max-Sharpe blend weight from the overlay test
    print("\n### HARDEN 1 — purged 5-fold CV (embargo=63d) on the headline sleeve (no fold should flip)")
    for k_, idx_ in purged_folds(port.index, k=5, embargo=63).items():
        s = port.reindex(idx_).dropna()
        print(f"  {k_}: Sharpe={_sharpe(s.to_numpy(), ANN):+.2f}  (n={len(s)})")

    print("\n### HARDEN 2 — leave-one-crisis-out (does the 60/40 + 30% overlay improvement survive?)")
    comb_full = (1 - w) * base.reindex(port.index) + w * port
    base_al = base.reindex(port.index)
    for nm, a, b in CRISES:
        keep = ~((comb_full.index >= a) & (comb_full.index <= b))
        cm, bm = metrics(comb_full[keep]), metrics(base_al[keep])
        dsh, ddd = cm["sharpe"] - bm["sharpe"], cm["maxdd"] - bm["maxdd"]
        print(f"  drop {nm:<11}: dSharpe={dsh:+.2f}  dMaxDD={ddd:+5.1f}pp  "
              f"-> {'holds' if dsh > 0 and ddd > 0 else 'WEAK'}")

    print("\n### HARDEN 3 — EXECUTABLE ETF-only sleeve (SPY/TLT/IEF/LQD/HYG; no commodities/FX)")
    pe = load_px(ASSETS_ETF)
    port_e, _ = sleeve_returns(pe, *GRID[HEADLINE])
    port_e = port_e.loc[START:]
    print(fmt("ETF-TSMOM standalone", metrics(port_e)))
    print(fmt("60/40 alone", metrics(base.loc[START:])))
    print(fmt("60/40 + 30% ETF-TSMOM", metrics(((1 - w) * base.reindex(port_e.index) + w * port_e).dropna())))
    print("  crisis convexity (ETF-only sleeve):")
    for nm, a, b in CRISES:
        ww = port_e.loc[a:b].dropna()
        cum = (np.prod(1.0 + ww.to_numpy()) - 1.0) * 100 if len(ww) else float("nan")
        print(f"    {nm:<12}{cum:+7.1f}%")

    print("\n" + "=" * 96)
    print("READ-ME: a SCOREABLE diversified-trend sleeve needs DSR>=0.90, same-sign split-half,")
    print("  a MaxDD materially shallower than 60/40, and POSITIVE crisis-window returns (convexity).")
    print("  Anything less = display/context, consistent with the equity-trend kill already on record.")
    print("=" * 96)


if __name__ == "__main__":
    main()
