"""S&P / Macro Vector — ALFRED point-in-time validation.

The last look-ahead honesty check: rebuild the de-risk score on a genuinely
POINT-IN-TIME feature frame — the revised macro legs that HAVE ALFRED vintages
(recession_prob = RECPROUSM156N, term premium = THREEFYTP10; Sahm is already
real-time via SAHMREALTIME) are replaced with their INITIAL-RELEASE values
timed by actual publication date — and confirm the gate still holds. Isolates the
revised-vs-PIT DATA effect (same per-leg lags on both sides).

Residual (honest): NFCI and EBP have no ALFRED path (NFCI weekly-fully-revised
archive times out on output_type=4; EBP is a Fed-board series), so those legs keep
the publication-lag approximation. Run: python -m scripts.calibrate_spvector_pit
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine.validation import backtest_core, deflated_sharpe, ret_moments
from engine.trial_ledger import TrialLedger
from collectors.fred import load_vintages
from lib import config, store

COST_BPS = 3.0
CRISES = {"dotcom": ("2000-03-01", "2002-10-31"), "GFC": ("2007-10-01", "2009-06-30"),
          "COVID": ("2020-02-01", "2020-06-30"), "2022": ("2022-01-01", "2022-12-31")}


def pit_daily(v: pd.DataFrame, series: str, index: pd.Index) -> pd.Series:
    """Leak-free daily PIT path: each period's INITIAL-RELEASE value, ffilled from
    its actual publication date (realtime_start) onto the daily index."""
    sub = v[v["series"] == series].sort_values("realtime_start")
    if sub.empty:
        return pd.Series(index=index, dtype=float)
    s = sub.set_index("realtime_start")["value"]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(index, method="ffill")


def _sh(r): r = r.dropna(); return round(float(r.mean() / r.std() * np.sqrt(ea.TRADING_YEAR)), 2) if r.std() else float("nan")
def _cagr(r): eq = (1 + r.dropna()).cumprod(); y = len(r.dropna()) / ea.TRADING_YEAR; return round(100 * (eq.iloc[-1] ** (1 / y) - 1), 2)
def _mdd(r): eq = (1 + r.dropna()).cumprod(); return round(100 * float((eq / eq.cummax() - 1).min()), 1)


def _evaluate(spy, alloc, bills):
    bt = backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=bills)
    net, hold = bt["net"], bt["hold"]
    loco = {c: round(_sh(net[~((net.index >= lo) & (net.index <= hi))]) -
               _sh(hold[~((hold.index >= lo) & (hold.index <= hi))]), 2) for c, (lo, hi) in CRISES.items()}
    mom = ret_moments(net)
    if mom:
        _led = TrialLedger()      # honest-N via the ledger (P3): declared honest count
        _led.log_declared_budget(30, family="spvector_pit",
                                 reason="PIT honest count (calibrate_spvector_pit)")
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_led,
                              family="spvector_pit", trading_year=ea.TRADING_YEAR)
    else:
        dsr = None
    return {"cagr": _cagr(net), "sharpe": _sh(net), "maxdd": _mdd(net), "loco": loco,
            "dsr": dsr["dsr"] if dsr else None}


def main() -> int:
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    print("[build] features + conditions ...")
    f = build_features(); reg = store.read("regime", "regime_history")
    spy = ea.index_close("SPY"); bills = ea.bill_yield()
    v = load_vintages()
    if v is None:
        print("no vintages on disk; run collect --only fred (vintage path) first")
        return 1

    # PIT feature frame: swap the revised legs that have ALFRED vintages
    f_pit = f.copy()
    rp = pit_daily(v, "RECPROUSM156N", f.index)
    tp = pit_daily(v, "THREEFYTP10", f.index)
    swapped = []
    if rp.notna().any():
        f_pit["recession_prob"] = rp; swapped.append("recession_prob")
    if tp.notna().any() and "term_premium_10y" in f_pit:
        f_pit["term_premium_10y"] = tp
        f_pit["curve_tp_adj"] = f_pit["spread_2s10s"] + f_pit["term_premium_10y"].fillna(0)
        swapped.append("term_premium_10y/curve_tp_adj")

    cf_std = conditions_frame(f); cf_pit = conditions_frame(f_pit)
    alloc_std = ea.vector_alloc(spy, f=f, regime=reg, cf=cf_std)
    alloc_pit = ea.vector_alloc(spy, f=f_pit, regime=reg, cf=cf_pit)

    std = _evaluate(spy, alloc_std, bills)
    pit = _evaluate(spy, alloc_pit, bills)

    md = ["# S&P / Macro Vector — ALFRED point-in-time validation", "",
          f"*Swapped to INITIAL-RELEASE (publication-timed) values: {', '.join(swapped)}. Sahm already real-time. "
          "NFCI + EBP have no ALFRED path -> keep the publication-lag approximation. Same per-leg lags on both "
          "sides, so this isolates the revised-vs-PIT DATA effect.*", "",
          "| | revised+lag (shipped) | genuine PIT |", "|---|--:|--:|",
          f"| CAGR | {std['cagr']} | {pit['cagr']} |",
          f"| Sharpe | {std['sharpe']} | {pit['sharpe']} |",
          f"| MaxDD | {std['maxdd']} | {pit['maxdd']} |",
          f"| DSR | {std['dsr']} | {pit['dsr']} |", "",
          "leave-one-crisis-out (Sharpe edge vs B&H):",
          f"- revised+lag: " + ", ".join(f"{k} {v:+}" for k, v in std["loco"].items()),
          f"- genuine PIT: " + ", ".join(f"{k} {v:+}" for k, v in pit["loco"].items()), ""]
    holds = (pit["sharpe"] >= std["sharpe"] - 0.05 and pit["maxdd"] >= std["maxdd"] - 2 and
             all(x > 0 for x in pit["loco"].values()) and (pit["dsr"] or 0) > 0.90)
    md += ["## Verdict",
           ("CONFIRMED — the edge holds on genuinely point-in-time data; the publication-lag approximation was "
            "sound (Sharpe/MaxDD/leave-one-crisis-out essentially unchanged). The revised-data look-ahead was NOT "
            "driving the result." if holds else
            "REVIEW — the PIT result diverges materially from the shipped approximation; investigate."),
           "", "_Residual: NFCI + EBP still revised (no ALFRED vintages). They feed the drawdown gauge but are not "
           "the load-bearing leg; the publication-lag buffer remains for them._"]

    out = config.ROOT / config.load()["storage"]["reports_dir"] / "spvector-pit.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n[report] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
