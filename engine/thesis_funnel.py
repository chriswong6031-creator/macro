"""engine/thesis_funnel.py — LT-4: Long-Hold Admission Funnel (shadow tier).

DISPLAY-ONLY — G1-DEFERRED ruling 2026-07-06.  horizon_role=hold_thesis.
These states MUST NOT feed board ordering, alert triage, top-setups gates,
or push floor.  No composite score, no weights, no behavioral surface (LH-R1, LH-R2).

Build contract: LT External Foundation Adjudication §3 LT-4
  research/long_hold/LT_EXTERNAL_FOUNDATION_ADJUDICATION.md

Ruling LH-R2 (transparent AND-gate)
-------------------------------------
The funnel is a TRANSPARENT conjunction of INDEPENDENTLY REGISTERED flags.
NO composite score, NO weighting, NO fused output.  Each flag is surfaced
individually so the reader can see exactly which criterion drove the state.
The ceiling is ``thesis_candidate_shadow`` — no ``active_thesis`` exists
anywhere in this module (W3-locked; W3/W4 remain deferred per G1 ruling).

FROZEN v1 state logic (display conventions, NOT registered hypotheses)
-----------------------------------------------------------------------
Survival flags (each independently computed):

  s1_dilution:
    shares_yoy_change >= +3%.  Same +3% threshold used by
    scripts/research/missed_hold_study.py and engine/capital_allocation.py
    _DILUTIVE_SHARES_CHANGE_PCT.  Source: capital_allocation_delta from
    engine/capital_allocation.py OR shares_yoy_change_pct from the same module.

  s2_moat_falsifier:
    Any of the four engine/moat_falsifiers.py sensors firing on the latest
    adjacent-FY pair.  Sensors: margin_compression_despite_revenue_growth,
    receivables_stretch, inventory_build, capital_intensity_rising.

  s3_solvency:
    Altman Z < 1.8 where computable (< 1.81 is the classic distress floor;
    we use 1.8 to match engine/stock_fundamentals.py _ALTMAN_DISTRESS_MAX).
    Source: altman sub-dict from engine/stock_fundamentals.py _multiyear output
    (already computed in panels() — passed in here; NOT re-loaded).

  s4_coverage (insufficient data):
    Fewer than 2 of {shares_yoy, moat sensors, altman_z} are computable.
    When coverage is below this floor the state is not_eligible regardless of
    what the available sensors say — the AND-gate is too incomplete to use.

States (enum — EXACTLY these three values, no others):

  not_eligible:
    s4_coverage fires  OR  any of s1/s2/s3 fires.

  watch_for_thesis:
    Survival passes (none of s1/s2/s3 fire, coverage ok),
    BUT NOT both (piotroski_f >= 6 AND capital_allocation_delta != 'dilutive').

  thesis_candidate_shadow:
    watch_for_thesis AND piotroski_f >= 6 AND capital_allocation_delta != 'dilutive'.
    ('unavailable' for capital_allocation_delta does NOT disqualify — the
    missing data is not treated as a negative; only 'dilutive' disqualifies.)

Context references (not gate inputs — printed for transparency):
  expectation_state: block from engine/expectation_state.py
  capital_allocation_delta: from engine/capital_allocation.py
  (insider context from engine/stock_fundamentals.py positioning block if available)

All output dicts carry:
  _display_only  = True
  _horizon_role  = 'hold_thesis'
  _version       = 'v1'

Usage
-----
  from engine.thesis_funnel import compute_thesis_funnel

  result = compute_thesis_funnel(
      ticker,
      altman_z=altman_z,           # float | None — from _multiyear()/panels()
      altman_approx=False,         # bool — approx flag from _altman()
      moat_falsifiers_result=mf,   # dict from compute_moat_falsifiers()
      shares_yoy_change_pct=syoy,  # float | None — from capital_allocation block
      capital_allocation_delta=delta,  # str | None — 'accretive'|'neutral'|'dilutive'|'unavailable'
      piotroski_score=f_score,     # int | None — the .score field from _piotroski()
      piotroski_of=f_of,           # int | None — the .of  field from _piotroski()
      expectation_state=es,        # dict | None — from expectation_states()
      insider_context=ins,         # dict | None — positioning.insider block
  )

Standalone smoke-test (real data path required)::

  python -m engine.thesis_funnel AAPL
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ── firewall constants ────────────────────────────────────────────────────────
_HORIZON_ROLE = "hold_thesis"
_DISPLAY_ONLY = True
_VERSION = "v1"

# ── threshold constants (frozen v1 display semantics) ─────────────────────────
# Dilution threshold (s1): same as capital_allocation._DILUTIVE_SHARES_CHANGE_PCT
_DILUTION_THRESHOLD_PCT = 3.0
# Solvency threshold (s3): Altman Z < 1.81 is classic distress;
# stock_fundamentals.py uses _ALTMAN_DISTRESS_MAX for the policy layer.
_ALTMAN_DISTRESS_MAX = 1.81
# Piotroski floor for thesis_candidate_shadow
_PIOTROSKI_CANDIDATE_MIN = 6
# Minimum computable sensors before coverage is acceptable
_COVERAGE_MIN_COMPUTABLE = 2


# ── state labels (frozen; must match template EN/ZH copy) ────────────────────
STATES = ("not_eligible", "watch_for_thesis", "thesis_candidate_shadow")


def _safe_float(x: Any) -> float | None:
    """Coerce to float, None on any failure (NaN, None, non-numeric)."""
    if x is None:
        return None
    try:
        import math
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _flag_s1_dilution(
    shares_yoy_change_pct: float | None,
    capital_allocation_delta: str | None,
) -> dict[str, Any]:
    """s1: dilution flag — shares_yoy_change >= +3%.

    Checks shares_yoy_change_pct directly.  capital_allocation_delta='dilutive'
    is also noted as context but the gate is the raw shares_yoy_change_pct test
    so both the threshold and the source are transparent.

    Returns:
      fired: True | False | None (None = insufficient data to evaluate)
      value: float | None (shares_yoy_change_pct)
      threshold: +3.0 (pct)
      computable: bool
    """
    syoy = _safe_float(shares_yoy_change_pct)
    computable = syoy is not None

    if not computable:
        return {
            "fired": None,
            "value": None,
            "threshold_pct": _DILUTION_THRESHOLD_PCT,
            "computable": False,
            "note": "shares_yoy_change_pct unavailable",
        }

    fired = bool(syoy >= _DILUTION_THRESHOLD_PCT)
    return {
        "fired": fired,
        "value": round(syoy, 2),
        "threshold_pct": _DILUTION_THRESHOLD_PCT,
        "computable": True,
        "capital_allocation_delta_context": capital_allocation_delta,
    }


def _flag_s2_moat_falsifier(moat_falsifiers_result: dict | None) -> dict[str, Any]:
    """s2: any moat falsifier sensor firing on latest adjacent-FY pair.

    Returns:
      fired: True | False | None
      any_fired: True | False | None
      sensors_fired: list of sensor names that fired
      sensor_coverage: 'full' | 'partial' | 'missing'
      computable: bool
    """
    if not moat_falsifiers_result or moat_falsifiers_result.get("sensor_coverage") == "missing":
        return {
            "fired": None,
            "any_fired": None,
            "sensors_fired": [],
            "sensor_coverage": "missing",
            "computable": False,
            "note": "moat_falsifiers result missing or no data",
        }

    sensors = moat_falsifiers_result.get("sensors") or {}
    sensors_fired = [
        name for name, sv in sensors.items()
        if sv.get("fired") is True
    ]
    # A sensor with fired=None is unevaluable (insufficient data), not 'not firing'
    any_evaluable = any(sv.get("fired") is not None for sv in sensors.values())
    computable = any_evaluable
    any_fired = bool(sensors_fired) if computable else None

    return {
        "fired": any_fired,
        "any_fired": any_fired,
        "sensors_fired": sensors_fired,
        "sensor_coverage": moat_falsifiers_result.get("sensor_coverage", "partial"),
        "computable": computable,
        "n_sensors_evaluable": sum(1 for sv in sensors.values() if sv.get("fired") is not None),
    }


def _flag_s3_solvency(
    altman_z: float | None,
    altman_approx: bool = False,
) -> dict[str, Any]:
    """s3: solvency flag — Altman Z < 1.81 (distress zone).

    approx=True means the score was computed without all required legs;
    the task spec says 'where computable' — we treat approx=True as a
    degraded-but-usable estimate and still evaluate, flagging it.

    Returns:
      fired: True | False | None
      value: float | None (Altman Z)
      threshold: 1.81
      approx: bool
      computable: bool
    """
    z = _safe_float(altman_z)
    computable = z is not None

    if not computable:
        return {
            "fired": None,
            "value": None,
            "threshold": _ALTMAN_DISTRESS_MAX,
            "approx": altman_approx,
            "computable": False,
            "note": "Altman Z not computable (missing data)",
        }

    fired = bool(z < _ALTMAN_DISTRESS_MAX)
    return {
        "fired": fired,
        "value": round(z, 2),
        "threshold": _ALTMAN_DISTRESS_MAX,
        "approx": altman_approx,
        "computable": True,
    }


def _coverage_check(
    s1: dict, s2: dict, s3: dict,
) -> dict[str, Any]:
    """s4: coverage — fewer than 2 of {shares_yoy, moat sensors, altman_z} computable.

    Returns:
      fired: bool (True = insufficient coverage → not_eligible)
      n_computable: int
      floor: int (minimum required)
    """
    n = sum([
        int(bool(s1["computable"])),
        int(bool(s2["computable"])),
        int(bool(s3["computable"])),
    ])
    return {
        "fired": bool(n < _COVERAGE_MIN_COMPUTABLE),
        "n_computable": n,
        "floor": _COVERAGE_MIN_COMPUTABLE,
        "inputs_checked": ["shares_yoy", "moat_sensors", "altman_z"],
    }


def compute_thesis_funnel(
    ticker: str,
    *,
    altman_z: float | None = None,
    altman_approx: bool = False,
    moat_falsifiers_result: dict | None = None,
    shares_yoy_change_pct: float | None = None,
    capital_allocation_delta: str | None = None,
    piotroski_score: int | None = None,
    piotroski_of: int | None = None,
    expectation_state: dict | None = None,
    insider_context: dict | None = None,
) -> dict[str, Any]:
    """Compute the LT-4 thesis funnel state for one ticker.

    All inputs are pre-computed by panels() callers; this function is PURE
    (no I/O, no parquet reads).  Caller-side the result is keyed as
    ``thesis_funnel`` inside the per-ticker panel dict.

    Parameters
    ----------
    ticker:
        Ticker symbol (for labelling only).
    altman_z:
        Altman Z from engine/stock_fundamentals.py _altman() → my["altman"]["z"].
        Pass None if not computable.
    altman_approx:
        True if the Altman Z was computed without all legs (approx flag from _altman()).
    moat_falsifiers_result:
        Full result dict from engine/moat_falsifiers.compute_moat_falsifiers().
        Pass None if unavailable.
    shares_yoy_change_pct:
        YoY share-count change (%) from engine/capital_allocation — the
        shares_yoy_change_pct field. Pass None if unavailable.
    capital_allocation_delta:
        'accretive' | 'neutral' | 'dilutive' | 'unavailable' | None.
        'dilutive' disqualifies from thesis_candidate_shadow.
        'unavailable' and None do NOT disqualify.
    piotroski_score:
        The .score field from engine/stock_fundamentals._piotroski() (int).
    piotroski_of:
        The .of field from _piotroski() — denominator (int).
    expectation_state:
        The full dict from engine/expectation_state — printed as context only.
    insider_context:
        Positioning.insider block — printed as context only.

    Returns
    -------
    dict with keys:
      ticker, state, flags (s1..s4), gate_inputs,
      context (expectation_state, capital_allocation_delta, insider),
      _horizon_role, _display_only, _version
    """
    ticker = str(ticker).upper().strip()

    # ── Step 1: compute each flag ─────────────────────────────────────────────
    s1 = _flag_s1_dilution(shares_yoy_change_pct, capital_allocation_delta)
    s2 = _flag_s2_moat_falsifier(moat_falsifiers_result)
    s3 = _flag_s3_solvency(altman_z, altman_approx)
    s4 = _coverage_check(s1, s2, s3)

    # ── Step 2: state machine ─────────────────────────────────────────────────
    # Survival fails → not_eligible
    if s4["fired"]:
        state = "not_eligible"
        state_reason = "s4_insufficient_data"
    elif s1["fired"] is True:
        state = "not_eligible"
        state_reason = "s1_dilution"
    elif s2["fired"] is True:
        state = "not_eligible"
        state_reason = "s2_moat_falsifier"
    elif s3["fired"] is True:
        state = "not_eligible"
        state_reason = "s3_solvency"
    else:
        # Survival gate passed — check candidate upgrade conditions
        piotroski_ok = (
            piotroski_score is not None
            and piotroski_of is not None
            and int(piotroski_score) >= _PIOTROSKI_CANDIDATE_MIN
        )
        # 'dilutive' disqualifies; 'unavailable'/None do NOT disqualify
        cap_alloc_ok = capital_allocation_delta != "dilutive"

        if piotroski_ok and cap_alloc_ok:
            state = "thesis_candidate_shadow"
            state_reason = "survival_pass+f>={n}+non_dilutive".format(n=_PIOTROSKI_CANDIDATE_MIN)
        else:
            state = "watch_for_thesis"
            parts = []
            if not piotroski_ok:
                if piotroski_score is None:
                    parts.append("piotroski_unavailable")
                else:
                    parts.append(f"piotroski_f={piotroski_score}_of_{piotroski_of}_below_{_PIOTROSKI_CANDIDATE_MIN}")
            if not cap_alloc_ok:
                parts.append("capital_allocation_dilutive")
            state_reason = "+".join(parts) if parts else "survival_pass"

    # ── Step 3: Piotroski context (not a gate input for survival, IS for candidate) ──
    piotroski_ctx: dict[str, Any] = {
        "score": piotroski_score,
        "of": piotroski_of,
        "meets_candidate_floor": (
            piotroski_score is not None
            and piotroski_of is not None
            and int(piotroski_score) >= _PIOTROSKI_CANDIDATE_MIN
        ),
        "floor": _PIOTROSKI_CANDIDATE_MIN,
    }

    # ── Step 4: context block (non-gate; print for transparency) ─────────────
    context: dict[str, Any] = {
        "capital_allocation_delta": capital_allocation_delta,
    }
    if expectation_state is not None:
        context["expectation_state"] = expectation_state
    if insider_context is not None:
        context["insider"] = insider_context

    return {
        "ticker": ticker,
        "state": state,
        "state_reason": state_reason,
        "flags": {
            "s1_dilution": s1,
            "s2_moat_falsifier": s2,
            "s3_solvency": s3,
            "s4_coverage": s4,
        },
        "gate_inputs": {
            "piotroski": piotroski_ctx,
        },
        "context": context,
        "_horizon_role": _HORIZON_ROLE,
        "_display_only": _DISPLAY_ONLY,
        "_version": _VERSION,
    }


# ── Batch helper for panels() ─────────────────────────────────────────────────

def compute_thesis_funnel_safe(
    ticker: str,
    *,
    altman_z: float | None = None,
    altman_approx: bool = False,
    moat_falsifiers_result: dict | None = None,
    shares_yoy_change_pct: float | None = None,
    capital_allocation_delta: str | None = None,
    piotroski_score: int | None = None,
    piotroski_of: int | None = None,
    expectation_state: dict | None = None,
    insider_context: dict | None = None,
) -> dict[str, Any] | None:
    """Non-fatal wrapper for compute_thesis_funnel.

    Returns None on any exception so that a single broken ticker never
    crashes the full panels() build.  Logs at DEBUG level.
    """
    try:
        return compute_thesis_funnel(
            ticker,
            altman_z=altman_z,
            altman_approx=altman_approx,
            moat_falsifiers_result=moat_falsifiers_result,
            shares_yoy_change_pct=shares_yoy_change_pct,
            capital_allocation_delta=capital_allocation_delta,
            piotroski_score=piotroski_score,
            piotroski_of=piotroski_of,
            expectation_state=expectation_state,
            insider_context=insider_context,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("thesis_funnel: skipped for %s (%s)", ticker, exc)
        return None


# ── Standalone CLI smoke-test ─────────────────────────────────────────────────

def main() -> int:
    """Smoke-test: load real data for a ticker and compute the funnel state."""
    import json
    import sys
    import time

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    t0 = time.time()

    # Lazy imports so the module stays import-light in normal build paths
    from lib import config  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    from engine.moat_falsifiers import compute_moat_falsifiers, compute_base_rates  # noqa: PLC0415
    from engine.capital_allocation import compute_capital_allocation  # noqa: PLC0415

    data_dir = config.data_dir()

    # Load statements
    stmt_path = data_dir / "edgar" / "statements.parquet"
    try:
        statements_df = pd.read_parquet(stmt_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cannot load statements.parquet: %s", exc)
        statements_df = pd.DataFrame()

    # Load fundamentals_panel
    fp_path = data_dir / "edgar" / "fundamentals_panel.parquet"
    try:
        fp_df = pd.read_parquet(fp_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cannot load fundamentals_panel.parquet: %s", exc)
        fp_df = pd.DataFrame()

    # Load quarterly
    qp_path = data_dir / "edgar" / "statements_quarterly.parquet"
    try:
        quarterly_df = pd.read_parquet(qp_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cannot load statements_quarterly.parquet: %s", exc)
        quarterly_df = pd.DataFrame()

    # Compute moat falsifiers
    base_rates = compute_base_rates(statements_df) if not statements_df.empty else {}
    mf_result = compute_moat_falsifiers(ticker, statements_df, base_rates=base_rates)

    # Compute capital allocation
    ca_result = compute_capital_allocation(
        ticker, quarterly_df, fp_df, statements_df=statements_df,
    )

    # Get Altman Z from stock_fundamentals-style multiyear computation
    from engine.stock_fundamentals import _load_statements, _multiyear  # noqa: PLC0415
    rows = _load_statements().get(ticker) or []
    my = _multiyear(rows, None)
    altman_block = (my or {}).get("altman") or {}
    altman_z = altman_block.get("z")
    altman_approx = bool(altman_block.get("approx", False))

    # Get Piotroski
    from engine.stock_fundamentals import _piotroski  # noqa: PLC0415
    pio = _piotroski(rows) or {}

    result = compute_thesis_funnel(
        ticker,
        altman_z=altman_z,
        altman_approx=altman_approx,
        moat_falsifiers_result=mf_result,
        shares_yoy_change_pct=ca_result.get("shares_yoy_change_pct"),
        capital_allocation_delta=ca_result.get("capital_allocation_delta"),
        piotroski_score=pio.get("score"),
        piotroski_of=pio.get("of"),
    )

    elapsed = time.time() - t0
    print(json.dumps(result, indent=2, default=str))
    print(f"\n--- computed in {elapsed:.2f}s ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
