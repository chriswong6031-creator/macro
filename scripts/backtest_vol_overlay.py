"""scripts/backtest_vol_overlay.py — does the engine/vol_regime SIZING OVERLAY actually help?

The vol-regime overlay (engine/vol_regime.sizing_overlay) is WIRED into basket + ladder + bot
gross sizing. It is SUBTRACT-ONLY (gross_scalar ∈ [floor, 1.0], never > 1.0) — it can only give
up upside to cut downside — so it must be judged on DRAWDOWN / tail / risk-adjusted metrics, NOT
on CAGR. This script measures it honestly with a NESTED ABLATION that isolates each lever:

  L0  unscaled book              gross 1.0 every day (baseline)
  L1  + mechanical vol-target    min(vol_target_scalar, 1.0)            — plain Moreira-Muir leg
  L2  + regime caution           mech × regime_caution  (gate CLOSED)  — THE LIVE overlay today
  L3  + scored deepener          mech × regime_caution × scored_cut    — gate OPEN (not live)

So L1−L0 = the value of plain vol-targeting; **L2−L1 = the marginal value of the REGIME caution
beyond vol-targeting** (the real question); L3−L2 = the gated scored leg (a separate decision).
The overlay scalar at t uses only data ≤ t (build_frame is causal) and is applied NEXT bar
(backtest_core shifts alloc internally). The de-risked sleeve earns the T-bill (cash_yield) so the
WITH-vs-WITHOUT return comparison is fair.

Books tested: SPY (1990+, the long, clean, crisis-spanning power test) and a basket-of-baskets
PIT book (production-relevant but membership is hindsight-curated/survivorship-biased + only to
2014 — framed as a RELATIVE sizing test, never an OOS basket-selection backtest).

The headline test is the PAIRED block-bootstrap CI of the difference (resampling both legs on the
same blocks), plus a paired drawdown-reduction CI, leave-one-crisis-out, split-half, a 200d-trend
brake comparator, turnover/cost break-even, and a ledger-deflated Sharpe. PASS (tail-framed): the
LIVE rung's dd-reduction CI lower-bound > 0 AND Sharpe not degraded AND beats the brake AND robust.
Writes reports/vol-regime-overlay-backtest.md + data/vol_regime/basket_overlay_gate.json.

Run: .venv/bin/python -m scripts.backtest_vol_overlay
"""
from __future__ import annotations

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from engine import validation as V
from engine import vol_regime
from engine.trial_ledger import TrialLedger
from lib import config, store
from scripts.calibrate_baskets import (SZ_CRISES, _ann_sharpe, _daily_bill,
                                       _dd_reduction_ci, _maxdd_ret)

log = logging.getLogger(__name__)
FAMILY = "vol_overlay_book"
COSTS = (2, 5, 10, 20)
SPLIT = pd.Timestamp("2013-01-01")


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def _series(group, name, col="close"):
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    s = df[col] if col in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index().astype(float)


def _nn(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else x


def overlay_scalars() -> pd.DataFrame:
    """Causal daily gross-scalar series for each ablation rung, replayed from the SAME
    build_frame the live engine uses. Columns: mech (L1), L2 (gate-closed=live), L3 (gate-open)."""
    vix = _series("yahoo", "_VIX")
    if vix is None:
        raise SystemExit("no VIX series")
    vvix = _series("cboe", "vvix", col="vvix")
    if vvix is None:
        vvix = _series("yahoo", "_VVIX")
    frame = vol_regime.build_frame(
        vix, _series("yahoo", "_VIX3M"), _series("yahoo", "_VIX9D"),
        _series("yahoo", "_MOVE"), _series("cboe", "skew", col="skew"),
        _series("yahoo", "SPY"), cfg=None, vvix=vvix)
    cf = vol_regime.overlay_config()
    DEF = vol_regime.DEFAULTS
    out = {}
    for d, row in frame.iterrows():
        ts = _nn(row.get("ts_slope")); rs = _nn(row.get("risk_score"))
        frag = _nn(row.get("fragility_confluence")); vt = _nn(row.get("vol_target_scalar"))
        regime = vol_regime._regime_label(ts, rs, frag, DEF)
        base = {"available": True, "regime": regime, "vol_target_scalar": vt}
        oc = vol_regime.sizing_overlay({**base, "scored_active": False, "scored_score": None}, cf)
        oo = vol_regime.sizing_overlay({**base, "scored_active": True, "scored_score": rs}, cf)
        out[d] = (oc["mech_scalar"], oc["gross_scalar"], oo["gross_scalar"])
    df = pd.DataFrame.from_dict(out, orient="index", columns=["mech", "L2", "L3"])
    return df.sort_index()


def basket_book() -> pd.Series | None:
    """Basket-of-baskets PIT equal-weight book level (perf-faithful, survivorship-caveated)."""
    try:
        from engine import baskets, basket_index
        mem = baskets._membership()
        if not mem or not mem.get("baskets"):
            return None
        rets = {}
        for bid, b in (mem["baskets"] or {}).items():
            members = b.get("members") or []
            if len(members) < 3:
                continue
            idx = basket_index.deep_calendar(members)
            cand, _ = basket_index.consolidated_candle(members, idx, "equal", pit=True)
            if cand is not None and "close" in cand:
                rets[bid] = cand["close"].pct_change()
        if not rets:
            return None
        book_ret = pd.concat(rets, axis=1).mean(axis=1)
        return (1 + book_ret.fillna(0)).cumprod()
    except Exception as e:  # noqa: BLE001
        log.warning("basket_book failed: %s", e)
        return None


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(net: pd.Series, alloc: pd.Series | None) -> dict:
    r = net.dropna().to_numpy(float)
    n = len(r)
    if n < 60:
        return {}
    ann_ret = float(np.prod(1 + r) ** (252 / n) - 1)
    ann_vol = float(np.std(r) * np.sqrt(252))
    downside = r[r < 0]
    sortino = float(np.mean(r) / (np.std(downside) or np.nan) * np.sqrt(252)) if len(downside) else None
    cvar = float(np.mean(np.sort(r)[: max(1, int(0.05 * n))]) * 100)
    turn = float(alloc.diff().abs().sum()) if alloc is not None else None
    return {"ann_ret_pct": round(ann_ret * 100, 2), "ann_vol_pct": round(ann_vol * 100, 2),
            "sharpe": round(_ann_sharpe(net), 2), "sortino": round(sortino, 2) if sortino else None,
            "calmar": round(V._calmar(r, 252), 2), "maxdd_pct": round(_maxdd_ret(net) * 100, 1),
            "cvar5_pct": round(cvar, 2), "avg_gross": round(float(alloc.mean()), 3) if alloc is not None else 1.0,
            "turnover": round(turn, 1) if turn is not None else None}


def _bt(book_lvl, alloc, bill, cost_bps):
    return V.backtest_core(book_lvl, alloc, cost_bps=cost_bps, cash_yield=bill)


# --------------------------------------------------------------------------- #
# evaluate one book across the ablation ladder
# --------------------------------------------------------------------------- #
def eval_book(name: str, book_lvl: pd.Series, scal: pd.DataFrame, *, do_crises: bool,
              led: TrialLedger) -> dict:
    book_lvl = book_lvl.dropna()
    bill = _daily_bill(book_lvl.index)
    # align scalars to the book calendar (causal: ffill prior reading; 1.0 before any regime data)
    mech = scal["mech"].reindex(book_lvl.index).ffill().fillna(1.0).clip(upper=1.0)
    L2 = scal["L2"].reindex(book_lvl.index).ffill().fillna(1.0).clip(upper=1.0)
    L3 = scal["L3"].reindex(book_lvl.index).ffill().fillna(1.0).clip(upper=1.0)
    one = pd.Series(1.0, index=book_lvl.index)
    legs = {"L0_unscaled": one, "L1_voltarget": mech, "L2_regime_live": L2, "L3_scored_open": L3}

    panel, nets = {}, {}
    for k, a in legs.items():
        bt = _bt(book_lvl, a, bill, cost_bps=5)
        nets[k] = bt["net"]
        panel[k] = _metrics(bt["net"], a)

    # paired difference CIs (resample both legs on the same blocks)
    def pair(a, b):
        return {"dd_reduction": _dd_reduction_ci(nets[a], nets[b]),
                "delta": V.paired_delta_ci(nets[a], nets[b])}
    diffs = {"L1_vs_L0": pair("L1_voltarget", "L0_unscaled"),
             "L2_vs_L1": pair("L2_regime_live", "L1_voltarget"),  # the real question
             "L2_vs_L0": pair("L2_regime_live", "L0_unscaled"),
             "L3_vs_L2": pair("L3_scored_open", "L2_regime_live")}

    # cost break-even for the LIVE rung (L2 vs L0): highest cost where L2's dd-reduction stays favorable
    breakeven = None
    for c in COSTS:
        l2c = _bt(book_lvl, L2, bill, c)["net"]; l0c = _bt(book_lvl, one, bill, c)["net"]
        if _dd_reduction_ci(l2c, l0c).get("favorable"):
            breakeven = c
    # 200d-trend brake comparator at L2's average gross (clone _book_brake idea on the book level)
    sma = book_lvl.rolling(200, min_periods=120).mean()
    brake_alloc = (book_lvl > sma).astype(float)
    brake_alloc = (brake_alloc * (float(L2.mean()) / (brake_alloc.mean() or 1.0))).clip(0, 1.0)
    brake_net = _bt(book_lvl, brake_alloc, bill, 5)["net"]
    beats_brake = bool(_ann_sharpe(nets["L2_regime_live"]) >= _ann_sharpe(brake_net))

    # split-half + leave-one-crisis-out on the LIVE rung's dd reduction (L2 vs L0)
    def dd_red(mask):
        bl = book_lvl[mask]
        if len(bl) < 400:
            return None
        bb = _daily_bill(bl.index)
        a = _bt(bl, L2.reindex(bl.index).ffill().fillna(1.0), bb, 5)["net"]
        b = _bt(bl, one.reindex(bl.index), bb, 5)["net"]
        return round((_maxdd_ret(a) - _maxdd_ret(b)) * 100, 1)
    halves = {h: dd_red(m) for h, m in
              {"pre2013": book_lvl.index < SPLIT, "post2013": book_lvl.index >= SPLIT}.items()}
    halves = {k: v for k, v in halves.items() if v is not None}
    split_robust = len(halves) == 2 and all(v > 0 for v in halves.values())
    loo = {}
    if do_crises:
        for cn, (s0, s1) in SZ_CRISES.items():
            keep = ~((book_lvl.index >= pd.Timestamp(s0)) & (book_lvl.index <= pd.Timestamp(s1)))
            v2 = dd_red(keep)
            if v2 is not None:
                loo[cn] = v2
    loo_robust = bool(loo) and all(v > 0 for v in loo.values())

    # DSR on the LIVE rung, deflated by the ledger (legs × costs)
    mom = V.ret_moments(nets["L2_regime_live"])
    dsr = V.deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=led, family=FAMILY,
                            trading_year=252) if mom else None

    l2 = diffs["L2_vs_L0"]; l2v1 = diffs["L2_vs_L1"]
    dd_lo = (l2["dd_reduction"].get("dd_reduction_pp_ci") or [None])[0]
    sharpe_ok = panel["L2_regime_live"]["sharpe"] >= panel["L0_unscaled"]["sharpe"] - 0.05
    return {
        "book": name, "window": f"{book_lvl.index[0].date()}..{book_lvl.index[-1].date()}",
        "n_days": len(book_lvl), "panel": panel, "diffs": diffs,
        "breakeven_cost_bps": breakeven, "beats_brake": beats_brake,
        "split_robust": split_robust, "halves": halves, "loo": loo, "loo_robust": loo_robust,
        "dsr": dsr,
        "verdict": {
            "live_overlay_helps": bool(l2["dd_reduction"].get("favorable") and sharpe_ok and beats_brake
                                       and (loo_robust if do_crises else split_robust)),
            "live_dd_reduction_pp_lo": dd_lo,
            "regime_marginal_over_voltarget": bool(l2v1["dd_reduction"].get("favorable")),
            "regime_delta_calmar_ci": l2v1["delta"].get("delta_calmar_ci"),
            "scored_marginal": bool(diffs["L3_vs_L2"]["dd_reduction"].get("favorable")),
        },
    }


# --------------------------------------------------------------------------- #
# orchestrate
# --------------------------------------------------------------------------- #
def run() -> dict:
    scal = overlay_scalars()
    led = TrialLedger()
    led.log_grid([{"leg": lg, "cost_bps": c} for lg in ("L1", "L2", "L3") for c in COSTS],
                 family=FAMILY, info_cutoff=str(date.today()), source="backtest_vol_overlay")
    led.log_declared_budget(20, family=FAMILY,
                            reason="overlay-eval variants: book choice (SPY/basket) + brake comparator + gate on/off")

    spy = _series("yahoo", "SPY")
    results = {}
    results["SPY"] = eval_book("SPY", spy, scal, do_crises=True, led=led)
    bk = basket_book()
    if bk is not None and len(bk) > 600:
        results["baskets"] = eval_book("baskets", bk, scal, do_crises=False, led=led)

    primary = results["SPY"]
    gate = {
        "asof": str(date.today()), "family": FAMILY,
        "live_overlay_helps": primary["verdict"]["live_overlay_helps"],
        "live_dd_reduction_pp": primary["verdict"]["live_dd_reduction_pp_lo"],
        "dd_reduction_pp_ci": (primary["diffs"]["L2_vs_L0"]["dd_reduction"] or {}).get("dd_reduction_pp_ci"),
        "regime_marginal_over_voltarget": primary["verdict"]["regime_marginal_over_voltarget"],
        "scored_marginal": primary["verdict"]["scored_marginal"],
        "beats_brake": primary["beats_brake"], "breakeven_cost_bps": primary["breakeven_cost_bps"],
        "loo_robust": primary["loo_robust"], "dsr": (primary["dsr"] or {}).get("dsr"),
        "window": primary["window"], "books": list(results),
        "note": ("Subtract-only vol-regime gross-sizing overlay (engine/vol_regime). Judged on "
                 "drawdown/tail, not CAGR. live=L2 (gate-closed: mech vol-target × regime caution). "
                 "surface the live chip ONLY if live_overlay_helps."),
    }
    return {"results": results, "gate": gate}


def _render(out: dict) -> str:
    g = out["gate"]; L = [
        "# Vol-regime sizing-overlay backtest\n",
        f"_generated {date.today()} · subtract-only gross overlay (engine/vol_regime), judged on "
        "drawdown/tail not CAGR · L0 unscaled / L1 +vol-target / L2 +regime-caution (LIVE) / L3 +scored (gate-open)_\n"]
    for name, r in out["results"].items():
        L.append(f"\n## Book: {name} ({r['window']}, {r['n_days']} days)\n")
        L.append("| rung | ann% | vol% | Sharpe | Sortino | Calmar | maxDD% | CVaR5% | avgGross | turnover |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for k, m in r["panel"].items():
            L.append(f"| {k} | {m.get('ann_ret_pct')} | {m.get('ann_vol_pct')} | {m.get('sharpe')} | "
                     f"{m.get('sortino')} | {m.get('calmar')} | {m.get('maxdd_pct')} | {m.get('cvar5_pct')} | "
                     f"{m.get('avg_gross')} | {m.get('turnover')} |")
        d = r["diffs"]
        L.append("\n**Paired difference CIs** (resampled on the same blocks; 'helps' iff CI excludes 0):")
        for cmp_, dd in d.items():
            ddci = (dd["dd_reduction"] or {}).get("dd_reduction_pp_ci"); fav = (dd["dd_reduction"] or {}).get("favorable")
            L.append(f"- **{cmp_}**: dd-reduction {ddci} pp (favorable={fav}); "
                     f"Δsharpe {dd['delta'].get('delta_sharpe_ci')}; Δcalmar {dd['delta'].get('delta_calmar_ci')}")
        L.append(f"\n- beats 200d-brake: {r['beats_brake']} · break-even cost: {r['breakeven_cost_bps']}bps · "
                 f"split-half robust: {r['split_robust']} {r['halves']}")
        if r["loo"]:
            L.append(f"- leave-one-crisis-out dd-reduction(pp): {r['loo']} (robust={r['loo_robust']})")
        if r["dsr"]:
            L.append(f"- DSR (ledger-deflated): {r['dsr'].get('dsr')} ({V.dsr_verdict(r['dsr'].get('dsr', 0))})")
        v = r["verdict"]
        L.append(f"\n**Verdict ({name}):** live overlay (L2) helps = **{v['live_overlay_helps']}** "
                 f"(dd-reduction lower-bound {v['live_dd_reduction_pp_lo']}pp). "
                 f"Regime caution adds value beyond plain vol-targeting (L2−L1) = **{v['regime_marginal_over_voltarget']}**. "
                 f"Scored leg marginal (L3−L2) = {v['scored_marginal']}.")
    L.append("\n## Gate\n")
    L.append(f"- **live_overlay_helps = {g['live_overlay_helps']}** → "
             + ("surface the live basket-sizing chip." if g["live_overlay_helps"]
                else "keep the chip as honest-caution display or hold; do not claim improvement."))
    L.append(f"- regime caution beyond vol-targeting: {g['regime_marginal_over_voltarget']}; "
             f"scored leg (gate-open): {g['scored_marginal']} → "
             + ("consider opening the gate." if g["scored_marginal"] else "keep gate closed."))
    L.append("\n_Honest framing: the overlay is subtract-only (gross ≤ 1.0) — it trades upside for "
             "smaller drawdowns; a flat/slightly-lower CAGR with materially lower maxDD is a PASS. "
             "The basket book is survivorship-caveated (relative sizing test, not OOS selection)._\n")
    return "\n".join(L)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = run()
    rep = _render(out)
    (config.ROOT / "reports" / "vol-regime-overlay-backtest.md").write_text(rep)
    gp = config.data_dir() / "vol_regime" / "basket_overlay_gate.json"
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps(out["gate"], indent=2))
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
