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
SZ_N_TRIALS = len(SZ_VOL_WINS) * len(SZ_TARGETS) * len(SZ_CAPS)   # 36 — honest DSR haircut
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
                   trend_ma: int = 200) -> pd.DataFrame:
    """Daily EW weights of the validated dual-momentum book: monthly select the top_n by
    (lookback-1)m relative momentum among names ABOVE their own trend_ma, equal-weight,
    daily hold; idle slots (fewer than top_n trend) sit in cash. Causal (month-end decision
    uses data through that month-end; backtest_portfolio applies the next-bar lag)."""
    M = P.resample("ME").last()
    mom = M.pct_change(lookback) - M.pct_change(1)
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

    # DSR over the honest 36-config grid (vol_win x target x cap)
    srs, best = [], None
    for a in SZ_VOL_WINS:
        for t in SZ_TARGETS:
            for c in SZ_CAPS:
                m = V.ret_moments(bt(_book_voltarget(ew, P, a, t, c))["net"])
                if m is None:
                    continue
                srs.append(m[0])
                if best is None or m[0] > best[0]:
                    best = (m[0], m[1], m[2], m[3], (a, t, c))
    sr_var = float(np.var(srs, ddof=1)) if len(srs) > 1 else None
    dsr = V.deflated_sharpe(best[0], best[1], best[2], best[3], SZ_N_TRIALS,
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
            "best_cfg": best[4] if best else None, "n_trials": SZ_N_TRIALS, "cost_bps": SZ_COST_BPS,
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
    sys.exit(main("--live" in sys.argv))
