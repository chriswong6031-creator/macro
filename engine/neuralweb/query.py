"""engine.neuralweb.query — The spine QUERY LAYER (Neural Web W2 PR1).

READ-SIDE ONLY: one place answering "what did any engine claim, and what
happened?" across every graded ledger in the Macro Dashboard suite.

FEDERATION NOT MIGRATION
------------------------
No source ledger is modified.  qledger is joined read-only via claim_id.
The substrate ruling (qledger → spine promotion) remains OPEN pending the
joint QI co-sign.  Both sequencing escape hatches verified by scout
(data/neuralweb/w2_scout.json):
  - W6 promotion monitor has NOT fired (n_families_ready=0; earliest
    projection 2026-08-29).
  - qledger semantics frozen since #1180; only post-#1180 change is the
    numpy coerce hotfix (#1225 — no schema change).

DOUBLE-COUNT PREVENTION
-----------------------
``adapt_spine()`` skips altdata_conv rows ONLY when a qledger twin exists
for the same (symbol, as_of) — i.e. event-matched exclusion, not blanket
engine exclusion.  ``build_index`` computes the qledger frame first, derives
the altdata twin key set (frozenset of (symbol, as_of) for desk='altdata'
claims), then passes it to ``adapt_spine(twin_keys=...)``.

Called standalone (``adapt_spine()`` without twin_keys), no altdata_conv
rows are excluded — the caller has no qledger context.

The real-world correspondence: spine has 134 altdata_conv rows; qledger has
133 desk='altdata' claims (one-to-one match for 133 events).  The 1 orphan
(BWXT@2026-07-02) has NO qledger twin and is retained with ledger='spine'.
Today it is ungraded so calibration-inert, but a future graded orphan would
otherwise silently vanish from the W3 calibration index.

engine='desk:ai_desk' rows are intentionally NOT excluded — they have no
qledger twin family and no dedicated adapter.

PIT CORRECTNESS FOR GRADED_AT
------------------------------
``data/spine/predictions.parquet`` carries ``graded_at`` as a column that
is NULL for every row in the current build (0 of 1086 rows populated),
including all 952 rows with ``outcome_graded=True``.  Because the graded_at
timestamp cannot be known from the spine parquet alone, ``adapt_spine()``
backfills it from ``as_of + horizon`` calendar days for graded rows — a
conservative lower bound (the grade could not have been computed before the
horizon elapsed).

``query(graded_before=cutoff)`` enforces: rows with ``outcome_graded=True``
AND ``graded_at`` still null (i.e. graded-but-timestampless, which can only
happen if the adapter backfill was bypassed) are EXCLUDED from the result.
This is the safe direction for PIT replay — a graded row with no timestamp
is a look-ahead hazard, not a pre-cutoff observation.  Ungraded rows
(``outcome_graded=False``) with null graded_at are retained (they have not
yet been graded; they are legitimately pre-cutoff candidates).

CANONICAL COLUMNS
-----------------
Every row in the materialized index carries::

    signal_id, engine, family, ledger, as_of, symbol, scope_type,
    universe, horizon, direction, size_binding, fill_basis, score,
    outcome_excess, outcome_graded, graded_at,
    terminal_state_clean15_126, terminal_state_clean8_21,
    fwd_mfe_5, fwd_mfe_10, fwd_mfe_21, fwd_mfe_63, fwd_mfe_126,
    rate_pressure, quad_hard_label, fused_risk_label, vol_regime,
    risk_radar_state, vector_asof, species_id, archetype

Missing fields per source = NaN/None (honest sparsity, never fabricated).
``fill_basis`` preserves provenance (e.g. "t1_hl2" for CN, "next_bar" for
US/HK/CA post Stage B-e, "asof_legacy" for older qledger rows).
``ledger`` is a source enum:
  spine, track_record, board_hk, board_ca, board_cn, qledger,
  cycles_us, cycles_china, cycles_country
``scope_type`` domain: 'entity' | 'basket' are produced by current data;
  'sector' | 'macro' are reserved for future adapters — no current qledger
  rows produce them.

ADAPTERS (one per source — all fail-open)
-----------------------------------------
a) adapt_spine()         → ledger='spine'
b) adapt_track_record()  → ledger='track_record' (data/signal_archive/; fail-open: absent on fresh clone)
c) adapt_board('hk')     → ledger='board_hk'
d) adapt_board('ca')     → ledger='board_ca'
e) adapt_china_board()   → ledger='board_cn'
f) adapt_qledger()       → ledger='qledger'  (claims⋈grades join, read-only)
g) adapt_forward_logs()  → ledger='cycles_*' (only graded rows)

BUILD IDIOM
-----------
``write_index(root)`` is the single nightly entry point.  It is a FULL
REBUILD (idempotent) — the index is a derived view, not a forward ledger, so
there is no ledger-law tension from overwriting.  ``load_index(root)``
reads the parquet.  ``query(...)`` filters in-memory (fast at today's ~5 MB
scale).

PIT GUARD (documented for callers)
-----------------------------------
``query(..., as_of_before=date)`` retains rows with ``as_of < date``; call
this to restrict to signals that EXISTED before a cutoff.  Outcomes on those
rows were graded AFTER ``as_of``; PIT-correct backtest replay MUST also
supply ``graded_before=date`` to restrict to knowledge state at cutoff.  See
``query()`` docstring.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

__all__ = [
    "COLUMNS",
    "LEDGER_ENUM",
    "adapt_reflexes",
    "adapt_cortex_attention",
    "adapt_options_entry",
    "adapt_tech_signals",
    "build_index",
    "write_index",
    "load_index",
    "query",
]

# ---------------------------------------------------------------------------
# Canonical column contract
# ---------------------------------------------------------------------------

COLUMNS: list[str] = [
    # identity
    "signal_id",
    "engine",
    "family",
    "ledger",          # source enum (see LEDGER_ENUM)
    "as_of",           # decision date (str "YYYY-MM-DD")
    "symbol",          # name / sector / basket slug
    "scope_type",      # entity | sector | basket | macro
    "universe",
    "horizon",         # trading-day horizon (int)
    "direction",       # +1 long / -1 short / 0 context
    "size_binding",    # True iff real money was sized
    "fill_basis",      # fill convention provenance (see docstring)
    "score",
    # outcomes
    "outcome_excess",
    "outcome_graded",
    "graded_at",
    # terminal-state (from engine.grading vocabulary)
    "terminal_state_clean15_126",
    "terminal_state_clean8_21",
    # fwd_mfe horizons — NaN where source does not carry them
    "fwd_mfe_5",
    "fwd_mfe_10",
    "fwd_mfe_21",
    "fwd_mfe_63",
    "fwd_mfe_126",
    # regime stamps (US primary on all lanes; HK/CA/CN have own_market_regime=null by design)
    "rate_pressure",
    "quad_hard_label",
    "fused_risk_label",
    "vol_regime",
    "risk_radar_state",
    "vector_asof",
    # species
    "species_id",
    "archetype",
    # W1 Spine v2 — descriptive role flags (additive; no behavioral reader; spine-ledger only)
    "is_sizing",    # True iff this row sized real money
    "is_veto",      # True iff short/avoid lane
    "is_alpha",     # True iff directional long conviction that was sized
    "is_timing",    # Always False this wave (no mechanical source)
    "is_context",   # Catch-all default; True for non-sizing/non-veto/non-alpha rows
    "falsifier",    # Human-facing falsifier text (nullable str); spine-ledger rows only
    "half_life",    # Decay half-life in trading days (nullable float); filled by W2
]

# Conservative defaults for role flag columns in _ensure_columns / load_index.
# is_context=True for old rows; other flags default False; non-flag new cols get NaN.
_FLAG_DEFAULTS: dict[str, object] = {
    "is_sizing":  False,
    "is_veto":    False,
    "is_alpha":   False,
    "is_timing":  False,
    "is_context": True,
}

# Valid ledger values — used to name-space signal_id prefixes
LEDGER_ENUM: tuple[str, ...] = (
    "spine",
    "track_record",
    "board_hk",
    "board_ca",
    "board_cn",
    "qledger",
    "cycles_us",
    "cycles_china",
    "cycles_country",
    "reflexes",             # Neural Web W6a: per-reflex firings ledgers
    "cortex_attention",     # Neural Web W7b PR2: graded cortex attention claims
    "options_entry",        # Options→NW W-B (RO-5): ungraded-honest options state context
    "tech_signals",         # Tech-signal suite W2 (DARK): display/context only; §3 gate required for promotion
)

# ---------------------------------------------------------------------------
# Double-count prevention: event-matched altdata_conv exclusion
# ---------------------------------------------------------------------------
# altdata_conv rows in data/spine/predictions.parquet are excluded from
# adapt_spine() ONLY when a qledger twin exists for the same (symbol, as_of).
# build_index passes the twin key set; standalone adapt_spine() calls (no
# twin_keys) skip no rows.  engine='desk:ai_desk' rows are intentionally not
# excluded — they have no qledger twin family.
_ALTDATA_CONV_ENGINE: str = "altdata_conv"

# Regime key mapping from board_ledger / china_standout_track (us_ prefixed) to canonical
_US_PREFIX_MAP: dict[str, str] = {
    "us_rate_pressure":    "rate_pressure",
    "us_quad_hard_label":  "quad_hard_label",
    "us_fused_risk_label": "fused_risk_label",
    "us_vol_regime":       "vol_regime",
    "us_risk_radar_state": "risk_radar_state",
    "us_regime_vector_degraded": "regime_vector_degraded",
    "vector_asof":         "vector_asof",
    "staleness_hours":     "staleness_hours",
}

_MFE_COL_FOR_H: dict[int, str] = {
    5:   "fwd_mfe_5",
    10:  "fwd_mfe_10",
    21:  "fwd_mfe_21",
    63:  "fwd_mfe_63",
    126: "fwd_mfe_126",
}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _data_dir(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root) / "data"
    from lib import config  # noqa: PLC0415
    return config.data_dir()


def _index_path(root: Path | str | None) -> Path:
    p = _data_dir(root) / "neuralweb" / "spine_index.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical columns."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add any missing canonical columns as NaN/conservative-default and reorder to COLUMNS.

    W1: role flag columns default to conservative values (is_context=True, others=False)
    rather than NaN so old rows honour R8's 'is_context=true for pre-W1 rows' requirement.
    falsifier defaults None, half_life defaults NaN.
    """
    for c in COLUMNS:
        if c not in df.columns:
            # Use conservative default for flag cols; NaN for everything else
            default = _FLAG_DEFAULTS.get(c, np.nan)
            df[c] = default
    df = df[COLUMNS].copy()
    # Backfill any NaN in flag columns with conservative defaults (handles mixed old/new rows)
    for flag, default_val in _FLAG_DEFAULTS.items():
        if flag in df.columns:
            df[flag] = df[flag].fillna(default_val)
    return df


def _safe_float(val: Any) -> float | None:
    try:
        v = float(val)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _safe_str(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return str(val)


def _safe_bool(val: Any) -> bool | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return bool(val)


def _str_date(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val)
    # strip time component if present ("2026-01-01T..." → "2026-01-01")
    return s[:10] if len(s) >= 10 else s


# ---------------------------------------------------------------------------
# ADAPTER a) spine
# ---------------------------------------------------------------------------

def adapt_spine(
    root: Path | str | None = None,
    *,
    twin_keys: frozenset[tuple[str, str]] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/spine/predictions.parquet → ledger='spine'.

    The spine parquet is the canonical carrier for the us_board + 7 desk
    adapters.  Do NOT re-adapt those sources directly — that would double-count
    rows already in the spine.

    DOUBLE-COUNT GUARD (event-matched): engine='altdata_conv' rows are skipped
    ONLY when ``twin_keys`` contains (symbol, as_of) — meaning a qledger twin
    exists for that event.  Orphan altdata_conv rows (no qledger twin) are
    retained with ledger='spine' so they are not silently dropped from the
    calibration index.

    ``twin_keys`` is a frozenset of (symbol, as_of) tuples built from
    qledger desk='altdata' claims by ``build_index``.  When ``twin_keys`` is
    None (standalone call), no altdata_conv rows are excluded.

    engine='desk:ai_desk' rows are intentionally NOT excluded — they have no
    qledger twin family and no dedicated adapter.

    GRADED_AT BACKFILL: data/spine/predictions.parquet carries graded_at=null
    for every row (0 of 1086 populated in the current build).  For rows with
    outcome_graded=True, this adapter synthesises graded_at = as_of + horizon
    calendar days as a conservative lower bound.  This prevents the query
    layer's graded_before filter from being a no-op for the entire spine ledger
    (which would be a silent PIT look-ahead leak).

    Returns (df, gap_notes).
    """
    import datetime  # noqa: PLC0415  (local import — avoid module-level cost)
    gaps: list[str] = []
    p = _data_dir(root) / "spine" / "predictions.parquet"
    if not p.exists():
        gaps.append("spine: data/spine/predictions.parquet absent — zero rows")
        return _empty_df(), gaps
    try:
        raw = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"spine: read failed ({e}) — zero rows")
        return _empty_df(), gaps

    if raw.empty:
        return _empty_df(), gaps

    excluded_twin = 0   # altdata_conv rows skipped because qledger twin found
    orphan_kept   = 0   # altdata_conv rows retained because no qledger twin
    rows: list[dict] = []
    for _, r in raw.iterrows():
        sig = _safe_str(r.get("signal_id"))
        if not sig:
            continue
        engine_val = _safe_str(r.get("engine")) or ""
        # EVENT-MATCHED DOUBLE-COUNT GUARD (altdata_conv only):
        # Skip this altdata_conv row only when twin_keys was supplied AND
        # (symbol, as_of) is in the qledger altdata twin key set.  Orphans
        # (no qledger twin) are retained.  Standalone calls (twin_keys=None)
        # skip no rows.  engine='desk:ai_desk' is intentionally not touched here.
        if engine_val == _ALTDATA_CONV_ENGINE and twin_keys is not None:
            sym  = _safe_str(r.get("symbol")) or ""
            asof = _str_date(r.get("as_of")) or ""
            if (sym, asof) in twin_keys:
                excluded_twin += 1
                continue
            else:
                orphan_kept += 1
        row: dict[str, Any] = {c: None for c in COLUMNS}
        row["signal_id"]      = sig
        row["engine"]         = engine_val
        row["family"]         = _safe_str(r.get("family"))
        row["ledger"]         = "spine"
        row["as_of"]          = _str_date(r.get("as_of"))
        row["symbol"]         = _safe_str(r.get("symbol"))
        row["scope_type"]     = "entity"  # spine rows are per-ticker
        row["universe"]       = _safe_str(r.get("universe"))
        row["horizon"]        = r.get("horizon")
        row["direction"]      = r.get("direction")
        row["size_binding"]   = _safe_bool(r.get("size_binding"))
        row["fill_basis"]     = "next_bar"
        row["score"]          = _safe_float(r.get("score"))
        row["outcome_excess"] = _safe_float(r.get("outcome_excess"))
        row["outcome_graded"] = _safe_bool(r.get("outcome_graded"))

        # GRADED_AT BACKFILL: spine parquet has graded_at=null for all rows.
        # For graded rows (outcome_graded=True), synthesise graded_at from
        # as_of + horizon days so graded_before filters work correctly.
        raw_graded_at = _str_date(r.get("graded_at"))
        if raw_graded_at is None and _safe_bool(r.get("outcome_graded")):
            asof_str = row["as_of"]
            h = r.get("horizon")
            if asof_str and h is not None:
                try:
                    asof_dt = datetime.date.fromisoformat(str(asof_str))
                    graded_dt = asof_dt + datetime.timedelta(days=int(h))
                    raw_graded_at = graded_dt.isoformat()
                except (ValueError, TypeError, OverflowError):
                    pass  # leave null; query filter will exclude graded+timestampless rows
        row["graded_at"] = raw_graded_at

        # W1 Spine v2 — map role flags and falsifier from spine parquet.
        # If columns are absent (pre-W1 parquet), apply conservative defaults per R8.
        for flag, default_val in _FLAG_DEFAULTS.items():
            raw_val = r.get(flag)
            if raw_val is None or (isinstance(raw_val, float) and raw_val != raw_val):
                row[flag] = default_val
            else:
                row[flag] = bool(raw_val)
        # falsifier: nullable str
        raw_falsifier = r.get("falsifier")
        if raw_falsifier is None or (isinstance(raw_falsifier, float) and raw_falsifier != raw_falsifier):
            row["falsifier"] = None
        else:
            row["falsifier"] = str(raw_falsifier)
        # half_life: nullable float
        raw_hl = r.get("half_life")
        if raw_hl is None or (isinstance(raw_hl, float) and raw_hl != raw_hl):
            row["half_life"] = None
        else:
            try:
                row["half_life"] = float(raw_hl)
            except (TypeError, ValueError):
                row["half_life"] = None

        rows.append(row)

    if twin_keys is not None and (excluded_twin or orphan_kept):
        gaps.append(
            f"spine: altdata_conv: {excluded_twin} excluded (qledger twin), "
            f"{orphan_kept} retained (no twin)"
        )

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# ADAPTER b) track_record
# ---------------------------------------------------------------------------

def adapt_track_record(root: Path | str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/signal_archive/track_record.parquet → ledger='track_record'.

    The canonical path is data/signal_archive/track_record.parquet (git-tracked,
    registered in config/synapse.yml as signal-archive-track-record).  The old
    path data/track_record/track_record.parquet was never written by any producer
    and caused all US track-record rows to be silently dropped from the index
    (fail-open reported it as a benign gap).

    Fail-open is still load-bearing — the file may be absent in a fresh clone
    that has not yet run the engine (degrade-never-raise law).

    Returns (df, gap_notes).
    """
    gaps: list[str] = []
    p = _data_dir(root) / "signal_archive" / "track_record.parquet"
    if not p.exists():
        gaps.append("track_record: data/signal_archive/track_record.parquet absent "
                    "— zero rows")
        return _empty_df(), gaps
    try:
        raw = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"track_record: read failed ({e}) — zero rows")
        return _empty_df(), gaps

    if raw.empty:
        return _empty_df(), gaps

    rows: list[dict] = []
    for _, r in raw.iterrows():
        ticker = _safe_str(r.get("ticker") or r.get("symbol"))
        as_of  = _str_date(r.get("date") or r.get("as_of"))
        if not ticker or not as_of:
            continue
        # track_record carries multiple horizons per row; emit one row per horizon
        # SPINE_HORIZONS = (5, 10, 21, 63, 126)
        for h in (5, 10, 21, 63, 126):
            mfe_col = f"fwd_mfe_{h}"
            # A row must carry at least the horizon column to be meaningful
            if mfe_col not in r.index and f"fwd_ret_{h}" not in r.index:
                continue
            sig = f"track_record:{as_of}:{ticker}:{h}"
            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = "track_record"
            row["family"]         = _safe_str(r.get("lane") or r.get("type") or "track_record")
            row["ledger"]         = "track_record"
            row["as_of"]          = as_of
            row["symbol"]         = ticker
            row["scope_type"]     = "entity"
            row["universe"]       = _safe_str(r.get("universe") or "us_track_record")
            row["horizon"]        = h
            row["direction"]      = 1
            row["size_binding"]   = _safe_bool(r.get("size_binding"))
            row["fill_basis"]     = "next_bar"
            row["score"]          = _safe_float(r.get("composite_z") or r.get("score"))
            # fwd_mfe_H is the outcome column at this horizon
            row[mfe_col]          = _safe_float(r.get(mfe_col))
            # Also grab all fwd_mfe cols available
            for hh in (5, 10, 21, 63, 126):
                col = f"fwd_mfe_{hh}"
                if col in r.index:
                    row[col] = _safe_float(r.get(col))
            # outcome_excess: use fwd_mfe for this horizon as proxy if present
            row["outcome_excess"] = _safe_float(r.get(mfe_col))
            row["outcome_graded"] = row["outcome_excess"] is not None
            row["graded_at"]      = _str_date(r.get("graded_at"))
            # terminal states
            row["terminal_state_clean15_126"] = _safe_str(r.get("terminal_state_clean15_126"))
            row["terminal_state_clean8_21"]   = _safe_str(r.get("terminal_state_clean8_21"))
            # regime stamps (track_record uses us_* prefix or direct)
            for src, dst in _US_PREFIX_MAP.items():
                if dst in COLUMNS and src in r.index:
                    row[dst] = _safe_str(r.get(src))
            for k in ("rate_pressure", "quad_hard_label", "fused_risk_label",
                      "vol_regime", "risk_radar_state", "vector_asof"):
                if k in COLUMNS and k in r.index and row.get(k) is None:
                    row[k] = _safe_str(r.get(k))
            row["species_id"] = _safe_str(r.get("species_id"))
            row["archetype"]  = _safe_str(r.get("archetype"))
            rows.append(row)

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# ADAPTER c/d) HK and CA board ledgers
# ---------------------------------------------------------------------------

def adapt_board(
    market: str,
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/board_ledger/{hk,ca}_board.parquet → ledger='board_{market}'.

    market must be 'hk' or 'ca'.

    Returns (df, gap_notes).
    """
    m = market.lower()
    if m not in ("hk", "ca"):
        raise ValueError(f"adapt_board: market must be 'hk' or 'ca', got {market!r}")
    ledger_name = f"board_{m}"
    gaps: list[str] = []
    p = _data_dir(root) / "board_ledger" / f"{m}_board.parquet"
    if not p.exists():
        gaps.append(f"{ledger_name}: {p} absent — zero rows")
        return _empty_df(), gaps
    try:
        raw = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"{ledger_name}: read failed ({e}) — zero rows")
        return _empty_df(), gaps

    if raw.empty:
        return _empty_df(), gaps

    rows: list[dict] = []
    for _, r in raw.iterrows():
        ticker = _safe_str(r.get("ticker"))
        as_of  = _str_date(r.get("as_of") or r.get("date"))
        if not ticker or not as_of:
            continue
        # Board ledger has one row per (as_of, ticker) with all horizons inline.
        # Emit one index row per horizon that has a fwd_mfe column.
        for h in (5, 10, 21, 63, 126):
            mfe_col = f"fwd_mfe_{h}"
            if mfe_col not in r.index:
                continue
            sig = f"{ledger_name}:{as_of}:{ticker}:{h}"
            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = f"{m}_board"
            row["family"]         = f"{m}_board:{_safe_str(r.get('lane')) or 'buy'}"
            row["ledger"]         = ledger_name
            row["as_of"]          = as_of
            row["symbol"]         = ticker
            row["scope_type"]     = "entity"
            row["universe"]       = f"{m}_stocks"
            row["horizon"]        = h
            row["direction"]      = 1
            row["size_binding"]   = _safe_bool(r.get("size_binding"))
            row["fill_basis"]     = "next_bar"
            row["score"]          = _safe_float(r.get("composite_z") or r.get("score") or r.get("level"))
            row["outcome_excess"] = _safe_float(r.get(mfe_col))
            row["outcome_graded"] = row["outcome_excess"] is not None
            row["graded_at"]      = _str_date(r.get("graded_at"))
            row["terminal_state_clean15_126"] = _safe_str(r.get("terminal_state_clean15_126"))
            row["terminal_state_clean8_21"]   = _safe_str(r.get("terminal_state_clean8_21"))
            # all fwd_mfe
            for hh in (5, 10, 21, 63, 126):
                col = f"fwd_mfe_{hh}"
                if col in r.index:
                    row[col] = _safe_float(r.get(col))
            # regime stamps (us_ prefixed — own_market_regime is null by design)
            for src, dst in _US_PREFIX_MAP.items():
                if dst in COLUMNS and src in r.index:
                    row[dst] = _safe_str(r.get(src))
            row["species_id"] = _safe_str(r.get("species_id"))
            row["archetype"]  = _safe_str(r.get("archetype"))
            rows.append(row)

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# ADAPTER e) China standout board
# ---------------------------------------------------------------------------

def adapt_china_board(root: Path | str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/china_standout_track/board.parquet → ledger='board_cn'.

    fill_basis='t1_hl2' is preserved as provenance (never pooled with US
    next_bar fills without filtering on this column).

    Returns (df, gap_notes).
    """
    gaps: list[str] = []
    p = _data_dir(root) / "china_standout_track" / "board.parquet"
    if not p.exists():
        gaps.append("board_cn: data/china_standout_track/board.parquet absent — zero rows")
        return _empty_df(), gaps
    try:
        raw = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"board_cn: read failed ({e}) — zero rows")
        return _empty_df(), gaps

    if raw.empty:
        return _empty_df(), gaps

    rows: list[dict] = []
    for _, r in raw.iterrows():
        ticker = _safe_str(r.get("ticker"))
        as_of  = _str_date(r.get("date") or r.get("as_of"))
        if not ticker or not as_of:
            continue
        fill_basis = _safe_str(r.get("fill_basis")) or "t1_hl2"
        for h in (5, 10, 21, 63, 126):
            mfe_col = f"fwd_mfe_{h}"
            if mfe_col not in r.index:
                continue
            sig = f"board_cn:{as_of}:{ticker}:{h}"
            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = "cn_board"
            row["family"]         = f"cn_board:{_safe_str(r.get('tier')) or 'tier'}"
            row["ledger"]         = "board_cn"
            row["as_of"]          = as_of
            row["symbol"]         = ticker
            row["scope_type"]     = "entity"
            row["universe"]       = "cn_stocks"
            row["horizon"]        = h
            row["direction"]      = 1
            row["size_binding"]   = _safe_bool(r.get("size_binding"))
            row["fill_basis"]     = fill_basis
            row["score"]          = _safe_float(r.get("score") or r.get("board_rank"))
            row["outcome_excess"] = _safe_float(r.get(mfe_col))
            row["outcome_graded"] = row["outcome_excess"] is not None
            row["graded_at"]      = _str_date(r.get("graded_at"))
            row["terminal_state_clean15_126"] = _safe_str(r.get("terminal_state_clean15_126"))
            row["terminal_state_clean8_21"]   = _safe_str(r.get("terminal_state_clean8_21"))
            for hh in (5, 10, 21, 63, 126):
                col = f"fwd_mfe_{hh}"
                if col in r.index:
                    row[col] = _safe_float(r.get(col))
            # regime stamps (us_ prefixed)
            for src, dst in _US_PREFIX_MAP.items():
                if dst in COLUMNS and src in r.index:
                    row[dst] = _safe_str(r.get(src))
            row["species_id"] = _safe_str(r.get("species_id"))
            row["archetype"]  = _safe_str(r.get("archetype"))
            rows.append(row)

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# ADAPTER f) qledger claims ⋈ grades
# ---------------------------------------------------------------------------

def adapt_qledger(root: Path | str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/qledger/claims.jsonl ⋈ data/qledger/grades.jsonl → ledger='qledger'.

    JOIN KEY: claim_id.
    GRADE HORIZONS: contract is (5, 21, 63) — no 10d or 126d rows exist in
    qledger; those fwd_mfe cells stay NaN in the index.  Current graded data
    is horizon=5 only (1088/1088 graded rows are h=5); h=21 and h=63 are
    contract-reserved but not yet populated.

    FILL CONVENTION: pre-Stage B-e rows carry fill_convention absent or
    "asof_legacy"; post-Stage B-e rows carry "next_bar".  The fill_basis
    column preserves this distinction so callers never pool conventions.

    REGIME STAMPS: written at claim registration time by
    engine/qledger.py:_regime_stamp_for_asof.  However, the real claims.jsonl
    data (7937 rows as of this build) does NOT carry regime fields at the top
    level or nested — all 7937 rows have null rate_pressure / quad_hard_label /
    fused_risk_label / vol_regime / risk_radar_state.  The adapter reads these
    keys defensively (claim.get(k) → null if absent) and carries the nulls
    honestly.  Consequence: query(regime=...) never matches any qledger row;
    regime-conditioned calibration against qledger is a functional gap until the
    claims store is backfilled.  Not data corruption — honest nulls.

    Qledger substrate ruling: READ-ONLY join pending joint QI co-sign.
    signal_id namespace: 'qledger:<claim_id>:<grade_horizon>' — never
    collides with spine or board namespaces.

    Returns (df, gap_notes).
    """
    gaps: list[str] = []
    data = _data_dir(root)
    claims_path = data / "qledger" / "claims.jsonl"
    grades_path = data / "qledger" / "grades.jsonl"

    if not claims_path.exists():
        gaps.append("qledger: data/qledger/claims.jsonl absent — zero rows")
        return _empty_df(), gaps

    # Load claims
    try:
        with claims_path.open(encoding="utf-8") as fh:
            claims_raw = [json.loads(ln) for ln in fh if ln.strip()]
    except Exception as e:  # noqa: BLE001
        gaps.append(f"qledger: claims.jsonl read failed ({e}) — zero rows")
        return _empty_df(), gaps

    # Load grades (may be absent — fail-open)
    grades_by_claim: dict[str, list[dict]] = {}
    if grades_path.exists():
        try:
            with grades_path.open(encoding="utf-8") as fh:
                for ln in fh:
                    if not ln.strip():
                        continue
                    g = json.loads(ln)
                    cid = g.get("claim_id")
                    if cid:
                        grades_by_claim.setdefault(str(cid), []).append(g)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"qledger: grades.jsonl read failed ({e}) — outcomes will be null")
    else:
        gaps.append("qledger: data/qledger/grades.jsonl absent — outcomes will be null")

    rows: list[dict] = []
    for claim in claims_raw:
        cid = _safe_str(claim.get("claim_id"))
        if not cid:
            continue
        desk   = _safe_str(claim.get("desk")) or "unknown"
        asof   = _str_date(claim.get("asof"))
        scope  = claim.get("scope") or {}
        scope_key  = _safe_str(scope.get("key")) or ""
        scope_type = _safe_str(scope.get("type")) or "entity"
        horizon_d  = claim.get("horizon_d")
        direction  = claim.get("direction")
        family     = _safe_str(claim.get("claim_family")) or desk

        # Each grade row is one (claim_id, grade_horizon) pair
        grades_for_claim = grades_by_claim.get(cid, [])
        if not grades_for_claim:
            # Ungraded claim — one row with null outcomes; include for completeness
            grades_for_claim = [{}]

        for grade in grades_for_claim:
            gh = grade.get("horizon_d") or grade.get("grade_horizon")
            # signal_id is namespaced so it never collides across ledgers
            sig = f"qledger:{cid}:{gh or 'open'}"

            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = desk
            row["family"]         = family
            row["ledger"]         = "qledger"
            row["as_of"]          = asof
            row["symbol"]         = scope_key
            row["scope_type"]     = scope_type
            row["universe"]       = "qledger"
            row["horizon"]        = gh if gh is not None else horizon_d
            row["direction"]      = direction
            row["size_binding"]   = False  # qledger is never size-binding
            # fill_basis: post Stage B-e = next_bar; legacy = asof_legacy
            fill_conv = _safe_str(grade.get("fill_convention"))
            row["fill_basis"]     = fill_conv or "asof_legacy"
            row["score"]          = _safe_float(claim.get("edge_score") or claim.get("convergence_score"))

            # outcomes from grade row
            excess = _safe_float(grade.get("excess"))
            hit    = grade.get("hit")
            graded_at = _str_date(grade.get("graded_at"))
            row["outcome_excess"] = excess
            row["outcome_graded"] = (excess is not None and hit is not None)
            row["graded_at"]      = graded_at

            # Map grade horizon to fwd_mfe slot if it matches a SPINE horizon
            if gh in _MFE_COL_FOR_H:
                row[_MFE_COL_FOR_H[gh]] = excess

            # Regime stamps — from claim row (stamped at registration time)
            for k in ("rate_pressure", "quad_hard_label", "fused_risk_label",
                      "vol_regime", "risk_radar_state", "vector_asof"):
                if k in COLUMNS:
                    row[k] = _safe_str(claim.get(k))

            # species_id and archetype are null by design for qledger
            row["species_id"] = None
            row["archetype"]  = None

            rows.append(row)

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# ADAPTER g) Forward logs (cycle graders)
# ---------------------------------------------------------------------------

def adapt_forward_logs(root: Path | str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Adapt sector/china/country cycle forward logs → ledger='cycles_*'.

    ONLY rows carrying graded outcome fields are included.  Projection-only
    rows (no outcome columns populated) are NOT claims-with-outcomes and are
    skipped.  If a log has no graded rows, zero rows are contributed with a
    note.

    China sector cycles grader columns: drawdown_p{21,63}, return_p{21,63},
    bench_ret_p{21,63}.  These do NOT map to fwd_mfe_* (different semantic:
    max-drawdown probability, not max-favorable-excursion) and stay in
    outcome_excess as None.  They are kept as additional context but the
    canonical outcome fields remain null — honest sparsity, not fabrication.

    US sector cycles and country cycles are graded via scripts/grade_promises.py
    into separate scorecard JSON files (not appended to the forward log).
    If those logs have no graded columns, zero rows are contributed.

    Returns (df, gap_notes).
    """
    gaps: list[str] = []
    data = _data_dir(root)

    sources = [
        ("sector_cycles",       "forward_log.parquet", "cycles_us",      "sector"),
        ("china_sector_cycles", "forward_log.parquet", "cycles_china",   "sector"),
        ("country_cycles",      "forward_log.parquet", "cycles_country", "sector"),
    ]

    all_rows: list[dict] = []

    # graded outcome col patterns we look for
    _GRADED_PATTERNS = ("drawdown_p", "return_p", "bench_ret_p", "fwd_ret", "excess", "grade")

    for engine_dir, fname, ledger_name, scope_t in sources:
        p = data / engine_dir / fname
        if not p.exists():
            gaps.append(f"{ledger_name}: {p} absent — zero rows")
            continue
        try:
            df_log = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"{ledger_name}: read failed ({e}) — zero rows")
            continue

        if df_log.empty:
            gaps.append(f"{ledger_name}: empty parquet — zero rows")
            continue

        # Find graded outcome columns
        graded_cols = [c for c in df_log.columns
                       if any(pat in c for pat in _GRADED_PATTERNS)]
        if not graded_cols:
            gaps.append(
                f"{ledger_name}: no graded outcome columns found in {p} "
                f"(cols={list(df_log.columns[:10])}...) — zero rows; "
                "grade_promises produces separate scorecard JSONs for this engine"
            )
            continue

        for _, r in df_log.iterrows():
            date_val = _str_date(r.get("date") or r.get("as_of"))
            sid_val  = _safe_str(r.get("id"))
            if not date_val or not sid_val:
                continue
            # Only include rows where at least one graded col is non-null
            has_outcome = any(
                r.get(c) is not None and not (isinstance(r.get(c), float) and np.isnan(r.get(c)))
                for c in graded_cols
            )
            if not has_outcome:
                continue

            sig = f"{ledger_name}:{date_val}:{sid_val}"
            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = engine_dir
            row["family"]         = f"{engine_dir}:{_safe_str(r.get('signal')) or 'phase'}"
            row["ledger"]         = ledger_name
            row["as_of"]          = date_val
            row["symbol"]         = sid_val
            row["scope_type"]     = scope_t
            row["universe"]       = f"{engine_dir}_universe"
            row["horizon"]        = None  # cycle horizons are not spine trading-day horizons
            row["direction"]      = 1 if _safe_str(r.get("signal")) == "BUY" else (
                                    -1 if _safe_str(r.get("signal")) == "SELL" else 0)
            row["size_binding"]   = False
            row["fill_basis"]     = "cycle_projection"
            row["score"]          = _safe_float(r.get("pos") or r.get("pos_v2"))
            # outcome_excess: not applicable for cycle claims at this level
            row["outcome_excess"] = None
            row["outcome_graded"] = False  # cycle grading is at scorecard level, not row level
            row["graded_at"]      = None
            # no fwd_mfe for cycles — they use their own probability columns
            # no regime stamps in forward log rows
            all_rows.append(row)

    if not all_rows:
        return _empty_df(), gaps

    result = pd.DataFrame(all_rows)
    return _ensure_columns(result), gaps


# ---------------------------------------------------------------------------
# BUILD INDEX
# ---------------------------------------------------------------------------

def build_index(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Run all adapters, union, dedup, sort, return (DataFrame, gaps dict).

    The gaps dict maps adapter name → list of gap note strings (empty list
    means clean).  A missing / corrupt source logs + contributes zero rows.

    Dedup: signal_ids are namespaced by ledger prefix, so collisions across
    ledgers are structurally prevented.  Within a ledger, signal_id should
    be unique by construction (last-write-wins if somehow duplicated).

    Returns (df, gaps).
    """
    gaps: dict[str, list[str]] = {}
    frames: list[pd.DataFrame] = []

    # Run qledger first so we can derive the altdata twin key set for adapt_spine.
    # Twin keys = (symbol, as_of) for every desk='altdata' qledger claim.
    # adapt_spine uses this set to skip altdata_conv rows that have a qledger twin
    # (event-matched exclusion) while retaining orphans with no twin.
    try:
        qledger_df, qledger_gaps = adapt_qledger(root)
        gaps["qledger"] = qledger_gaps
        if not qledger_df.empty:
            frames.append(qledger_df)
        # Build twin key set: rows adapted from desk='altdata' (engine='altdata' in qledger)
        altdata_mask = qledger_df["engine"].astype(str) == "altdata"
        altdata_twin_keys: frozenset[tuple[str, str]] = frozenset(
            zip(
                qledger_df.loc[altdata_mask, "symbol"].astype(str),
                qledger_df.loc[altdata_mask, "as_of"].astype(str),
            )
        )
    except Exception as e:  # noqa: BLE001
        msg = f"qledger: adapter raised unexpectedly ({e}) — zero rows"
        log.warning(msg)
        gaps["qledger"] = [msg]
        altdata_twin_keys = frozenset()

    adapters = [
        ("spine",          lambda: adapt_spine(root, twin_keys=altdata_twin_keys)),
        ("track_record",   lambda: adapt_track_record(root)),
        ("board_hk",       lambda: adapt_board("hk", root)),
        ("board_ca",       lambda: adapt_board("ca", root)),
        ("board_cn",       lambda: adapt_china_board(root)),
        ("forward_logs",   lambda: adapt_forward_logs(root)),
        ("reflexes",       lambda: adapt_reflexes(root)),            # W6a — reflex firings ledgers
        ("cortex_attention", lambda: adapt_cortex_attention(root)),  # W7b PR2 — graded cortex attention
        ("options_entry",  lambda: adapt_options_entry(root)),       # Options→NW W-B — ungraded-honest context
        ("tech_signals",   lambda: adapt_tech_signals(root)),        # W2 tech-signal suite — DARK display/context
    ]

    for name, fn in adapters:
        try:
            df, gap_notes = fn()
            gaps[name] = gap_notes
            if not df.empty:
                frames.append(df)
        except Exception as e:  # noqa: BLE001
            msg = f"{name}: adapter raised unexpectedly ({e}) — zero rows"
            log.warning(msg)
            gaps[name] = [msg]

    if not frames:
        log.warning("build_index: all adapters returned zero rows")
        return _empty_df(), gaps

    combined = pd.concat(frames, ignore_index=True)

    # Dedup on signal_id + horizon: signal_ids are namespaced, so cross-ledger
    # collisions are prevented.  Within a ledger, keep-last (most recent write).
    combined = combined.drop_duplicates(
        subset=["signal_id", "horizon"], keep="last"
    ).reset_index(drop=True)

    # Sort for deterministic output
    combined = combined.sort_values(
        ["ledger", "as_of", "symbol", "horizon"],
        na_position="last",
    ).reset_index(drop=True)

    # W2 — stamp family_half_life from half_life.json (family-level constant broadcast).
    # This is a cheap map-merge: reads the artifact once and joins on engine.
    # CRITICAL: the stamped value is a FAMILY-level constant broadcast to rows,
    # NOT a per-row measurement (flagged as open question in W2 pre-reg).
    # Behavioral consumers (allocation, alert_triage, board ordering) must NOT
    # branch on this column — it is display-only (R7/R8 compliance).
    # If the artifact is absent or unreadable, half_life stays NaN (fail-open).
    # NOTE: daily.yml writes half_life.json AFTER build_spine_index, so the stamped
    # column carries the PRIOR night's artifact (fail-open NaN on first run).
    # This is display-only family metadata, not PIT-sensitive.
    combined = _stamp_family_half_life(combined, root)

    return combined, gaps


def _stamp_family_half_life(df: pd.DataFrame, root: Path | str | None) -> pd.DataFrame:
    """Stamp the family-level half_life from half_life.json onto each row.

    Reads data/neuralweb/half_life.json (produced by W2 scripts/build_kernel_half_lives.py).
    Maps (engine → half_life float | None) and broadcasts to all rows with that engine.
    Rows for engines not in the artifact, or engines with null half_life, get NaN.

    Fail-open: if the artifact is absent, unreadable, or invalid, returns df unchanged.
    This makes W2 entirely additive with no risk of breaking the index build.
    """
    if df.empty or "half_life" not in df.columns:
        return df
    try:
        import json  # noqa: PLC0415
        hl_path = _data_dir(root) / "neuralweb" / "half_life.json"
        if not hl_path.exists():
            return df  # artifact absent — no-op, half_life stays NaN
        hl_data = json.loads(hl_path.read_text(encoding="utf-8"))
        families = hl_data.get("families", {})
        if not families:
            return df

        # Build engine → half_life float|None map
        hl_map: dict[str, float | None] = {}
        for engine_key, entry in families.items():
            if not isinstance(entry, dict):
                continue
            hl_val = entry.get("half_life")
            if hl_val is None or not isinstance(hl_val, (int, float)):
                hl_map[engine_key] = None
            else:
                try:
                    fv = float(hl_val)
                    hl_map[engine_key] = fv if not (fv != fv) else None  # NaN guard
                except (TypeError, ValueError):
                    hl_map[engine_key] = None

        # Broadcast: only overwrite rows where half_life is currently NaN/None
        # (adapters may have already set half_life from source data; respect those)
        engine_col = df["engine"].astype(str)
        for eng, hl_val in hl_map.items():
            if hl_val is None:
                continue  # null half_life → leave as NaN (already the default)
            mask_engine = engine_col == eng
            mask_null_hl = df["half_life"].isna()
            df.loc[mask_engine & mask_null_hl, "half_life"] = hl_val

    except Exception as e:  # noqa: BLE001
        log.warning("_stamp_family_half_life: failed (half_life stays NaN): %s", e)

    return df


# ---------------------------------------------------------------------------
# WRITE + LOAD
# ---------------------------------------------------------------------------

def write_index(root: Path | str | None = None) -> dict:
    """Build the spine index and write to data/neuralweb/spine_index.parquet.

    Also writes the envelope sidecar via engine.neuralweb.envelope.write_sidecar.

    IDEMPOTENT FULL REBUILD: the index is a derived view (not a forward ledger).
    Overwriting on each nightly run is correct — there is no ledger-law tension
    because the index is entirely re-derived from source ledgers every time.

    Returns a stats dict with row/gap counts.
    """
    df, gaps = build_index(root)
    out_path = _index_path(root)

    try:
        df.to_parquet(out_path, index=False)
    except Exception as e:  # noqa: BLE001
        log.error("write_index: to_parquet failed: %s", e)
        raise

    # Write the envelope sidecar
    try:
        from engine.neuralweb.envelope import write_sidecar  # noqa: PLC0415
        write_sidecar(out_path, artifact_id="spine-index")
    except Exception as e:  # noqa: BLE001
        log.warning("write_index: sidecar write failed: %s", e)

    # Build stats
    per_ledger: dict[str, int] = {}
    if not df.empty and "ledger" in df.columns:
        for ldg, sub in df.groupby("ledger"):
            per_ledger[str(ldg)] = len(sub)

    total_gap_notes = sum(len(v) for v in gaps.values())
    stats = {
        "total_rows": len(df),
        "per_ledger": per_ledger,
        "gap_count": total_gap_notes,
        "gaps": gaps,
        "output_path": str(out_path),
    }
    log.info(
        "write_index: %d rows from %d ledgers (%d gap notes)",
        len(df), len(per_ledger), total_gap_notes,
    )
    return stats


def load_index(root: Path | str | None = None) -> pd.DataFrame:
    """Read data/neuralweb/spine_index.parquet. Returns empty frame if absent.

    W1 R8 backfill: old spine_index.parquet (pre-W1) loads with conservative flag
    defaults: is_context=True, others=False (not NaN) so consumers see correct defaults.
    """
    p = _index_path(root)
    if not p.exists():
        return _empty_df()
    try:
        df = pd.read_parquet(p)
        return _ensure_columns(df)
    except Exception as e:  # noqa: BLE001
        log.warning("load_index: read failed: %s", e)
        return _empty_df()


# ---------------------------------------------------------------------------
# QUERY
# ---------------------------------------------------------------------------

def query(
    df: pd.DataFrame | None = None,
    *,
    engine: str | None = None,
    family: str | None = None,
    ledger: str | None = None,
    regime: str | None = None,
    horizon: int | None = None,
    symbol: str | None = None,
    scope_type: str | None = None,
    as_of_before: str | None = None,
    graded_before: str | None = None,
    graded_only: bool = False,
    root: Path | str | None = None,
) -> pd.DataFrame:
    """Filter the spine index by the given criteria.

    Parameters
    ----------
    df:
        Pre-loaded frame.  If None, ``load_index(root)`` is called.
    engine:
        Filter by engine name (exact match).
    family:
        Filter by family name (exact match).
    ledger:
        Filter by ledger enum value (exact match).
    regime:
        Filter by regime label.  Matches against quad_hard_label OR
        fused_risk_label OR vol_regime OR risk_radar_state (any match
        qualifies the row).
    horizon:
        Filter by horizon (int, exact).
    symbol:
        Filter by symbol (exact).
    scope_type:
        Filter by scope_type (entity | sector | basket | macro).
    as_of_before:
        PIT guard — retain rows where as_of < cutoff (ISO date str).
        These rows EXISTED before the cutoff; their outcomes were graded AFTER.
        For a PIT-correct backtest replaying knowledge state at cutoff, ALSO
        supply ``graded_before`` to restrict to what was KNOWN at cutoff.
    graded_before:
        PIT knowledge-state guard — retain rows where graded_at < cutoff.
        Use in tandem with as_of_before for PIT-correct backtest replay.

        Null-graded_at handling (two cases):
        - ``outcome_graded=False`` (ungraded): retained.  These rows existed
          before the cutoff and have not yet been graded; they are legitimately
          pre-cutoff candidates.
        - ``outcome_graded=True`` (graded, but timestamp absent): EXCLUDED.
          A graded row with no timestamp cannot be placed on the timeline;
          retaining it is a look-ahead hazard.  Adapters must supply
          graded_at for graded rows (adapt_spine() backfills as_of+horizon;
          other adapters read graded_at from the source record).

        Note: ``graded_only=True`` additionally removes all ungraded rows
        regardless of their graded_at.
    graded_only:
        If True, only retain rows with outcome_graded == True.

    Returns
    -------
    pd.DataFrame
        Filtered copy of the index (or subset thereof).
    """
    if df is None:
        df = load_index(root)

    if df.empty:
        return df.copy()

    mask = pd.Series([True] * len(df), index=df.index)

    if engine is not None:
        mask &= df["engine"].astype(str) == engine
    if family is not None:
        mask &= df["family"].astype(str) == family
    if ledger is not None:
        mask &= df["ledger"].astype(str) == ledger
    if regime is not None:
        reg_mask = (
            (df["quad_hard_label"].astype(str) == regime) |
            (df["fused_risk_label"].astype(str) == regime) |
            (df["vol_regime"].astype(str) == regime) |
            (df["risk_radar_state"].astype(str) == regime)
        )
        mask &= reg_mask
    if horizon is not None:
        mask &= pd.to_numeric(df["horizon"], errors="coerce") == int(horizon)
    if symbol is not None:
        mask &= df["symbol"].astype(str) == symbol
    if scope_type is not None:
        mask &= df["scope_type"].astype(str) == scope_type
    if as_of_before is not None:
        mask &= df["as_of"].astype(str) < as_of_before
    if graded_before is not None:
        # PIT knowledge-state guard.
        #
        # Three cases for a row with null graded_at:
        #   (a) outcome_graded=False → the row is genuinely ungraded.  It existed
        #       before the cutoff and is legitimately pre-cutoff.  RETAIN.
        #   (b) outcome_graded=True, graded_at null → the row is graded but its
        #       grading timestamp was not recorded.  Passing it through the filter
        #       unconditionally is a look-ahead leak (we don't know WHEN it was
        #       graded — it may have been graded after the cutoff).  EXCLUDE.
        #       Note: adapt_spine() backfills graded_at = as_of+horizon for spine
        #       rows, so case (b) only arises if a new adapter omits the backfill.
        #
        # Rows with a known graded_at pass only if graded_at < cutoff (strict).
        null_graded_at = df["graded_at"].isna() | (df["graded_at"].astype(str).isin({"None", "nan", ""}))
        is_graded = df["outcome_graded"].fillna(False).map(
            lambda x: bool(x) if x is not None else False
        )
        # Retain if: has timestamp AND it's before cutoff
        has_timestamp_before = (~null_graded_at) & (df["graded_at"].astype(str) < graded_before)
        # Retain ungraded rows with no timestamp (legitimately pre-cutoff)
        ungraded_no_timestamp = null_graded_at & (~is_graded)
        mask &= has_timestamp_before | ungraded_no_timestamp
    if graded_only:
        graded_col = df["outcome_graded"].fillna(False)
        try:
            graded_col = graded_col.astype(bool)
        except (TypeError, ValueError):
            graded_col = graded_col.map(lambda x: bool(x) if x is not None else False)
        mask &= graded_col

    return df[mask].copy().reset_index(drop=True)


# ---------------------------------------------------------------------------
# ADAPTER h) reflexes (Neural Web W6a)
# ---------------------------------------------------------------------------

def adapt_reflexes(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt ``data/reflexes/<name>/firings.jsonl`` files → ledger='reflexes'.

    GRADING DESIGN — UNGRADED-HONEST
    ---------------------------------
    All reflex firings ship as ``outcome_graded=False``.  Reflexes are
    operational event records, not calibrated forward-return predictions.
    Grading design is documented as future work:

      - Infrastructure reflexes (e.g. regime_stale_selfheal, circuit_breaker_trip):
        direction=0, ungradeable by design.  Even if a grading study were
        desired, the relevant outcome would be operational (did the engine catch
        up?) not a financial return.

      - Signal reflexes (e.g. commodity_shock, btc_flash_crash): direction
        carried from the event (±1); a forward-return study could in principle
        be pre-registered against a commodity ETF / BTC bench.  That study is
        DEFERRED to a post-W6 gauntlet.  No grading is fabricated here.

    The ``outcome_graded=False`` path in the spine query layer's graded_before
    filter retains these rows correctly as "legitimately pre-cutoff candidates"
    (they existed before the cutoff and have not yet been graded).

    SCOPE TYPE MAPPING
    ------------------
    Firing records carry ``scope_type`` from the event payload.  Accepted values:
    'macro', 'entity', 'sector', 'basket'.  Anything else is normalised to 'macro'.

    Returns (df, gap_notes).
    """
    gaps: list[str] = []

    try:
        from engine.neuralweb.reflexes import discover_all_firings  # noqa: PLC0415
        all_firings = discover_all_firings(root)
    except Exception as e:  # noqa: BLE001 — fail-open
        gaps.append(f"reflexes: discover_all_firings failed ({e}) — zero rows")
        return _empty_df(), gaps

    if not all_firings:
        gaps.append("reflexes: no firings.jsonl files found under data/reflexes/ — zero rows")
        return _empty_df(), gaps

    _VALID_SCOPE = {"macro", "entity", "sector", "basket"}
    rows: list[dict] = []
    skipped = 0

    for name, records in all_firings.items():
        if not records:
            continue
        for rec in records:
            ts = rec.get("ts") or rec.get("asof") or ""
            asof = _str_date(rec.get("asof") or ts)
            if not asof:
                skipped += 1
                continue

            claim_id = _safe_str(rec.get("claim_id"))
            trigger_key = _safe_str(rec.get("trigger_key")) or ""
            sig = f"reflexes:{name}:{asof}:{claim_id or trigger_key}"

            scope_raw = _safe_str(rec.get("scope_type")) or "macro"
            scope_type = scope_raw if scope_raw in _VALID_SCOPE else "macro"

            direction = rec.get("direction")
            try:
                direction = int(direction) if direction is not None else 0
            except (TypeError, ValueError):
                direction = 0

            horizon = rec.get("horizon_d")
            try:
                horizon = int(horizon) if horizon is not None else None
            except (TypeError, ValueError):
                horizon = None

            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]      = sig
            row["engine"]         = f"reflex.{name}"
            row["family"]         = f"reflex.{name}:{_safe_str(rec.get('trigger_type')) or 'event'}"
            row["ledger"]         = "reflexes"
            row["as_of"]          = asof
            row["symbol"]         = _safe_str(rec.get("scope_key")) or "macro"
            row["scope_type"]     = scope_type
            row["universe"]       = f"reflexes.{name}"
            row["horizon"]        = horizon
            row["direction"]      = direction
            row["size_binding"]   = False
            row["fill_basis"]     = "reflex_event"
            row["score"]          = None
            row["outcome_excess"] = None
            # UNGRADED-HONEST: outcome_graded=False for all reflex firings.
            # Grading design is documented above; no fabrication.
            row["outcome_graded"] = False
            row["graded_at"]      = None
            rows.append(row)

    if skipped:
        gaps.append(f"reflexes: {skipped} firing records skipped (no asof/ts)")

    total_records = sum(len(v) for v in all_firings.values())
    gaps.append(
        f"reflexes: {len(all_firings)} streams, {total_records} total records, "
        f"{len(rows)} rows emitted"
    )

    if not rows:
        return _empty_df(), gaps

    df = pd.DataFrame(rows)
    return _ensure_columns(df), gaps


# ---------------------------------------------------------------------------
# adapt_options_entry — Options→NW Entry Intelligence W-B (RO-5)
# ---------------------------------------------------------------------------

def adapt_options_entry(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt ``data/options_entry/state.parquet`` → ledger='options_entry'.

    GRADING DESIGN — UNGRADED-HONEST (RO-5, OPTIONS_NW masterplan §2)
    -----------------------------------------------------------------
    The options entry state table is a display-tier per-ticker LATEST snapshot
    of raw options fields (no composites — those are REJECTED under Signal
    Commons R3 / RO-2).  Every row folds as ``outcome_graded=False`` and
    ``direction=0``: these are CONTEXT records, not directional claims.  Future
    grading joins the us_board retro_grades fwd_mfe_* columns READ-ONLY (A9
    single-writer preserved) via the harness in the options-alpha program —
    never here, and never via qledger writes (blocked until the QI co-sign).

    Fail-open: missing/unreadable state.parquet → gap note + zero rows.
    """
    gaps: list[str] = []

    path = _data_dir(root) / "options_entry" / "state.parquet"
    if not path.exists():
        gaps.append("options_entry: state.parquet absent — zero rows")
        return _empty_df(), gaps

    try:
        state = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001 — fail-open
        gaps.append(f"options_entry: state.parquet unreadable ({e}) — zero rows")
        return _empty_df(), gaps

    if state.empty:
        gaps.append("options_entry: state.parquet empty — zero rows")
        return _empty_df(), gaps

    rows: list[dict] = []
    skipped = 0
    for rec in state.to_dict("records"):
        asof = _str_date(rec.get("as_of"))
        ticker = _safe_str(rec.get("ticker"))
        if not asof or not ticker:
            skipped += 1
            continue
        row: dict[str, Any] = {c: None for c in COLUMNS}
        row["signal_id"]      = f"options_entry:{asof}:{ticker}"
        row["engine"]         = "options_entry"
        row["family"]         = "options.entry_state"
        row["ledger"]         = "options_entry"
        row["as_of"]          = asof
        row["symbol"]         = ticker
        row["scope_type"]     = "entity"
        row["universe"]       = "options_entry.state"
        row["horizon"]        = None
        # CONTEXT record: direction=0 always (RO-9: no signed-flow direction).
        row["direction"]      = 0
        row["size_binding"]   = False
        row["fill_basis"]     = "options_state"
        row["score"]          = None
        row["outcome_excess"] = None
        # UNGRADED-HONEST: outcome_graded=False for all options state rows.
        row["outcome_graded"] = False
        row["graded_at"]      = None
        row["is_context"]     = True
        rows.append(row)

    if skipped:
        gaps.append(f"options_entry: {skipped} rows skipped (no as_of/ticker)")
    gaps.append(f"options_entry: {len(rows)} context rows emitted (ungraded-honest)")

    if not rows:
        return _empty_df(), gaps
    return _ensure_columns(pd.DataFrame(rows)), gaps


# ---------------------------------------------------------------------------
# adapt_cortex_attention — W7b PR2
# ---------------------------------------------------------------------------

def adapt_cortex_attention(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt cortex attention firings + grades → ledger='cortex_attention'.

    Reads data/reflexes/cortex_attention/firings.jsonl and joins
    data/reflexes/cortex_attention/grades.jsonl by claim_id.

    When a grade exists: outcome_graded=True, graded_at=grade.graded_at,
    outcome_excess computed from outcome_hit and direction.
    Without a grade: outcome_graded=False (ungraded-honest).

    Infrastructure reflexes (direction=0) stay outcome_graded=False by design —
    ungradeable on a financial return basis.

    This makes graded attention claims queryable in the spine index with
    the standard query(graded_only=True) filter, enabling the A2 earn-in
    evidence accumulation from the spine.
    """
    gaps: list[str] = []

    if root is not None:
        root_p = Path(root)
    else:
        try:
            from lib import config as _cfg  # noqa: PLC0415
            root_p = Path(_cfg.ROOT)
        except Exception:  # noqa: BLE001
            root_p = Path(".")

    firings_path = root_p / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
    grades_path = root_p / "data" / "reflexes" / "cortex_attention" / "grades.jsonl"

    if not firings_path.exists():
        gaps.append("cortex_attention: no firings.jsonl — zero rows")
        return _empty_df(), gaps

    # Load firings
    firings_raw: list[dict] = []
    try:
        for line in firings_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                firings_raw.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        gaps.append(f"cortex_attention: firings read failed ({e}) — zero rows")
        return _empty_df(), gaps

    # Load grades (sidecar; absent until first grading run)
    grades_by_claim: dict[str, dict] = {}
    if grades_path.exists():
        try:
            for line in grades_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    g = json.loads(line)
                    cid = g.get("claim_id")
                    if cid:
                        grades_by_claim[cid] = g
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            gaps.append(f"cortex_attention: grades read failed ({e}) — using ungraded")

    _VALID_SCOPE = {"macro", "entity", "sector", "basket"}
    rows: list[dict] = []
    skipped = 0

    for rec in firings_raw:
        ts = rec.get("ts") or rec.get("asof") or ""
        asof = _str_date(rec.get("asof") or ts)
        if not asof:
            skipped += 1
            continue

        claim_id = _safe_str(rec.get("claim_id"))
        sig = (
            f"cortex_attention:{asof}:"
            f"{claim_id or _safe_str(rec.get('trigger_key')) or 'unk'}"
        )

        scope_raw = _safe_str(rec.get("scope_type")) or "macro"
        scope_type = scope_raw if scope_raw in _VALID_SCOPE else "macro"

        direction = rec.get("direction")
        try:
            direction = int(direction) if direction is not None else 0
        except (TypeError, ValueError):
            direction = 0

        horizon = rec.get("horizon_d")
        try:
            horizon = int(horizon) if horizon is not None else None
        except (TypeError, ValueError):
            horizon = None

        # Join grade if available
        grade = grades_by_claim.get(claim_id or "")
        outcome_graded = False
        outcome_excess: float | None = None
        graded_at_val = None

        if grade is not None:
            hit = bool(grade.get("outcome_hit"))
            # Infrastructure (direction=0): ungradeable by design
            if direction != 0:
                outcome_graded = True
                # ±0.01 is a SIGN PLACEHOLDER, not a real excess return.
                # The sign encodes directional correctness (hit + direction>0
                # → positive; miss + direction>0 → negative).  The magnitude
                # 0.01 is arbitrary and must NOT be used for any return or
                # volatility calculation.  Consumers needing real magnitudes
                # must read the full grade record from grades.jsonl.
                outcome_excess = 0.01 if hit else -0.01
                graded_at_val = grade.get("graded_at")
            # direction=0: stays outcome_graded=False

        row: dict[str, Any] = {c: None for c in COLUMNS}
        row["signal_id"]      = sig
        row["engine"]         = "reflex.cortex_attention"
        row["family"]         = (
            f"reflex.cortex_attention:"
            f"{_safe_str(rec.get('trigger_type')) or 'event'}"
        )
        row["ledger"]         = "cortex_attention"
        row["as_of"]          = asof
        row["symbol"]         = _safe_str(rec.get("scope_key")) or "macro"
        row["scope_type"]     = scope_type
        row["universe"]       = "cortex_attention"
        row["horizon"]        = horizon
        row["direction"]      = direction
        row["size_binding"]   = False
        row["fill_basis"]     = "cortex_attention_event"
        row["score"]          = None
        row["outcome_excess"] = outcome_excess
        row["outcome_graded"] = outcome_graded
        row["graded_at"]      = graded_at_val
        rows.append(row)

    if skipped:
        gaps.append(f"cortex_attention: {skipped} records skipped (no asof/ts)")

    gaps.append(
        f"cortex_attention: {len(firings_raw)} firings, "
        f"{len(grades_by_claim)} grades joined, "
        f"{len(rows)} rows emitted"
    )

    if not rows:
        return _empty_df(), gaps

    df_out = pd.DataFrame(rows)
    return _ensure_columns(df_out), gaps


# ---------------------------------------------------------------------------
# adapt_tech_signals — Tech-signal suite NW context feed (DARK)
# ---------------------------------------------------------------------------
# GATE: these signals are display/context only (direction=0, outcome_graded=False,
# is_context=True). Promotion to confirmer tier requires an Article-3 gauntlet
# pass (n_dates>=25, Wilson CI lower-bound > 0 vs matched control). LLMs may
# only de-escalate calibrated keys — never originate signals, scores, or
# escalations. Nothing here is wired to allocation or masterminds.
# ---------------------------------------------------------------------------

def adapt_tech_signals(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt ``site/factordata/tech_lab.json`` → ledger='tech_signals'.

    DARK — NW CONTEXT FEED (tech-signal suite W2)
    ----------------------------------------------
    Registers per-signal descriptive fire-metrics from ``engine.tech_catalog``
    as display/context rows in the spine index.  Every row carries:

      direction=0           — no directional claim; purely descriptive state
      outcome_graded=False  — UNGRADED-HONEST; no §3 gauntlet has passed
      is_context=True       — catch-all context flag per W1 R8

    PROMOTION GATE: a signal family may only be promoted from display →
    confirmer after an Article-3 gauntlet with n_dates>=25 and Wilson CI
    lower-bound > 0 vs a matched control.  Until that gate fires, these rows
    are invisible to every Article-2 surface (alert_triage, board_ordering,
    top_setups, attention_queue, push_floor).

    Fail-open: missing or unreadable tech_lab.json → gap note + zero rows.
    The artifact is DARK at registration time (site/factordata/tech_lab.json
    may not yet exist on a fresh clone); zero rows is the correct behaviour.
    """
    gaps: list[str] = []

    if root is not None:
        root_p = Path(root)
    else:
        try:
            from lib import config as _cfg  # noqa: PLC0415
            root_p = Path(_cfg.ROOT)
        except Exception:  # noqa: BLE001
            root_p = Path(".")

    path = root_p / "site" / "factordata" / "tech_lab.json"
    if not path.exists():
        gaps.append("tech_signals: site/factordata/tech_lab.json absent — zero rows (DARK)")
        return _empty_df(), gaps

    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"tech_signals: tech_lab.json unreadable ({e}) — zero rows")
        return _empty_df(), gaps

    # Extract top-level asof from generated_utc (ISO string → date prefix)
    asof_raw = payload.get("generated_utc") or ""
    asof = _str_date(asof_raw) if asof_raw else None
    if not asof:
        gaps.append("tech_signals: missing generated_utc — zero rows")
        return _empty_df(), gaps

    signals: dict = payload.get("signals") or {}
    if not signals:
        gaps.append("tech_signals: no signals block in tech_lab.json — zero rows")
        return _empty_df(), gaps

    rows: list[dict] = []
    for sig_name, sig_meta in signals.items():
        if not isinstance(sig_meta, dict):
            continue
        row: dict[str, Any] = {c: None for c in COLUMNS}
        row["signal_id"]      = f"tech_signals:{asof}:{sig_name}"
        row["engine"]         = "tech_signals"
        row["family"]         = f"tech.{sig_name}"
        row["ledger"]         = "tech_signals"
        row["as_of"]          = asof
        row["symbol"]         = sig_name          # signal name as the "symbol" key
        row["scope_type"]     = "basket"           # cross-sectional; not a single entity
        row["universe"]       = "tech_signals.lab"
        row["horizon"]        = None
        # CONTEXT record: direction=0 always — no directional claim (DARK gate)
        row["direction"]      = 0
        row["size_binding"]   = False
        row["fill_basis"]     = "tech_lab_snapshot"
        row["score"]          = None   # DARK context row carries no score (matches adapt_options_entry)
        row["outcome_excess"] = None
        # UNGRADED-HONEST: outcome_graded=False until §3 gauntlet passes
        row["outcome_graded"] = False
        row["graded_at"]      = None
        row["is_context"]     = True
        rows.append(row)

    gaps.append(
        f"tech_signals: {len(rows)} context rows emitted from tech_lab.json "
        f"(asof={asof}, DARK — direction=0, ungraded-honest)"
    )

    if not rows:
        return _empty_df(), gaps
    return _ensure_columns(pd.DataFrame(rows)), gaps
