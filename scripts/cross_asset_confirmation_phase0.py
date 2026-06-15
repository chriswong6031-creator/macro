"""Cross-Asset Confirmation — Phase-0 honesty gate.

The macro "Risk appetite" card now shows a cross-asset CONFIRMATION tally: how many
of the 7 signed RORO legs (VIX, HY, SKEW, vol-term, NFCI, copper/gold, DXY) agree on
the dominant risk direction, and which dissent. It ships DISPLAY-ONLY. This script
asks the only question that could justify promoting it to a SCORED signal:

  Does cross-asset NON-CONFIRMATION (leg dispersion / dissent) predict forward
  EQUITY DRAWDOWN — and does it do so INCREMENTALLY, beyond what the composite RORO
  level and VIX already tell us?

Method (PIT-causal signal; the legs are causal rolling z-scores from conditions_frame):
  - features (non-confirmation): disp = std of legs, rng = max-min, frac_opp =
    fraction of legs opposing the mean's sign, worst = -min(leg).
  - baselines / confounds: roro level, |roro| (extremeness), vix_z.
  - forward outcomes from SPY: fwd_maxloss_H = min cumulative return over the next H
    days (drawdown proxy), fwd_ret_H = H-day forward return. H in {21,63,126}.
  - Spearman IC with a HAC (Newey-West, lag=H) t-stat for the overlapping windows.
  - PARTIAL Spearman of each feature given [roro, |roro|, vix_z] — the decisive test.
  - Benjamini-Hochberg FDR across the whole screen; first/second-half sign stability.
  - A causal de-risk strategy from dispersion, DSR'd, HORSE-RACED against the identical
    strategy driven by VIX (if dispersion-derisk ~ VIX-derisk, dispersion adds nothing).

Writes reports/cross-asset-confirmation-phase0.md. Run:
  python -m scripts.cross_asset_confirmation_phase0
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.conditions import conditions_frame
from engine.inputs import build_features
from engine.validation import (backtest_core, benjamini_hochberg, deflated_sharpe,
                               dsr_verdict, newey_west_tstat, ret_moments)
from lib import config

TY = 252
LEG_KEYS = ["vix", "hy_oas", "skew", "vix_term", "nfci", "copper_gold", "dxy"]
HORIZONS = [21, 63, 126]


# --- causal helpers ----------------------------------------------------------
def _czelle(s: pd.Series, win: int = 252) -> pd.Series:
    """Causal expanding-capped rolling z (no look-ahead)."""
    m = s.rolling(win, min_periods=60).mean()
    sd = s.rolling(win, min_periods=60).std()
    return (s - m) / sd.replace(0, np.nan)


def _zr(s: pd.Series) -> pd.Series:
    r = s.rank()
    return (r - r.mean()) / (r.std(ddof=0) or np.nan)


def _spear_hac(x: pd.Series, y: pd.Series, lags: int) -> dict:
    """Full-sample Spearman IC + HAC t (mean of the product of z-scored ranks IS the
    rank correlation; its Newey-West mean-t corrects for the overlapping windows)."""
    d = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(d) < 40:
        return {"ic": None, "t": None, "p": None, "n": len(d)}
    g = _zr(d["x"]) * _zr(d["y"])
    nw = newey_west_tstat(g, lags=lags)
    return {"ic": round(float(g.mean()), 4), "t": nw["t"], "p": nw["p"], "n": len(d)}


def _partial_spear_hac(x: pd.Series, y: pd.Series, basis: list[pd.Series], lags: int) -> dict:
    """Partial Spearman of x,y controlling for `basis`: rank everything, OLS-residualize
    rank(x) and rank(y) on the rank(basis)+const, correlate the residuals (HAC t)."""
    cols = {"x": x, "y": y, **{f"z{i}": b for i, b in enumerate(basis)}}
    d = pd.concat([s.rename(n) for n, s in cols.items()], axis=1).dropna()
    if len(d) < 60:
        return {"pic": None, "t": None, "p": None, "n": len(d)}
    Z = np.column_stack([np.ones(len(d))] + [d[f"z{i}"].rank().values for i in range(len(basis))])

    def _resid(col: str) -> np.ndarray:
        yv = d[col].rank().values
        beta, *_ = np.linalg.lstsq(Z, yv, rcond=None)
        return yv - Z @ beta

    rx, ry = _resid("x"), _resid("y")
    zx = (rx - rx.mean()) / (rx.std() or np.nan)
    zy = (ry - ry.mean()) / (ry.std() or np.nan)
    g = pd.Series(zx * zy, index=d.index)
    nw = newey_west_tstat(g, lags=lags)
    return {"pic": round(float(g.mean()), 4), "t": nw["t"], "p": nw["p"], "n": len(d)}


def _fwd_maxloss(spy: pd.Series, H: int) -> pd.Series:
    """min cumulative return over the next H days = worst buy-at-t / hold-<=H loss."""
    fwd_min = spy.shift(-1)[::-1].rolling(H, min_periods=H).min()[::-1]
    return fwd_min / spy - 1.0


def _fwd_ret(spy: pd.Series, H: int) -> pd.Series:
    return spy.shift(-H) / spy - 1.0


def _strat(spy: pd.Series, trigger_z: pd.Series, thr: float = 1.0) -> dict:
    """Causal de-risk overlay: hold SPY (alloc 1) unless the trigger z-score is above
    `thr` (then go to cash), vs buy&hold. Trigger is shifted 1d (act on yesterday)."""
    alloc = (trigger_z.shift(1) <= thr).astype(float).reindex(spy.index).fillna(1.0)
    bt = backtest_core(spy, alloc, cost_bps=2.0)
    net, hold = bt["net"].dropna(), bt["hold"].dropna()

    def sh(r):
        return float(r.mean() / r.std() * np.sqrt(TY)) if len(r) and r.std() else float("nan")

    def mdd(r):
        eq = (1 + r).cumprod()
        return float((eq / eq.cummax() - 1).min()) if len(eq) else float("nan")

    return {"sharpe": round(sh(net), 2), "bh_sharpe": round(sh(hold), 2),
            "maxdd": round(100 * mdd(net), 1), "bh_maxdd": round(100 * mdd(hold), 1),
            "net": net, "days_in_cash_pct": round(100 * float((alloc == 0).mean()), 1)}


def main() -> int:
    f = build_features()
    cf = conditions_frame(f)
    legs = pd.DataFrame({k: cf.get(f"roro_{k}") for k in LEG_KEYS
                         if f"roro_{k}" in cf.columns}).dropna(how="all")
    present = list(legs.columns)
    spy = f["SPY"].reindex(cf.index) if "SPY" in f.columns else None
    if spy is None or len(present) < 5:
        print("[conf phase0] insufficient data (SPY or legs missing)"); return 1

    # --- non-confirmation features (all from the signed legs) ---
    mean = legs.mean(axis=1)
    feats = {
        "disp": legs.std(axis=1),                                   # cross-leg dispersion
        "rng": legs.max(axis=1) - legs.min(axis=1),                 # leg spread
        "frac_opp": legs.apply(lambda r: np.mean(np.sign(r.dropna()) != np.sign(r.dropna().mean()))
                               if r.dropna().size else np.nan, axis=1),
        "worst": -legs.min(axis=1),                                 # most risk-off leg
    }
    # baselines / confounds
    roro = mean.rename("roro")
    base = {"roro": roro, "absroro": roro.abs(), "vix_z": _czelle(f["vix"]).reindex(cf.index)}

    outcomes = {}
    for H in HORIZONS:
        outcomes[f"maxloss_{H}"] = _fwd_maxloss(spy, H)
        outcomes[f"ret_{H}"] = _fwd_ret(spy, H)

    n = int(pd.concat([legs, spy], axis=1).dropna().shape[0])
    span = f"{cf.index.min().date()}→{cf.index.max().date()}"
    print(f"[conf phase0] legs={present} | n~{n} | {span}")

    # --- univariate IC screen (feature x outcome) ---
    rows, pvals = [], {}
    for fn, fs in feats.items():
        for H in HORIZONS:
            for kind in ("maxloss", "ret"):
                y = outcomes[f"{kind}_{H}"]
                r = _spear_hac(fs, y, lags=H)
                key = f"{fn}|{kind}_{H}"
                rows.append((key, r))
                if r["p"] is not None:
                    pvals[key] = r["p"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    n_surv = sum(1 for v in fdr.values() if v["reject"])

    # --- DECISIVE: partial IC vs forward 63d maxloss, controlling for roro,|roro|,vix ---
    yprimary = outcomes["maxloss_63"]
    partial = {}
    for fn, fs in feats.items():
        uni = _spear_hac(fs, yprimary, lags=63)
        par = _partial_spear_hac(fs, yprimary, [base["roro"], base["absroro"], base["vix_z"]], lags=63)
        partial[fn] = {"uni": uni, "par": par}

    # baselines' OWN univariate skill on the same target (the bar to beat)
    base_ic = {bn: _spear_hac(bs, yprimary, lags=63) for bn, bs in base.items()}

    # --- split-half sign stability for the primary feature (disp vs maxloss_63) ---
    dd = pd.concat([feats["disp"].rename("x"), yprimary.rename("y")], axis=1).dropna()
    mid = dd.index[len(dd) // 2]
    h1 = _spear_hac(dd.loc[:mid, "x"], dd.loc[:mid, "y"], lags=63)
    h2 = _spear_hac(dd.loc[mid:, "x"], dd.loc[mid:, "y"], lags=63)

    # --- tradable horse-race: dispersion-derisk vs VIX-derisk vs |roro|-derisk ---
    disp_z = _czelle(feats["disp"])
    st_disp = _strat(spy, disp_z)
    st_vix = _strat(spy, base["vix_z"])
    st_absr = _strat(spy, _czelle(roro.abs()))
    mom = ret_moments(st_disp["net"])
    N_TRIALS = len(rows)                  # honest screen count (features×horizons×outcomes)
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], N_TRIALS, trading_year=TY) if mom else None

    # --- verdict logic ---
    par_survivor = any((p["par"]["p"] is not None and p["par"]["p"] < 0.05
                        and p["par"]["pic"] is not None and abs(p["par"]["pic"]) > 0.03)
                       for p in partial.values())
    splithalf_ok = (h1["ic"] is not None and h2["ic"] is not None
                    and np.sign(h1["ic"]) == np.sign(h2["ic"]))
    beats_vix = (st_disp["maxdd"] > st_vix["maxdd"] + 1.0) and (st_disp["sharpe"] >= st_vix["sharpe"])
    dsr_ok = bool(dsr and dsr["dsr"] >= 0.90)
    GO = bool(par_survivor and splithalf_ok and dsr_ok and beats_vix)
    verdict = ("SCORED-CANDIDATE — incremental skill survives confound control, FDR, "
               "split-half and DSR, and beats a plain VIX de-risk"
               if GO else
               "DISPLAY-ONLY — does not show INCREMENTAL drawdown-prediction skill beyond "
               "the RORO level / VIX; keep it as a legibility read, never scored")

    # --- report ---
    def fic(r):
        v = r.get('ic', r.get('pic'))
        return (f"{v:+.3f}" if v is not None else "—") + \
               (f" (t={r['t']}, p={r['p']})" if r.get('t') is not None else "")

    md = ["# Cross-Asset Confirmation — Phase-0 honesty gate", "",
          f"*Does cross-asset NON-CONFIRMATION (dispersion/dissent across the 7 signed "
          f"RORO legs) predict forward EQUITY DRAWDOWN — incrementally, beyond the RORO "
          f"level and VIX? Legs: {', '.join(present)}. n~{n}, {span}. PIT-causal signal; "
          f"HAC(lag=H) t-stats; the forward windows overlap.*", "",
          f"### Verdict: {verdict}", "",
          "## 1. Decisive test — PARTIAL IC vs forward-63d max-loss",
          "*(controlling for RORO level, |RORO|, VIX z. If the partial collapses toward "
          "zero, the feature is just a stress proxy.)*", "",
          "| feature | univariate IC | PARTIAL IC (given roro,|roro|,vix) |",
          "|---|---|---|"]
    for fn, p in partial.items():
        md.append(f"| {fn} | {fic(p['uni'])} | **{fic(p['par'])}** |")
    md += ["", "_Baselines' own univariate skill on the same target (the bar):_ "
           + " · ".join(f"{bn} {fic(r)}" for bn, r in base_ic.items()), "",
           "## 2. Full IC screen + Benjamini-Hochberg FDR (α=0.10)", "",
           f"{n_surv}/{len(pvals)} feature×outcome tests survive FDR.", "",
           "| feature\\|outcome | IC | t (HAC) | p | q (BH) | reject |",
           "|---|---|---|---|---|---|"]
    for key, r in rows:
        q = fdr.get(key, {})
        md.append(f"| {key} | {r['ic'] if r['ic'] is not None else '—'} | {r.get('t')} | "
                  f"{r.get('p')} | {q.get('q','—')} | {'✅' if q.get('reject') else '—'} |")
    md += ["", "## 3. Split-half sign stability (disp → maxloss_63)", "",
           f"- 1st half IC: {fic(h1)}", f"- 2nd half IC: {fic(h2)}",
           f"- same sign: {'YES' if splithalf_ok else 'NO'}", "",
           "## 4. Tradable horse-race — de-risk overlay (cash when trigger z>1), 2bps", "",
           "| trigger | Sharpe | B&H Sharpe | MaxDD% | B&H MaxDD% | days in cash |",
           "|---|---|---|---|---|---|",
           f"| **dispersion** | {st_disp['sharpe']} | {st_disp['bh_sharpe']} | {st_disp['maxdd']} | "
           f"{st_disp['bh_maxdd']} | {st_disp['days_in_cash_pct']}% |",
           f"| VIX | {st_vix['sharpe']} | {st_vix['bh_sharpe']} | {st_vix['maxdd']} | "
           f"{st_vix['bh_maxdd']} | {st_vix['days_in_cash_pct']}% |",
           f"| \\|RORO\\| | {st_absr['sharpe']} | {st_absr['bh_sharpe']} | {st_absr['maxdd']} | "
           f"{st_absr['bh_maxdd']} | {st_absr['days_in_cash_pct']}% |", "",
           f"- dispersion-derisk **beats VIX-derisk** (lower MaxDD & ≥ Sharpe): "
           f"{'YES' if beats_vix else 'NO'}",
           f"- Deflated Sharpe (dispersion overlay): {dsr['dsr'] if dsr else '—'} "
           f"at n_trials={N_TRIALS} → {dsr_verdict(dsr['dsr']) if dsr else '—'}", "",
           "## Honesty notes", "",
           "- The signal is PIT-causal (rolling-z legs); association ICs are full-sample "
           "rank correlations — standard for screening, not a tradable claim.",
           "- The de-risk overlay IS causal (trigger shifted 1d) and after 2bps.",
           "- Dispersion co-moves with stress, so a univariate hit is EXPECTED and not "
           "evidence of a new edge — only the PARTIAL IC and the VIX horse-race are.",
           "", "*Run: `python -m scripts.cross_asset_confirmation_phase0`*"]
    out = config.ROOT / "reports" / "cross-asset-confirmation-phase0.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md))

    print(f"[conf phase0] FDR survivors {n_surv}/{len(pvals)} | partial-survivor={par_survivor} "
          f"| splithalf={'ok' if splithalf_ok else 'no'} | disp-derisk MaxDD {st_disp['maxdd']} vs "
          f"VIX {st_vix['maxdd']} | DSR {dsr['dsr'] if dsr else '—'} | {'GO' if GO else 'DISPLAY-ONLY'}")
    print(f"[conf phase0] → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
