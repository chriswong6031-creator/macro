"""engine/cycle_pattern/lake.py — Unified monthly PIT research panel.

UNION of the three monthly cycle backfills (US sector, country, China Shenwan),
mapped onto the shared entity registry (registry.py) and LEFT-JOINed to the
hazard-panel FEATURE columns. Labels (y1/y3/y6/event_date) and hazard
probabilities are deliberately excluded — labels live in outcomes, never in
state (doctrine), and retro hazard scoring is a later preregistered wave.

Row identity is (entity_id, date). China backfill lacks the v2/stance/
divergence/overdue/basis columns; those are filled NaN/None and the affected
rows carry china_schema_v0=True.

Binding contract:
  - Join key against hazard is (native_id UPPERCASE, month-end date). US and
    country ids join 100%; China rows on dates/ids the hazard panel had not yet
    begun tracking join to NaN (a real left-join miss, not a defect).
  - hazard_epoch = 'price_c4414dcb' on joined rows, else None.
  - No sklearn/statsmodels/scipy.stats. Pure pandas joins, no engine recompute.

Monthly oscillator columns (Wave 0 preregistration substrate):
  mmacd_hist, mmacd_sign, mmacd_slope  — monthly RSI-MACD histogram & derivatives
  mstoch_k, mstoch_d                   — monthly StochRSI K and D (0-100 scale)
  osc_missing                          — True when oscillators cannot be computed

PINNED MATH (nondelegable, ruling ESX-RUL-31 + RUL-33-OSCSPECIES):
  RSI-MACD = engine.confluence_tiers._rsi_macd (NEVER price macd_parts)
  StochRSI  = engine.confluence_tiers._stoch_rsi_kd (14/3/3, K&D, 0-100)
  cycles.stoch_rsi (K-only) is FORBIDDEN for scored features.
  Applied on MONTHLY-RESAMPLED ("ME") close only.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.cycle_pattern import registry

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA = _ROOT / "data"

HAZARD_EPOCH = "price_c4414dcb"
_HAZARD_PATH = _DATA / "hazard" / f"panel_{HAZARD_EPOCH}.parquet"

# Engine dir -> (family used to build entity_id, engine label, provenance path).
_ENGINE_SOURCES = {
    "sector_cycles": ("us_sector", "us_sector_cycles",
                    "data/sector_cycles/backfill.parquet"),
    "country_cycles": (None, "country_cycles",  # family split: country vs bloc
                    "data/country_cycles/backfill.parquet"),
    "china_sector_cycles": ("cn_sector", "china_sector_cycles",
                            "data/china_sector_cycles/backfill.parquet"),
}

# Backfill state columns carried into the lake (label/outcome columns never here).
_STATE_COLS = [
    "phase", "pos", "osc_slope", "signal", "timing_state", "above200d",
    "rs_63d", "proj_next", "proj_central", "proj_lo", "proj_hi",
    "pos_v2", "phase_v2", "stance", "divergence", "overdue", "basis",
]

# Columns the China backfill lacks (drive the china_schema_v0 gap flag).
_CHINA_GAP_COLS = ["pos_v2", "phase_v2", "stance", "divergence", "overdue", "basis"]

# Hazard FEATURE columns joined onto state. Labels y1/y3/y6/event_date and the
# leg_open_date / censored bookkeeping are intentionally excluded.
_HAZARD_FEATURES = [
    "age_m", "age_bucket", "direction", "trend_pass", "mom_score", "rs_63d",
    "vol_pctile", "amp_proxy", "log_age_ratio", "quad", "liquidity",
]

# Label/outcome columns that MUST NOT appear anywhere in the lake.
_FORBIDDEN_COLS = frozenset({"y1", "y3", "y6", "event_date"})

# --- monthly oscillator columns (Wave 0 substrate) ---
# PINNED MATH per ESX-RUL-31 + RUL-33-OSCSPECIES:
#   RSI-MACD  = confluence_tiers._rsi_macd  (14/14/60/5 RSI-MACD, NOT price MACD)
#   StochRSI  = confluence_tiers._stoch_rsi_kd (14/3/3, K&D, 0-100)
# Applied on ME-resampled close only; incomplete final month is DROPPED before
# the stamp-date slice so no future bars leak.
_OSC_COLS = [
    "mmacd_hist",   # monthly RSI-MACD histogram value  (m - signal)
    "mmacd_sign",   # +1 / -1 from histogram sign
    "mmacd_slope",  # hist[t] - hist[t-1] on monthly bars
    "mstoch_k",     # monthly StochRSI K (0-100)
    "mstoch_d",     # monthly StochRSI D (0-100)
    "osc_missing",  # True when < 40 completed monthly bars or no daily tape
]

# Minimum completed monthly bars required to produce non-missing oscillators.
_OSC_MIN_BARS = 40

# Tickers whose daily tape lives in the yahoo store under the ticker.lower() name
# (with ^/=// replaced by _).  China Shenwan sectors (801xxx) have no yahoo
# entry and are always osc_missing.
_YAHOO_ENGINE_LABELS = {"us_sector_cycles", "country_cycles"}


def _native_to_entity(entities: pd.DataFrame, engine_label: str) -> dict[str, str]:
    """UPPERCASE native_id -> entity_id, scoped to one engine."""
    sub = entities[entities["engine"] == engine_label]
    return {str(n).upper(): eid for n, eid in zip(sub["native_id"], sub["entity_id"])}


def _load_backfill(engine_dir: str, entities: pd.DataFrame) -> pd.DataFrame:
    fam, engine_label, prov = _ENGINE_SOURCES[engine_dir]
    b = pd.read_parquet(_DATA / engine_dir / "backfill.parquet")
    b = b.copy()
    b["native_id"] = b["id"].astype(str).str.upper()

    n2e = _native_to_entity(entities, engine_label)
    b["entity_id"] = b["native_id"].map(n2e)
    if b["entity_id"].isna().any():
        missing = sorted(b.loc[b["entity_id"].isna(), "native_id"].unique())
        raise ValueError(f"{engine_dir}: unmapped native ids {missing}")

    # normalized month-end date (hazard panel is strictly EOM) + raw string kept
    nd = pd.to_datetime(b["date"])
    b["date"] = (nd + pd.offsets.MonthEnd(0)).dt.normalize()

    china = engine_dir == "china_sector_cycles"
    for col in _STATE_COLS:
        if col not in b.columns:
            b[col] = np.nan
    b["china_schema_v0"] = bool(china)

    b["engine"] = engine_label
    b["source_artifact"] = prov
    # per-row basis: China backfill has no basis column -> price (measured px engine)
    if china:
        b["basis"] = "price"

    keep = ["entity_id", "native_id", "date"] + _STATE_COLS + [
        "china_schema_v0", "engine", "source_artifact"]
    return b[keep]


def _load_hazard_features() -> pd.DataFrame:
    h = pd.read_parquet(_HAZARD_PATH)
    h = h.copy()
    h["native_id"] = h["id"].astype(str).str.upper()
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    cols = ["native_id", "date"] + _HAZARD_FEATURES
    hf = h[cols].copy()
    # hazard rows are unique per (id, date); guard against silent fan-out.
    if hf.duplicated(["native_id", "date"]).any():
        hf = hf.drop_duplicates(["native_id", "date"], keep="last")
    return hf


def _compute_monthly_oscs_for_entity(
    native_id: str,
    engine_label: str,
    stamp_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Compute monthly oscillator columns for one entity across all stamp_dates.

    Returns a DataFrame indexed by stamp_date with columns _OSC_COLS.
    All values are NaN / osc_missing=True when the daily tape is unavailable
    or when too few completed monthly bars exist at the stamp date.

    PIT discipline: for stamp date t, only monthly bars whose month-end <= t
    are used.  The in-progress (incomplete) final month is DROPPED by taking
    only completed month-ends, i.e., we resample to 'ME' on the daily series
    and keep only those month-ends that are strictly before t (i.e., < t +
    1 day, equivalent to month_end <= t since our stamp dates ARE month-ends).

    PINNED MATH per ESX-RUL-31 + RUL-33-OSCSPECIES:
      RSI-MACD histogram via confluence_tiers._rsi_macd (FORBIDDEN: price macd_parts)
      StochRSI K/D via confluence_tiers._stoch_rsi_kd (FORBIDDEN: cycles.stoch_rsi)
    Both applied on ME-resampled close only.
    """
    # Lazy import to keep the module lean (pinned per ESX-RUL-31).
    from engine.confluence_tiers import _rsi_macd, _stoch_rsi_kd  # noqa: PLC0415

    result_cols = {c: np.full(len(stamp_dates), np.nan) for c in _OSC_COLS}
    result_cols["osc_missing"] = np.ones(len(stamp_dates), dtype=bool)
    out = pd.DataFrame(result_cols, index=stamp_dates)

    # Only yahoo-backed engines have daily close via store.
    if engine_label not in _YAHOO_ENGINE_LABELS:
        # China Shenwan sectors: no yahoo tape -> always osc_missing.
        return out

    from lib import store  # noqa: PLC0415
    ticker = native_id.lower().replace("^", "_").replace("=", "_").replace("/", "_")
    df = store.read("yahoo", ticker)
    if df is None or df.empty or "close" not in df.columns:
        log.debug("osc: no daily close for %s (%s)", native_id, engine_label)
        return out

    daily_close = df["close"].sort_index().dropna()
    if daily_close.empty:
        return out

    # Monthly resample (last close of each completed month-end).
    monthly = daily_close.resample("ME").last().dropna()
    if monthly.empty:
        return out

    for i, stamp in enumerate(stamp_dates):
        # PIT: only months whose period-end <= stamp (completed bars only).
        m_pit = monthly[monthly.index <= stamp]
        n_bars = len(m_pit)
        if n_bars < _OSC_MIN_BARS:
            # Too few bars: osc_missing stays True, values stay NaN.
            continue

        # Compute RSI-MACD histogram via pinned function (ESX-RUL-31).
        macd_line, signal_line = _rsi_macd(m_pit)
        hist = macd_line - signal_line

        # Compute StochRSI K/D via pinned function (ESX-RUL-31).
        k, d = _stoch_rsi_kd(m_pit)

        # Read off the last valid value at the stamp month-end.
        h_val = hist.iloc[-1]
        k_val = k.iloc[-1]
        d_val = d.iloc[-1]

        if pd.isna(h_val) or pd.isna(k_val) or pd.isna(d_val):
            # Not enough warm-up bars after resampling; stay missing.
            continue

        # mmacd_slope: hist[t] - hist[t-1] on monthly bars.
        h_prev = hist.iloc[-2] if len(hist) >= 2 else np.nan

        out.iloc[i] = {
            "mmacd_hist": float(h_val),
            "mmacd_sign": float(np.sign(h_val)) if not pd.isna(h_val) else np.nan,
            "mmacd_slope": float(h_val - h_prev) if not pd.isna(h_prev) else np.nan,
            "mstoch_k": float(k_val),
            "mstoch_d": float(d_val),
            "osc_missing": False,
        }

    out["osc_missing"] = out["osc_missing"].astype(bool)
    return out


def _add_monthly_oscillators(state: pd.DataFrame) -> pd.DataFrame:
    """Attach monthly oscillator columns to the unified state lake in-place.

    Iterates over each unique (native_id, engine) pair; computes oscillators
    across all stamp dates for that entity; assigns into the result.  This
    is a pure computation on committed daily-close store data — no new sources.
    """
    # Pre-allocate output columns.
    state = state.copy()
    for col in _OSC_COLS:
        if col == "osc_missing":
            state[col] = True  # default missing; filled below
        else:
            state[col] = np.nan

    groups = state.groupby(["native_id", "engine"], sort=False)
    total = len(groups)
    for idx, ((native_id, engine_label), grp) in enumerate(groups):
        stamp_dates = pd.DatetimeIndex(sorted(grp["date"].unique()))
        oscs = _compute_monthly_oscs_for_entity(native_id, engine_label, stamp_dates)
        # Map results back to the state rows.
        mask = (state["native_id"] == native_id) & (state["engine"] == engine_label)
        date_to_row = {d: i for i, d in enumerate(stamp_dates)}
        for col in _OSC_COLS:
            vals = oscs[col].values
            date_col = state.loc[mask, "date"]
            osc_vals = date_col.map(lambda d, v=vals, m=date_to_row: v[m[d]])  # noqa: B023
            state.loc[mask, col] = osc_vals.values
        if (idx + 1) % 20 == 0:
            log.info("osc: %d/%d entities processed", idx + 1, total)

    state["osc_missing"] = state["osc_missing"].astype(bool)
    return state


def build_state_monthly() -> pd.DataFrame:
    """Return the unified monthly PIT panel, deterministically ordered.

    Includes monthly oscillator columns (mmacd_hist/sign/slope, mstoch_k/d,
    osc_missing) computed via pinned functions per ESX-RUL-31 + RUL-33-OSCSPECIES.
    """
    entities = registry.build_entities()

    parts = [_load_backfill(d, entities) for d in
            ("sector_cycles", "country_cycles", "china_sector_cycles")]
    state = pd.concat(parts, ignore_index=True)

    hf = _load_hazard_features()
    # hazard rs_63d would collide with the backfill's own rs_63d; suffix the join.
    merged = state.merge(
        hf, on=["native_id", "date"], how="left", suffixes=("", "_hz"),
    )
    merged["hazard_epoch"] = np.where(
        merged["age_m"].notna(), HAZARD_EPOCH, None)

    # doctrine guard: no label/outcome columns may have leaked in.
    leaked = _FORBIDDEN_COLS.intersection(merged.columns)
    if leaked:
        raise ValueError(f"label/outcome columns leaked into state lake: {sorted(leaked)}")

    # Attach monthly oscillator columns (Wave 0 substrate).
    # PINNED MATH per ESX-RUL-31 + RUL-33-OSCSPECIES.
    merged = _add_monthly_oscillators(merged)

    merged = merged.sort_values(["entity_id", "date"], kind="stable").reset_index(drop=True)
    return merged


def _meta() -> dict:
    """Column-level PIT metadata sidecar contents."""

    def col(pit_class: str, source: str) -> dict:
        return {"pit_class": pit_class, "source": source}

    meta: dict = {"_note": (
        "Rows with date > 2024-01-01 fall inside the permanently embargoed "
        "holdout and MUST NOT be used for any trial/model selection."
    ), "columns": {}}
    c = meta["columns"]

    # keys / provenance
    for k in ("entity_id", "native_id", "date"):
        c[k] = col("pit_pure", "registry+backfill key")
    c["engine"] = col("engine_stamped", "cycle-engine identity")
    c["source_artifact"] = col("pit_pure", "provenance path")
    c["china_schema_v0"] = col("pit_pure", "schema-gap flag")
    c["hazard_epoch"] = col("pit_pure", f"hazard {HAZARD_EPOCH} join marker")

    # engine-stamped cycle state (revision-sensitive engine output, PIT-stamped
    # by the backfill run but not a pure function of price alone)
    for k in ("phase", "pos", "osc_slope", "signal", "timing_state", "above200d",
            "proj_next", "proj_central", "proj_lo", "proj_hi", "pos_v2",
            "phase_v2", "stance", "divergence", "overdue", "basis"):
        c[k] = col("engine_stamped", "cycle backfill (engine stamp)")

    # backfill rs_63d (percent-point scale) is the engine's own relative-strength
    # stamp; the hazard panel carries a distinct fractional rs_63d, joined as
    # rs_63d_hz. Both are price-derived <= t (pit_pure) but not interchangeable.
    c["rs_63d"] = col("pit_pure", "backfill relative strength (pp scale)")
    c["rs_63d_hz"] = col("pit_pure", f"hazard {HAZARD_EPOCH} rs_63d (fractional)")

    # hazard FEATURES
    for k in ("age_m", "age_bucket", "direction", "trend_pass", "mom_score",
            "vol_pctile", "amp_proxy", "log_age_ratio"):
        c[k] = col("pit_pure", f"hazard {HAZARD_EPOCH} price feature")
    # quad/liquidity are revision-optimistic per P-D5-1
    c["quad"] = col("revision_optimistic", "hazard quad (P-D5-1)")
    c["liquidity"] = col("revision_optimistic", "hazard liquidity (P-D5-1)")

    # monthly oscillator columns (Wave 0 substrate; pinned math ESX-RUL-31 + RUL-33-OSCSPECIES)
    # pit_class: pit_pure — computed from daily close <= stamp date (completed months only).
    # Forbidden re-parameterizations: price macd_parts, cycles.stoch_rsi (K-only).
    for k in ("mmacd_hist", "mmacd_sign", "mmacd_slope"):
        c[k] = col("pit_pure",
                   "monthly RSI-MACD (confluence_tiers._rsi_macd, pinned ESX-RUL-31)")
    for k in ("mstoch_k", "mstoch_d"):
        c[k] = col("pit_pure",
                   "monthly StochRSI K/D (confluence_tiers._stoch_rsi_kd, pinned ESX-RUL-31)")
    c["osc_missing"] = col("pit_pure",
                           "True: <40 completed monthly bars or no daily tape (no-yahoo engines)")

    return meta


def write_meta(path: Path) -> None:
    path.write_text(json.dumps(_meta(), ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
