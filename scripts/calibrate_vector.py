"""Bitcoin Vector calibration — the house rule applied to crypto signals.

Every signal band earns a MEASURED forward-return record before the dashboard
is allowed to make any claim about it. We learned this the hard way on the
macro heat board (D31: the confluence score was INVERTED vs forward returns);
the same discipline applies here, with even thinner history (~3.5 BTC cycles).

Outputs (written to reports/ + data/vector/):
  1. Forward-return records per band for Risk Index, Momentum, Structure, BFI,
     Risk Oscillator — count / hit-rate / mean / median at 7/30/90d.
  2. Split-half robustness: same tables on pre/post `split_date`; a relationship
     is "robust" only if its sign holds in BOTH halves.
  3. Allocation backtest vs HODL for all 4 variants: CAGR, Sharpe, Sortino,
     MaxDD, time-in-market (the Vector scorecard metrics).
  4. Whipsaw stats per state signal.
  5. A verdict block: which signals are CONFIRMED (monotone + robust), which are
     CONTEXT-ONLY (weak/unstable), which are INVERTED (flag loudly).

Run: .venv/bin/python -m scripts.calibrate_vector
No look-ahead: signals are close-based, so the backtest acts on shift(1).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import btc_signals  # noqa: E402
from lib import config, store  # noqa: E402
# DSR + cost engine now live in engine.validation (shared with the commodity /
# forex calibrators). Re-exported here so existing importers (and tests) that
# referenced them on scripts.calibrate_vector keep working.
from engine.validation import (  # noqa: E402,F401
    EULER_GAMMA, _norm_cdf, _norm_ppf, _ret_moments, backtest_core, bootstrap_effective_t,
    deflated_sharpe,
)
from engine.validation import (  # noqa: E402 — stability gates (D-vec-GATES)
    block_bootstrap_ci, brier_reliability, dsr_verdict, platt_fit, purged_folds,
    top_correlated_pairs, vif,
)
from engine.trial_ledger import TrialLedger  # noqa: E402

TRADING_YEAR = 365  # BTC trades every day

# Pre-declared DOF for the midterm-blackout override (decision-to-gate + year%4==2
# selector + window shape) per masterplan §4 N1 and the W0 registry draft.
# The registry value takes precedence the moment vector.overrides lands in config,
# so there is no double count — the fallback disappears automatically.
_W0_MIDTERM_DOF: int = 3


def _override_dof(vcfg: dict) -> dict[str, int]:
    """Count the degrees-of-freedom cost of each entry in the override registry.

    vcfg is the full ``vector`` config block (config.load()["vector"]).

    If ``vcfg["overrides"]`` is a non-empty list, read dof_cost from each entry
    that has an id.  Otherwise fall back to the legacy pre-registry inference: if
    the midterm_gate is enabled in the allocation config, charge ``_W0_MIDTERM_DOF``
    DOF as a declared upper-bound (the registry takes precedence once it lands).
    Returns {} when no overrides are active and the gate is disabled or absent.
    """
    overrides = vcfg.get("overrides")
    if isinstance(overrides, list) and overrides:
        return {
            o["id"]: int(o.get("dof_cost", 0))
            for o in overrides
            if isinstance(o, dict) and "id" in o
        }
    # Legacy fallback: infer from allocation.midterm_gate (W0 not yet merged)
    if vcfg.get("allocation", {}).get("midterm_gate", {}).get("enabled"):
        return {"midterm_blackout": _W0_MIDTERM_DOF}
    return {}


# --------------------------------------------------------------------------- #
# forward-return record per band
# --------------------------------------------------------------------------- #
def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({h: close.shift(-h) / close - 1 for h in horizons})


def forward_drawdown(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    """Worst close-to-close drawdown over the next h days — the CORRECT test
    for a risk gauge (a high reading should precede deeper drawdowns even if
    price eventually recovers; forward *return* misses that because extreme
    risk also marks capitulation bottoms — the U-shape we found)."""
    out = {}
    for h in horizons:
        fwd_min = close[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1)
        out[h] = fwd_min / close - 1
    return pd.DataFrame(out)


def drawdown_table(signal: pd.Series, fdd: pd.DataFrame, bands: list,
                   labels: list[str], horizons: list[int]) -> pd.DataFrame:
    cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
    rows = []
    for lab in labels:
        mask = cats == lab
        rec = {"band": lab, "n": int(mask.sum())}
        for h in horizons:
            d = fdd.loc[mask, h].dropna()
            rec[f"avgDD_{h}d"] = round(100 * d.mean(), 2) if len(d) else np.nan
            rec[f"p05DD_{h}d"] = round(100 * d.quantile(0.05), 2) if len(d) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def band_table(signal: pd.Series, fwd: pd.DataFrame, bands: list, labels: list[str],
               horizons: list[int]) -> pd.DataFrame:
    """Bucket `signal` into bands (numeric edges) or categories (list of values)."""
    rows = []
    if isinstance(bands[0], (list, tuple)):  # categorical: each band is a set of values
        grouping = [(lab, signal.isin(vals if isinstance(vals, (list, tuple)) else [vals]))
                    for lab, vals in zip(labels, bands)]
    else:  # numeric edges
        cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
        grouping = [(lab, cats == lab) for lab in labels]
    for lab, mask in grouping:
        n = int(mask.sum())
        rec = {"band": lab, "n": n}
        for h in horizons:
            r = fwd.loc[mask, h].dropna()
            if len(r):
                rec[f"hit_{h}d"] = round(100 * (r > 0).mean(), 1)
                rec[f"mean_{h}d"] = round(100 * r.mean(), 2)
            else:
                rec[f"hit_{h}d"], rec[f"mean_{h}d"] = np.nan, np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def monotone(table: pd.DataFrame, col: str) -> int:
    """+1 if `col` increases down the bands, -1 if decreases, 0 if neither."""
    v = table[col].dropna().values
    if len(v) < 2:
        return 0
    d = np.diff(v)
    if (d >= 0).all() and (d > 0).any():
        return 1
    if (d <= 0).all() and (d < 0).any():
        return -1
    return 0


def _extremes_verdict(table: pd.DataFrame, base: float, mcol: str, hcol: str,
                      n_floor: int = 40) -> str:
    """Characterize a U-shaped (valuation/miner) signal by its TAILS vs. the
    full-sample forward return `base`. The actionable edge of these metrics is
    the extreme band — a deep-value bottom or an over-extended top — not a
    monotone gradient across the middle."""
    parts = []
    lo, hi = table.iloc[0], table.iloc[-1]
    lo_m, lo_n, lo_h = lo.get(mcol), lo.get("n", 0), lo.get(hcol)
    hi_m, hi_n, hi_h = hi.get(mcol), hi.get("n", 0), hi.get(hcol)
    if lo_n >= n_floor and pd.notna(lo_m):
        tag = "BOTTOM" if lo_m > base * 1.25 else "weak"
        parts.append(f"low {lo['band']}: {lo_m:+.1f}%/90d {lo_h}% hit (n={lo_n}) [{tag}]")
    if hi_n >= n_floor and pd.notna(hi_m):
        tag = "TOP" if (hi_m < 0 or hi_m < base * 0.5) else "weak"
        parts.append(f"high {hi['band']}: {hi_m:+.1f}%/90d {hi_h}% hit (n={hi_n}) [{tag}]")
    return "EXTREMES — " + ("; ".join(parts) if parts else "tails too thin to judge")


def rank_trend(table: pd.DataFrame, col: str, n_floor: int = 150) -> int:
    """Robust direction: Spearman sign between band order and `col`, ignoring
    bands thinner than n_floor (small-sample tails shouldn't veto a real trend).
    Returns +1 / -1 / 0."""
    t = table[table["n"] >= n_floor] if "n" in table.columns else table
    v = t[col].dropna().values
    if len(v) < 3:
        return 0
    order = np.arange(len(v))
    rho = np.corrcoef(order, v)[0, 1]
    return 1 if rho > 0.6 else (-1 if rho < -0.6 else 0)


# --------------------------------------------------------------------------- #
# allocation backtest (DSR + cost engine factored into engine.validation; the
# multiple-testing haircut math and the turnover-cost core are shared with the
# commodity / forex calibrators — see engine/validation.py).
# --------------------------------------------------------------------------- #
def backtest(close: pd.Series, alloc: pd.Series, cost_bps: float = 0.0) -> dict:
    """Allocation backtest vs buy-and-hold. `cost_bps` is the ONE-WAY transaction
    cost (spread + fee) in basis points, charged on each unit of position turnover
    |Δpos| — so a full 0→1→0 round trip pays 2×cost_bps. The headline cagr/sharpe/
    maxdd are NET of cost (the honest figure); `*_gross` and `cost_drag_pp` expose
    how much cost ate, and `turnover_annual` is the one-way turnover/yr driving it.
    Default 0.0 keeps legacy callers gross-of-cost; calibrate_vector.main() passes
    the configured crypto cost so the published headline is net."""
    bt = backtest_core(close, alloc, cost_bps=cost_bps)
    ret, gross, strat, turnover, years = (
        bt["ret"], bt["gross"], bt["net"], bt["turnover"], bt["years"])
    eq = (1 + strat).cumprod()
    eq_gross = (1 + gross).cumprod()
    hodl = (1 + ret).cumprod()
    pos = bt["pos"]

    def cagr(e):
        return (e.iloc[-1]) ** (1 / years) - 1 if years > 0 and e.iloc[-1] > 0 else np.nan

    def sharpe(r):
        sd = r.std()
        return (r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan

    def sortino(r):
        dn = r[r < 0].std()
        return (r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan

    def maxdd(e):
        return float((e / e.cummax() - 1).min())

    cagr_net, cagr_gross = cagr(eq), cagr(eq_gross)
    mom = _ret_moments(strat)  # net per-period moments for the Deflated Sharpe
    return {
        "cagr": round(100 * cagr_net, 1), "hodl_cagr": round(100 * cagr(hodl), 1),
        "cagr_gross": round(100 * cagr_gross, 1) if pd.notna(cagr_gross) else np.nan,
        "cost_drag_pp": (round(100 * (cagr_gross - cagr_net), 1)
                         if pd.notna(cagr_net) and pd.notna(cagr_gross) else np.nan),
        "sharpe": round(sharpe(strat), 2), "hodl_sharpe": round(sharpe(ret), 2),
        "sharpe_gross": round(sharpe(gross), 2),
        "sortino": round(sortino(strat), 2), "hodl_sortino": round(sortino(ret), 2),
        "maxdd": round(100 * maxdd(eq), 1), "hodl_maxdd": round(100 * maxdd(hodl), 1),
        "time_in_market": round(100 * (pos > 0).mean(), 1),
        "turnover_annual": round(float(turnover.sum() / years), 1) if years > 0 else np.nan,
        "cost_bps": cost_bps,
        "total_return": round(100 * (eq.iloc[-1] - 1), 0),
        "hodl_total_return": round(100 * (hodl.iloc[-1] - 1), 0),
        "final_vs_hodl": round(eq.iloc[-1] / hodl.iloc[-1], 2),
        # per-period (daily) stats the Deflated Sharpe Ratio consumes:
        "sharpe_daily": round(mom[0], 6) if mom else None,
        "skew": round(mom[1], 4) if mom else None,
        "kurt": round(mom[2], 4) if mom else None,
        "n_obs": mom[3] if mom else None,
    }


def whipsaw(state: pd.Series, max_days: int) -> dict:
    s = state.dropna()
    seg = (s != s.shift()).cumsum()
    sizes = s.groupby(seg).size()
    changes = len(sizes) - 1
    whips = int((sizes.iloc[1:] < max_days).sum()) if changes > 0 else 0
    return {"changes": changes, "whipsaws": whips,
            "pct": round(100 * whips / changes, 1) if changes else 0.0}


# --------------------------------------------------------------------------- #
# STABILITY GATES (D-vec-GATES) — purged walk-forward CV robustness, out-of-fold
# probability calibration of the conditional direction model, signal collinearity,
# and a block-bootstrap CI on the allocation backtest. All ADDITIVE report blocks.
# --------------------------------------------------------------------------- #
def cv_fold_signs(signal: pd.Series, fdf: pd.DataFrame, bands, labels, h: int,
                  col_prefix: str, folds: dict, builder, n_floor: int = 80) -> list:
    """Per-fold rank-trend sign under purged walk-forward CV (folds already embargoed
    by `embargo` rows, so no forward label leaks across a fold edge). 0 = fold too thin."""
    signs = []
    for idx in folds.values():
        if len(idx) < max(n_floor * 2, 200):
            signs.append(0)
            continue
        t = builder(signal.loc[idx], fdf.loc[idx], bands, labels, [h])
        signs.append(rank_trend(t, f"{col_prefix}_{h}d", n_floor=n_floor))
    return signs


def fold_robust(full_sign: int, fold_signs: list, want: int) -> bool:
    """Purged-CV robustness: the full-sample sign matches `want`, NO fold with
    adequate data flips to the opposite sign, and all-but-one of the non-empty folds
    agree. Stricter than the single pre/post split it complements."""
    nz = [s for s in fold_signs if s != 0]
    if not nz:
        return False
    flip = sum(1 for s in nz if s == -want)
    agree = sum(1 for s in nz if s == want)
    return full_sign == want and flip == 0 and agree >= max(1, len(nz) - 1)


def oof_cell_probs(df: pd.DataFrame, folds: dict, h: int, alpha: int = 10, min_n: int = 20):
    """OUT-OF-FOLD calibration data for the conditional direction model: for each
    test fold, predict P(up over h) from the momentum_state×risk_regime cell rate fit
    on the OTHER folds (empirical-Bayes shrunk to the marginal, exactly the live
    _cond_up_prob mechanism), then pool (p, y). This is the missing LEVEL check on the
    headline conviction probability — no look-ahead because the cell rate is OOF."""
    close = df["close"]
    y = (close.shift(-h) > close).astype(float)
    mom, risk = df.get("momentum_state"), df.get("risk_regime")
    if mom is None or risk is None:
        return None
    P, Y = [], []
    for test in folds.values():
        train = df.index.difference(test)
        sub = pd.DataFrame({"y": y, "m": mom, "r": risk}).loc[train].dropna()
        if len(sub) < 200:
            continue
        marg = sub["y"].mean()
        cell = {}
        for (m_, r_), g in sub.groupby(["m", "r"]):
            n = len(g)
            cell[(m_, r_)] = (g["y"].sum() + alpha * marg) / (n + alpha) if n >= min_n else marg
        for d in test:
            yd, md, rd = y.get(d), mom.get(d), risk.get(d)
            if pd.isna(yd) or pd.isna(md) or pd.isna(rd):
                continue
            P.append(cell.get((md, rd), marg))
            Y.append(float(yd))
    return (np.array(P), np.array(Y)) if len(P) >= 50 else None


# --------------------------------------------------------------------------- #
# ENSEMBLE CAPSTONE promotion gate (D-vec-ENSEMBLE) — does a fixed-form,
# orthogonalized, gate-passed ensemble BEAT the heuristic composite_state + the
# best single signal, out-of-sample, in BOTH halves? Each axis is oriented by its
# CALIBRATED expected-return band-map (so U-shaped extremes are oriented correctly,
# which a linear z×want cannot), de-correlated in a fixed order, equal-weight
# combined. Honest if-it-fails: ship the simpler winner, never overfit.
# --------------------------------------------------------------------------- #
_ENS_ORDER = ["risk_index", "net_liq_roc", "vrp", "cot_z", "mvrv_z", "momentum"]
_HEUR_EXPOSURE = {"RISK-OFF": 0.0, "DISTRIBUTE": 0.25, "NEUTRAL": 0.5,
                  "RISK-ON": 0.75, "ACCUMULATE": 1.0}


def _zc(s: pd.Series, n: int = 365) -> pd.Series:
    m = s.rolling(n, min_periods=max(60, n // 4))
    return (s - m.mean()) / m.std().replace(0, np.nan)


def _expret_signal(signal: pd.Series, fwd: pd.DataFrame, bands, labels, h: int,
                   halves: dict | None = None):
    """Orient a (U-shaped) signal by its CALIBRATED expected fwd-h return: map each
    value to its band's mean_h. The non-linear orientation a linear z×want can't do.

    When `halves` is given (the pre/post evaluation split), orient CROSS-FITTED: each
    evaluation half is mapped using the band->mean fitted on the COMPLEMENTARY data, so
    the pre/post Sharpe comparison that drives the promotion gate is out-of-sample. The
    old full-sample map leaked each half's own future outcomes into its orientation — a
    split-half look-ahead that biased the gate toward PROMOTE. Without `halves` (display)
    it keeps the full-sample map."""
    if isinstance(bands[0], (list, tuple)):
        return None

    def _map(fit_idx, apply_idx):
        t = band_table(signal.loc[fit_idx], fwd.loc[fit_idx], bands, labels, [h])
        m = {r["band"]: r.get(f"mean_{h}d") for _, r in t.iterrows()}
        cats = pd.cut(signal.loc[apply_idx], bins=bands, labels=labels, include_lowest=True)
        return cats.astype(object).map(m).astype(float)

    legs = [hf for hf in (halves or {}) if hf != "full"]
    if len(legs) < 2:
        return _map(signal.index, signal.index)
    out = pd.Series(np.nan, index=signal.index, dtype=float)
    covered = signal.index[:0]
    for ev in legs:
        comp = signal.index.difference(halves[ev])     # fit on everything NOT in this half
        out.loc[halves[ev]] = _map(comp, halves[ev])
        covered = covered.union(halves[ev])
    # ONLY fill rows OUTSIDE every eval half (embargo / full-only) with the full-sample
    # map. An eval-half row whose band is absent from its complement stays NaN (dropped
    # from scoring) rather than being full-map-filled — that fill would re-leak its own
    # outcomes, the very look-ahead this cross-fit removes.
    rest = signal.index.difference(covered)
    if len(rest):
        out.loc[rest] = _map(signal.index, signal.index).loc[rest]
    return out


def ensemble_promotion(df, fwd, halves, folds, SIGNALS, cost_bps, n_trials):
    """Build the orthogonalized equal-weight ensemble + baselines; decide promotion."""
    from engine.validation import resid_z, block_bootstrap_ci
    ecfg = config.load()["vector"].get("ensemble", {})
    bw, bmin = ecfg.get("beta_window_d", 252), ecfg.get("beta_min_train_d", 252)
    zw = ecfg.get("z_window_d", 365)
    close = df["close"]
    h = 90 if 90 in fwd.columns else int(fwd.columns[-1])
    res, basis = {}, []
    for sig in _ENS_ORDER:
        if sig not in df.columns or sig not in SIGNALS:
            continue
        er = _expret_signal(df[sig], fwd, SIGNALS[sig]["bands"], SIGNALS[sig]["labels"], h,
                            halves=halves)   # cross-fit so pre/post scoring is out-of-sample
        if er is None:
            continue
        z = _zc(er, zw)
        r = resid_z(z, basis, bw, bmin) if basis else z.copy()
        r = _zc(r, zw)
        res[sig] = r
        basis.append(r)
    if len(res) < 3:
        return None
    R = pd.DataFrame(res)
    ens = R.mean(axis=1, skipna=True)                       # equal-weight (the robust default)
    ics = {s: round(float(R[s].rank().corr(fwd[h].rank())), 3) for s in res}
    best = max(ics, key=lambda s: abs(ics[s]))
    exp = {
        "ensemble_eqw": ((_zc(ens) + 1.5) / 3.0).clip(0, 1),
        "best_single": ((_zc(R[best]) + 1.5) / 3.0).clip(0, 1),
        "heuristic": df["composite_state"].map(_HEUR_EXPOSURE),
    }

    def sharpe(net):
        r = net.dropna()
        sd = r.std()
        return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else float("nan")

    def ns(e, idx):
        return round(sharpe(backtest_core(close.loc[idx], e.reindex(idx), cost_bps)["net"]), 2)

    table = {name: {half: ns(e, idx) for half, idx in halves.items()} for name, e in exp.items()}
    ens_ic = round(float(ens.rank().corr(fwd[h].rank())), 3)
    legs = [hf for hf in halves if hf != "full"]
    beats = lambda a, b: all(table[a][hf] > table[b][hf] for hf in legs)
    boot = block_bootstrap_ci(backtest_core(close, exp["ensemble_eqw"], cost_bps)["net"],
                              block=21, B=5000, ann=TRADING_YEAR)
    if beats("ensemble_eqw", "best_single") and beats("ensemble_eqw", "heuristic"):
        verdict = "PROMOTE — orthogonalized ensemble beats best-single AND heuristic in both halves"
    elif beats("ensemble_eqw", "heuristic"):
        verdict = "KEEP-EQUAL-WEIGHT — beats the heuristic but not the best single signal; ship the simpler read"
    elif all(table["heuristic"][hf] >= table["ensemble_eqw"][hf] for hf in legs):
        verdict = "KEEP-HEURISTIC — the hand-tuned composite_state is NOT beaten by the fixed-form ensemble"
    else:
        verdict = "KEEP-HEURISTIC+DIAGNOSTIC — no clean sweep; ensemble is context-only"
    return {"axes": list(res), "best_single": best, "ensemble_ic": ens_ic, "axis_ic": ics,
            "net_sharpe": table, "ensemble_sharpe_ci": boot.get("sharpe_ci") if boot else None,
            "horizon": h, "verdict": verdict,
            "note": ("Each axis oriented by its calibrated expected-fwd-return band-map (handles the "
                     "U-shape a linear z can't), de-correlated in a fixed order, equal-weight combined. "
                     "Promotion needs the ensemble to beat BOTH the best single signal AND the heuristic "
                     "composite_state on net Sharpe in BOTH halves. Honest non-promotion = keep the simpler "
                     "winner (the forecast-combination literature: equal-weight/best-single are brutal "
                     "baselines on ~3 cycles).")}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = config.load()["vector"]["calibration"]
    horizons = cfg["forward_days"]
    df = btc_signals.compute_all()
    df = df.loc[cfg["start_date"]:].copy()
    close = df["close"]
    fwd = forward_returns(close, horizons)
    fdd = forward_drawdown(close, horizons)

    # EMBARGO FIX (D-vec-GATES): the pre-half's last `embargo` rows have forward
    # labels (up to max horizon) that peek across split_date into the post half —
    # the leak a bare split has. Drop them so the two halves are clean.
    embargo = int(max(horizons))
    _pre = df.index[df.index < cfg["split_date"]]
    halves = {
        "full": df.index,
        "pre": _pre[:-embargo] if len(_pre) > embargo else _pre,
        "post": df.index[df.index >= cfg["split_date"]],
    }
    # Purged + embargoed walk-forward folds — the stricter robustness gate that
    # complements the single split (K contiguous folds, each embargoed on its right edge).
    k_folds = int(cfg.get("cv_folds", 5))
    folds = purged_folds(df.index, k_folds, embargo)

    SIGNALS = {
        "risk_index": {
            "bands": [-0.1, 25, 50, 75, 100],
            "labels": ["0-25", "25-50", "50-75", "75-100"],
            "want": -1,  # higher risk SHOULD mean lower forward return
        },
        "momentum": {
            "bands": [-1.01, -0.5, 0.0, 0.5, 1.01],
            "labels": ["<-0.5", "-0.5..0", "0..0.5", ">0.5"],
            "want": 1,
        },
        "structure": {
            "bands": [-1.01, -0.5, 0.5, 1.01],
            "labels": ["broken", "neutral", "constructive"],
            "want": 1,
        },
        "risk_oscillator": {
            "bands": [-0.01, 0.4, 0.6, 1.01],
            "labels": ["falling", "neutral", "rising"],
            "want": -1,
        },
    }
    if "bfi" in df.columns:
        SIGNALS["bfi"] = {"bands": [-0.1, 40, 60, 100.1],
                          "labels": ["<40", "40-60", ">60"], "want": 1}

    # Tier-1 accuracy-upgrade signals (standalone, MEASURED before any blend —
    # research/VECTOR_ACCURACY_UPGRADE.md §4). Deep-history valuation/miner
    # metrics (mvrv_z, nupl, mayer, puell) are the trustworthy anchors; the
    # 2022-> cohort metric (sth_cb_ratio) is confirmation-only until another
    # cycle accrues. hash_ribbon_capit is a 2-state flag — read its table, not
    # the rank-trend verdict (rank-trend needs >=3 bands).
    VAL_SIGNALS = {
        "mvrv_z": {"bands": [-5, 0, 1, 2, 3.5, 100], "shape": "extremes",
                   "labels": ["<0", "0-1", "1-2", "2-3.5", ">3.5"], "want": -1},
        "nupl": {"bands": [-1, 0, 0.25, 0.5, 0.65, 1.1], "shape": "extremes",
                 "labels": ["<0", "0-.25", ".25-.5", ".5-.65", ">.65"], "want": -1},
        "mayer": {"bands": [0, 0.8, 1.0, 1.5, 2.4, 100], "shape": "extremes",
                  "labels": ["<0.8", "0.8-1", "1-1.5", "1.5-2.4", ">2.4"], "want": -1},
        "puell": {"bands": [0, 0.5, 1, 2, 4, 100], "shape": "extremes",
                  "labels": ["<0.5", "0.5-1", "1-2", "2-4", ">4"], "want": -1},
        "sth_cb_ratio": {"bands": [-1, -0.1, 0, 0.2, 0.5, 100], "shape": "extremes",
                         "labels": ["<-10%", "-10-0%", "0-20%", "20-50%", ">50%"], "want": 1},
        "hash_ribbon_capit": {"bands": [[0.0], [1.0]],
                              "labels": ["normal", "capitulation"], "want": 1},
        # Tier-2 options layer (DVOL/VRP history 2021-> => post-half only). DVOL
        # is U-shaped (complacency vs. panic-bounce); VRP negative = vol underpriced.
        "dvol": {"bands": [0, 40, 55, 70, 90, 500], "shape": "extremes",
                 "labels": ["<40", "40-55", "55-70", "70-90", ">90"], "want": -1},
        "vrp": {"bands": [-100, -5, 0, 5, 15, 100], "shape": "extremes",
                "labels": ["<-5", "-5-0", "0-5", "5-15", ">15"], "want": -1},
        # Tier-2 leverage layer (OI 2022->, funding 2023-> => confirmation-only).
        "leverage_stress": {"bands": [-0.1, 25, 50, 75, 100.1], "shape": "extremes",
                            "labels": ["0-25", "25-50", "50-75", "75-100"], "want": -1},
        "funding_z": {"bands": [-10, -1, 0, 1, 2, 10], "shape": "extremes",
                      "labels": ["<-1", "-1-0", "0-1", "1-2", ">2"], "want": -1},
        "oi_price_divergence": {"bands": [-10, -0.1, 0, 0.1, 0.25, 10], "shape": "extremes",
                                "labels": ["<-10%", "-10-0%", "0-10%", "10-25%", ">25%"], "want": -1},
        # Tier-3 macro overlay (BTC 2014-> => deeper; judged monotone, not tails).
        "net_liq_roc": {"bands": [-50, -2, 0, 2, 5, 50],
                        "labels": ["<-2%", "-2-0%", "0-2%", "2-5%", ">5%"], "want": 1},
        "macro_score": {"bands": [-1.01, -0.3, -0.1, 0.1, 0.3, 1.01],
                        "labels": ["<-.3", "-.3-.1", "-.1-.1", ".1-.3", ">.3"], "want": 1},
        # On-chain regime (CryptoQuant-style). SSR osc deep (2017->); premium/MPI 2022->.
        "coinbase_premium_ema": {"bands": [-5, -0.3, 0, 0.5, 1.5, 5], "shape": "extremes",
                                 "labels": ["<-.3", "-.3-0", "0-.5", ".5-1.5", ">1.5"], "want": 1},
        "ssr_oscillator": {"bands": [-3.01, -1, -0.3, 0.5, 1.5, 3.01],
                           "labels": ["<-1", "-1-.3", "-.3-.5", ".5-1.5", ">1.5"], "want": 1},
        "mpi": {"bands": [0, 0.7, 1, 1.5, 2.5, 10],
                "labels": ["<0.7", "0.7-1", "1-1.5", "1.5-2.5", ">2.5"], "want": -1},
        # US spot-ETF net flows (bgeo/Glassnode 2024-> => ETF-era only, CONFIRMATION-
        # grade: too short for both-halves robustness). z of the 5d net flow vs 90d norm;
        # hypothesis is momentum-like (strong inflow -> higher forward return, want +1).
        "etf_flow_z": {"bands": [-3.01, -0.75, -0.25, 0.25, 0.75, 3.01],
                       "labels": ["<-.75", "-.75--.25", "-.25-.25", ".25-.75", ">.75"], "want": 1},
        # Reserve Risk (checkonchain 2010-> => deep). Low = accumulation, high = top.
        "reserve_risk": {"bands": [0, 0.0015, 0.0025, 0.005, 0.02, 1], "shape": "extremes",
                         "labels": ["<.0015", ".0015-.0025", ".0025-.005", ".005-.02", ">.02"],
                         "want": -1},
        # Impulse (momentum acceleration, 2014-> deep). Positive = thrust/continuation.
        "impulse": {"bands": [-3.01, -0.5, -0.15, 0.15, 0.5, 3.01],
                    "labels": ["<-.5", "-.5--.15", "-.15-.15", ".15-.5", ">.5"], "want": 1},
        # New-factor hunt: halving clock (cyclical, n=3 prior), COT positioning, BTC-SPX corr.
        "cycle_pct": {"bands": [-0.01, 0.22, 0.42, 0.70, 1.0, 1.41],
                      "labels": ["accum", "markup", "markdown", "recovery", "late"], "want": -1},
        "cot_z": {"bands": [-5, -1.5, -0.5, 0.5, 1.5, 5], "shape": "extremes",
                  "labels": ["<-1.5", "-1.5--.5", "-.5-.5", ".5-1.5", ">1.5"], "want": -1},
        "corr_spx": {"bands": [-1.01, 0, 0.2, 0.4, 1.01],
                     "labels": ["<0", "0-.2", ".2-.4", ">.4"], "want": -1},
        # VDD Multiple (spending-behaviour, checkonchain 2011-> deep). High = distribution.
        "vdd_multiple": {"bands": [0, 0.5, 0.87, 1.4, 2.9, 100], "shape": "extremes",
                         "labels": ["<.5", ".5-.87", ".87-1.4", "1.4-2.9", ">2.9"], "want": -1},
        # Global (US+China) M2 YoY growth — broad-money tide, leads BTC ~10wk.
        "global_m2_yoy": {"bands": [0, 5.5, 7, 8.5, 11, 20],
                          "labels": ["<5.5", "5.5-7", "7-8.5", "8.5-11", ">11"], "want": 1},
        # Tier-1 NEW factors (D-vec-RVCONE / D-vec-STBL). Realized-vol CONE + vol-of-vol
        # are full-history 2015-> (both-halves-clean) — judged as U-shaped vol (extremes:
        # low=complacency, high=panic-bounce). Stablecoin supply-growth z = the crypto-
        # native liquidity TIDE 2018-> (monotone, want +1, like the M2/net-liq tides).
        "rv_cone_pctile": {"bands": [-0.1, 25, 50, 75, 100.1], "shape": "extremes",
                           "labels": ["0-25", "25-50", "50-75", "75-100"], "want": -1},
        "vov_pctile": {"bands": [-0.1, 25, 50, 75, 100.1], "shape": "extremes",
                       "labels": ["0-25", "25-50", "50-75", "75-100"], "want": -1},
        "stbl_growth_z": {"bands": [-4.01, -1, 0, 1, 2, 4.01],
                          "labels": ["<-1", "-1-0", "0-1", "1-2", ">2"], "want": 1},
    }
    for _k, _v in VAL_SIGNALS.items():
        if _k in df.columns:
            SIGNALS[_k] = _v

    report: dict = {"meta": {"span": f"{df.index.min().date()}..{df.index.max().date()}",
                             "rows": len(df), "split": cfg["split_date"]},
                    "signals": {}, "risk_drawdown": {}, "allocation": {}, "whipsaw": {}}

    # Risk Index judged as a RISK gauge: forward drawdown by band (the correct
    # test — a working risk gauge precedes deeper drawdowns monotonically).
    rk_bands = [-0.1, 25, 50, 75, 100]
    rk_labels = ["0-25", "25-50", "50-75", "75-100"]
    ddt = {half: drawdown_table(df.loc[idx, "risk_index"], fdd.loc[idx],
                                rk_bands, rk_labels, horizons).to_dict("records")
           for half, idx in halves.items()}
    dd_col = f"avgDD_{horizons[0]}d"  # near-term: the right horizon for a risk gauge
    dd_full = rank_trend(pd.DataFrame(ddt["full"]), dd_col)
    dd_pre = rank_trend(pd.DataFrame(ddt["pre"]), dd_col)
    dd_post = rank_trend(pd.DataFrame(ddt["post"]), dd_col)
    if dd_full == -1 and dd_pre == -1 and dd_post == -1:
        ddt["verdict"] = f"CONFIRMED near-term risk gauge ({horizons[0]}d drawdown)"
    elif dd_full == -1:
        ddt["verdict"] = f"DIRECTIONAL near-term risk gauge ({horizons[0]}d; one half weak)"
    else:
        ddt["verdict"] = "CONTEXT-ONLY — rely on allocation drawdown reduction"
    ddt["rank_trend"] = {"full": dd_full, "pre": dd_pre, "post": dd_post, "want": -1,
                         "horizon": horizons[0]}
    report["risk_drawdown"] = ddt

    for sig, spec in SIGNALS.items():
        if sig not in df.columns:
            continue
        entry = {}
        for half, idx in halves.items():
            t = band_table(df.loc[idx, sig], fwd.loc[idx], spec["bands"], spec["labels"], horizons)
            entry[half] = t.to_dict("records")
        # robustness verdict on the 90d column via rank-trend (tolerant of one
        # noisy small-sample band; the long horizon is where signal separates)
        hcol = f"mean_{horizons[-1]}d"
        want = spec["want"]
        m_full = rank_trend(pd.DataFrame(entry["full"]), hcol)
        m_pre = rank_trend(pd.DataFrame(entry["pre"]), hcol)
        m_post = rank_trend(pd.DataFrame(entry["post"]), hcol)
        # Valuation/miner metrics are U-SHAPED (the signal is in the tails, not a
        # monotone gradient — same reason the Risk Index is judged on drawdown).
        # rank-trend would mislabel a real top/bottom call as INVERTED, so judge
        # these on tail separation vs. the sample mean instead.
        if spec.get("shape") == "extremes":
            base = float(fwd.loc[df.index, horizons[-1]].mean() * 100)
            full_t = pd.DataFrame(entry["full"])
            entry["verdict"] = _extremes_verdict(full_t, base, hcol, f"hit_{horizons[-1]}d")
            entry["monotone"] = {"full": m_full, "pre": m_pre, "post": m_post,
                                 "want": want, "sample_mean_90d": round(base, 1)}
            report["signals"][sig] = entry
            continue
        if m_full == want and m_pre == want and m_post == want:
            verdict = "CONFIRMED"
        elif m_full == -want:
            verdict = "INVERTED"
        elif m_full == want and (m_pre == want or m_post == want):
            verdict = "DIRECTIONAL (one half weak)"
        elif m_full == want:
            verdict = "DIRECTIONAL (full only)"
        else:
            verdict = "CONTEXT-ONLY"
        entry["verdict"] = verdict
        entry["monotone"] = {"full": m_full, "pre": m_pre, "post": m_post, "want": want}
        report["signals"][sig] = entry

    # One-way transaction cost (spread+fee) and the honest trial count for the
    # Deflated Sharpe live in config with code defaults (the dislocation/leaf
    # precedent — ships without a config.yml edit). 10 bps ≈ a realistic BTC-spot
    # round-trip leg; n_trials is a manual UPPER-BOUND of configs explored.
    cost_bps = float(cfg.get("cost_bps", 10.0))
    n_trials = int(cfg.get("n_trials", 50))

    for variant in config.load()["vector"]["allocation"]["variants"]:
        col = f"alloc_{variant}"
        if col in df.columns:
            report["allocation"][variant] = backtest(close, df[col], cost_bps=cost_bps)

    # ---- multiple-testing haircut (Deflated Sharpe on the SHIPPED variant) ---- #
    # The published Sharpe is the MAX over the variants/thresholds we tried, so it
    # is upward-biased; the DSR deflates it for n_trials, sample length, skew and
    # fat tails. We estimate the cross-trial SR variance from the variants actually
    # backtested (falls back to the SR-estimator proxy if only one exists).
    va = report["allocation"]
    if va:
        sel = ("optimal" if "optimal" in va else
               max(va, key=lambda k: va[k]["cagr"] if pd.notna(va[k]["cagr"]) else -1e9))
        daily_srs = [v["sharpe_daily"] for v in va.values() if v.get("sharpe_daily") is not None]
        sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) >= 2 else None
        m = va[sel]
        # Block-bootstrap effective sample size (W5/N7): autocorrelated daily returns
        # make raw sqrt(T-1) overconfident; t_eff is the autocorrelation-honest count.
        net_series = backtest_core(close, df[f"alloc_{sel}"], cost_bps=cost_bps)["net"]
        eff = bootstrap_effective_t(net_series)
        # Override-registry DOF counting (W5): add declared dof_cost of each override
        # entry to n_trials so the multiple-testing budget accounts for human overrides
        # that were not itemized as allocation variants.
        dof = _override_dof(config.load()["vector"])
        n_declared = n_trials + sum(dof.values())
        # honest-N via the ledger (P3): itemize the allocation variants tried + declare the
        # config upper-bound (including override dof) as a floor.
        _led = TrialLedger()
        _led.log_grid([{"variant": k} for k in va], family="vector", source="alloc_variant")
        _led.log_declared_budget(n_declared, family="vector",
                                 reason=f"cfg.calibration.n_trials ({n_trials}) + override dof_cost {dof} — declared upper-bound (calibrate_vector W5)")
        dsr = deflated_sharpe(m.get("sharpe_daily"), m.get("skew"), m.get("kurt"),
                              m.get("n_obs"), ledger=_led, family="vector", sr_variance=sr_var,
                              trading_year=TRADING_YEAR, t_eff=eff.get("t_eff"))
        if dsr is not None:
            dsr["selected_variant"] = sel
            dsr["sr_variance_source"] = ("max(cross-variant dispersion, null SR-sampling proxy)"
                                         if sr_var else "null SR-sampling proxy")
            dsr["verdict"] = ("SURVIVES multiple-testing (DSR≥0.95)" if dsr["dsr"] >= 0.95
                              else "MARGINAL (0.90≤DSR<0.95)" if dsr["dsr"] >= 0.90
                              else "FAILS multiple-testing haircut (DSR<0.90)")
            dsr["effective_t"] = eff if eff else {"note": "series too short"}
            dsr["note"] = ("DSR = P(true Sharpe>0) after deflating for n_trials independent "
                           "configs, sample length, skew & kurtosis. n_trials is a manual "
                           "UPPER-BOUND of the signal/threshold/window variants explored — "
                           "overestimating is the conservative direction (de Prado). Bump "
                           "vector.calibration.n_trials as you try more. "
                           "The DSR statistic now uses a block-bootstrap effective sample size "
                           "(T_eff) instead of raw sqrt(T-1), so autocorrelated daily returns "
                           "no longer overstate confidence.")
        report["multiple_testing"] = dsr or {"dsr": None, "verdict": "insufficient data"}
        report["trial_log"] = {
            "asof": str(df.index.max().date()),
            "n_trials_config": n_trials,
            "overrides_dof": dof,
            "n_trials_declared": n_declared,
            "cost_bps_one_way": cost_bps,
            "allocation_variants_tested": list(va),
            "signal_families_screened": sorted(report["signals"]),
            "n_signal_families": len(report["signals"]),
            "fdr_note": (
                "The 32-family band-edge screen is a multiple-comparison surface — at screen "
                "strength expect ~1-2 spuriously CONFIRMED families out of 32 under the null. "
                "Verdicts are hypothesis-generating only and should be treated as directional "
                "priors, not causal proofs. Sizing authority flows solely through the DSR-gated "
                "allocation backtest, whose N these signal families inflate via n_trials."
            ),
            "note": ("Point-in-time trial ledger (overwritten each run). n_trials_declared is "
                     "an upper-bound count of independent strategy configs explored across the "
                     "hunt, used to deflate the headline Sharpe. Raise it as you try more."),
        }

    for sig in ("momentum_state", "risk_regime", "structure_state", "market_mode", "alt_cycle_leader"):
        if sig in df.columns:
            report["whipsaw"][sig] = whipsaw(df[sig], cfg["whipsaw_max_days"])

    # ===================== STABILITY GATES (D-vec-GATES) ===================== #
    # (1) Purged walk-forward CV robustness — a stricter, leak-free complement to
    #     the single split: each return-signal's band→forward sign must hold across
    #     the embargoed folds with no flip. Drawdown-judged signals use want=-1.
    cv = {"k_folds": len(folds), "embargo_days": embargo,
          "fold_spans": [f"{idx.min().date()}..{idx.max().date()}" for idx in folds.values() if len(idx)],
          "signals": {}}
    h_last = horizons[-1]
    for sig, spec in SIGNALS.items():
        if sig not in df.columns or isinstance(spec["bands"][0], (list, tuple)) or len(spec["labels"]) < 3:
            continue
        drawdown_judged = sig in ("risk_index", "risk_oscillator")
        builder = drawdown_table if drawdown_judged else band_table
        fdf = fdd if drawdown_judged else fwd
        prefix = "avgDD" if drawdown_judged else "mean"
        # judge each signal at ITS calibrated horizon: drawdown gauges at the short
        # horizon (the contrarian flip weakens the relation by 90d), returns at long.
        h_cv = horizons[0] if drawdown_judged else h_last
        signs = cv_fold_signs(df[sig], fdf, spec["bands"], spec["labels"], h_cv, prefix, folds, builder)
        full_t = builder(df[sig], fdf, spec["bands"], spec["labels"], [h_cv])
        full_sign = rank_trend(full_t, f"{prefix}_{h_cv}d", n_floor=150)
        cv["signals"][sig] = {"full": full_sign, "folds": signs,
                              "robust": fold_robust(full_sign, signs, spec["want"]), "want": spec["want"]}
    cv["n_robust"] = sum(1 for v in cv["signals"].values() if v["robust"])
    cv["note"] = ("Purged + embargoed walk-forward CV (embargo = max forward horizon) replaces the "
                  "single split_date's leaky boundary. 'robust' = full-sample sign matches `want`, no "
                  "fold flips, all-but-one folds agree. Stricter than pre/post; both are reported.")
    report["cross_validation"] = cv

    # (2) Out-of-fold PROBABILITY CALIBRATION of the conditional direction model —
    #     does the headline conviction probability match realized frequency?
    oof = oof_cell_probs(df, folds, horizons[0])
    if oof is not None:
        P, Y = oof
        pc = brier_reliability(P, Y) or {}
        pc["platt"] = platt_fit(P, Y) or {}
        pc["horizon"] = horizons[0]
        pc["note"] = ("Out-of-fold: each day's P(up) is the momentum×risk cell rate fit on the OTHER "
                      "folds (EB-shrunk, the live mechanism), scored vs realized. brier<base_brier = "
                      "skill; Platt a≈1/b≈0 = already calibrated. Direction is a near-coin-flip, so "
                      "calibrated probabilities cluster near the base rate — that is the honest result.")
        report["probability_calibration"] = pc

    # (3) COLLINEARITY — VIF + the high-|corr| clusters, to surface the cost-basis
    #     triple-counting a heuristic composite_state can't see.
    coll_cols = [s for s in SIGNALS if s in df.columns
                 and not isinstance(SIGNALS[s]["bands"][0], (list, tuple))]
    cdf = df[coll_cols].apply(pd.to_numeric, errors="coerce")
    vifs = vif(cdf)
    if vifs:
        report["collinearity"] = {
            "vif": dict(sorted(vifs.items(), key=lambda kv: -kv[1])),
            "redundant": [k for k, v in vifs.items() if v >= 5],
            "top_pairs": top_correlated_pairs(cdf, k=10, thresh=0.6),
            "note": ("VIF>5 ≈ redundant (its forward info is already carried by other signals); the "
                     "high-corr pairs name the cluster. This MEASURES the independent contribution "
                     "the one-representative-per-axis rule asserts — orthogonalize before any blend."),
        }

    # (4) Block-bootstrap CI on the shipped allocation variant — the point-estimate
    #     Sharpe/MaxDD now ship with a 95% interval (+ DSR already haircuts the mean).
    sel_variant = (report.get("multiple_testing") or {}).get("selected_variant") or "optimal"
    acol = f"alloc_{sel_variant}"
    if acol in df.columns:
        net = backtest_core(close, df[acol], cost_bps=cfg.get("cost_bps", 0))["net"]
        boot = block_bootstrap_ci(net, block=21, B=5000, ann=TRADING_YEAR)
        if boot:
            boot["variant"] = sel_variant
            boot["note"] = ("Circular block bootstrap (21d blocks) of the NET daily strategy returns → "
                            "95% CI [2.5, 50, 97.5]. sharpe_gt0_prob = bootstrap P(Sharpe>0). Pairs with "
                            "the Deflated-Sharpe haircut: DSR deflates the mean, this bounds the variance.")
            report["allocation_bootstrap"] = boot

    # ENSEMBLE CAPSTONE promotion gate (D-vec-ENSEMBLE) — measure-before-blend
    try:
        ens = ensemble_promotion(df, fwd, halves, folds, SIGNALS, cost_bps, n_trials)
        if ens:
            report["ensemble_promotion"] = ens
    except Exception as e:  # noqa: BLE001 — never let the gate break the calibration
        report["ensemble_promotion"] = {"verdict": f"error: {e}"}

    # ---- persist ----------------------------------------------------------- #
    outdir = config.data_dir() / "vector"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "calibration.json").write_text(json.dumps(report, indent=2, default=str))
    (outdir / "trial_log.json").write_text(json.dumps(report.get("trial_log", {}), indent=2, default=str))
    df.to_parquet(outdir / "signals.parquet")
    _write_markdown(report)
    # Standing integration-candidates A/B (does any factor earn a place in the
    # risk/allocation MATH yet?) — re-checked each calibration as history deepens.
    try:
        from scripts.integration_lab import write_report as _intg_report
        _intg_report(config.load()["storage"]["reports_dir"])
    except Exception as e:  # noqa: BLE001 — never let the candidate report break calibration
        print(f"integration-candidates report skipped ({e})")
    print(_summary(report))
    return 0


def _summary(report: dict) -> str:
    L = [f"\n=== Bitcoin Vector calibration ({report['meta']['span']}, "
         f"{report['meta']['rows']} days) ==="]
    L.append("\nSIGNAL VERDICTS (forward-return monotonicity, split-half):")
    for sig, e in report["signals"].items():
        L.append(f"  {sig:16s} {e['verdict']:28s} monotone={e['monotone']}")
    L.append("\nForward-return by band (full sample):")
    for sig, e in report["signals"].items():
        L.append(f"  [{sig}]")
        for r in e["full"]:
            cols = "  ".join(f"{k}={r[k]}" for k in r if k not in ("band",))
            L.append(f"     {r['band']:16s} {cols}")
    if report.get("risk_drawdown"):
        rd = report["risk_drawdown"]
        L.append(f"\nRISK INDEX as a drawdown gauge: {rd['verdict']} "
                 f"(rank_trend={rd['rank_trend']})")
        L.append("  forward drawdown by risk band (full sample):")
        for r in rd["full"]:
            cols = "  ".join(f"{k}={r[k]}" for k in r if k not in ("band",))
            L.append(f"     {r['band']:10s} {cols}")
    _cb = next(iter(report["allocation"].values()), {}).get("cost_bps", 0)
    L.append(f"\nALLOCATION BACKTEST vs HODL (NET of {_cb}bps one-way cost):")
    for v, m in report["allocation"].items():
        L.append(f"  {v:13s} CAGR {m['cagr']:>6}% net (gross {m.get('cagr_gross')}%, "
                 f"drag {m.get('cost_drag_pp')}pp; HODL {m['hodl_cagr']}%)  "
                 f"Sharpe {m['sharpe']} (HODL {m['hodl_sharpe']})  "
                 f"MaxDD {m['maxdd']}% (HODL {m['hodl_maxdd']}%)  "
                 f"inMkt {m['time_in_market']}%  turn {m.get('turnover_annual')}x/yr  "
                 f"xHODL {m['final_vs_hodl']}")
    mt = report.get("multiple_testing")
    if mt and mt.get("dsr") is not None:
        L.append(f"\nDEFLATED SHARPE [{mt['selected_variant']}]: DSR={mt['dsr']}  "
                 f"(SR {mt['sr_annual']} ann vs haircut SR0 {mt['sr0_annual']} ann; "
                 f"N={mt['n_trials']} trials, T={mt['T']}d, skew={mt['skew']}, kurt={mt['kurt']})")
        L.append(f"  => {mt['verdict']}")
    L.append("\nWHIPSAW (state flips < max_days):")
    for s, w in report["whipsaw"].items():
        L.append(f"  {s:18s} {w['changes']:4d} changes, {w['pct']}% whipsaw")
    cv = report.get("cross_validation")
    if cv:
        robust = [s for s, v in cv["signals"].items() if v["robust"]]
        L.append(f"\nPURGED WALK-FORWARD CV ({cv['k_folds']} folds, {cv['embargo_days']}d embargo): "
                 f"{cv['n_robust']}/{len(cv['signals'])} signals robust (leak-free, no fold flip)")
        L.append(f"  robust: {', '.join(robust) if robust else '(none — single signals are weak at the fold level on ~3 cycles)'}")
    pc = report.get("probability_calibration")
    if pc:
        L.append(f"\nPROBABILITY CALIBRATION (OOF, {pc['horizon']}d direction): Brier {pc['brier']} vs "
                 f"base {pc['base_brier']} (skill {pc['skill_score']}); Platt a={pc['platt'].get('a')} "
                 f"b={pc['platt'].get('b')} — near-coin-flip, odds ~calibrated, ~0 skill (honest).")
    co = report.get("collinearity")
    if co and co.get("top_pairs"):
        tp = co["top_pairs"][0]
        L.append(f"\nCOLLINEARITY: {len(co['redundant'])} signals VIF≥5 (redundant); "
                 f"worst pair {tp['a']}~{tp['b']} r={tp['corr']} — the cost-basis cluster is triple-counted.")
    ab = report.get("allocation_bootstrap")
    if ab:
        L.append(f"\nBOOTSTRAP CI [{ab['variant']}]: Sharpe {ab['sharpe_ci'][1]} "
                 f"95%CI[{ab['sharpe_ci'][0]}, {ab['sharpe_ci'][2]}]  MaxDD {ab['maxdd_ci_pct'][1]}% "
                 f"[{ab['maxdd_ci_pct'][2]}, {ab['maxdd_ci_pct'][0]}]  P(Sharpe>0)={ab['sharpe_gt0_prob']}")
    ep = report.get("ensemble_promotion")
    if ep and ep.get("net_sharpe"):
        L.append(f"\nENSEMBLE CAPSTONE ({ep['horizon']}d): {ep['verdict']}")
        for name, t in ep["net_sharpe"].items():
            legs = " ".join(f"{hf} {t.get(hf)}" for hf in ("pre", "post"))
            L.append(f"  net Sharpe [{name:13s}] full {t.get('full')}  ({legs})")
        L.append(f"  ensemble OOF-IC {ep['ensemble_ic']} · best-single axis = {ep['best_single']}")
    return "\n".join(L)


def _write_markdown(report: dict) -> None:
    m = report["meta"]
    lines = [f"# Bitcoin Vector — calibration report",
             "",
             f"Span: {m['span']} ({m['rows']} days). Split-half boundary: {m['split']}.",
             "",
             "House rule: a signal is trusted (labeled a *signal* in the UI) only if its "
             "forward outcome relationship trends in the expected direction in the full "
             "sample AND survives both halves (rank-trend |rho|>0.6, tolerant of one "
             "small-sample band). Return-predicting signals (momentum, structure, BFI) "
             "are judged on forward RETURN; the Risk Index is judged on forward DRAWDOWN "
             "(its actual job) because at long horizons extreme risk marks capitulation "
             "and forward *return* is U-shaped — the documented contrarian behavior, not "
             "a defect. Anything failing is context-only; anything inverted is flagged.",
             ""]
    lines.append("## Signal verdicts\n")
    lines.append("| Signal | Verdict | full | pre | post | want |")
    lines.append("|---|---|--:|--:|--:|--:|")
    for sig, e in report["signals"].items():
        mo = e["monotone"]
        lines.append(f"| {sig} | **{e['verdict']}** | {mo['full']} | {mo['pre']} "
                     f"| {mo['post']} | {mo['want']} |")
    if report.get("risk_drawdown"):
        rd = report["risk_drawdown"]
        lines.append(f"\n## Risk Index as a drawdown gauge\n")
        lines.append(f"**{rd['verdict']}** — rank-trend {rd['rank_trend']}.\n")
        lines.append(pd.DataFrame(rd["full"]).to_markdown(index=False))
    for sig, e in report["signals"].items():
        lines.append(f"\n### {sig} — forward returns by band (full sample)\n")
        t = pd.DataFrame(e["full"])
        lines.append(t.to_markdown(index=False))
    _cb = next(iter(report["allocation"].values()), {}).get("cost_bps", 0)
    lines.append(f"\n## Allocation backtest vs HODL (NET of {_cb}bps one-way cost)\n")
    lines.append(f"`cagr` is net of transaction cost (the honest headline); `cagr_gross` "
                 f"and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way "
                 f"turnover/yr driving it.\n")
    cols = ["cagr", "cagr_gross", "cost_drag_pp", "hodl_cagr", "sharpe", "hodl_sharpe",
            "sortino", "hodl_sortino", "maxdd", "hodl_maxdd", "time_in_market",
            "turnover_annual", "final_vs_hodl"]
    at = pd.DataFrame(report["allocation"]).T
    at = at[[c for c in cols if c in at.columns]]
    lines.append(at.to_markdown())
    ab = report.get("allocation_bootstrap")
    if ab:
        lines.append(f"\n**Block-bootstrap 95% CI** [{ab['variant']}, {ab['B']} resamples, "
                     f"{ab['block']}d blocks]: Sharpe **{ab['sharpe_ci'][1]}** "
                     f"[{ab['sharpe_ci'][0]}, {ab['sharpe_ci'][2]}] · MaxDD {ab['maxdd_ci_pct'][1]}% "
                     f"[{ab['maxdd_ci_pct'][2]}, {ab['maxdd_ci_pct'][0]}] · P(Sharpe>0) {ab['sharpe_gt0_prob']}. "
                     f"{ab['note']}")
    cv = report.get("cross_validation")
    if cv:
        lines.append("\n## Purged walk-forward CV (stability gate)\n")
        lines.append(f"{cv['n_robust']}/{len(cv['signals'])} signals **robust** under "
                     f"{cv['k_folds']} embargoed folds ({cv['embargo_days']}d embargo = max horizon). "
                     f"{cv['note']}\n")
        lines.append("| Signal | full | folds | want | robust |")
        lines.append("|---|--:|---|--:|:-:|")
        for s, v in cv["signals"].items():
            lines.append(f"| {s} | {v['full']:+d} | {v['folds']} | {v['want']:+d} | "
                         f"{'✅' if v['robust'] else '·'} |")
    pc = report.get("probability_calibration")
    if pc:
        lines.append("\n## Probability calibration of the conviction layer (out-of-fold)\n")
        lines.append(f"OOF {pc['horizon']}d direction: **Brier {pc['brier']}** vs base "
                     f"{pc['base_brier']} (skill {pc['skill_score']}); Platt a={pc['platt'].get('a')}, "
                     f"b={pc['platt'].get('b')}. {pc['note']}\n")
        lines.append("| prob bin | n | predicted | observed |")
        lines.append("|---|--:|--:|--:|")
        for r in pc.get("reliability", []):
            lines.append(f"| {r['bin']} | {r['n']} | {r['pred']} | {r['obs']} |")
    co = report.get("collinearity")
    if co:
        lines.append("\n## Signal collinearity (orthogonalize before any blend)\n")
        lines.append(f"{len(co['redundant'])} signals with **VIF≥5** (redundant): "
                     f"{', '.join(co['redundant'])}. {co['note']}\n")
        lines.append("| a | b | \\|corr\\| |")
        lines.append("|---|---|--:|")
        for p in co.get("top_pairs", []):
            lines.append(f"| {p['a']} | {p['b']} | {p['corr']} |")
    mt = report.get("multiple_testing")
    if mt and mt.get("dsr") is not None:
        lines.append("\n## Deflated Sharpe Ratio (multiple-testing haircut)\n")
        lines.append(f"**{mt['verdict']}** — shipped variant `{mt['selected_variant']}`.\n")
        lines.append(f"- DSR — P(true Sharpe > 0) after deflation: **{mt['dsr']}**")
        lines.append(f"- Observed Sharpe {mt['sr_annual']} ann ({mt['sr_daily']}/day); "
                     f"haircut threshold SR0 {mt['sr0_annual']} ann")
        lines.append(f"- N={mt['n_trials']} trials (upper-bound) · T={mt['T']}d · "
                     f"skew={mt['skew']} · kurt={mt['kurt']} · SR-variance: {mt['sr_variance_source']}")
        lines.append(f"\n> {mt['note']}")
    tl = report.get("trial_log")
    if tl:
        lines.append("\n## Trial log\n")
        lines.append(f"As-of {tl['asof']}: **{tl['n_trials_declared']}** declared independent "
                     f"trials (upper-bound); {tl['n_signal_families']} signal families screened; "
                     f"allocation variants: {', '.join(tl['allocation_variants_tested'])}; "
                     f"transaction cost {tl['cost_bps_one_way']}bps one-way.")
    ep = report.get("ensemble_promotion")
    if ep and ep.get("net_sharpe"):
        lines.append("\n## Ensemble capstone — does combining beat the heuristic?\n")
        lines.append(f"**{ep['verdict']}**\n")
        lines.append(ep["note"] + "\n")
        ns = ep["net_sharpe"]
        lines.append("| read | net Sharpe full | pre-2021 | post-2021 |")
        lines.append("|---|--:|--:|--:|")
        for name in ("ensemble_eqw", "best_single", "heuristic"):
            t = ns.get(name, {})
            lines.append(f"| {name} | {t.get('full')} | {t.get('pre')} | {t.get('post')} |")
        lines.append(f"\nEnsemble OOF rank-IC vs {ep['horizon']}d return: **{ep['ensemble_ic']}** "
                     f"(best single axis = `{ep['best_single']}`). Per-axis IC: "
                     f"{', '.join(f'{k} {v}' for k, v in ep['axis_ic'].items())}.")
    lines.append("\n## Whipsaw\n")
    wt = pd.DataFrame(report["whipsaw"]).T
    lines.append(wt.to_markdown())
    Path(config.load()["storage"]["reports_dir"], "vector-calibration.md").write_text(
        "\n".join(lines))


def refresh_trial_log(root=None) -> dict:
    """Surgical trial-log refresh (W5) — rebuilds the trial_log dict from the existing
    calibration.json + current config WITHOUT re-running any backtests.

    Reads:
      - data/vector/calibration.json  (allocation variant names, signal family list)
      - data/vector/trial_log.json    (existing asof date — left untouched)
    Uses:
      - current config (vector.calibration.{cost_bps, n_trials} + vector.overrides)
    Writes ONLY data/vector/trial_log.json (calibration.json and signals.parquet are
    never touched). Also mirrors the declared budget into the persistent TrialLedger.

    Returns the new trial_log dict.
    """
    from datetime import date as _date
    outdir = (Path(root) if root is not None else config.data_dir()) / "vector"
    cal_path = outdir / "calibration.json"
    tl_path = outdir / "trial_log.json"

    with cal_path.open(encoding="utf-8") as fh:
        cal = json.load(fh)
    with tl_path.open(encoding="utf-8") as fh:
        old_tl = json.load(fh)

    cfg = config.load()["vector"]["calibration"]
    cost_bps = float(cfg.get("cost_bps", 10.0))
    n_trials = int(cfg.get("n_trials", 50))
    dof = _override_dof(config.load()["vector"])
    n_declared = n_trials + sum(dof.values())

    alloc_variants = list(cal.get("allocation", {}).keys())
    sig_families = sorted(cal.get("signals", {}).keys())
    n_sig = len(sig_families)

    # Mirror declared budget into the persistent ledger (idempotent).
    _led = TrialLedger()
    _led.log_declared_budget(
        n_declared,
        family="vector",
        reason=(
            f"cfg.calibration.n_trials ({n_trials}) + override dof_cost {dof} — "
            "declared upper-bound (calibrate_vector W5)"
        ),
    )

    new_tl = {
        "asof": old_tl.get("asof"),          # data as-of date: unchanged
        "n_trials_config": n_trials,
        "overrides_dof": dof,
        "n_trials_declared": n_declared,
        "cost_bps_one_way": cost_bps,
        "allocation_variants_tested": alloc_variants,
        "signal_families_screened": sig_families,
        "n_signal_families": n_sig,
        "fdr_note": (
            "The 32-family band-edge screen is a multiple-comparison surface — at screen "
            "strength expect ~1-2 spuriously CONFIRMED families out of 32 under the null. "
            "Verdicts are hypothesis-generating only and should be treated as directional "
            "priors, not causal proofs. Sizing authority flows solely through the DSR-gated "
            "allocation backtest, whose N these signal families inflate via n_trials."
        ),
        "note": old_tl.get(
            "note",
            "Point-in-time trial ledger (overwritten each run). n_trials_declared is "
            "an upper-bound count of independent strategy configs explored across the "
            "hunt, used to deflate the headline Sharpe. Raise it as you try more.",
        ),
        "refreshed_on": _date.today().isoformat(),
        "refresh_note": (
            "Surgical refresh (W5): declared trial budget + override dof only; "
            "backtest-derived numbers untouched — the full dual (raw+final) recompute "
            "lands in W1."
        ),
    }
    tl_path.write_text(json.dumps(new_tl, indent=2, default=str))
    return new_tl


if __name__ == "__main__":
    import argparse as _argparse

    _parser = _argparse.ArgumentParser(description="Bitcoin Vector calibration")
    _parser.add_argument(
        "--trial-log-only",
        action="store_true",
        help=(
            "Surgical refresh (W5): rebuild data/vector/trial_log.json from the "
            "existing calibration.json + current config without re-running backtests."
        ),
    )
    _args = _parser.parse_args()
    if _args.trial_log_only:
        result = refresh_trial_log()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)
    sys.exit(main())
