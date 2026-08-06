"""Regime-conditioning ESTIMABILITY meter — can a regime-conditional claim be made at all?

MEASUREMENT ONLY. Emits no signal, no score, no escalation. Display-tier by construction:
it reports the DENOMINATOR of a conditional claim, never the claim.

WHY THIS EXISTS
---------------
`data/signal_archive/track_record.parquet` carries six candidate regime axes stamped on each
signal (`regime_at_entry`, `quad_hard_label`, `vol_regime`, `fused_risk_label`,
`rate_pressure`, `risk_radar_state`). Five of the six were added by the W0-stageB vector
stamping and are therefore present on only the newest rows. As of the 2026-08 audit:

    regime_at_entry   100.0% coverage, 1962-2026, 3 states   <- estimable
    quad_hard_label     0.4% coverage, 2026-07 only, 2 states
    vol_regime          0.4% coverage, 2026-07 only, 1 STATE
    rate_pressure       0.4% coverage, 2026-07 only, 1 STATE
    fused_risk_label    0.4% coverage, 2026-07 only, 4 states
    risk_radar_state    0.4% coverage, 2026-07 only, 2 states

An axis observed in ONE state cannot support a conditional statement: E[outcome | regime]
is undefined off the observed cell, and a table built on it reads as a comparison while
being a constant. This is the trap the meter exists to make visible — a future study can
otherwise compute a confident-looking 6x4 reliability grid from 235 rows in a single month
and nothing in the stack would object.

THE HONEST UNIT IS MONTHS, NOT ROWS. A board ledger with 2,282 rows across 18 trading days
carries ~18 independent observations, not 2,282: same-day rows share the same market. Every
count this module reports is a DISTINCT-MONTH count alongside the raw row count, and the
gate binds on months.

GATE THRESHOLDS (frozen; changing them is a v2, not an edit)
------------------------------------------------------------
MIN_COVERAGE      = 0.20  an axis stamped on <20% of the record cannot describe the record
MIN_STATES        = 2     one observed state is a constant, not a condition
MIN_MONTHS_STATE  = 12    per-state independent months; mirrors the ">=10 contributing
                          months" floor pre-registered for H1 in
                          research/factor_intelligence/PREREGISTRATION.md, rounded up to a
                          calendar year so a verdict cannot rest on one season

VERDICTS
--------
    "estimable"              all three gates pass
    "insufficient_coverage"  axis stamped on too little of the record
    "single_state"           no contrast — the axis is a constant on this sample
    "insufficient_contrast"  >=2 states but some state is too thin to compare

Consumers must treat anything other than "estimable" as a hard NO on regime-conditional
claims for that axis. The meter never returns a reliability number and never ranks axes by
outcome — it reports only what the sample can support.

Reference: reports/regime-reliability-phase0.md (the measured null this meter generalizes).
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

# --- frozen gate constants (see module docstring) ---------------------------------
MIN_COVERAGE = 0.20
MIN_STATES = 2
MIN_MONTHS_STATE = 12

#: Regime axes stamped on the signal track record, in stamping-generation order.
CANDIDATE_AXES = (
    "regime_at_entry",
    "quad_hard_label",
    "vol_regime",
    "fused_risk_label",
    "rate_pressure",
    "risk_radar_state",
)

#: Values that are present-but-meaningless as a regime state.
_NULL_TOKENS = {"", "none", "nan", "null", "unknown", "na", "n/a"}


def _clean_states(s: pd.Series) -> pd.Series:
    """Drop nulls and placeholder tokens. An 'unknown' row is an unstamped row wearing a
    label — counting it as a state would manufacture contrast that does not exist."""
    v = s.astype("string").str.strip()
    return v[v.notna() & ~v.str.lower().isin(_NULL_TOKENS)]


def assess_axis(df: pd.DataFrame, axis: str, date_col: str = "date") -> dict:
    """Estimability of ONE regime axis on ``df``. Never raises: a missing/unusable column
    returns a verdict, not an exception."""
    n_rows = int(len(df))
    base = {
        "axis": axis, "n_rows_total": n_rows, "n_rows_stamped": 0, "coverage": 0.0,
        "n_states": 0, "states": {}, "months_total": 0, "min_state_months": 0,
        "verdict": "insufficient_coverage", "estimable": False, "reason": "",
    }
    if axis not in df.columns:
        base["reason"] = f"column '{axis}' absent from the record"
        return base
    if date_col not in df.columns:
        base["reason"] = f"date column '{date_col}' absent — months are not countable"
        return base
    if n_rows == 0:
        base["reason"] = "empty record"
        return base

    states = _clean_states(df[axis])
    stamped = df.loc[states.index].copy()
    stamped["_state"] = states
    dt = pd.to_datetime(stamped[date_col], errors="coerce")
    stamped = stamped[dt.notna()]
    if stamped.empty:
        base["reason"] = "no rows carry both a state and a parseable date"
        return base
    stamped["_month"] = pd.to_datetime(stamped[date_col]).dt.to_period("M").astype(str)

    per_state = (stamped.groupby("_state")
                 .agg(rows=("_month", "size"), months=("_month", "nunique")))
    # An axis is only as good as its THINNEST state — a comparison needs both sides.
    detail = {str(k): {"rows": int(r.rows), "months": int(r.months)}
              for k, r in per_state.iterrows()}

    out = dict(base)
    out.update({
        "n_rows_stamped": int(len(stamped)),
        "coverage": round(len(stamped) / n_rows, 4),
        "n_states": int(len(per_state)),
        "states": detail,
        "months_total": int(stamped["_month"].nunique()),
        "min_state_months": int(per_state["months"].min()),
        "span": [str(pd.to_datetime(stamped[date_col]).min().date()),
                 str(pd.to_datetime(stamped[date_col]).max().date())],
    })

    if out["coverage"] < MIN_COVERAGE:
        out["verdict"] = "insufficient_coverage"
        out["reason"] = (f"stamped on {100 * out['coverage']:.1f}% of rows "
                         f"(floor {100 * MIN_COVERAGE:.0f}%)")
    elif out["n_states"] < MIN_STATES:
        only = next(iter(detail), "?")
        out["verdict"] = "single_state"
        out["reason"] = (f"only one state observed ('{only}') — a constant, not a "
                         f"condition; E[outcome | regime] is undefined elsewhere")
    elif out["min_state_months"] < MIN_MONTHS_STATE:
        thin = min(detail, key=lambda k: detail[k]["months"])
        out["verdict"] = "insufficient_contrast"
        out["reason"] = (f"thinnest state '{thin}' spans {detail[thin]['months']} distinct "
                         f"months (floor {MIN_MONTHS_STATE})")
    else:
        out["verdict"] = "estimable"
        out["estimable"] = True
        out["reason"] = (f"{out['n_states']} states, thinnest spans "
                         f"{out['min_state_months']} months")
    return out


def assess(df: pd.DataFrame, axes: tuple[str, ...] = CANDIDATE_AXES,
           date_col: str = "date") -> dict:
    """Estimability report across every candidate regime axis.

    Returns ``{"axes": {...}, "estimable_axes": [...], "any_estimable": bool, ...}``.
    Degrades to an all-unavailable report rather than raising."""
    try:
        per = {a: assess_axis(df, a, date_col=date_col) for a in axes}
    except Exception:  # noqa: BLE001 — a meter must never break its caller
        log.exception("regime conditioning assessment failed")
        return {"axes": {}, "estimable_axes": [], "any_estimable": False,
                "n_rows": int(len(df)) if df is not None else 0,
                "status": "unavailable",
                "note": "assessment raised; treat every axis as NOT estimable"}

    ok = [a for a, r in per.items() if r["estimable"]]
    return {
        "axes": per,
        "estimable_axes": ok,
        "any_estimable": bool(ok),
        "n_rows": int(len(df)),
        "status": "ok",
        "gates": {"min_coverage": MIN_COVERAGE, "min_states": MIN_STATES,
                  "min_months_per_state": MIN_MONTHS_STATE},
        "note": ("months, not rows, are the independent unit; an axis that is not "
                 "'estimable' cannot carry a regime-conditional claim"),
    }


def format_report(report: dict) -> str:
    """Compact human-readable rendering for reports/ and CLI output."""
    if report.get("status") != "ok":
        return f"regime conditioning: UNAVAILABLE — {report.get('note', '')}"
    lines = [f"regime-conditioning estimability  (n_rows={report['n_rows']}, "
             f"gates: coverage>={MIN_COVERAGE:.0%}, states>={MIN_STATES}, "
             f"months/state>={MIN_MONTHS_STATE})", ""]
    for axis, r in report["axes"].items():
        mark = "PASS" if r["estimable"] else "----"
        span = f" {r['span'][0]}..{r['span'][1]}" if r.get("span") else ""
        lines.append(f"  [{mark}] {axis:18s} cov={100 * r['coverage']:5.1f}%  "
                     f"states={r['n_states']}  min_state_months={r['min_state_months']:3d}"
                     f"{span}")
        lines.append(f"         {r['verdict']}: {r['reason']}")
    lines.append("")
    lines.append(f"  estimable axes: {report['estimable_axes'] or 'NONE'}")
    return "\n".join(lines)
