"""engine/neuralweb/bottom_sensors.py — Bottom-sensor envelope for the US board.

Amendment 1, Lane B0, PR-1 (envelope + labels_v1) + PR-3 (sponsorship connector).
Display-only — is_display_only=True.  labels_version=labels_v1.
Ranks nothing, gates nothing, alerts nothing.

Source-of-truth document: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md §C2, §C3.

Bind-first law (Amendment §C2 ⟦RV⟧):
  Every field that an existing engine already emits is BOUND read-only from its
  authoritative artifact.  Exactly two new computed columns are introduced here:
    - dist_21d_low_pct  : pct distance of current close above rolling 21-day low
    - dist_126d_high_pct: pct distance of current close below rolling 126-day high
  These are the ONLY rolling operations on price series in this module.

Field sources (source_artifacts column in output):
  trigger_tier / trigger_age_ticks  → site/factordata/signal_gate.json
  coiled / star / coiled_fire       → site/factordata/us_standouts.json (buy rows)
  donor_state                       → site/factordata/us_standouts.json (.donor)
  entry_quality_band                → site/factordata/us_standouts.json (conviction.potential.band)
  squeeze_state                     → site/factordata/us_standouts.json (conviction.vol_squeeze.state)
  hold_state (BIND from hold.py)    → site/factordata/us_standouts.json (.hold)
  knife (for KNIFE_RISK fallback)   → site/factordata/us_standouts.json (conviction.alignment.knife)
  bars_to_cross                     → site/factordata/signal_gate.json and us_standouts
  earnings_next_date/days_to        → data/earnings/earnings.parquet
  dist_21d_low_pct                  → computed here (rolling 21d; close series from data/stocks/*.parquet)
  dist_126d_high_pct                → computed here (rolling 126d; close series from data/stocks/*.parquet)
  decline_herf / decline_geometry   → computed here (Amendment 3 family E, DISPLAY-CANDIDATE):
                                       decline_herf = latest trailing-63-bar loss-Herfindahl bound from
                                       engine.entry_primitives.decline_concentration_series (leak-tested);
                                       decline_geometry = current-day cross-sectional tercile label
                                       (flush / mixed / grind).  A decline-SHAPE read, display-only, NOT
                                       an escalation.  CHIP-blocked until the true eq_band lands (RUL-28).
  underwater_bars / underwater_state → computed here (Amendment 3 family F, ADVERSE-CONTEXT, shadow-only):
                                       underwater_bars = latest bars-since-trailing-252-peak bound from
                                       engine.entry_primitives.time_underwater_series; underwater_state =
                                       cross-sectional tercile label (short / mid / long).  Caution context
                                       (long underwater = historically higher stop-out); de-escalation-
                                       eligible only, never a buy signal.  Not surfaced on the QA page.
  sponsorship_state                 → computed here (Amendment §C3); reads data/oracle/panel_s.parquet
                                       and data/oracle/panel_m.parquet; stock→sector/subsector map
                                       from engine/neuralweb/sector_map.py (existing repo stores only)
  rs_repair_state                   → stamped unavailable (W0.4 of #1302 not yet shipped)

KNIFE condition binding law (Amendment §C2):
  The _ALIGN_KNIFE_BLOCK constant (cycles.py: _ALIGN_KNIFE_BLOCK = 0.7) defines the
  HARD-exclude threshold.  When the alignment.knife field is available from us_standouts
  (bound from scripts/build_stock_library.py ~2030 where it is computed via washout()),
  we bind it.  When absent (name not in us_standouts), we fall back to dist_126d_high_pct
  >= 15% AND dist_21d_low_pct < 0 (close below 21d low), exactly per the Amendment.

Sponsorship state definition (Amendment §C3, FROZEN — no tuning):
  vel = vel_1m; accel = accel column (Oracle-emitted: vel_1w − vel_3m per panel.py:286;
  bound read-only — NOT the derivative of vel_1m).  At the latest completed date in
  panel_s (sector arm) or panel_m (subsector arm, 2021+ only).  Sector arm is primary;
  subsector arm is fallback.  A stale sector arm (> 5 trading days old) short-circuits
  without falling through to subsector.
    tailwind    : vel > 0 AND accel > 0
    headwind    : vel < 0 AND accel < 0
    neutral     : mixed signs
    stale       : latest panel row older than 5 trading days (date-age gate only)
    unavailable : unmapped ticker, OR vel_1m/accel is NaN on an otherwise-fresh row

Never raises publicly.  All failures degrade gracefully (return empty frame / partial rows).
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.entry_primitives import (
    decline_concentration_series,
    time_underwater_series,
)
from engine.neuralweb.sector_map import SectorMapping, build_sector_map
from engine.stock_fundamentals import _leverage_ratios, _load_statements

log = logging.getLogger(__name__)

# ── Labels version (frozen in this PR) ────────────────────────────────────────
LABELS_VERSION = "labels_v1"
IS_DISPLAY_ONLY = True
REGION = "US"

# ── Amendment 3 structural descriptors (family E display + family F shadow) ───
# Bound from the leak-tested engine.entry_primitives series; display/shadow only,
# CHIP-blocked until the true eq_band lands (RUL-28).  Terciles are assigned on
# the CURRENT-day cross-section in assemble() using the research cut semantics
# (scripts/research/_a3_common.assign_trailing_tercile): pct 33.33/66.67,
# val<=q33 → low, val<=q67 → mid, else → high.
_DECLINE_WINDOW = 63
_DECLINE_MIN_DOWN_DAYS = 8
_UNDERWATER_WINDOW = 252
_XSEC_TERCILE_MIN_NAMES = 30    # min computable cross-section before terciles assigned
_TERCILE_Q_LO = 33.33
_TERCILE_Q_HI = 66.67

# ── Path helpers ─────────────────────────────────────────────────────────────
def _repo_root() -> Path:
    """Repo root: three levels up from engine/neuralweb/bottom_sensors.py."""
    return Path(__file__).resolve().parent.parent.parent


def _site_factordata(root: Path) -> Path:
    return root / "site" / "factordata"


def _data_neuralweb(root: Path) -> Path:
    return root / "data" / "neuralweb"


def _site_neuralwebdata(root: Path) -> Path:
    return root / "site" / "neuralwebdata"


def _data_stocks(root: Path) -> Path:
    return root / "data" / "stocks"


def _data_earnings(root: Path) -> Path:
    return root / "data" / "earnings" / "earnings.parquet"


def _data_dilution(root: Path) -> Path:
    return root / "data" / "edgar" / "dilution_events.parquet"


# ── Knife threshold (bind from cycles.py; never reimport to avoid circular) ───
_ALIGN_KNIFE_BLOCK = 0.7   # mirrors engine/cycles.py:1892

# ── EVENT_BLACKOUT window (per Amendment §C2 overlay rule) ───────────────────
_BLACKOUT_DAYS = 3  # earnings within <= 3 trading days


# ── Source loading ─────────────────────────────────────────────────────────────

def _load_signal_gate(root: Path) -> tuple[dict[str, dict], str]:
    """Load site/factordata/signal_gate.json.
    Returns (verdicts_dict, as_of_str).  Never raises (returns {}, "" on failure).
    """
    path = _site_factordata(root) / "signal_gate.json"
    try:
        with open(path) as fh:
            raw = json.load(fh)
        verdicts = raw.get("verdicts") or {}
        as_of = raw.get("as_of") or ""
        return verdicts, str(as_of)
    except Exception as exc:  # noqa: BLE001
        log.warning("signal_gate.json load failed: %s", exc)
        return {}, ""


def _load_us_standouts(root: Path) -> dict:
    """Load site/factordata/us_standouts.json.
    Returns the full dict (with 'buy', 'watch', 'laggards', 'donor').
    Never raises (returns {} on failure).
    """
    path = _site_factordata(root) / "us_standouts.json"
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log.warning("us_standouts.json load failed: %s", exc)
        return {}


def _load_earnings(root: Path) -> pd.DataFrame:
    """Load data/earnings/earnings.parquet.
    Index = ticker.  Columns: next_date (str), as_of (str), etc.
    Never raises (returns empty DataFrame on failure).
    """
    path = _data_earnings(root)
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings.parquet load failed: %s", exc)
        return pd.DataFrame()


# ── Dilution event helpers (nwqs-c; display-only, RENDER_NO_DRIP convention) ──

_SHELF_FORMS = {"S-3", "S-3ASR", "S-3/A"}
_TAKEDOWN_FORMS = {"424B1", "424B2", "424B3", "424B4", "424B5"}


def _load_dilution_index(root: Path) -> pd.DataFrame:
    """Load data/edgar/dilution_events.parquet.

    RENDER_NO_DRIP convention: absent parquet → return empty DataFrame.
    The parquet will be absent on CI runners and fresh render paths; all
    consumers must degrade gracefully to None columns (never fabricate 0).
    Never raises.
    """
    path = _data_dilution(root)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
        # Ensure filing_date is datetime so we can do date arithmetic.
        if "filing_date" in df.columns:
            df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("dilution_events.parquet load failed: %s", exc)
        return pd.DataFrame()


def _build_dilution_index(dilution_df: pd.DataFrame) -> dict[str, dict]:
    """Pre-index dilution events by ticker for O(1) per-ticker lookup.

    Returns dict[ticker → {
        'latest_shelf': Timestamp | None,
        'latest_takedown': Timestamp | None,
        'dates': list[Timestamp],          # all events regardless of form
    }].

    Unmapped rows (ticker=None/NaN) are excluded; they cannot be consumed.
    """
    if dilution_df.empty or "ticker" not in dilution_df.columns:
        return {}
    # Drop unmapped rows
    df = dilution_df.dropna(subset=["ticker"])
    if df.empty:
        return {}
    index: dict[str, dict] = {}
    for ticker, grp in df.groupby("ticker", sort=False):
        shelf = grp[grp["form"].isin(_SHELF_FORMS)]
        takedown = grp[grp["form"].isin(_TAKEDOWN_FORMS)]
        latest_shelf = shelf["filing_date"].max() if not shelf.empty else None
        latest_takedown = takedown["filing_date"].max() if not takedown.empty else None
        all_dates = grp["filing_date"].dropna().tolist()
        index[str(ticker)] = {
            "latest_shelf": latest_shelf,
            "latest_takedown": latest_takedown,
            "dates": all_dates,
        }
    return index


def _dilution_fields(
    ticker: str,
    dilution_index: dict[str, dict],
    today: datetime.date,
) -> tuple[int | None, int | None, int | None]:
    """Return (days_since_shelf, days_since_takedown, dilution_events_365d) for a ticker.

    RENDER_NO_DRIP convention:
      - dilution_index empty (parquet absent) → (None, None, None).
      - ticker not in index → (None, None, None).
      - Date present but NaT → field = None.
    Never fabricates 0 for missing data.
    """
    if not dilution_index:
        return None, None, None
    entry = dilution_index.get(ticker)
    if entry is None:
        return None, None, None

    def _days(ts) -> int | None:
        if ts is None or (hasattr(ts, "is_nat") and ts.is_nat()):
            return None
        try:
            d = pd.Timestamp(ts).date()
            return max(0, (today - d).days)
        except Exception:  # noqa: BLE001
            return None

    days_shelf = _days(entry["latest_shelf"])
    days_takedown = _days(entry["latest_takedown"])

    # Count events in the trailing 365-day window
    cutoff = pd.Timestamp(today) - pd.Timedelta(days=365)
    dates_365 = [d for d in entry["dates"] if pd.notna(d) and pd.Timestamp(d) >= cutoff]
    events_365: int | None = len(dates_365) if entry["dates"] else None

    return days_shelf, days_takedown, events_365


def _data_oracle(root: Path) -> Path:
    return root / "data" / "oracle"


# ── Oracle panel loading (read-only; sponsorship connector) ───────────────────

def _load_oracle_panel(root: Path, filename: str) -> pd.DataFrame | None:
    """Load data/oracle/{filename}.  Returns DataFrame with MultiIndex[node, date]
    or None on failure.

    The panels are loaded once per assemble() call and passed through; this function
    is the single load path so callers never need to handle IOErrors directly.
    """
    path = _data_oracle(root) / filename
    try:
        df = pd.read_parquet(path)
        # Ensure date level is datetime
        if "date" in df.index.names:
            new_levels = []
            for i, name in enumerate(df.index.names):
                if name == "date":
                    lv = pd.to_datetime(df.index.get_level_values(i))
                    new_levels.append(lv)
                else:
                    new_levels.append(df.index.get_level_values(i))
            df.index = pd.MultiIndex.from_arrays(new_levels, names=df.index.names)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("oracle panel load failed (%s): %s", filename, exc)
        return None


# ── Sponsorship state (Amendment §C3, FROZEN definition) ─────────────────────

# Number of trading days beyond which a panel row is considered stale.
_SPONSORSHIP_STALE_TRADING_DAYS = 5


def _sponsorship_state(
    ticker: str,
    mapping: SectorMapping | None,
    panel_s: pd.DataFrame | None,
    panel_m: pd.DataFrame | None,
    today: datetime.date,
) -> str:
    """Compute sponsorship_state for one ticker.

    Definition (frozen, §C3):
      vel = vel_1m;  accel = accel column (Oracle-emitted: vel_1w − vel_3m, bound read-only).
      Sector arm (panel_s, primary) → subsector arm (panel_m, fallback).
      tailwind    : vel > 0 AND accel > 0
      headwind    : vel < 0 AND accel < 0
      neutral     : mixed signs
      stale       : latest panel row older than 5 trading days (date-age gate; sector arm is
                    terminal — stale sector does NOT fall through to subsector arm)
      unavailable : no mapping, both panels missing/empty, OR vel_1m/accel is NaN on a
                    fresh row (data-absence, not date-staleness)

    Stale check uses numpy.busday_count (no holiday calendar; conservative per §C2 note).
    Both vel_1m AND accel must be non-null; if either is NaN on a fresh row → unavailable.
    """
    if mapping is None:
        return "unavailable"

    # Try sector arm first (deeper history), then subsector arm
    arms = [
        (mapping.sector_node, panel_s),
        (mapping.subsector_node, panel_m),
    ]

    for node, panel in arms:
        if node is None or panel is None or panel.empty:
            continue
        try:
            node_rows = panel.xs(node, level="node")
        except KeyError:
            continue
        if node_rows.empty:
            continue

        # Latest completed row
        latest_date = node_rows.index.max()
        latest = node_rows.loc[latest_date]

        # Staleness check
        stale_td = int(np.busday_count(latest_date.date(), today))
        if stale_td > _SPONSORSHIP_STALE_TRADING_DAYS:
            return "stale"

        vel = latest.get("vel_1m") if isinstance(latest, pd.Series) else None
        accel = latest.get("accel") if isinstance(latest, pd.Series) else None

        if vel is None or accel is None or (
            isinstance(vel, float) and np.isnan(vel)
        ) or (
            isinstance(accel, float) and np.isnan(accel)
        ):
            # NaN vel/accel on a fresh (date-current) row is data-absence, not date-staleness.
            # Per amendment law: "an input that does not exist is stamped unavailable."
            return "unavailable"

        vel = float(vel)
        accel = float(accel)

        if vel > 0 and accel > 0:
            return "tailwind"
        if vel < 0 and accel < 0:
            return "headwind"
        return "neutral"

    return "unavailable"


def _load_close(root: Path, ticker: str) -> pd.Series | None:
    """Load close series for a ticker from data/stocks/<TICKER>.parquet.
    Returns daily close as a DatetimeIndex pd.Series, or None on failure.
    """
    safe = ticker.replace("/", "_").replace("=", "_")
    path = _data_stocks(root) / f"{safe}.parquet"
    try:
        df = pd.read_parquet(path)
        c = df["close"] if "close" in df.columns else df.iloc[:, 0]
        c = c.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        c = c.sort_index()
        return c
    except Exception:  # noqa: BLE001
        return None


# ── Rolling distance columns (the ONLY two new computed columns) ──────────────

def _dist_21d_low_pct(close: pd.Series) -> float | None:
    """Pct distance of today's close above its 21-bar rolling low.
    > 0 means above the 21d low (the lower the number the closer to the low).
    Returns None when insufficient data.
    """
    if close is None or len(close) < 21:
        return None
    roll_min = float(close.rolling(21).min().iloc[-1])
    last_close = float(close.iloc[-1])
    if roll_min <= 0 or np.isnan(roll_min):
        return None
    return round((last_close / roll_min - 1.0) * 100.0, 2)


def _dist_126d_high_pct(close: pd.Series) -> float | None:
    """Pct distance of today's close below its 126-bar rolling high (negative or zero).
    0 = at the high; -15 = 15% below the high.
    Returns None when insufficient data.
    """
    if close is None or len(close) < 126:
        return None
    roll_max = float(close.rolling(126).max().iloc[-1])
    last_close = float(close.iloc[-1])
    if roll_max <= 0 or np.isnan(roll_max):
        return None
    return round((last_close / roll_max - 1.0) * 100.0, 2)


# ── Amendment-3 structural descriptors (bound, render-budget-safe) ────────────

def _decline_herf(close: pd.Series | None) -> float | None:
    """Latest trailing-63-bar loss-Herfindahl for one name (family E raw value).

    Binds engine.entry_primitives.decline_concentration_series on the last
    (window+1) closes.  Because that rolling apply is POSITIONAL, the trailing
    63-return window at the last bar depends only on the last 64 closes, so
    ``fn(close.tail(64)).iloc[-1]`` equals ``fn(close).iloc[-1]`` exactly — this
    is a bind of the leak-tested primitive, not a reimplemented variant, and it
    is O(1) windows instead of the full history (render-budget bind; proven by
    tests/test_bottom_sensors_a3.py).  Returns None on short/NaN.
    """
    if close is None:
        return None
    tail = close.tail(_DECLINE_WINDOW + 1)
    if len(tail) < _DECLINE_WINDOW + 1:
        return None
    try:
        val = decline_concentration_series(
            tail, window=_DECLINE_WINDOW, min_down_days=_DECLINE_MIN_DOWN_DAYS
        ).iloc[-1]
    except Exception:  # noqa: BLE001
        return None
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), 6)


def _underwater_bars(close: pd.Series | None) -> int | None:
    """Latest bars-since-trailing-252-peak for one name (family F raw value).

    Binds engine.entry_primitives.time_underwater_series on the last window
    closes; positional rolling makes ``fn(close.tail(252)).iloc[-1]`` identical
    to the full-series latest value.  Returns None on short/NaN.
    """
    if close is None:
        return None
    tail = close.tail(_UNDERWATER_WINDOW)
    if len(tail) < _UNDERWATER_WINDOW:
        return None
    try:
        val = time_underwater_series(tail, window=_UNDERWATER_WINDOW).iloc[-1]
    except Exception:  # noqa: BLE001
        return None
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return int(val)


def _assign_terciles(
    values: pd.Series,
    labels: tuple[str, str, str],
    *,
    min_names: int = _XSEC_TERCILE_MIN_NAMES,
) -> pd.Series:
    """Current-day cross-sectional tercile labels for a per-name numeric Series.

    ``values`` is symbol-indexed (NaN where uncomputable); ``labels`` =
    (low, mid, high) for terciles (val<=q33, val<=q67, val>q67).  Mirrors the
    research cut semantics (scripts/research/_a3_common.assign_trailing_tercile):
    percentiles 33.33 / 66.67, ``val<=q33 → low``, ``val<=q67 → mid``, else high.

    Returns a symbol-indexed object Series of labels; None where the value is NaN
    or where the cross-section has fewer than ``min_names`` computable values
    (terciles are not meaningful on a thin cross-section — degrade to None).
    """
    out = pd.Series([None] * len(values), index=values.index, dtype=object)
    computable = values.dropna()
    if len(computable) < min_names:
        return out
    q33 = float(np.percentile(computable.values, _TERCILE_Q_LO))
    q67 = float(np.percentile(computable.values, _TERCILE_Q_HI))
    low, mid, high = labels
    for sym, v in computable.items():
        if v <= q33:
            out.at[sym] = low
        elif v <= q67:
            out.at[sym] = mid
        else:
            out.at[sym] = high
    return out


# ── Earnings freshness ─────────────────────────────────────────────────────────

def _trading_days_to(today: datetime.date, target: datetime.date) -> int:
    """Count trading days (Mon-Fri, no holiday calendar) from today to target.

    Uses numpy.busday_count which counts business days in the half-open interval
    [today, target).  We use (today, target] semantics: a target tomorrow = 1.
    numpy.busday_count(today, target) gives the Mon-Fri days in [today, target),
    which equals 0 for same day and 1 for next business day.  We treat the target
    date itself as included (<=), so we add 1 when target is a business day.

    NOTE: No holiday calendar is applied (amendment §C2 says "trading days"
    without specifying exchange holidays; conservative approximation is stated
    in schema docs).  Direction is conservative for a hygiene veto.
    """
    bd = int(np.busday_count(today, target))
    # If target itself is a weekday, include it; if weekend it doesn't add a bd.
    if np.is_busday(target):
        bd += 1
    return max(bd, 0)


def _earnings_info(
    ticker: str,
    earnings_df: pd.DataFrame,
    today: datetime.date,
) -> tuple[str | None, int | None, bool]:
    """Return (next_date_str, days_to, is_blackout) for a ticker.

    Per-row fresh rule (Amendment §C2, masterplan §3 F1):
      - Drop passed dates (next_date <= today).
      - Blackout if trading_days_to <= _BLACKOUT_DAYS.

    `earnings_days_to` in the output reflects calendar days (for display);
    the blackout decision uses trading days per the spec.

    Returns (None, None, False) when data absent.
    """
    if earnings_df.empty or ticker not in earnings_df.index:
        return None, None, False
    try:
        row = earnings_df.loc[ticker]
        nd = row.get("next_date") if isinstance(row, pd.Series) else None
        if nd is None:
            return None, None, False
        next_dt = pd.to_datetime(nd).date()
        if next_dt <= today:
            return None, None, False
        # Calendar days for display; trading days for blackout gate
        cal_days = (next_dt - today).days
        trading_days = _trading_days_to(today, next_dt)
        blackout = trading_days <= _BLACKOUT_DAYS
        return str(next_dt), int(cal_days), blackout
    except Exception:  # noqa: BLE001
        return None, None, False


# ── Label computation (frozen labels_v1) ──────────────────────────────────────

def _classify_labels_v1(
    *,
    hold_state: str | None,
    hold_days_basing: int | None,
    hold_ret: float | None,
    trigger_tier: str | None,
    ticks: int | None,
    coiled: bool,
    dist_21d_low: float | None,
    dist_126d_high: float | None,
    bars_to_cross: float | None,
    knife_score: float | None,
    knife_available: bool,
) -> str:
    """Frozen labels_v1 decision table (Amendment §C2).

    Precedence top-down; returns state string.
    Inputs with value None mean field unavailable for that name.
    """
    # ── 1. HOLD_LAUNCHED (highest precedence) ────────────────────────────────
    # BIND: hold["state"] == "launched" (engine/hold.py:188-195)
    if hold_state == "launched":
        return "HOLD_LAUNCHED"

    # ── helpers ──────────────────────────────────────────────────────────────
    has_fresh_tier = (
        trigger_tier in ("T1", "T2", "T3")
        and ticks is not None
        and ticks <= 2
    )
    # dist_21d_low: > 0 means above the low.  <= 12 means within 12% of low.
    # "dist_21d_low <= 12%" in spec means pct distance above 21d low is <=12.
    within_12_of_low = (
        dist_21d_low is not None and dist_21d_low <= 12.0
    )
    drawdown_15_from_126d = (
        dist_126d_high is not None and dist_126d_high <= -15.0
    )

    # ── 2. FRESH_FIRE_DURABLE_CAND ───────────────────────────────────────────
    # fresh T1-T3 (ticks <= 2) AND COILED AND dist_21d_low <= 12%
    if has_fresh_tier and coiled and within_12_of_low:
        return "FRESH_FIRE_DURABLE_CAND"

    # ── 3. FRESH_FIRE_TACTICAL ───────────────────────────────────────────────
    # fresh T1-T3 (ticks <= 2) AND NOT COILED AND dist_21d_low <= 12%
    if has_fresh_tier and not coiled and within_12_of_low:
        return "FRESH_FIRE_TACTICAL"

    # ── 4. CHASE_RISK ─────────────────────────────────────────────────────────
    # T1-T3 present AND (ticks > 2 OR dist_21d_low > 12%) AND not HOLD_LAUNCHED
    # Binding law §C2: when dist_21d_low_pct is unavailable (None) we do NOT
    # treat the name as "far from the low" — that would fabricate a risk verdict.
    # Instead we only fire CHASE_RISK when dist is actually known to be > 12%.
    # A fresh-tier name with unavailable dist falls through to WATCH (degrade
    # gracefully), NOT CHASE_RISK.
    has_any_tier = trigger_tier in ("T1", "T2", "T3")
    if has_any_tier:
        ticks_stale = ticks is None or ticks > 2
        dist_far = dist_21d_low is not None and dist_21d_low > 12.0
        if ticks_stale or dist_far:
            return "CHASE_RISK"

    # ── 5. DEAD_MONEY_RISK ────────────────────────────────────────────────────
    # BIND: hold state intact/basing, days_basing 15-40, abs(ret_since_take) < 4%
    # Where hold fields absent for a name, stamp unavailable (not recomputed).
    if hold_state in ("intact",):
        if (
            hold_days_basing is not None
            and 15 <= hold_days_basing <= 40
            and hold_ret is not None
            and abs(hold_ret) < 4.0
        ):
            return "DEAD_MONEY_RISK"

    # ── 6. EARLY_WATCH ────────────────────────────────────────────────────────
    # drawdown >= 15% from 126d high AND bars_to_cross <= 2 (T3/T4 rows only)
    # AND no fresh T1-T3.  The 2D hist-curl arm is DEFERRED until engine emits it.
    if (
        not has_fresh_tier
        and drawdown_15_from_126d
        and bars_to_cross is not None
        and bars_to_cross <= 2.0
    ):
        return "EARLY_WATCH"

    # ── 7. KNIFE_RISK ─────────────────────────────────────────────────────────
    # BIND: the existing _ALIGN_KNIFE_BLOCK condition when knife_available.
    # Fallback: drawdown >= 15% from 126d high AND close < prior 21d rolling low
    # (dist_21d_low <= 0) AND no fresh tier.
    if not has_fresh_tier:
        if knife_available and knife_score is not None and knife_score >= _ALIGN_KNIFE_BLOCK:
            return "KNIFE_RISK"
        if not knife_available:
            # fallback to dist-based rule when knife not available
            below_21d_low = dist_21d_low is not None and dist_21d_low <= 0.0
            if drawdown_15_from_126d and below_21d_low:
                return "KNIFE_RISK"

    # ── 8. WATCH (default) ────────────────────────────────────────────────────
    return "WATCH"


# ── Build one row ──────────────────────────────────────────────────────────────

def _build_row(
    ticker: str,
    sg_verdict: dict,
    standout_row: dict | None,
    standout_donor: dict | None,
    earnings_df: pd.DataFrame,
    today: datetime.date,
    root: Path,
    sg_asof: str = "",
    sector_mapping: SectorMapping | None = None,
    panel_s: "pd.DataFrame | None" = None,
    panel_m: "pd.DataFrame | None" = None,
) -> dict[str, Any]:
    """Assemble one bottom-sensor row for a ticker.

    sg_verdict      : from signal_gate.json['verdicts'][ticker]
    standout_row    : the buy/watch/laggard row from us_standouts.json (may be None)
    standout_donor  : the top-level donor dict from us_standouts.json (board-level)
    sg_asof         : as_of from signal_gate.json; used as the row-level data vintage.
    sector_mapping  : SectorMapping for this ticker (sector_node / subsector_node).
    panel_s / panel_m : pre-loaded oracle panels; None = load skipped.

    Two-clock design: `as_of` reflects the source data vintage (sg_asof) so the
    synapse freshness guard (asof_field: as_of) tracks real data staleness.
    `computed_at` records when this row was assembled (today).  Earnings
    days_to is computed relative to today (wall-clock) because that is what
    the user cares about, but as_of tracks the data anchor.
    """
    # as_of tracks the source data vintage (signal_gate anchor), NOT today.
    # This prevents the synapse freshness guard from being fooled by always-fresh
    # computed_at timestamps while the underlying data may be stale.
    source_as_of = sg_asof if sg_asof else today.isoformat()

    row: dict[str, Any] = {
        "symbol": ticker,
        "as_of": source_as_of,
        "computed_at": today.isoformat(),
        "region": REGION,
        "labels_version": LABELS_VERSION,
        "is_display_only": IS_DISPLAY_ONLY,
        # rs_repair_state stamped unavailable (W0.4 of #1302 not yet shipped)
        "rs_repair_state": "unavailable",
        # sponsorship_state: computed from oracle panels via frozen §C3 definition.
        # If panels unavailable/ticker unmapped, degrades to "unavailable" gracefully.
        "sponsorship_state": _sponsorship_state(
            ticker=ticker,
            mapping=sector_mapping,
            panel_s=panel_s,
            panel_m=panel_m,
            today=today,
        ),
    }

    # ── Trigger tier + ticks (source: signal_gate.json) ─────────────────────
    row["trigger_tier"] = sg_verdict.get("tier_cascade")          # T1/T2/T3/T4/None
    row["trigger_age_ticks"] = sg_verdict.get("ticks")            # int or None
    row["source_artifacts"] = "signal_gate.json"

    # ── bars_to_cross (prefer signal_gate; standout fallback) ────────────────
    bars_to_cross = sg_verdict.get("bars_to_cross")
    if bars_to_cross is None and standout_row:
        sig = standout_row.get("signal") or {}
        bars_to_cross = sig.get("bars_to_cross")
    row["bars_to_cross"] = bars_to_cross

    # ── Coiled / STAR / coiled_fire (source: us_standouts.json buy rows) ─────
    coiled_dict = (standout_row or {}).get("coiled") or {}
    row["coiled"] = bool(coiled_dict.get("coiled", False))
    row["star"] = bool(coiled_dict.get("star", False))
    row["coiled_fire"] = bool(coiled_dict.get("fire", False))
    if standout_row:
        row["source_artifacts"] += ";us_standouts.json"

    # ── Donor state (board-level, source: us_standouts.json top-level .donor) ─
    donor_dict = standout_donor or {}
    row["donor_state"] = donor_dict.get("state")   # "intact"/"cracking"/None

    # ── Hold state (BIND from hold.py output in us_standouts.json) ───────────
    hold_dict = (standout_row or {}).get("hold") or {}
    hold_state_val = hold_dict.get("state") if hold_dict else None
    row["hold_state"] = hold_state_val
    row["hold_days_basing"] = hold_dict.get("days_basing") if hold_dict else None
    row["hold_maxup_pct"] = hold_dict.get("maxup_pct") if hold_dict else None

    # ── Entry quality band (source: conviction.potential.band in standout) ────
    conv = (standout_row or {}).get("conviction") or {}
    potential = conv.get("potential") or {}
    row["entry_quality_band"] = potential.get("band")  # high/constructive/neutral/low

    # ── Squeeze state (source: conviction.vol_squeeze.state) ─────────────────
    vs = conv.get("vol_squeeze") or {}
    row["squeeze_state"] = vs.get("state")   # COILED/COMPRESSED/EXPANSION/NONE/etc.

    # ── Knife score (source: conviction.alignment.knife) ─────────────────────
    alignment = conv.get("alignment") or {}
    knife_score = alignment.get("knife")
    knife_available = knife_score is not None
    row["knife_score"] = knife_score

    # ── Rolling distance columns (the ONLY two new computed columns) ──────────
    close = _load_close(root, ticker)
    dist_21 = _dist_21d_low_pct(close)
    dist_126 = _dist_126d_high_pct(close)
    row["dist_21d_low_pct"] = dist_21
    row["dist_126d_high_pct"] = dist_126
    # ── Amendment-3 raw structural descriptors (bound from the already-loaded
    #    close — no new I/O).  The flush/mixed/grind and short/mid/long tercile
    #    LABELS are assigned cross-sectionally in assemble() once every row's raw
    #    value is known.  Display-only (E) / shadow-only (F); CHIP-blocked (RUL-28).
    row["decline_herf"] = _decline_herf(close)
    row["underwater_bars"] = _underwater_bars(close)
    if close is not None:
        row["source_artifacts"] += ";data/stocks/<TICKER>.parquet"

    # ── Earnings (source: data/earnings/earnings.parquet) ────────────────────
    e_date, e_days, e_blackout = _earnings_info(ticker, earnings_df, today)
    row["earnings_next_date"] = e_date
    row["earnings_days_to"] = e_days
    if not earnings_df.empty:
        row["source_artifacts"] += ";data/earnings/earnings.parquet"

    # ── Overlay flags ─────────────────────────────────────────────────────────
    overlays: list[str] = []
    if e_blackout:
        overlays.append("EVENT_BLACKOUT")
    if row["coiled"]:
        overlays.append("COILED")
    if row["star"]:
        overlays.append("STAR")
    row["overlay_flags"] = ",".join(overlays) if overlays else None

    # ── State label (labels_v1 frozen decision table) ─────────────────────────
    # hold_ret_since_take: approximate from maxup_pct when intact/basing.
    # The spec says "abs(ret since take) < 4%".  maxup_pct (max FAVORABLE
    # excursion since anchor, always >= 0) is used as a proxy because hold.py
    # does not currently emit a signed ret_since_anchor field.
    #
    # Deviation note (deviation #4): this proxy is conservative ONLY for names
    # that rallied (maxup > 0 → |ret| proxy is the upside max).  For names that
    # are DOWN since anchor (intact but underwater), maxup ≈ 0 while true
    # |ret_since_take| may be large, causing the proxy to under-detect real
    # drawdown and potentially label a falling name DEAD_MONEY_RISK when it
    # should not be.  Impact is bounded: only names already in hold["intact"]
    # with days_basing 15-40 are eligible; the label is display-only.
    # TODO: when hold.py emits ret_since_anchor (signed), bind it here instead.
    hold_ret_proxy = row.get("hold_maxup_pct")

    row["bottom_state"] = _classify_labels_v1(
        hold_state=hold_state_val,
        hold_days_basing=row["hold_days_basing"],
        hold_ret=hold_ret_proxy,
        trigger_tier=row["trigger_tier"],
        ticks=row["trigger_age_ticks"],
        coiled=row["coiled"],
        dist_21d_low=dist_21,
        dist_126d_high=dist_126,
        bars_to_cross=bars_to_cross,
        knife_score=knife_score,
        knife_available=knife_available,
    )

    return row


# ── Main assembly ──────────────────────────────────────────────────────────────

def assemble(
    root: Path | None = None,
    today: datetime.date | None = None,
) -> pd.DataFrame:
    """Assemble the bottom-sensor envelope for all US board names.

    Reads:
      - site/factordata/signal_gate.json  (trigger tier + ticks for full universe)
      - site/factordata/us_standouts.json  (coiled/hold/squeeze/donor for board names)
      - data/earnings/earnings.parquet    (earnings next_date)
      - data/stocks/<TICKER>.parquet      (rolling distance columns)
      - data/edgar/dilution_events.parquet  (nwqs-c; absent on CI runners → degrade)

    Returns a DataFrame with one row per ticker in signal_gate.json universe.
    Never raises; partial failures degrade gracefully.
    """
    if root is None:
        root = _repo_root()
    root = Path(root)
    if today is None:
        today = datetime.date.today()

    log.info("bottom_sensors.assemble: root=%s, today=%s", root, today)

    # Load sources
    sg_verdicts, sg_asof = _load_signal_gate(root)
    if not sg_verdicts:
        log.error("signal_gate.json empty/missing — cannot build envelope")
        return pd.DataFrame()

    standouts = _load_us_standouts(root)
    earnings_df = _load_earnings(root)

    # ── Dilution context (nwqs-c; display-only, RENDER_NO_DRIP) ──────────────
    # Absent parquet → empty DataFrame → all dilution fields degrade to None.
    # Never fabricates 0 for missing data.
    dilution_df = _load_dilution_index(root)
    dilution_index = _build_dilution_index(dilution_df)

    # ── Survival-quality leverage ratios (FR-9/FR-10; display-only) ──────────
    # Load statements once; degrade gracefully when parquet is absent (CI runners,
    # first run before the drip has fired).  Uses the latest filed fiscal year
    # (PIT-safe for a current snapshot; rows[-1] = most recently filed FY).
    statements_by_ticker = _load_statements()

    # ── Sponsorship connector (Amendment §C3) — load once, pass through ──────
    # build_sector_map is fast (parquet reads from existing stores, cached on disk).
    # Oracle panels are loaded once and reused across all ticker rows.
    # All failures degrade to sponsorship_state="unavailable" gracefully.
    sector_map_dict = build_sector_map(root)
    panel_s = _load_oracle_panel(root, "panel_s.parquet")
    panel_m = _load_oracle_panel(root, "panel_m.parquet")

    # Build per-ticker dicts from standouts
    buy_rows: dict[str, dict] = {}
    for r in standouts.get("buy", []):
        t = r.get("ticker")
        if t:
            buy_rows[t] = r
    # watch/laggards: they have fewer fields but we include them for field binding
    watch_rows: dict[str, dict] = {}
    for r in standouts.get("watch", []) + standouts.get("laggards", []):
        t = r.get("ticker")
        if t:
            watch_rows[t] = r

    standout_donor = standouts.get("donor") or {}

    rows: list[dict] = []
    n_ok = 0
    n_fail = 0

    for ticker, sg_v in sg_verdicts.items():
        try:
            # Prefer buy row (richer fields); fallback to watch row
            standout_row = buy_rows.get(ticker) or watch_rows.get(ticker)
            # Sponsorship: look up pre-built sector mapping for this ticker
            s_mapping = sector_map_dict.get(ticker)  # None = unmapped → unavailable
            row = _build_row(
                ticker=ticker,
                sg_verdict=sg_v,
                standout_row=standout_row,
                standout_donor=standout_donor,
                earnings_df=earnings_df,
                today=today,
                root=root,
                sg_asof=sg_asof,
                sector_mapping=s_mapping,
                panel_s=panel_s,
                panel_m=panel_m,
            )
            # ── Bottom-survival-quality leverage ratios (FR-9/FR-10) ──────────
            # Additive per-ticker columns: None when statements absent or ratio
            # uncomputable (Financial-sector names, sparse filers).  No additional PIT
            # truncation needed here: _load_statements() availability-gates the rows
            # (period_end + 120d, #1572) so rows[-1] is the latest *filed* FY — never a
            # not-yet-filed future row — and _leverage_ratios() uses only that row.
            stmt_rows = statements_by_ticker.get(ticker) or []
            lev = _leverage_ratios(stmt_rows)
            row["interest_coverage"] = lev.get("interest_coverage")
            row["net_debt_to_op_income"] = lev.get("net_debt_to_op_income")
            row["net_debt_to_ebitda"] = lev.get("net_debt_to_ebitda")
            # ── Dilution context (nwqs-c; display-only) ───────────────────────
            # None when dilution_events.parquet absent or ticker unmapped.
            d_shelf, d_takedown, d_events = _dilution_fields(
                ticker, dilution_index, today
            )
            row["days_since_shelf"] = d_shelf
            row["days_since_takedown"] = d_takedown
            row["dilution_events_365d"] = d_events
            rows.append(row)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("bottom_sensors row failed for %s: %s", ticker, exc)
            n_fail += 1

    if not rows:
        log.error("bottom_sensors.assemble: zero rows built")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index("symbol")

    # ── Cross-sectional decline-geometry + underwater terciles (Amendment 3) ──
    # decline_geometry (family E, DISPLAY-CANDIDATE): high trailing-63-bar loss-
    #   Herfindahl = FLUSH (few large down-days = forced supply that empties);
    #   low = GRIND (loss spread evenly = distribution that persists).  A decline-
    #   SHAPE read, display-only, NOT an escalation.
    # underwater_state (family F, ADVERSE-CONTEXT, shadow-only): LONG = longest under
    #   the trailing-252 peak (historically higher stop-out; caution context).
    # Both descriptors are display/shadow-only (is_display_only) and CHIP-blocked
    # (RUL-28) until the true eq_band cache lands.
    if "decline_herf" in df.columns:
        df["decline_geometry"] = _assign_terciles(
            df["decline_herf"], ("grind", "mixed", "flush")
        )
    if "underwater_bars" in df.columns:
        df["underwater_state"] = _assign_terciles(
            df["underwater_bars"].astype("float"), ("short", "mid", "long")
        )

    # stamp as_of from signal_gate
    meta_as_of = sg_asof or today.isoformat()

    log.info(
        "bottom_sensors.assemble done: %d rows (ok=%d fail=%d) as_of=%s",
        len(df), n_ok, n_fail, meta_as_of,
    )

    # Store as metadata attribute (accessible for the runner)
    df.attrs["as_of"] = meta_as_of
    df.attrs["labels_version"] = LABELS_VERSION
    df.attrs["is_display_only"] = IS_DISPLAY_ONLY

    return df
