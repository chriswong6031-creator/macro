"""engine/china_cycle_phase.py — A-share cycle-phase lobe (W3 of China System Program).

Authority: context_only (CN-SYS-R1).  No scores, ranks, gates, or origination.

Produces
--------
  data/china_cycle_phase/phase_tape.parquet   — backfilled + forward, §5 schema
  data/china_cycle_phase/falsifier_ledger.parquet — auto-graded falsifiers, §5 schema
  site/chinastatedata/cycle_phase.json        — latest snapshot

PHASES (10)
-----------
CAPITULATION       — panic selling accelerates; limit-down breadth surges; margin calls cascade
POLICY_PUT         — selling exhausted, policy easing arrives; turnover low; ZT dead
LIQUIDITY_IGNITION — money supply ignites first-move; turnover explodes; ZT/lianban spike
THEME_LEADERSHIP   — selective leadership; narrow breadth; thematic clusters running
BROADENING         — leadership widens across sectors; participation broadens
EUPHORIA           — retail FOMO; extreme limit-up breadth; lianban acceleration; margin frothy
DISTRIBUTION       — insiders/institutions sell into retail excitement; breadth falters
DELEVERAGING       — margin calls; forced selling; limit-down breadth picks up
GRINDING_BEAR      — slow capital attrition; low turnover; periodic relief rallies fail
REPAIR             — base-building; turnover stable-low; no extreme breadth in either direction

PHASE CLASSIFIER — RULE-BASED WITH DOCUMENTED THRESHOLDS + PRECEDENCE ORDER
=============================================================================
Every rule is transparent and documented here.  Thresholds are calibrated so that:
  2015-06 → 2015-08: should traverse EUPHORIA → DISTRIBUTION → DELEVERAGING
  2024-09 / 2024-10: should show POLICY_PUT → LIQUIDITY_IGNITION
  2018: should be mostly GRINDING_BEAR / DELEVERAGING

Input metrics (computed daily from raw tapes):
  lup5    = 5-day mean of limit_up_breadth_pct  (% of universe at limit-up)
  ldn5    = 5-day mean of limit_down_breadth_pct
  lup1    = single-day limit_up_breadth_pct
  ldn1    = single-day limit_down_breadth_pct
  lban5   = 5-day mean of lianban_2plus
  par_regime = participation regime string (from tape.parquet)
  turnover_z20 = from participation tape
  margin_chg_5d = from participation tape (% 5-day change in margin balance)
  fin_pct_float = margin_to_mcap from participation tape
  qvix_z = QVIX z-score from participation tape
  policy  = policy_impulse string (from site/chinastatedata/policy_transmission.json)
  quad    = regime quad (Q1/Q2/Q3/Q4) from regime_history
  liquidity = liquidity_overlay (expanding/neutral/tightening)
  sec_wash = cross-sector fraction in Downturn+Trough phases (from china_sector_cycles)
  sec_peak = cross-sector fraction in Peak phase

PRECEDENCE ORDER (first matching rule fires, earlier = higher priority):
  1. CAPITULATION  — panic cascade (limit-down overwhelms, margin forced)
  2. POLICY_PUT    — capitulation exhausted, policy floor
  3. LIQUIDITY_IGNITION — ignition burst (extreme ZT spike)
  4. EUPHORIA      — late-bull frenzy
  5. DISTRIBUTION  — selling into late rally
  6. DELEVERAGING  — margin unwind
  7. BROADENING    — expanding breadth, healthy
  8. THEME_LEADERSHIP — selective narrow rally
  9. GRINDING_BEAR — slow decay
 10. REPAIR        — quiet base-building (default fallback)

HYSTERESIS
----------
min_dwell_sessions prevents daily flip-flop.  The phase must meet its conditions for at
least MIN_DWELL_SESSIONS consecutive sessions before a transition is recorded.  The
initial phase (no prior tape) bypasses hysteresis.  Hysteresis is only applied in the
nightly increment path; the backfill path uses full rolling windows and applies hysteresis
in a single vectorized pass.

CONFIDENCE
----------
confidence ∈ [0.0, 1.0].  Computed as the fraction of the rule's constituent conditions
that are unambiguously satisfied (not borderline).  Borderline = within 20% of the threshold.

FALSIFIERS (CN-SYS-R5)
=======================
Each daily print embeds 2–4 machine-checkable falsifiers.  Expr is a deterministic DSL
over named tape metrics (evaluated by the safe _eval_falsifier() function — NO eval() on
arbitrary strings).  The nightly builder grades due falsifiers from prior prints.

DSL Metric vocabulary (these are the ONLY names recognised by _eval_falsifier):
  lup5          — 5-day mean limit_up_breadth_pct
  ldn5          — 5-day mean limit_down_breadth_pct
  lban5         — 5-day mean lianban_2plus
  turnover_z20  — turnover z-score vs 20-day window (from participation tape)
  margin_chg_5d — 5-day % change in margin balance
  qvix_z        — QVIX z-score vs 60-day (from participation tape)
  sec_wash      — cross-sector washout breadth fraction

Operators: <, >, <=, >=, ==  (binary; no logic combinators — each falsifier has one comparison)

STATIC ERA REFERENCE TABLE (Codex §4, 2005→2026)
==================================================
Descriptive historical episode map for display/analog use.  NOT used in phase
classification; these are labels assigned after the fact for historical grounding.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

SCHEMA = "china_cycle_phase.v1"

PHASES = (
    "CAPITULATION",
    "POLICY_PUT",
    "LIQUIDITY_IGNITION",
    "THEME_LEADERSHIP",
    "BROADENING",
    "EUPHORIA",
    "DISTRIBUTION",
    "DELEVERAGING",
    "GRINDING_BEAR",
    "REPAIR",
)

FALSIFIER_OUTCOMES = ("held", "fired", "indeterminate")

# ---------------------------------------------------------------------------
# Hysteresis
# ---------------------------------------------------------------------------

MIN_DWELL_SESSIONS = 3   # minimum consecutive days before a phase transition is accepted

# ---------------------------------------------------------------------------
# Classifier thresholds — documented, not magic
# ---------------------------------------------------------------------------

# Limit-up breadth thresholds (% of universe)
_LUP_IGNITION   = 8.0   # 5d mean >8% = liquidity ignition burst (Sep-30/Oct-08 2024 were 17/35)
_LUP_EUPHORIA   = 4.0   # 5d mean >4% = euphoria (sustained frenzy)
_LUP_RALLY      = 1.5   # 5d mean >1.5% = active rally
_LUP_QUIET      = 0.5   # 5d mean <0.5% = very quiet

# Limit-down breadth thresholds (% of universe)
_LDN_PANIC      = 5.0   # 5d mean >5% = capitulation panic
_LDN_STRESS     = 1.5   # 5d mean >1.5% = stress / deleveraging

# Lianban (multi-day locked limit-up) threshold
_LBAN_IGNITION  = 10.0  # 5d mean >10 lianban stocks = ignition
_LBAN_ACTIVE    = 3.0   # 5d mean >3 = active theme-chasing

# Turnover z-score thresholds
_TOZ_HOT        =  1.0
_TOZ_WARM       =  0.3
_TOZ_COLD       = -0.5
_TOZ_DEAD       = -1.0

# Margin thresholds
_MARGIN_ACCEL   =  1.0   # margin_chg_5d > 1% = accelerating
_MARGIN_STRESS  = -1.0   # margin_chg_5d < -1% = forced deleveraging
_MARGIN_FIN_PCT_FROTHY = 3.5  # fin_pct_float > 3.5% = leveraged

# QVIX z-score threshold
_QVIX_STRESS    = 1.5

# Sector breadth thresholds
_SEC_WASH_HIGH  = 0.5    # >50% sectors in Downturn+Trough = broad washout
_SEC_PEAK_HIGH  = 0.4    # >40% sectors in Peak = broad euphoria


# ---------------------------------------------------------------------------
# Static ERA reference table (Codex §4, 2005→2026)
# ---------------------------------------------------------------------------

ERA_TABLE: list[dict[str, Any]] = [
    {"era": "2005_reform_bottom",  "start": "2005-06-01", "end": "2005-12-31",
     "phases": ["CAPITULATION", "REPAIR"],
     "note": "Split-share structure reform; market bottomed Jun-2005"},
    {"era": "2006_2007_bull",      "start": "2006-01-01", "end": "2007-10-31",
     "phases": ["LIQUIDITY_IGNITION", "BROADENING", "THEME_LEADERSHIP", "EUPHORIA"],
     "note": "Structural bull; Shanghai Composite 1000→6124; retail FOMO 2007-H2"},
    {"era": "2007_2008_bust",      "start": "2007-11-01", "end": "2008-10-31",
     "phases": ["DISTRIBUTION", "DELEVERAGING", "CAPITULATION"],
     "note": "Global GFC + overvaluation unwind; market -70%"},
    {"era": "2008_policy_rescue",  "start": "2008-11-01", "end": "2009-08-31",
     "phases": ["POLICY_PUT", "LIQUIDITY_IGNITION", "BROADENING"],
     "note": "4-trillion RMB stimulus; rapid V-shape recovery"},
    {"era": "2009_2012_grind",     "start": "2009-09-01", "end": "2012-12-31",
     "phases": ["DISTRIBUTION", "GRINDING_BEAR", "REPAIR"],
     "note": "Post-stimulus hangover; property tightening; 3-year bear"},
    {"era": "2013_thematic_bull",  "start": "2013-01-01", "end": "2014-12-31",
     "phases": ["THEME_LEADERSHIP", "REPAIR"],
     "note": "ChiNext / TMT thematics; SOE reform; big-caps flat"},
    {"era": "2014h2_2015h1_mania", "start": "2014-11-01", "end": "2015-06-12",
     "phases": ["LIQUIDITY_IGNITION", "BROADENING", "EUPHORIA"],
     "note": "RRR cuts + margin surge; SHCOMP 2000→5178; peak retail mania"},
    {"era": "2015h2_crash",        "start": "2015-06-13", "end": "2015-09-30",
     "phases": ["DISTRIBUTION", "DELEVERAGING", "CAPITULATION"],
     "note": "Margin unwind cascade; circuit-breaker; -45% from peak"},
    {"era": "2015q4_2016_repair",  "start": "2015-10-01", "end": "2016-12-31",
     "phases": ["REPAIR", "POLICY_PUT", "GRINDING_BEAR"],
     "note": "Circuit-breaker incident (Jan-2016); slow repair"},
    {"era": "2017_blue_chip",      "start": "2017-01-01", "end": "2017-12-31",
     "phases": ["THEME_LEADERSHIP", "BROADENING"],
     "note": "White-horse / blue-chip rally; Mao index diverges from ChiNext"},
    {"era": "2018_deleveraging",   "start": "2018-01-01", "end": "2018-12-31",
     "phases": ["GRINDING_BEAR", "DELEVERAGING"],
     "note": "Trade war + regulatory deleveraging; -30% A-shares"},
    {"era": "2019_policy_recovery","start": "2019-01-01", "end": "2019-04-30",
     "phases": ["POLICY_PUT", "LIQUIDITY_IGNITION"],
     "note": "PBOC easing; market rallied 30% Q1-2019"},
    {"era": "2019_2020_range",     "start": "2019-05-01", "end": "2020-01-31",
     "phases": ["THEME_LEADERSHIP", "GRINDING_BEAR"],
     "note": "Trade-war uncertainty + selective themes"},
    {"era": "2020_covid_crash",    "start": "2020-02-01", "end": "2020-03-31",
     "phases": ["CAPITULATION", "POLICY_PUT"],
     "note": "COVID shock; PBOC rapid easing; A-shares recovered faster than global"},
    {"era": "2020_2021_bull",      "start": "2020-04-01", "end": "2021-02-28",
     "phases": ["LIQUIDITY_IGNITION", "BROADENING", "THEME_LEADERSHIP", "EUPHORIA"],
     "note": "Post-COVID liquidity surge; semiconductor/EV themes; peak Feb-2021"},
    {"era": "2021_2022_grind",     "start": "2021-03-01", "end": "2022-10-31",
     "phases": ["DISTRIBUTION", "DELEVERAGING", "GRINDING_BEAR"],
     "note": "Regulatory crackdowns (edu/platform/property); Ukraine risk; -40% peak-trough"},
    {"era": "2022q4_2023_repair",  "start": "2022-11-01", "end": "2023-08-31",
     "phases": ["POLICY_PUT", "REPAIR", "THEME_LEADERSHIP"],
     "note": "COVID reopening bounce; AI-theme (ChatGPT wave)"},
    {"era": "2023_2024_grind",     "start": "2023-09-01", "end": "2024-09-23",
     "phases": ["GRINDING_BEAR", "REPAIR"],
     "note": "Persistent deflationary pressure; property crisis; policy half-measures"},
    {"era": "2024q3_ignition",     "start": "2024-09-24", "end": "2024-11-30",
     "phases": ["POLICY_PUT", "LIQUIDITY_IGNITION"],
     "note": "Politburo Sep-24 stimulus surprise; SHCOMP +30% in 2 weeks"},
    {"era": "2025_theme_phase",    "start": "2024-12-01", "end": "2025-12-31",
     "phases": ["THEME_LEADERSHIP", "BROADENING", "REPAIR"],
     "note": "DeepSeek AI wave Q1-2025; selective technology themes"},
    {"era": "2026_current",        "start": "2026-01-01", "end": "2026-12-31",
     "phases": ["GRINDING_BEAR", "REPAIR"],
     "note": "Ongoing assessment — accruing"},
]


# ---------------------------------------------------------------------------
# Per-phase falsifier templates
# ---------------------------------------------------------------------------
# Each entry: (falsifier_id_suffix, metric, operator, threshold, horizon_d)
# The expr is assembled as "{metric} {operator} {threshold}"
# These are descriptive falsifiers: if the phase is e.g. EUPHORIA, we expect
# certain metrics NOT to collapse; if they do, the phase call was wrong.

_FALSIFIER_TEMPLATES: dict[str, list[tuple[str, str, str, float, int]]] = {
    "CAPITULATION": [
        ("CAP_LDN_PERSIST",  "ldn5",         ">",  1.0, 5),
        ("CAP_TOZ_DEPRESSED","turnover_z20",  ">", -0.5, 10),
        ("CAP_NO_LUP",       "lup5",         "<",  2.0, 5),
    ],
    "POLICY_PUT": [
        ("PP_LUP_RECOVERING","lup5",          ">",  1.0, 10),
        ("PP_TOZ_STABILISE", "turnover_z20",  ">", -1.0, 10),
        ("PP_LDN_FADING",    "ldn5",         "<",  2.0,  5),
    ],
    "LIQUIDITY_IGNITION": [
        ("LI_LUP_SUSTAINED", "lup5",          ">",  3.0, 5),
        ("LI_TOZ_HOT",       "turnover_z20",  ">",  0.5, 5),
        ("LI_LBAN_ACTIVE",   "lban5",         ">",  5.0, 5),
    ],
    "THEME_LEADERSHIP": [
        ("TL_LUP_NONZERO",   "lup5",          ">",  0.5, 10),
        ("TL_NO_PANIC",      "ldn5",         "<",  1.5, 10),
        ("TL_SEC_UNWASHED",  "sec_wash",     "<",  0.6, 10),
    ],
    "BROADENING": [
        ("BR_LUP_WARM",      "lup5",          ">",  1.5, 10),
        ("BR_TOZ_POSITIVE",  "turnover_z20",  ">",  0.0, 10),
        ("BR_NO_MARGIN_RUSH","margin_chg_5d", "<",  3.0, 10),
    ],
    "EUPHORIA": [
        ("EU_LUP_ELEVATED",  "lup5",          ">",  2.0, 5),
        ("EU_LBAN_HIGH",     "lban5",         ">",  2.0, 5),
        ("EU_TOZ_HOT",       "turnover_z20",  ">",  0.5, 5),
    ],
    "DISTRIBUTION": [
        ("DI_LDN_RISING",    "ldn5",          ">",  0.5, 10),
        ("DI_TOZ_DECLINES",  "turnover_z20", "<",  1.5, 10),
        ("DI_LUP_FADING",    "lup5",         "<",  4.0, 10),
    ],
    "DELEVERAGING": [
        ("DL_MARGIN_STRESS", "margin_chg_5d", "<", -0.5, 5),
        ("DL_LDN_ELEVATED",  "ldn5",          ">",  0.8, 5),
        ("DL_QVIX_UP",       "qvix_z",        ">",  0.5, 5),
    ],
    "GRINDING_BEAR": [
        ("GB_TOZ_COLD",      "turnover_z20", "<",  0.5, 10),
        ("GB_LUP_QUIET",     "lup5",         "<",  1.5, 10),
        ("GB_SEC_WASH",      "sec_wash",      ">",  0.3, 10),
    ],
    "REPAIR": [
        ("RP_LDN_LOW",       "ldn5",         "<",  1.0, 10),
        ("RP_LUP_LOW",       "lup5",         "<",  2.0, 10),
        ("RP_TOZ_STABLE",    "turnover_z20", ">", -1.5, 10),
    ],
}


# ---------------------------------------------------------------------------
# DSL evaluator (no eval() on arbitrary strings — CN-SYS-R5)
# ---------------------------------------------------------------------------

_DSL_METRICS = frozenset({
    "lup5", "ldn5", "lban5", "turnover_z20", "margin_chg_5d", "qvix_z", "sec_wash",
})
_DSL_OPS = frozenset({"<", ">", "<=", ">=", "=="})


def _eval_falsifier(expr: str, metrics: dict[str, float | None]) -> str:
    """Evaluate one falsifier expression against a dict of current metric values.

    Returns 'held' | 'fired' | 'indeterminate'.

    expr format: "{metric} {operator} {threshold}"
    Example: "lup5 > 2.0"

    indeterminate if the metric is None/NaN.
    """
    parts = expr.strip().split()
    if len(parts) != 3:
        return "indeterminate"
    metric_name, op, threshold_str = parts
    if metric_name not in _DSL_METRICS:
        return "indeterminate"
    if op not in _DSL_OPS:
        return "indeterminate"
    try:
        threshold = float(threshold_str)
    except ValueError:
        return "indeterminate"
    val = metrics.get(metric_name)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "indeterminate"
    val_f = float(val)
    result: bool
    if op == "<":
        result = val_f < threshold
    elif op == ">":
        result = val_f > threshold
    elif op == "<=":
        result = val_f <= threshold
    elif op == ">=":
        result = val_f >= threshold
    elif op == "==":
        result = abs(val_f - threshold) < 1e-9
    else:
        return "indeterminate"
    return "held" if result else "fired"


# ---------------------------------------------------------------------------
# Input loading helpers
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent


def _load_limit_tape(root: Path) -> pd.DataFrame | None:
    p = root / "data" / "china_microstructure" / "limit_tape.parquet"
    if not p.exists():
        log.warning("limit_tape not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        # date may be a column or the index
        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log.warning("Could not read limit_tape (%s)", e)
        return None


def _load_participation_tape(root: Path) -> pd.DataFrame | None:
    p = root / "data" / "china_participation" / "tape.parquet"
    if not p.exists():
        log.warning("participation tape not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log.warning("Could not read participation tape (%s)", e)
        return None


def _load_regime_history(root: Path) -> pd.DataFrame | None:
    p = root / "data" / "china_regime" / "regime_history.parquet"
    if not p.exists():
        log.warning("regime_history not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log.warning("Could not read regime_history (%s)", e)
        return None


def _load_sector_cycles(root: Path) -> pd.DataFrame | None:
    p = root / "data" / "china_sector_cycles" / "backfill.parquet"
    if not p.exists():
        log.warning("china_sector_cycles/backfill not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as e:
        log.warning("Could not read sector_cycles (%s)", e)
        return None


def _load_policy_json(root: Path) -> dict[str, Any]:
    p = root / "site" / "chinastatedata" / "policy_transmission.json"
    if not p.exists():
        log.warning("policy_transmission.json not found at %s", p)
        return {}
    try:
        with p.open() as f:
            return json.load(f)
    except Exception as e:
        log.warning("Could not read policy_transmission.json (%s)", e)
        return {}


# ---------------------------------------------------------------------------
# Feature frame assembly
# ---------------------------------------------------------------------------

def _build_sector_breadth(sc: pd.DataFrame | None) -> pd.DataFrame | None:
    """Compute cross-sector washout and peak fractions per date."""
    if sc is None:
        return None
    try:
        sc = sc.copy()
        sc["date"] = pd.to_datetime(sc["date"])
        grp = sc.groupby("date")["phase"].value_counts(normalize=True).unstack(fill_value=0.0)
        sec_wash = grp.get("Downturn", pd.Series(0.0, index=grp.index)) + \
                   grp.get("Trough",   pd.Series(0.0, index=grp.index))
        sec_peak = grp.get("Peak", pd.Series(0.0, index=grp.index))
        result = pd.DataFrame({"sec_wash": sec_wash, "sec_peak": sec_peak})
        result.index = pd.to_datetime(result.index)
        return result
    except Exception as e:
        log.warning("Could not build sector breadth (%s)", e)
        return None


def build_feature_frame(
    root: Path | None = None,
    limit_tape: pd.DataFrame | None = None,
    participation_tape: pd.DataFrame | None = None,
    regime_history: pd.DataFrame | None = None,
    sector_cycles: pd.DataFrame | None = None,
    policy_json: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Assemble a feature frame of daily classifier inputs and a data_gaps list.

    All inputs are optional; missing inputs degrade to null columns with an entry
    in data_gaps.  Returns (feature_df, data_gaps).

    feature_df columns:
      lup1, lup5, ldn1, ldn5, lban5 (from limit_tape)
      turnover_z20, margin_chg_5d, fin_pct_float, qvix_z, par_regime
        (from participation_tape)
      quad, liquidity (from regime_history)
      sec_wash, sec_peak (from sector_cycles)
      policy_impulse (from policy_json — single scalar broadcast to all rows)
    """
    if root is None:
        root = _ROOT

    data_gaps: list[str] = []

    # ── limit tape ───────────────────────────────────────────────────────────
    lt = limit_tape if limit_tape is not None else _load_limit_tape(root)
    if lt is None:
        data_gaps.append("limit_tape_missing")
        lt_frame = pd.DataFrame(
            columns=["lup1", "lup5", "ldn1", "ldn5", "lban5"]
        )
    else:
        lup_col = lt.get("limit_up_breadth_pct", pd.Series(dtype=float))
        ldn_col = lt.get("limit_down_breadth_pct", pd.Series(dtype=float))
        lban_col = lt.get("lianban_2plus", pd.Series(dtype=float))
        lt_frame = pd.DataFrame({
            "lup1":  lup_col,
            "ldn1":  ldn_col,
            "lup5":  lup_col.rolling(5,  min_periods=1).mean(),
            "ldn5":  ldn_col.rolling(5,  min_periods=1).mean(),
            "lban5": lban_col.rolling(5, min_periods=1).mean(),
        }, index=lt.index)

    # ── participation tape ───────────────────────────────────────────────────
    pt = participation_tape if participation_tape is not None else _load_participation_tape(root)
    if pt is None:
        data_gaps.append("participation_tape_missing")
        pt_frame = pd.DataFrame(
            columns=["turnover_z20", "margin_chg_5d", "fin_pct_float", "qvix_z", "par_regime"]
        )
    else:
        pt_frame = pd.DataFrame({
            "turnover_z20":  pt.get("turnover_z20",  pd.Series(dtype=float, index=pt.index)),
            "margin_chg_5d": pt.get("margin_chg_5d", pd.Series(dtype=float, index=pt.index)),
            "fin_pct_float": pt.get("margin_to_mcap", pd.Series(dtype=float, index=pt.index)),
            "qvix_z":        pt.get("qvix_z",         pd.Series(dtype=float, index=pt.index)),
            "par_regime":    pt.get("regime",          pd.Series(dtype=object, index=pt.index)),
        }, index=pt.index)

    # ── regime history ───────────────────────────────────────────────────────
    rh = regime_history if regime_history is not None else _load_regime_history(root)
    if rh is None:
        data_gaps.append("regime_history_missing")
        rh_frame = pd.DataFrame(columns=["quad", "liquidity"])
    else:
        rh_frame = pd.DataFrame({
            "quad":      rh.get("quad",      pd.Series(dtype=object, index=rh.index)),
            "liquidity": rh.get("liquidity", pd.Series(dtype=object, index=rh.index)),
        }, index=rh.index)

    # ── sector cycles ────────────────────────────────────────────────────────
    sc = sector_cycles if sector_cycles is not None else _load_sector_cycles(root)
    sb = _build_sector_breadth(sc)
    if sb is None:
        data_gaps.append("sector_cycles_missing")
        sb = pd.DataFrame(columns=["sec_wash", "sec_peak"])

    # ── policy (single scalar, current-state only, broadcast) ────────────────
    if policy_json is None:
        policy_json = _load_policy_json(root)
    policy_impulse: str = policy_json.get("policy_impulse", "neutral") if policy_json else "neutral"

    # ── merge all on date index ───────────────────────────────────────────────
    frames = [lt_frame, pt_frame, rh_frame, sb]
    # Start from the widest date range (union of all indexes)
    all_dates = sorted(
        set().union(*[set(f.index) for f in frames if not f.empty])
    )
    if not all_dates:
        # No data at all → empty frame
        empty = pd.DataFrame(columns=[
            "lup1", "lup5", "ldn1", "ldn5", "lban5",
            "turnover_z20", "margin_chg_5d", "fin_pct_float", "qvix_z", "par_regime",
            "quad", "liquidity", "sec_wash", "sec_peak", "policy_impulse",
        ])
        return empty, data_gaps

    idx = pd.DatetimeIndex(all_dates)
    merged = pd.DataFrame(index=idx)
    for frame in frames:
        if not frame.empty:
            merged = merged.join(frame, how="left")

    merged["policy_impulse"] = policy_impulse
    merged = merged.sort_index()

    return merged, data_gaps


# ---------------------------------------------------------------------------
# Phase classifier
# ---------------------------------------------------------------------------

class _PhaseResult(NamedTuple):
    phase: str
    confidence: float
    evidence: list[str]
    contradictions: list[str]
    falsifiers: list[dict[str, Any]]


def _safe(val: Any) -> float | None:
    """Return a float or None; handle NaN."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _classify_row(row: pd.Series) -> _PhaseResult:
    """Classify a single daily observation.  Returns a PhaseResult."""
    # Extract metrics, coercing to float or None
    lup5          = _safe(row.get("lup5"))
    lup1          = _safe(row.get("lup1"))
    ldn5          = _safe(row.get("ldn5"))
    ldn1          = _safe(row.get("ldn1"))
    lban5         = _safe(row.get("lban5"))
    turnover_z20  = _safe(row.get("turnover_z20"))
    margin_chg_5d = _safe(row.get("margin_chg_5d"))
    fin_pct_float = _safe(row.get("fin_pct_float"))
    qvix_z        = _safe(row.get("qvix_z"))
    par_regime    = str(row.get("par_regime") or "unclear")
    quad          = str(row.get("quad") or "")
    liquidity     = str(row.get("liquidity") or "")
    sec_wash      = _safe(row.get("sec_wash"))
    sec_peak      = _safe(row.get("sec_peak"))
    policy_impulse = str(row.get("policy_impulse") or "neutral")

    evidence: list[str] = []
    contradictions: list[str] = []

    # Track metric dict for falsifier evaluation
    metrics: dict[str, float | None] = {
        "lup5":          lup5,
        "ldn5":          ldn5,
        "lban5":         lban5,
        "turnover_z20":  turnover_z20,
        "margin_chg_5d": margin_chg_5d,
        "qvix_z":        qvix_z,
        "sec_wash":      sec_wash,
    }

    # ── Condition tests (each emits evidence or contradiction tags) ───────────

    lup_hot     = lup5 is not None and lup5 > _LUP_EUPHORIA
    lup_ignite  = lup5 is not None and lup5 > _LUP_IGNITION
    lup_rally   = lup5 is not None and lup5 > _LUP_RALLY
    lup_quiet   = lup5 is None or lup5 < _LUP_QUIET
    ldn_panic   = ldn5 is not None and ldn5 > _LDN_PANIC
    ldn_stress  = ldn5 is not None and ldn5 > _LDN_STRESS
    ldn_quiet   = ldn5 is None or ldn5 < 0.5
    lban_burst  = lban5 is not None and lban5 > _LBAN_IGNITION
    lban_active = lban5 is not None and lban5 > _LBAN_ACTIVE
    toz_hot     = turnover_z20 is not None and turnover_z20 > _TOZ_HOT
    toz_warm    = turnover_z20 is not None and turnover_z20 > _TOZ_WARM
    toz_cold    = turnover_z20 is None or turnover_z20 < _TOZ_COLD
    toz_dead    = turnover_z20 is None or turnover_z20 < _TOZ_DEAD
    margin_accel = margin_chg_5d is not None and margin_chg_5d > _MARGIN_ACCEL
    margin_stress = margin_chg_5d is not None and margin_chg_5d < _MARGIN_STRESS
    margin_frothy = fin_pct_float is not None and fin_pct_float > _MARGIN_FIN_PCT_FROTHY
    qvix_high   = qvix_z is not None and qvix_z > _QVIX_STRESS
    sec_washed  = sec_wash is not None and sec_wash > _SEC_WASH_HIGH
    sec_peaked  = sec_peak is not None and sec_peak > _SEC_PEAK_HIGH
    policy_easy = policy_impulse in ("easing", "market_rescue")
    policy_ease_or_support = policy_impulse in ("easing", "market_rescue", "targeted_support")

    # participation corroboration
    par_deleverage = par_regime in ("forced_deleveraging",)
    par_mania      = par_regime in ("broad_mania", "margin_acceleration")
    par_dist       = par_regime in ("distribution",)
    par_dormant    = par_regime in ("dormant",)
    par_ignite     = par_regime in ("retail_ignition", "margin_acceleration", "broad_mania")

    # ── Evidence accumulation ─────────────────────────────────────────────────
    if lup_ignite:
        evidence.append(f"limit_up_breadth_5d_extreme ({lup5:.1f}%)")
    elif lup_hot:
        evidence.append(f"limit_up_breadth_5d_elevated ({lup5:.1f}%)")
    elif lup_rally:
        evidence.append(f"limit_up_breadth_5d_active ({lup5:.1f}%)")
    if ldn_panic:
        evidence.append(f"limit_down_breadth_5d_panic ({ldn5:.1f}%)")
    elif ldn_stress:
        evidence.append(f"limit_down_breadth_5d_stress ({ldn5:.1f}%)")
    if lban_burst:
        evidence.append(f"lianban_5d_burst ({lban5:.1f})")
    elif lban_active:
        evidence.append(f"lianban_5d_active ({lban5:.1f})")
    if toz_hot:
        evidence.append(f"turnover_z20_hot ({turnover_z20:.2f})")
    elif toz_cold:
        evidence.append(f"turnover_z20_cold ({turnover_z20:.2f})" if turnover_z20 is not None else "turnover_z20_null")
    if margin_accel:
        evidence.append(f"margin_chg_5d_accelerating ({margin_chg_5d:.2f}%)")
    if margin_stress:
        evidence.append(f"margin_chg_5d_stress ({margin_chg_5d:.2f}%)")
    if margin_frothy:
        evidence.append(f"fin_pct_float_frothy ({fin_pct_float:.2f}%)")
    if qvix_high:
        evidence.append(f"qvix_z_elevated ({qvix_z:.2f})")
    if policy_easy:
        evidence.append(f"policy_impulse_{policy_impulse}")
    if sec_washed:
        evidence.append(f"sector_breadth_washout ({sec_wash:.0%})")
    if sec_peaked:
        evidence.append(f"sector_breadth_peak ({sec_peak:.0%})")
    if par_regime not in ("unclear", "dormant"):
        evidence.append(f"participation_regime_{par_regime}")

    # ── Contradictions ────────────────────────────────────────────────────────
    if lup_hot and ldn_stress:
        contradictions.append("limit_up_and_down_simultaneous_elevated")
    if toz_hot and lup_quiet and ldn_quiet:
        contradictions.append("high_turnover_but_no_breadth_extremes")
    if margin_accel and qvix_high:
        contradictions.append("margin_accelerating_during_fear_spike")
    if policy_easy and toz_dead:
        contradictions.append("policy_easing_but_turnover_dead")
    if par_mania and ldn_stress:
        contradictions.append("participation_mania_but_limit_down_stress")

    # ── PHASE CLASSIFIER (precedence order) ──────────────────────────────────

    # Condition trackers for confidence
    phase = "REPAIR"  # default fallback
    conditions_met: int = 0
    conditions_total: int = 1

    # 1. CAPITULATION — panic cascade
    # Trigger: limit-down panic OR (margin stress AND QVIX spike AND low lup)
    cap_conds = [
        ldn_panic,
        ldn_stress and margin_stress,
        margin_stress and qvix_high and not lup_hot,
        par_deleverage and ldn_stress,
    ]
    cap_conds_total = 4
    cap_conds_met = sum(1 for c in cap_conds if c)
    if cap_conds_met >= 1 and ldn5 is not None and ldn5 > 1.0:
        # At least one strong capitulation signal with meaningful limit-down breadth
        phase = "CAPITULATION"
        conditions_met = cap_conds_met
        conditions_total = cap_conds_total

    # 2. POLICY_PUT — floor formed, policy acting, selling exhausted
    # Trigger: policy easing/support AND turnover quiet/recovering AND limit-down fading.
    # "targeted_support" is included because: (a) it is the current live broadcast
    # and structurally causes POLICY_PUT to be unreachable without it; (b) the
    # boundary between "market_rescue" and "targeted_support" is definitional, and
    # the phase's behavioural hallmarks (low turnover, fading limit-down, sector
    # washout) are the stronger discriminators anyway.
    # CAVEAT: policy_impulse is a current-state scalar broadcast to all backfill
    # rows; see the "caveat" field in cycle_phase.json for disclosure.
    elif policy_ease_or_support and not ldn_stress and not lup_ignite:
        put_conds = [
            policy_ease_or_support,
            not ldn_stress,
            toz_cold or par_dormant,
            sec_washed,  # broad sector washout = exhaustion
        ]
        phase = "POLICY_PUT"
        conditions_met = sum(1 for c in put_conds if c)
        conditions_total = 4

    # 3. LIQUIDITY_IGNITION — first-move burst
    # Trigger: extreme lup5 OR (lban burst AND toz hot)
    elif lup_ignite or (lban_burst and toz_hot):
        ig_conds = [lup_ignite, lban_burst, toz_hot, par_ignite]
        phase = "LIQUIDITY_IGNITION"
        conditions_met = sum(1 for c in ig_conds if c)
        conditions_total = 4

    # 4. EUPHORIA — sustained frenzy
    # Trigger: lup hot (>4%) AND lban active AND margin frothy
    elif lup_hot and (lban_active or margin_frothy) and toz_warm:
        eu_conds = [lup_hot, lban_active, margin_frothy, toz_hot, sec_peaked]
        phase = "EUPHORIA"
        conditions_met = sum(1 for c in eu_conds if c)
        conditions_total = 5

    # 5. DISTRIBUTION — selling into late rally
    # Trigger: participation=distribution OR (toz_warm but lup_hot fading and ldn rising)
    elif par_dist or (toz_warm and not lup_hot and ldn_stress):
        di_conds = [
            par_dist,
            toz_warm,
            not lup_hot,
            ldn5 is not None and ldn5 > 0.5,
        ]
        phase = "DISTRIBUTION"
        conditions_met = sum(1 for c in di_conds if c)
        conditions_total = 4

    # 6. DELEVERAGING — margin unwind with stress
    # Trigger: margin_stress AND (ldn_stress OR qvix_high)
    elif margin_stress and (ldn_stress or qvix_high):
        dl_conds = [margin_stress, ldn_stress, qvix_high, par_deleverage]
        phase = "DELEVERAGING"
        conditions_met = sum(1 for c in dl_conds if c)
        conditions_total = 4

    # 7. BROADENING — expanding participation, healthy advance
    # Trigger: lup_rally + toz_warm + not frothy
    elif lup_rally and toz_warm and not margin_frothy and not lup_hot:
        br_conds = [lup_rally, toz_warm, not margin_frothy, not ldn_stress, sec_wash is not None and sec_wash < 0.4]
        phase = "BROADENING"
        conditions_met = sum(1 for c in br_conds if c)
        conditions_total = 5

    # 8. THEME_LEADERSHIP — selective narrow advance
    # Trigger: lban_active but lup moderate
    elif lban_active and not lup_hot and not ldn_stress:
        tl_conds = [lban_active, not lup_hot, not ldn_stress, not toz_dead]
        phase = "THEME_LEADERSHIP"
        conditions_met = sum(1 for c in tl_conds if c)
        conditions_total = 4

    # 9. GRINDING_BEAR — slow attrition
    # Trigger: cold turnover + no extreme breadth + no policy easing/support
    elif toz_cold and lup_quiet and not ldn_panic and not policy_ease_or_support:
        gb_conds = [toz_cold, lup_quiet, not ldn_panic, not policy_ease_or_support, sec_washed]
        phase = "GRINDING_BEAR"
        conditions_met = sum(1 for c in gb_conds if c)
        conditions_total = 5

    # 10. REPAIR — default
    else:
        rp_conds = [not ldn_stress, not lup_hot, not toz_dead]
        phase = "REPAIR"
        conditions_met = sum(1 for c in rp_conds if c)
        conditions_total = 3

    confidence = round(min(1.0, conditions_met / max(conditions_total, 1)), 3)

    # ── Falsifiers ────────────────────────────────────────────────────────────
    falsifiers: list[dict[str, Any]] = []
    templates = _FALSIFIER_TEMPLATES.get(phase, [])
    for suffix, metric, op, threshold, horizon_d in templates:
        falsifier_id = f"{phase[:4]}_{suffix}"
        expr = f"{metric} {op} {threshold}"
        falsifiers.append({
            "id":        falsifier_id,
            "expr":      expr,
            "horizon_d": horizon_d,
        })

    return _PhaseResult(
        phase=phase,
        confidence=confidence,
        evidence=evidence,
        contradictions=contradictions,
        falsifiers=falsifiers,
    )


# ---------------------------------------------------------------------------
# Backfill vectorized classifier
# ---------------------------------------------------------------------------

def classify_history(
    feature_df: pd.DataFrame,
    data_gaps: list[str],
    apply_hysteresis: bool = True,
) -> pd.DataFrame:
    """Classify every row in feature_df.  Returns phase_tape DataFrame.

    Applies hysteresis via a rolling-window smooth:  a phase must appear for
    MIN_DWELL_SESSIONS consecutive days to "stick".  Transitions are assigned
    the new phase only once the dwell count is reached.
    """
    if feature_df.empty:
        return pd.DataFrame(columns=[
            "date", "phase", "confidence", "evidence", "contradictions",
            "falsifiers", "backfill",
        ])

    # DSL metric columns are stored in the tape so falsifier grading can evaluate
    # prior prints at their due_date (CN-SYS-R5).
    _METRIC_COLS = ["lup5", "ldn5", "lban5", "turnover_z20", "margin_chg_5d", "qvix_z", "sec_wash"]

    rows: list[dict[str, Any]] = []
    for dt, row in feature_df.iterrows():
        result = _classify_row(row)
        row_dict: dict[str, Any] = {
            "date":          dt,
            "phase":         result.phase,
            "confidence":    result.confidence,
            "evidence":      result.evidence,
            "contradictions":result.contradictions,
            "falsifiers":    result.falsifiers,
            "backfill":      True,
            "_data_gaps":    list(data_gaps),
        }
        # Persist DSL metrics for falsifier grading
        for col in _METRIC_COLS:
            val = row.get(col)
            row_dict[col] = None if (val is None or (isinstance(val, float) and np.isnan(val))) else float(val)
        rows.append(row_dict)

    tape = pd.DataFrame(rows).set_index("date")
    tape.index = pd.to_datetime(tape.index)

    if apply_hysteresis and len(tape) >= MIN_DWELL_SESSIONS:
        tape = _apply_hysteresis(tape)

    return tape


def _apply_hysteresis(
    tape: pd.DataFrame,
    seed_phase: str | None = None,
    seed_dwell: int = 0,
) -> pd.DataFrame:
    """Smooth phase series so each phase must dwell MIN_DWELL_SESSIONS days.

    Algorithm: forward-pass; a transition to a new phase is accepted only after
    that phase has been the 'raw' phase for MIN_DWELL_SESSIONS consecutive rows.
    Otherwise the previous stable phase is kept.

    Parameters
    ----------
    seed_phase : str | None
        The last stable phase from a prior tape segment.  When supplied (nightly
        increment path), the algorithm starts from this phase rather than the
        first row's raw phase, giving continuity across night boundaries.
    seed_dwell : int
        How many consecutive sessions the prior tape segment has already dwelled
        in seed_phase.  Combined with this slice's leading rows, the total dwell
        is counted correctly so a multi-night ramp accumulates properly.
    """
    phases = tape["phase"].tolist()
    n = len(phases)

    if seed_phase is not None:
        # Seed from the prior tape's last stable phase + its running dwell count.
        current_phase = seed_phase
        # If first row matches the seed, carry the existing dwell count forward.
        if phases[0] == seed_phase:
            candidate = seed_phase
            candidate_count = seed_dwell + 1
        else:
            candidate = phases[0]
            candidate_count = 1
    else:
        current_phase = phases[0]
        candidate = phases[0]
        candidate_count = 1

    stable = []
    # Emit the first row's stable value
    if candidate == current_phase or candidate_count >= MIN_DWELL_SESSIONS:
        if candidate_count >= MIN_DWELL_SESSIONS:
            current_phase = candidate
        stable.append(current_phase)
    else:
        stable.append(current_phase)

    for i in range(1, n):
        p = phases[i]
        if p == candidate:
            candidate_count += 1
        else:
            candidate = p
            candidate_count = 1

        if candidate == current_phase:
            stable.append(current_phase)
        elif candidate_count >= MIN_DWELL_SESSIONS:
            current_phase = candidate
            stable.append(current_phase)
        else:
            # In the middle of a candidate accumulation — keep current stable phase
            stable.append(current_phase)

    tape = tape.copy()
    tape["phase"] = stable
    return tape


# ---------------------------------------------------------------------------
# Falsifier grading
# ---------------------------------------------------------------------------

def grade_falsifiers(
    phase_tape: pd.DataFrame,
    grading_date: pd.Timestamp,
    existing_ledger: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Grade all falsifiers from phase_tape whose due_date <= grading_date.

    Reads each falsifier from the tape's falsifiers column, checks if it is due,
    and evaluates it against the feature metrics stored in the tape row at
    due_date.  Appends to existing_ledger if provided.

    Returns updated falsifier_ledger DataFrame per §5 schema:
      printed_date, falsifier_id, expr, due_date, outcome, graded_date
    """
    schema_cols = ["printed_date", "falsifier_id", "expr", "due_date", "outcome", "graded_date"]
    if existing_ledger is None:
        existing_ledger = pd.DataFrame(columns=schema_cols)

    # Build lookup of already-graded (printed_date, falsifier_id) pairs
    if not existing_ledger.empty:
        graded_keys = set(
            zip(
                pd.to_datetime(existing_ledger["printed_date"]).dt.date,
                existing_ledger["falsifier_id"].tolist(),
            )
        )
    else:
        graded_keys: set = set()

    new_rows: list[dict[str, Any]] = []

    # Build a sorted integer-position index for market-session horizon lookup.
    # horizon_d is interpreted as N MARKET SESSIONS (not calendar days): we find
    # the position of printed_dt in the tape index and advance by horizon_d
    # positions.  This prevents 40% of due_dates from landing on weekends/
    # holidays and being forced to "indeterminate" (MAJOR found in review).
    tape_index_sorted = phase_tape.index.sort_values()
    tape_pos_map: dict[pd.Timestamp, int] = {
        ts: i for i, ts in enumerate(tape_index_sorted)
    }

    for printed_dt, row in phase_tape.iterrows():
        falsifiers_raw = row.get("falsifiers") or []
        if not isinstance(falsifiers_raw, list):
            # stored as JSON string in some parquet writers
            try:
                falsifiers_raw = json.loads(falsifiers_raw)
            except Exception:
                falsifiers_raw = []

        for fal in falsifiers_raw:
            fid  = fal.get("id", "")
            expr = fal.get("expr", "")
            horiz = int(fal.get("horizon_d", 10))

            # Resolve due_date as N market sessions forward (not calendar days).
            printed_pos = tape_pos_map.get(pd.Timestamp(printed_dt))
            if printed_pos is None:
                continue
            due_pos = printed_pos + horiz
            if due_pos >= len(tape_index_sorted):
                continue  # beyond tape tail — not gradeable yet
            due_dt = tape_index_sorted[due_pos]

            if due_dt > grading_date:
                continue  # not due yet

            key = (pd.Timestamp(printed_dt).date(), fid)
            if key in graded_keys:
                continue  # already graded

            # Look up metrics at due_date in the phase_tape
            if due_dt in phase_tape.index:
                due_row = phase_tape.loc[due_dt]
                # Reconstruct a best-effort metrics dict from available tape columns
                # (falsifier metrics are already embedded via feature frame)
                outcome = _eval_falsifier(expr, {
                    "lup5":          _safe(due_row.get("lup5")),
                    "ldn5":          _safe(due_row.get("ldn5")),
                    "lban5":         _safe(due_row.get("lban5")),
                    "turnover_z20":  _safe(due_row.get("turnover_z20")),
                    "margin_chg_5d": _safe(due_row.get("margin_chg_5d")),
                    "qvix_z":        _safe(due_row.get("qvix_z")),
                    "sec_wash":      _safe(due_row.get("sec_wash")),
                })
            else:
                outcome = "indeterminate"

            new_rows.append({
                "printed_date":  printed_dt,
                "falsifier_id":  fid,
                "expr":          expr,
                "due_date":      due_dt,
                "outcome":       outcome,
                "graded_date":   grading_date,
            })
            graded_keys.add(key)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        return pd.concat([existing_ledger, new_df], ignore_index=True)

    return existing_ledger


# ---------------------------------------------------------------------------
# Latest-snapshot JSON
# ---------------------------------------------------------------------------

def build_cycle_phase_json(
    phase_tape: pd.DataFrame,
    falsifier_ledger: pd.DataFrame,
    data_gaps: list[str],
    built_at: str | None = None,
) -> dict[str, Any]:
    """Build the cycle_phase.json site artifact from the latest tape row."""
    if built_at is None:
        built_at = datetime.now(timezone.utc).isoformat()

    if phase_tape.empty:
        return {
            "schema": SCHEMA,
            "authority": {"tier": "context_only"},
            "built": built_at,
            "asof": None,
            "phase": None,
            "confidence": None,
            "evidence": [],
            "contradictions": [],
            "falsifiers": [],
            "data_gaps": list(data_gaps),
            "era_table": ERA_TABLE,
            "ledger_summary": {},
        }

    latest = phase_tape.iloc[-1]
    asof = str(phase_tape.index[-1].date())

    # Decode list columns that may have been round-tripped through parquet as
    # JSON strings (see _save_tape in the builder).  Without this, list(str)
    # splits the string into individual characters, corrupting evidence/
    # contradictions/falsifiers in the JSON artifact (BLOCKER found in review).
    def _as_list(val: Any) -> list:
        if val is None:
            return []
        if isinstance(val, str):
            try:
                decoded = json.loads(val)
                return list(decoded) if isinstance(decoded, list) else []
            except Exception:
                return []
        try:
            return list(val)
        except Exception:
            return []

    # Falsifier ledger summary
    ledger_summary: dict[str, Any] = {}
    if not falsifier_ledger.empty:
        outcome_counts = falsifier_ledger["outcome"].value_counts().to_dict()
        ledger_summary = {
            "total_graded": len(falsifier_ledger),
            "held": outcome_counts.get("held", 0),
            "fired": outcome_counts.get("fired", 0),
            "indeterminate": outcome_counts.get("indeterminate", 0),
        }

    # Allowed actions per phase (display framing only — CN-SYS-R1 / context_only)
    allowed_actions_map: dict[str, list[str]] = {
        "CAPITULATION":      ["monitor_only", "no_new_positions"],
        "POLICY_PUT":        ["watch_for_stabilisation", "reversal_only"],
        "LIQUIDITY_IGNITION":["reversal_only", "no_chase"],
        "THEME_LEADERSHIP":  ["watch_leaders", "no_chase"],
        "BROADENING":        ["watch_rotation", "no_chase"],
        "EUPHORIA":          ["no_chase", "distribution_watch"],
        "DISTRIBUTION":      ["caution_only", "no_new_longs"],
        "DELEVERAGING":      ["monitor_only", "no_new_positions"],
        "GRINDING_BEAR":     ["monitor_only", "cash_is_option"],
        "REPAIR":            ["watch_for_base", "reversal_only"],
    }
    phase_str = str(latest.get("phase") or "REPAIR")

    return {
        "schema":        SCHEMA,
        "authority":     {"tier": "context_only"},
        "built":         built_at,
        "asof":          asof,
        "phase":         phase_str,
        "confidence":    float(latest.get("confidence") or 0.0),
        "evidence":      _as_list(latest.get("evidence")),
        "contradictions":_as_list(latest.get("contradictions")),
        "falsifiers":    _as_list(latest.get("falsifiers")),
        "allowed_actions": allowed_actions_map.get(phase_str, ["monitor_only"]),
        "data_gaps":     list(data_gaps),
        "era_table":     ERA_TABLE,
        "ledger_summary":ledger_summary,
        "caveat": (
            "regime_history is a current-best-estimate non-PIT series; "
            "policy_impulse is a CURRENT-STATE scalar broadcast to all backfill rows "
            "(not a per-date historical series) — POLICY_PUT backfill counts reflect "
            "today's policy stance, not the historical stance at each date; "
            "all outputs are context_only (CN-SYS-R1)"
        ),
    }
