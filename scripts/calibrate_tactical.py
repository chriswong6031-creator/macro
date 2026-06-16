"""Phase-0 calibration + GATE for the two tactical-yield strategies (Credit Carry,
Duration Timing), mirroring scripts/calibrate_spvector.py.

Each strategy is subjected to the honest gate before it earns more than its
"experimental" label — net of cost, cash-credited, on its OWN total-return benchmark:

  GATE (all must pass):
   (a) cut MaxDD materially vs buy & hold
   (b) beat the best naive baseline (buy & hold / 200dma) on Sharpe
   (c) paired block-bootstrap drawdown-REDUCTION CI excludes zero
   (d) survive leave-one-crisis-out (Sharpe edge vs B&H stays positive each crisis)
   (e) turnover tax-tolerable
   (f) hold up in BOTH split-halves
   (g) Deflated-Sharpe > 0.90 at an honest trial count

It validates the EXACT shipped allocation (engine.strategies primary = glide_path at
confirm_days=5) plus a small pre-registered variant set for the DSR haircut.

SAMPLE CAVEAT (surfaced in each report): locally the HY benchmark is HYG (2007->) and the
long-Treasury benchmark is TLT (2002->), since FRED is unreachable from the sandbox. Once
the ICE BofA total-return indices land in CI (config.yml fred.series.credit:
BAMLHYH0A0HYM2TRIV, 1986->), engine.total_return auto-upgrades and a deeper-history re-run
becomes possible. The small independent-bear count is the binding limit on confidence.

Run: python -m scripts.calibrate_tactical
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine import strategies as S
from engine.validation import backtest_core, deflated_sharpe, ret_moments
from lib import config

COST_BPS = 3.0
N_TRIALS_HONEST = 8                  # pre-registered variant configs tried (DSR haircut)
TY = ea.TRADING_YEAR

# strategy-specific independent stress windows (the bears a switch must navigate).
# Credit: default/liquidity drawdowns. Duration: RATE-SHOCK drawdowns (2008 is excluded —
# long Treasuries RALLIED in the GFC flight-to-quality, so it is not a duration bear).
CRISES = {
    "credit_carry": {
        "GFC 2008": ("2007-10-01", "2009-06-30"),
        "euro 2011": ("2011-07-01", "2011-12-31"),
        "energy/EM 2015-16": ("2015-08-01", "2016-02-29"),
        "COVID 2020": ("2020-02-01", "2020-06-30"),
        "rate/credit 2022": ("2022-01-01", "2022-12-31"),
    },
    "duration_timing": {
        "taper 2013": ("2013-05-01", "2013-12-31"),
        "hikes 2016-18": ("2016-07-01", "2018-11-30"),
        "rate shock 2020-23": ("2020-08-01", "2023-10-31"),
    },
}
HEADER = {
    "credit_carry": ("Credit Carry", "High-yield credit (TR)", "5y Treasury (DGS5)",
                     "credit-carry-phase0.md"),
    "duration_timing": ("Duration / Treasury Timing", "Long Treasuries (TR)", "T-bills (DTB3)",
                        "duration-timing-phase0.md"),
}


def _sharpe(r: pd.Series) -> float:
    r = r.dropna(); sd = r.std()
    return float(r.mean() / sd * np.sqrt(TY)) if sd else float("nan")


def _maxdd_from_ret(r: np.ndarray) -> float:
    eq = np.cumprod(1.0 + r)
    return float(np.min(eq / np.maximum.accumulate(eq) - 1.0))


def paired_dd_reduction_ci(strat: pd.Series, hold: pd.Series, block: int = 21,
                           B: int = 5000, seed: int = 7) -> dict:
    """Block-bootstrap the drawdown REDUCTION (B&H MaxDD - strat MaxDD, pp, positive =
    strat shallower) resampling the SAME blocks for both legs (pairing preserved)."""
    df = pd.concat([strat, hold], axis=1).dropna()
    a, h = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    n = len(a)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block)); grid = np.arange(block)
    red = np.empty(B)
    for k in range(B):
        st = rng.integers(0, n, nb)
        idx = (st[:, None] + grid[None, :]).ravel()[:n] % n
        red[k] = (_maxdd_from_ret(a[idx]) - _maxdd_from_ret(h[idx])) * 100.0
    return {"dd_reduction_pp_ci": [round(float(np.percentile(red, p)), 1) for p in (2.5, 50, 97.5)],
            "p_reduction_gt0": round(float(np.mean(red > 0)), 3)}


def _candidates(score: pd.Series, bench: pd.Series) -> dict[str, pd.Series]:
    """Pre-registered variant set. PRIMARY (cd5) is the SHIPPED allocation."""
    g = lambda cd, **k: ea.glide_path(score, confirm_days=cd, **k).reindex(bench.index, method="ffill").fillna(1.0)
    return {
        "glide (cd5) — shipped": g(5),
        "glide (cd3)": g(3),
        "glide (cd10)": g(10),
        "glide binary": g(5, weights=(1.0, 1.0, 0.0, 0.0)),
    }


def _evaluate(bench: pd.Series, alloc: pd.Series, cash: pd.Series, split: str,
              crises: dict, base_sharpe: float) -> dict:
    s = ea.summarize(bench, alloc, "x", cash_yield=cash, cost_bps=COST_BPS)
    bt = backtest_core(bench, alloc, cost_bps=COST_BPS, cash_yield=cash)
    net, hold = bt["net"], bt["hold"]
    halves = {"pre": round(_sharpe(net.loc[:split]), 2), "post": round(_sharpe(net.loc[split:]), 2),
              "bh_pre": round(_sharpe(hold.loc[:split]), 2), "bh_post": round(_sharpe(hold.loc[split:]), 2)}
    loco = {}
    for cname, (lo, hi) in crises.items():
        mask = ~((net.index >= lo) & (net.index <= hi))
        loco[cname] = round(_sharpe(net[mask]) - _sharpe(hold[mask]), 2)
    ddci = paired_dd_reduction_ci(net, hold)
    mom = ret_moments(net)
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], N_TRIALS_HONEST, trading_year=TY) if mom else None
    return {"score": s, "halves": halves, "loco": loco, "ddci": ddci, "dsr": dsr,
            "beats_baseline": s["sharpe"] >= base_sharpe}


def _calibrate(spec: S.StrategySpec, ctx: dict) -> tuple[str, list[str]]:
    name, bench_lab, cash_lab, out_name = HEADER[spec.key]
    crises = CRISES[spec.key]
    bench = spec.benchmark(ctx)
    cash = spec.cash_yield(ctx)
    score = spec.score(ctx, bench)["score"]
    split = bench.index[len(bench) // 2].strftime("%Y-%m-%d")   # midpoint split

    bh = ea.summarize(bench, ea.buy_hold(bench), "B&H", cash_yield=cash, cost_bps=COST_BPS)
    sma = ea.summarize(bench, ea.sma_switch(bench, 200), "200dma", cash_yield=cash, cost_bps=COST_BPS)
    base_sharpe = max(bh["sharpe"], sma["sharpe"])

    cands = _candidates(score, bench)
    results = {nm: _evaluate(bench, al, cash, split, crises, base_sharpe) for nm, al in cands.items()}

    md = [f"# {name} — Phase-0 calibration & GATE", "",
          f"*{bench_lab} {bh['years']}yr (to {bench.index[-1].date()}), cost {COST_BPS}bps one-way, "
          f"de-risked sleeve at {cash_lab}. Split-half boundary {split}. Baseline Sharpe to beat = "
          f"{base_sharpe} (max of buy&hold {bh['sharpe']} / 200dma {sma['sharpe']}).*", "",
          "> HONEST FRAME: this is a DRAWDOWN / risk-adjusted-return engine, NOT a CAGR-beater — sitting in "
          "the cash leg through stress gives up some carry, so CAGR ~matches or trails buy & hold. The thesis "
          "is timing the LEFT TAIL that destroys the yield (the recession / credit / rate shock), not the yield.",
          "",
          f"> SAMPLE CAVEAT: the benchmark is the dividend/coupon-adjusted ETF close ({bench_lab}); the small "
          "number of INDEPENDENT bears in this window — not the day count — bounds confidence. The authoritative "
          "ICE BofA total-return index (deeper history) lands via CI (config.yml fred.series.credit) and enables "
          "a deeper-history re-run; until then treat a PASS as provisional.", "",
          "## Baselines", "",
          "| strategy | CAGR | Sharpe | MaxDD | turn/yr |", "|---|--:|--:|--:|--:|",
          f"| buy & hold | {bh['cagr']} | {bh['sharpe']} | {bh['maxdd']} | {bh['turnover_annual']} |",
          f"| 200dma | {sma['cagr']} | {sma['sharpe']} | {sma['maxdd']} | {sma['turnover_annual']} |",
          "", "## Candidates (PRIMARY = shipped `glide (cd5)`)", "",
          "| candidate | CAGR | CAGR(noC) | Sharpe | MaxDD | %inMkt | turn | DSR |",
          "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for nm, r in results.items():
        sc = r["score"]; dsr = r["dsr"]["dsr"] if r["dsr"] else "—"
        md.append(f"| {nm} | {sc['cagr']} | {sc['cagr_nocarry']} | {sc['sharpe']} | {sc['maxdd']} | "
                  f"{sc['time_in_market']} | {sc['turnover_annual']} | {dsr} |")

    prim = "glide (cd5) — shipped"
    pr = results[prim]; ps = pr["score"]
    gate = {
        "(a) cut MaxDD vs B&H (>10pp shallower)": ps["maxdd"] > bh["maxdd"] + 10,
        "(b) beat baseline Sharpe": ps["sharpe"] >= base_sharpe,
        "(c) dd-reduction CI excludes 0": bool(pr["ddci"] and pr["ddci"]["dd_reduction_pp_ci"][0] > 0),
        "(d) survive leave-one-crisis-out": all(v > 0 for v in pr["loco"].values()),
        "(e) turnover < 4/yr (tax-tolerable)": ps["turnover_annual"] < 4,
        "(f) both split-halves beat B&H": pr["halves"]["pre"] > pr["halves"]["bh_pre"] and pr["halves"]["post"] > pr["halves"]["bh_post"],
        "(g) DSR > 0.90": bool(pr["dsr"] and pr["dsr"]["dsr"] > 0.90),
    }
    md += ["", f"## GATE — primary `{prim}`", "",
           f"- split-half Sharpe: pre {pr['halves']['pre']} (B&H {pr['halves']['bh_pre']}), "
           f"post {pr['halves']['post']} (B&H {pr['halves']['bh_post']})",
           "- leave-one-crisis-out (Sharpe edge vs B&H): " +
           ", ".join(f"{k} {v:+}" for k, v in pr["loco"].items()),
           f"- drawdown-reduction bootstrap (pp, B&H−strat): CI {pr['ddci'].get('dd_reduction_pp_ci')} "
           f"P(>0)={pr['ddci'].get('p_reduction_gt0')}",
           f"- DSR {pr['dsr']['dsr'] if pr['dsr'] else '—'} at n_trials={N_TRIALS_HONEST}", ""]
    for k, v in gate.items():
        md.append(f"- {'PASS' if v else 'FAIL'} {k}")
    n_pass = sum(gate.values())
    if all(gate.values()):
        verdict = "PASS — edge survives the honest gate (provisional on sample depth)"
    elif gate["(a) cut MaxDD vs B&H (>10pp shallower)"] and gate["(c) dd-reduction CI excludes 0"]:
        verdict = (f"DISPLAY-ONLY — the drawdown-control edge is robust ({n_pass}/7 gates), but it does not clear "
                   "every bar (see FAILs); keep it experimental / display-first, not a scored signal")
    else:
        verdict = f"DISPLAY-ONLY — fails the gate ({n_pass}/7); keep experimental, do not score"
    md += ["", f"### Verdict: {verdict}"]
    return out_name, md


def main() -> int:
    print("[build] features + conditions (shared) ...")
    ctx = S._ctx()
    reports_dir = config.ROOT / config.load()["storage"]["reports_dir"]
    for spec in (S.CREDIT_CARRY, S.DURATION_TIMING):
        print(f"[calibrate] {spec.key} ...")
        out_name, md = _calibrate(spec, ctx)
        (reports_dir / out_name).write_text("\n".join(md) + "\n")
        print("\n".join(md))
        print(f"\n[report] {reports_dir / out_name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
