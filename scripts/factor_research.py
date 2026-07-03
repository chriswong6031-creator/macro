"""Institutional factor-research battery on the deep panel — the rigor layer above
the leg IC screen (scripts/backtest_strategies.py).

Computes, causally and sector-/market-neutral, for a focused set of legs:
  1. IC-DECAY curve        rank-IC at horizons [10,21,42,63,126] -> optimal holding
  2. MARGINAL IC           each leg residualized vs a momentum CORE -> independent info
  3. REGIME-conditional IC IC in trend-up vs trend-down tapes (validates the live
                           regime-scaled momentum weight in engine/stock_score.py)
  4. LEG CORRELATION       avg cross-sectional Spearman among the leg signals (crowding)
  5. NET-OF-COST L/S       quintile long/short, turnover-costed, annualized Sharpe + MaxDD
  6. ENSEMBLE              EW-z blend of the robust legs vs the best single leg, with a
                           PURGED k-fold + embargo CV (engine.validation.purged_folds)

Honest framing: the deep panel is 114 S&P SURVIVORS (no delisted, no PIT membership),
so every number is survivorship-touched and is WEIGHTING/validation evidence, not a
ship decision. The DSR gate in backtest_strategies already showed these legs are
context, not standalone alpha; this battery characterizes HOW they decay, overlap and
combine, which is what a re-weighting needs.

Run:  .venv/bin/python -m scripts.factor_research
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import logging  # noqa: E402

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import strategy_lab as sl  # noqa: E402
from engine.validation import _maxdd, _sharpe, ic_summary, purged_folds, rank_ic  # noqa: E402
from scripts.backtest_strategies import load_panel  # noqa: E402

LEGS = ["mom_12_1", "resid_mom", "ma200_slope", "volscaled_mom", "live_rs_crowded",
        "rsi_oversold", "idio_vol", "low_beta", "near_52w_high"]
CORE = ["mom_12_1"]                       # momentum core that marginal-IC residualizes against
ENSEMBLE = ["mom_12_1", "resid_mom", "ma200_slope"]   # the robust cohort
HORIZONS = [10, 21, 42, 63, 126]
H0, REBAL, WARMUP, MIN_N = 63, 21, 280, 12


def _z(s: pd.Series) -> pd.Series:
    sd = s.std()
    return (s - s.mean()) / sd if sd else s * 0.0


def _fwd(closes: pd.DataFrame, pos: int, h: int) -> pd.Series:
    fwd = (closes.iloc[pos + h] / closes.iloc[pos] - 1.0).dropna()
    return fwd - fwd.mean()


def main() -> int:
    t0 = time.time()
    closes, sec, _ = load_panel("deep")
    idx = closes.index
    mkt = closes.pct_change().mean(axis=1)            # EW market for the regime tag (causal use below)
    positions = list(range(WARMUP, len(idx) - max(HORIZONS) - 1, REBAL))

    ic = {lg: {h: [] for h in HORIZONS} for lg in LEGS}
    ic_marg = {lg: [] for lg in LEGS}
    ic_reg = {lg: {"up": [], "down": []} for lg in LEGS}
    ls_spread = {lg: [] for lg in ENSEMBLE + ["__ensemble__"]}
    ls_mem = {lg: [] for lg in ENSEMBLE + ["__ensemble__"]}   # per-entry (longs, shorts) sets
    ens_ic = []                                       # (pos, ic) for purged CV
    n_proc = 0                                        # accepted rebalance dates
    corr_acc, corr_n = np.zeros((len(LEGS), len(LEGS))), 0

    for pos in positions:
        d = idx[pos]
        fwds = {h: _fwd(closes, pos, h) for h in HORIZONS}
        if len(fwds[H0]) < MIN_N:
            continue
        n_proc += 1
        reg = "up" if (mkt.iloc[pos - 63:pos].mean() >= 0) else "down"   # causal trailing-mkt tape

        sigs = {}
        for lg in LEGS:
            try:
                raw = sl.STRATEGIES[lg]["fn"](closes, d)
            except Exception:
                continue
            if raw is None or len(raw) < MIN_N:
                continue
            sigs[lg] = sl.sector_demean(raw, sec)

        # 1+3: IC by horizon + regime-conditional IC at H0
        for lg, sg in sigs.items():
            for h in HORIZONS:
                v = rank_ic(sg, fwds[h])
                if v == v:
                    ic[lg][h].append(v)
            v0 = rank_ic(sg, fwds[H0])
            if v0 == v0:
                ic_reg[lg][reg].append(v0)

        # 2: marginal IC — residualize each leg vs the CORE cross-section, then IC the residual
        core_present = [c for c in CORE if c in sigs]
        if core_present:
            X = pd.concat([_z(sigs[c]) for c in core_present], axis=1).dropna()
            for lg, sg in sigs.items():
                if lg in CORE:
                    continue
                j = pd.concat([_z(sg).rename("y"), X], axis=1).dropna()
                if len(j) < MIN_N:
                    continue
                Xm = j.iloc[:, 1:].to_numpy()
                y = j["y"].to_numpy()
                beta, *_ = np.linalg.lstsq(np.c_[np.ones(len(Xm)), Xm], y, rcond=None)
                resid = pd.Series(y - np.c_[np.ones(len(Xm)), Xm] @ beta, index=j.index)
                v = rank_ic(resid, fwds[H0])
                if v == v:
                    ic_marg[lg].append(v)

        # 4: pairwise signal correlation among LEGS present
        present = [lg for lg in LEGS if lg in sigs]
        if len(present) >= 2:
            M = pd.concat([sigs[lg].rename(lg) for lg in present], axis=1).dropna()
            if len(M) >= MIN_N:
                c = M.rank().corr().reindex(index=LEGS, columns=LEGS)
                corr_acc += np.nan_to_num(c.to_numpy())
                corr_n += np.nan_to_num((~c.isna()).to_numpy()).astype(int)

        # 5+6: L/S spread (top-minus-bottom quintile) for ensemble legs + the ensemble blend
        blend = None
        zs = [_z(sigs[lg]) for lg in ENSEMBLE if lg in sigs]
        if len(zs) == len(ENSEMBLE):
            blend = pd.concat(zs, axis=1).mean(axis=1).dropna()
            sigs["__ensemble__"] = blend
            ev = rank_ic(blend, fwds[H0])
            if ev == ev:
                ens_ic.append((pos, ev))
        for lg in ENSEMBLE + ["__ensemble__"]:
            if lg not in sigs:
                continue
            j = pd.concat([sigs[lg].rename("s"), fwds[H0].rename("f")], axis=1).dropna()
            if len(j) < 10:
                continue
            r = j["s"].rank()
            longs = set(j.index[r >= r.quantile(0.8)])
            shorts = set(j.index[r <= r.quantile(0.2)])
            ls_spread[lg].append(float(j["f"][list(longs)].mean() - j["f"][list(shorts)].mean()))
            ls_mem[lg].append((longs, shorts))          # turnover computed at the holding cadence in ls_stats

    # ---- assemble ----
    step = max(1, int(np.ceil(H0 / REBAL)))
    ann = 252.0 / H0

    def ls_stats(lg, cost_bps=10.0):
        sp = np.array(ls_spread[lg][::step], float)   # non-overlapping H0-spaced returns
        mem = ls_mem[lg][::step]                      # memberships at the SAME H0 cadence
        if len(sp) < 10:
            return {"n": len(sp)}
        # turnover = membership churn between consecutive HOLDING-PERIOD snapshots (so the
        # cost frequency matches the H0 return frequency — not the 21d sampling grid).
        tn = [0.0]
        for i in range(1, len(mem)):
            (l, s), (pl, ps) = mem[i], mem[i - 1]
            denom = max(len(l) + len(s), 1)
            tn.append((len(l ^ pl) + len(s ^ ps)) / (2 * denom))
        tn = np.array(tn, float)
        net = sp - tn * (cost_bps / 1e4) * 2.0        # both legs turn over
        return {"n": int(len(sp)), "gross_sharpe": round(_sharpe(sp, int(round(ann))), 2),
                "net_sharpe": round(_sharpe(net, int(round(ann))), 2),
                "net_maxdd_pct": round(100 * _maxdd(net), 1),
                "avg_turnover": round(float(np.mean(tn)), 2),
                "mean_ls_pct": round(100 * float(np.mean(sp)), 2)}

    out = {
        "kind": "factor_research.v1", "panel": "deep",
        "span": [str(idx.min().date()), str(idx.max().date())],
        "n_rebalances": n_proc, "ensemble_n": len(ens_ic),
        "primary_horizon": H0, "rebal": REBAL,
        "ic_decay": {lg: {h: ic_summary(ic[lg][h], periods_per_year=round(252 / REBAL)).get("mean_ic")
                          for h in HORIZONS} for lg in LEGS},
        "ic_ir_by_h": {lg: {h: ic_summary(ic[lg][h], periods_per_year=round(252 / REBAL)).get("ic_ir")
                            for h in HORIZONS} for lg in LEGS},
        "marginal_ic_vs_core": {lg: (round(float(np.mean(ic_marg[lg])), 4) if ic_marg[lg] else None)
                                for lg in LEGS if lg not in CORE},
        "regime_ic": {lg: {"up_mean": round(float(np.mean(ic_reg[lg]["up"])), 4) if ic_reg[lg]["up"] else None,
                           "down_mean": round(float(np.mean(ic_reg[lg]["down"])), 4) if ic_reg[lg]["down"] else None,
                           "n_up": len(ic_reg[lg]["up"]), "n_down": len(ic_reg[lg]["down"])}
                      for lg in LEGS},
        "ls_net": {lg: ls_stats(lg) for lg in ENSEMBLE + ["__ensemble__"]},
        "ensemble_ic": ic_summary([v for _, v in ens_ic], periods_per_year=round(252 / REBAL)),
    }

    # leg correlation matrix
    with np.errstate(invalid="ignore"):
        corr = np.where(corr_n > 0, corr_acc / np.maximum(corr_n, 1), np.nan)
    out["leg_correlation"] = {LEGS[i]: {LEGS[j]: (round(float(corr[i, j]), 2) if corr_n[i, j] else None)
                                        for j in range(len(LEGS))} for i in range(len(LEGS))}

    # purged k-fold + embargo CV of the ensemble IC
    dates = pd.DatetimeIndex([idx[p] for p, _ in ens_ic])
    folds = purged_folds(dates, k=5, embargo=step)
    ic_by_date = {idx[p]: v for p, v in ens_ic}
    out["ensemble_purged_cv"] = {fk: round(float(np.mean([ic_by_date[t] for t in fi if t in ic_by_date])), 4)
                                 for fk, fi in folds.items()
                                 if any(t in ic_by_date for t in fi)}

    outp = Path("data/signal_training/factor_research.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2, default=str))

    # ---- scorecard ----
    print(f"\n===== IC-DECAY by horizon (deep, n={out['n_rebalances']} rebalances) =====")
    print(f"  {'leg':<16}" + "".join(f"{('H'+str(h)):>9}" for h in HORIZONS))
    for lg in LEGS:
        print(f"  {lg:<16}" + "".join(f"{str(out['ic_decay'][lg][h]):>9}" for h in HORIZONS))
    print(f"\n===== MARGINAL IC vs momentum core {CORE} (H{H0}) — independent info =====")
    for lg, v in out["marginal_ic_vs_core"].items():
        print(f"  {lg:<16} {v}")
    print(f"\n===== REGIME-conditional IC (H{H0}: trailing-mkt up vs down tape) =====")
    print(f"  {'leg':<16}{'up':>9}{'down':>9}  (validates regime-scaled momentum weight)")
    for lg in LEGS:
        r = out["regime_ic"][lg]
        print(f"  {lg:<16}{str(r['up_mean']):>9}{str(r['down_mean']):>9}  (n {r['n_up']}/{r['n_down']})")
    print(f"\n===== NET-OF-COST L/S (quintile, 10bps/side, H{H0}) =====")
    print(f"  {'leg':<16}{'gross_SR':>9}{'net_SR':>8}{'maxDD%':>8}{'turn':>7}{'meanLS%':>9}")
    for lg in ENSEMBLE + ["__ensemble__"]:
        s = out["ls_net"][lg]
        if "net_sharpe" in s:
            print(f"  {lg:<16}{s['gross_sharpe']:>9}{s['net_sharpe']:>8}{s['net_maxdd_pct']:>8}"
                  f"{s['avg_turnover']:>7}{s['mean_ls_pct']:>9}")
    e = out["ensemble_ic"]
    print(f"\n  ENSEMBLE {ENSEMBLE}: IC {e.get('mean_ic')}  IC-IR {e.get('ic_ir')}  t {e.get('t_hac')}")
    print(f"  purged-CV per-fold IC: {out['ensemble_purged_cv']}")
    print(f"\n[factor] wrote {outp}  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
