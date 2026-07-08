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
    "adapt_personality_context",
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
    # R5 PR-C — macro context + market routing + own-market quad (additive; None defaults)
    "macro_context_id",       # sha256[:16] of the day's macro label composite; None pre-ledger
    "macro_context_asof",     # asof of the macro snapshot that stamped this row; None pre-ledger
    "market",                 # US | CN | HK | CA | None (derived from ledger+symbol routing)
    "own_market_quad",        # national market quad for CN/HK/CA rows; None for US / macro
    "regime_stamp_basis",     # pit_live | recomputed_history | None
    # basis describes REGIME-stamp provenance (the regime= filter axis);
    # macro_context_id provenance is guaranteed separately by the max-asof
    # join-key law.  A row with a live macro_context_id whose quad was filled
    # from history is correctly 'recomputed_history'.
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

# R5 PR-C new columns — None defaults (read-time compatibility with existing parquets).
# These are NOT in _FLAG_DEFAULTS because they are nullable str/None, not bool flags.
_R5_NEW_COLS: tuple[str, ...] = (
    "macro_context_id",
    "macro_context_asof",
    "market",
    "own_market_quad",
    "regime_stamp_basis",
)

# Ledgers whose rows are reconstructed from history, not registered at live time.
# Census 2026-07-06 — track_record date==first_seen_asof match rate 0.0002;
# a per-row first_seen_asof column is docketed.
_RECONSTRUCTED_LEDGERS: frozenset[str] = frozenset({"track_record"})

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
    "macro_context",        # R5 PR-C: macro snapshot context rows (scope_type='macro')
    "personality_context",  # Stock Personality R-SP20: slim label join by ticker (display/context)
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
    R5: macro_context_id, macro_context_asof, market, own_market_quad, regime_stamp_basis
    default to None for read-time compatibility with existing parquets.
    """
    for c in COLUMNS:
        if c not in df.columns:
            if c in _R5_NEW_COLS:
                df[c] = None
            else:
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
        ("macro_context",  lambda: adapt_macro_context(root)),        # R5 PR-C — macro snapshot context rows
        ("personality_context", lambda: adapt_personality_context(root)),  # R-SP20 — slim label join
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

    # R5 PR-C — market routing: derive market for every row from (ledger, symbol).
    # Vectorised by applying _market_for_row row-wise.  None for non-market ledgers.
    if "market" in combined.columns:
        combined["market"] = [
            _market_for_row(str(r["ledger"]) if r["ledger"] is not None else None,
                            str(r["symbol"]) if r["symbol"] is not None else None)
            for _, r in combined[["ledger", "symbol"]].iterrows()
        ]

    # R5 PR-C — adapter-carried regime stamps are live-registration stamps (qledger
    # claims stamped at registration via regime_vector; board rows stamped during
    # live nightly builds).  Label them pit_live BEFORE the historical helper runs,
    # so the default regime= filter keeps the genuinely-live population.  Rows with
    # no stamps keep basis None (nothing to label).
    # NOTE: track_record rows are in _RECONSTRUCTED_LEDGERS and must NOT be labeled
    # pit_live here; _stamp_macro_context will assign 'recomputed_history' when it
    # stamps them.  The clobber gate below guards against double-labeling.
    if "regime_stamp_basis" in combined.columns:
        _stamp_cols = [
            "rate_pressure", "quad_hard_label", "fused_risk_label",
            "vol_regime", "risk_radar_state",
        ]
        _has_stamp = combined[_stamp_cols].notna().any(axis=1)
        _no_basis = combined["regime_stamp_basis"].isna()
        _not_reconstructed = ~combined["ledger"].astype(str).isin(_RECONSTRUCTED_LEDGERS)
        combined.loc[_has_stamp & _no_basis & _not_reconstructed, "regime_stamp_basis"] = "pit_live"

    # R5 PR-C — macro context stamp-join: backward merge_asof from macro snapshot ledger.
    # Stamps macro_context_id + macro_context_asof onto all rows (PIT-correct, fail-open).
    combined = _stamp_macro_context(combined, root)

    # R5 PR-C — historical quad stamps: fill quad_hard_label + own_market_quad from
    # per-market regime_history parquets (recomputed_history basis).
    combined = _stamp_historical_quads(combined, root)

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


def _stamp_macro_context(combined: pd.DataFrame, root: Path | str | None = None) -> pd.DataFrame:
    """Stamp macro_context_id and macro_context_asof onto all rows from the macro snapshot ledger.

    Backward merge_asof: each spine row gets the macro snapshot from the MOST RECENT
    snapshot day whose asof <= row's as_of (PIT-correct, no forward-look).

    DTYPE LAW (§0.5 item 9):
      1. pd.to_datetime both keys
      2. sort left table by datetime key
      3. merge_asof(direction='backward')
      4. restore string as_of

    Source: data/macro_snapshots/ledger.parquet — one row per (asof, domain,
    field); the backward merge_asof uses the unique asof index.
    If ledger.parquet absent → gap note, no-op.

    Only stamps rows where macro_context_id is currently None (non-destructive).
    Sets regime_stamp_basis='pit_live' for rows that receive a stamp, EXCEPT
    rows from _RECONSTRUCTED_LEDGERS which receive 'recomputed_history'.
    """
    if combined.empty:
        return combined

    snap_path = _data_dir(root) / "macro_snapshots" / "ledger.parquet"
    if not snap_path.exists():
        log.debug("_stamp_macro_context: ledger.parquet absent — macro_context_id stays None")
        return combined

    try:
        snap = pd.read_parquet(snap_path)
    except Exception as e:  # noqa: BLE001
        log.warning("_stamp_macro_context: ledger.parquet unreadable (%s) — no-op", e)
        return combined

    if snap.empty or "asof" not in snap.columns or "macro_context_id" not in snap.columns:
        log.debug("_stamp_macro_context: ledger.parquet empty or missing columns — no-op")
        return combined

    # Build per-asof snapshot index: one row per unique asof, most-recent macro_context_id
    snap_asofs = (
        snap[["asof", "macro_context_id"]]
        .dropna(subset=["asof", "macro_context_id"])
        .drop_duplicates(subset=["asof"], keep="last")
        .copy()
    )
    if snap_asofs.empty:
        return combined

    # DTYPE LAW
    snap_asofs["_snap_dt"] = pd.to_datetime(snap_asofs["asof"], errors="coerce")
    snap_asofs = snap_asofs.dropna(subset=["_snap_dt"]).sort_values("_snap_dt")
    snap_asofs = snap_asofs.rename(columns={"asof": "_snap_asof"})

    # Only stamp rows where macro_context_id is currently None
    needs_stamp = combined["macro_context_id"].isna()
    if not needs_stamp.any():
        return combined

    work = combined.loc[needs_stamp, ["as_of"]].copy()
    work["_as_of_dt"] = pd.to_datetime(work["as_of"], errors="coerce")
    work = work.dropna(subset=["_as_of_dt"]).sort_values("_as_of_dt")

    if work.empty:
        return combined

    try:
        merged = pd.merge_asof(
            work,
            snap_asofs[["_snap_dt", "_snap_asof", "macro_context_id"]],
            left_on="_as_of_dt",
            right_on="_snap_dt",
            direction="backward",
        )
        merged.index = work.index

        # Apply non-null results back
        stamp_mask = needs_stamp & combined.index.isin(merged.index)
        ctx_id_vals = merged["macro_context_id"].reindex(combined.index)
        ctx_asof_vals = merged["_snap_asof"].reindex(combined.index)

        notnull_ctx = ctx_id_vals.notna()
        combined.loc[stamp_mask & notnull_ctx, "macro_context_id"] = ctx_id_vals[stamp_mask & notnull_ctx]
        combined.loc[stamp_mask & notnull_ctx, "macro_context_asof"] = ctx_asof_vals[stamp_mask & notnull_ctx]
        # Set basis for rows that just received a stamp and don't have a basis yet.
        # Rows from reconstructed ledgers receive 'recomputed_history'; all others
        # receive 'pit_live' (they were registered at live time).
        no_basis = combined["regime_stamp_basis"].isna() | (
            combined["regime_stamp_basis"].astype(str).isin({"None", "nan", ""})
        )
        is_reconstructed = combined["ledger"].astype(str).isin(_RECONSTRUCTED_LEDGERS)
        combined.loc[stamp_mask & notnull_ctx & no_basis & ~is_reconstructed, "regime_stamp_basis"] = "pit_live"
        combined.loc[stamp_mask & notnull_ctx & no_basis & is_reconstructed, "regime_stamp_basis"] = "recomputed_history"

    except Exception as e:  # noqa: BLE001
        log.warning("_stamp_macro_context: merge_asof failed (%s) — no-op", e)

    return combined


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
    macro_context_id: str | None = None,
    stamp_basis: str | None = None,
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
        qualifies the row).  Default (None) returns all rows (no filter).
        Note: ``regime='pit_live'`` is NOT a valid label — pit_live is a
        stamp BASIS, not a regime label; use ``stamp_basis='pit_live'``
        for that filter.
    horizon:
        Filter by horizon (int, exact).
    symbol:
        Filter by symbol (exact).
    scope_type:
        Filter by scope_type (entity | sector | basket | macro).
    macro_context_id:
        R5 — filter by macro_context_id (sha256[:16] of macro label composite).
        Returns only rows stamped with this specific snapshot id.
    stamp_basis:
        R5 — filter by regime_stamp_basis.

        Interaction with ``regime``::

            regime=X, stamp_basis=None     → restrict regime match to pit_live rows
                                             (callers opt out via stamp_basis='any')
            regime=X, stamp_basis='any'    → no basis restriction (all rows)
            regime=X, stamp_basis='pit_live'            → pit_live rows only
            regime=X, stamp_basis='recomputed_history'  → reconstructed rows only
            regime=None, stamp_basis='pit_live'         → pit_live rows (any regime)
            regime=None, stamp_basis=None  → no basis filter

        When regime is None, stamp_basis=None applies no basis filter.
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
        # Default pit_live restriction when regime is set and no explicit basis given.
        # Callers opt out via stamp_basis='any' (no restriction) or pass an explicit value.
        if stamp_basis is None and "regime_stamp_basis" in df.columns:
            mask &= df["regime_stamp_basis"].astype(str) == "pit_live"
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
    if macro_context_id is not None:
        if "macro_context_id" in df.columns:
            mask &= df["macro_context_id"].astype(str) == macro_context_id
        else:
            # Column absent (pre-R5 index) — filter returns zero rows for safety
            mask &= pd.Series([False] * len(df), index=df.index)
    if stamp_basis is not None and stamp_basis != "any":
        if "regime_stamp_basis" in df.columns:
            mask &= df["regime_stamp_basis"].astype(str) == stamp_basis
        else:
            mask &= pd.Series([False] * len(df), index=df.index)

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
# R5 PR-C helpers: market routing, historical quad stamps, macro adapter
# ---------------------------------------------------------------------------

def _market_for_row(ledger: str | None, symbol: str | None) -> str | None:
    """Derive market routing from (ledger, symbol).

    Routing rules (§6.3):
      board_hk                    → HK
      board_ca                    → CA
      board_cn                    → CN
      track_record, spine,
        options_entry              → US  (track_record verified all-US by census)
      qledger                     → by symbol suffix:
                                     .SS / .SZ → CN; .HK → HK; else → US
      macro_context               → None  (not market-specific)
      reflexes, cortex_attention,
        cycles_*                  → None  (no market-specific routing)
      None / other                → None
    """
    ledger = _safe_str(ledger) or ""
    symbol = _safe_str(symbol) or ""

    if ledger in ("board_hk",):
        return "HK"
    if ledger in ("board_ca",):
        return "CA"
    if ledger in ("board_cn",):
        return "CN"
    if ledger in ("track_record", "spine", "options_entry"):
        return "US"
    if ledger == "qledger":
        sym_upper = symbol.upper()
        if sym_upper.endswith(".SS") or sym_upper.endswith(".SZ"):
            return "CN"
        if sym_upper.endswith(".HK"):
            return "HK"
        return "US"
    # macro_context, reflexes, cortex_attention, cycles_*, etc. → None
    return None


def _stamp_historical_quads(df: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    """Fill quad_hard_label and own_market_quad from per-market regime_history parquets.

    Deterministic, build-time, inside build_index. §6.3.3.

    quad_hard_label: US quads only — fills where null from data/regime/regime_history.parquet
    (US history, 1971→). US quads stay US-primary EVERYWHERE (query.py:159 invariant).
    regime_stamp_basis set to 'recomputed_history' for these rows.

    own_market_quad: fills for market ∈ {CN, HK, CA} from matching history parquet:
      CN → data/china_regime/regime_history.parquet
      HK → data/hk_regime/regime_history.parquet
      CA → data/canada_regime/regime_history.parquet

    DTYPE LAW (§0.5 item 9): reset_index() on DatetimeIndex parquets, convert both keys
    with pd.to_datetime, sort, merge_asof(direction='backward'), restore string as_of.

    Rows outside a parquet's range stay null (no imputation).
    """
    if df.empty:
        return df

    data = _data_dir(root)

    def _merge_history(
        target_df: pd.DataFrame,
        history_path: Path,
        quad_col: str,
        dest_col: str,
    ) -> pd.DataFrame:
        """Merge regime_history onto target_df by backward merge_asof on as_of."""
        if not history_path.exists():
            return target_df
        try:
            hist = pd.read_parquet(history_path)
        except Exception as e:  # noqa: BLE001
            log.warning("_stamp_historical_quads: cannot read %s (%s)", history_path, e)
            return target_df

        if hist.empty:
            return target_df

        # Reset DatetimeIndex → plain column. An unnamed DatetimeIndex resets to a
        # column literally called "index" — name it first so the date-column
        # resolution below finds it (all four regime_history parquets are unnamed).
        if isinstance(hist.index, pd.DatetimeIndex):
            if hist.index.name is None:
                hist.index.name = "date"
            hist = hist.reset_index()

        # Resolve the date column name
        date_col = None
        for cand in ("date", "as_of", "asof"):
            if cand in hist.columns:
                date_col = cand
                break
        if date_col is None:
            log.warning("_stamp_historical_quads: no date column in %s", history_path)
            return target_df

        if quad_col not in hist.columns:
            # Try common alternatives
            for alt in ("quad", "hard_label", "quad_hard_label"):
                if alt in hist.columns:
                    quad_col = alt
                    break
            else:
                log.warning(
                    "_stamp_historical_quads: column %r absent in %s", quad_col, history_path
                )
                return target_df

        # DTYPE LAW: convert both keys to datetime, sort, merge_asof, restore string
        try:
            hist_sorted = hist[[date_col, quad_col]].copy()
            hist_sorted[date_col] = pd.to_datetime(hist_sorted[date_col], errors="coerce")
            hist_sorted = hist_sorted.dropna(subset=[date_col]).sort_values(date_col)
            hist_sorted = hist_sorted.rename(columns={date_col: "_hist_dt", quad_col: "_hist_quad"})

            # Need a mask of rows to update
            needs_update = target_df[dest_col].isna()
            if not needs_update.any():
                return target_df

            work = target_df.loc[needs_update, ["as_of"]].copy()
            work["_as_of_dt"] = pd.to_datetime(work["as_of"], errors="coerce")
            work = work.dropna(subset=["_as_of_dt"]).sort_values("_as_of_dt")

            if work.empty:
                return target_df

            merged = pd.merge_asof(
                work,
                hist_sorted,
                left_on="_as_of_dt",
                right_on="_hist_dt",
                direction="backward",
            )

            # Restore original index
            merged.index = work.index
            # Apply to target_df
            update_mask = needs_update & target_df.index.isin(merged.index)
            quad_values = merged["_hist_quad"].reindex(target_df.index)
            target_df.loc[update_mask, dest_col] = quad_values[update_mask]

            # Set basis for rows that got filled
            filled_mask = update_mask & target_df[dest_col].notna()
            target_df.loc[filled_mask, "regime_stamp_basis"] = "recomputed_history"

        except Exception as e:  # noqa: BLE001
            log.warning("_stamp_historical_quads: merge failed for %s (%s)", history_path, e)

        return target_df

    # 1. Fill quad_hard_label for ALL rows with null quad_hard_label
    #    from US history parquet (US quads are US-primary on every lane)
    us_hist_path = data / "regime" / "regime_history.parquet"
    df = _merge_history(df, us_hist_path, "quad", "quad_hard_label")

    def _apply_subset(
        target_df: pd.DataFrame,
        market_val: str,
        hist_path: Path,
        quad_col: str,
        dest_col: str,
    ) -> pd.DataFrame:
        """Apply _merge_history on the subset matching market_val, write results back."""
        market_mask = target_df["market"] == market_val
        if not market_mask.any():
            return target_df
        subset = target_df[market_mask].copy()
        subset = _merge_history(subset, hist_path, quad_col, dest_col)
        # Write own_market_quad back using reindex to keep index alignment
        target_df.loc[market_mask, dest_col] = subset[dest_col].reindex(
            target_df.loc[market_mask].index
        )
        # Write regime_stamp_basis back for rows that got filled
        basis_vals = subset["regime_stamp_basis"].reindex(target_df.loc[market_mask].index)
        filled = basis_vals.notna()
        target_df.loc[target_df.index[market_mask][filled], "regime_stamp_basis"] = (
            basis_vals[filled].values
        )
        return target_df

    # 2. Fill own_market_quad for CN rows
    cn_hist_path = data / "china_regime" / "regime_history.parquet"
    df = _apply_subset(df, "CN", cn_hist_path, "quad", "own_market_quad")

    # 3. Fill own_market_quad for HK rows
    hk_hist_path = data / "hk_regime" / "regime_history.parquet"
    df = _apply_subset(df, "HK", hk_hist_path, "quad", "own_market_quad")

    # 4. Fill own_market_quad for CA rows
    ca_hist_path = data / "canada_regime" / "regime_history.parquet"
    df = _apply_subset(df, "CA", ca_hist_path, "quad", "own_market_quad")

    return df


def adapt_macro_context(
    root: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt data/macro_snapshots/ledger.parquet → ledger='macro_context'.

    ADAPTER PATTERN: follows adapt_options_entry (ungraded-honest context rows).
    One row per (asof, domain) from ledger.parquet.

    signal_id: 'macro_context:{asof}:{domain}'
    ledger: 'macro_context'
    engine: 'macro_context'
    scope_type: 'macro'  (pre-declared vocabulary at query.py COLUMNS, first population)
    direction: 0  (context rows)
    is_context: True
    horizon: 0  (context, no trading-day horizon)
    regime_stamp_basis: 'pit_live'
    market: None  (not market-specific)

    us_* regime stamps are injected from the day's labels where present.

    Fail-open: absent/unreadable ledger.parquet → gap note + zero rows.
    """
    gaps: list[str] = []

    ledger_path = _data_dir(root) / "macro_snapshots" / "ledger.parquet"
    if not ledger_path.exists():
        gaps.append("macro_context: data/macro_snapshots/ledger.parquet absent — zero rows")
        return _empty_df(), gaps

    try:
        ledger_df = pd.read_parquet(ledger_path)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"macro_context: ledger.parquet unreadable ({e}) — zero rows")
        return _empty_df(), gaps

    if ledger_df.empty:
        gaps.append("macro_context: ledger.parquet empty — zero rows")
        return _empty_df(), gaps

    # Group by (asof, domain) — emit one row per group
    # Pivot field→value within each (asof, domain) pair to build a mini dict
    # Then extract us_* stamps from the 'us' domain for regime stamp injection.

    # First build a lookup: asof → {domain → {field: value}}
    asof_domain_map: dict[str, dict[str, dict[str, Any]]] = {}
    for _, r in ledger_df.iterrows():
        asof = _str_date(r.get("asof")) or ""
        domain = _safe_str(r.get("domain")) or ""
        field = _safe_str(r.get("field")) or ""
        value = _safe_str(r.get("value"))
        macro_context_id = _safe_str(r.get("macro_context_id"))
        if not asof or not domain:
            continue
        asof_domain_map.setdefault(asof, {}).setdefault(domain, {})[field] = value
        # Attach macro_context_id to the asof level
        if "macro_context_id" not in asof_domain_map[asof]:
            asof_domain_map[asof]["macro_context_id"] = macro_context_id

    rows: list[dict] = []
    for asof, domain_map in asof_domain_map.items():
        ctx_id = domain_map.pop("macro_context_id", None)
        # us stamps for regime injection
        us_fields = domain_map.get("us") or {}

        for domain, field_vals in domain_map.items():
            sig = f"macro_context:{asof}:{domain}"
            row: dict[str, Any] = {c: None for c in COLUMNS}
            row["signal_id"]         = sig
            row["engine"]            = "macro_context"
            row["family"]            = domain
            row["ledger"]            = "macro_context"
            row["as_of"]             = asof
            row["symbol"]            = domain
            row["scope_type"]        = "macro"
            row["universe"]          = "macro_context"
            row["horizon"]           = 0
            row["direction"]         = 0
            row["size_binding"]      = False
            row["fill_basis"]        = "macro_snapshot"
            row["score"]             = None
            row["outcome_excess"]    = None
            row["outcome_graded"]    = False
            row["graded_at"]         = None
            row["is_context"]        = True
            row["macro_context_id"]  = ctx_id
            row["macro_context_asof"] = asof
            row["market"]            = None
            row["own_market_quad"]   = None
            row["regime_stamp_basis"] = "pit_live"

            # Inject us_* regime stamps from the day's 'us' domain labels
            row["quad_hard_label"]  = us_fields.get("us_quad")
            row["fused_risk_label"] = us_fields.get("us_fused_risk")
            row["vol_regime"]       = us_fields.get("us_vol_regime")
            row["risk_radar_state"] = us_fields.get("us_risk_radar")
            row["rate_pressure"]    = us_fields.get("us_rate_pressure")

            rows.append(row)

    if not rows:
        gaps.append("macro_context: no (asof, domain) pairs found — zero rows")
        return _empty_df(), gaps

    gaps.append(f"macro_context: {len(rows)} context rows emitted (ungraded-honest)")
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
# adapt_personality_context — Stock Personality R-SP20
# ---------------------------------------------------------------------------

def adapt_personality_context(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Adapt site/factordata/stock_personality.json → ledger='personality_context'.

    DISPLAY/CONTEXT ONLY (R-SP19/R-SP20)
    -------------------------------------
    Joins slim personality labels (chart labels, modes, archetype) onto spine
    rows by ticker from the site aggregate.  Every row folds as
    ``outcome_graded=False``, ``direction=0``: these are CONTEXT records, not
    directional claims, and carry no size_binding (R-SP19 descriptive tier).

    Cortex may cite these labels in de-escalation memos (R-SP20); labels may
    never originate, score, rank, or escalate (R-SP19 NEVER guarantees).

    Field mapping from per_ticker:
      arch      → archetype (spine "archetype" column)
      chart[0]  → symbol suffix slot; emitted in signal_id only
      modes[0]  → emitted in family field for cortex query surface

    Fail-open: missing/unreadable aggregate → gap note + zero rows.
    """
    gaps: list[str] = []

    if root is not None:
        data_root = Path(root)
    else:
        data_root = Path(__file__).resolve().parent.parent.parent

    path = data_root / "site" / "factordata" / "stock_personality.json"
    if not path.exists():
        gaps.append("personality_context: stock_personality.json absent — zero rows")
        return _empty_df(), gaps

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        gaps.append(f"personality_context: stock_personality.json unreadable ({e}) — zero rows")
        return _empty_df(), gaps

    if not isinstance(raw, dict):
        gaps.append("personality_context: aggregate not a dict — zero rows")
        return _empty_df(), gaps

    per_ticker: dict = raw.get("per_ticker") or {}
    if not per_ticker:
        gaps.append("personality_context: per_ticker empty — zero rows")
        return _empty_df(), gaps

    as_of_global = _str_date(raw.get("as_of"))

    rows: list[dict] = []
    skipped = 0

    for ticker, rec in per_ticker.items():
        if not isinstance(rec, dict):
            skipped += 1
            continue
        asof = as_of_global
        if not asof:
            skipped += 1
            continue

        # Slim label extraction (chart first, then modes, then archetype)
        arch = _safe_str(rec.get("arch"))
        charts: list[str] = [c for c in (rec.get("chart") or []) if isinstance(c, str)]
        modes: list[str] = [m for m in (rec.get("modes") or []) if isinstance(m, str)]

        primary_chart = charts[0] if charts else None
        primary_mode = modes[0] if modes else None

        family_label = (
            f"personality.{primary_mode}" if primary_mode
            else "personality.normal"
        )

        sig = f"personality_context:{asof}:{ticker}"

        row: dict[str, Any] = {c: None for c in COLUMNS}
        row["signal_id"]      = sig
        row["engine"]         = "stock_personality"
        row["family"]         = family_label
        row["ledger"]         = "personality_context"
        row["as_of"]          = asof
        row["symbol"]         = ticker
        row["scope_type"]     = "entity"
        row["universe"]       = "personality_context"
        row["horizon"]        = None
        row["direction"]      = 0           # CONTEXT record: never directional
        row["size_binding"]   = False
        row["fill_basis"]     = "personality_site_aggregate"
        row["score"]          = None
        row["outcome_excess"] = None
        row["outcome_graded"] = False       # UNGRADED-HONEST by design
        row["graded_at"]      = None
        row["is_context"]     = True
        row["archetype"]      = arch        # slim label for cortex surface
        rows.append(row)

    if skipped:
        gaps.append(f"personality_context: {skipped} rows skipped (no asof/rec)")
    gaps.append(f"personality_context: {len(rows)} context rows emitted (ungraded-honest)")

    if not rows:
        return _empty_df(), gaps
    return _ensure_columns(pd.DataFrame(rows)), gaps
