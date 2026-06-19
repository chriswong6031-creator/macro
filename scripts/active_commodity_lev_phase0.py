"""Phase-0 honesty harness for the LEVERED active-commodity allocators (silver & copper).

TRACK-A VERIFY + the one missing gate. The active models on masterminds/active-commodity
cards (engine.active_commodity) already ship a full-sample scorecard + split-half OOS panel,
and silver/copper beat B&H CAGR in BOTH halves. The OPEN gate the spec calls out is the
DEFLATED SHARPE on the LEVERED net-return series — the sister LONG/FLAT commodity allocators
FAILED DSR (gold 0.58, silver 0.07, copper 0.32, oil 0.12), so we must check whether levering
the same conviction clears the multiple-testing haircut.

This is READ-ONLY research: it re-runs the live engine.active_commodity.evaluate() to confirm
the headline scorecard, then computes — on the LEVERED net series — the deflated Sharpe (with
an honestly-counted n_trials), a leave-one-crisis-out re-test, and a beats-dumb-baseline check
vs the SAME-asset 200dma long/flat timer. Prints results + writes reports/<slug>-phase0.md.
NO look-ahead is introduced: signals/vol use data through t and the position acts next bar
(engine.active_alloc.backtest_lev applies size.shift(1)); the 200dma baseline shifts too.

Run: .venv/bin/python -m scripts.active_commodity_lev_phase0
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from engine import equity_alloc as ea  # noqa: E402
from engine import active_alloc as aa  # noqa: E402
from engine import active_commodity as ac  # noqa: E402
from engine import validation as V  # noqa: E402

# --------------------------------------------------------------------------- #
# honest trial count. The active-model design grid that was searched in building
# these two models, per the structural knobs in engine.active_commodity:
#
#   target_vol        : silver 0.32, copper 0.25                 (a tuned sizing knob)
#   size cap          : silver 3.0, copper 4.0                   (a tuned leverage cap)
#   conviction cap    : silver 1.7, copper 1.8
#   leg weights/power : silver {0.55 ratio,0.30 gold,0.15 cu}, ratio_power 1.5,
#                       ratio lookback 5y, extreme {0.80,0.50}, boost 0.6
#   copper            : trend {63,126,252}, growth {china,cg126,indpro,usd126},
#                       tilt 0.6+1.2g clipped {0.6,1.8}
#
# That is a multi-dimensional hand-search. A defensible-but-CONSERVATIVE n_trials
# counts the distinct *axes* actually varied (vol-target x leverage-cap x lookback x
# leg-weighting/structure). We report a SWEEP of n_trials so the verdict does not
# hinge on one guess; the headline uses N_HEADLINE.
N_GRID = [12, 20, 30, 50, 100]
N_HEADLINE = 30          # ~ (vol-target ladder) x (cap ladder) x (lookback/structure)

CRISES = [("2008 GFC", "2008-09-01", "2009-03-31"),
          ("2011 selloff", "2011-08-01", "2011-10-31"),
          ("2013 taper/gold crash", "2013-04-01", "2013-07-31"),
          ("2015-16 China/commodity", "2015-08-01", "2016-02-29"),
          ("2018Q4", "2018-10-01", "2018-12-31"),
          ("2020 COVID", "2020-02-19", "2020-03-31"),
          ("2022 bear", "2022-01-01", "2022-10-31")]


def _yclose(tk: str) -> pd.Series:
    s = ea.index_close(tk).astype(float).dropna()
    return s[s > 0]


def _dma_baseline(close: pd.Series, bill: pd.Series, win: int = 200) -> dict:
    """The DUMB baseline: 200dma long/flat (1.0 when close>200dma, else 0), same
    next-bar lag + same cost/carry engine as the levered model (no leverage)."""
    sma = close.rolling(win).mean()
    alloc = (close > sma).astype(float)
    return aa.backtest_lev(close, alloc, bill, cost_bps=3.0, borrow_spread=ac._FIN_SPREAD)


def _bh_sharpe(close: pd.Series) -> float:
    r = close.pct_change().dropna()
    return V._sharpe(r.values, 252)


def loco(close: pd.Series, size: pd.Series, bill: pd.Series) -> list[dict]:
    """Leave-one-crisis-out: drop each crisis window from the net-return series and
    recompute the annualized Sharpe + CAGR-beat-vs-B&H on the remainder. Robust = the
    edge does not depend on any single crisis (Sharpe stays positive & beats B&H net of
    cost on every leave-out)."""
    r = aa.backtest_lev(close, size, bill, cost_bps=3.0, borrow_spread=ac._FIN_SPREAD)
    net, ret = r["net"], r["ret"]
    out = []
    for nm, a, b in CRISES:
        mask = ~((net.index >= pd.Timestamp(a)) & (net.index <= pd.Timestamp(b)))
        n2, h2 = net[mask], ret[mask]
        if len(n2) < 200:
            continue
        yrs = (n2.index[-1] - n2.index[0]).days / 365.25
        cagr = (1 + n2).cumprod().iloc[-1] ** (1 / yrs) - 1
        hcagr = (1 + h2).cumprod().iloc[-1] ** (1 / yrs) - 1
        out.append({"crisis": nm, "sharpe": round(V._sharpe(n2.values, 252), 3),
                    "cagr": round(100 * cagr, 2), "hodl_cagr": round(100 * hcagr, 2),
                    "beats": bool(cagr > hcagr)})
    return out


def dsr_for(key: str) -> dict:
    m = ac.MODELS[key]
    b = _yclose(m["ticker"])
    bill = ea.bill_yield()
    size = m["size"](b)
    r = aa.backtest_lev(b, size, bill, cost_bps=3.0, borrow_spread=ac._FIN_SPREAD)
    net = r["net"].dropna()
    mom = V.ret_moments(net)              # (sr_daily, skew, kurt, n)
    sweep = {}
    for n in N_GRID:
        d = V.deflated_sharpe(*mom, n_trials=n)
        sweep[n] = d["dsr"] if d else None
    head = V.deflated_sharpe(*mom, n_trials=N_HEADLINE)
    # leave-one-crisis-out
    lc = loco(b, size, bill)
    # dumb baseline: same-asset 200dma long/flat
    base = _dma_baseline(b, bill)
    return {"key": key, "ticker": m["ticker"], "scorecard": r, "net": net,
            "moments": mom, "dsr_head": head, "dsr_sweep": sweep,
            "loco": lc, "baseline": base, "bh_sharpe": round(_bh_sharpe(b), 3)}


def main() -> int:
    print("=" * 78)
    print("LEVERED active-commodity Phase-0 — silver & copper (gold for context)")
    print("=" * 78)
    md = ["# Levered active-commodity — Phase-0 (silver & copper)\n",
          "Re-run of `engine.active_commodity.evaluate()` (net 3 bps + 1% financing on the "
          "levered part, 2000→2026) + the MISSING gate: deflated Sharpe on the LEVERED net "
          "series, leave-one-crisis-out, and beats-dumb-baseline (same-asset 200dma).\n",
          f"Honest n_trials headline = {N_HEADLINE} (vol-target x leverage-cap x lookback x "
          "leg-structure search); reported across a sweep so the verdict is robust to the count.\n"]

    rows = {}
    for key in ["cm_silver_active", "cm_copper_active", "cm_gold_active"]:
        res = dsr_for(key)
        rows[key] = res
        sc, d, sw = res["scorecard"], res["dsr_head"], res["dsr_sweep"]
        oos = ac.evaluate(key)["oos"]
        sr_d, skew, kurt, nobs = res["moments"]
        print(f"\n### {key} ({res['ticker']})")
        print(f"  full: CAGR {sc['cagr']} vs B&H {sc['hodl_cagr']} | Sharpe {sc['sharpe']} "
              f"vs {sc['hodl_sharpe']} | MaxDD {sc['maxdd']} vs {sc['hodl_maxdd']} | "
              f"avg_lev {sc['avg_leverage']} max_lev {sc['max_leverage']}")
        print(f"  split-half robust (beats CAGR both halves): {oos.get('robust')}")
        print(f"  net-series moments: sr_daily {sr_d:.4f}  skew {skew:.2f}  kurt {kurt:.2f}  n {nobs}")
        print(f"  DSR (n={N_HEADLINE}): {d['dsr']}  -> {V.dsr_verdict(d['dsr'])}")
        print(f"    sr_annual {d['sr_annual']}  haircut sr0_annual {d['sr0_annual']}")
        print(f"  DSR sweep over n_trials: " + ", ".join(f"n{n}={v}" for n, v in sw.items()))
        bl = res["baseline"]
        beats_base = sc["sharpe"] > bl["sharpe"] and sc["cagr"] > bl["cagr"]
        print(f"  DUMB 200dma baseline: CAGR {bl['cagr']} Sharpe {bl['sharpe']} "
              f"MaxDD {bl['maxdd']} -> model beats baseline (Sharpe&CAGR): {beats_base}")
        loco_ok = all(x["sharpe"] > 0 and x["beats"] for x in res["loco"])
        print(f"  leave-one-crisis-out ({len(res['loco'])} crises) all positive&beat: {loco_ok}")
        for x in res["loco"]:
            print(f"    - drop {x['crisis']:28} Sharpe {x['sharpe']:.3f}  "
                  f"CAGR {x['cagr']} vs B&H {x['hodl_cagr']}  beats={x['beats']}")

        md.append(f"\n## {key} ({res['ticker']})\n")
        md.append(f"- full: CAGR **{sc['cagr']}** vs B&H {sc['hodl_cagr']} | Sharpe "
                  f"**{sc['sharpe']}** vs {sc['hodl_sharpe']} | MaxDD {sc['maxdd']} vs "
                  f"{sc['hodl_maxdd']} | avg_lev {sc['avg_leverage']} max_lev {sc['max_leverage']}")
        md.append(f"- split-half robust (beats CAGR both halves): **{oos.get('robust')}**")
        md.append(f"- net moments: sr_daily {sr_d:.4f}, skew {skew:.2f}, kurt {kurt:.2f}, n {nobs}")
        md.append(f"- **DSR (n={N_HEADLINE}) = {d['dsr']}** — {V.dsr_verdict(d['dsr'])} "
                  f"(sr_ann {d['sr_annual']}, haircut sr0_ann {d['sr0_annual']})")
        md.append(f"- DSR sweep: " + ", ".join(f"n{n}={v}" for n, v in sw.items()))
        md.append(f"- dumb 200dma baseline: CAGR {bl['cagr']} / Sharpe {bl['sharpe']} / "
                  f"MaxDD {bl['maxdd']} → model beats baseline: **{beats_base}**")
        md.append(f"- leave-one-crisis-out all positive & beat B&H: **{loco_ok}** "
                  f"(min Sharpe {min(x['sharpe'] for x in res['loco']):.3f})")

    rpath = config.ROOT / "reports" / "active-commodity-lev-phase0.md"
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text("\n".join(md) + "\n")
    print(f"\nwrote {rpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
