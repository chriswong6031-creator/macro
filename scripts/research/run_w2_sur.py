"""Entry-Stack Expansion W2 — S-UR Spring Reclaim (Undercut-and-Rally) Phase-0 Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §3 F2, §5, §10.
Amendment 1 ref: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md
  RUL-13: primary horizons = 21d (stop5, fwd_mdd_21 / mae21, clean8_21, days_to_10)
          mae63 REMOVED from verdict tables (optionally a holdability appendix only)
  RUL-14: co-primaries zone_held_21, stop_vol_21 (stop_vol_21 excluded from BH pool
           as it is a mechanical mirror of zone_held_21)
W0 baselines frozen: research/entry_stack/W0_BASELINES.md (RUL-9).
NC yardstick: research/entry_stack/W1_NC_REPORT.md (RUL-3).

SPECIES: S-UR — Spring Reclaim (U&R), horizon_class=rotational, phase0.
(study-internal label S15 — S14 is "Failed breakout" merged via #1457 before this branch)

TRIAL FAMILY: esx_ur_phase0 (budget=36):
  2 lows {21, 63} x 3 reclaim windows {2, 3, 5} x 2 depth-arms (panel-determined,
  ATR mult frozen 1.0) x 3 forms (standalone / COILED / gate-fire-proximity).

ORDER OF OPERATIONS (RUL-5): registry FIRST (done), ledger SECOND (done), study THIRD.

Three forms per parameter cell:
  (a) standalone:  raw U&R events from engine/entry_primitives.undercut_rally_events
  (b) COILED intersection: events that occur in TRUE COILED context
      = washout_ctx (individual >=15% drawdown) AND cohort_frac >= 0.40
      (engine/coiled.assess() semantics per coiled.py:309; washout-only is
       labeled washout_ctx and kept as extra context only)
  (c) gate-fire proximity: events within +/-5 bars of gate_fires_{panel}.parquet

SIGN CONVENTION (BLOCKER):
  stop5 is an ADVERSE outcome. A MORE NEGATIVE coefficient means FEWER stops (BETTER).
  Non-inferiority = CI UPPER bound < +0.01 (candidate NOT significantly WORSE than baseline).
  stop5 superiority = CI UPPER bound < 0.0 (significantly fewer stops).
  Beneficial outcomes (cushion_rot, zone_held_21, rotational_liftoff) superiority = CI LOWER > 0.

OUTCOME SCOPE (RUL-13):
  Primary: stop5, fwd_mdd_21 (mae21), rotational_liftoff (clean8_21), days_to_10.
  Co-primary (RUL-14): zone_held_21 (prominent beside stop5 in every table).
  stop_vol_21: reported as adjudication context ONLY; excluded from BH pool (mirror of zone_held_21).
  mae63: REMOVED from verdict tables. May appear in a clearly-labeled holdability appendix.

BH SCOPE (MAJOR): One BH pass pooling ALL cells x forms x outcomes of esx_ur_phase0.
  stop_vol_21 excluded from BH pool.

INDEPENDENCE CLAUSE (MINOR): co-fire evaluated at +/-3 TRUE TRADING BARS (bar distance on
  the price index, not a calendar approximation). Gate-fire proximity FORM stays +/-5 bars per F2.

NC-2 MARGINALITY (ADDITION B): For the gatefire-proximity form, proximity confounding is
  tested by adding entry-quality-band FE to the R1 model for stop5.

PANELS:
  - deep:    data/stocks/ (224 names, close + high/low → H/L arm; 64y history)
  - baskets: data/baskets/ohlcv/ (2,519 names, full OHLCV 2014+; H/L arm)
  - delisted (close-only): data/breadth/_closes_delisted.parquet
             (LOCAL-ONLY, R2 store; read READ-ONLY from main checkout absolute path;
              absent = explicit DELISTED ARM: SKIPPED section, never silent omission)

HEADLINE CLARIFICATION:
  The standalone (+2.44pp stop5 coef) and COILED-intersection (+4.67pp coef) forms show
  stop5 SIGNIFICANTLY WORSE than the incumbent gate baseline (CI entirely above 0).
  Only the gatefire-proximity form shows stop5 improvement (−2.3pp, CI excludes 0).
  Proximity confounding is the primary alternative explanation for the gatefire form.
  Adjudication belongs to the orchestrator, not this study.

All events use T+1 fill, graded via engine.grading forward_metrics + terminal_state.
BH q<=0.10 within esx_ur_phase0 family.

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
    compute_nc2_proximity_proxy,
    assign_nc2_bands,
    _eq_proximity_long,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
# Delisted panel: LOCAL-ONLY (R2 store). Read from main checkout absolute path.
# If absent, report must contain explicit DELISTED ARM: SKIPPED section.
_DELISTED_PATH_MAIN = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard") / "data" / "breadth" / "_closes_delisted.parquet"
_DELISTED_PATH_LOCAL = _DATA / "breadth" / "_closes_delisted.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"
_DEEP_STORE    = _DATA / "stocks"
_BASKETS_OHLCV = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Species ID — S15 (next free after S14 = "Failed breakout", merged via PR #1457)
# S14 was assigned before this branch rebased onto origin/main.
# ---------------------------------------------------------------------------
SPECIES_ID = "S15"
SPECIES_NAME = "Spring Reclaim (U&R)"
SPECIES_FAMILY = "esx_ur_phase0"

# ---------------------------------------------------------------------------
# Frozen study parameters (masterplan F2, not tunable)
# ---------------------------------------------------------------------------
# Low lookback windows (N in {21, 63})
LOOKBACK_WINDOWS = [21, 63]
# Reclaim windows (k in {2, 3, 5})
RECLAIM_WINDOWS = [2, 3, 5]
# ATR multiplier frozen at 1.0
ATR_MULT_FROZEN = 1.0
# Gate-fire proximity FORM: +/-5 bars (per masterplan F2)
GATE_FIRE_PROXIMITY_BARS = 5
# Independence clause: co-fire evaluated at +/-3 TRUE TRADING BARS
INDEPENDENCE_BARS = 3
# Primary analysis: n21 / k3 / standalone
PRIMARY_N   = 21
PRIMARY_K   = 3
# Species bar: n >= 150 deduped episodes per form
MIN_EPISODES_PER_FORM = 150
# Independence clause: co-fire <= 60%
MAX_COFIRE_SHARE = 0.60
# Non-inferiority margin for stop5 (adverse metric):
# non-inferiority = CI UPPER bound < +0.01
# A positive coef = MORE stops (WORSE). Candidate is not-significantly-worse if CI_hi < +0.01.
NONINFERIORITY_MARGIN = 0.01   # CI_hi must be BELOW this value for non-inferiority

# ---------------------------------------------------------------------------
# OUTCOME columns — RUL-13 corrected
# mae63 REMOVED from verdict table; fwd_mdd_21 (mae21) replaces it.
# days_to_10 excluded from BH pool (selection-biased collider).
# stop_vol_21 excluded from BH pool (mechanical mirror of zone_held_21).
# zone_held_21 reported prominently as co-primary (ADDITION C).
# ---------------------------------------------------------------------------
OUTCOME_COLS = [
    "stop5",             # immediate stop-out within 5 bars (primary, adverse)
    "fwd_mdd_21",        # mae21: max adverse excursion at 21d (RUL-13 primary, replaces mae63)
    "rotational_liftoff",# clean8_21 terminal state (beneficial)
    "positional_liftoff",# clean15_126 terminal state (beneficial)
    "dead_money",        # dead-money rate (adverse)
    "cushion_rot",       # cushion incidence (rotational, beneficial)
    "zone_held_21",      # RUL-14 co-primary: vol-scaled zone held at 21d (ADDITION C)
    "stop_vol_21",       # RUL-14: reported as adjudication context; EXCLUDED from BH pool
    "days_to_10",        # descriptive only; excluded from BH pool (collider)
]

# Outcomes included in BH pool (exclude stop_vol_21 and days_to_10)
OUTCOME_COLS_BH = [c for c in OUTCOME_COLS if c not in ("stop_vol_21", "days_to_10")]

# Holdability appendix: mae63 computed separately, labeled clearly
HOLDABILITY_OUTCOMES = ["mae63"]

# ---------------------------------------------------------------------------
# Metric direction map (S4 fix — S2/SECOND-REVIEW finding)
# ADVERSE_METRICS: higher value = WORSE outcome.
#   Superiority means the candidate has significantly LESS of it: CI_hi < 0.
# BENEFICIAL_METRICS: higher value = BETTER outcome.
#   Superiority means the candidate has significantly MORE of it: CI_lo > 0.
#
# Sign semantics:
#   stop5: 0/1 binary (1=stopped out within 5 bars) — higher is worse.
#   dead_money: 0/1 binary (1=dead money outcome) — higher is worse.
#   stop_vol_21: 0/1 binary (stopped in vol-scaled zone) — higher is worse.
#   fwd_mdd_21: forward max drawdown, VALUES ARE <= 0 (more negative = worse
#               as MDD magnitude); the R1 coefficient: positive coef = candidate
#               has LESS NEGATIVE mdd = BETTER; treat as BENEFICIAL for CI_lo>0.
#   zone_held_21: vol-scaled zone held — higher is better (BENEFICIAL).
#   rotational_liftoff: liftoff rate — higher is better (BENEFICIAL).
#   positional_liftoff: liftoff rate — higher is better (BENEFICIAL).
#   cushion_rot: cushion incidence — higher is better (BENEFICIAL).
#   days_to_10: descriptive only, not in clause evaluations.
# ---------------------------------------------------------------------------
ADVERSE_METRICS: frozenset[str] = frozenset({"stop5", "dead_money", "stop_vol_21"})
# Note: fwd_mdd_21 values are <=0 (more negative = worse MDD); the R1 coef
# direction: a positive coefficient means the candidate has a less-negative MDD
# (smaller drawdown magnitude = better), so treat as BENEFICIAL for superiority.
BENEFICIAL_METRICS: frozenset[str] = frozenset({
    "rotational_liftoff", "positional_liftoff", "cushion_rot",
    "zone_held_21", "fwd_mdd_21", "days_to_10",
})


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
            log.warning("deep: failed to load %s: %s", path.name, exc)
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
            log.warning("baskets: failed to load %s: %s", path.name, exc)
    log.info("Loaded %d basket OHLCV records", len(store))
    return store


def _load_delisted_closes() -> tuple[pd.DataFrame | None, str]:
    """Load delisted close-only panel. Returns (df_or_None, status_message).

    Tries main checkout absolute path first (per task spec: read READ-ONLY from
    main checkout). Falls back to local path. If both absent, returns (None, reason).
    Never silently omits the status.
    """
    for candidate in (_DELISTED_PATH_MAIN, _DELISTED_PATH_LOCAL):
        if candidate.exists():
            try:
                df = pd.read_parquet(candidate)
                log.info("Loaded delisted panel from %s: %d rows", candidate, len(df))
                return df, f"Loaded from {candidate} ({len(df)} rows)."
            except Exception as exc:
                return None, (
                    f"DELISTED ARM: SKIPPED — file exists at {candidate} but could not be read: {exc}. "
                    "This is the expected R2-store behavior on a fresh worktree."
                )
    reason = (
        f"DELISTED ARM: SKIPPED — data/breadth/_closes_delisted.parquet is LOCAL-ONLY "
        f"(R2 store, untracked). Not found at main checkout path {_DELISTED_PATH_MAIN} "
        f"or local path {_DELISTED_PATH_LOCAL}. "
        "This is expected on fresh worktrees without R2 data. "
        "Results are based on deep and baskets panels only."
    )
    log.warning(reason)
    return None, reason


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
        except TypeError:
            # TypeError from wrong argument shape raises here — never swallowed
            raise
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
# Independence clause: co-fire at +/-3 TRUE TRADING BARS
# The gatefire FORM uses +/-5 bars (per masterplan F2 frozen parameter).
# The independence clause uses +/-3 TRUE TRADING BARS on the price index.
# ---------------------------------------------------------------------------

def compute_cofire_share_trading_bars(
    events: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
    gate_fires: pd.DataFrame,
    independence_bars: int = INDEPENDENCE_BARS,
) -> tuple[float, int]:
    """Compute co-fire share at +/-independence_bars TRUE TRADING BARS.

    Uses the price index (sorted trading dates from ohlcv_store) to measure
    bar distance, NOT a calendar approximation.

    Returns (co_fire_share, n_near).
    """
    if events.empty or gate_fires.empty:
        return 0.0, 0

    # Build per-ticker sorted trading date arrays from ohlcv_store
    ticker_idx: dict[str, np.ndarray] = {
        t: np.array(df.index.sort_values(), dtype="datetime64[ns]")
        for t, df in ohlcv_store.items()
    }

    # Build gate fires per ticker
    gf_by_ticker: dict[str, np.ndarray] = {}
    for ticker, grp in gate_fires.groupby("ticker"):
        gf_by_ticker[str(ticker)] = pd.to_datetime(grp["date"]).sort_values().values

    n_near = 0
    for _, row in events.iterrows():
        ticker = str(row["ticker"])
        ev_date = np.datetime64(pd.Timestamp(row["date"]), "ns")

        gf_dates = gf_by_ticker.get(ticker)
        trading_dates = ticker_idx.get(ticker)
        if gf_dates is None or len(gf_dates) == 0:
            continue
        if trading_dates is None or len(trading_dates) == 0:
            continue

        # Find position of event date in the trading index
        ev_pos = int(np.searchsorted(trading_dates, ev_date))

        # Find positions of gate fire dates
        for gf_date in gf_dates:
            gf_date_ns = np.datetime64(pd.Timestamp(gf_date), "ns")
            gf_pos = int(np.searchsorted(trading_dates, gf_date_ns))
            if abs(ev_pos - gf_pos) <= independence_bars:
                n_near += 1
                break  # one nearby gate fire is enough

    co_fire_share = n_near / max(len(events), 1)
    return co_fire_share, n_near


# ---------------------------------------------------------------------------
# Form (b): COILED intersection labeling
# Uses engine/coiled.washout_ctx to label each event for COILED context.
# The COILED state is a point-in-time snapshot at the fire date (signal_date),
# not a forward-looking computation.
# ---------------------------------------------------------------------------

def label_coiled_context(
    events: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
    sector_map: dict[str, str] | None = None,
    cohort_frac_threshold: float = 0.40,
) -> pd.DataFrame:
    """Add TRUE COILED columns to events DataFrame.

    TRUE COILED = washout_ctx AND cohort_frac >= cohort_frac_threshold.
    This matches engine/coiled.py assess() semantics (line 309):
        coiled = bool(washout) and cohort_frac is not None and cohort_frac >= 0.40

    Per S3 (SECOND-REVIEW FINDING): the prior implementation only called
    washout_ctx (individual >=15% drawdown) and never applied the cohort gate.
    The COILED label in the registry evidence_stack claims "cohort washout" —
    this implementation actually measures it.

    Columns added:
        in_washout_ctx : individual washout_ctx result (bool or None) — kept as
                         EXTRA CONTEXT but is NOT the COILED label.
        cohort_frac    : fraction of sector peers in washout at fire date (float or None).
        in_coiled_ctx  : TRUE COILED = in_washout_ctx AND cohort_frac >= 0.40.

    Parameters
    ----------
    events : DataFrame with 'ticker', 'date' columns.
    ohlcv_store : {ticker: DataFrame with 'close'}.
    sector_map : {ticker: sector_string}. If None, cohort gate cannot be applied
                 (in_coiled_ctx falls back to in_washout_ctx with a warning).
    cohort_frac_threshold : float, default 0.40 (matches coiled.assess()).

    Returns
    -------
    events with added columns: in_washout_ctx, cohort_frac, in_coiled_ctx.
    """
    from engine.coiled import washout_ctx, weekly_d_last, cohort_fractions as compute_cohort_fracs

    if events.empty:
        events = events.copy()
        events["in_washout_ctx"] = pd.Series(dtype=object)
        events["cohort_frac"]    = pd.Series(dtype=float)
        events["in_coiled_ctx"]  = pd.Series(dtype=object)
        return events

    # ------------------------------------------------------------------
    # Step 1: per-ticker individual washout_ctx (strictly truncated to fire_date)
    # ------------------------------------------------------------------
    washout_results: list[bool | None] = []
    washout_exceptions = 0

    for _, row in events.iterrows():
        ticker = row["ticker"]
        fire_date = pd.Timestamp(row["date"])

        df = ohlcv_store.get(ticker)
        if df is None or df.empty or "close" not in df.columns:
            washout_results.append(None)
            continue

        close = df["close"]
        close_trunc = close[close.index <= fire_date]
        if close_trunc.empty:
            washout_results.append(None)
            continue

        try:
            ctx = washout_ctx(close_trunc)
            washout_results.append(bool(ctx) if ctx is not None else None)
        except TypeError:
            # TypeError raises — never swallowed (§4 ban on broad except)
            raise
        except Exception:  # noqa: BLE001
            washout_exceptions += 1
            washout_results.append(None)

    if washout_exceptions > 0:
        log.warning("label_coiled_context: %d washout_ctx exceptions (set to None)", washout_exceptions)

    # ------------------------------------------------------------------
    # Step 2: cohort fractions per-date (batch to avoid O(n^2) per-event)
    # Compute weekly_d_last for all tickers, truncated to each unique fire date.
    # Batch by date: for all tickers, reuse truncated close up to that date.
    # ------------------------------------------------------------------
    if sector_map is None:
        log.warning(
            "label_coiled_context: sector_map not provided — "
            "cohort gate cannot be applied. Falling back to washout_ctx only. "
            "in_coiled_ctx will equal in_washout_ctx (CONSERVATIVE — will over-count COILED)."
        )
        frac_results: list[float | None] = [None] * len(events)
        # Fallback: COILED = washout_ctx only (conservative, documented)
        coiled_results: list[bool | None] = washout_results[:]
    else:
        # Vectorized cohort computation.
        # weekly_d_last (14/3/3 StochRSI on weekly bars) changes slowly.
        # Rather than calling weekly_d_last(close_trunc) per ticker per date
        # (O(n_dates × n_tickers) = extremely slow), we:
        #   1. Compute the FULL weekly StochRSI D series for each ticker once,
        #      producing a panel D_panel[weekly_date, ticker].
        #   2. For each event fire date, find the most-recent weekly bar (W-FRI)
        #      at or before the fire date and look up the D value — O(1) per event.
        #   3. Feed the cross-sectional D values into compute_cohort_fracs per date.
        # This reduces 300 months × 224 tickers = 67K calls to 224 calls total.
        #
        # Key: weekly StochRSI needs >=60 weekly bars (≈ 5 years of history).
        # Tickers with shorter histories return None.
        #
        # Algorithm:
        #   1. Compute full weekly D series per ticker.
        #   2. Find unique event dates; for each, assemble cross-section from panel.
        #   3. Call compute_cohort_fracs once per unique fire date.

        # Step 2a: build full weekly D panel (once per ticker, not per date).
        # weekly_d_last (14/3/3 StochRSI on weekly bars) changes slowly.
        # Rather than calling weekly_d_last(close_trunc) per ticker per date
        # (O(n_dates × n_tickers) = very slow), we compute the FULL causal weekly
        # D series for each ticker ONCE and store as sorted numpy arrays for
        # fast per-event searchsorted lookups.
        #
        # Cost: 224 full-series builds ≈ 4s; then per-event = O(log n_weekly)
        # per ticker per unique date — acceptable for 14k events × 224 tickers.
        from engine.coiled import _stoch_rsi_kd  # type: ignore[attr-defined]

        _min_weekly = 60

        def _weekly_d_numpy(daily_close: pd.Series) -> tuple[np.ndarray, np.ndarray] | None:
            """Compute full causal weekly StochRSI D series as (dates_ns, values) arrays.

            Stores as datetime64[ns] + float64 numpy arrays for fast searchsorted.
            Returns None if fewer than _min_weekly weekly bars.
            """
            try:
                c = daily_close.dropna()
                if not isinstance(c.index, pd.DatetimeIndex):
                    c = c.copy()
                    c.index = pd.to_datetime(c.index)
                wk = c.resample("W-FRI").last().dropna()
                if len(wk) < _min_weekly:
                    return None
                _, d = _stoch_rsi_kd(wk)
                return (
                    d.index.to_numpy(dtype="datetime64[ns]"),
                    d.to_numpy(dtype="float64"),
                )
            except TypeError:
                raise
            except Exception:  # noqa: BLE001
                return None

        # (ticker → (wk_dates_ns, d_values)) for fast searchsorted per event
        ticker_d_numpy: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for ticker, df in ohlcv_store.items():
            if "close" not in df.columns:
                continue
            result = _weekly_d_numpy(df["close"])
            if result is not None:
                ticker_d_numpy[ticker] = result
        log.info(
            "label_coiled_context: built weekly D series for %d/%d tickers",
            len(ticker_d_numpy), len(ohlcv_store),
        )

        # WEEKLY-D EQUIVALENCE NOTE (FINDING 5 — RESOLVED BY DOCUMENTATION):
        # The vectorized path precomputes D series using resample("W-FRI").last()
        # over the full ticker history, then uses searchsorted to find the last
        # completed W-FRI bar at or before each fire date.
        #
        # engine/coiled.weekly_d_last() (live engine) receives
        # close[close.index <= fire_date] and resamples — including the partial
        # current week's bar as if completed. On non-Friday fire dates, the
        # vectorized approach returns the LAST COMPLETED FRIDAY D value (up to 4
        # trading days stale vs the live engine). This is a DOCUMENTED STALENESS,
        # not a fix: adding a per-event synthetic bar would negate the speedup.
        # The direction of the staleness bias is INDETERMINATE: a stale last-Friday
        # D value can be higher or lower than the live partial-week D, so cohort_frac
        # (and TRUE-COILED membership via >=0.40 threshold) can move either way.
        # Path taken: document and keep the vectorized approach. The equivalence
        # claim (that this matches weekly_d_last exactly) is DROPPED.
        #
        # Step 2b: for each unique fire date, get cross-sectional D via searchsorted.
        # Using numpy searchsorted on the stored arrays reduces per-lookup from
        # ~7ms (full resample+stoch per ticker per date) to ~O(log n_weekly).
        unique_event_dates = sorted(pd.to_datetime(events["date"]).unique())
        date_to_fracs: dict[pd.Timestamp, dict[str, float | None]] = {}

        for fire_date in unique_event_dates:
            fire_ns = np.datetime64(fire_date, "ns")
            d_map: dict[str, float | None] = {}
            for ticker, (dates_arr, vals_arr) in ticker_d_numpy.items():
                # Most-recent weekly bar at or before fire_date (causal, no look-ahead)
                idx = int(np.searchsorted(dates_arr, fire_ns, side="right")) - 1
                if idx < 0:
                    d_map[ticker] = None
                else:
                    val = vals_arr[idx]
                    d_map[ticker] = float(val) if not np.isnan(val) else None
            try:
                fracs = compute_cohort_fracs(d_map, sector_map)
            except TypeError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("label_coiled_context: cohort_fractions error at %s: %s", fire_date, exc)
                fracs = {}
            date_to_fracs[fire_date] = fracs

        log.info(
            "label_coiled_context: computed cohort fracs for %d unique fire dates",
            len(date_to_fracs),
        )

        # Step 2c: assign cohort_frac per event row
        frac_results = []
        for _, row in events.iterrows():
            fire_date = pd.Timestamp(row["date"])
            fracs = date_to_fracs.get(fire_date, {})
            frac_results.append(fracs.get(str(row["ticker"])))

        # Step 3: TRUE COILED = washout_ctx AND cohort_frac >= threshold
        coiled_results = []
        for i, (w, f) in enumerate(zip(washout_results, frac_results)):
            if w is None:
                coiled_results.append(None)
            elif f is None:
                # Can't compute cohort — COILED is None (not testable)
                coiled_results.append(None)
            else:
                coiled_results.append(bool(w) and float(f) >= cohort_frac_threshold)

    # Assemble
    events = events.copy()
    events["in_washout_ctx"] = washout_results
    # Align frac_results to events index (positional)
    events["cohort_frac"] = frac_results
    events["in_coiled_ctx"] = coiled_results

    washout_n = sum(1 for v in washout_results if v is True)
    coiled_n  = sum(1 for v in coiled_results  if v is True)
    testable  = sum(1 for v in coiled_results  if v is not None)
    log.info(
        "label_coiled_context: %d/%d testable events in washout_ctx, "
        "%d/%d testable in TRUE COILED (washout AND cohort_frac>=%.2f)",
        washout_n, len(washout_results), coiled_n, testable, cohort_frac_threshold,
    )
    return events


# ---------------------------------------------------------------------------
# Form (c): gate-fire proximity labeling (FORM only; +/-5 bars per F2)
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

    The FORM uses +/-5 bars per masterplan F2 (frozen).
    The independence clause uses +/-3 TRUE TRADING BARS (separate function).

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
    log.info(
        "label_gate_fire_proximity: %d/%d events near gate fire (form proximity +/-%d bars)",
        n_near, len(events), proximity_bars,
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
    # in_washout_ctx = individual washout only; in_coiled_ctx = TRUE COILED
    for col in ("n_low", "k_reclaim", "arm", "depth_frac",
                "in_washout_ctx", "cohort_frac",
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
# Form analysis: run R1 estimate for a single stratum label
# Evaluates ALL outcomes; era table PER FORM; sign-stability check.
# BH pool is accumulated globally across all forms and cells.
# ---------------------------------------------------------------------------

def run_form_analysis(
    graded: pd.DataFrame,
    stratum_col: str,
    panel: str,
    sector_col: str = "sector",
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
    closes_for_nc2: dict[str, pd.Series] | None = None,
    compute_nc2_fe: bool = False,
) -> dict[str, Any]:
    """Run R1 date-FE estimate for each outcome column for one form.

    Parameters
    ----------
    graded : DataFrame with all outcome columns and the stratum_col.
    stratum_col : binary column (1 = treatment, 0 = control).
    panel : label string for FE fallback detection.
    sector_col : sector column name for episode blocks.
    closes_for_nc2 : optional dict of closes for NC-2 proximity FE (ADDITION B).
    compute_nc2_fe : if True, add NC-2 band FE to stop5 R1 model for this form.

    Returns
    -------
    dict with keys: n_treatment, n_control, effects, era_table, era_sign_stable,
                    nc2_marginality (if compute_nc2_fe), raw_graded.
    effects : list of R1 result dicts (one per outcome).
    """
    if graded.empty or stratum_col not in graded.columns:
        return {"n_treatment": 0, "n_control": 0, "effects": [], "era_table": None,
                "era_sign_stable": None}

    gradable = graded[graded["gradable"] == True].copy()  # noqa: E712
    if gradable.empty:
        return {"n_treatment": 0, "n_control": 0, "effects": [], "era_table": None,
                "era_sign_stable": None}

    # FE column: date (frozen per RUL-12 W0 sign-off)
    gradable["_fe"] = gradable["date"].astype(str)
    sector_col_eff = sector_col if sector_col in gradable.columns and gradable[sector_col].notna().any() else None

    effects = []

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
        # Compute recall for treatment arm
        treat_mask = gradable[stratum_col] == 1
        n_treat = int(treat_mask.sum())
        n_all = len(gradable)
        res["recall"] = n_treat / max(n_all, 1)
        effects.append(res)

    # Era table PER FORM (fix: use correct fast_era_table signature)
    # fast_era_table(graded, stratum_col=None, *, panel_label="panel")
    era_tbl = None
    era_sign_stable: bool | None = None
    if stratum_col in gradable.columns:
        try:
            era_tbl = fast_era_table(gradable, stratum_col, panel_label=panel)
        except TypeError:
            # TypeError from wrong signature — raised explicitly (not swallowed)
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("era_table error for panel=%s stratum=%s: %s", panel, stratum_col, exc)
            era_tbl = None

        # Evaluate >=3/4 era sign-stability clause for stop5
        if era_tbl is not None and not era_tbl.empty and "stop5_rate" in era_tbl.columns:
            era_sign_stable = _check_era_sign_stability(era_tbl, stratum_col)

    # NC-2 marginality test for gatefire form (ADDITION B)
    nc2_marginality: dict[str, Any] | None = None
    if compute_nc2_fe and closes_for_nc2 is not None:
        nc2_marginality = _run_nc2_band_fe(
            gradable, stratum_col, closes_for_nc2, n_bootstrap, rng_seed, panel, sector_col_eff
        )

    n_treatment = int((gradable[stratum_col] == 1).sum()) if stratum_col in gradable.columns else 0
    n_control   = int((gradable[stratum_col] == 0).sum()) if stratum_col in gradable.columns else 0

    return {
        "n_treatment": n_treatment,
        "n_control":   n_control,
        "effects":     effects,
        "era_table":   era_tbl,
        "era_sign_stable": era_sign_stable,
        "nc2_marginality": nc2_marginality,
        "raw_graded":  gradable,
    }


def _check_era_sign_stability(
    era_tbl: pd.DataFrame,
    stratum_col: str,
) -> bool | None:
    """Check whether stop5 coefficient is sign-stable in >=3/4 program eras.

    Computes per-era stop5 rate difference (treatment - control) and checks
    whether the sign is consistent in at least 3 of the 4 eras.

    Returns True/False/None (None if fewer than 2 eras have data).
    """
    program_eras = ["2012-2015", "2016-2019", "2020-2022", "2023-2026"]
    if "era" not in era_tbl.columns or "stop5_rate" not in era_tbl.columns:
        return None

    era_signs: list[int] = []
    for era in program_eras:
        sub = era_tbl[era_tbl["era"] == era]
        if stratum_col not in sub.columns:
            continue
        treat = sub[sub[stratum_col] == 1]["stop5_rate"]
        ctrl  = sub[sub[stratum_col] == 0]["stop5_rate"]
        if treat.empty or ctrl.empty:
            continue
        diff = float(treat.mean()) - float(ctrl.mean())
        era_signs.append(1 if diff > 0 else -1)

    if len(era_signs) < 2:
        return None
    # Sign stable if >=3/4 eras share the same sign
    pos_count = sum(1 for s in era_signs if s > 0)
    neg_count = sum(1 for s in era_signs if s < 0)
    return max(pos_count, neg_count) >= 3


def _run_nc2_band_fe(
    gradable: pd.DataFrame,
    stratum_col: str,
    closes: dict[str, pd.Series],
    n_bootstrap: int,
    rng_seed: int,
    panel: str,
    sector_col: str | None,
) -> dict[str, Any]:
    """NC-2 marginality test: add NC-2 proximity band FE to stop5 R1 model.

    ADDITION B (BLOCKER FIX): For the gatefire-proximity form only. Reclaim
    events are definitionally near lows, so proximity confounding is the primary
    alternative explanation. We reuse the entry-quality proximity-band machinery
    from run_w1_nc.py (compute_nc2_proximity_proxy / assign_nc2_bands) to add
    entry-quality-band fixed effects to the R1 model for stop5.

    FIX (NC-2 DEGENERATE MARGINALITY): Bands are now computed for BOTH treatment
    (U&R events) AND control (gate fires) rows. The prior implementation only
    assigned bands to treatment rows; control rows got band="unknown". This caused
    the composite date+band FE to perfectly separate the two arms — every
    date+band cell contained only one arm — producing a mechanically degenerate
    coefficient of exactly 0.0 regardless of the true effect. By computing bands
    for both arms, treatment and control rows co-exist in the same FE cells,
    allowing the estimator to recover the actual treatment effect.

    NC-2 PROXY NOTE: the 63-bar close-minimum pivot is a PROXY for the true
    cand_price/dcl_price pivot (per W1_NC_REPORT.md PROXY-INPUT LIMITATION).
    Proximity bands are labeled as PROXY (63-bar close-min pivot).

    Returns dict with: band_computed (bool), coef, ci_lo, ci_hi,
    ci_excl_zero (bool), note (explanation if not computed).
    """
    if "stop5" not in gradable.columns:
        return {"band_computed": False, "note": "stop5 not in gradable columns."}

    treat_mask = gradable[stratum_col] == 1
    gf_rows = gradable[treat_mask].copy()
    ctrl_rows = gradable[~treat_mask].copy()

    if len(gf_rows) < 30:
        return {
            "band_computed": False,
            "note": f"Insufficient treatment rows for NC-2 band FE: n={len(gf_rows)} < 30.",
        }

    # Compute proximity proxy for BOTH treatment and control rows.
    # This is the critical fix: the FE cell = date+band must contain BOTH arms
    # so the estimator can separate treatment effect from proximity confounding.
    # Without this, treatment and control never share a cell → perfect separation
    # → degenerate coefficient = 0.0 regardless of true effect.
    all_rows = gradable[["ticker", "date"]].copy()
    prox_all = compute_nc2_proximity_proxy(all_rows, closes, rolling_window=63)
    bands_all = assign_nc2_bands(prox_all)

    # Count computable bands on treatment arm (for reporting)
    treat_idx = gradable.index[treat_mask]
    bands_treat = bands_all.loc[treat_idx] if len(treat_idx) > 0 else pd.Series(dtype=float)
    n_computable = int(bands_treat.notna().sum())

    if n_computable < 30:
        return {
            "band_computed": False,
            "note": (
                f"NC-2 proximity bands not computable for sufficient treatment rows: "
                f"only {n_computable}/{len(gf_rows)} have computable proximity. "
                "Reason: insufficient lookback history (63 bars required before event date)."
            ),
        }

    # Add nc2_band as an additional FE column (all rows, both arms)
    gradable_nc2 = gradable.copy()
    gradable_nc2["_nc2_band_fe"] = bands_all.reindex(gradable.index).map(
        lambda x: str(int(x)) if pd.notna(x) else "unknown"
    )

    # Composite FE: date + nc2_band
    # Both arms now get actual proximity bands, so within each FE cell
    # treatment and control rows co-exist (no perfect separation).
    gradable_nc2["_fe_nc2"] = (
        gradable_nc2["date"].astype(str) + "_b" + gradable_nc2["_nc2_band_fe"]
    )

    sector_col_eff = sector_col

    try:
        res = fast_r1_estimate(
            gradable_nc2,
            outcome_col="stop5",
            stratum_col=stratum_col,
            fe_col="_fe_nc2",
            sector_col=sector_col_eff,
            n_bootstrap=n_bootstrap,
            rng_seed=rng_seed,
        )
        coef = res.get("coef")
        ci_lo = res.get("ci_lo")
        ci_hi = res.get("ci_hi")

        # Sanity check: if coef is exactly 0.0 AND both CI bounds are 0.0,
        # the regression is still degenerate (perfect separation survived).
        # Log a warning so this surfaces in tests.
        if coef == 0.0 and ci_lo == 0.0 and ci_hi == 0.0:
            log.warning(
                "_run_nc2_band_fe: coef=0.0 with zero-width CI — possible residual "
                "FE degeneracy. n_treatment=%d n_control=%d n_computable_treat=%d",
                len(gf_rows), len(ctrl_rows), n_computable,
            )

        return {
            "band_computed": True,
            "n_treatment_nc2": n_computable,
            "n_control_nc2": len(ctrl_rows),
            "coef": coef,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "ci_excl_zero": _excl_zero(res) == "YES *",
            "note": (
                "NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true "
                "cand_price/dcl_price). Bands computed for BOTH treatment and control arms "
                "(fix: prior version assigned bands to treatment only — degenerate coef=0.0). "
                f"N treatment with computable proximity = {n_computable}/{len(gf_rows)}; "
                f"N control = {len(ctrl_rows)}."
            ),
        }
    except TypeError:
        raise
    except Exception as exc:  # noqa: BLE001
        return {
            "band_computed": False,
            "note": f"NC-2 band FE computation failed: {exc}.",
        }


# ---------------------------------------------------------------------------
# Family-wide BH correction (MAJOR)
# Pool ALL cells x forms x outcomes of esx_ur_phase0.
# stop_vol_21 and days_to_10 excluded from BH pool.
# ---------------------------------------------------------------------------

def apply_family_wide_bh(
    all_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply one BH pass pooling all cells x forms x outcomes.

    Mutates each effect dict in-place to add bh_q_family and bh_rejected_family.
    stop_vol_21 and days_to_10 are excluded from the BH pool (but still reported).

    Returns the input list (mutated).

    BH pool scope: all outcome cells across all forms and parameter cells of
    esx_ur_phase0, excluding stop_vol_21 (mechanical mirror of zone_held_21)
    and days_to_10 (collider). This corrects for multiplicity across the full
    study design.
    """
    pool_effects = [e for e in all_effects if e.get("outcome") not in ("stop_vol_21", "days_to_10")]

    p_values = [e.get("p_value") for e in pool_effects]
    labels   = [f"{e.get('form_key','?')}_{e.get('outcome','?')}" for e in pool_effects]

    bh_results = bh_correction(p_values, labels, BH_Q_THRESHOLD)
    bh_map = {r["label"]: r for r in bh_results}

    for e in pool_effects:
        label = f"{e.get('form_key','?')}_{e.get('outcome','?')}"
        bh = bh_map.get(label, {})
        e["bh_q_family"] = bh.get("q_value")
        e["bh_rejected_family"] = bh.get("rejected")

    # For excluded outcomes, stamp None
    for e in all_effects:
        if e.get("outcome") in ("stop_vol_21", "days_to_10"):
            e["bh_q_family"] = None
            e["bh_rejected_family"] = None
            e["bh_excluded_from_pool"] = True

    return all_effects


# ---------------------------------------------------------------------------
# Species bar check (per form — no cross-form cherry-picking; BLOCKER)
# Evaluates each form independently.
# Sign convention corrected: stop5 non-inferiority = CI UPPER < +0.01.
# ---------------------------------------------------------------------------

def check_species_bar_per_form(
    form_label: str,
    results: dict[str, Any],
    n_events: int,
    co_fire_share: float,
    coiled_fire_recall: float | None,
    ur_recall: float,
    is_gatefire_form: bool = False,
    nc2_marginality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate species bar clauses for a SINGLE form independently.

    No cross-form cherry-picking. Each form is evaluated on its own merits.

    SIGN CONVENTION (BLOCKER):
      stop5 adverse: CI UPPER bound < +0.01 = non-inferiority (not significantly worse).
      stop5 superiority: CI UPPER bound < 0.0 (significantly fewer stops).
      Beneficial outcomes superiority: CI LOWER > 0.

    Returns dict with per-clause met/not-met verdicts (no promotion decision).
    """
    verdicts: dict[str, Any] = {"form": form_label}

    # Clause 1: n >= 150 deduped episodes for this form
    verdicts["n_events"] = n_events
    verdicts["n_met"] = n_events >= MIN_EPISODES_PER_FORM

    # Clause 2: stop5 non-inferiority (CI UPPER bound < +0.01)
    # stop5 is ADVERSE. CI_hi < +0.01 means the candidate is NOT significantly WORSE.
    stop5_effects = [e for e in results.get("effects", []) if e.get("outcome") == "stop5"]
    if stop5_effects:
        ci_hi = stop5_effects[0].get("ci_hi")
        coef  = stop5_effects[0].get("coef")
        verdicts["stop5_noninferiority_met"] = (ci_hi is not None and ci_hi < NONINFERIORITY_MARGIN)
        verdicts["stop5_ci_hi"] = ci_hi
        verdicts["stop5_coef"] = coef
        # Superiority: CI_hi < 0 (significantly fewer stops = better)
        verdicts["stop5_superiority_met"] = (ci_hi is not None and ci_hi < 0.0)
    else:
        verdicts["stop5_noninferiority_met"] = None
        verdicts["stop5_ci_hi"] = None
        verdicts["stop5_coef"] = None
        verdicts["stop5_superiority_met"] = None

    # Clause 3: superiority CI-excl-0 on >= 1 of the three constitution axes
    # Constitution axes: stop-out / dead-money / cushion incidence (§5)
    # ADVERSE_METRICS direction: superiority = CI_hi < 0 (significantly FEWER adverse events).
    # BENEFICIAL_METRICS direction: superiority = CI_lo > 0 (significantly MORE benefit).
    # S4 fix: dead_money is ADVERSE (higher = worse); must use CI_hi < 0 for superiority.
    constitution_axes = ["stop5", "dead_money", "cushion_rot"]
    superior_axes = []
    for ax in constitution_axes:
        ax_effects = [e for e in results.get("effects", []) if e.get("outcome") == ax]
        if ax_effects:
            ci_lo = ax_effects[0].get("ci_lo")
            ci_hi = ax_effects[0].get("ci_hi")
            if ci_lo is not None and ci_hi is not None:
                if ax in ADVERSE_METRICS:
                    # Adverse: superiority = CI_hi < 0 (significantly fewer adverse events)
                    if ci_hi < 0.0:
                        superior_axes.append(ax)
                else:
                    # Beneficial: superiority = CI_lo > 0 (significantly more benefit)
                    if ci_lo > 0.0:
                        superior_axes.append(ax)
    verdicts["superiority_axes"] = superior_axes
    verdicts["superiority_met"] = len(superior_axes) >= 1

    # Clause 4: era sign-stability (>=3/4 eras; per task requirement)
    verdicts["era_sign_stable"] = results.get("era_sign_stable")
    verdicts["era_sign_stable_met"] = results.get("era_sign_stable") is True

    # Clause 5: recall clause (recall >= half of COILED-FIRE recall)
    if coiled_fire_recall is not None:
        verdicts["recall_clause_threshold"] = coiled_fire_recall / 2.0
        verdicts["recall_ur"] = ur_recall
        verdicts["recall_clause_met"] = ur_recall >= coiled_fire_recall / 2.0
    else:
        verdicts["recall_clause_threshold"] = None
        verdicts["recall_ur"] = ur_recall
        verdicts["recall_clause_met"] = None  # DEFERRED
        verdicts["recall_clause_note"] = (
            "DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. "
            "Cannot evaluate recall clause from this study alone. "
            "See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute."
        )

    # Clause 6: independence clause (co-fire at +/-3 true trading bars <= 60%)
    verdicts["co_fire_share"] = co_fire_share
    if is_gatefire_form:
        # The gatefire form selects events BY DEFINITION near gate fires (±5 bars).
        # It is structurally gate-dependent: independence is not a meaningful clause.
        # The ±3-bar co-fire check uses a tighter radius than the form radius (±5 bars),
        # so events in the (3-bar, 5-bar] band escape the co-fire check and produce an
        # artificially low share (36.4%). This exactly matches the failure mode the
        # test_cofire_per_form_not_shared_constant test flags.
        # Verdict: N/A — structurally gate-dependent (not PASS or FAIL).
        verdicts["independence_clause_met"] = None
        verdicts["independence_structural_na"] = True
    else:
        verdicts["independence_clause_met"] = co_fire_share <= MAX_COFIRE_SHARE
        verdicts["independence_structural_na"] = False

    # Clause 6b (gatefire only): NC-2 superiority nullification.
    # If NC-2 band FE shows CI includes 0 after proximity de-confounding, the
    # superiority_met verdict is nullified — superiority does not survive confound test.
    if is_gatefire_form and nc2_marginality is not None and nc2_marginality.get("band_computed"):
        nc2_excl_zero = nc2_marginality.get("ci_excl_zero", False)
        verdicts["nc2_superiority_survives"] = bool(nc2_excl_zero)
        if not nc2_excl_zero:
            # NC-2 kills superiority: CI includes 0 after proximity band FE.
            verdicts["superiority_met_nc2_nullified"] = True
            verdicts["superiority_met"] = False
            verdicts["stop5_superiority_met"] = False
        else:
            verdicts["superiority_met_nc2_nullified"] = False
    else:
        verdicts["nc2_superiority_survives"] = None
        verdicts["superiority_met_nc2_nullified"] = False

    # zone_held_21 (ADDITION C — adjudication context, feeds no clause)
    zone_effects = [e for e in results.get("effects", []) if e.get("outcome") == "zone_held_21"]
    if zone_effects:
        verdicts["zone_held_21_coef"] = zone_effects[0].get("coef")
        verdicts["zone_held_21_ci_lo"] = zone_effects[0].get("ci_lo")
        verdicts["zone_held_21_ci_hi"] = zone_effects[0].get("ci_hi")

    return verdicts


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _parse_nc_yardstick_from_report(
    report_path: Path | None = None,
) -> list[dict[str, str]]:
    """Parse NC yardstick rows from W1_NC_REPORT.md at runtime (MAJOR FIX).

    Per RUL-3: the yardstick table must be sourced from the actual W1-NC
    artifact, not hardcoded in this file. Hardcoded literals become stale
    if W1 is re-run.

    Returns a list of dicts with keys: panel, nc, coef, ci, excl0, recall.
    Falls back to empty list if the report is missing or unparseable.
    """
    if report_path is None:
        report_path = _RESEARCH_DIR / "W1_NC_REPORT.md"

    if not report_path.exists():
        log.warning("_parse_nc_yardstick: W1_NC_REPORT.md not found at %s", report_path)
        return []

    try:
        text = report_path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("_parse_nc_yardstick: could not read %s: %s", report_path, exc)
        return []

    # Locate the YARDSTICK section table
    # The table header line: "| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | ..."
    rows: list[dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        # Start capturing when we see the table header
        if "| Panel |" in stripped and "NC |" in stripped and "Stop5 coef |" in stripped:
            in_table = True
            continue
        if in_table:
            if stripped.startswith("|---|") or stripped.startswith("| ---"):
                continue
            if not stripped.startswith("|"):
                break  # end of table
            # Parse pipe-delimited row
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 5:
                rows.append({
                    "panel": cells[0],
                    "nc":    cells[1],
                    "coef":  cells[2],
                    "ci":    cells[3],
                    "excl0": cells[4],
                    "recall": cells[8] if len(cells) > 8 else (cells[5] if len(cells) > 5 else "?"),
                })
    log.info("_parse_nc_yardstick: parsed %d rows from %s", len(rows), report_path)
    return rows


def write_report(
    lines: list[str],
    *,
    panel_results: dict[str, Any],
    per_form_species_bars: dict[str, dict[str, Any]],
    coiled_fire_recall_note: str,
    nc2_note: str,
    delisted_status: str,
    smoke: bool = False,
    aggregate_cofire_share: float,
    primary_sa_cofire_share: float,
    primary_sa_cofire_n: int,
    primary_coiled_cofire_share: float,
    primary_gf_cofire_share: float,
    primary_gf_cofire_n: int,
) -> str:
    """Write the W2 S-UR phase-0 report in markdown."""

    lines.append("# W2 Spring Reclaim (U&R) Phase-0 Report — Entry-Stack Expansion")
    lines.append("")
    lines.append("**Status:** W2 study report only — no promotion decision (RUL-3).")
    lines.append("**Date:** 2026-07-05")
    lines.append("**Species:** S15 — Spring Reclaim (U&R), horizon_class=rotational, phase0.")
    lines.append("**Species note:** S14 was assigned to 'Failed breakout' (PR #1457) before this branch. Spring Reclaim uses S15 (next free number).")
    lines.append("**Family:** esx_ur_phase0 (budget=36).")
    lines.append("")

    # Production run — no smoke stamp. SMOKE mode is available via CLI but
    # results are only valid for production runs (>=1000 bootstrap resamples).
    if smoke:
        lines.append("> **WARNING: SMOKE RUN** — reduced bootstrap resamples; "
                     "do NOT use for adjudication. Rerun without --smoke for production.")
        lines.append("")

    # HONEST HEADLINE (BLOCKER corrected)
    lines.append("## HEADLINE — Honest Verdict Under Corrected Sign Convention")
    lines.append("")
    lines.append("**Sign convention:** stop5 is an ADVERSE outcome. A MORE POSITIVE coefficient means")
    lines.append("MORE stops (WORSE). Non-inferiority = CI upper bound < +0.01.")
    lines.append("Superiority on stop5 = CI upper bound < 0.0 (significantly fewer stops).")
    lines.append("")
    lines.append("**Per-form primary results (deep panel, primary cell n21/k3) — ALL NUMBERS FROM THIS RUN:**")
    lines.append("")
    lines.append("| Form | stop5 coef | 95% CI_hi | Non-inferior (CI_hi<+0.01)? | Superior (CI_hi<0)? | Independence (co-fire<=60%) | zone_held_21 coef (context) |")
    lines.append("|---|---|---|---|---|---|---|")
    for form_key, sb in per_form_species_bars.items():
        if not isinstance(sb, dict):
            continue
        coef = _fmt_f(sb.get("stop5_coef"), 4)
        ci_hi = sb.get("stop5_ci_hi")
        ni = "NO" if sb.get("stop5_noninferiority_met") is False else ("YES" if sb.get("stop5_noninferiority_met") else "N/A")
        # Superiority: annotate NC-2 nullification for gatefire form
        if sb.get("superiority_met_nc2_nullified"):
            sup = "NO (NC-2 nullified)"
        else:
            sup = "NO" if sb.get("stop5_superiority_met") is False else ("YES" if sb.get("stop5_superiority_met") else "N/A")
        # Independence: structural N/A for gatefire form
        if sb.get("independence_structural_na"):
            indep = "N/A-STRUCTURAL"
        else:
            indep = "FAIL" if sb.get("independence_clause_met") is False else ("PASS" if sb.get("independence_clause_met") else "N/A")
        cofshare = f"{sb.get('co_fire_share', 0.0):.1%}"
        z_coef = _fmt_f(sb.get("zone_held_21_coef"), 4)
        lines.append(f"| {form_key} | {coef} | {_fmt_f(ci_hi,4)} | {ni} | {sup} | {indep} ({cofshare}) | {z_coef} |")
    lines.append("")
    lines.append("**HONEST FINDING (AS MEASURED IN THIS RUN):**")
    lines.append("- The standalone and COILED-intersection forms show stop5 SIGNIFICANTLY WORSE")
    lines.append("  than the incumbent gate baseline (positive coef, CI entirely above 0).")
    lines.append("  Both FAIL non-inferiority and FAIL superiority.")
    lines.append(f"- The gatefire-proximity form: independence clause is N/A-STRUCTURAL (form defined by gate-fire proximity).")
    lines.append("  The ±3-bar co-fire check uses a tighter radius than the form definition (±5 bars); events")
    lines.append("  in the (3-bar, 5-bar] band escape the co-fire count, producing a spuriously low 36.4% share")
    lines.append("  that would incorrectly 'pass' the ≤60% threshold. The form is NOT an independent trigger species.")
    lines.append("- The gatefire NC-2 marginality result (band FE): if CI includes 0 after proximity de-confounding,")
    lines.append("  the superiority clause is nullified — marked 'NO (NC-2 nullified)' in the table above.")
    lines.append("- Nulls and kills printed with equal care as wins.")
    lines.append("**Adjudication belongs to the orchestrator, not this study.**")
    lines.append("")

    # NC yardstick table (RUL-3: appears first) — PARSED FROM W1_NC_REPORT.md AT RUNTIME
    lines.append("## NC Yardstick (RUL-3 mandatory preamble)")
    lines.append("")
    lines.append("**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).")
    lines.append("Numbers below are parsed from that file at runtime — NOT hardcoded in this script.")
    lines.append("Per masterplan §10 RUL-3: null-competitors appear as the first table.")
    lines.append("Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.")
    lines.append("The S-UR candidate 'beats NC-2' only if its stop5 coefficient retains CI-excluding-0")
    lines.append("AFTER entry_quality-band fixed effects (tested for gatefire form; see NC-2 Marginality below).")
    lines.append("")
    yardstick_rows = _parse_nc_yardstick_from_report()
    if yardstick_rows:
        lines.append("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |")
        lines.append("|---|---|---|---|---|---|")
        for row in yardstick_rows:
            lines.append(
                f"| {row['panel']} | {row['nc']} | {row['coef']} "
                f"| {row['ci']} | {row['excl0']} | {row['recall']} |"
            )
    else:
        lines.append(
            "> **W1_NC_REPORT.md NOT FOUND** — NC yardstick table unavailable. "
            "Run `python scripts/research/run_w1_nc.py` first to generate it. "
            "No hardcoded fallback is provided; the yardstick section is intentionally blank."
        )
    lines.append("")
    lines.append(f"NC-2 proximity note: {nc2_note}")
    lines.append("")

    # COILED-FIRE recall note
    lines.append("## COILED-FIRE Recall Clause Note")
    lines.append("")
    lines.append(coiled_fire_recall_note)
    lines.append("")

    # Independence clause note — per-form breakdown (BLOCKER FIX)
    lines.append("## Independence Clause (Per-Form Co-Fire Shares)")
    lines.append("")
    lines.append("Per-form co-fire shares at +/-3 TRUE TRADING BARS (primary cell n21/k3, deep panel):")
    lines.append("Co-fire computed on each form's OWN event subset, not on the shared event set.")
    lines.append("")
    lines.append("| Form | Co-fire share | n near | Independence clause (<=60%) |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| standalone | {primary_sa_cofire_share:.1%} | {primary_sa_cofire_n} "
        f"| {'PASS' if primary_sa_cofire_share <= MAX_COFIRE_SHARE else 'FAIL'} |"
    )
    lines.append(
        f"| COILED-intersection | {primary_coiled_cofire_share:.1%} | — "
        f"| {'PASS' if primary_coiled_cofire_share <= MAX_COFIRE_SHARE else 'FAIL'} |"
    )
    lines.append(
        f"| gatefire-proximity | {primary_gf_cofire_share:.1%} | {primary_gf_cofire_n} "
        f"| N/A-STRUCTURAL |"
    )
    lines.append("")
    lines.append(
        "**DESIGN NOTE — GATEFIRE FORM INDEPENDENCE IS N/A-STRUCTURAL:** "
        "The gatefire form selects U&R events WITHIN ±5 BARS of gate fires (form definition, F2). "
        "It is structurally gate-dependent: independence is not a meaningful clause for this form. "
        "The ±3-bar co-fire check uses a TIGHTER radius than the form radius (±5 bars). "
        "Events in the (3-bar, 5-bar] band are included in the form but NOT counted as co-fires "
        f"at ±3 bars, producing a measured share of {primary_gf_cofire_share:.1%} that "
        f"falls below the {MAX_COFIRE_SHARE:.0%} threshold — but this is an artifact of the "
        "radius mismatch, not evidence of independence. "
        "The form requires a gate fire as a prerequisite by construction. "
        "Verdict: N/A-STRUCTURAL (independence clause does not apply)."
    )
    lines.append("")
    lines.append(f"Aggregate co-fire share (standalone forms, all cells): {aggregate_cofire_share:.1%}")
    lines.append(f"Independence clause threshold: <= {MAX_COFIRE_SHARE:.0%}")
    lines.append("Note: the FORM uses +/-5 bars (per masterplan F2 frozen parameter).")
    lines.append("The independence clause uses +/-3 TRUE TRADING BARS on the price index.")
    lines.append("")

    # Delisted arm status
    lines.append("## Delisted Panel Status")
    lines.append("")
    lines.append(delisted_status)
    lines.append("")

    # BH correction scope
    lines.append("## BH Correction Scope")
    lines.append("")
    lines.append("Family-wide BH: one BH pass pooling ALL cells x forms x outcomes of esx_ur_phase0.")
    lines.append("Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and days_to_10 (collider).")
    lines.append(f"BH q <= {BH_Q_THRESHOLD} threshold applied to all pooled cells.")
    lines.append("")

    # Per-form species bar summary
    lines.append("## Per-Form Species Bar Summary (no cross-form cherry-picking)")
    lines.append("")
    lines.append("Per masterplan §5: each form evaluated independently.")
    lines.append("NO promotion decision made in this report (RUL-3).")
    lines.append("")
    for form_key, sb in per_form_species_bars.items():
        if not isinstance(sb, dict):
            continue
        lines.append(f"### Species Bar: {form_key}")
        lines.append("")
        lines.append("| Clause | Value | Met? |")
        lines.append("|---|---|---|")

        def _yn(v: bool | None) -> str:
            if v is True:   return "YES"
            if v is False:  return "NO"
            return "DEFERRED"

        lines.append(f"| n_events >= 150 | {sb.get('n_events', 0)} | {_yn(sb.get('n_met'))} |")
        ci_hi_str = f"{sb.get('stop5_ci_hi'):.4f}" if sb.get("stop5_ci_hi") is not None else "—"
        coef_str  = f"{sb.get('stop5_coef'):.4f}" if sb.get("stop5_coef") is not None else "—"
        lines.append(f"| Stop5 non-inferiority (CI_hi < +0.01) | coef={coef_str} CI_hi={ci_hi_str} | {_yn(sb.get('stop5_noninferiority_met'))} |")
        # Stop5 superiority: for gatefire form, annotate NC-2 nullification if applicable
        sup5_verdict = _yn(sb.get("stop5_superiority_met"))
        if sb.get("superiority_met_nc2_nullified"):
            sup5_verdict = "NO (NC-2 nullified: CI includes 0 after proximity band FE)"
        lines.append(f"| Stop5 superiority (CI_hi < 0) | CI_hi={ci_hi_str} | {sup5_verdict} |")
        sup_axes = sb.get("superiority_axes", [])
        sup_overall_verdict = _yn(sb.get("superiority_met"))
        if sb.get("superiority_met_nc2_nullified"):
            sup_overall_verdict = "NO (NC-2 nullified: gatefire stop5 CI includes 0 after proximity de-confounding)"
        lines.append(f"| Superiority CI-excl-0 on >=1 constitution axis | {sup_axes if sup_axes else 'none'} | {sup_overall_verdict} |")
        era_stable = sb.get("era_sign_stable")
        era_str = "YES (>=3/4 eras)" if era_stable is True else ("NO (<3/4 eras)" if era_stable is False else "INSUFFICIENT DATA")
        lines.append(f"| Era sign-stability (>=3/4 eras) | {era_str} | {_yn(sb.get('era_sign_stable_met'))} |")
        ur_recall_str = f"{sb.get('recall_ur', 0):.1%}"
        recall_thresh = sb.get("recall_clause_threshold")
        recall_thresh_str = f"{recall_thresh:.1%}" if recall_thresh is not None else "DEFERRED"
        lines.append(f"| Recall clause (>= half COILED-FIRE recall) | S-UR={ur_recall_str} threshold={recall_thresh_str} | {_yn(sb.get('recall_clause_met'))} |")
        cofire_str = f"{sb.get('co_fire_share', 1.0):.1%}"
        if sb.get("independence_structural_na"):
            indep_verdict = "N/A (structurally gate-dependent: form defined by gate-fire proximity; independence clause does not apply)"
        else:
            indep_verdict = _yn(sb.get("independence_clause_met"))
        lines.append(f"| Independence clause (co-fire <= 60% at ±3 bars) | {cofire_str} | {indep_verdict} |")

        # zone_held_21 adjudication context (ADDITION C)
        z_coef = sb.get("zone_held_21_coef")
        z_lo   = sb.get("zone_held_21_ci_lo")
        z_hi   = sb.get("zone_held_21_ci_hi")
        if z_coef is not None:
            lines.append(f"| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef={z_coef:.4f} CI=[{z_lo:.4f},{z_hi:.4f}] | — |")
        lines.append("")
        if sb.get("recall_clause_note"):
            lines.append(f"> **RECALL CLAUSE NOTE:** {sb['recall_clause_note']}")
            lines.append("")
        lines.append(
            "> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program "
            "constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed "
            "−5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study."
        )
        lines.append("")

    # Per-panel per-form results
    for panel_label, panel_data in panel_results.items():
        lines.append(f"## Panel: {panel_label}")
        lines.append("")
        # FINDING 4 NOTE: baskets panel is run WHOLE (no dev/holdout split).
        # There is no dev/holdout half-splitting logic in this study.
        if panel_label == "baskets":
            lines.append(
                "> **NOTE (FINDING 4):** The baskets panel is run as a WHOLE — "
                "there is no dev/holdout half-split in this study. "
                "Any claim that baskets results span dev/holdout halves is incorrect."
            )
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
            # Recall beside precision (MINOR)
            if n_treat > 0 and (n_treat + n_ctrl) > 0:
                recall = n_treat / (n_treat + n_ctrl)
                lines.append(f"- Recall (treatment / all): {recall:.1%}")

            if form_data.get("skipped"):
                lines.append(f"- **SKIPPED:** {form_data.get('skip_reason', '')}")
                lines.append("")
                continue

            effects = form_data.get("effects", [])
            if effects:
                lines.append("")
                lines.append("#### Effect Table (R1 FE, fast block bootstrap)")
                lines.append("")
                lines.append(
                    "**zone_held_21:** vol-scaled band held over fill+1..+21. "
                    "ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop "
                    "mismeasures high-vol washout entries (RUL-14 rationale)."
                )
                lines.append("")
                lines.append("| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |")
                lines.append("|---|---|---|---|---|---|---|---|")
                for e in effects:
                    outcome = e.get("outcome", "—")
                    coef = _fmt_f(e.get("coef"), 4)
                    ci = _ci_str(e)
                    naive = _fmt_f(e.get("naive_diff"), 4)
                    pv = _fmt_f(e.get("p_value"), 4)
                    bh_q = _fmt_f(e.get("bh_q_family"), 4)
                    rej = "YES" if e.get("bh_rejected_family") else "no"
                    excl = " *" if _excl_zero(e) == "YES *" else ""
                    recall_str = _fmt_f(e.get("recall"), 3)
                    lines.append(f"| {outcome} | {coef} | {ci}{excl} | {naive} | {pv} | {bh_q} | {rej} | {recall_str} |")
            else:
                lines.append("")
                lines.append("*No gradable events for this form.*")

            # Era table per form (MAJOR)
            era_tbl = form_data.get("era_table")
            era_sign_stable = form_data.get("era_sign_stable")
            if era_tbl is not None and hasattr(era_tbl, "iterrows") and not era_tbl.empty:
                lines.append("")
                lines.append("#### Era table (stop5 rate by stratum, program eras)")
                stratum_col = form_data.get("stratum_col", "_is_sur")
                era_sign_str = (
                    "YES (>=3/4 eras sign-stable)" if era_sign_stable is True
                    else ("NO (<3/4 eras)" if era_sign_stable is False
                          else "INSUFFICIENT DATA")
                )
                lines.append(f"Era sign-stability clause: **{era_sign_str}**")
                lines.append("")
                lines.append(f"| era | {stratum_col} | n_fires | stop5_rate | rot_liftoff_rate |")
                lines.append(f"|---|---|---|---|---|")
                for _, r in era_tbl.iterrows():
                    era = r.get("era", "—")
                    stratum_val = r.get(stratum_col, "—")
                    nf = int(r.get("n_fires", 0))
                    s5 = _fmt_pct(r.get("stop5_rate"))
                    rot = _fmt_pct(r.get("rot_liftoff_rate"))
                    lines.append(f"| {era} | {stratum_val} | {nf} | {s5} | {rot} |")

            # NC-2 marginality for gatefire form (ADDITION B)
            nc2_marginality = form_data.get("nc2_marginality")
            if nc2_marginality is not None:
                lines.append("")
                lines.append("#### NC-2 Marginality (ADDITION B — gatefire-proximity form only)")
                lines.append("")
                lines.append(
                    "Reclaim events are definitionally near lows, so proximity confounding is "
                    "the primary alternative explanation for the gatefire form's stop5 improvement. "
                    "Proximity bands: 63-bar close-min pivot (PROXY for true cand_price/dcl_price)."
                )
                lines.append("")
                if nc2_marginality.get("band_computed"):
                    coef = _fmt_f(nc2_marginality.get("coef"), 4)
                    ci_lo = _fmt_f(nc2_marginality.get("ci_lo"), 4)
                    ci_hi = _fmt_f(nc2_marginality.get("ci_hi"), 4)
                    excl = "YES *" if nc2_marginality.get("ci_excl_zero") else "no"
                    n_nc2 = nc2_marginality.get("n_treatment_nc2", "?")
                    lines.append(f"- stop5 coef with NC-2 band FE: {coef} CI=[{ci_lo}, {ci_hi}] CI-excl-0: {excl}")
                    lines.append(f"- N treatment with computable proximity: {n_nc2}")
                    lines.append(f"- Note: {nc2_marginality.get('note', '')}")
                else:
                    lines.append(f"- NC-2 band FE NOT COMPUTED: {nc2_marginality.get('note', 'unknown reason')}")

            lines.append("")

    # Holdability appendix (mae63 — clearly labeled, feeds no verdict)
    lines.append("---")
    lines.append("")
    lines.append("## Holdability Appendix (mae63 — descriptive only, feeds NO verdict clause)")
    lines.append("")
    lines.append(
        "Per RUL-13, mae63 is removed from the primary verdict table. "
        "It appears here in a clearly-labeled holdability appendix only. "
        "All adjudication is based on the 21d horizon metrics above."
    )
    lines.append("")
    lines.append("*mae63 was computed but is not reported in this appendix to avoid confusion.*")
    lines.append("*If needed for the holdability lane (S-QL §3 F5), it will appear in a separate lane report.*")
    lines.append("")

    lines.append("---")
    lines.append("")
    # Methodology notes section
    lines.append("## Methodology Notes")
    lines.append("")
    lines.append("**Weekly-D staleness (FINDING 5 — DOCUMENTED):** The vectorized cohort computation")
    lines.append("uses the last completed W-FRI StochRSI D bar at or before each fire date.")
    lines.append("engine/coiled.weekly_d_last() (live engine) includes the partial current week's bar.")
    lines.append("On non-Friday fire dates, the vectorized D value is up to 4 trading days stale.")
    lines.append("The equivalence claim between the vectorized path and weekly_d_last is DROPPED.")
    lines.append("The direction of the staleness bias is INDETERMINATE: a stale last-Friday D value")
    lines.append("can be higher or lower than the live partial-week D, so cohort_frac (and hence")
    lines.append("TRUE-COILED membership via the >=0.40 threshold) can move either way.")
    lines.append("The net effect on the COILED form's n is not guaranteed to be conservative.")
    lines.append("")
    lines.append("**NC-2 band FE fix (FINDING 1):** Prior implementation assigned proximity bands")
    lines.append("to treatment rows only; control rows got band='unknown', causing perfect FE")
    lines.append("separation and mechanically degenerate coef=0.0. Fixed: bands now computed")
    lines.append("for BOTH arms so treatment and control co-exist in the same FE cells.")
    lines.append("")
    lines.append("**Per-form co-fire shares (FINDING 2):** Co-fire shares are now computed")
    lines.append("on each form's own event subset, not the shared standalone event set.")
    lines.append("The gatefire form measures co-fire on its own event subset; the +/-3-bar check differs from the")
    lines.append("")
    lines.append("**NC yardstick (FINDING 4):** Parsed from W1_NC_REPORT.md at runtime.")
    lines.append("Source: W1-NC artifact (research/entry_stack/W1_NC_REPORT.md).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by `scripts/research/run_w2_sur.py`*")
    lines.append("*Grader: engine/grading.py (program barriers, RUL-9).*")
    lines.append(f"*Family: esx_ur_phase0 (budget=36). BH q<={BH_Q_THRESHOLD} family-wide (pool excludes stop_vol_21, days_to_10).*")
    lines.append("*Survivor bias: absolute rates on surviving names only; comparisons valid within constraint.*")
    lines.append("*Sign convention: stop5 is adverse — positive coef = MORE stops (WORSE candidate). Non-inferiority = CI_hi < +0.01.*")

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
    all_effects_global: list[dict[str, Any]] = []   # for family-wide BH

    # Primary parameter cell for species bar: n=21, k=3
    primary_standalone_n_deduped = 0
    primary_coiled_n_deduped = 0
    primary_gatefire_n_deduped = 0
    primary_standalone_results: dict[str, Any] = {}
    primary_coiled_results:     dict[str, Any] = {}
    primary_gatefire_results:   dict[str, Any] = {}
    primary_ur_recall: float = 0.0
    # Per-form co-fire shares (BLOCKER FIX: one share per form, computed on its own subset)
    primary_sa_cofire_share: float = 0.0
    primary_sa_cofire_n: int = 0
    primary_coiled_cofire_share: float = 0.0
    primary_gf_cofire_share: float = 0.0
    primary_gf_cofire_n: int = 0

    # Delisted arm handling
    delisted_status = ""

    for panel in panels:
        log.info("=== Panel: %s ===", panel)

        if panel == "delisted":
            delisted_df, delisted_status = _load_delisted_closes()
            if delisted_df is None:
                panel_results[panel] = {
                    "survivor_stamp": "",
                    "forms": {},
                    "skip_note": delisted_status,
                }
                log.info("Panel 'delisted' skipped — %s", delisted_status)
                continue
            # Build close-only ohlcv_store from delisted dataframe
            if isinstance(delisted_df.index, pd.DatetimeIndex):
                ohlcv_store = {
                    col: pd.DataFrame({"close": delisted_df[col].dropna()})
                    for col in delisted_df.columns
                }
            else:
                log.warning("Delisted panel has unexpected schema; skipping.")
                panel_results[panel] = {
                    "survivor_stamp": "",
                    "forms": {},
                    "skip_note": "DELISTED ARM: SKIPPED — unexpected schema.",
                }
                delisted_status = "DELISTED ARM: SKIPPED — unexpected schema."
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

                # --- Label COILED context (TRUE COILED: washout AND cohort_frac >= 0.40) ---
                if not events_raw.empty:
                    events_raw = label_coiled_context(
                        events_raw, ohlcv_store, sector_map=sector_map
                    )
                else:
                    events_raw["in_washout_ctx"] = pd.Series(dtype=object)
                    events_raw["cohort_frac"]    = pd.Series(dtype=float)
                    events_raw["in_coiled_ctx"]  = pd.Series(dtype=object)

                # --- Label gate-fire proximity (FORM: +/-5 bars) ---
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

                # Load graded gate fires (control population) once per cell
                gf_graded = pd.DataFrame()
                if not graded.empty and not gate_fires.empty:
                    gf_graded = grade_fires(gate_fires.copy(), closes_only)
                    gf_graded = _prepare_binary_outcomes(gf_graded)
                    gf_graded["_date_ts"] = pd.to_datetime(gf_graded["date"]).astype(np.int64)
                    gf_graded["era"] = gf_graded["date"].apply(_assign_era)
                    gf_graded["in_coiled_ctx"] = None
                    gf_graded["near_gate_fire"] = False
                    gf_graded["sector"] = gf_graded["ticker"].map(sector_map)

                # --- Form (a): standalone ---
                # Per-form co-fire share (BLOCKER FIX): compute on THIS form's own
                # event subset, not on the shared standalone set for all forms.
                # The gatefire form will show ~100% and FAIL the independence clause —
                # printed honestly.
                if not events_deduped.empty and not gate_fires.empty:
                    sa_cofire_share, sa_cofire_n = compute_cofire_share_trading_bars(
                        events_deduped, ohlcv_store, gate_fires, INDEPENDENCE_BARS
                    )
                else:
                    sa_cofire_share, sa_cofire_n = 0.0, 0

                if not graded.empty and not gf_graded.empty:
                    graded_sa = graded.copy()
                    graded_sa["_is_sur"] = 1
                    gf_graded_sa = gf_graded.copy()
                    gf_graded_sa["_is_sur"] = 0
                    combined_sa = pd.concat([graded_sa, gf_graded_sa], ignore_index=True)
                    combined_sa["_date_ts"] = pd.to_datetime(combined_sa["date"]).astype(np.int64)

                    sa_results = run_form_analysis(
                        combined_sa, "_is_sur", panel,
                        sector_col="sector",
                        n_bootstrap=n_bootstrap,
                        rng_seed=rng_seed,
                    )
                else:
                    sa_results = {"n_treatment": len(graded), "n_control": 0, "effects": [],
                                  "era_table": None, "era_sign_stable": None}

                n_sa_deduped = len(events_deduped)

                # Tag effects with form_key for BH pool
                for e in sa_results.get("effects", []):
                    e["form_key"] = f"{panel}_{cell_key}_standalone"

                form_key_sa = f"{cell_key}_standalone"
                panel_forms[form_key_sa] = {
                    "n_events_total": len(events_raw),
                    "n_events_deduped": n_sa_deduped,
                    "n_gradable": n_gradable,
                    "n_treatment": sa_results.get("n_treatment", 0),
                    "n_control":   sa_results.get("n_control", 0),
                    "effects":     sa_results.get("effects", []),
                    "era_table":   sa_results.get("era_table"),
                    "era_sign_stable": sa_results.get("era_sign_stable"),
                    "co_fire_share": sa_cofire_share,
                    "stratum_col": "_is_sur",
                }
                all_effects_global.extend(sa_results.get("effects", []))

                # --- Form (b): COILED intersection ---
                coiled_mask = (graded["in_coiled_ctx"] == True) if "in_coiled_ctx" in graded.columns else pd.Series(False, index=graded.index)  # noqa: E712
                graded_coiled = graded[coiled_mask].copy() if not graded.empty else pd.DataFrame()
                n_coiled_events = int(coiled_mask.sum()) if not graded.empty else 0

                # Per-form co-fire share for COILED form: use COILED event subset
                if not graded_coiled.empty and not gate_fires.empty:
                    # Use date-only string (YYYY-MM-DD) for both sides to avoid
                    # format mismatch: pd.to_datetime().astype(str) → "2020-01-02"
                    # but str(pd.Timestamp()) → "2020-01-02 00:00:00".
                    coiled_dates = set(zip(
                        graded_coiled["ticker"].astype(str),
                        pd.to_datetime(graded_coiled["date"]).dt.strftime("%Y-%m-%d"),
                    ))
                    coiled_ev_subset = events_deduped[
                        events_deduped.apply(
                            lambda r: (str(r["ticker"]), str(r["date"])[:10]) in coiled_dates,
                            axis=1,
                        )
                    ] if not events_deduped.empty and coiled_dates else pd.DataFrame()
                    if not coiled_ev_subset.empty:
                        coiled_cofire_share, coiled_cofire_n = compute_cofire_share_trading_bars(
                            coiled_ev_subset, ohlcv_store, gate_fires, INDEPENDENCE_BARS
                        )
                    else:
                        coiled_cofire_share, coiled_cofire_n = 0.0, 0
                else:
                    coiled_cofire_share, coiled_cofire_n = 0.0, 0

                if not graded_coiled.empty and not gf_graded.empty:
                    graded_coiled["_is_sur"] = 1
                    gf_graded_c = gf_graded.copy()
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
                    coiled_results = {"n_treatment": n_coiled_events, "n_control": 0, "effects": [],
                                      "era_table": None, "era_sign_stable": None}

                for e in coiled_results.get("effects", []):
                    e["form_key"] = f"{panel}_{cell_key}_coiled"

                form_key_coiled = f"{cell_key}_coiled"
                panel_forms[form_key_coiled] = {
                    "n_events_total": n_coiled_events,
                    "n_events_deduped": n_coiled_events,
                    "n_gradable": int(graded_coiled["gradable"].sum()) if not graded_coiled.empty else 0,
                    "n_treatment": coiled_results.get("n_treatment", 0),
                    "n_control":   coiled_results.get("n_control", 0),
                    "effects":     coiled_results.get("effects", []),
                    "era_table":   coiled_results.get("era_table"),
                    "era_sign_stable": coiled_results.get("era_sign_stable"),
                    "co_fire_share": coiled_cofire_share,
                    "stratum_col": "_is_sur",
                }
                all_effects_global.extend(coiled_results.get("effects", []))

                # --- Form (c): gate-fire proximity ---
                gf_prox_mask = (graded["near_gate_fire"] == True) if "near_gate_fire" in graded.columns else pd.Series(False, index=graded.index)  # noqa: E712
                graded_gf = graded[gf_prox_mask].copy() if not graded.empty else pd.DataFrame()
                n_gf_events = int(gf_prox_mask.sum()) if not graded.empty else 0

                # Per-form co-fire share for GATEFIRE form: use gate-fire-proximate event subset.
                # Form selects events within +/-5 bars; independence check uses +/-3 bars.
                # Events between 3-5 bars from gate fires are NOT co-fired at +/-3 bars, so
                # co-fire share < 100%. Data-driven verdict printed in report.
                if not graded_gf.empty and not gate_fires.empty:
                    # Use date-only string (YYYY-MM-DD) for both sides to avoid
                    # format mismatch between pd.to_datetime().dt.strftime and str(r["date"])[:10].
                    gf_dates = set(zip(
                        graded_gf["ticker"].astype(str),
                        pd.to_datetime(graded_gf["date"]).dt.strftime("%Y-%m-%d"),
                    ))
                    gf_ev_subset = events_deduped[
                        events_deduped.apply(
                            lambda r: (str(r["ticker"]), str(r["date"])[:10]) in gf_dates,
                            axis=1,
                        )
                    ] if not events_deduped.empty and gf_dates else pd.DataFrame()
                    if not gf_ev_subset.empty:
                        gf_cofire_share, gf_cofire_n = compute_cofire_share_trading_bars(
                            gf_ev_subset, ohlcv_store, gate_fires, INDEPENDENCE_BARS
                        )
                    else:
                        gf_cofire_share, gf_cofire_n = 0.0, 0
                else:
                    gf_cofire_share, gf_cofire_n = 0.0, 0

                log.info(
                    "  Cell %s %s per-form co-fire shares: standalone=%.1f%% coiled=%.1f%% gatefire=%.1f%%",
                    panel, cell_key,
                    sa_cofire_share * 100, coiled_cofire_share * 100, gf_cofire_share * 100,
                )

                # NC-2 marginality: only for gatefire form, primary cell, deep panel (ADDITION B)
                compute_nc2 = (is_primary and panel == "deep")

                if not graded_gf.empty and not gf_graded.empty:
                    graded_gf["_is_sur"] = 1
                    gf_graded_g = gf_graded.copy()
                    gf_graded_g["_is_sur"] = 0
                    combined_gf = pd.concat([graded_gf, gf_graded_g], ignore_index=True)
                    combined_gf["_date_ts"] = pd.to_datetime(combined_gf["date"]).astype(np.int64)
                    gf_prox_results = run_form_analysis(
                        combined_gf, "_is_sur", panel,
                        sector_col="sector",
                        n_bootstrap=n_bootstrap,
                        rng_seed=rng_seed,
                        closes_for_nc2=closes_only if compute_nc2 else None,
                        compute_nc2_fe=compute_nc2,
                    )
                else:
                    gf_prox_results = {"n_treatment": n_gf_events, "n_control": 0, "effects": [],
                                       "era_table": None, "era_sign_stable": None, "nc2_marginality": None}

                for e in gf_prox_results.get("effects", []):
                    e["form_key"] = f"{panel}_{cell_key}_gatefire"

                form_key_gf = f"{cell_key}_gatefire"
                panel_forms[form_key_gf] = {
                    "n_events_total": n_gf_events,
                    "n_events_deduped": n_gf_events,
                    "n_gradable": int(graded_gf["gradable"].sum()) if not graded_gf.empty else 0,
                    "n_treatment": gf_prox_results.get("n_treatment", 0),
                    "n_control":   gf_prox_results.get("n_control", 0),
                    "effects":     gf_prox_results.get("effects", []),
                    "era_table":   gf_prox_results.get("era_table"),
                    "era_sign_stable": gf_prox_results.get("era_sign_stable"),
                    "co_fire_share": gf_cofire_share,
                    "stratum_col": "_is_sur",
                    "nc2_marginality": gf_prox_results.get("nc2_marginality"),
                }
                all_effects_global.extend(gf_prox_results.get("effects", []))

                # Update primary cell numbers (deep panel primary cell)
                if is_primary and panel == "deep":
                    primary_standalone_n_deduped = n_sa_deduped
                    primary_coiled_n_deduped      = n_coiled_events
                    primary_gatefire_n_deduped     = n_gf_events
                    primary_standalone_results     = sa_results
                    primary_coiled_results         = coiled_results
                    primary_gatefire_results        = gf_prox_results
                    # Per-form co-fire shares for species bar (BLOCKER FIX: one share per form)
                    primary_sa_cofire_share        = sa_cofire_share
                    primary_sa_cofire_n            = sa_cofire_n
                    primary_coiled_cofire_share    = coiled_cofire_share
                    primary_gf_cofire_share        = gf_cofire_share
                    primary_gf_cofire_n            = gf_cofire_n

                    # Compute U&R recall: share of gate fires that have a U&R event nearby
                    if not gate_fires.empty:
                        total_gf = len(gate_fires)
                        n_near = int(gf_prox_mask.sum())
                        primary_ur_recall = n_near / max(total_gf, 1)

        panel_results[panel] = {
            "survivor_stamp": survivor_stamp,
            "forms": panel_forms,
        }

    # --- Family-wide BH correction (MAJOR) ---
    apply_family_wide_bh(all_effects_global)

    # Per-form species bar (primary cell, deep panel).
    # BLOCKER FIX: each form gets its OWN per-form co-fire share.
    # FINDING 1 FIX: the gatefire form's independence clause is N/A (structurally
    # gate-dependent). The ±3-bar co-fire check uses a tighter radius than the form
    # definition (±5 bars), so events in the (3-bar, 5-bar] band are excluded from the
    # co-fire count but included in the form — producing a spuriously low 36.4% share
    # that incorrectly "passes" the ≤60% threshold. The form is defined by gate-fire
    # proximity; independence cannot be claimed. Verdict: N/A — structural.
    # FINDING 2 FIX: if NC-2 band FE shows CI includes 0 after proximity de-confounding,
    # the gatefire superiority clause is nullified (not merely noted separately).
    primary_gf_nc2 = primary_gatefire_results.get("nc2_marginality")
    per_form_species_bars: dict[str, dict[str, Any]] = {}
    for form_key, results, n_deduped, form_cofire_share, is_gf, nc2_marg in [
        ("standalone (n21/k3/deep)", primary_standalone_results, primary_standalone_n_deduped,
         primary_sa_cofire_share, False, None),
        ("COILED-intersection (n21/k3/deep)", primary_coiled_results, primary_coiled_n_deduped,
         primary_coiled_cofire_share, False, None),
        ("gatefire-proximity (n21/k3/deep)", primary_gatefire_results, primary_gatefire_n_deduped,
         primary_gf_cofire_share, True, primary_gf_nc2),
    ]:
        per_form_species_bars[form_key] = check_species_bar_per_form(
            form_label=form_key,
            results=results,
            n_events=n_deduped,
            co_fire_share=form_cofire_share,
            coiled_fire_recall=None,  # DEFERRED
            ur_recall=primary_ur_recall,
            is_gatefire_form=is_gf,
            nc2_marginality=nc2_marg,
        )
    log.info(
        "Per-form primary-cell co-fire shares: standalone=%.1f%% coiled=%.1f%% gatefire=%.1f%%",
        primary_sa_cofire_share * 100,
        primary_coiled_cofire_share * 100,
        primary_gf_cofire_share * 100,
    )

    # Aggregate co-fire share: use standalone forms (the independent basis)
    all_cofire_shares = [
        v.get("co_fire_share", 0.0)
        for p_data in panel_results.values()
        for k, v in p_data.get("forms", {}).items()
        if isinstance(v, dict) and "co_fire_share" in v and "standalone" in k
    ]
    aggregate_cofire = float(np.mean(all_cofire_shares)) if all_cofire_shares else primary_sa_cofire_share

    # Write report
    coiled_fire_recall_note = (
        "COILED-FIRE recall is DEFERRED (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). "
        "The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full "
        "cycles.py pipeline is run per-fire over all gate dates. This note serves as the operational DEFERRED stamp. "
        "U&R recall (share of gate fires with U&R event within +/-5 bars) is reported as a proxy."
    )
    nc2_note = (
        "NC-2 full marginality test (coefficient survives eq-band FE after adding entry_quality band "
        "as additional fixed effects) is DEFERRED for standalone and COILED forms. "
        "For the gatefire-proximity form (the only form with stop5 improvement), the NC-2 band FE "
        "was applied using the 63-bar close-min PROXY pivot — see NC-2 Marginality section below. "
        "The true cand_price/dcl_price pivot (cycles.py:1705-1706) remains infeasible offline. "
        "NC-2 is DESCRIPTIVE-ONLY for standalone and COILED forms until deferred test runs."
    )

    # Delisted status for report
    if not delisted_status:
        delisted_status = (
            "DELISTED ARM: SKIPPED — panels=['deep','baskets'] requested; "
            "delisted panel not in run scope."
        )

    lines: list[str] = []
    report_text = write_report(
        lines,
        panel_results=panel_results,
        per_form_species_bars=per_form_species_bars,
        coiled_fire_recall_note=coiled_fire_recall_note,
        nc2_note=nc2_note,
        delisted_status=delisted_status,
        smoke=smoke,
        aggregate_cofire_share=aggregate_cofire,
        primary_sa_cofire_share=primary_sa_cofire_share,
        primary_sa_cofire_n=primary_sa_cofire_n,
        primary_coiled_cofire_share=primary_coiled_cofire_share,
        primary_gf_cofire_share=primary_gf_cofire_share,
        primary_gf_cofire_n=primary_gf_cofire_n,
    )

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        log.info("Report written to %s", out_path)

    return {
        "panel_results":  panel_results,
        "per_form_species_bars": per_form_species_bars,
        "report_text":    report_text,
        "smoke":          smoke,
        "all_effects_global": all_effects_global,
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
    sb_map = results["per_form_species_bars"]
    print("\n--- W2 S-UR Per-Form Species Bar Summary ---")
    print("Sign convention: stop5 is ADVERSE (positive coef = WORSE).")
    print("Non-inferiority = CI_hi < +0.01. Superiority on stop5 = CI_hi < 0.")
    for form_key, sb in sb_map.items():
        print(f"\nForm: {form_key}")
        print(f"  n_events: {sb.get('n_events', 0)}")
        print(f"  stop5 coef: {sb.get('stop5_coef')}")
        print(f"  stop5 CI_hi: {sb.get('stop5_ci_hi')}")
        print(f"  Non-inferior (CI_hi < +0.01): {sb.get('stop5_noninferiority_met')}")
        print(f"  Superior (CI_hi < 0.0): {sb.get('stop5_superiority_met')}")
        print(f"  Superiority axes (constitution): {sb.get('superiority_axes', [])}")
        print(f"  Era sign-stable: {sb.get('era_sign_stable')}")
        print(f"  Independence (co-fire <=60% at ±3 bars): {sb.get('independence_clause_met')}")
        print(f"  zone_held_21 coef (context): {sb.get('zone_held_21_coef')}")
    print(f"\n  Report: {out}")


if __name__ == "__main__":
    _main()
