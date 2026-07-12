"""engine.neuralweb.causal_targets — CHF W3: Target panel builders (CHF-R6).

Builds the two v1 target families and the candidate-cause panel.

AUTHORITY CONTRACT (CHF-R1)
----------------------------
All outputs are display-tier infrastructure, not signals.
Authority booleans: all False.  not_a_signal: True.  scored_path_surfaces: [].

TARGET FAMILIES (CHF-R6)
-------------------------
1. regime_risk — CI-safe anchor family.
   Source: data/regime/regime_history.parquet (1971→, git-tracked).
   Targets: forward transition indicators, recession onset, breadth deterioration.
   Runs anywhere — no gitignored store required.

2. entry_quality — verdict-grade entry outcomes.
   Source: data/replay/replay_boarded.parquet (gitignored, runner-local).
   Resolved via env override REPLAY_BOARDED_PATH.
   When absent: returns None + prints honest data_absent note (CHF-R6).
   ERA STAMP: every edge on this family is auto-stamped era_specific/RECENT_ONLY
   (effective verdict window ≈2022-06-30+; P0 memo §6 v1.1).
   The era-split leg returns insufficient_era_span by construction.

CANDIDATE-CAUSE PANEL (CHF-R6)
--------------------------------
Built from the W1 feature inventory: only features with
  - candidate_cause in allowed_roles
  - present: True in the built inventory
Applies min_lag_days from the inventory when building EdgeSpec lag specs.

Language law: banned words (caused/proved/proof/validated) must not appear
in any user-facing text generated here (RUL-CC-5).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Effective verdict-grade window start for entry_quality (P0 memo §6 v1.1)
_ENTRY_QUALITY_ERA_START = pd.Timestamp("2022-06-30")

# Regime history parquet path (relative to repo root)
_REGIME_HISTORY_PATH = Path("data") / "regime" / "regime_history.parquet"
_BREADTH_PATH = Path("data") / "breadth" / "breadth.parquet"

# Replay boarded parquet — gitignored runner-local store (untracked-store law)
_REPLAY_BOARDED_DEFAULT = Path("data") / "replay" / "replay_boarded.parquet"
_REPLAY_BOARDED_ENV = "REPLAY_BOARDED_PATH"

# Good state labels for the good_21d target (CHF-R6)
_GOOD_21D_STATES = {"CUSHIONED", "CLEAN_LIFTOFF"}
_STOPPED_STATE = "STOPPED"

# Target metric ids per family — the ONLY valid target_id / test_spec.metric
# values the panels produce. Rendered into the brainstorm pack so proposal
# cards cannot invent metrics no panel builds (W28 skeptic finding: the
# generator minted 'entry_quality_score_21d' because the pack never listed
# the real names).
TARGET_IDS_BY_FAMILY = {
    "regime_risk": [
        "regime_worsening_5d",
        "regime_worsening_10d",
        "recession_onset_63d",
        "breadth_deterioration_21d",
    ],
    "entry_quality": ["good_21d", "stopped_8_21", "fwd_mdd_21"],
}


# ---------------------------------------------------------------------------
# Regime / risk target panel (CI-safe anchor family)
# ---------------------------------------------------------------------------

def build_regime_risk_panel(root: Path | str | None = None) -> dict[str, pd.Series]:
    """Build regime-risk target panel from git-tracked parquet files.

    Returns a dict mapping target_id → pd.Series (date-indexed, boolean or float).

    Targets produced:
      regime_worsening_5d   — transition_state worsens within 5 trading days
      regime_worsening_10d  — transition_state worsens within 10 trading days
      recession_onset_63d   — recession flag onset within 63 trading days
      breadth_deterioration_21d — pct_above_50 drops >= 5pp within 21 trading days

    All targets are market_series (time-series, not ticker panel).
    Returns {} if regime_history.parquet is absent (honest degradation).

    Transition-state worsening: we map transition_state to an integer severity
    score and flag if the score increases (deteriorates) within h days.
    Severity: 0=STABLE, 1=WATCHING, 2=WARNING, 3=DOWNGRADE, 4=CRISIS
    (or any novel label → score 0; new labels are safe-defaulted).
    """
    if root is None:
        root = Path(".")
    root = Path(root)

    regime_path = root / _REGIME_HISTORY_PATH
    breadth_path = root / _BREADTH_PATH

    if not regime_path.exists():
        log.warning("causal_targets: regime_history.parquet absent at %s — returning {}", regime_path)
        return {}

    try:
        rh = pd.read_parquet(regime_path)
    except Exception as exc:
        log.warning("causal_targets: could not load regime_history.parquet — %s", exc)
        return {}

    if not isinstance(rh.index, pd.DatetimeIndex):
        try:
            rh.index = pd.to_datetime(rh.index)
        except Exception:
            log.warning("causal_targets: regime_history.parquet index not parseable as dates")
            return {}

    rh = rh.sort_index()
    targets: dict[str, pd.Series] = {}

    # --- Transition-state severity mapping ---
    _SEVERITY = {
        "STABLE": 0,
        "WATCHING": 1,
        "WARNING": 2,
        "DOWNGRADE": 3,
        "CRISIS": 4,
    }

    if "transition_state" in rh.columns:
        sev = rh["transition_state"].map(
            lambda s: _SEVERITY.get(str(s).upper(), 0) if pd.notna(s) else 0
        ).astype(float)

        for h in (5, 10):
            # Worsening: max severity in next h days > current severity
            fwd_max = sev.rolling(window=h, min_periods=1).max().shift(-h)
            worsening = (fwd_max > sev).astype(float)
            worsening.name = f"regime_worsening_{h}d"
            # Drop NaN tail
            worsening = worsening.dropna()
            targets[f"regime_worsening_{h}d"] = worsening

    # --- Recession onset target ---
    if "recession" in rh.columns:
        rec_bool = rh["recession"].fillna(False).astype(bool)
        # Onset: not in recession today, enters recession within 63 trading days
        h = 63
        in_rec_fwd = rec_bool.rolling(window=h, min_periods=1).max().shift(-h)
        onset = ((~rec_bool) & (in_rec_fwd > 0)).astype(float)
        onset.name = "recession_onset_63d"
        onset = onset.dropna()
        targets["recession_onset_63d"] = onset

    # --- Breadth deterioration target ---
    if breadth_path.exists():
        try:
            bdf = pd.read_parquet(breadth_path)
            if not isinstance(bdf.index, pd.DatetimeIndex):
                bdf.index = pd.to_datetime(bdf.index)
            bdf = bdf.sort_index()

            if "pct_above_50" in bdf.columns:
                pct = bdf["pct_above_50"].astype(float)
                h = 21
                fwd_pct = pct.shift(-h)
                # Deterioration: forward value drops >= 5pp
                deterioration = (fwd_pct - pct <= -5.0).astype(float)
                deterioration.name = "breadth_deterioration_21d"
                deterioration = deterioration.dropna()
                targets["breadth_deterioration_21d"] = deterioration
        except Exception as exc:
            log.warning("causal_targets: could not load breadth.parquet — %s", exc)

    log.info("causal_targets: regime_risk panel built — %d targets", len(targets))
    return targets


# ---------------------------------------------------------------------------
# Entry-quality target panel (gitignored runner-local store)
# ---------------------------------------------------------------------------

def build_entry_quality_panel(root: Path | str | None = None) -> dict[str, pd.Series] | None:
    """Build entry-quality target panel from replay_boarded.parquet.

    Resolves the store via env override REPLAY_BOARDED_PATH first, then
    falls back to the repo-relative default path if the file exists.
    Returns None with a printed honest data_absent note when unresolved (CHF-R6).

    When present: verdict-grade subset only (verdict_type=='fire' AND
    verdict_grade==True). Targets:
      good_21d       — state_8_21 in {CUSHIONED, CLEAN_LIFTOFF}
      stopped_8_21   — state_8_21 == 'STOPPED'
      fwd_mdd_21     — fwd_mdd_21 (float, raw; negative = drawdown)

    ERA STAMP: this panel is auto-stamped era_specific/RECENT_ONLY.
    Effective window ≈2022-06-30+; era-split leg returns insufficient_era_span
    by construction (not enough pre-2010 verdict-grade data).

    Returns dict[target_id, pd.Series] when the store is present, else None.
    """
    if root is None:
        root = Path(".")
    root = Path(root)

    # Resolve store path: env override first, then repo-relative default
    env_path = os.environ.get(_REPLAY_BOARDED_ENV)
    if env_path:
        boarded_path = Path(env_path)
    else:
        boarded_path = root / _REPLAY_BOARDED_DEFAULT

    if not boarded_path.exists():
        log.warning(
            "causal_targets: data_absent — replay_boarded.parquet not found at %s. "
            "Set %s env var to point to the runner-local store. "
            "Entry-quality target family is unavailable on this checkout.",
            boarded_path, _REPLAY_BOARDED_ENV,
        )
        print(
            f"[causal_targets] data_absent: replay_boarded.parquet not found "
            f"(tried {boarded_path}). "
            f"Set {_REPLAY_BOARDED_ENV} to runner-local path. "
            "Entry-quality edges will not be built this run."
        )
        return None

    try:
        df = pd.read_parquet(boarded_path)
    except Exception as exc:
        log.warning("causal_targets: could not load replay_boarded.parquet — %s", exc)
        print(f"[causal_targets] data_absent: could not load replay_boarded.parquet — {exc}")
        return None

    # Verdict-grade subset (CHF-R6)
    required_cols = {"verdict_type", "verdict_grade", "state_8_21"}
    missing = required_cols - set(df.columns)
    if missing:
        log.warning(
            "causal_targets: replay_boarded.parquet missing columns %s — "
            "entry-quality panel unavailable",
            missing,
        )
        print(
            f"[causal_targets] data_absent: replay_boarded.parquet missing columns "
            f"{missing} — entry-quality panel unavailable"
        )
        return None

    mask = (df["verdict_type"] == "fire") & (df["verdict_grade"] == True)
    verdict_df = df.loc[mask].copy()

    if len(verdict_df) == 0:
        log.warning("causal_targets: replay_boarded verdict-grade subset is empty")
        print("[causal_targets] data_absent: verdict-grade subset is empty")
        return None

    # Ensure date index
    if not isinstance(verdict_df.index, pd.DatetimeIndex):
        # Try to find a date column
        date_col = None
        for col in ("signal_date", "date", "fire_date", "Date"):
            if col in verdict_df.columns:
                date_col = col
                break
        if date_col is None:
            log.warning("causal_targets: could not find date column in replay_boarded")
            return None
        verdict_df = verdict_df.set_index(date_col)
        verdict_df.index = pd.to_datetime(verdict_df.index)
    verdict_df = verdict_df.sort_index()

    # Filter to effective verdict window (≈2022-06-30+)
    verdict_df = verdict_df.loc[verdict_df.index >= _ENTRY_QUALITY_ERA_START]
    if len(verdict_df) == 0:
        log.warning(
            "causal_targets: no verdict-grade entries at or after %s",
            _ENTRY_QUALITY_ERA_START.date()
        )
        return None

    targets: dict[str, pd.Series] = {}

    # good_21d target
    if "state_8_21" in verdict_df.columns:
        good_21d = verdict_df["state_8_21"].isin(_GOOD_21D_STATES).astype(float)
        good_21d.name = "good_21d"
        targets["good_21d"] = good_21d

        stopped_8_21 = (verdict_df["state_8_21"] == _STOPPED_STATE).astype(float)
        stopped_8_21.name = "stopped_8_21"
        targets["stopped_8_21"] = stopped_8_21

    # fwd_mdd_21 target
    if "fwd_mdd_21" in verdict_df.columns:
        fwd_mdd = verdict_df["fwd_mdd_21"].astype(float)
        fwd_mdd.name = "fwd_mdd_21"
        targets["fwd_mdd_21"] = fwd_mdd

    # CHF-R5 ticker-panel law: many fires share one signal date, so the raw
    # series carries duplicate date labels. Collapse to per-date cross-sections
    # BEFORE any time-series inference — the v1 candidate causes are macro
    # series with no within-date cross-ticker variation, so the admissible
    # collapse is the per-date cross-sectional mean (daily good-rate /
    # stop-rate / mean drawdown). Effective N is calendar periods by
    # construction, never fire counts.
    # PROMOTION-PATH TODOs (Opus review 2026-07-12, non-blocking while all
    # verdicts are null): (1) the per-date mean of a varying-count Bernoulli
    # is heteroskedastic (1-fire dates are far noisier) and the downstream
    # market_series HAC does not model it — WLS-by-fire-count or a
    # min-fires-per-date gate before trusting any positive edge; (2) the
    # collapsed index is fire-dates-only (calendar-sparse), so HAC lags in
    # index positions ≠ calendar days — reindex to business days first.
    targets = {
        tid: s.groupby(s.index).mean().sort_index().rename(tid)
        for tid, s in targets.items()
    }

    n_dates = len(next(iter(targets.values()))) if targets else 0
    log.info(
        "causal_targets: entry_quality panel built — %d targets, %d fires "
        "collapsed to %d per-date cross-sections (era ≥%s)",
        len(targets), len(verdict_df), n_dates, _ENTRY_QUALITY_ERA_START.date()
    )
    return targets


# ---------------------------------------------------------------------------
# Candidate-cause panel from W1 inventory
# ---------------------------------------------------------------------------

def build_cause_panel(
    root: Path | str | None = None,
    inventory_path: Path | str | None = None,
) -> dict[str, dict]:
    """Build the candidate-cause panel from the W1 feature inventory.

    Returns a dict mapping feature_id → {
        'feature_id': str,
        'family': str,
        'path': str,
        'columns': list[str],
        'min_lag_days': int,
        'era_coverage': list[str],
        'tier': str,
        'pit_basis': str,
        'cadence': str,
        'present': bool,
    }.

    Only features with:
      - 'candidate_cause' in allowed_roles
      - present: True in the inventory
    are included.  min_lag_days is taken from the inventory entry.

    Columns fall back to the static FEATURE_SOURCES catalogue when the
    inventory artifact omits them (the build_inventory step strips columns).

    If the inventory artifact is absent, falls back to FEATURE_SOURCES directly.
    """
    from engine.neuralweb.causal_inventory import FEATURE_SOURCES

    # Build a lookup from feature_id to static columns from FEATURE_SOURCES
    _static_cols: dict[str, list[str]] = {
        fs["feature_id"]: fs.get("columns") or []
        for fs in FEATURE_SOURCES
    }

    if root is None:
        root = Path(".")
    root = Path(root)

    if inventory_path is None:
        inv_path = root / "data" / "neuralweb" / "causal_feature_inventory.json"
    else:
        inv_path = Path(inventory_path)

    if not inv_path.exists():
        log.warning(
            "causal_targets: causal_feature_inventory.json absent at %s — "
            "falling back to static FEATURE_SOURCES catalogue.",
            inv_path,
        )
        # Fall back to FEATURE_SOURCES directly
        cause_panel: dict[str, dict] = {}
        for fs in FEATURE_SOURCES:
            fid = fs.get("feature_id", "")
            if not fid:
                continue
            if "candidate_cause" not in (fs.get("allowed_roles") or []):
                continue
            path_str = fs.get("path", "")
            if path_str and not (root / path_str).exists():
                continue
            cause_panel[fid] = {
                "feature_id": fid,
                "family": fs.get("family", "unknown"),
                "path": path_str,
                "columns": fs.get("columns") or [],
                "min_lag_days": fs.get("min_lag_days", 1),
                "era_coverage": fs.get("era_coverage") or [],
                "tier": fs.get("tier", "unknown"),
                "pit_basis": fs.get("pit_basis", "unknown"),
                "cadence": fs.get("cadence", "daily-engine"),
                "present": True,
            }
        log.info("causal_targets: cause panel (static fallback) — %d features", len(cause_panel))
        return cause_panel

    try:
        with inv_path.open(encoding="utf-8") as fh:
            inventory = json.load(fh)
    except Exception as exc:
        log.warning("causal_targets: could not load inventory — %s", exc)
        return {}

    features = inventory.get("features", [])
    cause_panel = {}

    for feat in features:
        fid = feat.get("feature_id", "")
        if not fid:
            continue
        if "candidate_cause" not in (feat.get("allowed_roles") or []):
            continue
        if not feat.get("present", False):
            continue

        # Columns: use inventory field if present; fall back to static catalogue
        cols = feat.get("columns") or _static_cols.get(fid) or []

        cause_panel[fid] = {
            "feature_id": fid,
            "family": feat.get("family", "unknown"),
            "path": feat.get("path", ""),
            "columns": cols,
            "min_lag_days": feat.get("min_lag_days", 1),
            "era_coverage": feat.get("era_coverage") or [],
            "tier": feat.get("tier", "unknown"),
            "pit_basis": feat.get("pit_basis", "unknown"),
            "cadence": feat.get("cadence", "daily-engine"),
            "present": True,
        }

    log.info(
        "causal_targets: cause panel — %d candidate-cause features (of %d total in inventory)",
        len(cause_panel), len(features)
    )
    return cause_panel


# ---------------------------------------------------------------------------
# Cause data loader (for use by build_causal_edges.py)
# ---------------------------------------------------------------------------

def load_cause_series(
    feature_id: str,
    cause_meta: dict,
    root: Path,
    column: str | None = None,
) -> pd.Series | None:
    """Load a single cause series from its registered path.

    Returns a pd.Series (date-indexed) or None if the file is absent or
    the column is not found.

    column: if None, uses the first column in cause_meta['columns'].
    """
    path = root / cause_meta.get("path", "")
    if not path.exists():
        log.debug("load_cause_series: %s not found at %s", feature_id, path)
        return None

    col = column or (cause_meta.get("columns") or [None])[0]
    if col is None:
        log.debug("load_cause_series: no column specified for %s", feature_id)
        return None

    try:
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(path, columns=[col])
        elif suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and col in raw:
                # Snapshot-style: scalar value, not a series
                return None
            return None
        elif suffix == ".jsonl":
            rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            df = pd.DataFrame(rows)
            if col not in df.columns:
                return None
            asof = cause_meta.get("asof_field", "date")
            if asof in df.columns:
                df = df.set_index(asof)
                df.index = pd.to_datetime(df.index)
        else:
            return None
    except Exception as exc:
        log.debug("load_cause_series: error loading %s — %s", path, exc)
        return None

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            return None

    if col not in df.columns:
        return None

    s = df[col].astype(float, errors="ignore")
    if not isinstance(s, pd.Series):
        return None
    return s.sort_index().dropna()
