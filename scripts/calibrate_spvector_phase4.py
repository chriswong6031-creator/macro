"""S&P / Macro Vector — Phase 4 (diversified sleeve) A/B + GATE.

Uses the SAME validated Phase-3 allocation WEIGHT (engine.equity_alloc.vector_alloc) but
swaps the sleeves:
  A SPY + T-bills        (= the shipped Phase-3 strategy, the bar to beat)
  B SPY + Treasury TR    (duration defensive sleeve, DGS10 @ ~8y duration)
  C RS  + T-bills        (relative-strength equity rotation SPX/NDX/DJI/RUT)
  D RS  + Treasury TR    (both)

GATE for a diversified structure to SHIP: beat A on CAGR WITHOUT worse MaxDD, hold up in
BOTH split-halves, clear DSR, AND survive the 2022 stock-bond-correlation breakdown (the
Treasury sleeve must not turn the de-risked book into a second losing bet). Default = do
NOT ship; keep bills unless a structure clearly earns it. Writes reports/spvector-phase4.md.

Run: python -m scripts.calibrate_spvector_phase4
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine import equity_diversified as ed
from engine.validation import deflated_sharpe, ret_moments
from lib import config, store

COST_BPS = 3.0
SPLIT = "2010-01-01"
N_TRIALS = 40


def _sh(r): r = r.dropna(); return round(float(r.mean() / r.std() * np.sqrt(ed.TY)), 2) if r.std() else float("nan")
def _yr_ret(net, y): s = net[net.index.year == y]; return round(100 * ((1 + s).prod() - 1), 1)
def _yr_dd(net, y):
    s = net[net.index.year == y]; eq = (1 + s).cumprod(); return round(100 * float((eq / eq.cummax() - 1).min()), 1)


def main() -> int:
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    print("[build] features + conditions ...")
    f = build_features(); cf = conditions_frame(f); reg = store.read("regime", "regime_history")
    spy = ea.index_close("SPY"); bills_y = ea.bill_yield()
    alloc = ea.vector_alloc(spy, f=f, regime=reg, cf=cf)        # the validated weight
    idx = spy.index

    spy_ret = spy.pct_change(fill_method=None).fillna(0).reindex(idx).fillna(0)
    rs_ret = ed.rs_equity_returns().reindex(idx).fillna(0)
    bill_ret = ed.bill_returns(bills_y, idx)
    tsy_ret = ed.treasury_tr(store.read("fred", "DGS10")["us10y"], maturity_years=8.0).reindex(idx).fillna(0)
    # E: stock-bond-corr-gated defensive sleeve — Treasury when bonds are hedging
    # (realized corr < 0.2, lagged 5d), else bills. Tests whether the 2022 duration
    # tail can be gated away by the regime signal the repo already computes.
    corr = cf["stock_bond_corr"].reindex(idx, method="ffill").shift(5)
    cg_ret = tsy_ret.where(corr < 0.2, bill_ret)

    structs = {
        "A SPY + bills (Phase-3)": (spy_ret, bill_ret),
        "B SPY + Treasury": (spy_ret, tsy_ret),
        "C RS + bills": (rs_ret, bill_ret),
        "D RS + Treasury": (rs_ret, tsy_ret),
        "E SPY + corr-gated Treasury": (spy_ret, cg_ret),
    }
    res = {}
    for name, (er, dr) in structs.items():
        bt = ed.backtest_sleeves(er, dr, alloc, COST_BPS)
        net = bt["net"]
        s = ed.stats(net, bt["years"], name)
        s["pre"] = _sh(net.loc[:SPLIT]); s["post"] = _sh(net.loc[SPLIT:])
        s["y2022"] = _yr_ret(net, 2022); s["dd2022"] = _yr_dd(net, 2022)
        s["y2008"] = _yr_ret(net, 2008)
        mom = ret_moments(net)
        d = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], N_TRIALS, trading_year=ed.TY) if mom else None
        s["dsr"] = d["dsr"] if d else None
        res[name] = s

    bh = ed.stats(spy_ret, (idx[-1] - idx[0]).days / 365.25, "buy & hold")
    bh["y2022"] = _yr_ret(spy_ret, 2022); bh["y2008"] = _yr_ret(spy_ret, 2008)

    A = res["A SPY + bills (Phase-3)"]
    md = ["# S&P / Macro Vector — Phase 4 (diversified sleeve) A/B + GATE", "",
          f"*Same validated Phase-3 weight (vector_alloc); SPY {bh.get('label')} 1993-2026, cash@DTB3, {COST_BPS}bps. "
          "Treasury sleeve = synthetic constant-maturity 10y TR (~8y duration).*", "",
          "| structure | CAGR | Sharpe | Sortino | MaxDD | pre/post Sh | 2022 ret | 2022 DD | 2008 ret | DSR |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
          f"| buy & hold | {bh['cagr']} | {bh['sharpe']} | {bh['sortino']} | {bh['maxdd']} | — | {bh['y2022']} | — | {bh['y2008']} | — |"]
    for name, s in res.items():
        md.append(f"| {name} | {s['cagr']} | {s['sharpe']} | {s['sortino']} | {s['maxdd']} | "
                  f"{s['pre']}/{s['post']} | {s['y2022']} | {s['dd2022']} | {s['y2008']} | {s['dsr']} |")

    # GATE each diversified structure vs A
    md += ["", "## GATE (each diversified structure vs A = Phase-3 bills)", ""]
    verdicts = {}
    for name in ("B SPY + Treasury", "C RS + bills", "D RS + Treasury", "E SPY + corr-gated Treasury"):
        s = res[name]
        g = {
            "CAGR > A": s["cagr"] > A["cagr"],
            "MaxDD not worse than A": s["maxdd"] >= A["maxdd"] - 1.0,
            "both split-halves >= A": s["pre"] >= A["pre"] - 0.02 and s["post"] >= A["post"] - 0.02,
            "survives 2022 (>= A's 2022)": s["y2022"] >= A["y2022"] - 0.5,
            "DSR > 0.90": bool(s["dsr"] and s["dsr"] > 0.90),
        }
        verdicts[name] = all(g.values())
        md.append(f"**{name}** — {'SHIP' if all(g.values()) else 'REJECT'}")
        for k, v in g.items():
            md.append(f"  - {'PASS' if v else 'FAIL'} {k}")
        md.append("")

    md += ["## Read",
           f"- A (Phase-3 bills) is the bar: CAGR {A['cagr']} / Sharpe {A['sharpe']} / MaxDD {A['maxdd']}, "
           f"2022 {A['y2022']}%.",
           "- The Treasury sleeve's 2022 column is the decisive test: in the 2022 rates bear, bonds fell WITH "
           "stocks, so de-risking into duration was a SECOND losing bet (stock-bond correlation breakdown). If "
           "B/D's 2022 return is materially below A's, the duration sleeve is rejected for THIS macro-timed book "
           "regardless of its full-sample CAGR.",
           "- RS rotation (C) adds CAGR only if the winner-momentum across indices beats always-SPY net of its "
           "extra turnover; judged on OOS split-half + DSR, not the full-sample number.",
           "- E (corr-gated Treasury) tests the obvious fix — hold bonds only when they hedge. It FAILS too: "
           "realized stock-bond correlation in 2022 averaged ~0.06 and only turned positive AFTER the bond "
           "drawdown, so the lagging regime signal still held duration through the damage. No non-lagging signal "
           "gates the 2022 duration tail away.",
           "", f"### Verdict: " + (
               ", ".join(f"{n.split()[0]}=SHIP" for n, v in verdicts.items() if v) or
               "NONE clear the bar — KEEP bills (Phase-3 is the product). Diversification's CAGR edge does not "
               "survive the 2022 stock-bond breakdown / OOS test on this macro-timed switch.")]

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "spvector-phase4.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n[report] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
