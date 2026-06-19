"""TRACK-A VERIFY — Credit Carry & Duration Timing (signal_lab candidate).

READ-ONLY research. Re-runs the LIVE engine.strategies allocations through the
shared validation harness and recomputes EVERY signal_lab gate from scratch on the
deepest history available on disk, so the verdict rests on numbers I actually
computed here (not the cached report text):

  * DSR (deflated Sharpe, n_trials = the 4 glide variants the report swept)
  * split-half OOS (same-sign edge vs buy&hold in BOTH halves)
  * leave-one-crisis-out (Sharpe edge vs B&H with each crisis window dropped)
  * beats-the-dumb-baseline (200dma trend on the SAME asset + buy&hold)
  * dd-reduction block-bootstrap CI excludes 0
  * honest-N (independent crisis clusters, not raw row count)

No look-ahead: the live alloc factories already PIT-lag every leg; backtest_core
acts the position NEXT bar (shift(1)); the de-risked sleeve earns the cash carry.

The on-disk store now prefers a 3yr 'authoritative' HY TR stub for hy_tr(); for an
honest DEEP-history re-run we use the full HYG adjusted close (2007->, ~19yr) like
the original report, and full TLT (2002->, ~24yr).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine import total_return as tr
from engine import strategies as S
from engine.validation import (
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    block_bootstrap_ci, _sharpe as v_sharpe, _maxdd as v_maxdd,
)

ANN = 252


def _stats(net: pd.Series, years: float) -> dict:
    r = net.dropna()
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 else float("nan")
    return {"cagr": 100 * cagr, "sharpe": v_sharpe(r.to_numpy(), ANN),
            "maxdd": 100 * v_maxdd(r.to_numpy())}


def _baseline_200dma(close: pd.Series, cash: pd.Series, cost_bps=3.0) -> pd.Series:
    """The DUMB baseline: long when close > 200d SMA else flat-in-cash. Signal uses
    data through t; backtest_core acts next bar."""
    sma = close.rolling(200, min_periods=200).mean()
    alloc = (close > sma).astype(float)
    bt = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=cash)
    return bt["net"]


def _baseline_buydrawdown(close: pd.Series, cash: pd.Series, cost_bps=3.0) -> pd.Series:
    """Placebo: 'buy every drawdown' — fully long whenever price is >5% below its
    trailing 1y high (i.e. always-in on dips), else flat. A dumb dip-buyer."""
    hi = close.rolling(252, min_periods=60).max()
    alloc = ((close / hi - 1.0) < -0.05).astype(float)
    bt = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=cash)
    return bt["net"]


# crisis windows for leave-one-crisis-out (independent stress clusters = honest-N)
CRISES = {
    "credit": [
        ("GFC 2008", "2007-07-01", "2009-06-30"),
        ("euro 2011", "2011-05-01", "2012-06-30"),
        ("energy/EM 2015-16", "2015-07-01", "2016-03-31"),
        ("COVID 2020", "2020-02-01", "2020-05-31"),
        ("rate/credit 2022", "2022-01-01", "2022-12-31"),
        ("regional banks 2023", "2023-03-01", "2023-05-31"),
    ],
    "duration": [
        ("GFC 2008", "2007-07-01", "2009-06-30"),
        ("taper 2013", "2013-05-01", "2013-12-31"),
        ("hikes 2016-18", "2016-07-01", "2018-12-31"),
        ("COVID 2020", "2020-02-01", "2020-05-31"),
        ("rate shock 2022-23", "2022-01-01", "2023-10-31"),
    ],
}


def run_one(name: str, bench: pd.Series, alloc: pd.Series, cash: pd.Series,
            crises: list, n_trials: int, cost_bps=3.0) -> dict:
    bench = bench.dropna()
    alloc = alloc.reindex(bench.index).ffill().fillna(1.0)
    cash = cash.reindex(bench.index).ffill()
    bt = backtest_core(bench, alloc, cost_bps=cost_bps, cash_yield=cash)
    net, years = bt["net"], bt["years"]
    turn_per_yr = float(bt["turnover"].sum()) / years
    pct_in_mkt = 100 * float((bt["pos"] > 0.01).mean())

    strat = _stats(net, years)
    bh = _stats(bt["hold"], years)          # buy & hold (all-asset)

    base200 = _baseline_200dma(bench, cash, cost_bps)
    base_dd = _baseline_buydrawdown(bench, cash, cost_bps)
    s200 = _stats(base200, years)
    sdd = _stats(base_dd, years)
    baseline_sharpe = max(bh["sharpe"], s200["sharpe"])  # the bar to beat

    # DSR — per-bar Sharpe + moments of the strategy net return. Report the DSR at
    # n_trials = the report's honest count (8) AND at the 4 visible glide variants.
    mom = ret_moments(net)
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials)["dsr"]
    dsr4 = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], 4)["dsr"]

    # split-half: edge (strat Sharpe − B&H Sharpe) same SIGN in both halves
    idx = net.index
    mid = idx[len(idx) // 2]
    def half_edge(lo, hi):
        seg = (idx >= lo) & (idx <= hi)
        rs, rb = net[seg], bt["hold"][seg]
        return v_sharpe(rs.to_numpy(), ANN) - v_sharpe(rb.to_numpy(), ANN), \
               v_sharpe(rs.to_numpy(), ANN), v_sharpe(rb.to_numpy(), ANN)
    e1 = half_edge(idx[0], mid)
    e2 = half_edge(mid, idx[-1])
    split_same_sign = (e1[0] > 0) and (e2[0] > 0)

    # leave-one-crisis-out: drop each crisis window, edge vs B&H stays positive
    loco = []
    for cname, lo, hi in crises:
        m = ~((idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi)))
        rs, rb = net[m], bt["hold"][m]
        edge = v_sharpe(rs.to_numpy(), ANN) - v_sharpe(rb.to_numpy(), ANN)
        loco.append((cname, round(edge, 3)))
    loco_holds = all(e > 0 for _, e in loco)

    # dd-reduction bootstrap CI (pp, B&H maxdd − strat maxdd over resamples)
    rng = np.random.default_rng(7)
    rsn = net.dropna().to_numpy(); rbn = bt["hold"].reindex(net.dropna().index).to_numpy()
    nrows = len(rsn); block = 21; nb = int(np.ceil(nrows / block)); B = 5000
    grid = np.arange(block); dd_red = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, nrows, nb)
        ii = (starts[:, None] + grid[None, :]).ravel()[:nrows] % nrows
        dd_red[k] = (v_maxdd(rbn[ii]) - v_maxdd(rsn[ii])) * -100.0  # pp shallower (B&H more negative)
    dd_ci = [round(float(np.percentile(dd_red, p)), 1) for p in (2.5, 50, 97.5)]
    dd_excludes0 = dd_ci[0] > 0

    return {
        "name": name, "years": round(years, 1), "n": len(net),
        "strat": strat, "bh": bh, "base200": s200, "basedd": sdd,
        "baseline_sharpe": baseline_sharpe, "turn": round(turn_per_yr, 2),
        "pct_in_mkt": round(pct_in_mkt, 1), "dsr": dsr, "dsr4": dsr4, "n_trials": n_trials,
        "split": {"pre": round(e1[0], 3), "pre_s": round(e1[1], 2), "pre_bh": round(e1[2], 2),
                  "post": round(e2[0], 3), "post_s": round(e2[1], 2), "post_bh": round(e2[2], 2),
                  "same_sign": split_same_sign},
        "loco": loco, "loco_holds": loco_holds,
        "dd_ci": dd_ci, "dd_excludes0": dd_excludes0,
        "n_crises": len(crises),
    }


def gate_table(r: dict) -> dict:
    g = {}
    # maxdd values are negative; strat is shallower => strat_dd - bh_dd > 10pp
    g["a_maxdd_10pp"] = (r["strat"]["maxdd"] - r["bh"]["maxdd"]) > 10
    g["b_beat_baseline_sharpe"] = r["strat"]["sharpe"] > r["baseline_sharpe"]
    g["c_dd_ci_excl0"] = r["dd_excludes0"]
    g["d_loco"] = r["loco_holds"]
    g["e_turn_lt4"] = r["turn"] < 4.0
    g["f_split_same_sign"] = r["split"]["same_sign"]
    g["g_dsr_090"] = r["dsr"] >= 0.90
    g["g_dsr_095"] = r["dsr"] >= 0.95
    return g


def fmt(r: dict, g: dict) -> str:
    s, bh, b2, bd = r["strat"], r["bh"], r["base200"], r["basedd"]
    L = []
    L.append(f"=== {r['name']}  ({r['years']}yr, n={r['n']}, {r['n_crises']} crisis clusters) ===")
    L.append(f"  STRAT   CAGR {s['cagr']:.2f}  Sharpe {s['sharpe']:.3f}  MaxDD {s['maxdd']:.1f}  "
             f"turn/yr {r['turn']}  %inMkt {r['pct_in_mkt']}")
    L.append(f"  B&H     CAGR {bh['cagr']:.2f}  Sharpe {bh['sharpe']:.3f}  MaxDD {bh['maxdd']:.1f}")
    L.append(f"  200dma  CAGR {b2['cagr']:.2f}  Sharpe {b2['sharpe']:.3f}  MaxDD {b2['maxdd']:.1f}")
    L.append(f"  buyDD   CAGR {bd['cagr']:.2f}  Sharpe {bd['sharpe']:.3f}  MaxDD {bd['maxdd']:.1f}")
    L.append(f"  baseline-Sharpe-to-beat = {r['baseline_sharpe']:.3f}")
    L.append(f"  DSR {r['dsr']} (n_trials={r['n_trials']})  -> {dsr_verdict(r['dsr'])}"
             f"   [n_trials=4: DSR {r['dsr4']}]")
    sp = r["split"]
    L.append(f"  split-half edge vs B&H: pre {sp['pre']} (S {sp['pre_s']} / BH {sp['pre_bh']}), "
             f"post {sp['post']} (S {sp['post_s']} / BH {sp['post_bh']})  same-sign={sp['same_sign']}")
    L.append("  leave-one-crisis-out edge vs B&H: " + ", ".join(f"{c} {e:+.3f}" for c, e in r["loco"]))
    L.append(f"  dd-reduction CI (pp shallower) [2.5/50/97.5] = {r['dd_ci']}  excludes0={r['dd_excludes0']}")
    L.append("  GATES:")
    L.append(f"    (a) MaxDD >10pp shallower vs B&H ...... {'PASS' if g['a_maxdd_10pp'] else 'FAIL'}")
    L.append(f"    (b) beat baseline (200dma/B&H) Sharpe . {'PASS' if g['b_beat_baseline_sharpe'] else 'FAIL'}")
    L.append(f"    (c) dd-reduction CI excludes 0 ........ {'PASS' if g['c_dd_ci_excl0'] else 'FAIL'}")
    L.append(f"    (d) survives leave-one-crisis-out ..... {'PASS' if g['d_loco'] else 'FAIL'}")
    L.append(f"    (e) turnover < 4/yr ................... {'PASS' if g['e_turn_lt4'] else 'FAIL'}")
    L.append(f"    (f) both split-halves beat B&H ........ {'PASS' if g['f_split_same_sign'] else 'FAIL'}")
    L.append(f"    (g) DSR >= 0.90 (scored bar) .......... {'PASS' if g['g_dsr_090'] else 'FAIL'}"
             f"   [>=0.95 survives: {'YES' if g['g_dsr_095'] else 'NO'}]")
    return "\n".join(L)


def main():
    ctx = S._ctx()

    # ---- Credit Carry: DEEP history = full HYG adjusted close (2007->) ----
    hyg = tr._adj_close("HYG").dropna()
    cc_cash = tr.treasury_cash_yield()
    cc_alloc = S._credit_alloc(ctx, hyg)
    cc = run_one("Credit Carry (HYG 2007-> deep)", hyg, cc_alloc, cc_cash,
                 CRISES["credit"], n_trials=8)
    cc_g = gate_table(cc)

    # ---- Duration Timing: full TLT (2002->) ----
    tlt = tr.long_treasury_tr().dropna()
    du_cash = ea.bill_yield()
    du_alloc = S._duration_alloc(ctx, tlt)
    du = run_one("Duration Timing (TLT 2002-> deep)", tlt, du_alloc, du_cash,
                 CRISES["duration"], n_trials=8)
    du_g = gate_table(du)

    out = [fmt(cc, cc_g), "", fmt(du, du_g)]
    print("\n".join(out))
    return cc, cc_g, du, du_g


if __name__ == "__main__":
    main()
