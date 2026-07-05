"""Entry-Stack Expansion W2 — S-UR Spring Reclaim (Undercut-and-Rally) Phase-0 Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §3 F2, §5.
Amendment 1 ref: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md
  RUL-13: primary horizons = 21d (stop5, fwd_mdd_21 / mae21, clean8_21, days_to_10)
  RUL-14: co-primaries zone_held_21, stop_vol_21
W0 baselines frozen: research/entry_stack/W0_BASELINES.md (RUL-9).
NC yardstick: research/entry_stack/W1_NC_REPORT.md (RUL-3).

SPECIES: S14 — Spring Reclaim (U&R), horizon_class=rotational, phase0.

TRIAL FAMILY: esx_ur_phase0 (budget=36):
  2 lows {21, 63} x 3 reclaim windows {2, 3, 5} x 2 depth-arms (panel-determined,
  ATR mult frozen 1.0) x 3 forms (standalone / COILED / gate-fire-proximity).

ORDER OF OPERATIONS (RUL-5): registry FIRST (done), ledger SECOND (done), study THIRD.

Three forms per parameter cell:
  (a) standalone:  raw U&R events from engine/entry_primitives.undercut_rally_events
  (b) COILED intersection: events that occur inside cohort washout context
      (engine/coiled.washout_ctx per fire, reuses cohort-washout machinery)
  (c) gate-fire proximity: events within +/-5 bars of gate_fires_{panel}.parquet

PANELS:
  - deep:    data/stocks/ (224 names, close + high/low → H/L arm; 64y history)
  - baskets: data/baskets/ohlcv/ (2,519 names, full OHLCV 2014+; H/L arm)
  - delisted (close-only): data/breadth/_closes_delisted.parquet
             (close-only arm with survivor stamps; absent = graceful skip with notice)

All events use T+1 fill, graded via engine.grading forward_metrics + terminal_state.
BH q<=0.10 within esx_ur_phase0 family.

NC-YARDSTICK: NC-2 proximity top-tercile stop5 coef on deep = -0.0427 [-0.044, -0.031]
  (significant, recall=33.4%). A candidate beats NC-2 iff its coefficient retains
  CI-excluding-0 AFTER entry_quality-band FE (DEFERRED; stamped if not computable).

Usage:
    cd /path/to/repo
    python scripts/research/run_w2_sur.py
    python scripts/research/run_w2_sur.py --smoke
    python scripts/research/run_w2_sur.py --n-bootstrap 500 --panel deep baskets
    python scripts/research/run_w2_sur.py --out research/entry_stack/W2_SUR_REPORT.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import harness primitives from W0 PR-C
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
)

# Import fast R1 estimator and formatting helpers from NC runner
from scripts.research.run_w1_nc import (  # noqa: E402
    fast_r1_estimate,
    fast_effect_table,
    fast_era_table,
    bh_correction,
    _fast_make_blocks,
    _empty_r1,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_DELISTED_PATH = _DATA / "breadth" / "_closes_delisted.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"
_DEEP_STORE    = _DATA / "stocks"
_BASKETS_OHLCV = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Frozen study parameters (masterplan F2, not tunable)
# ---------------------------------------------------------------------------
# Low lookback windows (N in {21, 63})
LOOKBACK_WINDOWS = [21, 63]
# Reclaim windows (k in {2, 3, 5})
RECLAIM_WINDOWS = [2, 3, 5]
# ATR multiplier frozen at 1.0
ATR_MULT_FROZEN = 1.0
# Gate-fire proximity: +/-5 bars
GATE_FIRE_PROXIMITY_BARS = 5
# Primary analysis: n21 / k3 / standalone
PRIMARY_N   = 21
PRIMARY_K   = 3
# Species bar: n >= 150 deduped episodes per form
MIN_EPISODES_PER_FORM = 150
# Independence clause: co-fire <= 60%
MAX_COFIRE_SHARE = 0.60
# Non-inferiority margin (CI lower bound > -1pp vs incumbent)
NONINFERIORITY_MARGIN = -0.01


# ---------------------------------------------------------------------------
# OHLCV loader (deep panel: close + high + low; baskets: close + high + low)
# ---------------------------------------------------------------------------

def _load_deep_ohlcv() -> dict[str, pd.DataFrame]:
    """Load deep panel: close + high + low (224 names)."""
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            cols = [c for c in ("close", "high", "low") if c in df.columns]
            if "close" not in cols:
                continue
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("deep: failed to load %s: %s", path, ticker)
    log.info("Loaded %d deep OHLCV records", len(store))
    return store


def _load_baskets_ohlcv() -> dict[str, pd.DataFrame]:
    """Load baskets panel: close + high + low (2,519 names)."""
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            cols = [c for c in ("close", "high", "low") if c in df.columns]
            if "close" not in cols:
                continue
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("baskets: failed to load %s", ticker)
    log.info("Loaded %d basket OHLCV records", len(store))
    return store


def _load_delisted_closes() -> pd.DataFrame | None:
    """Load delisted close-only panel. Returns None if absent (R2 store)."""
    if not _DELISTED_PATH.exists():
        log.warning(
            "Delisted panel not found at %s — R2 store absent on this checkout. "
            "Close-only survivor analysis will be SKIPPED. "
            "This is expected on a fresh worktree without R2 data.",
            _DELISTED_PATH,
        )
        return None
    try:
        df = pd.read_parquet(_DELISTED_PATH)
        log.info("Loaded delisted panel: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load delisted panel: %s", exc)
        return None


# ---------------------------------------------------------------------------
# U&R event enumeration — wraps engine/entry_primitives.undercut_rally_events
# ---------------------------------------------------------------------------

def enumerate_ur_events(
    ohlcv_store: dict[str, pd.DataFrame],
    panel_name: str,
    n: int,
    k: int,
) -> pd.DataFrame:
    """Enumerate all U&R events for one (n, k) parameter cell across a panel.

    Uses the FROZEN definition from engine/entry_primitives.undercut_rally_events.
    H/L arm used when high and low columns are present; close-only arm otherwise.
    Depth arm is panel-determined (never mixed).

    Parameters
    ----------
    ohlcv_store : dict[str, DataFrame]
        {ticker: DataFrame with at least 'close'; optionally 'high'/'low'}.
    panel_name : str
        Label string stamped on every event row.
    n : int
        Rolling lookback window for the prior low (21 or 63).
    k : int
        Maximum reclaim bars (2, 3, or 5).

    Returns
    -------
    DataFrame with columns: ticker, date, n_low, k_reclaim, panel,
        undercut_date, broken_level, depth_frac, arm (H/L or close-only).
    Empty DataFrame (same columns) if no events found.
    """
    from engine.entry_primitives import undercut_rally_events

    rows = []
    skipped = 0
    exceptions = 0

    for ticker, df in ohlcv_store.items():
        if df.empty or "close" not in df.columns:
            skipped += 1
            continue

        close = df["close"]
        has_hl = ("high" in df.columns and "low" in df.columns
                  and df["high"].notna().any() and df["low"].notna().any())

        if has_hl:
            high = df["high"]
            low = df["low"]
            arm = "H/L"
        else:
            high = None
            low = None
            arm = "close-only"

        try:
            ev = undercut_rally_events(close, low=low, high=high, n=n, k=k)
        except Exception as exc:  # noqa: BLE001
            exceptions += 1
            log.debug("U&R exception for %s n=%d k=%d: %s", ticker, n, k, exc)
            continue

        fires = ev[ev["event"]]
        if fires.empty:
            continue

        for date, row in fires.iterrows():
            rows.append({
                "ticker": ticker,
                "date": date,
                "n_low": n,
                "k_reclaim": k,
                "panel": panel_name,
                "undercut_date": row["undercut_date"],
                "broken_level": row["broken_level"],
                "depth_frac": row["depth_frac"],
                "arm": arm,
            })

    log.info(
        "enumerate_ur_events: panel=%s n=%d k=%d → %d events (%d tickers skipped, %d exceptions)",
        panel_name, n, k, len(rows), skipped, exceptions,
    )

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "date", "n_low", "k_reclaim", "panel",
            "undercut_date", "broken_level", "depth_frac", "arm",
        ])

    result = pd.DataFrame(rows)
    result["date"] = pd.to_datetime(result["date"])
    result["undercut_date"] = pd.to_datetime(result["undercut_date"])
    return result.sort_values(["ticker", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Deduplication (episode-level) — one event per (ticker, episode_key)
# A U&R episode is keyed by (ticker, undercut_date) to prevent double-counting
# across parameter cells when the same flush produces two close reclaims.
# ---------------------------------------------------------------------------

def dedup_events(events: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate U&R events: one event per (ticker, undercut_date).

    When a ticker has multiple event rows sharing the same undercut_date
    (possible with different k windows), keep the FIRST one by date
    (shortest reclaim = earliest signal).

    Returns deduplicated DataFrame; event count stamped in log.
    """
    if events.empty:
        return events
    deduped = (
        events
        .sort_values(["ticker", "undercut_date", "date"])
        .drop_duplicates(subset=["ticker", "undercut_date"], keep="first")
        .reset_index(drop=True)
    )
    removed = len(events) - len(deduped)
    if removed > 0:
        log.info("dedup_events: removed %d duplicate episodes (same ticker+undercut_date)", removed)
    return deduped


# ---------------------------------------------------------------------------
# Form (b): COILED intersection labeling
# Uses engine/coiled.washout_ctx to label each event for COILED context.
# The COILED state is a point-in-time snapshot at the fire date (signal_date),
# not a forward-looking computation.
# ---------------------------------------------------------------------------

def label_coiled_context(
    events: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Add 'in_coiled_ctx' boolean column to events DataFrame.

    For each event, calls engine.coiled.washout_ctx on the close series
    truncated to the signal date (fire date = event date). This reuses the
    existing cohort-washout machinery (engine/coiled.py washout_ctx) without
    reinventing COILED.

    COILED recall computation: the share of gate fires (T1-T3) that also
    have a matching U&R event within +/-5 bars is NOT computed here
    (that is the gate-fire proximity form, form c). The recall clause
    (recall >= half of COILED-FIRE recall) requires COILED-FIRE recall to
    be first computed — deferred to the report section.

    Parameters
    ----------
    events : DataFrame with 'ticker', 'date' columns.
    ohlcv_store : {ticker: DataFrame with 'close'}.

    Returns
    -------
    events with added column 'in_coiled_ctx' (bool or None for untestable).
    """
    from engine.coiled import washout_ctx

    results = []
    coiled_exceptions = 0

    for _, row in events.iterrows():
        ticker = row["ticker"]
        fire_date = pd.Timestamp(row["date"])

        df = ohlcv_store.get(ticker)
        if df is None or df.empty or "close" not in df.columns:
            results.append(None)
            continue

        close = df["close"]
        # Truncate strictly to fire_date (no lookahead)
        close_trunc = close[close.index <= fire_date]
        if close_trunc.empty:
            results.append(None)
            continue

        try:
            ctx = washout_ctx(close_trunc)
            results.append(bool(ctx) if ctx is not None else None)
        except Exception as exc:  # noqa: BLE001
            coiled_exceptions += 1
            results.append(None)

    if coiled_exceptions > 0:
        log.warning(
            "label_coiled_context: %d exceptions calling washout_ctx (set to None)",
            coiled_exceptions,
        )

    events = events.copy()
    events["in_coiled_ctx"] = results
    coiled_n = sum(1 for v in results if v is True)
    testable = sum(1 for v in results if v is not None)
    log.info(
        "label_coiled_context: %d/%d testable events in COILED context (%.1f%%)",
        coiled_n, testable, 100 * coiled_n / max(testable, 1),
    )
    return events


# ---------------------------------------------------------------------------
# Form (c): gate-fire proximity labeling
# ---------------------------------------------------------------------------

def label_gate_fire_proximity(
    events: pd.DataFrame,
    gate_fires: pd.DataFrame,
    proximity_bars: int = GATE_FIRE_PROXIMITY_BARS,
) -> pd.DataFrame:
    """Add 'near_gate_fire' boolean and 'gate_fire_proximity_bars' columns.

    For each U&R event, checks whether a gate fire for the same ticker exists
    within +/-proximity_bars bars (calendar-day approximation: 7 calendar days
    per 5 trading bars, so +/-5 bars ~ +/-7 calendar days).

    Also computes 'co_fire_share' over the full events DataFrame (the
    independence clause: co-fire <= 60%).

    Parameters
    ----------
    events : DataFrame with 'ticker', 'date'.
    gate_fires : DataFrame with 'ticker', 'date' columns from gate_fires_*.parquet.
    proximity_bars : int, bars radius (default 5 trading bars ~ 7 calendar days).

    Returns
    -------
    events with added columns:
        near_gate_fire (bool): True if a gate fire exists within proximity_bars.
        min_gate_fire_dist_bars (float): minimum abs distance in approximate trading bars.
    """
    # Approximate trading-bar to calendar day: 1 bar ~ 1.4 calendar days
    proximity_calendar_days = int(np.ceil(proximity_bars * 1.5))  # conservative

    gf_by_ticker: dict[str, np.ndarray] = {}
    for ticker, grp in gate_fires.groupby("ticker"):
        gf_by_ticker[str(ticker)] = pd.to_datetime(grp["date"]).sort_values().values

    near = []
    min_dist = []

    for _, row in events.iterrows():
        ticker = str(row["ticker"])
        ev_date = pd.Timestamp(row["date"])

        gf_dates = gf_by_ticker.get(ticker)
        if gf_dates is None or len(gf_dates) == 0:
            near.append(False)
            min_dist.append(np.nan)
            continue

        diffs = np.abs((gf_dates - np.datetime64(ev_date, "ns")).astype("timedelta64[D]").astype(int))
        min_d = float(diffs.min())
        # Approximate: proximity_calendar_days covers ±proximity_bars trading bars
        near.append(min_d <= proximity_calendar_days)
        # Convert calendar days back to approximate trading bars
        min_dist.append(round(min_d / 1.4, 1))

    events = events.copy()
    events["near_gate_fire"] = near
    events["min_gate_fire_dist_bars"] = min_dist

    n_near = sum(near)
    co_fire_share = n_near / max(len(events), 1)
    log.info(
        "label_gate_fire_proximity: %d/%d events near gate fire (%.1f%% co-fire share; "
        "independence clause: <= %.0f%%)",
        n_near, len(events), 100 * co_fire_share, 100 * MAX_COFIRE_SHARE,
    )
    return events


# ---------------------------------------------------------------------------
# Grade events via the harness (T+1 fill, both horizon classes)
# ---------------------------------------------------------------------------

def grade_ur_events(
    events: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    panel: str,
) -> pd.DataFrame:
    """Grade U&R events via the program harness grader.

    Constructs a fires-format DataFrame (ticker, date, tier, sub, ticks, ...)
    from U&R events and passes it to grade_fires from entry_strata_phase0.

    Returns graded DataFrame with all forward metrics and outcome columns.
    """
    if events.empty:
        log.warning("grade_ur_events: no events to grade for panel=%s", panel)
        return pd.DataFrame()

    # Build minimal fires-format DataFrame for grade_fires
    fires_df = pd.DataFrame({
        "ticker": events["ticker"].values,
        "date":   events["date"].values,
        "tier":   "SUR",   # study-internal tier label
        "sub":    events["arm"].values,
        "ticks":  0.0,
        "not_topped": True,
        "eligible":   True,
        "panel":      panel,
    })

    # sector mapping
    fires_df["sector"] = fires_df["ticker"].map(sector_map)

    # Build closes dict from ohlcv_store
    closes = {t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns}

    graded = grade_fires(fires_df, closes)
    graded = _prepare_binary_outcomes(graded)
    graded["_date_ts"] = pd.to_datetime(graded["date"]).astype(np.int64)
    graded["era"] = graded["date"].apply(_assign_era)

    # Attach form labels from events (aligned by index)
    for col in ("n_low", "k_reclaim", "arm", "depth_frac",
                "in_coiled_ctx", "near_gate_fire", "min_gate_fire_dist_bars"):
        if col in events.columns:
            graded[col] = events[col].values

    n_gradable = int(graded["gradable"].sum())
    log.info(
        "grade_ur_events: panel=%s → %d events, %d gradable (%.1f%%)",
        panel, len(graded), n_gradable, 100 * n_gradable / max(len(graded), 1),
    )
    return graded


# ---------------------------------------------------------------------------
# Primary outcomes list (RUL-13 + RUL-14)
# ---------------------------------------------------------------------------

OUTCOME_COLS = [
    "stop5",          # immediate stop-out within 5 bars (primary)
    "rotational_liftoff",  # clean8_21 terminal state
    "positional_liftoff",  # clean15_126 terminal state
    "dead_money",     # dead-money rate
    "cushion_rot",    # cushion incidence (rotational)
    "mae63",          # MAE at 63d (kept for continuity; mae21 = fwd_mdd_21)
    "zone_held_21",   # RUL-14 co-primary: vol-scaled zone held at 21d
    "stop_vol_21",    # RUL-14 co-primary: vol-scaled stop at 21d
]


# ---------------------------------------------------------------------------
# Form analysis: run R1 estimate for a single stratum label
# ---------------------------------------------------------------------------

def run_form_analysis(
    graded: pd.DataFrame,
    stratum_col: str,
    panel: str,
    sector_col: str = "sector",
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
) -> dict[str, Any]:
    """Run R1 date-FE estimate for each outcome column for one form.

    Parameters
    ----------
    graded : DataFrame with all outcome columns and the stratum_col.
    stratum_col : binary column (1 = treatment, 0 = control).
    panel : label string for FE fallback detection.
    sector_col : sector column name for episode blocks.

    Returns
    -------
    dict with keys: n_treatment, n_control, effects, era_table, raw_graded.
    effects : list of R1 result dicts (one per outcome).
    """
    if graded.empty or stratum_col not in graded.columns:
        return {"n_treatment": 0, "n_control": 0, "effects": [], "era_table": None}

    gradable = graded[graded["gradable"] == True].copy()  # noqa: E712
    if gradable.empty:
        return {"n_treatment": 0, "n_control": 0, "effects": [], "era_table": None}

    # FE column: date (frozen per RUL-12 W0 sign-off)
    gradable["_fe"] = gradable["date"].astype(str)
    sector_col_eff = sector_col if sector_col in gradable.columns and gradable[sector_col].notna().any() else None

    effects = []
    p_values = []
    labels = []

    for outcome in OUTCOME_COLS:
        if outcome not in gradable.columns:
            continue
        if gradable[outcome].notna().sum() < 10:
            continue

        res = fast_r1_estimate(
            gradable,
            outcome_col=outcome,
            stratum_col=stratum_col,
            fe_col="_fe",
            sector_col=sector_col_eff,
            n_bootstrap=n_bootstrap,
            rng_seed=rng_seed,
        )
        res["panel"] = panel
        effects.append(res)
        p_values.append(res.get("p_value"))
        labels.append(outcome)

    # BH correction across outcomes
    bh_results = bh_correction(p_values, labels, BH_Q_THRESHOLD)
    bh_map = {r["label"]: r for r in bh_results}
    for res in effects:
        bh = bh_map.get(res.get("outcome", ""), {})
        res["bh_q"] = bh.get("q_value")
        res["bh_rejected"] = bh.get("rejected")

    # Era table for stop5 (primary)
    era_tbl = None
    if "stop5" in gradable.columns and stratum_col in gradable.columns:
        try:
            era_tbl = fast_era_table(gradable, "stop5", stratum_col, era_col="era")
        except Exception as exc:  # noqa: BLE001
            log.debug("era_table error: %s", exc)

    n_treatment = int((gradable[stratum_col] == 1).sum()) if stratum_col in gradable.columns else 0
    n_control   = int((gradable[stratum_col] == 0).sum()) if stratum_col in gradable.columns else 0

    return {
        "n_treatment": n_treatment,
        "n_control":   n_control,
        "effects":     effects,
        "era_table":   era_tbl,
        "raw_graded":  gradable,
    }


# ---------------------------------------------------------------------------
# Species bar check (mechanical; per masterplan §5)
# ---------------------------------------------------------------------------

def check_species_bar(
    standalone_results: dict[str, Any],
    coiled_results: dict[str, Any],
    gatefire_results: dict[str, Any],
    n_standalone: int,
    n_coiled: int,
    n_gatefire: int,
    co_fire_share: float,
    coiled_fire_recall: float | None,
    ur_recall: float,
) -> dict[str, Any]:
    """Evaluate species bar clauses mechanically.

    Returns dict with per-clause met/not-met verdicts (no promotion decision).
    """
    verdicts: dict[str, Any] = {}

    # Clause 1: n >= 150 deduped episodes per form
    verdicts["n_standalone_met"] = n_standalone >= MIN_EPISODES_PER_FORM
    verdicts["n_coiled_met"]     = n_coiled >= MIN_EPISODES_PER_FORM
    verdicts["n_gatefire_met"]   = n_gatefire >= MIN_EPISODES_PER_FORM
    verdicts["n_standalone"]     = n_standalone
    verdicts["n_coiled"]         = n_coiled
    verdicts["n_gatefire"]       = n_gatefire

    # Clause 2: non-inferiority on stop5 (CI lower bound > -1pp vs incumbent)
    # Incumbent deep T1 stop5 rate = 11.6% (W0_BASELINES.md)
    stop5_effects_sa = [e for e in standalone_results.get("effects", []) if e.get("outcome") == "stop5"]
    if stop5_effects_sa:
        ci_lo = stop5_effects_sa[0].get("ci_lo")
        verdicts["stop5_noninferiority_met"] = (ci_lo is not None and ci_lo > NONINFERIORITY_MARGIN)
        verdicts["stop5_ci_lo"] = ci_lo
    else:
        verdicts["stop5_noninferiority_met"] = None
        verdicts["stop5_ci_lo"] = None

    # Clause 3: superiority CI-excl-0 on >= 1 of {stop-out, dead-money, cushion incidence}
    constitution_axes = ["stop5", "dead_money", "cushion_rot"]
    superior_axes = []
    for ax in constitution_axes:
        for result_set in (standalone_results, coiled_results, gatefire_results):
            effects = [e for e in result_set.get("effects", []) if e.get("outcome") == ax]
            if effects:
                ci_lo = effects[0].get("ci_lo")
                ci_hi = effects[0].get("ci_hi")
                if ci_lo is not None and ci_hi is not None:
                    if (ax == "stop5" and ci_hi < 0) or (ax != "stop5" and ci_lo > 0):
                        if ax not in superior_axes:
                            superior_axes.append(ax)
    verdicts["superiority_axes"] = superior_axes
    verdicts["superiority_met"] = len(superior_axes) >= 1

    # Clause 4: recall clause (recall >= half of COILED-FIRE recall)
    if coiled_fire_recall is not None:
        verdicts["recall_clause_threshold"] = coiled_fire_recall / 2.0
        verdicts["recall_ur"] = ur_recall
        verdicts["recall_clause_met"] = ur_recall >= coiled_fire_recall / 2.0
    else:
        verdicts["recall_clause_threshold"] = None
        verdicts["recall_ur"] = ur_recall
        verdicts["recall_clause_met"] = None  # DEFERRED: COILED-FIRE recall not yet computed
        verdicts["recall_clause_note"] = (
            "DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. "
            "Cannot evaluate recall clause from this study alone. "
            "See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute."
        )

    # Clause 5: independence clause (co-fire <= 60%)
    verdicts["co_fire_share"] = co_fire_share
    verdicts["independence_clause_met"] = co_fire_share <= MAX_COFIRE_SHARE

    return verdicts


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    lines: list[str],
    *,
    panel_results: dict[str, Any],
    species_bar: dict[str, Any],
    coiled_fire_recall_note: str,
    nc2_note: str,
    smoke: bool = False,
) -> str:
    """Write the W2 S-UR phase-0 report in markdown."""

    lines.append("# W2 Spring Reclaim (U&R) Phase-0 Report — Entry-Stack Expansion")
    lines.append("")
    lines.append("**Status:** W2 study report only — no promotion decision (RUL-3).")
    lines.append("**Date:** 2026-07-05")
    lines.append("**Species:** S14 — Spring Reclaim (U&R), horizon_class=rotational, phase0.")
    lines.append("**Family:** esx_ur_phase0 (budget=36).")
    lines.append("")

    if smoke:
        lines.append("> **SMOKE RUN** — reduced bootstrap (50 resamples). Results are indicative, not final.")
        lines.append("")

    # NC yardstick table (RUL-3: appears first)
    lines.append("## NC Yardstick (RUL-3 mandatory preamble)")
    lines.append("")
    lines.append("Per masterplan §10 RUL-3: the null-competitors appear as the first table.")
    lines.append("Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.")
    lines.append("NC-2 proximity top-tercile deep stop5 coef = −0.0427 [−0.044, −0.031]* (significant).")
    lines.append("The S-UR candidate 'beats NC-2' only if its coefficient retains CI-excluding-0")
    lines.append("AFTER entry_quality-band fixed effects (DEFERRED: cycles.py pipeline required).")
    lines.append("")
    lines.append("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |")
    lines.append("|---|---|---|---|---|---|")
    lines.append("| deep | NC-1A (T1-only) | −0.0019 | [−0.016, +0.008] | no | 89.1% |")
    lines.append("| deep | NC-1B (ticks=0) | +0.0001 | [−0.015, +0.007] | no | 90.8% |")
    lines.append("| deep | NC-2 (prox top-tercile) | −0.0427 | [−0.044, −0.031] * | YES * | 33.4% |")
    lines.append("| baskets | NC-1A (T1-only) | −0.0036 | [−0.011, +0.006] | no | 85.9% |")
    lines.append("| baskets | NC-1B (ticks=0) | +0.0099 | [+0.002, +0.015] * | YES * | 90.9% |")
    lines.append("| baskets | NC-2 (prox top-tercile) | −0.1012 | [−0.108, −0.096] * | YES * | 34.0% |")
    lines.append("")
    lines.append(f"NC-2 proximity note: the NC-2 full marginality test (coefficient survives eq-band FE)")
    lines.append(f"is DEFERRED. {nc2_note}")
    lines.append("")

    # COILED-FIRE recall note
    lines.append("## COILED-FIRE Recall Clause Note")
    lines.append("")
    lines.append(coiled_fire_recall_note)
    lines.append("")

    # Species bar summary
    lines.append("## Species Bar Summary (mechanical, state met/not-met per clause)")
    lines.append("")
    lines.append("Per masterplan §5: non-inferiority + superiority + n >= 150 + recall + independence.")
    lines.append("NO promotion decision is made in this report (RUL-3).")
    lines.append("")
    lines.append("| Clause | Value | Met? |")
    lines.append("|---|---|---|")

    def _yn(v: bool | None) -> str:
        if v is True:   return "YES"
        if v is False:  return "NO"
        return "DEFERRED"

    lines.append(f"| n_standalone >= 150 | {species_bar.get('n_standalone', 0)} | {_yn(species_bar.get('n_standalone_met'))} |")
    lines.append(f"| n_coiled >= 150 | {species_bar.get('n_coiled', 0)} | {_yn(species_bar.get('n_coiled_met'))} |")
    lines.append(f"| n_gatefire >= 150 | {species_bar.get('n_gatefire', 0)} | {_yn(species_bar.get('n_gatefire_met'))} |")
    ci_lo_str = f"{species_bar.get('stop5_ci_lo'):.4f}" if species_bar.get('stop5_ci_lo') is not None else "—"
    lines.append(f"| Stop5 non-inferiority (CI_lo > -1pp) | {ci_lo_str} | {_yn(species_bar.get('stop5_noninferiority_met'))} |")
    sup_axes = species_bar.get('superiority_axes', [])
    lines.append(f"| Superiority CI-excl-0 on >=1 axis | {sup_axes if sup_axes else 'none'} | {_yn(species_bar.get('superiority_met'))} |")
    ur_recall_str = f"{species_bar.get('recall_ur', 0):.1%}"
    recall_thresh_str = f"{species_bar.get('recall_clause_threshold'):.1%}" if species_bar.get('recall_clause_threshold') is not None else "DEFERRED"
    lines.append(f"| Recall clause (>= half COILED-FIRE recall) | S-UR={ur_recall_str} threshold={recall_thresh_str} | {_yn(species_bar.get('recall_clause_met'))} |")
    cofire_str = f"{species_bar.get('co_fire_share', 1.0):.1%}"
    lines.append(f"| Independence clause (co-fire <= 60%) | {cofire_str} | {_yn(species_bar.get('independence_clause_met'))} |")
    if species_bar.get("recall_clause_note"):
        lines.append(f"")
        lines.append(f"> **RECALL CLAUSE NOTE:** {species_bar['recall_clause_note']}")
    lines.append("")

    # Per-panel per-form results
    for panel_label, panel_data in panel_results.items():
        lines.append(f"## Panel: {panel_label}")
        lines.append("")
        survivor_msg = panel_data.get("survivor_stamp", "")
        if survivor_msg:
            lines.append(f"**SURVIVOR BIAS STAMP:** {survivor_msg}")
            lines.append("")

        for form_label, form_data in panel_data.get("forms", {}).items():
            lines.append(f"### Form: {form_label}")
            lines.append("")

            n_events = form_data.get("n_events_total", 0)
            n_deduped = form_data.get("n_events_deduped", 0)
            n_gradable = form_data.get("n_gradable", 0)
            n_treat = form_data.get("n_treatment", 0)
            n_ctrl  = form_data.get("n_control", 0)

            lines.append(f"- Total events: {n_events}")
            lines.append(f"- Deduped episodes: {n_deduped}")
            lines.append(f"- Gradable: {n_gradable}")
            lines.append(f"- N treatment: {n_treat} | N control: {n_ctrl}")

            if form_data.get("skipped"):
                lines.append(f"- **SKIPPED:** {form_data.get('skip_reason', '')}")
                lines.append("")
                continue

            effects = form_data.get("effects", [])
            if effects:
                lines.append("")
                lines.append("#### Effect Table (R1 FE, fast block bootstrap)")
                lines.append("")
                lines.append("| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |")
                lines.append("|---|---|---|---|---|---|---|")
                for e in effects:
                    outcome = e.get("outcome", "—")
                    coef = _fmt_f(e.get("coef"), 4)
                    ci = _ci_str(e)
                    naive = _fmt_f(e.get("naive_diff"), 4)
                    pv = _fmt_f(e.get("p_value"), 4)
                    bh_q = _fmt_f(e.get("bh_q"), 4)
                    rej = "YES" if e.get("bh_rejected") else "no"
                    excl = " *" if _excl_zero(e) == "YES *" else ""
                    lines.append(f"| {outcome} | {coef} | {ci}{excl} | {naive} | {pv} | {bh_q} | {rej} |")
            else:
                lines.append("")
                lines.append("*No gradable events for this form.*")

            era_tbl = form_data.get("era_table")
            if era_tbl is not None and hasattr(era_tbl, "iterrows"):
                lines.append("")
                lines.append("#### Era summary (stop5 rate by stratum)")
                lines.append("")
                lines.append("| era | stratum | n_fires | stop5_rate | mae63_mean |")
                lines.append("|---|---|---|---|---|")
                for _, r in era_tbl.iterrows():
                    era = r.get("era", "—")
                    stratum_val = r.get(form_data.get("stratum_col", "stratum"), "—")
                    nf = int(r.get("n_fires", 0))
                    s5 = _fmt_pct(r.get("stop5_mean"))
                    m63 = _fmt_f(r.get("mae63_mean"), 4) if r.get("mae63_mean") is not None else "—"
                    lines.append(f"| {era} | {stratum_val} | {nf} | {s5} | {m63} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by `scripts/research/run_w2_sur.py`*")
    lines.append("*Grader: engine/grading.py (program barriers, RUL-9).*")
    lines.append("*Family: esx_ur_phase0 (budget=36). BH q<=0.10 within family.*")
    lines.append("*Survivor bias: absolute rates on surviving names only; comparisons valid within constraint.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main study runner
# ---------------------------------------------------------------------------

def run_study(
    panels: list[str] | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
    smoke: bool = False,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full W2 S-UR phase-0 study.

    Parameters
    ----------
    panels : list of panel names to run ('deep', 'baskets', 'delisted').
             Default: ['deep', 'baskets'] (delisted skipped if file absent).
    n_bootstrap : number of block-bootstrap resamples.
    smoke : if True, use reduced bootstrap (50 resamples) and deep only.
    out_path : output path for the markdown report.

    Returns
    -------
    dict with all study results.
    """
    if smoke:
        n_bootstrap = 50
        if panels is None:
            panels = ["deep"]

    if panels is None:
        panels = ["deep", "baskets"]

    # Register trial families (idempotent)
    _register_all_families()

    sector_map = _build_sector_map()

    # Load gate fires for proximity labeling
    gate_fires_by_panel: dict[str, pd.DataFrame] = {}
    if _FIRES_DEEP.exists():
        gate_fires_by_panel["deep"] = load_fires(_FIRES_DEEP)
    if _FIRES_BASKETS.exists():
        gate_fires_by_panel["baskets"] = load_fires(_FIRES_BASKETS)

    panel_results: dict[str, Any] = {}
    all_cofire_shares: list[float] = []

    # Primary parameter cell for species bar: n=21, k=3
    primary_standalone_n_deduped = 0
    primary_coiled_n_deduped = 0
    primary_gatefire_n_deduped = 0
    primary_standalone_results: dict[str, Any] = {}
    primary_coiled_results:     dict[str, Any] = {}
    primary_gatefire_results:   dict[str, Any] = {}
    primary_ur_recall: float = 0.0

    for panel in panels:
        log.info("=== Panel: %s ===", panel)

        if panel == "delisted":
            delisted_df = _load_delisted_closes()
            if delisted_df is None:
                panel_results[panel] = {
                    "survivor_stamp": "SURVIVOR BIAS STAMP: delisted panel absent (R2 store).",
                    "forms": {},
                    "skip_note": "Delisted panel absent — R2 store. Skipped.",
                }
                log.info("Panel 'delisted' skipped — data absent.")
                continue
            # Build close-only ohlcv_store from delisted dataframe
            # Expected schema: columns are ticker symbols, index is date
            if isinstance(delisted_df.index, pd.DatetimeIndex):
                ohlcv_store = {
                    col: pd.DataFrame({"close": delisted_df[col].dropna()})
                    for col in delisted_df.columns
                }
            else:
                log.warning("Delisted panel has unexpected schema; skipping.")
                panel_results[panel] = {
                    "survivor_stamp": "SURVIVOR BIAS STAMP: delisted panel schema unknown.",
                    "forms": {},
                    "skip_note": "Delisted panel schema unrecognized.",
                }
                continue
            gate_fires = gate_fires_by_panel.get("deep", pd.DataFrame())
            survivor_stamp = "SURVIVOR BIAS STAMP: delisted close-only panel — ex-members included."
        elif panel == "deep":
            ohlcv_store = _load_deep_ohlcv()
            gate_fires = gate_fires_by_panel.get("deep", pd.DataFrame())
            survivor_stamp = "SURVIVOR BIAS STAMP: absolute rates on surviving deep-panel names only. Comparisons within-era are directionally valid."
        elif panel == "baskets":
            ohlcv_store = _load_baskets_ohlcv()
            gate_fires = gate_fires_by_panel.get("baskets", pd.DataFrame())
            survivor_stamp = "SURVIVOR BIAS STAMP: absolute rates on surviving basket names only. Comparisons within-era are directionally valid."
        else:
            log.warning("Unknown panel: %s — skipping.", panel)
            continue

        closes_only: dict[str, pd.Series] = {
            t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns
        }

        panel_forms: dict[str, Any] = {}

        # Run all parameter combinations (primary cell first for species bar)
        for n_val in LOOKBACK_WINDOWS:
            for k_val in RECLAIM_WINDOWS:
                cell_key = f"n{n_val}_k{k_val}"
                is_primary = (n_val == PRIMARY_N and k_val == PRIMARY_K)
                log.info("  Cell: %s (primary=%s)", cell_key, is_primary)

                # --- Enumerate events ---
                events_raw = enumerate_ur_events(ohlcv_store, panel, n=n_val, k=k_val)

                # --- Label COILED context ---
                if not events_raw.empty:
                    events_raw = label_coiled_context(events_raw, ohlcv_store)
                else:
                    events_raw["in_coiled_ctx"] = pd.Series(dtype=object)

                # --- Label gate-fire proximity ---
                if not events_raw.empty and not gate_fires.empty:
                    events_raw = label_gate_fire_proximity(events_raw, gate_fires)
                else:
                    events_raw["near_gate_fire"] = False
                    events_raw["min_gate_fire_dist_bars"] = np.nan

                # --- Deduplicate ---
                events_deduped = dedup_events(events_raw)

                # --- Grade ---
                if events_deduped.empty:
                    log.info("    No events after dedup for %s %s; skipping cell.", panel, cell_key)
                    for form_name in ("standalone", "coiled", "gatefire"):
                        panel_forms[f"{cell_key}_{form_name}"] = {
                            "n_events_total": 0,
                            "n_events_deduped": 0,
                            "n_gradable": 0,
                            "n_treatment": 0,
                            "n_control": 0,
                            "effects": [],
                            "skipped": True,
                            "skip_reason": "No events after deduplication.",
                        }
                    continue

                graded = grade_ur_events(events_deduped, ohlcv_store, sector_map, panel)
                n_gradable = int(graded["gradable"].sum()) if not graded.empty else 0

                # --- Form (a): standalone ---
                # All events are "standalone"; stratum = 1 for all vs control = 0
                # (The R1 estimator compares against the gate-fire population in W0)
                # For standalone, we run against all gradable fires from gate_fires
                # as baseline. Build the combined DataFrame.
                if not graded.empty and not gate_fires.empty:
                    # Load gate_fires graded (use closes_only for speed in smoke)
                    gf_graded = grade_fires(
                        gate_fires.copy(),
                        closes_only,
                    )
                    gf_graded = _prepare_binary_outcomes(gf_graded)
                    gf_graded["_date_ts"] = pd.to_datetime(gf_graded["date"]).astype(np.int64)
                    gf_graded["era"] = gf_graded["date"].apply(_assign_era)
                    gf_graded["in_coiled_ctx"] = None
                    gf_graded["near_gate_fire"] = False
                    gf_graded["sector"] = gf_graded["ticker"].map(sector_map)

                    # Combine: UR events get stratum=1; gate fires (not UR) get stratum=0
                    graded_sa = graded.copy()
                    graded_sa["_is_sur"] = 1
                    gf_graded["_is_sur"] = 0
                    combined_sa = pd.concat([graded_sa, gf_graded], ignore_index=True)
                    combined_sa["_date_ts"] = pd.to_datetime(combined_sa["date"]).astype(np.int64)

                    sa_results = run_form_analysis(
                        combined_sa, "_is_sur", panel,
                        sector_col="sector",
                        n_bootstrap=n_bootstrap,
                        rng_seed=rng_seed,
                    )
                else:
                    sa_results = {"n_treatment": len(graded), "n_control": 0, "effects": [], "era_table": None}

                n_sa_deduped = len(events_deduped)

                form_key_sa = f"{cell_key}_standalone"
                panel_forms[form_key_sa] = {
                    "n_events_total": len(events_raw),
                    "n_events_deduped": n_sa_deduped,
                    "n_gradable": n_gradable,
                    "n_treatment": sa_results.get("n_treatment", 0),
                    "n_control":   sa_results.get("n_control", 0),
                    "effects":     sa_results.get("effects", []),
                    "era_table":   sa_results.get("era_table"),
                    "stratum_col": "_is_sur",
                }

                # --- Form (b): COILED intersection ---
                coiled_mask = (graded["in_coiled_ctx"] == True) if "in_coiled_ctx" in graded.columns else pd.Series(False, index=graded.index)  # noqa: E712
                graded_coiled = graded[coiled_mask].copy() if not graded.empty else pd.DataFrame()
                n_coiled_events = int(coiled_mask.sum()) if not graded.empty else 0

                if not graded_coiled.empty and not gate_fires.empty:
                    gf_graded_c = gf_graded.copy()
                    graded_coiled["_is_sur"] = 1
                    gf_graded_c["_is_sur"] = 0
                    combined_coiled = pd.concat([graded_coiled, gf_graded_c], ignore_index=True)
                    combined_coiled["_date_ts"] = pd.to_datetime(combined_coiled["date"]).astype(np.int64)
                    coiled_results = run_form_analysis(
                        combined_coiled, "_is_sur", panel,
                        sector_col="sector",
                        n_bootstrap=n_bootstrap,
                        rng_seed=rng_seed,
                    )
                else:
                    coiled_results = {"n_treatment": n_coiled_events, "n_control": 0, "effects": [], "era_table": None}

                form_key_coiled = f"{cell_key}_coiled"
                panel_forms[form_key_coiled] = {
                    "n_events_total": n_coiled_events,
                    "n_events_deduped": n_coiled_events,
                    "n_gradable": int(graded_coiled["gradable"].sum()) if not graded_coiled.empty else 0,
                    "n_treatment": coiled_results.get("n_treatment", 0),
                    "n_control":   coiled_results.get("n_control", 0),
                    "effects":     coiled_results.get("effects", []),
                    "era_table":   coiled_results.get("era_table"),
                    "stratum_col": "_is_sur",
                }

                # --- Form (c): gate-fire proximity ---
                gf_prox_mask = (graded["near_gate_fire"] == True) if "near_gate_fire" in graded.columns else pd.Series(False, index=graded.index)  # noqa: E712
                graded_gf = graded[gf_prox_mask].copy() if not graded.empty else pd.DataFrame()
                n_gf_events = int(gf_prox_mask.sum()) if not graded.empty else 0

                co_fire_share = n_gf_events / max(len(events_deduped), 1)
                all_cofire_shares.append(co_fire_share)

                if not graded_gf.empty and not gate_fires.empty:
                    gf_graded_g = gf_graded.copy()
                    graded_gf["_is_sur"] = 1
                    gf_graded_g["_is_sur"] = 0
                    combined_gf = pd.concat([graded_gf, gf_graded_g], ignore_index=True)
                    combined_gf["_date_ts"] = pd.to_datetime(combined_gf["date"]).astype(np.int64)
                    gf_prox_results = run_form_analysis(
                        combined_gf, "_is_sur", panel,
                        sector_col="sector",
                        n_bootstrap=n_bootstrap,
                        rng_seed=rng_seed,
                    )
                else:
                    gf_prox_results = {"n_treatment": n_gf_events, "n_control": 0, "effects": [], "era_table": None}

                form_key_gf = f"{cell_key}_gatefire"
                panel_forms[form_key_gf] = {
                    "n_events_total": n_gf_events,
                    "n_events_deduped": n_gf_events,
                    "n_gradable": int(graded_gf["gradable"].sum()) if not graded_gf.empty else 0,
                    "n_treatment": gf_prox_results.get("n_treatment", 0),
                    "n_control":   gf_prox_results.get("n_control", 0),
                    "effects":     gf_prox_results.get("effects", []),
                    "era_table":   gf_prox_results.get("era_table"),
                    "co_fire_share": co_fire_share,
                    "stratum_col": "_is_sur",
                }

                # Update primary cell numbers
                if is_primary and panel == "deep":
                    primary_standalone_n_deduped = n_sa_deduped
                    primary_coiled_n_deduped      = n_coiled_events
                    primary_gatefire_n_deduped     = n_gf_events
                    primary_standalone_results     = sa_results
                    primary_coiled_results         = coiled_results
                    primary_gatefire_results        = gf_prox_results

                    # Compute U&R recall: share of gate fires that have a U&R event nearby
                    if not gate_fires.empty:
                        total_gf = len(gate_fires)
                        n_near = int(gf_prox_mask.sum())
                        primary_ur_recall = n_near / max(total_gf, 1)

        panel_results[panel] = {
            "survivor_stamp": survivor_stamp,
            "forms": panel_forms,
        }

    # Aggregate co-fire share
    aggregate_cofire = float(np.mean(all_cofire_shares)) if all_cofire_shares else 1.0

    # Compute species bar
    species_bar = check_species_bar(
        standalone_results=primary_standalone_results,
        coiled_results=primary_coiled_results,
        gatefire_results=primary_gatefire_results,
        n_standalone=primary_standalone_n_deduped,
        n_coiled=primary_coiled_n_deduped,
        n_gatefire=primary_gatefire_n_deduped,
        co_fire_share=aggregate_cofire,
        coiled_fire_recall=None,  # DEFERRED: W0_BASELINES.md
        ur_recall=primary_ur_recall,
    )

    # Write report
    coiled_fire_recall_note = (
        "COILED-FIRE recall is DEFERRED to this study PR (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). "
        "The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full cycles.py "
        "pipeline is run per-fire over all gate dates. This note serves as the operational DEFERRED stamp. "
        "U&R recall (share of gate fires with U&R event within +/-5 bars) is reported as a proxy."
    )
    nc2_note = (
        "NC-2 full marginality test (coefficient survives eq-band FE after adding entry_quality band "
        "as additional fixed effects) is DEFERRED. The cycles.py pipeline (multi_cycle, mtf_state, "
        "early_state, regime_state) required per-fire is computationally infeasible at this scale. "
        "No offline cache of cand_price/dcl_price exists. NC-2 is DESCRIPTIVE-ONLY until deferred test runs."
    )

    lines: list[str] = []
    report_text = write_report(
        lines,
        panel_results=panel_results,
        species_bar=species_bar,
        coiled_fire_recall_note=coiled_fire_recall_note,
        nc2_note=nc2_note,
        smoke=smoke,
    )

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        log.info("Report written to %s", out_path)

    return {
        "panel_results":  panel_results,
        "species_bar":    species_bar,
        "report_text":    report_text,
        "smoke":          smoke,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    warnings.filterwarnings("ignore", category=FutureWarning)

    ap = argparse.ArgumentParser(description="W2 S-UR Spring Reclaim phase-0 study")
    ap.add_argument("--smoke", action="store_true",
                    help="Smoke run: 50 bootstrap resamples, deep panel only")
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP,
                    help=f"Number of bootstrap resamples (default {N_BOOTSTRAP})")
    ap.add_argument("--panel", nargs="+", choices=["deep", "baskets", "delisted"],
                    default=None, help="Panels to run (default: deep baskets)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path for the markdown report")

    args = ap.parse_args()

    out = args.out or (_REPO_ROOT / "research" / "entry_stack" / "W2_SUR_REPORT.md")

    results = run_study(
        panels=args.panel,
        n_bootstrap=args.n_bootstrap,
        smoke=args.smoke,
        out_path=out,
    )

    # Print brief headline numbers
    sb = results["species_bar"]
    print("\n--- W2 S-UR Species Bar Summary ---")
    print(f"  n_standalone (primary n21/k3/deep): {sb.get('n_standalone', 0)}")
    print(f"  n_coiled     (primary n21/k3/deep): {sb.get('n_coiled', 0)}")
    print(f"  n_gatefire   (primary n21/k3/deep): {sb.get('n_gatefire', 0)}")
    print(f"  Stop5 non-inferiority CI_lo: {sb.get('stop5_ci_lo')}")
    print(f"  Superiority axes: {sb.get('superiority_axes', [])}")
    print(f"  Independence co-fire share: {sb.get('co_fire_share', 'unknown'):.2%}" if isinstance(sb.get('co_fire_share'), float) else f"  Independence co-fire share: {sb.get('co_fire_share', 'unknown')}")
    print(f"  Recall clause (recall >= half COILED-FIRE): {sb.get('recall_clause_met', 'DEFERRED')}")
    print(f"  Report: {out}")


if __name__ == "__main__":
    _main()
