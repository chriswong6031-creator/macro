"""F-HZ-1 — Dilution-Hazard Phase-0 Study Harness.

Pre-registered in: research/dilution_hazard/F_HZ1_PREREG.md (commit BEFORE running).
Family: dilution_hazard (FDR budget=3: predicates A=shelf, B=takedown, C=trailing).
Adjacent prior: research/entry_stack/W1_SEV_REPORT.md
  (S-EV earnings-window: stop5 NULL, mae21 NULL — mechanistically distinct but noted).

Data gates:
  1. data/edgar/dilution_events.parquet   — absent → ACCRUAL-CONVERT (exit 0)
  2. data/replay/replay_boarded.parquet   — absent → ACCRUAL-CONVERT (exit 0)
  Both absent → print combined gate status and exit 0.

Floor check (printed BEFORE any statistic):
  N_FIRES_FLOOR   = 300  gradable fires per arm (non-NaN outcomes)
  N_EPISODE_FLOOR = 25   episode clusters per arm (on gradable fires)
  Fail → DEFER-on-floor (exit 0).

FDR: family='dilution_hazard', declared_budget=3, logged idempotently BEFORE outcomes.

Usage:
    python scripts/research/f_hz1_study.py
    python scripts/research/f_hz1_study.py --dilution-path /path/to/dilution_events.parquet
    python scripts/research/f_hz1_study.py --boarded-path /path/to/replay_boarded.parquet
    python scripts/research/f_hz1_study.py --ledger-path /tmp/test_ledger.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical data paths (mirrors run_rule_replay._CANONICAL_DATA pattern)
# ---------------------------------------------------------------------------
_CANONICAL_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
_DILUTION_PATH  = _CANONICAL_DATA / "edgar" / "dilution_events.parquet"
_BOARDED_PATH   = _CANONICAL_DATA / "replay" / "replay_boarded.parquet"
_LEDGER_PATH    = _CANONICAL_DATA / "trial_ledger.jsonl"
_SUMMARY_OUT    = _CANONICAL_DATA / "research" / "f_hz1_summary.json"
_REPORT_OUT     = _REPO_ROOT / "research" / "dilution_hazard" / "F_HZ1_REPORT.md"

# ---------------------------------------------------------------------------
# F_HZ1_CONSTANTS — single source of truth; imported by tests
# ---------------------------------------------------------------------------

class F_HZ1_CONSTANTS:
    """Frozen predicate and floor thresholds from F_HZ1_PREREG.md §3, §4, §6.

    Do NOT modify values here without amending the prereg document.
    """
    # Predicate A — shelf <=365d
    SHELF_LOOKBACK_DAYS: int = 365
    SHELF_FORMS: frozenset = frozenset({"S-3", "S-3ASR", "S-3/A"})

    # Predicate B — takedown <=90d
    TAKEDOWN_LOOKBACK_DAYS: int = 90
    TAKEDOWN_FORMS: frozenset = frozenset({"424B1", "424B2", "424B3", "424B4", "424B5"})

    # Predicate C — trailing event >=1 in 365d (all forms)
    TRAILING_LOOKBACK_DAYS: int = 365
    TRAILING_MIN_COUNT: int = 1
    TRAILING_FORMS: frozenset = frozenset({
        "S-3", "S-3ASR", "S-3/A",
        "424B1", "424B2", "424B3", "424B4", "424B5",
    })

    # Outcomes
    STOP_MULT: float = 0.95                  # -5% stop (entry_strata_phase0.STOP_MULT)
    DEAD_MONEY_21_THRESHOLD: float = 0.0     # fwd_ret_21 <= 0.0 → dead_money_21 = 1

    # Floors (printed BEFORE any statistic)
    N_FIRES_FLOOR: int = 300
    N_EPISODE_FLOOR: int = 25

    # FDR
    FDR_FAMILY: str = "dilution_hazard"
    FDR_BUDGET: int = 3

    # Minimum store age for reliable predicate A/C (365-day lookback)
    MIN_STORE_AGE_DAYS: int = 365


# ---------------------------------------------------------------------------
# Trial-ledger budget declaration (idempotent; runs even when data gates fail)
# ---------------------------------------------------------------------------

def declare_trial_budget(ledger_path: Path | None = None) -> None:
    """Log declared budget for family='dilution_hazard', n=3, BEFORE any outcome computation.

    Idempotent: repeated calls with the same (family, n, reason) do not append
    duplicate rows (TrialLedger.log_declared_budget dedup guarantee).
    """
    path = ledger_path or _LEDGER_PATH
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; budget declaration skipped")
        return
    led = TrialLedger(path=path, family=F_HZ1_CONSTANTS.FDR_FAMILY)
    led.log_declared_budget(
        F_HZ1_CONSTANTS.FDR_BUDGET,
        family=F_HZ1_CONSTANTS.FDR_FAMILY,
        reason=(
            "F-HZ-1: 3 predicates (A=shelf<=365d, B=takedown<=90d, "
            "C=trailing_365d) x 1 arm each"
        ),
    )
    log.info(
        "Trial budget declared: family=%s n=%d → %s",
        F_HZ1_CONSTANTS.FDR_FAMILY, F_HZ1_CONSTANTS.FDR_BUDGET, path,
    )


# ---------------------------------------------------------------------------
# Data-gate checks
# ---------------------------------------------------------------------------

def _store_age_days(dilution_df: pd.DataFrame) -> int | None:
    """Return calendar days between earliest and latest filing_date in the store.

    Returns None if the store is empty or filing_date cannot be parsed.
    """
    if dilution_df.empty:
        return None
    try:
        dates = pd.to_datetime(dilution_df["filing_date"], errors="coerce").dropna()
        if dates.empty:
            return None
        span = (dates.max() - dates.min()).days
        return int(span)
    except Exception:  # noqa: BLE001
        return None


def check_data_gates(
    dilution_path: Path,
    boarded_path: Path,
) -> dict[str, Any]:
    """Check both data gates and return a status dict.

    Keys:
        all_clear: bool — True only if both files present and store is old enough
        dilution_present: bool
        boarded_present: bool
        store_age_days: int | None
        come_back_date: str | None  — ISO date when store should have >=365d history
        messages: list[str]         — human-readable gate messages
    """
    messages: list[str] = []
    dilution_present = dilution_path.exists()
    boarded_present  = boarded_path.exists()

    store_age_days: int | None = None
    come_back_date: str | None = None

    if not dilution_present:
        messages.append(
            f"GATE FAIL [dilution]: {dilution_path} not found. "
            "Run nightly collector (scripts/collect.py edgar_dilution) first. "
            "First sweep backfills ~90 calendar days (LOOKBACK_DAYS_FIRST=90). "
            "Routing to ACCRUAL-CONVERT."
        )
    else:
        try:
            df = pd.read_parquet(dilution_path)
            store_age_days = _store_age_days(df)
            if store_age_days is not None:
                need = F_HZ1_CONSTANTS.MIN_STORE_AGE_DAYS - store_age_days
                if need > 0:
                    cb = date.today() + timedelta(days=need)
                    come_back_date = str(cb)
                    messages.append(
                        f"GATE PARTIAL [dilution]: store age={store_age_days}d, "
                        f"need >={F_HZ1_CONSTANTS.MIN_STORE_AGE_DAYS}d for reliable "
                        f"predicate A/C. Come-back date: {come_back_date}. "
                        "Routing to ACCRUAL-CONVERT."
                    )
        except Exception as e:  # noqa: BLE001
            messages.append(f"GATE FAIL [dilution]: cannot read {dilution_path}: {e}. Routing to ACCRUAL-CONVERT.")
            dilution_present = False

    if not boarded_present:
        messages.append(
            f"GATE FAIL [replay_boarded]: {boarded_path} not found. "
            "Run scripts/run_rule_replay.py to generate. "
            "File is Mac-local (gitignored). "
            "Routing to ACCRUAL-CONVERT."
        )

    all_clear = (
        dilution_present
        and boarded_present
        and (store_age_days is None or store_age_days >= F_HZ1_CONSTANTS.MIN_STORE_AGE_DAYS)
    )

    return {
        "all_clear": all_clear,
        "dilution_present": dilution_present,
        "boarded_present": boarded_present,
        "store_age_days": store_age_days,
        "come_back_date": come_back_date,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Predicate construction
# ---------------------------------------------------------------------------

def build_predicates(
    fires: pd.DataFrame,
    dilution: pd.DataFrame,
) -> pd.DataFrame:
    """Attach three hazard predicates to fires via a PIT join.

    PIT law: filing_date < fire_date (strictly before). Same-day filings excluded.

    Returns fires with new bool columns:
        hazard_shelf_active    — predicate A
        hazard_takedown_recent — predicate B
        hazard_trailing_event  — predicate C

    Parameters
    ----------
    fires : DataFrame with at least columns ['ticker', 'date'] where 'date'
            is the fire date (parseable to datetime).
    dilution : DataFrame with columns ['ticker', 'form', 'filing_date']
               as produced by edgar_dilution collector.
    """
    fires = fires.copy()
    fire_date_col = pd.to_datetime(fires["date"])
    fires["_fire_date"] = fire_date_col

    dilution = dilution.copy()
    dilution["_filing_date"] = pd.to_datetime(dilution["filing_date"], errors="coerce")
    dilution = dilution.dropna(subset=["_filing_date", "ticker"])

    # Pre-split dilution by form category for efficiency
    shelf_dil    = dilution[dilution["form"].isin(F_HZ1_CONSTANTS.SHELF_FORMS)].copy()
    takedown_dil = dilution[dilution["form"].isin(F_HZ1_CONSTANTS.TAKEDOWN_FORMS)].copy()
    all_dil      = dilution[dilution["form"].isin(F_HZ1_CONSTANTS.TRAILING_FORMS)].copy()

    def _any_in_window(
        ticker: str,
        fire_date: pd.Timestamp,
        dil_subset: pd.DataFrame,
        lookback_days: int,
        min_count: int = 1,
    ) -> bool:
        """Return True if ticker has >=min_count dilution filings strictly before
        fire_date and within lookback_days calendar days."""
        rows = dil_subset[dil_subset["ticker"] == ticker]
        if rows.empty:
            return False
        window_start = fire_date - pd.Timedelta(days=lookback_days)
        # PIT law: filing_date < fire_date (strictly before)
        mask = (rows["_filing_date"] >= window_start) & (rows["_filing_date"] < fire_date)
        return int(mask.sum()) >= min_count

    # Build predicates row by row (handles varying fire counts gracefully)
    pred_a: list[bool] = []
    pred_b: list[bool] = []
    pred_c: list[bool] = []

    for _, row in fires.iterrows():
        ticker    = str(row["ticker"])
        fire_date = row["_fire_date"]

        pred_a.append(_any_in_window(
            ticker, fire_date, shelf_dil,
            F_HZ1_CONSTANTS.SHELF_LOOKBACK_DAYS,
        ))
        pred_b.append(_any_in_window(
            ticker, fire_date, takedown_dil,
            F_HZ1_CONSTANTS.TAKEDOWN_LOOKBACK_DAYS,
        ))
        pred_c.append(_any_in_window(
            ticker, fire_date, all_dil,
            F_HZ1_CONSTANTS.TRAILING_LOOKBACK_DAYS,
            min_count=F_HZ1_CONSTANTS.TRAILING_MIN_COUNT,
        ))

    fires["hazard_shelf_active"]    = pred_a
    fires["hazard_takedown_recent"] = pred_b
    fires["hazard_trailing_event"]  = pred_c

    # Clean up helper column
    fires.drop(columns=["_fire_date"], inplace=True)

    return fires


# ---------------------------------------------------------------------------
# Episode clustering (mirrors run_rule_replay._assign_episode_cluster)
# ---------------------------------------------------------------------------

def _assign_episode_cluster(fires: pd.DataFrame) -> pd.Series:
    """Return episode cluster series.

    If 'episode_id' column is present in fires, use it directly.
    Otherwise fall back to ticker×calendar-year (YYYYQ).
    """
    if "episode_id" in fires.columns:
        return fires["episode_id"].astype(str)
    # Fallback: ticker×year
    year = pd.to_datetime(fires["date"], errors="coerce", format="mixed").dt.year.astype(str)
    return (fires["ticker"].astype(str) + "_" + year).rename("episode_cluster")


# ---------------------------------------------------------------------------
# Outcome computation
# ---------------------------------------------------------------------------

def compute_outcomes(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Attach stop5 and dead_money_21 to fires that have price data.

    If `closes` is None or empty, outcome columns are set to NaN (graceful
    degradation — floor check will fail and route to DEFER-on-floor).

    stop5: bool (True if forward close touches STOP_MULT=-5% within 5 bars).
    dead_money_21: bool (True if fwd_ret_21 <= 0.0).

    Both computed strictly forward from fill_date+1.
    """
    fires = fires.copy()
    fires["stop5"]          = float("nan")
    fires["dead_money_21"]  = float("nan")
    fires["fwd_ret_21"]     = float("nan")
    fires["gradable"]       = False

    if not closes:
        return fires

    try:
        from engine.grading import forward_metrics
    except ImportError:
        log.warning("engine.grading not importable; outcomes not computed")
        return fires

    HORIZONS = (5, 21)

    for idx, row in fires.iterrows():
        ticker    = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])
        close     = closes.get(ticker)

        if close is None or close.empty:
            continue

        try:
            fm = forward_metrics(close, fire_date, horizons=HORIZONS)
        except Exception:  # noqa: BLE001
            continue

        if fm.get("fill_date") is None:
            continue

        fires.at[idx, "gradable"] = True

        # stop5: path touch — minimum close within fill+1..fill+5 reaches -5% barrier.
        # Uses fwd_mdd_5 (= min(0, min(close[fill+1..fill+5]) / entry - 1)) per
        # entry_strata_phase0.py:429 and grading.forward_metrics() definition.
        fwd_mdd_5 = fm.get("fwd_mdd_5")
        fwd_21    = fm.get("fwd_ret_21")

        if fwd_mdd_5 is not None:
            fires.at[idx, "stop5"] = float(fwd_mdd_5 <= (F_HZ1_CONSTANTS.STOP_MULT - 1.0))

        if fwd_21 is not None:
            fires.at[idx, "fwd_ret_21"]    = float(fwd_21)
            fires.at[idx, "dead_money_21"] = float(fwd_21 <= F_HZ1_CONSTANTS.DEAD_MONEY_21_THRESHOLD)

    return fires


# ---------------------------------------------------------------------------
# Floor check
# ---------------------------------------------------------------------------

def check_floors(
    fires: pd.DataFrame,
    predicate_col: str,
    episode_col: str = "episode_cluster",
) -> dict[str, Any]:
    """Check n-fires and n-episode-cluster floors for hazard vs non-hazard arms.

    Floors are enforced on GRADABLE counts (fires with non-NaN outcomes, i.e.
    fires where price paths were available). Membership counts (all fires in the
    predicate arm) are also printed for diagnostic purposes.

    Both gradable n_fires and gradable n_clusters must meet the floor thresholds.
    Episode clusters are counted only on gradable fires.

    Returns a dict with keys:
        pass: bool
        hazard_n_fires: int              — gradable fires in hazard arm
        non_hazard_n_fires: int          — gradable fires in non-hazard arm
        hazard_n_fires_member: int       — all membership fires in hazard arm
        non_hazard_n_fires_member: int   — all membership fires in non-hazard arm
        hazard_n_clusters: int           — gradable episode clusters in hazard arm
        non_hazard_n_clusters: int       — gradable episode clusters in non-hazard arm
        message: str
    """
    hazard_fires     = fires[fires[predicate_col] == True]  # noqa: E712
    non_hazard_fires = fires[fires[predicate_col] == False]  # noqa: E712

    # Membership counts (all fires in the arm, regardless of gradability)
    hz_n_member  = len(hazard_fires)
    nhz_n_member = len(non_hazard_fires)

    # Gradable counts (fires with price paths available → non-NaN outcomes)
    if "gradable" in hazard_fires.columns:
        hz_gradable  = hazard_fires[hazard_fires["gradable"] == True]   # noqa: E712
        nhz_gradable = non_hazard_fires[non_hazard_fires["gradable"] == True]  # noqa: E712
    else:
        # If no gradable column, treat all as gradable (pre-outcome-compute call)
        hz_gradable  = hazard_fires
        nhz_gradable = non_hazard_fires

    hz_n   = len(hz_gradable)
    nhz_n  = len(nhz_gradable)

    hz_cl  = hz_gradable[episode_col].nunique() if episode_col in hz_gradable.columns else 0
    nhz_cl = nhz_gradable[episode_col].nunique() if episode_col in nhz_gradable.columns else 0

    fires_ok    = (hz_n >= F_HZ1_CONSTANTS.N_FIRES_FLOOR and nhz_n >= F_HZ1_CONSTANTS.N_FIRES_FLOOR)
    clusters_ok = (hz_cl >= F_HZ1_CONSTANTS.N_EPISODE_FLOOR and nhz_cl >= F_HZ1_CONSTANTS.N_EPISODE_FLOOR)
    passed = fires_ok and clusters_ok

    msg = (
        f"FLOOR [{predicate_col}]: "
        f"hazard membership={hz_n_member}, gradable={hz_n} (need >={F_HZ1_CONSTANTS.N_FIRES_FLOOR}), "
        f"hazard n_clusters_gradable={hz_cl} (need >={F_HZ1_CONSTANTS.N_EPISODE_FLOOR}); "
        f"non_hazard membership={nhz_n_member}, gradable={nhz_n} (need >={F_HZ1_CONSTANTS.N_FIRES_FLOOR}), "
        f"non_hazard n_clusters_gradable={nhz_cl} (need >={F_HZ1_CONSTANTS.N_EPISODE_FLOOR}) "
        f"→ {'PASS' if passed else 'FAIL'}"
    )

    return {
        "pass": passed,
        "hazard_n_fires":            hz_n,
        "non_hazard_n_fires":        nhz_n,
        "hazard_n_fires_member":     hz_n_member,
        "non_hazard_n_fires_member": nhz_n_member,
        "hazard_n_clusters":         hz_cl,
        "non_hazard_n_clusters":     nhz_cl,
        "message": msg,
    }


# ---------------------------------------------------------------------------
# Era-law splits
# ---------------------------------------------------------------------------

def era_law_split(fires: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split fires into era-law cohorts per prereg §8.

    Returns dict:
        'verdict_grade_2021plus': fires with fire_date >= 2021-01-01
        'pre_2021':               fires with fire_date < 2021-01-01
    """
    dates = pd.to_datetime(fires["date"], errors="coerce", format="mixed")
    cutoff = pd.Timestamp("2021-01-01")
    return {
        "verdict_grade_2021plus": fires[dates >= cutoff].copy(),
        "pre_2021":               fires[dates < cutoff].copy(),
    }


# ---------------------------------------------------------------------------
# Contrast summary (descriptive; no BH correction in this PR — printed only)
# ---------------------------------------------------------------------------

def _arm_stats(
    arm: pd.DataFrame,
    outcome: str,
) -> dict[str, Any]:
    """Compute mean rate and n for a binary outcome column."""
    col = arm[outcome].dropna() if outcome in arm.columns else pd.Series(dtype=float)
    n   = len(col)
    rate = float(col.mean()) if n > 0 else float("nan")
    return {"n": n, "rate": round(rate, 5) if n > 0 else None}


def compute_contrast(
    fires: pd.DataFrame,
    predicate_col: str,
    episode_col: str = "episode_cluster",
    era_label: str = "all",
) -> dict[str, Any]:
    """Descriptive contrast for one predicate column.

    Returns hazard vs non-hazard arm stats for stop5 and dead_money_21.
    No BH correction applied — this is descriptive-only per prereg §10.
    """
    hazard     = fires[fires[predicate_col] == True]  # noqa: E712
    non_hazard = fires[fires[predicate_col] == False]  # noqa: E712

    floor = check_floors(fires, predicate_col, episode_col)
    print(floor["message"])

    result: dict[str, Any] = {
        "predicate": predicate_col,
        "era": era_label,
        "floor": floor,
    }

    if not floor["pass"]:
        result["note"] = "DEFER-on-floor: n-floors not met; no rates computed"
        return result

    for outcome in ("stop5", "dead_money_21"):
        hz_stats  = _arm_stats(hazard, outcome)
        nhz_stats = _arm_stats(non_hazard, outcome)
        delta = (
            round(hz_stats["rate"] - nhz_stats["rate"], 5)
            if hz_stats["rate"] is not None and nhz_stats["rate"] is not None
            else None
        )
        result[outcome] = {
            "hazard": hz_stats,
            "non_hazard": nhz_stats,
            "delta_hazard_minus_nonhazard": delta,
        }

    result["episode_cluster_definition"] = (
        "episode_id column from replay_boarded"
        if episode_col == "episode_id"
        else "ticker×year fallback"
    )
    return result


# ---------------------------------------------------------------------------
# Vintage stamp
# ---------------------------------------------------------------------------

def _build_stamp(fires: pd.DataFrame) -> dict[str, Any]:
    """Build vintage stamp for summary JSON."""
    n_gradable = int(fires["gradable"].sum()) if "gradable" in fires.columns else 0
    n_total    = len(fires)
    cov        = float(n_gradable / n_total) if n_total > 0 else 0.0

    try:
        from engine.vintage_stamp import vintage_stamp
        return vintage_stamp(
            price_plane_id="massive_stock_day_v1",
            adjustment_mode="split_adjusted_raw",
            universe_as_of=str(date.today()),
            frame="pit_massive_era_law",
            survivorship_biased=False,
            coverage_frac=cov,
            dead_name_coverage_pct=None,
            era_law_cohort="verdict_grade_2021plus",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("vintage_stamp not available: %s", e)
        return {
            "price_plane_id": "massive_stock_day_v1",
            "adjustment_mode": "split_adjusted_raw",
            "universe_as_of": str(date.today()),
            "frame": "pit_massive_era_law",
            "survivorship_biased": False,
            "coverage_frac": round(cov, 4),
            "dead_name_coverage_pct": None,
            "era_law_cohort": "verdict_grade_2021plus",
            "stamp_degraded": True,
            "stamp_error": str(e),
        }


# ---------------------------------------------------------------------------
# Closes loader (RUN branch only — called after data gates pass)
# ---------------------------------------------------------------------------

_MASSIVE_DIR = _CANONICAL_DATA / "massive_stock_day"


def _load_closes(
    tickers: list[str],
    massive_dir: Path | None = None,
) -> dict[str, pd.Series]:
    """Load split-adjusted close series for the given tickers from massive_stock_day.

    Follows EXACTLY the pattern used by scripts/run_rule_replay._load_closes
    (canonical data-path resolution + split_adjust from scripts.replay_standout_pipeline
    per the rails program §3.2). Returns {} for any ticker not found.

    Called only in the RUN branch after data gates pass. If the store directory
    is absent, returns an empty dict (graceful degradation — floors will fail).
    """
    mass_dir = massive_dir or _MASSIVE_DIR

    try:
        from scripts.replay_standout_pipeline import split_adjust as _split_adjust
    except ImportError:
        log.warning(
            "Could not import split_adjust from scripts.replay_standout_pipeline; "
            "falling back to identity (splits NOT adjusted — test-mode only)"
        )
        def _split_adjust(s: pd.Series) -> pd.Series:  # type: ignore[misc]
            return s

    closes: dict[str, pd.Series] = {}
    missing: list[str] = []

    for ticker in tickers:
        path = mass_dir / f"{ticker}.parquet"
        if not path.exists():
            missing.append(ticker)
            continue
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                missing.append(ticker)
                continue
            c = df["close"].dropna()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)
            c = c.sort_index()
            closes[ticker] = _split_adjust(c)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load %s: %s", ticker, exc)
            missing.append(ticker)

    if missing:
        log.info(
            "Closes missing for %d/%d tickers (%.1f%%) — these fires will be ungradable",
            len(missing), len(tickers), 100 * len(missing) / max(1, len(tickers)),
        )
    return closes


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_study(
    dilution_path: Path | None = None,
    boarded_path: Path | None = None,
    ledger_path: Path | None = None,
    closes: dict[str, pd.Series] | None = None,
    massive_dir: Path | None = None,
) -> dict[str, Any]:
    """Run F-HZ-1 study, returning a result dict.

    Always declares the trial budget before any computation (idempotent).
    Returns gate_status dict if data gates fail or floors not met.
    Returns full study result if study runs.

    `closes` may be supplied directly (for tests). If None, the RUN branch
    loads closes from massive_stock_day via _load_closes() after gates pass.
    If the store is unreachable, _load_closes() returns {} and floors fail.
    `massive_dir` overrides the massive_stock_day directory for testing.
    """
    dilution_path = dilution_path or _DILUTION_PATH
    boarded_path  = boarded_path  or _BOARDED_PATH
    ledger_path   = ledger_path   or _LEDGER_PATH

    # ── Step 1: Declare trial budget (ALWAYS, before any computation) ─────
    declare_trial_budget(ledger_path)

    # ── Step 2: Data gates ─────────────────────────────────────────────────
    gate = check_data_gates(dilution_path, boarded_path)
    for msg in gate["messages"]:
        print(msg)

    if not gate["all_clear"]:
        return {
            "ran": False,
            "branch": "ACCRUAL-CONVERT",
            "gate": gate,
        }

    # ── Step 3: Load data ──────────────────────────────────────────────────
    print("Loading replay_boarded...")
    fires_raw = pd.read_parquet(boarded_path)

    # Filter to verdict_grade=True cohort
    if "verdict_grade" in fires_raw.columns:
        fires_raw = fires_raw[fires_raw["verdict_grade"] == True].copy()  # noqa: E712
    if "verdict_type" in fires_raw.columns:
        fires_raw = fires_raw[fires_raw["verdict_type"] == "fire"].copy()

    print(f"Loaded {len(fires_raw):,} fires (verdict_grade=True)")

    print("Loading dilution_events...")
    dilution = pd.read_parquet(dilution_path)
    print(f"Loaded {len(dilution):,} dilution events")

    # ── Step 4: Assign episode clusters ────────────────────────────────────
    fires_raw["episode_cluster"] = _assign_episode_cluster(fires_raw).values
    episode_defn = (
        "episode_id column from replay_boarded"
        if "episode_id" in fires_raw.columns
        else "ticker×year fallback (no episode_id column)"
    )
    n_clusters = fires_raw["episode_cluster"].nunique()
    print(f"Episode cluster definition: {episode_defn}")
    print(f"Distinct episode clusters: {n_clusters:,}")

    # ── Step 5: Era-law splits ─────────────────────────────────────────────
    era_cohorts = era_law_split(fires_raw)
    for era_name, df in era_cohorts.items():
        print(f"Era cohort '{era_name}': {len(df):,} fires")

    # Primary cohort for FDR tests: verdict_grade_2021plus
    primary_fires = era_cohorts["verdict_grade_2021plus"]

    # ── Step 6: Build predicates (PIT join) ────────────────────────────────
    print("Building dilution hazard predicates (PIT join)...")
    primary_labeled = build_predicates(primary_fires, dilution)

    for pred_col in ("hazard_shelf_active", "hazard_takedown_recent", "hazard_trailing_event"):
        n_hazard = int(primary_labeled[pred_col].sum())
        n_total  = len(primary_labeled)
        print(f"  {pred_col}: {n_hazard:,} hazard fires / {n_total:,} total "
              f"({n_hazard / n_total:.1%})")

    # ── Step 7: Load closes and compute outcomes ───────────────────────────
    # Load closes from massive_stock_day (RUN branch — gates already passed).
    # If closes were injected by caller (tests), use them directly.
    if closes is None:
        mass_dir = massive_dir or _MASSIVE_DIR
        if not mass_dir.exists():
            print(
                f"GATE FAIL [massive_stock_day]: {mass_dir} not found. "
                "Mac-local store is required for outcome computation. "
                "Outcomes will be NaN; floors will fail. "
                "Routing to DEFER-on-floor."
            )
            closes = {}
        else:
            all_tickers = list(fires_raw["ticker"].dropna().unique())
            print(f"Loading closes for {len(all_tickers):,} tickers from {mass_dir}...")
            closes = _load_closes(all_tickers, mass_dir)
            print(f"Closes loaded for {len(closes):,}/{len(all_tickers):,} tickers")

    print("Computing outcomes (stop5, dead_money_21)...")
    primary_labeled = compute_outcomes(primary_labeled, closes)
    n_gradable = int(primary_labeled["gradable"].sum())
    print(f"Gradable fires (price paths available): {n_gradable:,} / {len(primary_labeled):,}")

    # ── Step 8: Floor check and contrasts (PRIMARY: verdict_grade_2021plus) ─
    print("\n=== FLOOR CHECK AND CONTRASTS (verdict_grade_2021plus) ===")
    print(f"N_FIRES_FLOOR={F_HZ1_CONSTANTS.N_FIRES_FLOOR}, "
          f"N_EPISODE_FLOOR={F_HZ1_CONSTANTS.N_EPISODE_FLOOR}")
    print("(Floors printed BEFORE any rate statistic per prereg §6)\n")

    predicates = [
        ("hazard_shelf_active",    "A: shelf <=365d"),
        ("hazard_takedown_recent", "B: takedown <=90d"),
        ("hazard_trailing_event",  "C: trailing event <=365d"),
    ]

    primary_results: dict[str, Any] = {}
    all_floors_pass = False

    for pred_col, pred_label in predicates:
        print(f"--- Predicate {pred_label} ---")
        contrast = compute_contrast(
            primary_labeled, pred_col, episode_col="episode_cluster",
            era_label="verdict_grade_2021plus",
        )
        primary_results[pred_col] = contrast

        if contrast["floor"]["pass"]:
            all_floors_pass = True
            for outcome in ("stop5", "dead_money_21"):
                stats = contrast.get(outcome, {})
                hz  = stats.get("hazard", {})
                nhz = stats.get("non_hazard", {})
                dlt = stats.get("delta_hazard_minus_nonhazard")
                print(
                    f"  {outcome}: hazard={hz.get('rate')} (n={hz.get('n')}), "
                    f"non_hazard={nhz.get('rate')} (n={nhz.get('n')}), "
                    f"delta={dlt}"
                )
        print()

    if not all_floors_pass:
        print("DEFER-on-floor: no predicate arm met n-floors. No report written.")
        return {
            "ran": False,
            "branch": "DEFER-on-floor",
            "gate": gate,
            "primary_results": primary_results,
        }

    # ── Step 9: Pre-2021 era (directional context only) ────────────────────
    pre2021_fires   = era_cohorts["pre_2021"]
    pre2021_labeled = build_predicates(pre2021_fires, dilution)
    pre2021_labeled = compute_outcomes(pre2021_labeled, closes)
    pre2021_results: dict[str, Any] = {}

    print("=== PRE-2021 ERA (directional context only; survivorship bias) ===")
    for pred_col, pred_label in predicates:
        contrast = compute_contrast(
            pre2021_labeled, pred_col, episode_col="episode_cluster",
            era_label="pre_2021",
        )
        pre2021_results[pred_col] = contrast
        print(f"  {pred_col}: floor={'PASS' if contrast['floor']['pass'] else 'FAIL'}")

    # ── Step 10: Build vintage stamp ────────────────────────────────────────
    stamp = _build_stamp(primary_labeled)

    # ── Step 11: Assemble summary JSON ─────────────────────────────────────
    summary: dict[str, Any] = {
        "study":              "F-HZ-1",
        "prereg":             "research/dilution_hazard/F_HZ1_PREREG.md",
        "adjacent_prior":     "research/entry_stack/W1_SEV_REPORT.md",
        "adjacent_prior_note": (
            "W1-SEV (S-EV earnings-window): stop5 NULL, mae21 NULL. "
            "Mechanistically distinct from dilution hazard, but noted per prereg §13."
        ),
        "fdr_family":         F_HZ1_CONSTANTS.FDR_FAMILY,
        "fdr_budget":         F_HZ1_CONSTANTS.FDR_BUDGET,
        "ran_at":             datetime.now(timezone.utc).isoformat(),
        "n_fires_primary":    len(primary_labeled),
        "n_fires_pre2021":    len(pre2021_labeled),
        "episode_cluster_definition": episode_defn,
        "n_clusters_primary": int(primary_labeled["episode_cluster"].nunique()),
        "gate":               gate,
        "primary_era":        "verdict_grade_2021plus",
        "primary_results":    primary_results,
        "pre2021_results":    pre2021_results,
        "vintage_stamp":      stamp,
        "verdict":            "DESCRIPTIVE-ONLY",
        "promotion_eligible": False,
        "survivorship_caveat": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Within-arm comparisons are directionally valid. "
            "cheap_trap survivorship caveats apply."
        ),
    }

    # Write summary JSON (single writer = this script)
    out_path = _SUMMARY_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSummary JSON written to: {out_path}")

    # ── Step 12: Write report skeleton ──────────────────────────────────────
    _write_report(summary, _REPORT_OUT)
    print(f"Report written to: {_REPORT_OUT}")

    return {"ran": True, "branch": "RUN", "summary": summary}


# ---------------------------------------------------------------------------
# Report writer (only called when study actually runs)
# ---------------------------------------------------------------------------

def _write_report(summary: dict[str, Any], report_path: Path) -> None:
    """Write F_HZ1_REPORT.md skeleton to report_path."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# F-HZ-1 Dilution-Hazard Phase-0 Report")
    a("")
    a(f"**Status:** DESCRIPTIVE-ONLY. No alpha claim. No promotion.")
    a(f"**Pre-registration:** research/dilution_hazard/F_HZ1_PREREG.md")
    a(f"**Family:** `dilution_hazard` (budget=3)")
    a(f"**Ran at:** {summary.get('ran_at', 'unknown')}")
    a(f"**Adjacent prior:** {summary.get('adjacent_prior_note', '')}")
    a("")
    a("## Survivorship Caveat")
    a("")
    a(f"> {summary.get('survivorship_caveat', '')}")
    a("")
    a("## Coverage Notes")
    a("")
    a("- Dilution store covers ~90d on first run (LOOKBACK_DAYS_FIRST=90).")
    a("- Predicates A and C require >=365d history for full PIT correctness.")
    a("- CIK→ticker unmapped events excluded from hazard labeling (treated as non-hazard).")
    a("")
    a("## Primary Era: verdict_grade_2021plus")
    a("")
    a(f"N fires: {summary.get('n_fires_primary', 'N/A'):,}" if isinstance(summary.get('n_fires_primary'), int) else f"N fires: {summary.get('n_fires_primary', 'N/A')}")
    a(f"Episode clusters: {summary.get('n_clusters_primary', 'N/A')}")
    a(f"Episode cluster definition: {summary.get('episode_cluster_definition', 'N/A')}")
    a("")
    a("### Predicate Contrasts")
    a("")
    a("| Predicate | Hazard n | Non-hazard n | stop5 hazard | stop5 non-hazard | stop5 delta | dead_money_21 hazard | dead_money_21 non-hazard | dead_money_21 delta |")
    a("|---|---|---|---|---|---|---|---|---|")

    primary_results = summary.get("primary_results", {})
    for pred_col in ("hazard_shelf_active", "hazard_takedown_recent", "hazard_trailing_event"):
        r = primary_results.get(pred_col, {})
        fl = r.get("floor", {})
        if not fl.get("pass"):
            a(f"| {pred_col} | FLOOR-FAIL | — | — | — | — | — | — | — |")
            continue
        s5  = r.get("stop5", {})
        dm21 = r.get("dead_money_21", {})
        a(
            f"| {pred_col} "
            f"| {fl.get('hazard_n_fires', '?')} "
            f"| {fl.get('non_hazard_n_fires', '?')} "
            f"| {s5.get('hazard', {}).get('rate', '?')} "
            f"| {s5.get('non_hazard', {}).get('rate', '?')} "
            f"| {s5.get('delta_hazard_minus_nonhazard', '?')} "
            f"| {dm21.get('hazard', {}).get('rate', '?')} "
            f"| {dm21.get('non_hazard', {}).get('rate', '?')} "
            f"| {dm21.get('delta_hazard_minus_nonhazard', '?')} |"
        )

    a("")
    a("## Verdict")
    a("")
    a("DESCRIPTIVE-ONLY. No FDR correction applied. No promotion.")
    a("A future promotion prereg must carry `derived_from_surface: f_hz1`.")
    a("No alpha is claimed or confirmed by this report; it is a surface description only.")
    a("")
    a("---")
    a("*Generated by scripts/research/f_hz1_study.py*")
    a("*Family: dilution_hazard | Budget declared: 3*")

    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F-HZ-1 Dilution-Hazard Phase-0 Study Harness.",
    )
    parser.add_argument(
        "--dilution-path", type=Path, default=None,
        help=f"Override dilution_events.parquet path (default: {_DILUTION_PATH})",
    )
    parser.add_argument(
        "--boarded-path", type=Path, default=None,
        help=f"Override replay_boarded.parquet path (default: {_BOARDED_PATH})",
    )
    parser.add_argument(
        "--ledger-path", type=Path, default=None,
        help=f"Override trial_ledger.jsonl path (default: {_LEDGER_PATH})",
    )
    parser.add_argument(
        "--massive-dir", type=Path, default=None,
        help=f"Override massive_stock_day directory path (default: {_MASSIVE_DIR})",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    result = run_study(
        dilution_path=args.dilution_path,
        boarded_path=args.boarded_path,
        ledger_path=args.ledger_path,
        massive_dir=args.massive_dir,
    )

    if result.get("ran"):
        print("\nStudy complete. Branch: RUN.")
        return 0

    branch = result.get("branch", "UNKNOWN")
    print(f"\nStudy did not run. Branch: {branch}. This is the expected outcome when data is absent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
