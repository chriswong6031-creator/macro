"""Backtest-TRAINING + signal-strength calibration for the thematic-basket SIGNALS.

The thematic-basket subsystem emits per-theme LABELS (emerging / dominant / fading /
deteriorating), RECOs (enter / accumulate / hold / trim / avoid) and discrete ALERTS
(engine.theme_alerts). Every firing threshold in engine.theme_scoring / engine.basket_score
is HAND-SET and has never been measured against the forward outcome it implicitly claims.
This script TRAINS those signals against history — not to manufacture return alpha (the
honest prior is that cross-sectional theme momentum has rank-IC ~= 0; the one measured edge
is the absolute-trend gate as DRAWDOWN control), but to answer the questions that make a
signal worth surfacing and to calibrate WHEN it should fire:

  * does LABEL=emerging actually precede forward RELATIVE outperformance? (continuation)
  * does LABEL=fading / topping actually precede a forward DRAWDOWN? (the risk call)
  * is a fired signal's confidence calibrated — when we say "high risk", is the realised
    drawdown rate actually high? (the "needle-pinpoint accuracy of signal appearance")

PIT REALITY: the live signal archive (engine.signal_archive) is only days deep, so we do
NOT backtest archived signals. We RE-DERIVE the live signal point-in-time from the price
tape, on two universes (mirrors scripts/thematic_rotation_phase0.py):

  proxy   the 9-11 SPDR sector ETFs, ~27y daily, multi-cycle, survivorship-light. The
          CLEAN substrate that drives every GO/NO-GO. emerging/fading are breadth-free and
          reproduce FAITHFULLY here (engine.theme_scoring._label); dominant/deteriorating
          use a documented PANEL-breadth proxy and are secondary.
  live    the 25 US theme baskets, ~3y, HINDSIGHT-curated. Full-fidelity labels (real
          member breadth) but severely underpowered — DESCRIPTIVE context, never a gate.

Validation is the house toolkit (engine.validation): Newey-West HAC t on every event-study
CAR (overlapping forward windows serially correlate), Benjamini-Hochberg FDR across the
panel of signals tested, and Brier/Platt reliability to calibrate the firing-confidence.

Usage:  python -m scripts.calibrate_baskets [--live]
Writes: data/strategies/baskets_calibration.json  (+ prints the tables)
Additive / never fatal.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V              # noqa: E402
from engine.trial_ledger import TrialLedger     # noqa: E402
from engine.group_flow import _causal_z         # noqa: E402
from engine.indicators import pct_rank_window    # noqa: E402
from engine.theme_scoring import _label, _reco, WEIGHTS  # noqa: E402
from lib import config                           # noqa: E402
from scripts.thematic_rotation_phase0 import _adj, REGION_SECTORS, sector_prices  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("calibrate_baskets")

# horizons + sampling. STEP de-overlaps the event panel a bit; HAC mops up the rest.
FWD_H = (21, 63)                  # forward windows (1m / 3m trading days)
STEP = 5                          # sample every 5 trading days (de-overlap)
RS_WIN, Z_LB = 20, 252            # match group_flow rs_window_d / z_lookback_d
DD_RISK = -0.08                   # "a drawdown worth warning about" = >8% peak-to-trough
HAC_FLOOR_T = 2.0                 # |HAC t| bar to call an outcome measurably non-zero
BH_Q = 0.10                       # Benjamini-Hochberg FDR across the signal panel


def _tanh(x: float, k: float) -> float:
    return float(np.tanh(k * x))


# --------------------------------------------------------------------------- #
# PIT feature construction on a single basket/sector level series (no member
# data needed — exactly the legs group_flow.prep_group derives from lvl & bench)
# --------------------------------------------------------------------------- #
def _rs_features(lvl: pd.Series, bench: pd.Series) -> dict:
    """accel_z, rs_pctile and the 5/20/60d RELATIVE returns + delta_5d for a level
    series vs its benchmark — the breadth-free inputs to engine.theme_scoring._label,
    all CAUSAL (no look-ahead), aligned on lvl's index."""
    rs = (lvl / bench).reindex(lvl.index)
    rs_chg = rs.pct_change(RS_WIN, fill_method=None)
    accel_z = _causal_z(rs_chg - rs_chg.shift(RS_WIN), Z_LB)
    rs_pctile = pct_rank_window(rs, Z_LB)
    # relative return over h days = basket h-return minus bench h-return
    rel = {h: lvl.pct_change(h, fill_method=None) - bench.pct_change(h, fill_method=None)
           for h in (5, 20, 60)}
    # delta_5d MUST match engine.theme_scoring (compute_theme_intel:452): it passes the
    # single 5d RELATIVE return as delta_5d, and _label reads `falling = delta_5d < 0`
    # (i.e. 'underperformed over the last 5d'), NOT a 5d change-of-the-5d-read.
    return {"accel_z": accel_z, "rs_pctile": rs_pctile,
            "r5": rel[5], "r20": rel[20], "r60": rel[60], "delta_5d": rel[5]}


def _panel_breadth(P: pd.DataFrame) -> pd.DataFrame:
    """Market-breadth read across the sector PANEL — % above 50/200d MA and net new
    52w highs-lows. The documented stand-in for intra-basket member breadth on the
    proxy (a sector ETF has no members). Same value broadcast to every sector that day."""
    ma50 = P.rolling(50, min_periods=25).mean()
    ma200 = P.rolling(200, min_periods=100).mean()
    pct50 = (P > ma50).where(P.notna() & ma50.notna()).mean(axis=1)
    pct200 = (P > ma200).where(P.notna() & ma200.notna()).mean(axis=1)
    roll_hi = P.rolling(252, min_periods=60).max()
    roll_lo = P.rolling(252, min_periods=60).min()
    nh = (P >= roll_hi * (1 - 1e-3)).sum(axis=1)
    nl = (P <= roll_lo * (1 + 1e-3)).sum(axis=1)
    n = P.notna().sum(axis=1).replace(0, np.nan)
    return pd.DataFrame({"pct50": pct50, "pct200": pct200,
                         "nh": nh, "nl": nl, "net_nh": (nh - nl) / n})


def _proxy_score(trend: float, breadth_leg: float, crowd_pen: float) -> int:
    """A conservative proxy of the 0-100 score for the dominant>=62 gate. Uses the
    breadth-free trend leg + panel-breadth leg + crowding penalty; impulse & macro legs
    have no faithful single-ETF analogue, so they are omitted (biases the proxy score
    LOW — proxy 'dominant' is therefore conservative; the live universe carries the
    full-fidelity dominant test)."""
    raw = WEIGHTS["trend"] * trend + WEIGHTS["breadth"] * breadth_leg - WEIGHTS["crowding"] * crowd_pen
    return int(round(50 + 50 * float(np.clip(raw, -1, 1))))


def _trend_leg(r5, r20, r60, accel_z) -> float:
    parts, wts = [], []
    if r5 is not None and np.isfinite(r5):
        parts.append(_tanh(r5, 12)); wts.append(0.25)
    if r20 is not None and np.isfinite(r20):
        parts.append(_tanh(r20, 8)); wts.append(0.35)
    if r60 is not None and np.isfinite(r60):
        parts.append(_tanh(r60, 5)); wts.append(0.20)
    if accel_z is not None and np.isfinite(accel_z):
        parts.append(_tanh(accel_z, 0.7)); wts.append(0.20)
    return float(np.clip(np.average(parts, weights=wts), -1, 1)) if parts else 0.0


def _breadth_leg(pct50, pct200, net_nh) -> float:
    if pct50 is None or not np.isfinite(pct50):
        return 0.0
    return float(np.clip(0.45 * (2 * pct50 - 1) + 0.25 * (2 * pct200 - 1) + 0.20 * net_nh, -1, 1))


def _crowd_pen(rs_p) -> float:
    return float(np.clip(0.5 * (rs_p - 0.8) / 0.2, 0, 1)) if (rs_p is not None and rs_p > 0.8) else 0.0


# --------------------------------------------------------------------------- #
# forward outcomes
# --------------------------------------------------------------------------- #
def _fwd_rel(lvl: np.ndarray, bench: np.ndarray, i: int, h: int) -> float:
    """Forward h-day RELATIVE return: basket minus benchmark, i -> i+h."""
    if i + h >= len(lvl):
        return np.nan
    return float((lvl[i + h] / lvl[i] - 1.0) - (bench[i + h] / bench[i] - 1.0))


def _fwd_dd(lvl: np.ndarray, i: int, h: int) -> float:
    """Forward h-day max ABSOLUTE drawdown of the basket level, i+1 .. i+h."""
    if i + h >= len(lvl):
        return np.nan
    seg = lvl[i + 1:i + 1 + h]
    return float(seg.min() / lvl[i] - 1.0) if len(seg) else np.nan


# --------------------------------------------------------------------------- #
# event study: pool every (series, day, label) and summarise the forward outcome
# --------------------------------------------------------------------------- #
def _event_study(events: dict, claim: dict) -> dict:
    """events: label -> list of (fwd_rel21, fwd_rel63, fwd_dd21, fwd_dd63, bar_i). For each
    label report the outcome it CLAIMS (continuation -> fwd rel; risk -> fwd dd). The HAC t
    is computed on the DAILY cross-sectional mean (one obs per bar) — the per-event pool
    co-moves within a day (the 11 sectors are correlated), so a pooled HAC corrects only the
    time-serial leg and OVERSTATES |t|. Effect sizes (medians, hit, P(dd<risk)) stay pooled."""
    out = {}
    pvals = {}
    for lab, rows in events.items():
        if len(rows) < 30:
            out[lab] = {"n": len(rows), "verdict": "thin"}
            continue
        a = np.array(rows, float)
        rel21, rel63, dd21, dd63, ev = a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]
        kind = claim.get(lab, "continuation")

        def _daily(metric):                   # collapse same-day sectors -> one obs/bar
            msk = np.isfinite(metric)
            if not msk.any():
                return np.array([])
            return pd.Series(metric[msk]).groupby(ev[msk]).mean().to_numpy()

        rec = {"n": int(len(a)), "n_days": int(len(np.unique(ev))),
               "rel21_med_pct": round(100 * float(np.nanmedian(rel21)), 2),
               "rel63_med_pct": round(100 * float(np.nanmedian(rel63)), 2),
               "dd21_med_pct": round(100 * float(np.nanmedian(dd21)), 2),
               "dd63_med_pct": round(100 * float(np.nanmedian(dd63)), 2),
               "p_dd21_lt_risk": round(float(np.nanmean(dd21 < DD_RISK)), 3),
               "kind": kind}
        if kind == "continuation":            # claim: forward relative return > 0
            nw = V.newey_west_tstat(_daily(rel21), lags=int(np.ceil(21 / STEP)))
            rec.update({"car_metric": "fwd_rel_21d", "mean_pct": round(100 * (nw["mean"] or 0), 2),
                        "t_hac": nw["t"], "p_hac": nw["p"], "hit": round(float(np.nanmean(rel21 > 0)), 3)})
            want_sign = 1
        else:                                 # claim: forward drawdown (more negative)
            nw = V.newey_west_tstat(_daily(dd21), lags=int(np.ceil(21 / STEP)))
            rec.update({"car_metric": "fwd_dd_21d", "mean_pct": round(100 * (nw["mean"] or 0), 2),
                        "t_hac": nw["t"], "p_hac": nw["p"], "hit": round(float(np.nanmean(dd21 < DD_RISK)), 3)})
            want_sign = -1
        rec["t_n"] = nw.get("n")
        t = rec.get("t_hac")
        signed_ok = t is not None and np.sign(rec["mean_pct"]) == want_sign and abs(t) >= HAC_FLOOR_T
        rec["measurable"] = bool(signed_ok)
        rec["verdict"] = ("measurable_edge" if signed_ok else "not_measurable")
        if rec.get("p_hac") is not None:
            pvals[lab] = rec["p_hac"]
        out[lab] = rec
    # FDR across the panel of labels tested
    bh = V.benjamini_hochberg(pvals, alpha=BH_Q) if pvals else {}
    for lab, q in bh.items():
        out[lab]["bh_q"] = q["q"]
        out[lab]["bh_reject"] = q["reject"]
    return out


# --------------------------------------------------------------------------- #
# PROXY universe — the GO/NO-GO substrate
# --------------------------------------------------------------------------- #
def run_proxy(region: str = "us") -> dict:
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)             # daily sector ETF panel
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    breadth = _panel_breadth(P)

    # per-sector PIT features
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}

    events: dict = {k: [] for k in ("emerging", "dominant", "fading", "deteriorating", "neutral")}
    ic_rows21, ic_rows63 = [], []                        # cross-sectional rank-IC
    # confidence-calibration accumulators (proxy risk-score & entry-score); _i = bar index
    # so the OOS folds + CI block on DATES, not i.i.d. rows.
    risk_p, risk_y, risk_i, entry_p, entry_y, entry_i = [], [], [], [], [], []
    # trend-gate -> drawdown re-confirm
    gate_above_dd, gate_below_dd = [], []

    spy_v = spy.to_numpy()
    idx = P.index
    bnp = {"pct50": breadth["pct50"].to_numpy(), "pct200": breadth["pct200"].to_numpy(),
           "nh": breadth["nh"].to_numpy(), "nl": breadth["nl"].to_numpy(),
           "net_nh": breadth["net_nh"].to_numpy()}

    for i in range(max(Z_LB, 200), len(idx) - max(FWD_H) - 1, STEP):
        # cross-sectional score snapshot for rank-IC
        day_scores, day_fwd21, day_fwd63 = {}, {}, {}
        for c, f in feats.items():
            px = P[c].to_numpy()
            if not np.isfinite(px[i]):
                continue
            accel_z = f["accel_z"].iloc[i]; rs_p = f["rs_pctile"].iloc[i]
            r5, r20, r60 = f["r5"].iloc[i], f["r20"].iloc[i], f["r60"].iloc[i]
            d5 = f["delta_5d"].iloc[i]
            accel_z = float(accel_z) if pd.notna(accel_z) else None
            rs_p = float(rs_p) if pd.notna(rs_p) else None
            if accel_z is None or rs_p is None:
                continue
            trend = _trend_leg(r5, r20, r60, accel_z)
            bl = _breadth_leg(bnp["pct50"][i], bnp["pct200"][i], bnp["net_nh"][i])
            cp = _crowd_pen(rs_p)
            score = _proxy_score(trend, bl, cp)
            fp = {"accel_z": accel_z, "rs_pctile": rs_p}
            perf = {"5d": {"rel": _f(r5)}, "20d": {"rel": _f(r20)}, "60d": {"rel": _f(r60)}}
            bdict = {"pct50": _f(bnp["pct50"][i]), "nh": int(bnp["nh"][i]), "nl": int(bnp["nl"][i])}
            lab = _label(score, fp, perf, bdict, _f(d5))

            fr21, fr63 = _fwd_rel(px, spy_v, i, 21), _fwd_rel(px, spy_v, i, 63)
            dd21, dd63 = _fwd_dd(px, i, 21), _fwd_dd(px, i, 63)
            if not np.isfinite(fr21):
                continue
            events[lab].append((fr21, fr63, dd21, dd63, i))
            day_scores[c] = score; day_fwd21[c] = fr21; day_fwd63[c] = fr63

            # trend gate (above/below 200d) -> forward drawdown
            ma200 = P[c].rolling(200, min_periods=100).mean().iloc[i]
            if pd.notna(ma200) and np.isfinite(dd21):
                (gate_above_dd if px[i] > ma200 else gate_below_dd).append(dd21)

            # ---- confidence proxies ----
            # RISK score: extended + decelerating + below short trend (proxy rollover)
            ma50 = P[c].rolling(50, min_periods=25).mean().iloc[i]
            below50 = bool(pd.notna(ma50) and px[i] < ma50)
            rscore = (min(max((rs_p - 0.6) / 0.4, 0), 1) * 0.40
                      + min(max(-accel_z / 1.0, 0), 1) * 0.35
                      + (0.25 if below50 else 0.0))
            if np.isfinite(dd21):
                risk_p.append(min(rscore, 1.0)); risk_y.append(1.0 if dd21 < DD_RISK else 0.0)
                risk_i.append(i)
            # ENTRY score: accelerating + not extended + above trend (proxy clean-entry)
            above200 = bool(pd.notna(ma200) and px[i] > ma200)
            escore = (min(max(accel_z / 1.0, 0), 1) * 0.40
                      + (0.30 if (rs_p is not None and rs_p < 0.75) else 0.0)
                      + (0.30 if above200 else 0.0))
            entry_p.append(min(escore, 1.0)); entry_y.append(1.0 if fr21 > 0 else 0.0)
            entry_i.append(i)

        if len(day_scores) >= 5:
            s = pd.Series(day_scores)
            ic_rows21.append(V.rank_ic(s, pd.Series(day_fwd21)))
            ic_rows63.append(V.rank_ic(s, pd.Series(day_fwd63)))

    claim = {"emerging": "continuation", "dominant": "continuation",
             "fading": "risk", "deteriorating": "risk", "neutral": "continuation"}
    labels = _event_study(events, claim)

    # rank-IC of the composite score
    ic21 = V.ic_summary([x for x in ic_rows21 if np.isfinite(x)], periods_per_year=252 // STEP)
    ic63 = V.ic_summary([x for x in ic_rows63 if np.isfinite(x)], periods_per_year=252 // STEP)

    # trend gate verdict
    gate = {}
    if len(gate_above_dd) >= 30 and len(gate_below_dd) >= 30:
        ga, gb = np.array(gate_above_dd), np.array(gate_below_dd)
        gate = {"above_dd21_med_pct": round(100 * float(np.median(ga)), 2),
                "below_dd21_med_pct": round(100 * float(np.median(gb)), 2),
                "shallower_when_above": bool(np.median(ga) > np.median(gb)),
                "n_above": len(ga), "n_below": len(gb)}

    # confidence calibration (Brier + reliability + Platt) and an OOS firing gate
    alert_risk = _calibrate_confidence(risk_p, risk_y, risk_i, "fwd_dd21<-8%")
    alert_entry = _calibrate_confidence(entry_p, entry_y, entry_i, "fwd_rel21>0")

    return {"universe": "proxy_spdr_sectors", "n_assets": int(P.shape[1]),
            "span": [str(idx.min().date()), str(idx.max().date())],
            "n_steps": int((len(idx) - max(Z_LB, 200)) // STEP),
            "labels": labels, "rank_ic": {"21d": ic21, "63d": ic63},
            "trend_gate_drawdown": gate,
            "alert_gate": {"risk": alert_risk, "entry": alert_entry}}


def _f(x):
    return float(x) if (x is not None and np.isfinite(x)) else None


def _calibrate_confidence(p: list, y: list, idx: list, outcome: str) -> dict:
    """Reliability of a continuous signal-strength score vs its binary outcome, plus a
    Platt recalibration and an OUT-OF-SAMPLE firing gate. The threshold is chosen on a
    purged, horizon-embargoed K-fold TRAIN split and scored on the held-out TEST fold
    (every obs scored OOS exactly once); the lift carries a DATE-BLOCKED bootstrap CI. So
    the gate is NOT an in-sample max-precision artifact and the verdict is robust only if
    the OOS lift CI clears 1.0. This is the 'needle-pinpoint accuracy' deliverable —
    suppress firings whose out-of-sample odds don't beat the base rate."""
    p = np.asarray(p, float); y = np.asarray(y, float); ev = np.asarray(idx, float)
    m = np.isfinite(p) & np.isfinite(y)
    p, y, ev = p[m], y[m], ev[m]
    n = len(p)
    if n < 200:
        return {"n": int(n), "verdict": "thin"}
    rel = V.brier_reliability(p, y)
    platt = V.platt_fit(p, y)
    base = float(y.mean())
    base_brier = (rel or {}).get("base_brier")
    recal = (platt or {}).get("brier_recal")
    skill_recal = round(1 - recal / base_brier, 3) if (recal and base_brier) else None

    grid = np.round(np.arange(0.2, 0.91, 0.05), 2)
    k, emb_idx = 5, 21                       # 21-index embargo = the forward-window overlap
    oos_fire = np.zeros(n, bool); thresholds = []
    if n >= k * 40:
        bounds = np.linspace(0, n, k + 1).astype(int)
        for j in range(k):
            lo, hi = int(bounds[j]), int(bounds[j + 1])
            test = np.zeros(n, bool); test[lo:hi] = True
            if not test.any():
                continue
            blo, bhi = ev[test].min(), ev[test].max()     # purge train rows whose forward
            train = (~test) & ((ev < blo - emb_idx) | (ev > bhi + emb_idx))  # window overlaps test
            fb = max(int(0.05 * train.sum()), 20)
            best_thr, best_prec = None, -1.0
            for thr in grid:
                f = train & (p >= thr)
                if int(f.sum()) < fb:
                    continue
                prec = float(y[f].mean())
                if prec > best_prec:
                    best_prec, best_thr = prec, float(thr)
            if best_thr is None:
                continue
            thresholds.append(best_thr)
            oos_fire[test & (p >= best_thr)] = True

    if not thresholds or int(oos_fire.sum()) < 20:
        return {"n": int(n), "outcome": outcome, "base_rate": round(base, 3),
                "reliability": rel, "platt": platt, "skill_recal": skill_recal,
                "gate": None, "verdict": "weak_separation"}

    prec_oos = float(y[oos_fire].mean())
    lift_oos = prec_oos / base if base > 0 else None
    # date-blocked bootstrap CI on the OOS lift (resample whole BARS w/ replacement so
    # same-day correlated rows move together — an i.i.d. row bootstrap understates width).
    uniq = np.unique(ev); rng = np.random.default_rng(7)
    rows_by_bar = {b: np.where(ev == b)[0] for b in uniq}
    lifts = []
    for _ in range(800):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([rows_by_bar[b] for b in pick])
        fb = oos_fire[ridx]; b2 = float(y[ridx].mean())
        if int(fb.sum()) >= 20 and b2 > 0:
            lifts.append(float(y[ridx][fb].mean()) / b2)
    lift_ci = [round(float(np.percentile(lifts, 2.5)), 2),
               round(float(np.percentile(lifts, 97.5)), 2)] if lifts else None

    gate = {"min_confidence": round(float(np.median(thresholds)), 2),
            "precision_oos": round(prec_oos, 3), "recall_oos": round(float(oos_fire.mean()), 3),
            "lift_oos": round(lift_oos, 2) if lift_oos else None, "lift_ci": lift_ci,
            "n_fired_oos": int(oos_fire.sum()), "k_folds": len(thresholds)}
    robust = lift_ci is not None and lift_ci[0] > 1.0      # CI excludes 'no lift'
    verdict = "calibratable" if robust else "weak_separation"
    return {"n": int(n), "outcome": outcome, "base_rate": round(base, 3),
            "reliability": rel, "platt": platt, "skill_recal": skill_recal,
            "gate": gate if robust else None,           # don't surface a non-robust gate
            "gate_rejected": None if robust else gate,  # ...but keep it for the audit trail
            "verdict": verdict}


# =========================================================================== #
# SIZING / REGIME backtest (E1 vol-target + E2 regime throttle). HONEST objective:
# does book-level realized-vol-targeting (Moreira-Muir) + a regime gross-throttle CUT
# THE DRAWDOWN of the validated dual-momentum rotation book, net of cost, AND beat a
# trend-only brake at matched exposure? This is a SIZING/Sharpe/drawdown lever — never a
# cross-sectional return forecast. The verdict drives a `sizing` contract block that
# narrative_rotation.allocate() consumes (calibratable -> wire; display_only -> annotate).
# =========================================================================== #
SZ_VOL_WINS = [20, 40, 60]
SZ_TARGETS = [0.7, 0.85, 1.0, 1.2]   # MULTIPLES of the book's OWN trailing-median vol (transfers
                                     # across universes: sectors ~15% vol, themes ~40% — both "run
                                     # toward typical vol; de-risk when hotter, lever when calmer")
SZ_CAPS = [1.0, 1.3, 1.5]
SZ_N_TRIALS = len(SZ_VOL_WINS) * len(SZ_TARGETS) * len(SZ_CAPS)   # 36 in-code grid (logged to ledger)
SZ_FAMILY = "baskets_voltarget_sizing"           # Trial-Ledger multiple-testing budget key
# default = DE-RISK-ONLY (cap 1.0): the overlay can only cut exposure, never lever above the
# base book. Levering up (cap>1) chases a Sharpe lift the data doesn't support and deepens
# some resampled drawdowns — the honest drawdown-control default never exceeds the base.
SZ_DEF = (40, 0.85, 1.0)         # default (vol_win, target_mult, cap) — declared, not cherry-picked
SZ_FLOOR = 0.0
SZ_COST_BPS = 10.0
SZ_SPLIT = pd.Timestamp("2013-01-01")
SZ_CRISES = {"gfc_2008": ("2007-10-01", "2009-06-30"),
             "covid_2020": ("2020-02-15", "2020-04-30"),
             "bear_2022": ("2022-01-01", "2022-10-31")}


def _daily_bill(idx) -> pd.Series:
    from lib import store
    for k in ("DTB3", "DGS3MO", "TB3MS"):
        df = store.read("fred", k)
        if df is not None and not df.empty:
            return df[df.columns[0]].astype(float).reindex(idx).ffill().fillna(0.0)
    return pd.Series(0.0, index=idx)


def _rotation_book(P: pd.DataFrame, top_n: int = 4, lookback: int = 12,
                   trend_ma: int = 200, mom_monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily EW weights of the validated dual-momentum book: monthly select the top_n by
    (lookback-1)m momentum among names ABOVE their own trend_ma, equal-weight, daily hold;
    idle slots (fewer than top_n trend) sit in cash. Causal (month-end decision uses data
    through that month-end; backtest_portfolio applies the next-bar lag). `mom_monthly`
    overrides the ranking signal (e.g. RESIDUAL momentum for the Build#4 A/B) — the absolute-
    trend gate stays the price 200d gate, applied identically to both books."""
    M = P.resample("ME").last()
    mom = mom_monthly if mom_monthly is not None else (M.pct_change(lookback) - M.pct_change(1))
    above = (P > P.rolling(trend_ma, min_periods=trend_ma // 2).mean())
    w = pd.DataFrame(0.0, index=M.index, columns=P.columns)
    for dt in M.index[max(lookback, 10):]:
        m = mom.loc[dt].dropna()
        ab = above.loc[:dt]
        if ab.empty or m.empty:
            continue
        m = m[ab.iloc[-1].reindex(m.index).fillna(False)]
        top = m.sort_values(ascending=False).head(top_n).index
        if len(top):
            w.loc[dt, top] = 1.0 / top_n
    return w.reindex(P.index, method="ffill").fillna(0.0)


def _book_voltarget(ew: pd.DataFrame, P: pd.DataFrame, vol_win: int, target_mult: float,
                    cap: float, floor: float = SZ_FLOOR) -> pd.DataFrame:
    """Scale the WHOLE equal-weight book by clip(target / trailing book-vol, floor, cap) —
    book-level vol-timing (Moreira-Muir), NOT per-asset risk parity. The target is RELATIVE:
    target_mult x the book's own causal trailing-median vol, so the overlay transfers across
    universes (de-risk when hotter than typical, lever when calmer). Residual gross < 1 falls
    to cash (credited the bill by backtest_portfolio). All causal."""
    rets = P.pct_change().fillna(0.0)
    book_ret = (ew.shift(1) * rets).sum(axis=1)
    book_vol = book_ret.rolling(vol_win).std() * np.sqrt(252)
    target = target_mult * book_vol.rolling(756, min_periods=252).median()    # causal typical vol
    s = (target / book_vol.replace(0, np.nan)).clip(lower=floor, upper=cap)
    return ew.mul(s, axis=0).fillna(0.0)


def _book_brake(ew: pd.DataFrame, P: pd.DataFrame, match_gross: float,
                trend_ma: int = 200) -> pd.DataFrame:
    """The decisive comparator: the SAME book braked by a binary book-level 200d trend gate
    instead of the continuous vol scalar, rescaled to the SAME average gross as the vol-target
    book. If vol-targeting can't beat this, the vol brake is just a noisier trend gate."""
    eq = (1 + P.pct_change().mean(axis=1)).cumprod()
    gate = (eq > eq.rolling(trend_ma, min_periods=trend_ma // 2).mean()).astype(float)
    gated = ew.mul(gate, axis=0)
    cur = float(gated.abs().sum(axis=1).mean())
    return (gated * (match_gross / cur) if cur > 0 else gated).fillna(0.0)


def _book_regime_throttle(ew: pd.DataFrame, P: pd.DataFrame, feats: dict,
                          floor: float = 0.4, hyst: int = 10) -> pd.DataFrame:
    """E2: graded gross-exposure throttle from the FADING-label leg (the one PIT-faithful,
    breadth-free risk signal MEASURED to precede drawdowns). Per name, when its fading
    condition (extended rs_pctile>=0.80 AND accel_z<-0.3 AND 5d-rel<0) holds, trim that
    sleeve's weight by half; floor the book gross at `floor`; hysteresis kills whipsaw.
    Down-only, never up-size, defaults LONG. (Macro drawdown_risk leg is already MEASURED
    elsewhere; here we isolate the basket-risk leg on the clean panel.)"""
    fade = pd.DataFrame(False, index=P.index, columns=P.columns)
    for c in P.columns:
        f = feats[c]
        cond = (f["rs_pctile"] >= 0.80) & (f["accel_z"] < -0.3) & (f["r5"] < 0)
        fade[c] = cond.reindex(P.index).fillna(False)
    # hysteresis: a fade flag persists `hyst` bars
    fade = fade.where(fade).ffill(limit=hyst).fillna(False).astype(bool)
    w = ew.where(~fade, ew * 0.5)
    gross = w.abs().sum(axis=1)
    scale = (floor / gross.replace(0, np.nan)).clip(lower=1.0)     # only ever floor-UP toward base
    return w.mul(scale.where(gross < floor, 1.0), axis=0).fillna(0.0)


def _ann_sharpe(r: pd.Series) -> float:
    r = r.dropna(); sd = r.std()
    return float(r.mean() / sd * np.sqrt(252)) if sd else float("nan")


def _maxdd_np(r: np.ndarray) -> float:
    eq = np.cumprod(1.0 + r); peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def _maxdd_ret(r: pd.Series) -> float:
    return _maxdd_np(r.fillna(0).to_numpy(float))


def _dd_reduction_ci(strat_net: pd.Series, base_net: pd.Series, block: int = 21,
                     B: int = 4000, seed: int = 11) -> dict:
    """Paired circular-block bootstrap of the drawdown REDUCTION in pp. MaxDD is negative,
    so a shallower strat has the LESS-negative dd; the reduction = (strat_dd - base_dd) is
    then POSITIVE when the strat is shallower. CI lower bound > 0 => the drawdown reduction
    is real, not a single-path artifact."""
    a = strat_net.dropna(); b = base_net.reindex(a.index).fillna(0.0)
    ra, rb = a.to_numpy(float), b.to_numpy(float); n = len(ra)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / block)); grid = np.arange(block)
    diffs = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        diffs[k] = (_maxdd_np(ra[idx]) - _maxdd_np(rb[idx])) * 100.0   # strat - base; >0 = shallower
    lo, med, hi = (float(np.percentile(diffs, p)) for p in (2.5, 50, 97.5))
    return {"dd_reduction_pp_ci": [round(lo, 1), round(med, 1), round(hi, 1)],
            "favorable": bool(lo > 0), "excludes_0": bool(lo > 0 or hi < 0), "n": n}


def run_sizing(region: str = "us") -> dict:
    """E1 (vol-target) + E2 (regime throttle) backtest on the clean proxy rotation book."""
    from engine import active_alloc as aa
    P = sector_prices(region, monthly=False)
    if P.empty or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    bill = _daily_bill(P.index)
    ew = _rotation_book(P)
    vw, tg, cp = SZ_DEF

    def bt(w, prices=P, b=bill):
        return aa.backtest_portfolio(w, prices, b, cost_bps=SZ_COST_BPS)

    base = bt(ew)
    vt_w = _book_voltarget(ew, P, vw, tg, cp)
    vt = bt(vt_w)
    brake = bt(_book_brake(ew, P, float(vt_w.abs().sum(axis=1).mean())))

    # DSR over the sizing grid (vol_win x target_mult x cap). Honest multiple-testing
    # accounting: log EVERY config to the Trial Ledger AT GENERATION (the caller cannot
    # lowball it), plus a declared budget covering the research variants NOT itemized here
    # (the earlier absolute-vol-target grid + the de-risk-only-vs-lever + regime-throttle
    # exploration). The DSR then deflates by the ledger's count, not a literal.
    led = TrialLedger()
    grid = [{"vol_win": a, "target_mult": t, "cap": c}
            for a in SZ_VOL_WINS for t in SZ_TARGETS for c in SZ_CAPS]
    led.log_grid(grid, family=SZ_FAMILY, info_cutoff="2026-06-21", source="calibrate_baskets:sizing")
    led.log_declared_budget(80, family=SZ_FAMILY,
                            reason="vol-target research: absolute(36)+relative(36) grids + cap/throttle variants")
    srs, best = [], None
    for cfg in grid:
        m = V.ret_moments(bt(_book_voltarget(ew, P, cfg["vol_win"], cfg["target_mult"], cfg["cap"]))["net"])
        if m is None:
            continue
        srs.append(m[0])
        if best is None or m[0] > best[0]:
            best = (m[0], m[1], m[2], m[3], (cfg["vol_win"], cfg["target_mult"], cfg["cap"]))
    sr_var = float(np.var(srs, ddof=1)) if len(srs) > 1 else None
    dsr = V.deflated_sharpe(best[0], best[1], best[2], best[3], ledger=led, family=SZ_FAMILY,
                            sr_variance=sr_var, trading_year=252) if best else None

    ddci = _dd_reduction_ci(vt["net"], base["net"])
    boot = V.block_bootstrap_ci(vt["net"], block=21, B=4000, seed=7, ann=252)

    # split-half (DD reduction same-sign in both halves)
    halves = {}
    for hn, mask in {"pre2013": P.index < SZ_SPLIT, "post2013": P.index >= SZ_SPLIT}.items():
        sub = P[mask]
        if len(sub) < 400:
            continue
        sb = _daily_bill(sub.index); e = _rotation_book(sub)
        vv = aa.backtest_portfolio(_book_voltarget(e, sub, vw, tg, cp), sub, sb, cost_bps=SZ_COST_BPS)
        bb = aa.backtest_portfolio(e, sub, sb, cost_bps=SZ_COST_BPS)
        halves[hn] = {"dd_better_pp": round((_maxdd_ret(vv["net"]) - _maxdd_ret(bb["net"])) * 100, 1),
                      "sharpe_edge": round(_ann_sharpe(vv["net"]) - _ann_sharpe(bb["net"]), 2)}
    dd_both = len(halves) == 2 and all(h["dd_better_pp"] > 0 for h in halves.values())

    # leave-one-crisis-out (the DD cut must not vanish when any single crisis is removed)
    loo = {}
    for cn, (s0, s1) in SZ_CRISES.items():
        keep = ~((P.index >= pd.Timestamp(s0)) & (P.index <= pd.Timestamp(s1)))
        sub = P[keep]; sb = _daily_bill(sub.index); e = _rotation_book(sub)
        vv = aa.backtest_portfolio(_book_voltarget(e, sub, vw, tg, cp), sub, sb, cost_bps=SZ_COST_BPS)
        bb = aa.backtest_portfolio(e, sub, sb, cost_bps=SZ_COST_BPS)
        loo[cn] = round((_maxdd_ret(vv["net"]) - _maxdd_ret(bb["net"])) * 100, 1)

    # E2 regime throttle (fading leg) on top of the vol-target book
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), P.mean(axis=1)) for c in P.columns}
    thr = bt(_book_regime_throttle(vt_w, P, feats))
    thr_ddci = _dd_reduction_ci(thr["net"], vt["net"])

    vt_sh, base_sh, brake_sh = _ann_sharpe(vt["net"]), _ann_sharpe(base["net"]), _ann_sharpe(brake["net"])
    vt_dd, base_dd = _maxdd_ret(vt["net"]), _maxdd_ret(base["net"])
    beats_brake = bool(vt_sh > brake_sh)
    dsr_ok = bool((dsr or {}).get("dsr", 0) >= 0.90)
    dd_real = bool(ddci.get("favorable"))                 # DD-reduction CI lower bound > 0
    robust_dd = bool(dd_real and dd_both and beats_brake)  # real, both halves, beats trend brake
    sharpe_lift = bool(vt_sh > base_sh + 0.02)            # does it ALSO improve risk-adjusted return?
    # Honest verdict ladder (Moreira-Muir on a thematic book is a DRAWDOWN lever first):
    #  calibratable  — robust DD-cut AND a Sharpe lift that survives the DSR haircut -> WIRE to size.
    #  display_only  — robust DD-cut but it costs CAGR / doesn't lift Sharpe -> OPTIONAL de-risk overlay,
    #                  shown + offered, never forced onto live weights.
    #  no_edge       — the DD reduction isn't robust.
    if robust_dd and sharpe_lift and dsr_ok:
        verdict = "calibratable"
    elif robust_dd:
        verdict = "display_only"
    else:
        verdict = "no_edge"
    e2_verdict = ("calibratable" if (thr_ddci.get("favorable") and verdict in ("calibratable", "display_only"))
                  else "display_only")

    return {"universe": "proxy_spdr_sectors", "span": [str(P.index.min().date()), str(P.index.max().date())],
            "verdict": verdict, "default": {"vol_win": vw, "target_mult": tg, "cap": cp, "floor": SZ_FLOOR},
            "best_cfg": best[4] if best else None, "n_trials": led.effective_n(SZ_FAMILY), "cost_bps": SZ_COST_BPS,
            "dsr": (dsr or {}).get("dsr"), "dsr_verdict": V.dsr_verdict((dsr or {}).get("dsr", 0)) if dsr else None,
            "vt": {"sharpe": round(vt_sh, 3), "maxdd_pct": round(vt_dd * 100, 1),
                   "cagr": vt.get("cagr"), "avg_gross": round(float(vt.get("avg_leverage", 0) or 0), 2),
                   "turnover_yr": vt.get("turnover_annual")},
            "base": {"sharpe": round(base_sh, 3), "maxdd_pct": round(base_dd * 100, 1), "cagr": base.get("cagr")},
            "brake": {"sharpe": round(brake_sh, 3)}, "beats_brake": beats_brake,
            "dd_reduction_ci": ddci, "block_bootstrap": boot,
            "split_half": halves, "dd_cut_both_halves": bool(dd_both), "loo_crisis": loo,
            "regime_throttle": {"verdict": e2_verdict, "floor": 0.4,
                                "dd_reduction_vs_vt_ci": thr_ddci,
                                "sharpe": round(_ann_sharpe(thr["net"]), 3),
                                "maxdd_pct": round(_maxdd_ret(thr["net"]) * 100, 1)}}


# =========================================================================== #
# BUILD#4 — residual (beta-stripped) momentum A/B. Does ranking the trend-gated book by
# RESIDUAL momentum cut CRASH risk (MaxDD / skew) vs TOTAL momentum, additively after the
# trend gate? Ship only if the DD-reduction CI vs the total book excludes 0; else residual
# momentum stays a descriptive z-leg (the plan's pre-registered kill-test).
# =========================================================================== #
def _residual_momentum_monthly(P: pd.DataFrame, bench: pd.Series, lookback: int = 12,
                               beta_win: int = 252, shrink: float = 0.5) -> pd.DataFrame:
    """Monthly (lookback-1)m RESIDUAL momentum. Residual return e_i = r_i − β_i·bench (causal
    rolling β shrunk toward 1, Blitz-style); the daily residual-return index is resampled
    monthly and read as (lookback-1)m momentum, exactly parallel to the total-price form."""
    rets, br = P.pct_change(), bench.pct_change()
    resid = pd.DataFrame(index=P.index, columns=P.columns, dtype=float)
    for c in P.columns:
        r = rets[c]
        cov = r.rolling(beta_win, min_periods=beta_win // 2).cov(br)
        var = br.rolling(beta_win, min_periods=beta_win // 2).var()
        beta = (cov / var.replace(0, np.nan)).shift(1)               # causal
        beta = shrink * 1.0 + (1 - shrink) * beta                    # shrink toward 1
        resid[c] = r - beta * br
    ri = (1.0 + resid.fillna(0.0)).cumprod()                          # residual-return index
    rim = ri.resample("ME").last()
    return rim.pct_change(lookback) - rim.pct_change(1)


def _skew(r: pd.Series):
    r = r.dropna()
    if len(r) < 12 or r.std() == 0:
        return None
    z = (r - r.mean()) / r.std()
    return float((z ** 3).mean())


def run_ranking_ab(region: str = "us") -> dict:
    from engine import active_alloc as aa
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    bill = _daily_bill(P.index)
    led = TrialLedger()
    abgrid = [{"beta_win": bw, "shrink": sh, "lookback": 12}
              for bw in (126, 252, 504) for sh in (0.0, 0.5, 1.0)]
    led.log_grid(abgrid, family="baskets_residual_rank", info_cutoff="2026-06-21",
                 source="calibrate_baskets:residual_ab")
    ew_total = _rotation_book(P)
    mom_resid = _residual_momentum_monthly(P, spy, beta_win=252, shrink=0.5)
    ew_resid = _rotation_book(P, mom_monthly=mom_resid)

    def bt(w):
        return aa.backtest_portfolio(w, P, bill, cost_bps=SZ_COST_BPS)

    tot, res = bt(ew_total), bt(ew_resid)
    ddci = _dd_reduction_ci(res["net"], tot["net"])       # residual vs total, BOTH trend-gated
    additive = bool(ddci.get("favorable"))
    return {"universe": "proxy_spdr_sectors", "n_trials": led.effective_n("baskets_residual_rank"),
            "total": {"sharpe": round(_ann_sharpe(tot["net"]), 3), "maxdd_pct": round(_maxdd_ret(tot["net"]) * 100, 1),
                      "skew": round(_skew(tot["net"]) or 0, 2), "cagr": tot.get("cagr")},
            "residual": {"sharpe": round(_ann_sharpe(res["net"]), 3), "maxdd_pct": round(_maxdd_ret(res["net"]) * 100, 1),
                         "skew": round(_skew(res["net"]) or 0, 2), "cagr": res.get("cagr")},
            "dd_reduction_vs_total_ci": ddci,
            "verdict": "additive_crash_control" if additive else "not_additive_descriptive"}


# =========================================================================== #
# E1-risk — calibrate the LIVE basket_score.rollover_risk breadth-free weights to forward
# 21d drawdown (logistic, SIGN-constrained, L2-shrunk to the hand weights). Ship the fitted
# weights ONLY if they beat the hand form OUT-OF-SAMPLE; else keep hand weights. Either way,
# emit the reliability so the live 'high' band can show its MEASURED drawdown rate. The
# breadth legs (member %>50d, nl>nh) have no single-ETF analogue, so this calibrates the
# breadth-free core (rs_pctile / accel / below-50 / 5d-rel) — the dominant part.
# =========================================================================== #
def _fit_logistic_signed(X, y, w0, l2: float = 1.0, iters: int = 800, lr: float = 0.3):
    """Sign-constrained (w>=0) logistic fit, L2-shrunk toward prior w0 — pure numpy (house
    'no sklearn' rule). Risk penalties are non-negative, so projected GD clips w>=0; the L2
    toward the hand weights keeps it from overfitting a weak signal."""
    X = np.asarray(X, float); y = np.asarray(y, float); w = np.asarray(w0, float).copy(); b = 0.0
    n = len(y)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / n + l2 * (w - w0) / n)
        b -= lr * float(g.mean())
        w = np.clip(w, 0.0, None)
    return w, float(b)


def run_rollover_fit(region: str = "us") -> dict:
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}
    HAND = np.array([0.30, 0.25, 0.20, 0.15, 0.10])   # rs>=.8 · roll-over · decel<-.4 · below50 · 5d<-1%&rs>.7
    rows = []
    for c, f in feats.items():
        px = P[c].to_numpy()
        rs_p = f["rs_pctile"].to_numpy(); az = f["accel_z"].to_numpy(); r5 = f["r5"].to_numpy()
        az5 = f["accel_z"].shift(5).to_numpy()
        ma50 = P[c].rolling(50, min_periods=25).mean().to_numpy()
        for i in range(max(Z_LB, 200), len(px) - 22, STEP):
            rp, a = rs_p[i], az[i]
            if not (np.isfinite(rp) and np.isfinite(a)):
                continue
            dd = _fwd_dd(px, i, 21)
            if not np.isfinite(dd):
                continue
            l1 = 1.0 if rp >= 0.8 else 0.0
            l2_ = 1.0 if (np.isfinite(az5[i]) and a < az5[i] and a < 0) else 0.0
            l3 = 1.0 if a < -0.4 else 0.0
            l4 = 1.0 if (np.isfinite(ma50[i]) and px[i] < ma50[i]) else 0.0
            l5 = 1.0 if (np.isfinite(r5[i]) and r5[i] < -0.01 and rp > 0.7) else 0.0
            rows.append((l1, l2_, l3, l4, l5, 1.0 if dd < DD_RISK else 0.0, float(i)))
    if len(rows) < 500:
        return {"error": "thin", "n": len(rows)}
    A = np.array(rows, float)
    A = A[np.argsort(A[:, 6], kind="stable")]      # rows are sector-blocked -> sort by bar so
    X, y, ev = A[:, :5], A[:, 5], A[:, 6]           # positional folds are time-contiguous (embargo works)
    hand_score = (X @ HAND) / HAND.sum()
    base = float(y.mean())

    led = TrialLedger()
    led.log_grid([{"l2": v} for v in (0.5, 1.0, 2.0)], family="baskets_rollover_fit",
                 info_cutoff="2026-06-21", source="calibrate_baskets:rollover_fit")
    led.log_declared_budget(12, family="baskets_rollover_fit",
                            reason="rollover weight-fit: l2 x band-cut x feature variants")

    # OOS purged 5-fold: fit on train, compare fitted-vs-hand top-third lift on the test fold
    k, emb = 5, 21
    bounds = np.linspace(0, len(X), k + 1).astype(int)
    fit_lifts, hand_lifts = [], []
    for j in range(k):
        lo, hi = int(bounds[j]), int(bounds[j + 1])
        test = np.zeros(len(X), bool); test[lo:hi] = True
        if not test.any():
            continue
        blo, bhi = ev[test].min(), ev[test].max()
        train = (~test) & ((ev < blo - emb) | (ev > bhi + emb))
        if train.sum() < 200 or test.sum() < 50:
            continue
        w, b = _fit_logistic_signed(X[train], y[train], HAND, l2=1.0)
        bte = float(y[test].mean()) or 1.0
        for score, store in ((1.0 / (1.0 + np.exp(-(X[test] @ w + b))), fit_lifts),
                             (hand_score[test], hand_lifts)):
            fire = score >= np.quantile(score, 2 / 3)
            if int(fire.sum()) >= 20:
                store.append(float(y[test][fire].mean()) / bte)
    fit_lift = round(float(np.mean(fit_lifts)), 2) if fit_lifts else None
    hand_lift = round(float(np.mean(hand_lifts)), 2) if hand_lifts else None
    rel = V.brier_reliability(hand_score, y)
    wfull, _bfull = _fit_logistic_signed(X, y, HAND, l2=1.0)
    beats = bool(fit_lift and hand_lift and fit_lift > hand_lift + 0.05)
    # WIRED weights = fitted, renormalized to the hand total (1.0) so the live additive
    # rollover score keeps the same 0-1 scale + 0.35/0.6 bands. Only used live if the gate passed.
    wsum = float(wfull.sum()) or 1.0
    wired = [round(float(x) / wsum, 3) for x in wfull]
    return {"universe": "proxy_spdr_sectors", "n": len(rows),
            "n_trials": led.effective_n("baskets_rollover_fit"), "base_rate": round(base, 3),
            "legs": ["rs_pctile>=0.8", "rolling_over", "decel<-0.4", "below_50d", "5d_rel<-1%&rs>0.7"],
            "hand_weights": [round(x, 2) for x in HAND.tolist()],
            "fitted_weights": [round(float(x), 3) for x in wfull],
            "wired_weights": wired,
            "oos_lift_hand": hand_lift, "oos_lift_fitted": fit_lift,
            "reliability_skill": (rel or {}).get("skill_score"),
            "verdict": "ship_fitted_weights" if beats else "keep_hand_weights"}


# =========================================================================== #
# P2b — intra-basket breadth-DIVERGENCE Phase-0 kill-test (PRE-REGISTERED).
# Target: forward 21d BASKET drawdown — NEVER forward return (the one validated channel
# in this repo is drawdown; directional early leader-detection measured a coin-flip and
# CN drivers ran 0/152 vs FWER, so any CN read of this detector stays descriptive-only).
# Proxy mapping: the SPDR sector panel is ONE basket — members = the 9-11 sector ETFs,
# level = the EW compounded mean return (the same documented stand-in as _panel_breadth;
# 11 broad sectors are a coarse member set — reported, not hidden).
# Two gates, DECLARED HERE BEFORE THE RUN:
#   G1 STANDALONE  — purged/embargoed 5-fold OOS top-third lift of the divergence risk
#                    score vs base P(dd21<-8%); the date-blocked bootstrap CI of the
#                    pooled OOS lift must exclude 1.0.
#   G2 INCREMENTAL — divergence joins the rollover logistic as a 6th sign-constrained leg
#                    (prior weight 0.0, so it must EARN weight against the L2 pull);
#                    require fit6_lift > hand_lift + 0.05 (the run_rollover_fit bar) AND
#                    fit6_lift > fit5_lift AND full-fit w6 > 0.02. Overlap with below_50d
#                    (0.859 of the fitted rollover mass) is the null hypothesis.
# Verdicts: ship_sizing_leg (G1+G2) / redundant_with_rollover (G1 only) /
# weak_separation (G1 fails). In ALL cases the live texture ships DISPLAY-ONLY — the
# verdict only controls the displayed grade (engine.basket_breadth_divergence cites it
# exactly like theme_scoring._signal_calibration cites the label calibration).
# =========================================================================== #
def run_breadth_divergence(region: str = "us") -> dict:
    from engine import basket_breadth_divergence as bd
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    rets = P.pct_change(fill_method=None)
    lvl = (1.0 + rets.mean(axis=1).fillna(0.0)).cumprod()      # EW panel level = "the basket"
    S = bd.series(P, lvl)
    if S is None:
        return {"error": "divergence series unavailable"}
    risk_v = S["risk"].to_numpy()
    legs_v = S["legs"].to_numpy()                              # (gap, participation, stealth)
    lvl_v = lvl.to_numpy()

    rows = []
    for i in range(max(Z_LB, 200), len(lvl_v) - 22, STEP):
        r = risk_v[i]
        if not np.isfinite(r):
            continue
        dd = _fwd_dd(lvl_v, i, 21)
        if not np.isfinite(dd) or not np.all(np.isfinite(legs_v[i])):
            continue
        rows.append((float(r), float(legs_v[i][0]), float(legs_v[i][1]), float(legs_v[i][2]),
                     1.0 if dd < DD_RISK else 0.0, float(i)))
    if len(rows) < 300:
        return {"error": "thin", "n": len(rows)}
    A = np.array(rows, float)
    p, L3, y, ev = A[:, 0], A[:, 1:4], A[:, 4], A[:, 5]
    base = float(y.mean())

    led = TrialLedger()
    led.log_grid([{"legs": "gap+participation+stealth", "weights": list(bd._BD_HAND),
                   "l2": 1.0}], family="baskets_breadth_divergence",
                 info_cutoff="2026-06-30", source="calibrate_baskets:breadth_divergence")
    led.log_declared_budget(12, family="baskets_breadth_divergence",
                            reason="bd design variants considered: pin gate / ramp span / "
                                   "stealth floor / hand-weight splits")

    # ---- G1 standalone: purged 5-fold OOS top-third lift + date-blocked bootstrap CI
    k, emb = 5, 21
    n = len(p)
    bounds = np.linspace(0, n, k + 1).astype(int)
    oos_fire = np.zeros(n, bool)
    used = np.zeros(n, bool)
    fold_lifts = []
    for j in range(k):
        lo, hi = int(bounds[j]), int(bounds[j + 1])
        test = np.zeros(n, bool); test[lo:hi] = True
        if not test.any():
            continue
        blo, bhi = ev[test].min(), ev[test].max()
        train = (~test) & ((ev < blo - emb) | (ev > bhi + emb))
        if train.sum() < 100 or test.sum() < 40:
            continue
        thr = float(np.quantile(p[test], 2 / 3))   # top-third rank cut (score-only, no y)
        fire = test & ((p > 0) if thr <= 0 else (p >= thr))   # zero-inflated guard: a 0
        # threshold would "fire" the whole fold and dilute the read to lift 1 by definition
        used |= test
        oos_fire |= fire
        bte = float(y[test].mean())
        if int(fire.sum()) >= 15 and bte > 0:
            fold_lifts.append(float(y[fire].mean()) / bte)
    lift_oos = round(float(np.mean(fold_lifts)), 2) if fold_lifts else None
    lift_ci = None
    if used.sum() and oos_fire.sum() >= 20:
        uev, rng = np.unique(ev[used]), np.random.default_rng(7)
        rows_by_bar = {b: np.where(used & (ev == b))[0] for b in uev}
        lifts = []
        for _ in range(800):                        # date-blocked: resample whole BARS
            pick = rng.choice(uev, size=len(uev), replace=True)
            ridx = np.concatenate([rows_by_bar[b] for b in pick])
            fb = oos_fire[ridx]; b2 = float(y[ridx].mean())
            if int(fb.sum()) >= 15 and b2 > 0:
                lifts.append(float(y[ridx][fb].mean()) / b2)
        if lifts:
            lift_ci = [round(float(np.percentile(lifts, 2.5)), 2),
                       round(float(np.percentile(lifts, 97.5)), 2)]
    g1 = bool(lift_ci is not None and lift_ci[0] > 1.0)
    # house reliability/Platt read on the same score (secondary, reported not gating)
    confidence = _calibrate_confidence(list(p), list(y), list(ev), "fwd_dd21<-8%")
    confidence.pop("reliability", None); confidence.pop("platt", None)   # keep the JSON lean

    # standalone 3-leg weight fit (only ever wired live if the FULL verdict ships)
    HAND3 = np.array(bd._BD_HAND, float)
    w3, _b3 = _fit_logistic_signed(L3, y, HAND3, l2=1.0)
    w3sum = float(w3.sum()) or 1.0
    wired3 = [round(float(x) / w3sum, 3) for x in w3]

    # ---- G2 incremental: divergence as the 6th sign-constrained rollover leg
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}
    HAND5 = np.array([0.30, 0.25, 0.20, 0.15, 0.10])
    rows6 = []
    for c, f in feats.items():
        px = P[c].to_numpy()
        rs_p = f["rs_pctile"].to_numpy(); az = f["accel_z"].to_numpy(); r5 = f["r5"].to_numpy()
        az5 = f["accel_z"].shift(5).to_numpy()
        ma50 = P[c].rolling(50, min_periods=25).mean().to_numpy()
        for i in range(max(Z_LB, 200), len(px) - 22, STEP):
            rp, a, r6 = rs_p[i], az[i], risk_v[i]
            if not (np.isfinite(rp) and np.isfinite(a) and np.isfinite(r6)):
                continue
            dd = _fwd_dd(px, i, 21)
            if not np.isfinite(dd):
                continue
            l1 = 1.0 if rp >= 0.8 else 0.0
            l2_ = 1.0 if (np.isfinite(az5[i]) and a < az5[i] and a < 0) else 0.0
            l3 = 1.0 if a < -0.4 else 0.0
            l4 = 1.0 if (np.isfinite(ma50[i]) and px[i] < ma50[i]) else 0.0
            l5 = 1.0 if (np.isfinite(r5[i]) and r5[i] < -0.01 and rp > 0.7) else 0.0
            rows6.append((l1, l2_, l3, l4, l5, float(r6),
                          1.0 if dd < DD_RISK else 0.0, float(i)))
    g2 = False
    inc = {"n": len(rows6)}
    if len(rows6) >= 500:
        A6 = np.array(rows6, float)
        A6 = A6[np.argsort(A6[:, 7], kind="stable")]           # bar-sorted → contiguous folds
        X6, y6, ev6 = A6[:, :6], A6[:, 6], A6[:, 7]
        X5 = X6[:, :5]
        hand_score = (X5 @ HAND5) / HAND5.sum()
        prior6 = np.concatenate([HAND5, [0.0]])                # divergence must EARN weight
        b6 = np.linspace(0, len(X6), k + 1).astype(int)
        fit5_l, fit6_l, hand_l, w6_folds = [], [], [], []
        for j in range(k):
            lo, hi = int(b6[j]), int(b6[j + 1])
            test = np.zeros(len(X6), bool); test[lo:hi] = True
            if not test.any():
                continue
            blo, bhi = ev6[test].min(), ev6[test].max()
            train = (~test) & ((ev6 < blo - emb) | (ev6 > bhi + emb))
            if train.sum() < 200 or test.sum() < 50:
                continue
            w5f, b5f = _fit_logistic_signed(X5[train], y6[train], HAND5, l2=1.0)
            w6f, b6f = _fit_logistic_signed(X6[train], y6[train], prior6, l2=1.0)
            w6_folds.append(round(float(w6f[5]), 3))
            bte = float(y6[test].mean()) or 1.0
            for score, store in ((1.0 / (1.0 + np.exp(-(X5[test] @ w5f + b5f))), fit5_l),
                                 (1.0 / (1.0 + np.exp(-(X6[test] @ w6f + b6f))), fit6_l),
                                 (hand_score[test], hand_l)):
                fire = score >= np.quantile(score, 2 / 3)
                if int(fire.sum()) >= 20:
                    store.append(float(y6[test][fire].mean()) / bte)
        fit5 = round(float(np.mean(fit5_l)), 2) if fit5_l else None
        fit6 = round(float(np.mean(fit6_l)), 2) if fit6_l else None
        hand = round(float(np.mean(hand_l)), 2) if hand_l else None
        wfull6, _bf6 = _fit_logistic_signed(X6, y6, prior6, l2=1.0)
        g2 = bool(fit6 is not None and hand is not None
                  and fit6 > hand + 0.05                      # the run_rollover_fit bar
                  and (fit5 is None or fit6 > fit5)           # adds over the 5-leg FIT too
                  and float(wfull6[5]) > 0.02)                # ...and actually earned weight
        inc.update({"base_rate": round(float(y6.mean()), 3),
                    "oos_lift_hand5": hand, "oos_lift_fit5": fit5, "oos_lift_fit6": fit6,
                    "w6_full_fit": round(float(wfull6[5]), 3), "w6_by_fold": w6_folds,
                    "full_fit_weights": [round(float(x), 3) for x in wfull6]})

    verdict = ("ship_sizing_leg" if (g1 and g2)
               else "redundant_with_rollover" if g1 else "weak_separation")
    return {"universe": "proxy_spdr_sectors", "n_assets": int(P.shape[1]),
            "span": [str(P.index.min().date()), str(P.index.max().date())],
            "n": int(n), "base_rate": round(base, 3),
            "n_trials": led.effective_n("baskets_breadth_divergence"),
            "target": "fwd_dd21<-8% (basket drawdown — never forward return)",
            "legs": ["gap(pinned, basket_off_high−member_dd_med ramp 3→20pp)",
                     "participation(Δpct50_5d<-5pp | pct50<=0.5, pinned)",
                     "stealth(rising below-50d count 10d & share>=0.3 | share>=0.7, pinned)"],
            "hand_weights": [round(float(x), 2) for x in HAND3.tolist()],
            "fitted_leg_weights": [round(float(x), 3) for x in w3],
            "wired_weights": wired3,
            "g1_standalone": {"pass": g1, "oos_topthird_lift": lift_oos,
                              "lift_ci": lift_ci, "n_fired_oos": int(oos_fire.sum()),
                              "k_folds": len(fold_lifts)},
            "g2_incremental": {"pass": g2, **inc},
            "confidence": confidence,
            "verdict": verdict,
            "note": "Display-only texture in ALL cases; the verdict only controls the "
                    "displayed grade. CN/HK reads are descriptive-only regardless "
                    "(US-proxy verdict cited cross-market, 0/152-FWER CN prior)."}


def _print_bd(r: dict) -> None:
    if r.get("error"):
        print(f"\n=== BREADTH-DIVERGENCE PHASE-0: {r['error']} ==="); return
    print(f"\n=== BREADTH-DIVERGENCE PHASE-0 ({r.get('n_assets')} sector ETFs as one basket, "
          f"{r.get('span', ['?', '?'])[0]}→{r.get('span', ['?', '?'])[1]}) ===")
    print(f"  target {r.get('target')}   n {r.get('n')}  base {r.get('base_rate')}  "
          f"n_trials {r.get('n_trials')}")
    g1, g2 = r.get("g1_standalone", {}), r.get("g2_incremental", {})
    print(f"  G1 standalone:  top-third OOS lift {g1.get('oos_topthird_lift')}  "
          f"CI {g1.get('lift_ci')}  n_fired {g1.get('n_fired_oos')}  → pass={g1.get('pass')}")
    print(f"  G2 incremental: hand5 {g2.get('oos_lift_hand5')}  fit5 {g2.get('oos_lift_fit5')}  "
          f"fit6 {g2.get('oos_lift_fit6')}  w6 {g2.get('w6_full_fit')}  → pass={g2.get('pass')}")
    print(f"  leg weights: hand {r.get('hand_weights')} fitted {r.get('fitted_leg_weights')}")
    print(f"  >>> VERDICT: {r.get('verdict')}  (texture ships display-only in all cases)")


def main_bd() -> int:
    """Standalone Phase-0 entry (`--bd`): run ONLY run_breadth_divergence and merge its
    verdict block ADDITIVELY into data/strategies/baskets_calibration.json under
    'breadth_divergence_fit' — existing keys are never disturbed."""
    res = run_breadth_divergence("us")
    _print_bd(res)
    p = config.data_dir() / "strategies" / "baskets_calibration.json"
    try:
        d = json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001 — a corrupt file must not block the additive write
        d = {}
    d["breadth_divergence_fit"] = res
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, default=str))
    log.info("wrote %s (breadth_divergence_fit, additive)", p)
    return 0


# =========================================================================== #
# LABEL-FALTERING PHASE-0 (pre-registered 2026-07-03 — research/LABEL_FALTERING_PHASE0.md)
# Three candidate fixes from the 2026-07-03 "ACCUMULATE while the bubble pops" incident,
# deliberately NOT shipped blind. B1/B3 fit NO parameters (all thresholds pre-declared in
# the doc), so inference is HAC + date-blocked bootstrap + split-half, no CV folds; B2's
# incremental leg fits weights -> purged/embargoed 5-fold (the run_rollover_fit machinery).
# NOTHING here wires into _label()/_reco()/allocate() regardless of verdict.
# =========================================================================== #
ESC_GRID = (-0.03, -0.05, -0.07)   # B1: 5d ABSOLUTE-return escape thresholds
ESC_PRIMARY = -0.05                # pre-declared primary cell; ±2% cells are sensitivity
RDM_GRID = (-0.05, -0.10, -0.15)   # B3: 21d-return demotion thresholds at rank time
RDM_PRIMARY = -0.10                # pre-declared primary cell
CONV_LOW = 25.0                    # B2 proxy: member-median health "collapse" level (0-100)
LF_SPLIT = SZ_SPLIT                # split-half boundary (2013-01-01), shared with sizing


def _paired_daily_diff_t(metric: np.ndarray, fired: np.ndarray, inset: np.ndarray,
                         ev: np.ndarray) -> dict:
    """HAC t of the SAME-DAY paired difference: per bar, mean(metric | fired) minus
    mean(metric | in-set & not fired). Non-trivial by construction (fwd drawdown is <= 0
    everywhere, so a raw HAC t on it is meaningless — the paired diff is the claim)."""
    ok = inset & np.isfinite(metric)
    diffs = []
    for b in np.unique(ev[ok & fired]):
        day = ok & (ev == b)
        f, u = day & fired, day & ~fired
        if f.any() and u.any():
            diffs.append(float(metric[f].mean() - metric[u].mean()))
    if len(diffs) < 8:
        return {"t": None, "mean": None, "n_days": len(diffs)}
    nw = V.newey_west_tstat(np.array(diffs), lags=int(np.ceil(21 / STEP)))
    return {"t": nw["t"], "mean": round(100 * (nw["mean"] or 0), 2), "n_days": len(diffs)}


def _hit_lift_ci(fired: np.ndarray, inset: np.ndarray, y: np.ndarray, ev: np.ndarray,
                 B: int = 800, seed: int = 7) -> tuple[float | None, list | None]:
    """P(y|fired)/P(y|in-set) with a date-blocked bootstrap CI (whole bars resampled, so
    same-day correlated sector rows move together)."""
    if not fired.any() or not inset.any():
        return None, None
    base = float(y[inset].mean())
    lift = float(y[fired].mean()) / base if base > 0 else None
    uev = np.unique(ev[inset])
    rows_by_bar = {b: np.where(inset & (ev == b))[0] for b in uev}
    rng = np.random.default_rng(seed)
    lifts = []
    for _ in range(B):
        pick = rng.choice(uev, size=len(uev), replace=True)
        ridx = np.concatenate([rows_by_bar[b] for b in pick])
        fb = fired[ridx]
        b2 = float(y[ridx].mean())
        if int(fb.sum()) >= 10 and b2 > 0:
            lifts.append(float(y[ridx][fb].mean()) / b2)
    ci = [round(float(np.percentile(lifts, 2.5)), 2),
          round(float(np.percentile(lifts, 97.5)), 2)] if len(lifts) >= 100 else None
    return (round(lift, 2) if lift is not None else None), ci


# --------------------------------------------------------------------------- #
# B1 — absolute-return escape leg in the fading path (abs_escape_fit)
# --------------------------------------------------------------------------- #
def run_abs_escape(region: str = "us") -> dict:
    """Would `fading` on (5d ABS return <= X AND breadth deterioration) — fired ONLY where
    the relative-only path did NOT already flag risk — precede deeper forward drawdowns
    (G1) without systematically selling bottoms (KILL: fired events resolving UP vs the
    same-day in-set baseline)? Thresholds pre-declared; nothing fitted."""
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    breadth = _panel_breadth(P)
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}
    spy_v = spy.to_numpy()
    idx = P.index
    bnp = {"pct50": breadth["pct50"].to_numpy(), "pct200": breadth["pct200"].to_numpy(),
           "nh": breadth["nh"].to_numpy(), "nl": breadth["nl"].to_numpy(),
           "net_nh": breadth["net_nh"].to_numpy()}

    led = TrialLedger()
    led.log_grid([{"abs5_thresh": x} for x in ESC_GRID], family="baskets_abs_escape",
                 info_cutoff="2026-07-02", source="calibrate_baskets:abs_escape")
    led.log_declared_budget(12, family="baskets_abs_escape",
                            reason="escape-leg design variants considered: breadth-det gate "
                                   "forms / 1d-vs-5d window / in-set definitions")

    # rows: (abs5, det, inset, dd21, ret21, rel21, bar, pre2013)
    rows = []
    for i in range(max(Z_LB, 200), len(idx) - 22, STEP):
        net_raw = bnp["nh"][i] - bnp["nl"][i]
        det = bool((np.isfinite(net_raw) and net_raw <= 0)
                   or (np.isfinite(bnp["pct50"][i]) and bnp["pct50"][i] < 0.5))
        for c, f in feats.items():
            px = P[c].to_numpy()
            if not np.isfinite(px[i]) or i < 5 or not np.isfinite(px[i - 5]):
                continue
            accel_z = f["accel_z"].iloc[i]; rs_p = f["rs_pctile"].iloc[i]
            if pd.isna(accel_z) or pd.isna(rs_p):
                continue
            accel_z, rs_p = float(accel_z), float(rs_p)
            r5, r20, r60 = f["r5"].iloc[i], f["r20"].iloc[i], f["r60"].iloc[i]
            d5 = f["delta_5d"].iloc[i]
            trend = _trend_leg(r5, r20, r60, accel_z)
            bl = _breadth_leg(bnp["pct50"][i], bnp["pct200"][i], bnp["net_nh"][i])
            cp = _crowd_pen(rs_p)
            score = _proxy_score(trend, bl, cp)
            fp = {"accel_z": accel_z, "rs_pctile": rs_p}
            perf = {"5d": {"rel": _f(r5)}, "20d": {"rel": _f(r20)}, "60d": {"rel": _f(r60)}}
            bdict = {"pct50": _f(bnp["pct50"][i]), "nh": int(bnp["nh"][i]), "nl": int(bnp["nl"][i])}
            lab = _label(score, fp, perf, bdict, _f(d5))
            inset = lab not in ("fading", "deteriorating")   # relative path did NOT flag risk
            abs5 = float(px[i] / px[i - 5] - 1.0)
            dd21 = _fwd_dd(px, i, 21)
            ret21 = float(px[i + 21] / px[i] - 1.0) if i + 21 < len(px) else np.nan
            rel21 = _fwd_rel(px, spy_v, i, 21)
            if not (np.isfinite(dd21) and np.isfinite(ret21)):
                continue
            rows.append((abs5, 1.0 if det else 0.0, 1.0 if inset else 0.0,
                         dd21, ret21, rel21 if np.isfinite(rel21) else np.nan,
                         float(i), 1.0 if idx[i] < LF_SPLIT else 0.0))
    if len(rows) < 500:
        return {"error": "thin", "n": len(rows)}
    A = np.array(rows, float)
    abs5, det, inset = A[:, 0], A[:, 1].astype(bool), A[:, 2].astype(bool)
    dd21, ret21, rel21, ev, pre = A[:, 3], A[:, 4], A[:, 5], A[:, 6], A[:, 7].astype(bool)
    y = (dd21 < DD_RISK).astype(float)
    base_inset = float(y[inset].mean())

    cells = {}
    for x in ESC_GRID:
        fired = inset & det & (abs5 <= x)
        n_fired = int(fired.sum())
        cell = {"n_fired": n_fired, "n_days_fired": int(len(np.unique(ev[fired])))}
        if n_fired < 40:
            cell["verdict"] = "thin"
            cells[f"{x:+.0%}"] = cell
            continue
        lift, ci = _hit_lift_ci(fired, inset, y, ev)
        t_dd = _paired_daily_diff_t(dd21, fired, inset, ev)
        t_ret = _paired_daily_diff_t(ret21, fired, inset, ev)
        halves_ok, halves = True, {}
        for hn, hm in (("pre2013", pre), ("post2013", ~pre)):
            hb = float(y[inset & hm].mean()) if (inset & hm).any() else 0.0
            hf = float(y[fired & hm].mean()) if (fired & hm).any() else None
            hl = round(hf / hb, 2) if (hf is not None and hb > 0) else None
            halves[hn] = {"lift": hl, "n_fired": int((fired & hm).sum())}
            halves_ok &= bool(hl is not None and hl > 1.0)
        kill = bool(t_ret["t"] is not None and t_ret["t"] >= HAC_FLOOR_T)
        g1 = bool(ci is not None and ci[0] > 1.0
                  and t_dd["t"] is not None and t_dd["t"] <= -HAC_FLOOR_T
                  and halves_ok)
        cell.update({
            "dd21_med_fired_pct": round(100 * float(np.median(dd21[fired])), 2),
            "dd21_med_inset_pct": round(100 * float(np.median(dd21[inset])), 2),
            "ret21_med_fired_pct": round(100 * float(np.median(ret21[fired])), 2),
            "rel21_med_fired_pct": round(100 * float(np.nanmedian(rel21[fired])), 2),
            "hit_fired": round(float(y[fired].mean()), 3), "lift": lift, "lift_ci": ci,
            "t_dd_paired": t_dd, "t_ret_paired": t_ret, "split_half": halves,
            "g1_risk": g1, "killed": kill,
            "verdict": ("sell_the_bottom_generator" if kill
                        else "ship_escape_leg" if g1 else "no_incremental_edge")})
        cells[f"{x:+.0%}"] = cell

    prim = cells.get(f"{ESC_PRIMARY:+.0%}", {})
    sens_kill = any(c.get("killed") for k, c in cells.items()
                    if k != f"{ESC_PRIMARY:+.0%}")
    verdict = prim.get("verdict", "thin")
    if verdict == "ship_escape_leg" and sens_kill:
        verdict = "no_incremental_edge"          # a sensitivity-cell kill vetoes the ship
    return {"universe": "proxy_spdr_sectors", "n_assets": int(P.shape[1]),
            "span": [str(idx.min().date()), str(idx.max().date())],
            "preregistered": "research/LABEL_FALTERING_PHASE0.md#B1",
            "n": int(len(A)), "n_inset": int(inset.sum()),
            "base_rate_inset": round(base_inset, 3),
            "n_trials": led.effective_n("baskets_abs_escape"),
            "grid_pct": [round(100 * x) for x in ESC_GRID],
            "primary_cell_pct": round(100 * ESC_PRIMARY),
            "breadth_det_def": "net_nh<=0 OR pct50<0.5 (panel proxy, broadcast)",
            "cells": cells, "sensitivity_kill_veto": bool(sens_kill),
            "verdict": verdict,
            "note": "In-set = relative-path label NOT fading/deteriorating — the events the "
                    "escape leg would ADD. Not wired into _label() in this task."}


# --------------------------------------------------------------------------- #
# B2 — member-conviction-median demotion leg (conviction_demotion_fit)
# --------------------------------------------------------------------------- #
def _audit_conviction_pit() -> dict:
    """Programmatic audit of every candidate PIT source for per-basket member-conviction
    history (audited 2026-07-03). The real study needs a dated series of the member
    conviction.potential median; a rendered current-state store is not history."""
    out = {}
    try:
        b = pd.read_parquet(config.data_dir() / "china_standout_track" / "board.parquet")
        out["china_standout_track"] = {
            "span": [str(b["date"].min()), str(b["date"].max())],
            "n_days": int(b["date"].nunique()),
            "has_conviction_field": bool(any("conv" in c.lower() for c in b.columns)),
            "fields": list(b.columns)}
    except Exception as e:  # noqa: BLE001
        out["china_standout_track"] = {"error": str(e)}
    try:
        a = pd.read_parquet(config.data_dir() / "signal_archive" / "baskets.parquet")
        out["signal_archive_baskets"] = {
            "span": [str(a["asof"].min()), str(a["asof"].max())],
            "n_days": int(a["asof"].nunique()),
            "conviction_fields": [c for c in a.columns if "conv" in c.lower() or "member" in c.lower()]}
    except Exception as e:  # noqa: BLE001
        out["signal_archive_baskets"] = {"error": str(e)}
    out["git_rendered_stores"] = {
        "note": "site/*stockdata/*.json carried conviction blocks in git only 2026-06-13 → "
                "2026-07-01 (~13 trading days), then untracked to R2 (r2-data-plane). "
                "Rendered current-state, formula drift across renders — not a PIT series."}
    out["r2_data_plane"] = {"note": "current-state per-ticker stores only; no dated snapshots."}
    days = [v.get("n_days", 0) for v in out.values() if isinstance(v, dict)]
    conv = [bool(v.get("has_conviction_field")) or bool(v.get("conviction_fields"))
            for v in out.values() if isinstance(v, dict)]
    out["usable_pit_history"] = bool(any(d >= 126 and c for d, c in zip(days, conv)))
    return out


def run_conviction_demotion(region: str = "us") -> dict:
    """B2 in three pre-registered parts: (1) PIT-source audit — the real study cannot run
    without a dated member-conviction-median history; (2) the accrual spec if none exists;
    (3) an SPDR price-proxy kill-test (prior-setting ONLY — the proxy health composite is
    a price stand-in for conviction.potential's price legs and can never ship the leg)."""
    audit = _audit_conviction_pit()
    accrual = {
        "what": "daily, per basket and region: member conviction.potential median, IQR, "
                "n_members, theme score, label — archived via engine.signal_archive at render",
        "rerun_bar": ">=180 archived trading days (~9 months; ~36 non-overlapping 21d windows "
                     "per basket x ~25 baskets, date-blocked pooling)",
        "gates_on_rerun": "identical to the proxy G1/G2 below, pre-registered 2026-07-03"}

    led = TrialLedger()
    led.log_grid([{"health_legs": "50d+200d+r20+dd252", "low": CONV_LOW,
                   "constructive": "lvl>200dma & r20>0"}],
                 family="baskets_conviction_demotion",
                 info_cutoff="2026-07-02", source="calibrate_baskets:conviction_demotion")
    led.log_declared_budget(12, family="baskets_conviction_demotion",
                            reason="proxy-health design variants considered: leg splits / "
                                   "collapse-delta vs level / constructive definitions")

    # ---- Part 3 proxy: member health median vs the EW panel basket
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data", "pit_audit": audit, "accrual_spec": accrual}
    spy = spy.reindex(P.index).ffill()
    ma50 = P.rolling(50, min_periods=25).mean()
    ma200 = P.rolling(200, min_periods=100).mean()
    r20 = P.pct_change(20, fill_method=None)
    dd252 = P / P.rolling(252, min_periods=60).max() - 1.0
    health = (25.0 * (P > ma50).astype(float) + 25.0 * (P > ma200).astype(float)
              + 25.0 * (r20 > 0).astype(float) + 25.0 * (dd252 > -0.15).astype(float))
    health = health.where(P.notna() & ma200.notna())
    med_h = health.median(axis=1)
    lvl = (1.0 + P.pct_change(fill_method=None).mean(axis=1).fillna(0.0)).cumprod()
    lvl_ma = lvl.rolling(200, min_periods=100).mean()
    constructive = (lvl > lvl_ma) & (lvl.pct_change(20, fill_method=None) > 0)

    lvl_v, med_v, con_v = lvl.to_numpy(), med_h.to_numpy(), constructive.to_numpy()
    samp = []                                  # (event, y, bar) on constructive days only
    for i in range(max(Z_LB, 200), len(lvl_v) - 22, STEP):
        if not con_v[i] or not np.isfinite(med_v[i]):
            continue
        dd = _fwd_dd(lvl_v, i, 21)
        if not np.isfinite(dd):
            continue
        samp.append((1.0 if med_v[i] <= CONV_LOW else 0.0, 1.0 if dd < DD_RISK else 0.0, float(i)))
    proxy: dict = {"n_constructive": len(samp)}
    g1 = False
    if len(samp) >= 100:
        S = np.array(samp, float)
        event, y1, ev1 = S[:, 0].astype(bool), S[:, 1], S[:, 2]
        base = float(y1.mean())
        n_ev = int(event.sum())
        proxy.update({"base_rate": round(base, 3), "n_events": n_ev,
                      "event_def": f"constructive AND member-median health <= {CONV_LOW:.0f}"})
        if n_ev >= 20:
            # single-series -> BLOCK bootstrap (5-obs blocks span one forward window; an
            # i.i.d. bar bootstrap would understate width on overlapping 21d windows)
            lift = float(y1[event].mean()) / base if base > 0 else None
            rng = np.random.default_rng(7)
            n1, blk = len(y1), int(np.ceil(21 / STEP))
            nb, grid = int(np.ceil(n1 / blk)), np.arange(blk)
            lifts = []
            for _ in range(800):
                starts = rng.integers(0, n1, nb)
                ridx = (starts[:, None] + grid[None, :]).ravel()[:n1] % n1
                eb, yb = event[ridx], y1[ridx]
                b2 = float(yb.mean())
                if int(eb.sum()) >= 10 and b2 > 0:
                    lifts.append(float(yb[eb].mean()) / b2)
            ci = [round(float(np.percentile(lifts, 2.5)), 2),
                  round(float(np.percentile(lifts, 97.5)), 2)] if len(lifts) >= 100 else None
            g1 = bool(ci is not None and ci[0] > 1.0)
            proxy["g1_standalone"] = {"pass": g1, "lift": round(lift, 2) if lift else None,
                                      "lift_ci": ci}
        else:
            proxy["g1_standalone"] = {"pass": False, "note": "too few collapse events"}
    else:
        proxy["g1_standalone"] = {"pass": False, "note": "thin"}

    # ---- G2 incremental: collapse flag as 6th sign-constrained rollover leg (prior 0)
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}
    HAND5 = np.array([0.30, 0.25, 0.20, 0.15, 0.10])
    flag_v = (constructive & (med_h <= CONV_LOW)).to_numpy().astype(float)
    rows6 = []
    for c, f in feats.items():
        px = P[c].to_numpy()
        rs_p = f["rs_pctile"].to_numpy(); az = f["accel_z"].to_numpy(); r5 = f["r5"].to_numpy()
        az5 = f["accel_z"].shift(5).to_numpy()
        m50 = ma50[c].to_numpy()
        for i in range(max(Z_LB, 200), len(px) - 22, STEP):
            rp, a = rs_p[i], az[i]
            if not (np.isfinite(rp) and np.isfinite(a)):
                continue
            dd = _fwd_dd(px, i, 21)
            if not np.isfinite(dd):
                continue
            l1 = 1.0 if rp >= 0.8 else 0.0
            l2_ = 1.0 if (np.isfinite(az5[i]) and a < az5[i] and a < 0) else 0.0
            l3 = 1.0 if a < -0.4 else 0.0
            l4 = 1.0 if (np.isfinite(m50[i]) and px[i] < m50[i]) else 0.0
            l5 = 1.0 if (np.isfinite(r5[i]) and r5[i] < -0.01 and rp > 0.7) else 0.0
            rows6.append((l1, l2_, l3, l4, l5, float(flag_v[i]),
                          1.0 if dd < DD_RISK else 0.0, float(i)))
    g2 = False
    inc: dict = {"n": len(rows6)}
    if len(rows6) >= 500:
        A6 = np.array(rows6, float)
        A6 = A6[np.argsort(A6[:, 7], kind="stable")]
        X6, y6, ev6 = A6[:, :6], A6[:, 6], A6[:, 7]
        X5 = X6[:, :5]
        hand_score = (X5 @ HAND5) / HAND5.sum()
        prior6 = np.concatenate([HAND5, [0.0]])
        k, emb = 5, 21
        b6 = np.linspace(0, len(X6), k + 1).astype(int)
        fit5_l, fit6_l, hand_l, w6_folds = [], [], [], []
        for j in range(k):
            lo, hi = int(b6[j]), int(b6[j + 1])
            test = np.zeros(len(X6), bool); test[lo:hi] = True
            if not test.any():
                continue
            blo, bhi = ev6[test].min(), ev6[test].max()
            train = (~test) & ((ev6 < blo - emb) | (ev6 > bhi + emb))
            if train.sum() < 200 or test.sum() < 50:
                continue
            w5f, b5f = _fit_logistic_signed(X5[train], y6[train], HAND5, l2=1.0)
            w6f, b6f = _fit_logistic_signed(X6[train], y6[train], prior6, l2=1.0)
            w6_folds.append(round(float(w6f[5]), 3))
            bte = float(y6[test].mean()) or 1.0
            for score, store_ in ((1.0 / (1.0 + np.exp(-(X5[test] @ w5f + b5f))), fit5_l),
                                  (1.0 / (1.0 + np.exp(-(X6[test] @ w6f + b6f))), fit6_l),
                                  (hand_score[test], hand_l)):
                fire = score >= np.quantile(score, 2 / 3)
                if int(fire.sum()) >= 20:
                    store_.append(float(y6[test][fire].mean()) / bte)
        fit5 = round(float(np.mean(fit5_l)), 2) if fit5_l else None
        fit6 = round(float(np.mean(fit6_l)), 2) if fit6_l else None
        hand = round(float(np.mean(hand_l)), 2) if hand_l else None
        wfull6, _bf6 = _fit_logistic_signed(X6, y6, prior6, l2=1.0)
        g2 = bool(fit6 is not None and hand is not None
                  and fit6 > hand + 0.05 and (fit5 is None or fit6 > fit5)
                  and float(wfull6[5]) > 0.02)
        inc.update({"base_rate": round(float(y6.mean()), 3),
                    "oos_lift_hand5": hand, "oos_lift_fit5": fit5, "oos_lift_fit6": fit6,
                    "w6_full_fit": round(float(wfull6[5]), 3), "w6_by_fold": w6_folds})
    proxy["g2_incremental"] = {"pass": g2, **inc}
    proxy["verdict"] = ("proxy_supports" if (g1 and g2)
                        else "proxy_redundant_with_breadth" if g1 else "proxy_no_signal")

    verdict = ("pit_history_exists_run_real_study" if audit.get("usable_pit_history")
               else "no_pit_history_accrue")
    return {"universe": "proxy_spdr_sectors",
            "preregistered": "research/LABEL_FALTERING_PHASE0.md#B2",
            "n_trials": led.effective_n("baskets_conviction_demotion"),
            "pit_audit": audit, "accrual_spec": accrual, "proxy": proxy,
            "verdict": verdict,
            "note": "The proxy health composite is a PRICE stand-in for the conviction "
                    "score's price legs — it can set the prior for the accrued re-run but "
                    "can never ship the demotion leg. Not wired in this task."}


# --------------------------------------------------------------------------- #
# B3 — allocation-rank modulation for recent absolute drawdown (rank_dd_modulation_fit)
# --------------------------------------------------------------------------- #
def _rotation_book_dd_demote(P: pd.DataFrame, thresh: float, top_n: int = 4,
                             lookback: int = 12, trend_ma: int = 200) -> pd.DataFrame:
    """_rotation_book with the pre-registered demotion: at each monthly decision, a
    candidate whose trailing 21d ABSOLUTE return <= thresh is excluded from selection
    (the next eligible name refills the slot; unfilled slots sit in cash). This is the
    rank-time analogue of de-ranking a leader in a sharp current drawdown — exactly the
    window narrative_rotation's SKIP_D=21 blinds."""
    M = P.resample("ME").last()
    mom = M.pct_change(lookback) - M.pct_change(1)
    above = (P > P.rolling(trend_ma, min_periods=trend_ma // 2).mean())
    r21m = P.pct_change(21, fill_method=None).resample("ME").last()
    w = pd.DataFrame(0.0, index=M.index, columns=P.columns)
    for dt in M.index[max(lookback, 10):]:
        m = mom.loc[dt].dropna()
        ab = above.loc[:dt]
        if ab.empty or m.empty:
            continue
        m = m[ab.iloc[-1].reindex(m.index).fillna(False)]
        rr = r21m.loc[dt].reindex(m.index)
        m = m[~(rr <= thresh).fillna(False)]
        top = m.sort_values(ascending=False).head(top_n).index
        if len(top):
            w.loc[dt, top] = 1.0 / top_n
    return w.reindex(P.index, method="ffill").fillna(0.0)


def _sharpe_diff_ci(strat_net: pd.Series, base_net: pd.Series, block: int = 21,
                    B: int = 4000, seed: int = 13) -> dict:
    """Paired circular-block bootstrap CI of the annualized Sharpe DIFFERENCE
    (strat − base). Lower bound > 0 => a real risk-adjusted improvement; upper bound < 0
    => a real degradation (the reversal-noise signature)."""
    a = strat_net.dropna(); b = base_net.reindex(a.index).fillna(0.0)
    ra, rb = a.to_numpy(float), b.to_numpy(float); n = len(ra)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / block)); grid = np.arange(block)

    def _sh(x: np.ndarray) -> float:
        sd = x.std()
        return float(x.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan

    diffs = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        ridx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        diffs[k] = _sh(ra[ridx]) - _sh(rb[ridx])
    diffs = diffs[np.isfinite(diffs)]
    if len(diffs) < 100:
        return {}
    lo, med, hi = (float(np.percentile(diffs, p)) for p in (2.5, 50, 97.5))
    return {"sharpe_diff_ci": [round(lo, 3), round(med, 3), round(hi, 3)],
            "real_improvement": bool(lo > 0), "real_degradation": bool(hi < 0), "n": n}


def run_rank_dd_modulation(region: str = "us") -> dict:
    """Does demoting a ranked leader in a sharp recent absolute drawdown improve the
    allocation backtest, or does it re-import the short-term-reversal noise SKIP_D=21
    exists to avoid? Thresholds pre-declared; nothing fitted."""
    from engine import active_alloc as aa
    P = sector_prices(region, monthly=False)
    if P.empty or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    bill = _daily_bill(P.index)
    led = TrialLedger()
    led.log_grid([{"r21_demote": x} for x in RDM_GRID], family="baskets_rank_dd_mod",
                 info_cutoff="2026-07-02", source="calibrate_baskets:rank_dd_modulation")
    led.log_declared_budget(12, family="baskets_rank_dd_mod",
                            reason="rank-modulation variants considered: r21 vs dd-from-63d-high "
                                   "/ exclude-vs-downweight / refill rules")

    def bt(w, prices=P, b=bill):
        return aa.backtest_portfolio(w, prices, b, cost_bps=SZ_COST_BPS)

    base = bt(_rotation_book(P))
    base_sh, base_dd = _ann_sharpe(base["net"]), _maxdd_ret(base["net"])
    cells = {}
    for x in RDM_GRID:
        mod = bt(_rotation_book_dd_demote(P, x))
        sh, dd = _ann_sharpe(mod["net"]), _maxdd_ret(mod["net"])
        shci = _sharpe_diff_ci(mod["net"], base["net"])
        ddci = _dd_reduction_ci(mod["net"], base["net"])
        halves = {}
        for hn, mask in {"pre2013": P.index < LF_SPLIT, "post2013": P.index >= LF_SPLIT}.items():
            sub = P[mask]
            if len(sub) < 400:
                continue
            sb = _daily_bill(sub.index)
            mm = aa.backtest_portfolio(_rotation_book_dd_demote(sub, x), sub, sb, cost_bps=SZ_COST_BPS)
            bb = aa.backtest_portfolio(_rotation_book(sub), sub, sb, cost_bps=SZ_COST_BPS)
            halves[hn] = round(_ann_sharpe(mm["net"]) - _ann_sharpe(bb["net"]), 3)
        med = (shci.get("sharpe_diff_ci") or [None, None, None])[1]
        go = bool(shci.get("real_improvement")
                  or (ddci.get("favorable") and med is not None and med >= -0.02))
        cells[f"{x:+.0%}"] = {
            "sharpe": round(sh, 3), "maxdd_pct": round(dd * 100, 1), "cagr": mod.get("cagr"),
            "sharpe_diff_ci": shci, "dd_reduction_ci": ddci, "split_half_sharpe_diff": halves,
            "go": go,
            "verdict": ("ship_rank_modulation" if go
                        else "reversal_noise_reimported" if shci.get("real_degradation")
                        else "no_edge")}
    prim = cells.get(f"{RDM_PRIMARY:+.0%}", {})
    return {"universe": "proxy_spdr_sectors",
            "span": [str(P.index.min().date()), str(P.index.max().date())],
            "preregistered": "research/LABEL_FALTERING_PHASE0.md#B3",
            "n_trials": led.effective_n("baskets_rank_dd_mod"), "cost_bps": SZ_COST_BPS,
            "grid_pct": [round(100 * x) for x in RDM_GRID],
            "primary_cell_pct": round(100 * RDM_PRIMARY),
            "base": {"sharpe": round(base_sh, 3), "maxdd_pct": round(base_dd * 100, 1),
                     "cagr": base.get("cagr")},
            "cells": cells, "verdict": prim.get("verdict", "thin"),
            "note": "Verdict from the pre-declared primary cell; sensitivity cells reported. "
                    "Not wired into rank_themes()/allocate() in this task."}


def _print_label_faltering(esc: dict, conv: dict, rdm: dict) -> None:
    print("\n=== LABEL-FALTERING PHASE-0 (pre-registered research/LABEL_FALTERING_PHASE0.md) ===")
    if esc.get("error"):
        print(f"  B1 abs-escape: {esc['error']}")
    else:
        print(f"  B1 abs-escape (in-set n {esc['n_inset']}, base P(dd<-8%) {esc['base_rate_inset']}):")
        for k, c in esc.get("cells", {}).items():
            if c.get("verdict") == "thin":
                print(f"    X={k}: thin (n_fired {c.get('n_fired')})"); continue
            print(f"    X={k}: n_fired {c['n_fired']}  hit {c['hit_fired']}  lift {c['lift']} "
                  f"CI {c['lift_ci']}  t_dd {c['t_dd_paired'].get('t')}  "
                  f"t_ret {c['t_ret_paired'].get('t')}  med fwd ret {c['ret21_med_fired_pct']}%  "
                  f"→ {c['verdict']}")
        print(f"    >>> B1 VERDICT (primary {esc.get('primary_cell_pct')}%): {esc.get('verdict')}")
    if conv.get("error"):
        print(f"  B2 conviction-demotion: {conv['error']}")
    else:
        au = conv.get("pit_audit", {})
        print(f"  B2 conviction-demotion: usable PIT history = {au.get('usable_pit_history')}")
        px = conv.get("proxy", {})
        g1p, g2p = px.get("g1_standalone", {}), px.get("g2_incremental", {})
        print(f"    proxy: events {px.get('n_events')}  G1 lift {g1p.get('lift')} CI {g1p.get('lift_ci')} "
              f"pass={g1p.get('pass')}  G2 fit6 {g2p.get('oos_lift_fit6')} vs fit5 "
              f"{g2p.get('oos_lift_fit5')} w6 {g2p.get('w6_full_fit')} pass={g2p.get('pass')} "
              f"→ {px.get('verdict')}")
        print(f"    >>> B2 VERDICT: {conv.get('verdict')}")
    if rdm.get("error"):
        print(f"  B3 rank-modulation: {rdm['error']}")
    else:
        b = rdm.get("base", {})
        print(f"  B3 rank-modulation (base Sharpe {b.get('sharpe')} MaxDD {b.get('maxdd_pct')}%):")
        for k, c in rdm.get("cells", {}).items():
            print(f"    X={k}: Sharpe {c['sharpe']}  MaxDD {c['maxdd_pct']}%  "
                  f"ΔSharpe CI {c['sharpe_diff_ci'].get('sharpe_diff_ci')}  "
                  f"ΔDD CI {c['dd_reduction_ci'].get('dd_reduction_pp_ci')}  "
                  f"halves {c['split_half_sharpe_diff']}  → {c['verdict']}")
        print(f"    >>> B3 VERDICT (primary {rdm.get('primary_cell_pct')}%): {rdm.get('verdict')}")


def main_label_faltering() -> int:
    """Standalone entry (`--label-faltering`): run ONLY the three pre-registered B1/B2/B3
    studies and merge their verdict blocks ADDITIVELY into baskets_calibration.json under
    'abs_escape_fit' / 'conviction_demotion_fit' / 'rank_dd_modulation_fit' — existing
    keys are never disturbed."""
    log.info("running B1 absolute-escape kill-test…")
    esc = run_abs_escape("us")
    log.info("running B2 conviction-demotion PIT audit + proxy…")
    conv = run_conviction_demotion("us")
    log.info("running B3 rank-modulation A/B…")
    rdm = run_rank_dd_modulation("us")
    _print_label_faltering(esc, conv, rdm)
    p = config.data_dir() / "strategies" / "baskets_calibration.json"
    try:
        d = json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001 — a corrupt file must not block the additive write
        d = {}
    d["abs_escape_fit"] = esc
    d["conviction_demotion_fit"] = conv
    d["rank_dd_modulation_fit"] = rdm
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, default=str))
    log.info("wrote %s (abs_escape_fit + conviction_demotion_fit + rank_dd_modulation_fit, additive)", p)
    return 0


# --------------------------------------------------------------------------- #
# LIVE universe — full-fidelity labels, descriptive context only (never a gate)
# --------------------------------------------------------------------------- #
def run_live(region: str = "us") -> dict:
    """Reconstruct the FULL-fidelity live labels point-in-time on the ~3y, 25-basket tape
    (real member breadth) and run the same event study, pooled across baskets. Flagged
    underpowered + hindsight-curated — context only. Best-effort: returns {error} on any
    shortfall rather than breaking the proxy verdict."""
    try:
        from engine import group_flow, theme_scoring as TS
        from engine.baskets import _ew_level
        s = group_flow._setup()
        if s is None:
            return {"error": "no live setup"}
        closes, rets, idx, bench = s["closes"], s["rets"], s["idx"], s["bench"]
        cfg = group_flow._cfg()
        bdict = s["mem"]["baskets"]
        items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
        bench_v = bench.to_numpy()
        events = {k: [] for k in ("emerging", "dominant", "fading", "deteriorating", "neutral")}
        n_baskets = 0
        for bid, b in items:
            members = b.get("members", [])
            present = [m["ticker"] for m in members if m["ticker"] in rets.columns]
            if len(present) < 3:
                continue
            lvl = _ew_level(rets, members, idx)
            if lvl.dropna().empty:
                continue
            mask = pd.DataFrame(False, index=idx, columns=present)
            for m in members:
                t = m["ticker"]
                if t not in present:
                    continue
                act = np.asarray(idx >= pd.Timestamp(m["added"]))
                if m.get("removed"):
                    act = act & np.asarray(idx < pd.Timestamp(m["removed"]))
                mask[t] = act
            mc_closes = closes[present].where(mask)
            prep = group_flow.prep_group(mc_closes, lvl, bench, cfg)
            if prep is None:
                continue
            lvl_v = lvl.to_numpy()
            n_baskets += 1
            for i in range(max(cfg["min_history_d"], 200), len(idx) - max(FWD_H) - 1, STEP):
                fp = group_flow.fingerprint_at(prep, i, cfg)
                if fp is None:
                    continue
                trend = _trend_leg(_rel(lvl_v, bench_v, i, 5), _rel(lvl_v, bench_v, i, 20),
                                   _rel(lvl_v, bench_v, i, 60), fp.get("accel_z"))
                bl, bd = TS._breadth_leg(mc_closes, i, fp)
                il, _id = TS._impulse_leg(rets[present].where(mask), mc_closes, i)
                cp, _cw = TS._crowding_pen(fp, {"breadth": None}, None)
                raw = (WEIGHTS["trend"] * trend + WEIGHTS["breadth"] * bl
                       + WEIGHTS["impulse"] * il - WEIGHTS["crowding"] * cp)
                score = int(round(50 + 50 * float(np.clip(raw, -1, 1))))
                perf = {"5d": {"rel": _rel(lvl_v, bench_v, i, 5)},
                        "20d": {"rel": _rel(lvl_v, bench_v, i, 20)},
                        "60d": {"rel": _rel(lvl_v, bench_v, i, 60)}}
                d5 = _rel(lvl_v, bench_v, i, 5)   # single 5d rel — matches theme_scoring
                lab = _label(score, fp, perf, bd, d5)
                fr21, fr63 = _fwd_rel(lvl_v, bench_v, i, 21), _fwd_rel(lvl_v, bench_v, i, 63)
                dd21, dd63 = _fwd_dd(lvl_v, i, 21), _fwd_dd(lvl_v, i, 63)
                if np.isfinite(fr21):
                    events[lab].append((fr21, fr63, dd21, dd63, i))
        claim = {"emerging": "continuation", "dominant": "continuation",
                 "fading": "risk", "deteriorating": "risk", "neutral": "continuation"}
        labels = _event_study(events, claim)
        return {"universe": "live_baskets", "n_baskets": n_baskets,
                "span": [str(idx.min().date()), str(idx.max().date())],
                "labels": labels,
                "warning": "HINDSIGHT-curated membership, ~3y, ~25 names — severely "
                           "underpowered + survivorship-biased. Context only, NOT a validation."}
    except Exception as e:  # noqa: BLE001 — live leg is best-effort context
        log.warning("live universe skipped: %s", e)
        return {"error": str(e)}


def _rel(lvl: np.ndarray, bench: np.ndarray, i: int, h: int) -> float | None:
    if i - h < 0 or i >= len(lvl):
        return None
    v = (lvl[i] / lvl[i - h] - 1.0) - (bench[i] / bench[i - h] - 1.0)
    return float(v) if np.isfinite(v) else None


# --------------------------------------------------------------------------- #
def _verdict(proxy: dict) -> dict:
    """Distil the proxy event study into the honest per-signal verdict the page cites."""
    labs = proxy.get("labels", {})
    def lv(name):
        r = labs.get(name, {})
        return r.get("verdict", "thin"), r.get("t_hac"), r.get("mean_pct"), r.get("n")
    out = {}
    for name in ("emerging", "fading", "deteriorating", "dominant"):
        v, t, mean, n = lv(name)
        out[name] = {"verdict": v, "t_hac": t, "mean_pct": mean, "n": n}
    ic = (proxy.get("rank_ic", {}).get("21d", {}) or {}).get("mean_ic")
    out["cross_sectional_momentum"] = {
        "mean_ic_21d": ic,
        "verdict": "no_return_edge" if (ic is None or abs(ic) < 0.03) else "weak_edge"}
    gate = proxy.get("trend_gate_drawdown", {})
    out["trend_gate"] = {"verdict": "drawdown_control" if gate.get("shallower_when_above")
                         else "inconclusive", **gate}
    ag = proxy.get("alert_gate", {})
    out["alert_firing_gate"] = {
        "risk": (ag.get("risk", {}) or {}).get("gate"),
        "entry": (ag.get("entry", {}) or {}).get("gate"),
        "note": "Fire the alert only above the OUT-OF-SAMPLE min_confidence (a None gate means "
                "the lift CI did not clear 1.0 — keep firing but DON'T claim added precision). "
                "Display the Platt-recalibrated probability as the confidence number; show "
                "sub-threshold firings with a low-confidence badge (audit trail preserved)."}
    any_go = any(out[n]["verdict"] == "measurable_edge" for n in ("emerging", "fading",
                 "deteriorating", "dominant"))
    out["GO"] = bool(any_go or (ag.get("risk", {}) or {}).get("verdict") == "calibratable"
                     or (ag.get("entry", {}) or {}).get("verdict") == "calibratable")
    return out


def _print_proxy(proxy: dict) -> None:
    print(f"\n=== PROXY ({proxy.get('n_assets')} sector ETFs, "
          f"{proxy.get('span', ['?', '?'])[0]}→{proxy.get('span', ['?', '?'])[1]}) ===")
    print(f"{'label':14s} {'n':>6s} {'kind':>13s} {'mean%':>7s} {'t_HAC':>6s} "
          f"{'hit':>5s} {'BHq':>5s} verdict")
    for lab, r in proxy.get("labels", {}).items():
        if r.get("verdict") == "thin":
            print(f"{lab:14s} {r.get('n', 0):>6d}  (thin)"); continue
        print(f"{lab:14s} {r['n']:>6d} {r.get('kind', ''):>13s} {r.get('mean_pct', 0):>7} "
              f"{str(r.get('t_hac')):>6} {str(r.get('hit')):>5} {str(r.get('bh_q', '—')):>5} "
              f"{r.get('verdict')}")
    ic = proxy.get("rank_ic", {})
    print(f"  rank-IC score→fwd: 21d {ic.get('21d', {}).get('mean_ic')} "
          f"(t {ic.get('21d', {}).get('t_hac')}), 63d {ic.get('63d', {}).get('mean_ic')}")
    g = proxy.get("trend_gate_drawdown", {})
    if g:
        print(f"  trend gate dd21: above {g.get('above_dd21_med_pct')}% vs below "
              f"{g.get('below_dd21_med_pct')}%  (shallower_when_above={g.get('shallower_when_above')})")
    for k in ("risk", "entry"):
        a = proxy.get("alert_gate", {}).get(k, {})
        gt = a.get("gate") or a.get("gate_rejected")
        if gt:
            tag = a.get("verdict")
            print(f"  {k} gate: fire≥{gt['min_confidence']} → OOS precision {gt['precision_oos']} "
                  f"(base {a.get('base_rate')}, lift {gt.get('lift_oos')} CI {gt.get('lift_ci')}, "
                  f"n {gt['n_fired_oos']}) [{tag}{'' if a.get('gate') else ' — gate not surfaced'}]")
        else:
            print(f"  {k} gate: {a.get('verdict')} (skill_recal {a.get('skill_recal')})")


def _print_sizing(s: dict) -> None:
    if s.get("error"):
        print(f"\n=== SIZING: {s['error']} ==="); return
    print(f"\n=== SIZING / REGIME ({s.get('span', ['?', '?'])[0]}→{s.get('span', ['?', '?'])[1]}, "
          f"net {s.get('cost_bps')}bps) ===")
    vt, base, br = s.get("vt", {}), s.get("base", {}), s.get("brake", {})
    print(f"  base book (EW dual-mom):   Sharpe {base.get('sharpe')}  MaxDD {base.get('maxdd_pct')}%  CAGR {base.get('cagr')}")
    print(f"  vol-target book (E1):      Sharpe {vt.get('sharpe')}  MaxDD {vt.get('maxdd_pct')}%  CAGR {vt.get('cagr')}  "
          f"avg_gross {vt.get('avg_gross')}  turn/yr {vt.get('turnover_yr')}")
    print(f"  trend-brake (matched):     Sharpe {br.get('sharpe')}   → vol-target beats brake: {s.get('beats_brake')}")
    print(f"  DSR (best-of-{s.get('n_trials')}-grid): {s.get('dsr')}  [{s.get('dsr_verdict')}]")
    print(f"  DD-reduction vs base CI:   {s.get('dd_reduction_ci', {}).get('dd_reduction_pp_ci')}pp  "
          f"favorable {s.get('dd_reduction_ci', {}).get('favorable')}")
    print(f"  split-half DD-cut both:    {s.get('dd_cut_both_halves')}  ({s.get('split_half')})")
    print(f"  leave-one-crisis-out DDpp: {s.get('loo_crisis')}")
    rt = s.get("regime_throttle", {})
    print(f"  E2 regime throttle:        verdict {rt.get('verdict')}  Sharpe {rt.get('sharpe')}  MaxDD {rt.get('maxdd_pct')}%  "
          f"(DD vs vt CI {rt.get('dd_reduction_vs_vt_ci', {}).get('dd_reduction_pp_ci')})")
    print(f"  >>> SIZING VERDICT: {s.get('verdict')}  (default {s.get('default')})")


def main(do_live: bool = False) -> int:
    out = {"schema": "baskets_calibration.v1", "region": "us",
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "fwd_horizons_d": list(FWD_H), "step_d": STEP, "dd_risk": DD_RISK}
    log.info("running PROXY universe (27y SPDR sectors)…")
    out["proxy"] = run_proxy("us")
    _print_proxy(out["proxy"])

    log.info("running SIZING / REGIME backtest (vol-target + throttle)…")
    out["sizing"] = run_sizing("us")
    _print_sizing(out["sizing"])

    log.info("running BUILD#4 residual-momentum A/B…")
    out["ranking_ab"] = run_ranking_ab("us")
    ab = out["ranking_ab"]
    if not ab.get("error"):
        print(f"\n=== RESIDUAL-MOMENTUM A/B (both trend-gated, n_trials {ab.get('n_trials')}) ===")
        print(f"  total-mom book:    Sharpe {ab['total']['sharpe']}  MaxDD {ab['total']['maxdd_pct']}%  skew {ab['total']['skew']}")
        print(f"  residual-mom book: Sharpe {ab['residual']['sharpe']}  MaxDD {ab['residual']['maxdd_pct']}%  skew {ab['residual']['skew']}")
        print(f"  DD-reduction (resid vs total) CI: {ab['dd_reduction_vs_total_ci'].get('dd_reduction_pp_ci')}  → {ab['verdict']}")

    log.info("running E1-risk rollover_risk weight-fit…")
    out["rollover_fit"] = run_rollover_fit("us")
    rf = out["rollover_fit"]
    if not rf.get("error"):
        print(f"\n=== ROLLOVER WEIGHT-FIT (n {rf['n']}, base {rf['base_rate']}, n_trials {rf['n_trials']}) ===")
        print(f"  legs:           {rf['legs']}")
        print(f"  hand weights:   {rf['hand_weights']}")
        print(f"  fitted weights: {rf['fitted_weights']}")
        print(f"  OOS top-third lift: hand {rf['oos_lift_hand']}  vs fitted {rf['oos_lift_fitted']}  "
              f"(reliability skill {rf['reliability_skill']})  → {rf['verdict']}")

    log.info("running P2b breadth-divergence Phase-0 kill-test…")
    out["breadth_divergence_fit"] = run_breadth_divergence("us")
    _print_bd(out["breadth_divergence_fit"])
    if do_live:
        log.info("running LIVE universe (3y baskets, descriptive)…")
        out["live"] = run_live("us")
        if "labels" in out.get("live", {}):
            print("\n=== LIVE (descriptive, underpowered) ===")
            for lab, r in out["live"]["labels"].items():
                if r.get("verdict") != "thin":
                    print(f"{lab:14s} n {r['n']:>5d} {r.get('kind', ''):>13s} "
                          f"mean {r.get('mean_pct')}% t {r.get('t_hac')} → {r.get('verdict')}")
    out["verdict"] = _verdict(out["proxy"])
    print(f"\n  GO (something measurable/calibratable): {out['verdict']['GO']}")

    p = config.data_dir() / "strategies" / "baskets_calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", p)
    return 0


if __name__ == "__main__":
    # `--bd` runs ONLY the P2b breadth-divergence Phase-0; `--label-faltering` runs ONLY
    # the pre-registered B1/B2/B3 studies (research/LABEL_FALTERING_PHASE0.md). Both merge
    # their verdict blocks additively into the existing calibration JSON (the full main()
    # rerun is ~minutes).
    if "--label-faltering" in sys.argv:
        sys.exit(main_label_faltering())
    sys.exit(main_bd() if "--bd" in sys.argv else main("--live" in sys.argv))
