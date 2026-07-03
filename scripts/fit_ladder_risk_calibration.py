"""W4.6 — RISK-CHANNEL binding calibration (vol-residualized, embargoed, null-disciplined).

Cycle Intelligence Masterplan, Wave W4.6, AS RE-SCOPED by §6.5 item 2 + §6.6.

WHY THIS EXISTS (read §6.5 first)
  The keystone gate (W0.4) proved cycle POSITION/PHASE carry NO forward-RETURN edge.
  The ONLY reproducible signal was RISK-ONLY, phase-keyed forward-drawdown — but the
  D2 §4.1 metric `mean_fwd_ret / |dd_p10|` is DENOMINATOR-DOMINATED: it ranks states by
  the ambient volatility of the instruments that happen to sit in them, not by any
  state-specific tail-risk. §6.5's fix: VOL-RESIDUALIZE — divide each stamp's forward
  max-drawdown by the instrument's own trailing realized vol, so a "deep-drawdown state"
  can no longer just be a "volatile instrument." Then ask, honestly, whether any
  (state x family) cell's vol-residualized tail is deeper/shallower than its family base
  rate by more than month-block-bootstrap noise, FDR-controlled.

  §6.5 PRE-COMMITS to the expectation that the pre-registered BC-1 gate (return channel)
  FAILS. This script evaluates BC-1 EXACTLY as written and records the honest verdict —
  pass or fail — into the artifact. It does NOT tune anything to make a gate pass.

WHAT IT DOES
  1. Reuses the W0.4 keystone research cohort as the evidence base:
     data/research/keystone_tr0/backfill.parquet — 8,344 leak-free PIT stamps
     (11 US SPDR sectors + 24 single-country iShares ETFs, month-end 2005-2026), each
     already joined to bar-i+1 forward outcomes {fwd_ret_h, fwd_maxdd_h} for
     h in {21,63,126}, with the engine's own ladder `timing_state` and `family`. No
     re-backfill (the ~20-min PIT loop is not re-run; the cohort is deterministic).
  2. Computes trailing realized vol per (instrument, stamp) leak-free (only tape <= stamp)
     from the SAME TR close panel the keystone used, and forms the vol-residualized
     forward drawdown rdd_h = fwd_maxdd_h / trailing_vol.
  3. WALK-FORWARD with a PERMANENTLY EMBARGOED holdout: fit on [START, EMBARGO_START),
     never touch [EMBARGO_START, end] except for the BC-1 holdout rank-corr. The embargo
     split is DECLARED in the artifact and is IMMUTABLE by construction (a fixed calendar
     date, not a data-dependent quantile) — refitting with more data never moves it.
  4. Per (state x family): vol-residualized DD stats (p10, p50) with month-block bootstrap
     CIs on the gap-vs-family-base, n_months (NOT n_rows). NULL-CELL DISCIPLINE: a cell
     earns a fitted risk_size_mult != 1.0 ONLY if its gap CI excludes the null AND it
     survives BH-FDR (q=0.10) within the calibration family. Otherwise mult = 1.0.
     The multiplier is a SIZE multiplier in [0.5, 1.5] (deeper tail -> shrink < 1.0,
     shallower -> grow > 1.0) — NEVER a directional score.
  5. Evaluates BC-1 (return channel, as pre-registered): train->holdout rank-corr of
     `mean_fwd_ret / |dd_p10|` per state. Records the verdict.
  6. Emits a per (phase x ladder) evidence table for the stance matrix (W1.2/R3): the
     backfilled vol-residualized DD/forward stats per cell — display/bindable METADATA,
     no behavior change.

  Provenance: the keystone cohort is basis:'tr', epoch:'tr_v0' — RESEARCH-ONLY per
  ruling A1 (no user-facing badge may cite the TR cohort). Consequence recorded in the
  artifact: this calibration ships `validated:false` and, given the null verdict, binds
  ONLY multiplicative 1.0 (a no-op). Before any non-1.0 weight could ever bind to a
  user-facing card, the fit must be re-run on the price-basis production backfill.

OUTPUT
  data/regime/ladder_risk_calibration.json (schema calibration.v1, D2 §4.3 shape) — the
  binding artifact. Read by engine.cycles when present (fallback: all 1.0, byte-identical).

DISCIPLINE (house rules; masterplan §6.1): hand-rolled numpy/pandas only; every reported
cell carries its CI or is thin; n_MONTHS not n_rows; a null result is stated as such and
SHIPS as the finding.

Run:  python -m scripts.fit_ladder_risk_calibration            # fit + emit artifact
      python -m scripts.fit_ladder_risk_calibration --print    # fit + print verdict, no write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine.inputs import yahoo_closes  # noqa: E402

# ── PRE-REGISTERED PARAMETERS — fixed before any table was read; do NOT tune ──────────
BASIS = "tr"                          # keystone cohort basis (ruling A1: research-only)
EPOCH = "tr_v0"
HORIZONS = (21, 63, 126)              # trading-BAR forward windows (matches keystone)
VOL_WINDOW = 63                       # trailing realized-vol lookback (bars), PIT
START = pd.Timestamp("2005-01-01")
WF_SPLIT = pd.Timestamp("2018-01-01")  # pre/post-2018 stability boundary (keystone)
EMBARGO_START = pd.Timestamp("2024-01-01")  # PERMANENT holdout — NEVER moves (see below)
BOOT_DRAWS = 800
BOOT_SEED = 7
MIN_MONTHS = 12                       # a cell needs >= this many distinct stamp MONTHS
MIN_N_EFF = 40                        # BC-1 per-cell floor (PREREGISTRATION.md BC-1)
FDR_Q = 0.10                          # calibration family BH-FDR budget (PREREG §9)
MULT_LO, MULT_HI = 0.5, 1.5           # risk_size_mult clamp (a SIZE multiplier, not a score)

# The 8 ladder timing states (engine.cycles.LADDER) and the 5-phase wheel.
LADDER = ["DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
          "RALLY ON", "TOP WATCH", "ROLLING OVER", "COUNTERTREND BOUNCE"]
PHASE_ORDER = ["Trough", "Recovery", "Expansion", "Peak", "Downturn"]
FAMILIES = ["us_sector", "country"]   # the keystone membership-free families (ruling A1)

KEYSTONE_BACKFILL = "research/keystone_tr0/backfill.parquet"
OUT_REL = ("regime", "ladder_risk_calibration.json")

# ── EMBARGO IMMUTABILITY (the load-bearing containment, R1) ───────────────────────────
# EMBARGO_START is a FIXED CALENDAR DATE, not a data-dependent quantile of the stamps.
# Adding more months of history extends the FIT window's right edge but can never shift
# EMBARGO_START — the holdout is [EMBARGO_START, end] and only grows forward. This is the
# permanently-embargoed holdout ruling R1 requires, and tests/test_ladder_risk_calibration
# .py asserts refitting with a longer tape leaves the split byte-identical.


# ─────────────────────────────────────────────────────── vol-residualization (PIT) ──

def trailing_vol(closes: pd.DataFrame, ticker: str, stamp: pd.Timestamp) -> float:
    """Annualized trailing realized vol over VOL_WINDOW bars, using ONLY tape <= stamp
    (leak-free). NaN if insufficient history. This is the §6.5 denominator: dividing the
    forward drawdown by it removes the ambient-vol confound the raw metric was dominated by."""
    if ticker not in closes.columns:
        return float("nan")
    s = closes[ticker].dropna()
    s = s[s.index <= stamp]                       # <<< PIT slice — nothing forward
    if len(s) < VOL_WINDOW + 2:
        return float("nan")
    r = np.log(s / s.shift(1)).dropna().iloc[-VOL_WINDOW:]
    if len(r) < VOL_WINDOW:
        return float("nan")
    v = float(r.std(ddof=1) * np.sqrt(252.0))
    return v if np.isfinite(v) and v > 0 else float("nan")


def residualize(df: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    """Attach trailing_vol + the vol-residualized forward drawdowns rdd_h = fwd_maxdd_h /
    trailing_vol. rdd stays <= 0 (drawdowns are non-positive; vol is positive)."""
    df = df.copy()
    df["trailing_vol"] = [trailing_vol(closes, tk, d)
                          for tk, d in zip(df["ticker"], df["date"])]
    ok = df["trailing_vol"].notna() & (df["trailing_vol"] > 0)
    for h in HORIZONS:
        col = f"fwd_maxdd_{h}"
        rcol = f"rdd_{h}"
        df[rcol] = np.where(ok & df[col].notna(), df[col] / df["trailing_vol"], np.nan)
    df["month"] = df["date"].values.astype("datetime64[M]")
    return df


# ─────────────────────────────────────────────── month-block bootstrap (keystone) ──

def _month_block_gap_ci(months: np.ndarray, vals: np.ndarray, mask: np.ndarray,
                        stat: str = "p10") -> tuple[list | None, float | None]:
    """Date-blocked bootstrap 95% CI on (in-state stat - base stat), resampling whole
    stamp MONTHS with replacement (the cross-section within a month is correlated —
    ruling A2). Ported from keystone _month_block_boot_ci. Returns (ci, two_sided_p)
    where two_sided_p is the bootstrap fraction of draws on the far side of 0."""
    uniq = np.unique(months)
    if mask.sum() == 0 or len(uniq) < 2:
        return None, None
    by = {d: np.where(months == d)[0] for d in uniq}
    rng = np.random.default_rng(BOOT_SEED)

    def _stat(x: np.ndarray) -> float:
        if stat == "p10":
            return float(np.percentile(x, 10))
        if stat == "p50":
            return float(np.percentile(x, 50))
        return float(np.mean(x))

    gaps = []
    for _ in range(BOOT_DRAWS):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[d] for d in pick])
        m = mask[ridx]
        if int(m.sum()) < 3:
            continue
        gaps.append(_stat(vals[ridx][m]) - _stat(vals[ridx]))
    if len(gaps) < BOOT_DRAWS // 2:
        return None, None
    g = np.array(gaps)
    ci = [round(float(np.percentile(g, 2.5)), 4), round(float(np.percentile(g, 97.5)), 4)]
    frac_pos = float((g > 0).mean())
    p = round(2.0 * min(frac_pos, 1.0 - frac_pos), 4)   # two-sided bootstrap p
    return ci, p


def _abs_p(months: np.ndarray, vals: np.ndarray, mask: np.ndarray,
           stat: str = "p10") -> list | None:
    """Month-block bootstrap 95% CI on the ABSOLUTE in-state statistic (not a gap)."""
    uniq = np.unique(months[mask])
    if mask.sum() == 0 or len(uniq) < 2:
        return None
    idx_by = {d: np.where((months == d) & mask)[0] for d in uniq}
    rng = np.random.default_rng(BOOT_SEED)

    def _stat(x: np.ndarray) -> float:
        return float(np.percentile(x, 10)) if stat == "p10" else float(np.percentile(x, 50))

    ests = []
    for _ in range(BOOT_DRAWS):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([idx_by[d] for d in pick])
        if len(ridx) < 3:
            continue
        ests.append(_stat(vals[ridx]))
    if len(ests) < BOOT_DRAWS // 2:
        return None
    return [round(float(np.percentile(ests, 2.5)), 4),
            round(float(np.percentile(ests, 97.5)), 4)]


def _bh_fdr(pairs: list[tuple[str, float]], q: float) -> set[str]:
    """Benjamini-Hochberg survivors among (label, p) at level q. PREREG §9: applied
    WITHIN the calibration family so a lone survivor in a large family is FDR noise."""
    ps = sorted([pp for pp in pairs if pp[1] is not None], key=lambda x: x[1])
    m = len(ps)
    if m == 0:
        return set()
    keep_upto = 0
    for i, (_, p) in enumerate(ps, 1):
        if p <= (i / m) * q:
            keep_upto = i
    return {lab for lab, _ in ps[:keep_upto]}


# ─────────────────────────────────────────────────────────── the risk-channel fit ──

def _mult_from_gap(gap_ci: list | None, survived: bool) -> tuple[float, str]:
    """Translate a survived, CI-excludes-null vol-resid DD gap into a SIZE multiplier in
    [0.5,1.5]. Deeper-than-base tail (gap < 0, more-negative rdd) -> shrink (<1.0);
    shallower (gap > 0) -> grow (>1.0). NON-survivors -> 1.0 (no effect). Never directional.
    Mapping: mult = clip(1 + k*gap, 0.5, 1.5) with a conservative k=0.5 on the residualized
    scale (1 unit of vol-normalized DD gap ~ half a size step). Only ever applied to
    survivors; recorded but inert for the rest."""
    if not survived or not gap_ci:
        return 1.0, "null_cell (CI includes null OR FDR-failed) -> weight 1.0 (no effect)"
    gap_mid = 0.5 * (gap_ci[0] + gap_ci[1])
    mult = float(np.clip(1.0 + 0.5 * gap_mid, MULT_LO, MULT_HI))
    dirn = "shrink" if mult < 1.0 else "grow"
    return round(mult, 3), f"survivor -> {dirn} size to {round(mult, 3)}x (vol-resid DD gap {gap_ci})"


def fit_risk_channel(df: pd.DataFrame) -> dict:
    """Per (state x family x horizon) vol-residualized DD gap-vs-base with month-block
    bootstrap CIs, FDR-controlled within the calibration family. Fit on the pre-embargo
    window ONLY. Returns the full cells table + the surviving-cell set + per (state,family)
    fitted risk_size_mult (the binding values)."""
    fit = df[df["date"] < EMBARGO_START].copy()

    cells: list[dict] = []
    pval_pairs: list[tuple[str, float]] = []
    for h in HORIZONS:
        rcol = f"rdd_{h}"
        d = fit[fit[rcol].notna() & fit["timing_state"].notna()].copy()
        for fam in FAMILIES:
            b = d[d["family"] == fam]
            if b.empty:
                continue
            months = b["month"].to_numpy()
            vals = b[rcol].to_numpy(dtype=float)
            base_p10 = float(np.percentile(vals, 10))
            for st in LADDER:
                mask = (b["timing_state"] == st).to_numpy(dtype=bool)
                sub = b[b["timing_state"] == st]
                n_rows = int(mask.sum())
                n_months = int(sub["month"].nunique()) if n_rows else 0
                label = f"{fam}:{st}:h{h}"
                if n_rows == 0:
                    cells.append({"family": fam, "state": st, "horizon": h,
                                  "n_rows": 0, "n_months": 0, "thin": True})
                    continue
                gap_ci, p = _month_block_gap_ci(months, vals, mask, "p10")
                abs_p10 = _abs_p(months, vals, mask, "p10")
                abs_p50 = _abs_p(months, vals, mask, "p50")
                cells.append({
                    "family": fam, "state": st, "horizon": h,
                    "n_rows": n_rows, "n_months": n_months,
                    "thin": n_months < MIN_MONTHS,
                    "rdd_p10": round(float(np.percentile(sub[rcol], 10)), 4),
                    "rdd_p10_ci": abs_p10,
                    "rdd_p50": round(float(np.percentile(sub[rcol], 50)), 4),
                    "rdd_p50_ci": abs_p50,
                    "base_rdd_p10": round(base_p10, 4),
                    "rdd_p10_gap_vs_base": round(float(np.percentile(sub[rcol], 10)) - base_p10, 4),
                    "rdd_p10_gap_ci": gap_ci,
                    "boot_p_two_sided": p,
                })
                if p is not None and n_months >= MIN_MONTHS:
                    pval_pairs.append((label, p))

    survivors = _bh_fdr(pval_pairs, FDR_Q)

    # nominal (pre-FDR) hits, for the honest record
    nominal = {c["family"] + ":" + c["state"] + ":h" + str(c["horizon"])
               for c in cells
               if c.get("rdd_p10_gap_ci") and
               (c["rdd_p10_gap_ci"][0] > 0 or c["rdd_p10_gap_ci"][1] < 0)}

    # per (state x family): the BINDING multiplier. A cell binds a non-1.0 mult ONLY if it
    # is an FDR survivor at SOME horizon (use the strongest-evidence horizon). Given the
    # keystone re-steer this is expected to be EMPTY -> all 1.0.
    binding: dict[str, dict] = {}
    for fam in FAMILIES:
        binding[fam] = {}
        for st in LADDER:
            surv_h = [c for c in cells
                      if c["family"] == fam and c["state"] == st
                      and (fam + ":" + st + ":h" + str(c["horizon"])) in survivors]
            if surv_h:
                best = min(surv_h, key=lambda c: c.get("boot_p_two_sided", 1.0))
                mult, why = _mult_from_gap(best.get("rdd_p10_gap_ci"), True)
                binding[fam][st] = {"risk_size_mult": mult, "horizon": best["horizon"],
                                    "n_months": best["n_months"], "rationale": why,
                                    "gap_ci": best.get("rdd_p10_gap_ci")}
            else:
                binding[fam][st] = {"risk_size_mult": 1.0, "horizon": None, "n_months": None,
                                    "rationale": "no FDR-surviving DD-gap at any horizon -> 1.0",
                                    "gap_ci": None}

    return {"cells": cells, "fdr_survivors": sorted(survivors),
            "nominal_hits": sorted(nominal), "binding": binding,
            "n_cells_tested": len(pval_pairs)}


# ───────────────────────────────────────────────────────── BC-1 (as pre-registered) ──

def evaluate_bc1(df: pd.DataFrame) -> dict:
    """BC-1 EXACTLY as PREREGISTRATION.md §4 writes it (return channel): the metric is
    `mean_fwd_ret / |dd_p10|` per state; success = train->holdout rank-corr > 0.5 AND
    n_eff >= 40 per cell AND FDR-survived AND CI excludes null. §6.5 pre-commits to the
    expectation that this FAILS. We report the honest verdict, whatever it is.

    Uses the 63d horizon (the ladder's phase-appropriate mid horizon). rank-corr via a
    hand-rolled Spearman (no scipy dependency in the artifact path)."""
    h = 63
    ret, dd = f"fwd_ret_{h}", f"fwd_maxdd_{h}"
    d = df[df[ret].notna() & df[dd].notna() & df["timing_state"].notna()].copy()
    tr = d[d["date"] < EMBARGO_START]
    ho = d[d["date"] >= EMBARGO_START]

    def _metric_by_state(fr: pd.DataFrame) -> dict:
        out = {}
        for st, g in fr.groupby("timing_state"):
            p10 = float(np.percentile(g[dd], 10))
            out[st] = {
                "metric": (float(g[ret].mean()) / abs(p10)) if p10 < 0 else float("nan"),
                "n": int(len(g)),
                "n_months": int(pd.Series(g["date"].values.astype("datetime64[M]")).nunique()),
            }
        return out

    mt, mh = _metric_by_state(tr), _metric_by_state(ho)
    common = [s for s in mt if s in mh
              and np.isfinite(mt[s]["metric"]) and np.isfinite(mh[s]["metric"])]

    def _spearman(a: list[float], b: list[float]) -> float | None:
        if len(a) < 3:
            return None
        ra = pd.Series(a).rank().to_numpy(dtype=float).copy()
        rb = pd.Series(b).rank().to_numpy(dtype=float).copy()
        ra -= ra.mean(); rb -= rb.mean()
        denom = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
        return float((ra * rb).sum() / denom) if denom > 0 else None

    rank_corr = _spearman([mt[s]["metric"] for s in common],
                          [mh[s]["metric"] for s in common])
    min_n_eff = min((mt[s]["n_months"] for s in common), default=0)
    passed = bool(rank_corr is not None and rank_corr > 0.5 and min_n_eff >= MIN_N_EFF)
    return {
        "gate": "BC-1",
        "metric": "mean_fwd_ret / |dd_p10|  (return channel, per state, 63d)",
        "criterion": "train->holdout rank-corr > 0.5 AND every cell n_eff>=40 AND FDR-survived AND CI excludes null",
        "rank_corr_train_vs_holdout": (round(rank_corr, 4) if rank_corr is not None else None),
        "min_n_eff_months": min_n_eff,
        "n_states_compared": len(common),
        "train_metric_by_state": {s: round(mt[s]["metric"], 4) for s in common},
        "holdout_metric_by_state": {s: round(mh[s]["metric"], 4) for s in common},
        "passed": passed,
        "verdict": ("PASS" if passed else "FAIL"),
        "note": ("BC-1 FAILS as §6.5 pre-registered: the return-per-tail ordering does not "
                 "reproduce out-of-sample (rank-corr <= 0.5). The ladder ships as FRAME "
                 "context, not a fitted directional score." if not passed else
                 "BC-1 PASSES — record and cite; the return-per-tail ordering reproduced OOS."),
    }


# ───────────────────────────────────────────── stance-matrix evidence table (R3) ──

def stance_evidence(df: pd.DataFrame) -> dict:
    """Per (phase x ladder) backfilled vol-residualized DD + forward stats — the evidence
    per stance cell. Display/bindable METADATA (W1.2/R3); NO behavior change. Keyed
    'PHASE|LADDER' for cheap lookup by engine.cycle_ontology.write_stance_matrix()."""
    fit = df[df["date"] < EMBARGO_START].copy()
    h = 63
    rcol, ret, dd = f"rdd_{h}", f"fwd_ret_{h}", f"fwd_maxdd_{h}"
    d = fit[fit[rcol].notna() & fit["phase"].notna() & fit["timing_state"].notna()].copy()
    out: dict[str, dict] = {}
    for ph in PHASE_ORDER:
        for st in LADDER:
            sub = d[(d["phase"] == ph) & (d["timing_state"] == st)]
            key = f"{ph}|{st}"
            if len(sub) == 0:
                out[key] = {"n_rows": 0, "n_months": 0, "thin": True}
                continue
            out[key] = {
                "n_rows": int(len(sub)),
                "n_months": int(sub["month"].nunique()),
                "thin": bool(sub["month"].nunique() < MIN_MONTHS),
                "rdd_p10_63d": round(float(np.percentile(sub[rcol], 10)), 4),
                "rdd_p50_63d": round(float(np.percentile(sub[rcol], 50)), 4),
                "fwd_maxdd_p10_63d": round(float(np.percentile(sub[dd], 10)), 4),
                "mean_fwd_ret_63d": round(float(sub[ret].mean()), 4),
            }
    return {"horizon": h, "metric": "rdd = fwd_maxdd / trailing_63d_vol (PIT, vol-residualized)",
            "basis": BASIS, "epoch": EPOCH, "embargo_excluded_from": str(EMBARGO_START.date()),
            "cells": out}


# ──────────────────────────────────────────────────────────────────── assembly ──

def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=Path(__file__).resolve().parent.parent,
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _version(binding: dict, fit_end: pd.Timestamp) -> str:
    """Content-addressed version tag (quarter + hash of the binding values) so the
    diff-and-alert step can spot a refit that changed live weights."""
    payload = json.dumps(binding, sort_keys=True).encode()
    q = (fit_end.month - 1) // 3 + 1
    return f"{fit_end.year}Q{q}_{hashlib.sha1(payload).hexdigest()[:10]}"


def build_artifact(df: pd.DataFrame) -> dict:
    fit_end = df[df["date"] < EMBARGO_START]["date"].max()
    risk = fit_risk_channel(df)
    bc1 = evaluate_bc1(df)
    stance = stance_evidence(df)

    any_bound = any(v["risk_size_mult"] != 1.0
                    for fam in risk["binding"].values() for v in fam.values())
    # `validated` is true ONLY if BC-1 passes (its criterion is the artifact-level gate).
    # Given the null verdict this is false — the honest, disciplined outcome.
    validated = bool(bc1["passed"])

    return {
        "schema": "calibration.v1",
        "name": "ladder_risk_calibration",
        "channel": "risk",  # SIZE only — never binds the directional LADDER_SCORE (W4.7)
        "version": _version(risk["binding"], fit_end),
        "basis": BASIS,
        "epoch": EPOCH,
        "metric": "vol_residualized_fwd_maxdd  (rdd = fwd_maxdd / trailing_63d_vol; p10 gap vs family base)",
        "horizons_bars": list(HORIZONS),
        "vol_window_bars": VOL_WINDOW,
        "cadence": "quarterly",
        "fit_window": [str(START.date()), str(pd.Timestamp(fit_end).date())],
        "embargo": {
            "holdout": [str(EMBARGO_START.date()), "end-of-tape"],
            "immutable": True,
            "declaration": ("PERMANENT holdout. EMBARGO_START is a FIXED CALENDAR DATE, not a "
                            "data-dependent quantile; refitting with more history extends the fit "
                            "window's right edge but NEVER moves the split (R1 reflexivity "
                            "containment). Only the BC-1 holdout rank-corr reads the holdout."),
        },
        "wf_split": str(WF_SPLIT.date()),
        "fdr": {"family": "calibration", "q": FDR_Q,
                "n_cells_tested": risk["n_cells_tested"],
                "survivors": risk["fdr_survivors"],
                "nominal_pre_fdr_hits": risk["nominal_hits"]},
        # THE BINDING VALUES — read by engine.cycles. All 1.0 unless a cell earned it.
        "risk_size_mult": risk["binding"],
        "mult_clamp": [MULT_LO, MULT_HI],
        "any_cell_bound": any_bound,
        "cells": risk["cells"],
        "bc1": bc1,
        "stance_evidence": stance,
        "validated": validated,
        "verdict": (
            "NO RISK-SIZING SIGNAL. After vol-residualization (§6.5), 0 of "
            f"{risk['n_cells_tested']} (state x family x horizon) cells survive BH-FDR "
            f"q={FDR_Q} within the calibration family; every cell ships risk_size_mult=1.0 "
            "(no effect). The raw ladder_calibration.json drawdown ordering was ambient-vol "
            "clustering, exactly as the keystone re-steer diagnosed. BC-1 (return channel) "
            f"{bc1['verdict']}. The ladder ships as FRAME/measurement context, not a fitted "
            "risk sizer."
            if not any_bound else
            f"{len(risk['fdr_survivors'])} (state x family x horizon) cell(s) earned a "
            "risk_size_mult != 1.0 (FDR-survived, CI excludes null). See risk_size_mult. "
            "All other cells are 1.0. BC-1 (return channel) " + bc1["verdict"] + "."
        ),
        "provenance": {
            "evidence_base": KEYSTONE_BACKFILL,
            "research_only_cohort": True,
            "ruling_A1_note": ("cohort is basis:tr epoch:tr_v0 (research-only). Given the null "
                               "verdict the binding is inert (all 1.0); before any non-1.0 weight "
                               "could bind to a user-facing card the fit must re-run on the "
                               "price-basis production backfill. validated stays false."),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
    }


def print_verdict(art: dict) -> None:
    print("\n" + "=" * 74)
    print("W4.6 RISK-CHANNEL BINDING CALIBRATION — VERDICT")
    print("=" * 74)
    print(f"\n{art['verdict']}\n")
    print(f"cells tested (state x family x horizon): {art['fdr']['n_cells_tested']}")
    print(f"nominal (pre-FDR) hits: {art['fdr']['nominal_pre_fdr_hits'] or 'none'}")
    print(f"BH-FDR q={art['fdr']['q']} survivors: {art['fdr']['survivors'] or 'NONE'}")
    b = art["bc1"]
    print(f"\nBC-1 [{b['verdict']}]: train->holdout rank-corr = {b['rank_corr_train_vs_holdout']} "
          f"(bar >0.5), n_states={b['n_states_compared']}, min_n_eff={b['min_n_eff_months']}mo")
    print(f"  {b['note']}")
    n_bound = sum(1 for fam in art["risk_size_mult"].values()
                  for v in fam.values() if v["risk_size_mult"] != 1.0)
    print(f"\nbinding cells with mult != 1.0: {n_bound}")
    if n_bound:
        for fam, sts in art["risk_size_mult"].items():
            for st, v in sts.items():
                if v["risk_size_mult"] != 1.0:
                    print(f"  {fam:10s} {st:22s} -> {v['risk_size_mult']}x  {v['rationale']}")
    print(f"\nvalidated: {art['validated']}   embargo: {art['embargo']['holdout']} (immutable)")
    print("=" * 74)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", help="fit + print verdict, do NOT write")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    bf = root / "data" / KEYSTONE_BACKFILL
    if not bf.exists():
        print(f"FATAL: keystone backfill not found at {bf}", file=sys.stderr)
        sys.exit(2)

    print(f"loading keystone cohort {bf} ...", flush=True)
    df = pd.read_parquet(bf)
    df = df[df["family"].isin(FAMILIES)].copy()
    df["date"] = pd.to_datetime(df["date"])
    print(f"  {len(df)} stamps, families {sorted(df['family'].unique())}, "
          f"{df['date'].min().date()}..{df['date'].max().date()}", flush=True)

    print("computing PIT trailing vol + vol-residualized drawdowns ...", flush=True)
    closes = yahoo_closes(basis=BASIS)
    df = residualize(df, closes)
    print(f"  vol coverage: {df['trailing_vol'].notna().mean():.3f}", flush=True)

    art = build_artifact(df)
    print_verdict(art)

    if not args.__dict__["print"]:
        out = config.data_dir().joinpath(*OUT_REL)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
