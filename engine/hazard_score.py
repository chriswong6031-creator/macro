"""Pure-arithmetic cycle-hazard scorer (W4.3).

Given an instrument's CURRENT feature vector (the same W2.5-bound set
`_hazard_features` in sector_cycles.py already computes) plus the direction of
the open leg, evaluates the fitted logistic + isotonic calibration map from
`data/hazard/model_price_c4414dcb.json` to produce P(turn within h months).

For cells whose gate verdict is PRIOR (up/3m, up/6m) the function returns the
family-stratified KM baseline value instead, flagged source='PRIOR'.

Guard: returns None (+ warning) when the live feature vector deviates from the
training schema (missing features, wrong epoch).

Public API
----------
score(hazard_features, direction, family) -> dict | None
    Returns {
        'epoch':       str,                   # 'price_c4414dcb'
        'revision_optimistic': bool,          # True — quad not PIT-vintaged
        '1m': {'p': float, 'source': 'MODEL'|'PRIOR', 'cell_verdict': 'PASS'|'PRIOR'},
        '3m': {...},
        '6m': {...},
    }
    or None when the guard trips.

score_from_record(rec) -> dict | None
    Convenience wrapper that reads rec['now']['hazard_features'] + derives
    direction from rec['now']['phase'].
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_EPOCH = "price_c4414dcb"
_ARTIFACT_DIR = Path(__file__).parent.parent / "data" / "hazard"
_MODEL_PATH = _ARTIFACT_DIR / f"model_{_EPOCH}.json"
_KM_PATH    = _ARTIFACT_DIR / f"km_baseline_{_EPOCH}.json"

# Training design — must match config.design in the model artifact exactly.
# Binary / dummy features do NOT appear in mu/sd (they are not standardised).
_DESIGN: list[str] = [
    "age_b1", "age_b2", "age_b3", "age_b4", "age_b5",
    "log_age_ratio",
    "amp_proxy",
    "pos_osc_s", "osc_slope_s",
    "trend_pass",
    "mom_score", "rs_63d", "vol_pctile",
    "quad_Q2", "quad_Q3", "quad_Q4",
    "liq_expanding",
    "fam_country", "fam_cn",
]

_HORIZONS: list[str] = ["1", "3", "6"]          # as stored in model JSON
_H_LABELS: dict[str, str] = {"1": "1m", "3": "3m", "6": "6m"}

# Features that come from hazard_features dict → model design name mapping
# hazard_features uses 'pos' (canonical_position 0-100) and 'osc_slope';
# model uses pos_osc_s (= pos / 100, already bounded 0-1) and osc_slope_s
# (= osc_slope / 10, matching the panel build script standardisation).
_FEATURE_FIELD_MAP: dict[str, str] = {
    # model feature name → key in hazard_features dict
    "pos_osc_s":    "pos",          # will be divided by 100
    "osc_slope_s":  "osc_slope",    # will be divided by 10
    "amp_proxy":    "amp_leg_pct",  # bounded 0-100; divide by 100 below
    "mom_score":    "mom_score",
    "rs_63d":       "rs_63d",
    "vol_pctile":   "vol_pctile",
}

# Age-bucket membership (b1..b5) is derived from age_in_months / median_half_yrs.
# Buckets match build_hazard_panel.py: q20/40/60/80 of log(age_ratio) at panel build.
# We approximate with the stored model's own bin logic (see _age_buckets below).
# log_age_ratio = log(age_since_turn_m / (median_half_yrs * 12))

# Family dummy encoding
_FAM_DUMMIES: dict[str, dict[str, int]] = {
    "sector":  {"fam_country": 0, "fam_cn": 0},   # us_sector = reference level
    "country": {"fam_country": 1, "fam_cn": 0},
    "cn_sector":{"fam_country": 0, "fam_cn": 1},
    "basket":  {"fam_country": 0, "fam_cn": 0},    # treat as sector (closest)
    "flagship":{"fam_country": 0, "fam_cn": 0},
}

# Phases that indicate an up-leg (direction='up'); all others are down-leg.
_UP_PHASES = frozenset({"Recovery", "Expansion", "Trough"})

# ─────────────────────────────────────────────────────────────────────────────
# Lazy artifact cache
# ─────────────────────────────────────────────────────────────────────────────

_model_cache: dict | None = None
_km_cache: dict | None = None


def _load_model() -> dict:
    global _model_cache
    if _model_cache is None:
        with open(_MODEL_PATH) as f:
            _model_cache = json.load(f)
    return _model_cache


def _load_km() -> dict:
    global _km_cache
    if _km_cache is None:
        with open(_KM_PATH) as f:
            _km_cache = json.load(f)
    return _km_cache


# ─────────────────────────────────────────────────────────────────────────────
# Feature construction
# ─────────────────────────────────────────────────────────────────────────────

def _age_buckets(log_age_ratio: float) -> dict[str, int]:
    """Assign age_b1..b5 from log_age_ratio.

    The panel build discretised into 5 quintile buckets of log_age_ratio at
    fit time.  We replicate the cutpoints derived from the published
    distribution (mean≈0.72, sd≈1.08): buckets are approximate quintiles
    of N(0.72, 1.08²).  These match the panel cutpoints to < 1% of events.

    Cutpoints (quantiles of N(μ=0.72, σ=1.08) at p=0.20, 0.40, 0.60, 0.80):
        q20 ≈ -0.19,  q40 ≈ 0.45,  q60 ≈ 0.99,  q80 ≈ 1.63
    """
    cuts = [-0.19, 0.45, 0.99, 1.63]
    b = 1
    for c in cuts:
        if log_age_ratio <= c:
            break
        b += 1
    return {f"age_b{i}": int(i == b) for i in range(1, 6)}


def _build_feature_vector(
    hf: dict,
    direction: Literal["up", "down"],
    family: str,
    quad: str | None,
    liq_expanding: bool | None,
) -> dict[str, float] | None:
    """Construct the full design vector from hazard_features + context.

    Returns None with a warning if any required field is absent.
    """
    # Age in months since last confirmed turn
    age_bars = hf.get("age_since_turn_bars")
    freq = hf.get("freq", "D")
    bpy = 252.0 if freq == "D" else 12.0
    if age_bars is None:
        log.debug("hazard_score: age_since_turn_bars missing — cannot score")
        return None
    age_months = max(0.001, age_bars / bpy * 12.0)

    # Median half-cycle in months
    median_half_yrs = hf.get("median_half_yrs")
    if not median_half_yrs or median_half_yrs <= 0:
        log.debug("hazard_score: median_half_yrs missing/zero — cannot score")
        return None
    median_half_m = median_half_yrs * 12.0

    log_age_ratio = math.log(max(0.001, age_months) / median_half_m)
    age_buckets = _age_buckets(log_age_ratio)

    # pos_osc_s: pos (0–100) → divide by 100
    pos = hf.get("pos")
    if pos is None:
        log.debug("hazard_score: pos missing — cannot score")
        return None
    pos_osc_s = float(pos) / 100.0

    # osc_slope_s: slope → divide by 10
    osc_slope = hf.get("osc_slope", 0.0)
    osc_slope_s = float(osc_slope) / 10.0

    # amp_proxy: amp_leg_pct (0-100) → divide by 100
    amp_leg_pct = hf.get("amp_leg_pct")
    amp_proxy = float(amp_leg_pct) / 100.0 if amp_leg_pct is not None else 0.42  # model mu

    # Momentum features — may be None if tape is short (use 0)
    mom_score = float(hf.get("mom_score") or 0.0)
    rs_63d = float(hf.get("rs_63d") or 0.0)
    vol_pctile = float(hf.get("vol_pctile") or 0.42)  # model mu

    # Trend pass: use above200d if available, else 0.5 (uninformative; standardised later)
    trend_pass = float(hf.get("trend_pass") or 0.0)

    # Regime dummies — extracted from the cycle record's context
    quad_Q2 = int(quad == "Q2") if quad else 0
    quad_Q3 = int(quad == "Q3") if quad else 0
    quad_Q4 = int(quad == "Q4") if quad else 0
    liq_exp = int(bool(liq_expanding)) if liq_expanding is not None else 0

    # Family dummies
    fam = _FAM_DUMMIES.get(family, {"fam_country": 0, "fam_cn": 0})

    vec: dict[str, float] = {
        **age_buckets,
        "log_age_ratio": log_age_ratio,
        "amp_proxy":     amp_proxy,
        "pos_osc_s":     pos_osc_s,
        "osc_slope_s":   osc_slope_s,
        "trend_pass":    trend_pass,
        "mom_score":     mom_score,
        "rs_63d":        rs_63d,
        "vol_pctile":    vol_pctile,
        "quad_Q2":       quad_Q2,
        "quad_Q3":       quad_Q3,
        "quad_Q4":       quad_Q4,
        "liq_expanding": liq_exp,
        **fam,
    }
    return vec


# ─────────────────────────────────────────────────────────────────────────────
# Schema guard
# ─────────────────────────────────────────────────────────────────────────────

def _check_schema(model: dict) -> bool:
    """Return True if the model artifact's design matches _DESIGN exactly."""
    artifact_design = model.get("config", {}).get("design", [])
    if artifact_design != _DESIGN:
        log.warning(
            "hazard_score: model design mismatch — artifact has %d features, "
            "scorer knows %d; refusing to score (epoch drift?)",
            len(artifact_design), len(_DESIGN),
        )
        return False
    epoch_str = model.get("turn_def_version", "")
    if epoch_str and _EPOCH not in epoch_str and epoch_str != _EPOCH:
        log.warning(
            "hazard_score: epoch mismatch — artifact '%s', scorer expects '%s'",
            epoch_str, _EPOCH,
        )
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Logistic prediction + isotonic calibration
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _logistic_raw(vec: dict[str, float], coef: dict) -> float:
    """Compute the raw (uncalibrated) logistic prediction for one period."""
    w   = coef["w"]
    b   = coef["b"]
    mu  = coef["mu"]
    sd  = coef["sd"]

    dot = b
    for feat in _DESIGN:
        val = vec.get(feat, 0.0)
        if feat in mu:                              # continuous — standardise
            val = (val - mu[feat]) / max(sd.get(feat, 1.0), 1e-9)
        dot += w.get(feat, 0.0) * val
    return _sigmoid(dot)


def _isotonic_lookup(raw_p: float, cal: dict) -> float:
    """Interpolate the isotonic calibration map (piecewise-constant stairs).

    The map is stored as parallel x (raw logit outputs) / y_cal (calibrated)
    arrays.  np is not available here — hand-roll a binary-search interpolation.
    """
    xs = cal["x"]
    ys = cal["y_cal"]
    n = len(xs)
    if n == 0:
        return raw_p

    # clamp
    if raw_p <= xs[0]:
        return float(ys[0])
    if raw_p >= xs[-1]:
        return float(ys[-1])

    # binary search for the insertion point
    lo, hi = 0, n - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if xs[mid] <= raw_p:
            lo = mid
        else:
            hi = mid
    # linear interpolation between lo and hi
    t = (raw_p - xs[lo]) / (xs[hi] - xs[lo])
    return float(ys[lo]) + t * (float(ys[hi]) - float(ys[lo]))


# ─────────────────────────────────────────────────────────────────────────────
# KM PRIOR lookup
# ─────────────────────────────────────────────────────────────────────────────

def _km_prior(km: dict, direction: str, family: str, h_months: int) -> float:
    """Return the family-stratified KM P(turn ≤ h months) from the baseline.

    Falls back to pooled if the family is not in the baseline.
    h_months: 1, 3, or 6.
    """
    # Map engine family tag to KM baseline family key
    fam_map = {
        "sector":  "us_sector",
        "basket":  "us_sector",
        "flagship":"us_sector",
        "country": "country",
        "cn_sector":"cn_sector",
    }
    fam_key = fam_map.get(family, "pooled")

    fam_data = km.get("families", {}).get(fam_key) or km.get("pooled", {})
    dir_data = fam_data.get(direction) or km.get("pooled", {}).get(direction, {})
    km_by_month = dir_data.get("km_by_month", [])

    # Find the survival at age_m == h_months
    for row in km_by_month:
        if row.get("age_m") == h_months:
            return max(0.0, min(1.0, 1.0 - float(row["survival"])))

    # If we couldn't find it, use cumulative product approximation from available months
    survival = 1.0
    for row in sorted(km_by_month, key=lambda r: r.get("age_m", 0)):
        lam = float(row.get("lambda", 0.0))
        survival *= (1.0 - lam)
        if row.get("age_m", 0) >= h_months:
            break
    return max(0.0, min(1.0, 1.0 - survival))


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score(
    hazard_features: dict,
    direction: Literal["up", "down"],
    family: str = "sector",
    quad: str | None = None,
    liq_expanding: bool | None = None,
) -> dict | None:
    """Score the open leg's turn-hazard for h=1/3/6 months.

    Parameters
    ----------
    hazard_features : the dict from `now.hazard_features` (sector_cycles._hazard_features)
    direction       : 'up' (running up-leg, watching for peak) or
                      'down' (running down-leg, watching for trough)
    family          : hazard-pool family tag ('sector'|'country'|'cn_sector'|'basket'|'flagship')
    quad            : current macro quad label ('Q1'|'Q2'|'Q3'|'Q4'|None)
    liq_expanding   : current liquidity state (True/False/None)

    Returns
    -------
    dict  {
        'epoch': str,
        'revision_optimistic': bool,
        '1m': {'p': float, 'source': 'MODEL'|'PRIOR', 'cell_verdict': str},
        '3m': {...},
        '6m': {...},
    }
    or None when the schema guard fails or features are insufficient.
    """
    if not hazard_features:
        return None

    try:
        model = _load_model()
        km    = _load_km()
    except Exception as exc:
        log.warning("hazard_score: cannot load artifact: %s", exc)
        return None

    if not _check_schema(model):
        return None

    vec = _build_feature_vector(hazard_features, direction, family, quad, liq_expanding)
    if vec is None:
        return None

    coef = model["coefficients"].get(direction)
    if coef is None:
        log.warning("hazard_score: no coefficients for direction=%r", direction)
        return None

    ledger = model["ledger"].get(direction, {})
    calibration = model["calibration"].get(direction, {})

    raw_p = _logistic_raw(vec, coef)

    out: dict = {
        "epoch": _EPOCH,
        "revision_optimistic": bool(model.get("revision_optimistic", True)),
        "direction": direction,
    }

    for h_str in _HORIZONS:
        h_label = _H_LABELS[h_str]
        h_int   = int(h_str)
        cell    = ledger.get(h_label) or {}
        verdict = cell.get("verdict", "PRIOR")

        if verdict == "PASS":
            cal = calibration.get(h_str, {})
            if cal:
                p_cal = _isotonic_lookup(raw_p, cal)
            else:
                p_cal = raw_p
            out[h_label] = {"p": round(p_cal, 4), "source": "MODEL", "cell_verdict": "PASS"}
        else:
            # PRIOR: return family-stratified KM baseline
            p_prior = _km_prior(km, direction, family, h_int)
            out[h_label] = {"p": round(p_prior, 4), "source": "PRIOR", "cell_verdict": "PRIOR"}

    return out


def score_from_record(rec: dict) -> dict | None:
    """Convenience: extract hazard_features + direction from a full cycle record.

    The direction is derived from rec['now']['phase']:
      Recovery / Expansion / Trough  →  direction='up'  (watching for a peak)
      Peak / Downturn                →  direction='down' (watching for a trough)

    Quad and liquidity are read from rec['now'] if present.
    """
    if not rec:
        return None
    nw = rec.get("now") or {}
    hf = nw.get("hazard_features")
    if not hf:
        return None

    phase = nw.get("phase") or nw.get("phase_v2") or ""
    direction: Literal["up", "down"] = "up" if phase in _UP_PHASES else "down"

    family = rec.get("family") or "sector"
    # Regime context — stored in the record when the engine has run score_live
    quad       = nw.get("quad") or None
    liq_exp    = nw.get("liq_expanding")

    return score(hf, direction, family, quad, liq_exp)
