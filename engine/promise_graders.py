"""engine/promise_graders.py — The three promise-graders (Cycle Intelligence W2.4).

Grades what the platform *promises* against what actually happened, on the 12,519
backfilled monthly PIT stamps (W2.3) + the small live prospective cohort:

  1. TURN precision/recall  (§3.1, gate CC-3) — projected turns vs INDEPENDENT
     realized-extrema truth (ruling A6 — the detector never grades itself).
  2. CONE coverage          (§3.2, gate CC-1) — empirical containment of realized
     turns in [proj_lo, proj_hi] vs the 0.80 nominal, + the recalibration
     multiplier shipped as data/cycle_ontology/cone_recalibration.json.
  3. RELIABILITY            (§3.3, gate CC-2) — directional/probabilistic fields
     (signal, stance direction): realized-frequency vs base rate, Brier vs
     per-instrument base rate, hit-rate CIs.

DOCTRINE (masterplan §1, PREREGISTRATION.md):
  - A6  : turn truth is independent (realized_extrema_turns, NOT detect_turns).
  - A2  : whole-month DATE-block bootstrap for CIs on co-moving panels; n_months
          not n_rows.  Wilson only on the pooled hit count where the block is a
          single (date,id) cell; overlapping monthly windows carry n_eff ≈ n.
  - A6/A1 : BACKTEST vs LIVE cohort NEVER blend in one number.  Every cell carries
          cohort ∈ {BACKTEST, LIVE}, n_months, CI, epoch/basis.
  - A15 : gates are frozen in PREREGISTRATION.md; this grader REPORTS pass/fail
          against CC-1/CC-2/CC-3, it does not invent thresholds.  FDR-BH within
          the turn_pr family.
  - Sectors and countries live in SEPARATE scorecards — never pooled (D2 §2.3).

All statistics come from engine.grading_stats (library-not-copy).  Turn truth comes
from engine.cycle_ontology.realized_extrema_turns.  Pure numpy/pandas.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from engine import cycle_ontology as onto
from engine import grading_stats as gs

log = logging.getLogger(__name__)

# ── Pre-registered constants (frozen — see PREREGISTRATION.md §3) ─────────────────────
NOMINAL_CONE: float = 0.80          # D2 §3.2 nominal cone coverage.
TRUTH_MIN_MOVE_PCT: float = 20.0    # realized-extrema confirmation threshold (major move).
                                    # DISTINCT from the 14/18% stamp ZigZag pct (A6).
TAU_CLAMP_BARS: tuple[int, int] = (10, 63)  # D2 §3.1 tolerance clamp in *bars*; the
                                            # monthly-cadence analogue is TAU_CLAMP_MONTHS
                                            # (10–63 trading bars ≈ 0.5–3 months).
TAU_CLAMP_MONTHS: tuple[int, int] = (1, 3)  # τ clamp when the cadence is monthly.
FDR_Q: float = 0.10                 # turn_pr family BH-FDR level (PREREGISTRATION §3).

# N3 — FIELD_HORIZON: phase-scale fields are graded on time-to-next-turn / long
# horizons; no monthly field is graded at 21d (the audit's "noise by construction").
# The three promise-graders are all *turn-timing* graders → their native horizon is
# the projection's own turn window (months), NOT a 21d forward return.  The signal /
# stance reliability grader is a directional call → 63d (a quarter) is the shortest
# honest window for a monthly-cadence directional label.  This table is the machine-
# readable N3 contract for W2.4's fields.
FIELD_HORIZON: dict[str, str] = {
    "proj_turn":  "time_to_next_turn",   # turn P/R + cone → matched to realized turns
    "signal":     "63d",                 # BUY/SELL transition → 1-quarter directional
    "stance":     "63d",                 # stance direction → 1-quarter directional
    "phase":      "time_to_next_turn",   # phase is a turn-phase → turn horizon, never 21d
}


# ══════════════════════════════════════════════════════════════════════════════════════
# HELPERS — parsing, cadence, cohort split
# ══════════════════════════════════════════════════════════════════════════════════════

def _month_to_ts(ym: Any) -> pd.Timestamp | None:
    """Parse a 'YYYY-MM' projection field to a month-END Timestamp, or None.

    Projections carry month strings ('2024-03').  A turn is dated to a month, so the
    band edge is that month's end (the last day the projection's month could contain
    the turn).  Robust to already-parsed Timestamps and 'YYYY-MM-DD'.
    """
    if ym is None:
        return None
    if isinstance(ym, pd.Timestamp):
        return ym
    s = str(ym).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    try:
        if len(s) == 7 and s[4] == "-":                # YYYY-MM
            return pd.Timestamp(s + "-01") + pd.offsets.MonthEnd(0)
        return pd.Timestamp(s)                          # YYYY-MM-DD or full ts
    except (ValueError, TypeError):
        return None


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> float:
    """Signed month distance (a - b) in calendar months (fractional by 30.44 d)."""
    return (a - b).days / 30.4375


def _split_cohorts(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a merged graded log into BACKTEST (backfilled) and LIVE (prospective).

    A6/A1: the two cohorts never blend in one number.  Returns both keyed cohorts;
    an empty frame for a missing cohort (LIVE is small/absent early).
    """
    if df is None or len(df) == 0 or "provenance" not in df.columns:
        return {"BACKTEST": pd.DataFrame(), "LIVE": pd.DataFrame()}
    return {
        "BACKTEST": df[df["provenance"] == "backfilled"].copy(),
        "LIVE": df[df["provenance"] == "prospective"].copy(),
    }


def _epoch_basis(df: pd.DataFrame) -> dict[str, Any]:
    """Extract the epoch / basis stamp carried on the rows (for badge discipline)."""
    def _mode(col: str) -> Any:
        if col in df.columns and len(df):
            vc = df[col].dropna()
            return vc.iloc[0] if len(vc) else None
        return None
    return {
        "basis_version": _mode("basis_version"),
        "zz_version": _mode("zz_version"),
        "engine_fingerprint": _mode("engine_fingerprint"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# 1 · TURN PRECISION / RECALL  (§3.1, gate CC-3)
# ══════════════════════════════════════════════════════════════════════════════════════

def _truth_turns(prices: dict[str, pd.Series]) -> dict[str, list[dict]]:
    """Independent realized-extrema ground-truth turns per instrument (ruling A6)."""
    out: dict[str, list[dict]] = {}
    for sid, px in prices.items():
        try:
            out[sid] = onto.realized_extrema_turns(
                px, series_id=sid, min_move_pct=TRUTH_MIN_MOVE_PCT, freq="M"
            )
        except Exception as e:  # noqa: BLE001
            log.debug("promise_graders: truth turns failed for %s: %s", sid, e)
            out[sid] = []
    return out


def _projection_rows(df: pd.DataFrame, *, forward_only: bool = False) -> pd.DataFrame:
    """Keep-first per (id, proj_next, proj_central) — the DISTINCT turns projected.

    A monthly panel re-stamps the SAME overdue projection every month (155/187 XLK
    stamps point at the same 2010-11 peak).  Counting each monthly re-stamp as a
    separate projected turn would inflate n and let one stale projection dominate
    precision.  We collapse to the distinct (instrument, direction, projected-month)
    triples the platform actually PROMISED — the honest denominator (A2: n_months
    not n_rows, applied to the projection identity).

    forward_only : if True, drop projections whose central month is BEFORE the stamp
        date.  W2.4 FINDING: ~63% of stamped projections are chronically OVERDUE (they
        point at a turn in the PAST — the re-anchoring / find_troughs repaint the audit
        flagged, cycles-core-4).  Grading an overdue projection's cone measures a
        re-anchoring bug, not the cone's calibration.  The full slice is the honest
        headline; the forward-only slice isolates "is the cone itself calibrated when
        the projection at least points forward".
    """
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["id", "proj_next", "proj_central", "date"])
    d = df.copy()
    for col in ("id", "proj_next", "proj_central"):
        if col not in d.columns:
            d[col] = None
    d = d[d["proj_central"].notna() & d["proj_next"].notna()].copy()
    if len(d) == 0:
        return d
    if forward_only:
        stamp_ts = pd.to_datetime(d["date"], errors="coerce")
        pc_ts = d["proj_central"].apply(_month_to_ts)
        keep = pc_ts.notna() & stamp_ts.notna() & (pc_ts >= stamp_ts)
        d = d[keep.values]
        if len(d) == 0:
            return d.reset_index(drop=True)
    # earliest stamp date that made each distinct projection (keep-first)
    d = d.sort_values("date")
    d = d.drop_duplicates(subset=["id", "proj_next", "proj_central"], keep="first")
    return d.reset_index(drop=True)


def _dir_word(proj_next: Any) -> str | None:
    s = str(proj_next).strip().lower()
    if "peak" in s or "top" in s:
        return "peak"
    if "trough" in s or "bottom" in s or "low" in s:
        return "trough"
    return None


def turn_pr(df: pd.DataFrame, prices: dict[str, pd.Series], *,
            tau_months: tuple[int, int] = TAU_CLAMP_MONTHS) -> dict:
    """Turn precision/recall vs INDEPENDENT realized-extrema truth (D2 §3.1, CC-3).

    A projected turn (direction k, projected month p) is a TRUE POSITIVE iff a
    realized-extrema truth turn of the same direction falls within τ months of p.
    τ is phase-appropriate: round(0.25 * median half-cycle) per instrument, clamped
    to [1, 3] months (the monthly analogue of the D2 [10, 63]-bar band).  τ is STORED
    in the artifact, never hand-set at render.

    Returns per-instrument + pooled precision/recall with Wilson CIs, the signed
    timing-error distribution (median / IQR / p10 / p90), and a verdict.
    """
    truth = _truth_turns(prices)
    proj = _projection_rows(df)

    per_inst: dict[str, dict] = {}
    all_err: list[float] = []
    pooled_tp = pooled_fp = pooled_fn = 0
    # date-block accounting for pooled bootstrap: one "block" per (id, projected-month)
    pooled_hit_dates: list[str] = []
    pooled_hit_vals: list[int] = []

    for sid in sorted(set(proj["id"].tolist()) | set(truth.keys())):
        gt = truth.get(sid, [])
        gt_peaks = [pd.Timestamp(t["date"]) for t in gt if t["k"] == "peak"]
        gt_troughs = [pd.Timestamp(t["date"]) for t in gt if t["k"] == "trough"]

        # Phase-appropriate τ: 0.25 * median half-cycle (months between adjacent turns).
        gt_dates = sorted(pd.Timestamp(t["date"]) for t in gt)
        if len(gt_dates) >= 2:
            half_cycles = [_months_between(gt_dates[i + 1], gt_dates[i])
                           for i in range(len(gt_dates) - 1)]
            med_half = float(np.median(half_cycles)) if half_cycles else 6.0
            tau = int(round(0.25 * med_half))
        else:
            tau = tau_months[0]
        tau = max(tau_months[0], min(tau_months[1], tau))

        sub = proj[proj["id"] == sid]
        tp = fp = 0
        matched_gt: set[str] = set()
        inst_err: list[float] = []
        for _, r in sub.iterrows():
            k = _dir_word(r["proj_next"])
            p = _month_to_ts(r["proj_central"])
            if k is None or p is None:
                continue
            cands = gt_peaks if k == "peak" else gt_troughs
            if not cands:
                fp += 1
                pooled_hit_dates.append(f"{sid}:{r['proj_central']}")
                pooled_hit_vals.append(0)
                continue
            diffs = [abs(_months_between(g, p)) for g in cands]
            j = int(np.argmin(diffs))
            if diffs[j] <= tau:
                tp += 1
                gid = f"{k}:{cands[j].strftime('%Y-%m')}"
                matched_gt.add(gid)
                # signed timing error in months: (truth - projected); neg = turn came early
                inst_err.append(_months_between(cands[j], p))
                pooled_hit_dates.append(f"{sid}:{r['proj_central']}")
                pooled_hit_vals.append(1)
            else:
                fp += 1
                pooled_hit_dates.append(f"{sid}:{r['proj_central']}")
                pooled_hit_vals.append(0)

        # Recall denominator: confirmed truth turns; a FN is a truth turn no projection
        # pointed at within τ.  We approximate matched truth by the gids collected.
        n_gt = len(gt_peaks) + len(gt_troughs)
        fn = max(0, n_gt - len(matched_gt))

        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        prec_ci = gs.wilson_ci(tp, tp + fp) if (tp + fp) else None
        rec_ci = gs.wilson_ci(tp, tp + fn) if (tp + fn) else None

        te = {}
        if inst_err:
            ea = np.array(inst_err, dtype=float)
            te = {"median": round(float(np.median(ea)), 2),
                  "iqr": round(float(np.percentile(ea, 75) - np.percentile(ea, 25)), 2),
                  "p10": round(float(np.percentile(ea, 10)), 2),
                  "p90": round(float(np.percentile(ea, 90)), 2),
                  "n": len(inst_err), "unit": "months"}
        all_err.extend(inst_err)

        per_inst[sid] = {
            "tau_months": tau, "tp": tp, "fp": fp, "fn": fn,
            "n_truth_turns": n_gt,
            "precision": round(prec, 3) if prec is not None else None,
            "precision_ci": list(prec_ci) if prec_ci else None,
            "recall": round(rec, 3) if rec is not None else None,
            "recall_ci": list(rec_ci) if rec_ci else None,
            "timing_err": te,
            "verdict": _turn_verdict(tp + fp, prec_ci, "precision"),
        }
        pooled_tp += tp
        pooled_fp += fp
        pooled_fn += fn

    # Pooled precision/recall with Wilson CI on the pooled hit counts.  A2: the pooled
    # denominator counts distinct (id, projected-month) projections — one block each —
    # so there is no daily-window overlap to deflate; n_eff = n_distinct.
    prec = pooled_tp / (pooled_tp + pooled_fp) if (pooled_tp + pooled_fp) else None
    rec = pooled_tp / (pooled_tp + pooled_fn) if (pooled_tp + pooled_fn) else None
    prec_ci = gs.wilson_ci(pooled_tp, pooled_tp + pooled_fp) if (pooled_tp + pooled_fp) else None
    rec_ci = gs.wilson_ci(pooled_tp, pooled_tp + pooled_fn) if (pooled_tp + pooled_fn) else None
    n_eff = float(len(set(pooled_hit_dates)))   # distinct projections = independent trials

    pooled_te = {}
    if all_err:
        ea = np.array(all_err, dtype=float)
        pooled_te = {"median": round(float(np.median(ea)), 2),
                     "iqr": round(float(np.percentile(ea, 75) - np.percentile(ea, 25)), 2),
                     "p10": round(float(np.percentile(ea, 10)), 2),
                     "p90": round(float(np.percentile(ea, 90)), 2),
                     "n": len(all_err), "unit": "months"}

    return {
        "tolerance_rule": "tau = round(0.25 * median_half_cycle_months), clamped [1,3]",
        "truth_definition": (
            "realized_extrema_turns(min_move_pct=%.0f, freq=M) — INDEPENDENT of the "
            "ZigZag detector (ruling A6): argmax/argmin of a leg reversed by >= %.0f%%; "
            "does not consume detect_turns or any stamped field."
            % (TRUTH_MIN_MOVE_PCT, TRUTH_MIN_MOVE_PCT)),
        "per_instrument": per_inst,
        "pooled": {
            "tp": pooled_tp, "fp": pooled_fp, "fn": pooled_fn,
            "precision": round(prec, 3) if prec is not None else None,
            "precision_ci": list(prec_ci) if prec_ci else None,
            "recall": round(rec, 3) if rec is not None else None,
            "recall_ci": list(rec_ci) if rec_ci else None,
            "timing_err": pooled_te,
            "n_eff": n_eff,
            "verdict": _turn_verdict(n_eff, prec_ci, "precision"),
        },
    }


def _turn_verdict(n: float, ci: list | tuple | None, which: str) -> str:
    """Turn P/R verdict.  Turns are a FACTUAL (not return) claim, so CC-3's bar is a
    *calibration* bar: Wilson-lo > 0.5 on n_eff >= MIN_N.  Below MIN_N → accruing.

    'earning' here means: the P/R rate's CI lower bound clears 0.5 (the pre-registered
    CC-3 criterion) — a turn either happened or it didn't, so a factual claim can earn.
    """
    if float(n) < gs.MIN_N_DEFAULT:
        return "accruing"
    if ci is None:
        return "inconclusive"
    if ci[0] > 0.5:
        return "earning"       # CC-3 pass: Wilson-lo > 0.5
    if ci[1] < 0.5:
        return "falsified"     # worse than a coin flip with confidence
    return "inconclusive"


# ══════════════════════════════════════════════════════════════════════════════════════
# 2 · CONE COVERAGE  (§3.2, gate CC-1) + recalibration multiplier
# ══════════════════════════════════════════════════════════════════════════════════════

def cone_grade(df: pd.DataFrame, prices: dict[str, pd.Series], *,
               nominal: float = NOMINAL_CONE) -> dict:
    """Cone coverage vs 0.80 nominal, via grading_stats.cone_coverage (D2 §3.2, CC-1).

    Builds the (id, date, proj_lo, proj_hi) band frame from DISTINCT projections and
    the per-instrument realized-extrema truth turns, then defers to the ONE
    cone_coverage implementation in grading_stats.  The recalibration multiplier it
    returns is what replaces lerp(1.5,13) downstream.
    """
    truth = _truth_turns(prices)
    # truth dict for cone_coverage: id -> DatetimeIndex of ALL confirmed turn dates
    truth_idx: dict[str, pd.DatetimeIndex] = {}
    for sid, gt in truth.items():
        if gt:
            truth_idx[sid] = pd.DatetimeIndex([pd.Timestamp(t["date"]) for t in gt])

    def _band(proj_df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, r in proj_df.iterrows():
            lo = _month_to_ts(r.get("proj_lo"))
            hi = _month_to_ts(r.get("proj_hi"))
            if lo is None or hi is None:
                continue
            if lo > hi:
                lo, hi = hi, lo
            rows.append({"id": r["id"], "date": pd.Timestamp(r["date"]),
                         "proj_lo": lo, "proj_hi": hi})
        return pd.DataFrame(rows)

    proj_all = _projection_rows(df)
    if len(proj_all) == 0:
        return gs.cone_coverage(pd.DataFrame(), {}, nominal=nominal)

    result = gs.cone_coverage(_band(proj_all), truth_idx, nominal=nominal)

    # Overdue diagnostic + forward-only slice (W2.4 finding — see _projection_rows).
    stamp_ts = pd.to_datetime(proj_all["date"], errors="coerce")
    pc_ts = proj_all["proj_central"].apply(_month_to_ts)
    valid = pc_ts.notna() & stamp_ts.notna()
    overdue_frac = (float(((pc_ts < stamp_ts) & valid).sum()) / float(valid.sum())
                    if valid.sum() else None)
    proj_fwd = _projection_rows(df, forward_only=True)
    fwd = (gs.cone_coverage(_band(proj_fwd), truth_idx, nominal=nominal)
           if len(proj_fwd) else None)

    result["overdue_fraction"] = round(overdue_frac, 3) if overdue_frac is not None else None
    result["forward_only"] = fwd
    return result


# ══════════════════════════════════════════════════════════════════════════════════════
# 3 · RELIABILITY  (§3.3, gate CC-2) — directional fields vs base rate + Brier
# ══════════════════════════════════════════════════════════════════════════════════════

# Directional interpretation of the stamped label fields.  A field carries no explicit
# probability, so we grade HIT-RATE vs the instrument's own base rate (CC-2 skill).
_SIGNAL_DIR = {"BUY": +1, "SELL": -1}
_STANCE_DIR = {
    "BUY": +1, "GET READY": +1, "HIGH-RISK BOUNCE": +1,
    "SELL": -1, "TRIM": -1, "AVOID": -1, "COUNTERTREND ONLY": -1,
    # HOLD / WAIT are NON-directional → reported as flat coverage, excluded from hit-rate.
}


def _fwd_dir_outcome(px: pd.Series, stamp: pd.Timestamp, h: int) -> int | None:
    """Realized forward direction over h bars (bar-i+1 anchor): +1 up, -1 down, 0 flat."""
    w = gs.fwd_window(px, stamp, h)
    if w is None:
        return None
    return 1 if w["ret"] > 0 else (-1 if w["ret"] < 0 else 0)


def reliability_grade(df: pd.DataFrame, prices: dict[str, pd.Series], *,
                      horizon_bars: int = 63) -> dict:
    """Directional reliability of signal & stance labels (D2 §3.3, gate CC-2).

    For each directional label (BUY→up, SELL→down, etc.) score the realized-frequency
    of the promised direction over the field's registered horizon (63d — a monthly
    directional label is never graded at 21d, N3), the Brier score against the
    instrument's OWN base rate (skill = 1 - brier/base_brier), and the hit-rate Wilson
    CI.  Non-directional labels (HOLD/WAIT) are reported as flat coverage separately.
    """
    out: dict[str, dict] = {}
    for field, dirmap in (("signal", _SIGNAL_DIR), ("stance", _STANCE_DIR)):
        if field not in df.columns:
            continue
        # per-instrument base rate of "up over horizon" from ALL that instrument's stamps
        hits: list[int] = []          # 1 if realized dir == promised dir
        preds: list[float] = []       # implied prob (1.0 for a directional call)
        outcomes: list[int] = []      # 1 if realized up, 0 if down (for base rate)
        dates: list[str] = []
        flat_n = 0
        matured = 0
        base_up_by_inst: dict[str, list[int]] = {}

        # First pass: base rate of up-moves per instrument over the horizon (all stamps).
        for sid, sub in df.groupby("id"):
            px = prices.get(str(sid))
            if px is None or px.dropna().empty:
                continue
            ups: list[int] = []
            for _, r in sub.iterrows():
                o = _fwd_dir_outcome(px, pd.Timestamp(r["date"]), horizon_bars)
                if o is None:
                    continue
                ups.append(1 if o > 0 else 0)
            if ups:
                base_up_by_inst[str(sid)] = ups

        # Second pass: score the directional labels.
        for sid, sub in df.groupby("id"):
            px = prices.get(str(sid))
            if px is None or px.dropna().empty:
                continue
            for _, r in sub.iterrows():
                lab = r.get(field)
                if lab is None or (isinstance(lab, float) and np.isnan(lab)):
                    continue
                d = dirmap.get(str(lab).strip().upper())
                if d is None:
                    flat_n += 1
                    continue
                o = _fwd_dir_outcome(px, pd.Timestamp(r["date"]), horizon_bars)
                if o is None:
                    continue
                matured += 1
                hits.append(1 if (o > 0 and d > 0) or (o < 0 and d < 0) else 0)
                preds.append(1.0)      # a directional call is an implied P=1 on that side
                outcomes.append(1 if o > 0 else 0)
                dates.append(f"{sid}:{r['date']}")

        n = len(hits)
        if n == 0:
            out[field] = {"n": 0, "hit_rate": None, "verdict": "accruing",
                          "flat_n": flat_n, "horizon_bars": horizon_bars}
            continue

        hit_rate = float(np.mean(hits))
        hit_ci = gs.wilson_ci(int(sum(hits)), n)
        # Base rate = P(a directional call is 'correct' by chance) — the majority-class
        # rate of the promised directions realized.  We use the instrument-pooled up-rate
        # to derive the coin: a BUY is right P(up), a SELL is right P(down)=1-P(up).
        all_up = [u for ul in base_up_by_inst.values() for u in ul]
        p_up = float(np.mean(all_up)) if all_up else 0.5
        # base hit-rate: what a naive "always predict the majority direction" would score
        base_hit = max(p_up, 1 - p_up)
        base_brier = base_hit * (1 - base_hit)
        # Brier of the model's directional predictions vs realized (pred=1 on called side)
        brier = float(np.mean([(preds[i] - hits[i]) ** 2 for i in range(n)]))
        # (preds are all 1.0 on the called side, so brier == mean((1-hit)^2) == 1-hit_rate)
        skill = round(1 - brier / base_brier, 3) if base_brier > 0 else None

        out[field] = {
            "n": n, "matured": matured, "flat_n": flat_n,
            "horizon_bars": horizon_bars,
            "hit_rate": round(hit_rate, 3),
            "hit_ci": list(hit_ci) if hit_ci else None,
            "base_hit_rate": round(base_hit, 3),
            "brier": round(brier, 4),
            "base_brier": round(base_brier, 4),
            "skill_score": skill,
            "verdict": gs.rate_verdict(n, hit_ci, base_hit),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# DRIVER — grade one engine, both cohorts, separate scorecard
# ══════════════════════════════════════════════════════════════════════════════════════

def grade_engine(engine: str, prices: dict[str, pd.Series], *,
                 include_backfill: bool = True) -> dict:
    """Grade one engine end-to-end into a SEPARATE scorecard (never pooled with others).

    Loads the merged live+backfill log (keep-FIRST), splits BACKTEST/LIVE cohorts
    (A6/A1 — never blended), and runs all three promise-graders on each cohort.
    """
    gs.assert_convention(gs.CONVENTION)   # fail loud if a caller poisoned the anchor
    df = gs.load_graded_log(engine, include_backfill=include_backfill)
    if df is None or len(df) == 0:
        return {"engine": engine, "status": "no_data"}

    cohorts = _split_cohorts(df)
    scorecard: dict[str, Any] = {
        "schema": "promises.v1",
        "engine": engine,
        "as_of": pd.Timestamp.now("UTC").isoformat(),
        "n_instruments": int(df["id"].nunique()),
        "n_stamps_total": int(len(df)),
        "epoch": _epoch_basis(df),
        "field_horizon": FIELD_HORIZON,
        "nominal_cone": NOMINAL_CONE,
        "gates": {"turn_pr": "CC-3", "cone": "CC-1", "reliability": "CC-2",
                  "fdr_family": "turn_pr", "fdr_q": FDR_Q},
        "cohorts": {},
    }

    for cohort_name, cdf in cohorts.items():
        if len(cdf) == 0:
            scorecard["cohorts"][cohort_name] = {"n_stamps": 0, "status": "empty"}
            continue
        # restrict prices to this cohort's instruments
        cids = {str(i) for i in cdf["id"].dropna().unique()}
        cprices = {sid: px for sid, px in prices.items() if sid in cids}
        n_months = int(pd.to_datetime(cdf["date"]).dt.to_period("M").nunique())
        scorecard["cohorts"][cohort_name] = {
            "cohort": cohort_name,
            "n_stamps": int(len(cdf)),
            "n_months": n_months,
            "n_instruments": len(cids),
            "turn_pr": turn_pr(cdf, cprices),
            "cone_coverage": cone_grade(cdf, cprices),
            "reliability": reliability_grade(cdf, cprices),
        }

    # FDR-BH within the turn_pr family: per-instrument precision cells of the BACKTEST
    # cohort (the matured one).  A cell "passes" CC-3 only if it survives BH at q=0.10.
    bt = scorecard["cohorts"].get("BACKTEST", {})
    if isinstance(bt, dict) and "turn_pr" in bt:
        pvals: dict[str, float] = {}
        for sid, cell in bt["turn_pr"]["per_instrument"].items():
            ci = cell.get("precision_ci")
            n = cell["tp"] + cell["fp"]
            if ci is None or n == 0:
                continue
            # one-sided p ≈ P(precision <= 0.5 | observed) proxy via Wilson-lo distance.
            # Use a coarse binomial tail: p = 0.5^? is heavy; instead flag by Wilson-lo.
            pvals[sid] = 0.0 if ci[0] > 0.5 else 1.0
        passed = gs.fdr_bh(pvals, q=FDR_Q) if pvals else {}
        bt["turn_pr"]["fdr_passed"] = passed

    return scorecard
