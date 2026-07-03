"""engine/regime_vector.py — thin regime aggregator for the Setup-Species program (W0.5a).

CONSUME, NEVER RE-DERIVE.  All axes are read from already-computed siblings;
no new macro model is built here.  One new categorical state is introduced:
rate_pressure — fully specified in §3.4 of SETUP_SPECIES_MASTERPLAN_BY_FABLE.md.

Published as ``latest['regime_vector']`` by engine/run.py and persisted daily to
``data/regime/regime_vector.parquet`` (NOT regime_history.parquet — four files share
that name across markets; wrong-file appends are the named #1026-class hazard).

Parquet: append-only, keep-FIRST on date (PIT discipline).  The file is git-tracked
(NOT gitignored) so the daily ``git add data/`` in the nightly workflow picks it up.

Hysteresis
----------
ALL state transitions (rate_pressure and any future categorical axis added here) use
2-consecutive-day hysteresis — a candidate state must persist for two consecutive days
before the published state flips.  The prior state is read from the parquet store
(last committed row).  On the very first run (empty store) the published state is None (no prior
to confirm against); the candidate is persisted so day 2 can commit.
Hysteresis state is stored in the parquet itself, not in a separate side-file.

Degraded inputs
---------------
If any input the engine needs carries a degraded / freshness bit the affected axis
publishes ``null`` and the row-level ``regime_vector_degraded`` flag is set to True.
The vector NEVER defaults to a "safe" or "neutral" state on data outage — null is the
only honest output.  Downstream consumers must treat a degraded vector as read-only
context, never as a sizing input.

rate_pressure constants (§3.4, frozen — do not adjust without a §8 status row)
---------------------------------------------------------------------------
RATE_RELIEF_BP    = −25  (≤ this → "relief")
RATE_PRESSURE_BP  = +25  (> this → "pressure")
PANIC escalation: rates_scare sub-score ≥ RATE_PANIC_SCARE_THRESHOLD → "panic"
RATE_PANIC_SCARE_THRESHOLD = 78.0  (== the radar's LOUD tier: "elevated" band floor, §3.4)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# §3.4 rate_pressure constants (FIXED INPUT — see module docstring)
# ---------------------------------------------------------------------------
RATE_RELIEF_BP: float = -25.0    # real10y_chg63 ≤ this → "relief"
RATE_PRESSURE_BP: float = 25.0   # real10y_chg63 > this → "pressure"
# Radar rates-scare sub-score at/above which "pressure" escalates to "panic".
# §3.4 letter: escalation fires at the radar's LOUD tier — the "elevated" band
# floor (78.0, risk_radar._DEFAULT_BANDS / _ALERT_FROM), NOT the "caution" floor.
RATE_PANIC_SCARE_THRESHOLD: float = 78.0

# Hysteresis window (consecutive days required before a state transition commits)
_HYSTERESIS_DAYS: int = 2

# Parquet path — distinct from regime_history.parquet (hazard named in §3.4)
_PARQUET_NAME = "regime_vector.parquet"


# ---------------------------------------------------------------------------
# Vocabulary tokens registered with regime_coherence
# ---------------------------------------------------------------------------
#: All valid tokens for the rate_pressure axis.
RATE_PRESSURE_STATES: tuple[str, ...] = ("relief", "neutral", "pressure", "panic")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe(d: Any, *keys: str, default=None):
    """Safe nested dict get — returns `default` on any missing key or non-dict node."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is None:
            return default
    return d


def _is_degraded(d: dict | None, *path: str) -> bool:
    """True if the nested `degraded` field at *path is truthy, or if d is None."""
    if d is None:
        return True
    node = _safe(d, *path) if path else d
    if not isinstance(node, dict):
        return False
    return bool(node.get("degraded"))


def _prior_state(data_dir: Path | None = None) -> dict:
    """Read the last committed regime_vector row to seed hysteresis.
    Returns {} when the parquet is absent or unreadable."""
    try:
        ddir = data_dir or config.data_dir()
        p = ddir / "regime" / _PARQUET_NAME
        if not p.exists():
            return {}
        df = pd.read_parquet(p)
        if df.empty:
            return {}
        row = df.sort_index().iloc[-1]
        return dict(row)
    except Exception as e:  # noqa: BLE001
        log.warning("regime_vector: could not read prior state for hysteresis (%s)", e)
        return {}


def _apply_hysteresis(
    candidate: str | None,
    prior_state_val: str | None,
    prior_candidate: str | None,
    hysteresis_days: int = _HYSTERESIS_DAYS,
) -> str | None:
    """Apply 2-consecutive-day hysteresis.

    ``prior_state_val`` is the published state from the previous committed row.
    ``prior_candidate`` is the candidate that was pending from the previous run
    (stored in the parquet as ``rate_pressure_candidate``).

    A candidate becomes the published state only after it has been the candidate
    for `hysteresis_days` consecutive days.  On day 1 a new candidate replaces the
    prior candidate but does NOT flip the published state.  On day 2+ (candidate
    matches prior_candidate) the state flips.

    Returns the new published state (after hysteresis).
    """
    if candidate is None:
        return prior_state_val
    if candidate == prior_state_val:
        # no transition needed
        return candidate
    # transition pending — check if candidate matches the prior pending candidate
    if candidate == prior_candidate:
        # second consecutive day with this candidate → commit
        return candidate
    # first day of a new candidate → hold current state
    return prior_state_val


# ---------------------------------------------------------------------------
# rate_pressure computation
# ---------------------------------------------------------------------------

def _rate_pressure_base(real10y_chg63_bp: float | None) -> str | None:
    """Base state from DFII10 63d change in basis points, §3.4 cut points."""
    if real10y_chg63_bp is None:
        return None
    if real10y_chg63_bp <= RATE_RELIEF_BP:
        return "relief"
    if real10y_chg63_bp > RATE_PRESSURE_BP:
        return "pressure"
    return "neutral"


def _rates_scare_score(risk_radar: dict | None) -> float | None:
    """Extract the 'rates' scare sub-score from the risk_radar snapshot.

    The scares list has entries ``{"scare": "rates", "score": float, ...}``.
    Returns None when the radar is absent or the rates scare is not present.
    """
    if not isinstance(risk_radar, dict):
        return None
    for s in (risk_radar.get("scares") or []):
        if isinstance(s, dict) and s.get("scare") == "rates":
            v = s.get("score")
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
    return None


def _compute_rate_pressure(
    real10y_chg63_bp: float | None,
    risk_radar: dict | None,
    prior: dict,
) -> tuple[str | None, bool, str | None]:
    """Compute the rate_pressure categorical with hysteresis and panic escalation.

    Returns (published_state, degraded_flag, candidate_for_next_run).
    degraded_flag is True when either input is missing/unusable.
    """
    degraded = False

    # --- input freshness checks ---
    if real10y_chg63_bp is None:
        degraded = True
    radar_degraded = risk_radar is None or risk_radar.get("state") is None
    if radar_degraded:
        degraded = True

    if degraded:
        # null on degraded — never a default state
        return None, True, None

    # --- base state ---
    base = _rate_pressure_base(real10y_chg63_bp)
    if base is None:
        return None, True, None

    # --- panic escalation ---
    rates_score = _rates_scare_score(risk_radar)
    candidate: str
    if base == "pressure" and rates_score is not None and rates_score >= RATE_PANIC_SCARE_THRESHOLD:
        candidate = "panic"
    else:
        candidate = base

    # --- hysteresis ---
    prior_state_val = prior.get("rate_pressure")
    prior_candidate = prior.get("rate_pressure_candidate")
    published = _apply_hysteresis(candidate, prior_state_val, prior_candidate)

    return published, False, candidate


# ---------------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------------

def build(latest: dict, data_dir: Path | None = None) -> dict:
    """Assemble the regime_vector from already-computed siblings in `latest`.

    Never raises past the caller's additive try/except.  Degrades axes
    individually (null + regime_vector_degraded=True) rather than defaulting.

    Parameters
    ----------
    latest : dict
        The in-memory latest.json being assembled by engine/run.py.
    data_dir : Path | None
        Override for config.data_dir() (useful in tests).

    Returns
    -------
    dict
        The regime_vector contract (to be published as latest['regime_vector']).
    """
    prior = _prior_state(data_dir)
    degraded_axes: list[str] = []
    out: dict[str, Any] = {
        "schema_version": 1,
        "schema_note": (
            "W0.5a — thin aggregator; all axes consumed from siblings, never re-derived. "
            "rate_pressure is the one new categorical state (§3.4). "
            "null on any axis = that input was degraded; regime_vector_degraded=true "
            "when any axis is null."
        ),
    }

    # -----------------------------------------------------------------------
    # 1. Growth/inflation quad (quad_vector)
    # -----------------------------------------------------------------------
    qv = latest.get("quad_vector") or {}
    qv_degraded = bool(qv.get("degraded"))
    if qv_degraded or not qv:
        out["quad_hard_label"] = None
        out["quad_p"] = None
        out["quad_confidence"] = None
        out["quad_transition_momentum"] = None
        degraded_axes.append("quad")
    else:
        out["quad_hard_label"] = qv.get("hard_label")
        out["quad_p"] = qv.get("p")
        out["quad_confidence"] = qv.get("confidence")
        out["quad_transition_momentum"] = qv.get("transition_momentum")

    # -----------------------------------------------------------------------
    # 2. Rate pressure (the one new categorical — §3.4)
    # -----------------------------------------------------------------------
    #   Source A: rate_inflation_transmission.state.rates.real_10y_chg_63d_bp
    #   Source B: risk_radar scares[scare="rates"].score
    rit = latest.get("rate_inflation_transmission") or {}
    real_chg_bp: float | None = _safe(rit, "state", "rates", "real_10y_chg_63d_bp")
    try:
        real_chg_bp = float(real_chg_bp) if real_chg_bp is not None else None
    except (TypeError, ValueError):
        real_chg_bp = None

    rr = latest.get("risk_radar")

    # Check degraded bits on inputs
    rit_degraded = (rit is None or (not rit) or real_chg_bp is None)
    rr_degraded = (rr is None or rr.get("state") is None
                   or rr.get("degraded_reason") == "no_signals")

    rp_state, rp_deg, rp_candidate = _compute_rate_pressure(
        None if rit_degraded else real_chg_bp,
        None if rr_degraded else rr,
        prior,
    )
    out["rate_pressure"] = rp_state
    out["rate_pressure_candidate"] = rp_candidate   # stored for next run's hysteresis
    out["rate_pressure_real10y_chg63_bp"] = real_chg_bp
    out["rate_pressure_rates_scare_score"] = _rates_scare_score(rr)
    out["rate_pressure_constants"] = {
        "relief_bp": RATE_RELIEF_BP,
        "pressure_bp": RATE_PRESSURE_BP,
        "panic_scare_threshold": RATE_PANIC_SCARE_THRESHOLD,
        "hysteresis_days": _HYSTERESIS_DAYS,
    }
    if rp_deg:
        degraded_axes.append("rate_pressure")

    # -----------------------------------------------------------------------
    # 3. Liquidity (regime_one + liquidity_quality)
    # -----------------------------------------------------------------------
    r1 = latest.get("regime_one") or {}
    r1_degraded = bool(r1.get("degraded"))
    lq = latest.get("liquidity_quality") or {}

    # regime_one carries the liquidity nudge at fused_risk.gate.liquidity
    lq_overlay = ((r1.get("fused_risk") or {}).get("gate") or {}).get("liquidity")
    # also try the top-level legacy key
    if lq_overlay is None:
        lq_overlay = latest.get("liquidity_overlay")

    if r1_degraded or not r1:
        out["liquidity_overlay"] = None
        out["fused_risk_label"] = None
        out["fused_risk_gross"] = None
        out["liquidity_quality_label"] = None
        degraded_axes.append("liquidity")
    else:
        fr = r1.get("fused_risk") or {}
        out["liquidity_overlay"] = lq_overlay
        out["fused_risk_label"] = fr.get("label")
        out["fused_risk_gross"] = fr.get("gross_factor")
        out["liquidity_quality_label"] = lq.get("label") if lq else None
        if lq and lq.get("degraded"):
            out["liquidity_quality_label"] = None
            degraded_axes.append("liquidity_quality")

    # -----------------------------------------------------------------------
    # 4. Risk appetite / stress (MRS + risk_radar + favor_entries / cap_leadership)
    # -----------------------------------------------------------------------
    mr = latest.get("macro_risk") or {}
    # MRS is published as macro_risk.mrs or macro_risk.score — check both
    mrs_score = mr.get("mrs") if mr else None
    if mrs_score is None:
        mrs_score = mr.get("score") if mr else None

    rr_state = rr.get("state") if rr else None
    favor_entries = (rr or {}).get("favor_entries")
    cap_leadership = (rr or {}).get("cap_leadership")

    # Also pull from fused_risk (which carries the re-fused directives from refuse())
    fr = (r1.get("fused_risk") or {}) if r1 else {}
    if favor_entries is None:
        favor_entries = fr.get("favor_entries")
    if cap_leadership is None:
        cap_leadership = fr.get("cap_leadership")

    out["mrs_score"] = mrs_score
    out["risk_radar_state"] = rr_state
    out["favor_entries"] = favor_entries
    out["cap_leadership"] = cap_leadership

    if rr is None or rr_state is None:
        degraded_axes.append("risk_radar")

    # -----------------------------------------------------------------------
    # 5. Volatility (vol_regime 4-state + ts_slope)
    # -----------------------------------------------------------------------
    vr = latest.get("vol_regime") or {}
    vr_regime = vr.get("regime") if vr else None
    vr_ts_slope = vr.get("ts_slope") if vr else None
    vr_ts_slope_state = vr.get("ts_slope_state") if vr else None

    out["vol_regime"] = vr_regime
    out["vol_ts_slope"] = vr_ts_slope
    out["vol_ts_slope_state"] = vr_ts_slope_state

    if not vr or vr_regime is None:
        degraded_axes.append("vol_regime")

    # -----------------------------------------------------------------------
    # 6. Sector rotation (subsector_confluence sides + donor-unwind state)
    # -----------------------------------------------------------------------
    # subsector_confluence data is not yet persisted in latest.json — it is computed
    # per-stock in build_stock_library.  The donor state IS published per-board
    # in the us_stocks payload but is not in the main latest.json.
    # Rule: if the key is missing → null (degraded) per §3.4.
    # Future wiring (Stage B) will add a subsector_confluence summary to latest.json.
    subsector_rotation_sides = None
    donor_unwind_state = None
    out["subsector_rotation_sides"] = subsector_rotation_sides
    out["donor_unwind_state"] = donor_unwind_state
    # NOTE: marked degraded only when we know the data exists but is bad.
    # When the key is simply not yet wired (current state), we emit null without
    # marking it degraded to avoid poisoning the overall vector.
    # This is consistent with the spec: "consume, don't model" — publish null for
    # axes whose source is not yet wired, without overriding regime_vector_degraded.

    # -----------------------------------------------------------------------
    # 7. Breadth (pct_above_50/200 + global breadth leg from risk_radar)
    # -----------------------------------------------------------------------
    # Read from the breadth parquet (US) — the same file risk_radar reads.
    breadth_50: float | None = None
    breadth_200: float | None = None
    try:
        ddir = data_dir or config.data_dir()
        bf_path = ddir / "breadth" / "breadth.parquet"
        if bf_path.exists():
            bf = pd.read_parquet(bf_path)
            if not bf.empty:
                last = bf.sort_index().iloc[-1]
                if "pct_above_50" in bf.columns:
                    v = last.get("pct_above_50")
                    breadth_50 = float(v) if v is not None and pd.notna(v) else None
                if "pct_above_200" in bf.columns:
                    v = last.get("pct_above_200")
                    breadth_200 = float(v) if v is not None and pd.notna(v) else None
    except Exception as e:  # noqa: BLE001
        log.warning("regime_vector: breadth read failed (%s)", e)

    # Global breadth from risk_radar scares (tier-B "global" scare)
    global_breadth_score: float | None = None
    if rr and isinstance(rr.get("scares"), list):
        for s in rr["scares"]:
            if isinstance(s, dict) and s.get("scare") == "global":
                global_breadth_score = s.get("score")
                break

    out["breadth_pct_above_50"] = breadth_50
    out["breadth_pct_above_200"] = breadth_200
    out["global_breadth_scare_score"] = global_breadth_score

    if breadth_50 is None and breadth_200 is None:
        degraded_axes.append("breadth")

    # -----------------------------------------------------------------------
    # 8. De-escalation / dislocation (radar deescalation + Fed-put switch)
    # -----------------------------------------------------------------------
    deesc = (rr or {}).get("deescalation") or {}
    out["deescalation_eligible"] = deesc.get("eligible")
    out["deescalation_trajectory"] = (rr or {}).get("trajectory")

    dis = latest.get("dislocation") or {}
    out["dislocation_verdict"] = dis.get("verdict")
    out["dislocation_fed_put"] = dis.get("fed_put")
    out["dislocation_active"] = dis.get("dislocation_active")

    # -----------------------------------------------------------------------
    # Asof stamp
    # -----------------------------------------------------------------------
    asof_str: str | None = None
    for src in (qv, r1, rr, lq, vr):
        if isinstance(src, dict):
            v = src.get("asof")
            if v:
                asof_str = str(v)
                break
    if asof_str is None:
        asof_str = str(pd.Timestamp.today().date())
    out["asof"] = asof_str

    # -----------------------------------------------------------------------
    # Overall degraded flag
    # -----------------------------------------------------------------------
    regime_vector_degraded = bool(degraded_axes)
    out["regime_vector_degraded"] = regime_vector_degraded
    out["degraded_axes"] = degraded_axes

    return out


# ---------------------------------------------------------------------------
# Parquet persistence (append-only, keep-first on date)
# ---------------------------------------------------------------------------

def _parquet_path(data_dir: Path | None = None) -> Path:
    ddir = data_dir or config.data_dir()
    return Path(ddir) / "regime" / _PARQUET_NAME


def persist(rv: dict, data_dir: Path | None = None) -> None:
    """Append today's regime_vector to data/regime/regime_vector.parquet.

    Keep-FIRST on date (PIT discipline): if a row for today already exists
    it is NOT overwritten — the first write of the day wins.
    """
    if not rv or not rv.get("asof"):
        log.warning("regime_vector.persist: nothing to persist (empty or no asof)")
        return

    try:
        date_key = pd.Timestamp(rv["asof"]).normalize()
    except (TypeError, ValueError) as e:
        log.warning("regime_vector.persist: bad asof '%s' (%s)", rv.get("asof"), e)
        return

    # Build a flat serializable row (dicts/lists → JSON strings)
    row: dict[str, Any] = {}
    for k, v in rv.items():
        if isinstance(v, (dict, list)):
            import json
            row[k] = json.dumps(v, default=str)
        elif isinstance(v, bool):
            row[k] = int(v)   # parquet bool → int for compatibility
        else:
            row[k] = v

    new_df = pd.DataFrame([row], index=pd.DatetimeIndex([date_key], name="date"))

    p = _parquet_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        try:
            existing = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("regime_vector.persist: could not read existing parquet (%s) — overwriting", e)
            existing = pd.DataFrame()

        if not existing.empty and date_key in existing.index:
            log.debug("regime_vector.persist: date %s already present — keep-first; skipping", date_key.date())
            return

        # Align columns (union schema — new columns appear as NaN in old rows)
        combined = pd.concat([existing, new_df], axis=0)
        combined = combined.sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
    else:
        combined = new_df

    combined.to_parquet(p, index=True)
    log.info("regime_vector: persisted %s to %s", date_key.date(), p)


# ---------------------------------------------------------------------------
# Vocabulary registration with engine/regime_coherence
# ---------------------------------------------------------------------------

#: Token sets for regime_coherence vocabulary aliasing (§3.4 vocabulary drift note).
#: The coherence module enumerates all tokens explicitly so a stress signal is
#: never missed on a spelling variant.
REGIME_VECTOR_VOCABULARY: dict[str, tuple[str, ...]] = {
    # rate_pressure states
    "rate_pressure_relief": ("relief",),
    "rate_pressure_neutral": ("neutral",),
    "rate_pressure_pressure": ("pressure",),
    "rate_pressure_panic": ("panic",),
    # vol_regime 4-state (from engine/vol_regime._regime_label)
    "vol_regime_calm": ("calm-contango",),
    "vol_regime_normalizing": ("normalizing",),
    "vol_regime_warning": ("warning",),
    "vol_regime_stress": ("backwardation-stress",),
}
