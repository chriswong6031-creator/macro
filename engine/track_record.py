"""Signal Track-Record Logger — append-only, key-deduped measurement log.

MEASUREMENT ONLY. Do NOT touch engine/signal_quality.py. Framing is entirely on
DRAWDOWN / entry-quality (CHARTER §2b, §3, §4). Never return-alpha.

The buy-filter cut avg max drawdown -23.7% → -15.5% across 110 held-out US names
(84% improved). This logger is the standing forward track record that proves — or
surfaces blind spots in — that claim.

Public API
----------
update_track_record(repo_root, signals_dir, mtf_path, stocks_dir, out_path, asof) -> dict
    Summary keys: new_rows, matured_rows, total_rows, skipped_pending, out_path.

NO LOOK-AHEAD rule (CHARTER §3): every entry-time feature uses ONLY daily data with
index ≤ the marker date; forward metrics use ONLY data > the marker date — in *index*
terms there is no look-ahead.

FILL CONVENTION (W1c, audit #15): a signal that fires on the close of the marker bar is
FILLED at the NEXT bar's close — the honest convention matching the VALIDATED research
harness (research/signal_engine/tuning_harness.py enters at f=i+1) and validation.py's
alloc.shift(1) "act next bar". `entry_price` is the fill bar (marker bar + 1); forward
returns/drawdowns are measured from that fill; the strictly-forward window never includes
the entry bar. The forward/fill math is centralized in engine.grading so this logger, the
sector graders, and the desk graders all use ONE convention. Same-bar fills flatter short
mean-reversion signals most (you buy the exact trough), so the pre-W1c same-bar version was
optimistic in exactly the direction that over-sizes a mechanical system; a shadow same-bar
column (fwd_mdd_60_samebar) is emitted alongside so the correction is measurable, not hidden.

Price-store caveat (honest framing, not a fatal leak): the daily store is back-adjusted
(CHARTER §5; data/stocks `close` is split- AND dividend-back-adjusted total-return,
verified empirically — AAPL has no gap across the 2020 4:1 split). Splits are a constant
multiplicative factor that CANCELS in every ratio we compute (entry_price, fwd_ret /
fwd_mdd / trade_ret, price-vs-SMA200, pct_change vol, the ER ratio are all scale-
invariant) → split adjustment is leak-neutral. The residual is DIVIDENDS: an interim
dividend rebases the entry-leg bar but not the t+H bar, so forward returns / drawdowns
are total-return-with-hindsight, injecting interim dividends unknown at entry. The bias
is bounded by interim dividend yield (typically <1% over 60d) — it nudges the drawdown
*magnitudes* slightly, not the take-vs-block *direction*. Feed an unadjusted/as-of price
series to remove it entirely.

Append-only + idempotent: identity/entry columns frozen on first write
(first-observed wins). Only NULL maturation columns get filled as data matures.
Re-running on unchanged inputs is a no-op.

Key = (ticker, date, type).

Dependencies: pandas, numpy, pyarrow ONLY. No scipy. Python 3.
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from engine import grading  # W1c: one shared next-bar/survivorship-aware grader
from engine import ledger_identity  # ticker renames: one key per company, not per string
from engine import regime_vector as _rv  # W0-stageB: vector stamping

logger = logging.getLogger(__name__)



from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled


def _is_null(v: Any) -> bool:
    """NaN-aware null test.

    A maturation cell that was written as None round-trips back from a float64
    parquet column as ``np.nan`` (not None), so a plain ``v is None`` check would
    treat an un-matured cell as already-filled and SKIP it forever (maturation
    stall).  This handles None, np.nan, pd.NA, pd.NaT for scalars.
    """
    return v is None or (np.ndim(v) == 0 and pd.isna(v))


# ---------------------------------------------------------------------------
# Schema: ordered column list.  Types are pandas dtypes (object = str/nullable).
# ---------------------------------------------------------------------------

# Immutable identity + entry-time columns (frozen on first write, first-observed wins)
_IDENTITY_COLS = [
    "ticker",       # str
    "date",         # str YYYY-MM-DD  — the marker's 3D bar date
    "type",         # str  buy / rebuy / sell / cut
    "quality",      # str/null  take / block  (null for sell/cut)
    "reason",       # str/null  engine reason text  (null for sell/cut)
    "entry_price",  # float  close on date (snapped to prior bar if needed)
    "regime_at_entry",        # str  bull / bear / choppy / unknown  (per-name SMA200 axis)
    "above200_at_entry",      # bool/null
    "sma200_rising_at_entry", # bool/null
    "vol_annual_at_entry",    # float/null  trailing-63d σ × √252
    "er_at_entry",            # float/null  Kaufman Efficiency Ratio (20-bar)
    "first_seen_asof",        # str  mtf asof when row first written
    # W0.2 Stage C near-miss identity (null on fire rows):
    "primary_rejection_reason",  # str/null  CLOSED Appendix-A taxonomy reason
    "reason_detail",             # str/null  the gate's free-text why (display/audit)
    # W0-stageB: macro regime_vector stamp (§3.4) — US primary, distinct from regime_at_entry
    "rate_pressure",          # str/null  relief / neutral / pressure / panic
    "quad_hard_label",        # str/null  e.g. "goldilocks" / "stagflation" / …
    "fused_risk_label",       # str/null  regime_one fused risk label
    "vol_regime",             # str/null  calm-contango / normalizing / warning / backwardation-stress
    "risk_radar_state",       # str/null  e.g. "risk-off" / "risk-on" / …
    "regime_vector_degraded", # int/null  1 = any vector axis was null/degraded at stamp time
    "vector_asof",            # str/null  ISO date of the persisted vector row used
    "staleness_hours",        # float/null  hours between vector_asof and marker_date (0 = exact)
    # W0-stageB: species / archetype (§5.1 species_id + §3.2 archetype stamp)
    "species_id",             # str/null  unambiguous registry mapping; null if ambiguous or none
    "archetype",              # str/null  archetype key from site/stockdata/<ticker>.json at stamp time
    # R-SQ8: the §7 BUCKETING ERA this row's marker was drawn under, copied from the signal
    # file's own `anchor_era`. Null on every pre-2026-08-06 row (they were logged before the
    # field existed) and on near-miss rows (not §7 markers), which is itself the cohort
    # boundary — a graded read fences on this field rather than on a date guess.
    "anchor_era",             # str/null  e.g. "sq-abs-session-2026-08-06"
]

# Maturation columns — NULL until enough forward data, then filled once and frozen
_MATURATION_COLS = [
    "fwd_ret_20",   # float/null  close[t+20]/entry − 1
    "fwd_ret_60",
    "fwd_ret_180",
    "fwd_price_20", # float/null  close[t+20]
    "fwd_price_60",
    "fwd_price_180",
    "fwd_mdd_20",   # float/null  min(0, min(close[fill+1..fill+20])/entry − 1)  (≤0)  THE §3 METRIC
    "fwd_mdd_60",
    "fwd_mdd_180",
    "fwd_mdd_60_samebar",  # float/null  W1c shadow: the OLD same-bar-fill 60d MDD
    "fill_offset",  # int/null  bars from marker to fill (1 = honest next-bar; 0 = same-bar legacy)
    "trade_mae",    # float/null  min(0, min(close[fill+1..exit])/entry − 1)  (≤0, trade-level)
    "outcome",      # str/null  win / loss / still_held
    "exit_date",    # str/null
    "exit_type",    # str/null  sell / cut
    "exit_price",   # float/null
    "trade_ret",    # float/null  exit_price/entry − 1  (secondary context, NOT the verdict)
    "last_backfill_asof",  # str/null  provenance: asof of run that last filled a mat. col
    # W0-stageB: Outcome Spine v2 primitives (§5.1 sub-task; §1.1 terminal-state partition)
    # fwd_mfe at each spine horizon — max favorable excursion from grading.forward_metrics
    "fwd_mfe_5",    # float/null  max(0, max(close[fill+1..fill+5])/entry − 1)
    "fwd_mfe_10",
    "fwd_mfe_21",
    "fwd_mfe_63",
    "fwd_mfe_126",
    # terminal_state partition for clean15_126 (positional primary) — TerminalState str
    "terminal_state_clean15_126",   # str/null  STOPPED/DEAD_MONEY/CUSHIONED/CLEAN_LIFTOFF
    # terminal_state partition for clean8_21 (rotational primary) — TerminalState str
    "terminal_state_clean8_21",     # str/null  same vocabulary
    # post-cushion breakeven-breach flag (single-fire version of §1.1 cushion_incidence metric)
    # True = price fell back below entry_price after first touching +5%; False = did not;
    # None = fire not yet cushioned or not yet matured.
    "post_cushion_breach",          # bool/null
]

_ALL_COLS = _IDENTITY_COLS + _MATURATION_COLS
_KEY = ("ticker", "date", "type")

# --------------------------------------------------------------------------- #
# R-SQ8 — the §7 anchor-era floor, and why an append-only ledger needs one
# --------------------------------------------------------------------------- #
# This ledger's identity is literally (ticker, MARKER DATE, type), keep-FIRST, append-only,
# never-purge. It ingests the §7 marker files wholesale. On 2026-08-06 the marker engine's
# bucketing grid was deliberately re-anchored (signal_quality.ANCHOR_ERA =
# "sq-abs-session-2026-08-06"), which re-dates most historical markers by a session or two —
# so with no guard, the first post-cutover run would mint a NEW row beside every pre-era row
# whose date moved: permanent double-counting of the same physical event, in the one store
# whose whole value is that a fire is logged exactly once.
#
# The rule: a NEW key is appended only if its marker date is ON OR AFTER the floor AND no
# existing row of the same (ticker, type) sits within SQ_ERA_BOUNDARY_DAYS calendar days of
# it. Pre-floor history in tonight's file is treated as the RE-DATED IMAGE of already-logged
# events, never as new events. The ±4-day window (mirroring marker_integrity.TOL_DAYS) is
# the boundary-week guard: a marker logged at 2026-08-05 that re-dates to 2026-08-07 lands
# ON the wrong side of the floor and would otherwise slip through as new. It costs nothing
# in steady state — two same-type §7 markers cannot fire on adjacent 3D buckets (both `CB`
# and `CS` require a MACD cross, and a cross cannot repeat on consecutive bars), so real
# same-type prints are always ≳6 calendar days apart.
#
# Existing rows keep maturing normally: fills touch only NULL maturation columns, and no
# pre-era row is ever edited (the emitter-fix-cannot-heal-logged-rows law).
SQ_ANCHOR_ERA_FLOOR = "2026-08-06"
SQ_ERA_BOUNDARY_DAYS = 4

# Which marker types carry the buy-filter verdict
_ENTRY_TYPES = {"buy", "rebuy"}
_EXIT_TYPES  = {"sell", "cut"}
# W0.2 Stage C: the near-miss row type (candidates failing EXACTLY ONE Appendix-A
# condition at signal_gate). Graded as predictions (§5.2 move 3: same spine, same
# horizons) but NEVER an entry — excluded from every entry/outcome stat by type.
NEAR_MISS_TYPE = "near_miss"
_FWD_HORIZONS = [20, 60, 180]
# Spine horizons for fwd_mfe + terminal_state (§5.1, §1.1)
_SPINE_HORIZONS = list(grading.SPINE_HORIZONS)  # (5, 10, 21, 63, 126)


# ---------------------------------------------------------------------------
# Regime + archetype helpers  (all NO LOOK-AHEAD: use only data ≤ date)
# ---------------------------------------------------------------------------

def _snap_loc(close: pd.Series, date: str) -> int | None:
    """Integer iloc position of nearest prior bar (index ≤ date).  None if none."""
    dt = pd.Timestamp(date)
    lte = close.index <= dt
    if not lte.any():
        return None
    return int(np.searchsorted(close.index, dt, side="right") - 1)


def _regime_at(close: pd.Series, date: str) -> tuple[str, bool | None, bool | None]:
    """Compute regime using ONLY daily close data with index ≤ date.

    Returns (regime, above200, sma200_rising) where:
        regime  = 'bull' / 'bear' / 'choppy' / 'unknown'
        above200 = close > SMA200 as of date
        sma200_rising = SMA200[t] > SMA200[t-20] as of date

    bull   = above SMA200 AND SMA200 rising
    bear   = below SMA200 AND SMA200 falling
    choppy = mixed (one signal but not both)
    unknown = fewer than 200 bars of history through date
    """
    loc = _snap_loc(close, date)
    if loc is None:
        return "unknown", None, None

    # Use only data through 'date' (inclusive)
    sub = close.iloc[: loc + 1]

    if len(sub) < 200:
        return "unknown", None, None

    sma200 = sub.rolling(200).mean()
    sma200_now  = float(sma200.iloc[-1])
    sma200_prev = float(sma200.iloc[-21]) if len(sma200) >= 21 else float("nan")

    price_now = float(sub.iloc[-1])

    above200 = bool(price_now > sma200_now) if not np.isnan(sma200_now) else None
    rising   = (bool(sma200_now > sma200_prev)
                if (above200 is not None and not np.isnan(sma200_prev)) else None)

    if above200 is None or rising is None:
        return "unknown", above200, rising
    if above200 and rising:
        regime = "bull"
    elif (not above200) and (not rising):
        regime = "bear"
    else:
        regime = "choppy"

    return regime, above200, rising


def _vol_annual_at(close: pd.Series, date: str) -> float | None:
    """Trailing-63-day daily-return σ × √252 using only data ≤ date.  None if <64 bars."""
    loc = _snap_loc(close, date)
    if loc is None or loc < 63:
        return None
    sub = close.iloc[max(0, loc - 63): loc + 1]
    if len(sub) < 2:
        return None
    rets = sub.pct_change().dropna()
    if len(rets) < 2:
        return None
    return float(rets.std() * np.sqrt(252))


def _kaufman_er_at(close: pd.Series, date: str, n: int = 20) -> float | None:
    """Kaufman Efficiency Ratio (n-bar) using only data ≤ date.

    ER = |price_now - price_n_bars_ago| / sum(|daily_changes|)
    Returns None if fewer than n+1 bars available.
    """
    loc = _snap_loc(close, date)
    if loc is None or loc < n:
        return None
    sub = close.iloc[loc - n: loc + 1]  # n+1 points → n returns
    if len(sub) < n + 1:
        return None
    direction = abs(float(sub.iloc[-1]) - float(sub.iloc[0]))
    volatility = float((sub.diff().dropna().abs()).sum())
    if volatility == 0:
        return None
    return float(direction / volatility)


def _forward_metrics(
    close: pd.Series, entry_date: str, horizons: list[int]
) -> dict[str, Any]:
    """Fixed-horizon forward returns + drawdowns on the NEXT-BAR fill (W1c, audit #15).

    Routes through engine.grading.forward_metrics: entry = the bar STRICTLY AFTER the
    marker bar; the drawdown window is strictly forward of that fill. Returns the flat
    fwd_ret_{H}/fwd_price_{H}/fwd_mdd_{H} dict PLUS `fill_offset` and the shadow
    `fwd_mdd_60_samebar` (the old same-bar-fill 60d MDD) so the next-bar correction is
    measurable rather than hidden. Any horizon not yet matured is None.
    """
    m = grading.forward_metrics(close, entry_date, horizons=tuple(horizons))
    result: dict[str, Any] = {}
    for h in horizons:
        result[f"fwd_ret_{h}"]   = m.get(f"fwd_ret_{h}")
        result[f"fwd_price_{h}"] = m.get(f"fwd_price_{h}")
        result[f"fwd_mdd_{h}"]   = m.get(f"fwd_mdd_{h}")
    result["fill_offset"] = m.get("fill_offset")

    # shadow same-bar 60d MDD — the pre-W1c number, for the before/after audit only.
    if 60 in horizons:
        sb = grading.forward_metrics(close, entry_date, horizons=(60,), same_bar=True)
        result["fwd_mdd_60_samebar"] = sb.get("fwd_mdd_60")
    else:
        result["fwd_mdd_60_samebar"] = None
    return result


def _resolve_exit(
    markers: list[dict], entry_idx: int
) -> tuple[str | None, str | None]:
    """Find the first sell/cut marker after entry_idx in the marker list.

    Returns (exit_date, exit_type) or (None, None) if still open.
    """
    for m in markers[entry_idx + 1:]:
        if m.get("type") in _EXIT_TYPES:
            return m["date"], m["type"]
    return None, None


# ---------------------------------------------------------------------------
# W0-stageB helpers: regime_vector stamp, species_id, archetype
# ---------------------------------------------------------------------------

def _regime_stamp(marker_date: str, data_dir: "Path | None" = None) -> dict[str, Any]:
    """Stamp the persisted regime_vector onto a new row (§3.4).

    Returns a dict with the 8 stamp columns (all nullable).  PIT-safe: reads
    ONLY persisted rows whose date ≤ marker_date.

    Null result (all None) when no persisted vector covers the date.
    """
    try:
        return _rv.get_vector_for_date(marker_date, data_dir=data_dir)
    except Exception as exc:
        logger.debug("regime_stamp: could not look up vector for %s: %s", marker_date, exc)
        return {
            "rate_pressure": None, "quad_hard_label": None,
            "fused_risk_label": None, "vol_regime": None,
            "risk_radar_state": None, "regime_vector_degraded": None,
            "vector_asof": None, "staleness_hours": None,
        }


# ---------------------------------------------------------------------------
# Species registry cache (loaded once per builder run, not per row)
# ---------------------------------------------------------------------------

_species_registry_cache: dict | None = None


def _load_species_registry(
    repo_root: "Path | None" = None,
    data_dir: "Path | None" = None,
) -> dict:
    """Load data/species/registry.json; return {} on error.

    Lookup order:
      1. data_dir / "species" / "registry.json"   (when data_dir is supplied)
      2. repo_root / "data" / "species" / "registry.json"
      3. module-relative default (parents[1] / "data" / "species" / "registry.json")
    """
    global _species_registry_cache  # noqa: PLW0603
    if _species_registry_cache is not None:
        return _species_registry_cache

    candidates: list[Path] = []
    if data_dir is not None:
        candidates.append(Path(data_dir) / "species" / "registry.json")
    if repo_root is not None:
        candidates.append(Path(repo_root) / "data" / "species" / "registry.json")
    candidates.append(Path(__file__).resolve().parents[1] / "data" / "species" / "registry.json")

    for p in candidates:
        if p.exists():
            try:
                doc = json.loads(p.read_text())
                _species_registry_cache = doc
                return doc
            except Exception as exc:
                logger.debug("species registry read error (%s: %s) — trying next", p, exc)

    logger.debug("species registry not found — species_id stamps will be null")
    _species_registry_cache = {}
    return {}


def _build_mtype_to_species(registry: dict) -> dict[str, str]:
    """Build a dict mapping marker_type → species_id where the mapping is UNAMBIGUOUS.

    Reads `ledger_binding` entries from the registry.  A marker_type maps to a
    species_id only when EXACTLY one registered species binds to the 'track_record'
    ledger AND that species' ledger_binding covers this marker type.

    §5 spec: stamp only where mapping is UNAMBIGUOUS — else null.  The track_record
    ledger currently has no registered species (all species bind to us_board_ledger or
    china_standout_track), so this dict will be empty and all species_id stamps will
    be null.  When a future species registers track_record as its ledger, add it here
    via the ledger_binding field.
    """
    # species whose ledger_binding references 'track_record'
    candidates: dict[str, list[str]] = {}  # mtype -> [species_ids]
    for sp in registry.get("species", []):
        sp_id = sp.get("species_id")
        lb = sp.get("ledger_binding") or {}
        ledger = lb.get("ledger", "") if isinstance(lb, dict) else str(lb)
        if "track_record" in ledger:
            # For simplicity, register under the species' marker types if stated;
            # default to 'buy' for entry species
            marker_types = sp.get("marker_types") or ["buy"]
            for mt in marker_types:
                candidates.setdefault(mt, []).append(sp_id)
    # Only keep unambiguous (exactly 1 species per mtype)
    return {mt: sids[0] for mt, sids in candidates.items() if len(sids) == 1}


# ---------------------------------------------------------------------------
# Archetype cache: load from site/stockdata/<ticker>.json (last committed state)
# ---------------------------------------------------------------------------

_archetype_cache: dict[str, str | None] = {}  # ticker -> archetype key (or None)
_archetype_stockdata_dir: "Path | None" = None


def _archetype_for_ticker(ticker: str, stockdata_dir: "Path | None" = None) -> str | None:
    """Read the current archetype key for a ticker from site/stockdata/<ticker>.json.

    This is the archetype from the LAST COMMITTED stockdata build — PIT-safe because
    track_record runs before the new build; the stockdata reflects yesterday's state.

    Returns the archetype `key` string (e.g. 'mixed', 'quality_compounder', …) or None
    if the file is absent, the key is missing, or an error occurs.

    Caches per ticker within a builder run.
    """
    global _archetype_stockdata_dir  # noqa: PLW0603
    if ticker in _archetype_cache:
        return _archetype_cache[ticker]

    if stockdata_dir is None:
        if _archetype_stockdata_dir is not None:
            stockdata_dir = _archetype_stockdata_dir
        else:
            stockdata_dir = Path(__file__).resolve().parents[1] / "site" / "stockdata"

    p = Path(stockdata_dir) / f"{ticker}.json"
    result: str | None = None
    try:
        doc = json.loads(p.read_text())
        arche = (doc.get("profile") or {}).get("archetype") or {}
        result = arche.get("key") if isinstance(arche, dict) else None
    except Exception:
        result = None

    _archetype_cache[ticker] = result
    return result


def _reset_per_run_caches() -> None:
    """Reset caches that should refresh on each builder run."""
    global _species_registry_cache, _archetype_cache  # noqa: PLW0603
    _species_registry_cache = None
    _archetype_cache = {}


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _build_row(
    ticker: str,
    marker: dict,
    markers: list[dict],
    marker_idx: int,
    close: pd.Series,
    asof: str,
    *,
    mtype_to_species: dict | None = None,
    data_dir: "Path | None" = None,
    stockdata_dir: "Path | None" = None,
    anchor_era: str | None = None,
) -> dict[str, Any]:
    """Build a single track-record row dict from a marker.

    Entry-time features are computed no-look-ahead.  Maturation columns are left
    None here — they are filled separately during the maturation pass.

    New parameters (W0-stageB):
      mtype_to_species : unambiguous mtype→species_id mapping from the registry.
      data_dir         : override for regime_vector parquet dir.
      stockdata_dir    : override for site/stockdata/ dir (archetype source).
    """
    date = marker["date"]
    mtype = marker["type"]

    # NEXT-BAR fill (W1c): entry price = close of the bar STRICTLY AFTER the marker bar.
    # Falls back to the marker bar itself ONLY when there is no next bar yet (the fill has
    # not happened) — that row then carries entry NaN and stays un-matured, which is honest.
    fill = grading.fill_index(close, date)
    if fill is not None:
        entry_price = float(close.iloc[fill])
    else:
        loc = _snap_loc(close, date)
        entry_price = float(close.iloc[loc]) if loc is not None else float("nan")

    regime, above200, rising = _regime_at(close, date)
    vol_annual = _vol_annual_at(close, date)
    er = _kaufman_er_at(close, date)

    # W0-stageB: regime_vector stamp (§3.4) — PIT-safe from persisted parquet
    rv_stamp = _regime_stamp(date, data_dir=data_dir)

    # W0-stageB: species_id — unambiguous registry mapping only (§5 spec)
    sp_id: str | None = (mtype_to_species or {}).get(mtype)

    # W0-stageB: archetype from last committed stockdata (PIT-safe by construction)
    archetype = _archetype_for_ticker(ticker, stockdata_dir=stockdata_dir)

    row: dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "type": mtype,
        "quality": marker.get("quality"),   # None for sell/cut
        "reason": marker.get("reason"),
        "entry_price": entry_price,
        "regime_at_entry": regime,
        "above200_at_entry": above200,
        "sma200_rising_at_entry": rising,
        "vol_annual_at_entry": vol_annual,
        "er_at_entry": er,
        "first_seen_asof": asof,
        # W0-stageB: regime_vector stamp columns (frozen at creation)
        "rate_pressure": rv_stamp.get("rate_pressure"),
        "quad_hard_label": rv_stamp.get("quad_hard_label"),
        "fused_risk_label": rv_stamp.get("fused_risk_label"),
        "vol_regime": rv_stamp.get("vol_regime"),
        "risk_radar_state": rv_stamp.get("risk_radar_state"),
        "regime_vector_degraded": rv_stamp.get("regime_vector_degraded"),
        "vector_asof": rv_stamp.get("vector_asof"),
        "staleness_hours": rv_stamp.get("staleness_hours"),
        # W0-stageB: species/archetype (frozen at creation)
        "species_id": sp_id,
        "archetype": archetype,
        # R-SQ8: the §7 bucketing era of the FILE this marker came from (frozen at creation)
        "anchor_era": anchor_era,
        # maturation — all None at birth
        "fwd_ret_20": None, "fwd_ret_60": None, "fwd_ret_180": None,
        "fwd_price_20": None, "fwd_price_60": None, "fwd_price_180": None,
        "fwd_mdd_20": None, "fwd_mdd_60": None, "fwd_mdd_180": None,
        "fwd_mdd_60_samebar": None, "fill_offset": None,
        "trade_mae": None, "outcome": None,
        "exit_date": None, "exit_type": None, "exit_price": None,
        "trade_ret": None,
        "last_backfill_asof": None,
        # W0-stageB: spine maturation columns (all None at birth)
        "fwd_mfe_5": None, "fwd_mfe_10": None, "fwd_mfe_21": None,
        "fwd_mfe_63": None, "fwd_mfe_126": None,
        "terminal_state_clean15_126": None,
        "terminal_state_clean8_21": None,
        "post_cushion_breach": None,
    }
    return row


# ---------------------------------------------------------------------------
# Maturation filler — called on both new and existing rows
# ---------------------------------------------------------------------------

def _fill_maturation(
    row: dict[str, Any],
    markers: list[dict],
    marker_idx: int,
    close: pd.Series,
    asof: str,
) -> bool:
    """Fill any NULL maturation columns in-place.

    Returns True if at least one column was filled (so caller knows to set
    last_backfill_asof).

    Maturation discipline:
      * fwd_* / fixed-horizon columns are FROZEN first-observed — filled only when
        currently null, never overwritten (a horizon matures once and stays).
      * exit_* / trade_ret are frozen first-observed too.
      * `outcome` is the one provisional state: "still_held" is NOT final, so when an
        exit later appears it is resolved (overwritten) to win/loss and `trade_mae` is
        recomputed entry→exit.  win/loss are final.  This is the only post-birth
        overwrite, and it is a one-way resolution — so re-running on unchanged inputs
        is still a strict no-op (idempotent).
      * `outcome` (win/loss/still_held) is a MATURATION / EXCLUSION flag, NOT the
        verdict.  The verdict is drawdown (fwd_mdd_* / trade_mae) per CHARTER §3 — the
        audit uses outcome only to drop still_held rows and as a coverage count.

    entry-only metrics (trade_mae / outcome / exit_*) are only filled for buy/rebuy.
    sell/cut rows get all fwd_* columns too (for context) but no trade_* columns.
    """
    mtype = row["type"]
    date = row["date"]
    entry_price = row.get("entry_price")
    if _is_null(entry_price):
        return False

    entry_price_f = float(entry_price)
    filled = False

    def _freeze(key: str, value: Any) -> None:
        """Fill a frozen column only if currently null (first-observed wins)."""
        nonlocal filled
        if not _is_null(value) and _is_null(row.get(key)):
            row[key] = value
            filled = True

    # --- fixed-horizon forward metrics (frozen, NaN-aware) ---
    if any(_is_null(row.get(f"fwd_mdd_{h}")) for h in _FWD_HORIZONS):
        for k, v in _forward_metrics(close, date, _FWD_HORIZONS).items():
            _freeze(k, v)

    # --- W0-stageB: spine fwd_mfe at each SPINE_HORIZON ---
    if any(_is_null(row.get(f"fwd_mfe_{h}")) for h in _SPINE_HORIZONS):
        spine_m = grading.forward_metrics(close, date, horizons=tuple(_SPINE_HORIZONS))
        for h in _SPINE_HORIZONS:
            _freeze(f"fwd_mfe_{h}", spine_m.get(f"fwd_mfe_{h}"))

    # --- W0-stageB: terminal_state partition columns ---
    # clean15_126 (positional primary): liftoff_mult=1.15, liftoff_horizon=126
    if _is_null(row.get("terminal_state_clean15_126")):
        ts15 = grading.terminal_state(
            close, date,
            liftoff_mult=grading.LIFTOFF_15,
            liftoff_horizon=grading.LIFTOFF_HORIZON_126,
        )
        state15 = ts15.get("state")
        if state15 is not None:
            _freeze("terminal_state_clean15_126", str(state15))

    # clean8_21 (rotational primary): liftoff_mult=1.08, liftoff_horizon=21
    if _is_null(row.get("terminal_state_clean8_21")):
        ts8 = grading.terminal_state(
            close, date,
            liftoff_mult=grading.LIFTOFF_8,
            liftoff_horizon=grading.LIFTOFF_HORIZON_21,
        )
        state8 = ts8.get("state")
        if state8 is not None:
            _freeze("terminal_state_clean8_21", str(state8))

    # --- W0-stageB: post_cushion_breach flag (single-fire, §1.1) ---
    # Routed through grading.post_cushion_breach (one-grader law §1.2) — the
    # per-row flag uses the IDENTICAL scan as cushion_incidence's breach rate,
    # so a cushioned-then-stopped fire is True (below entry by definition),
    # never silently dropped. Window = clean8_21 horizon (21, rotational).
    if _is_null(row.get("post_cushion_breach")):
        breach = grading.post_cushion_breach(close, date, horizon=21)
        if breach is not None:
            _freeze("post_cushion_breach", bool(breach))

    # --- trade-level metrics (entry markers only) ---
    if mtype in _ENTRY_TYPES:
        outcome = row.get("outcome")
        provisional = _is_null(outcome) or outcome == "still_held"
        if provisional:
            # NEXT-BAR fill (W1c): entry = the bar AFTER the marker, EXIT = the bar AFTER
            # the sell/cut marker — symmetric with the forward-metric convention. entry_price_f
            # is already the fill-bar price, so the MAE window / trade_ret are measured from it.
            loc_entry = grading.fill_index(close, date)
            exit_date, exit_type = _resolve_exit(markers, marker_idx)
            loc_exit = grading.fill_index(close, exit_date) if exit_date is not None else None

            if loc_entry is not None and loc_exit is not None and loc_exit > loc_entry:
                # Closed trade — final MAE/outcome (resolves any provisional still_held).
                # Window is strictly forward of the entry fill: [fill+1 .. exit_fill].
                window = close.iloc[loc_entry + 1: loc_exit + 1]
                exit_price = float(close.iloc[loc_exit])
                if len(window) > 0:
                    new_mae = min(0.0, float(window.min()) / entry_price_f - 1.0)
                    if _is_null(row.get("trade_mae")) or row.get("outcome") == "still_held":
                        row["trade_mae"] = new_mae
                        filled = True
                _freeze("exit_date", exit_date)
                _freeze("exit_type", exit_type)
                _freeze("exit_price", exit_price)
                _freeze("trade_ret", exit_price / entry_price_f - 1.0)
                new_outcome = "win" if exit_price >= entry_price_f else "loss"
                if row.get("outcome") != new_outcome:
                    row["outcome"] = new_outcome
                    filled = True
            elif loc_entry is not None and _is_null(row.get("outcome")):
                # Open (no priced exit yet) — provisional still_held; freeze a
                # first-window MAE (the audit excludes still_held from trade_mae, so it
                # is held frozen until an exit resolves it rather than re-extended).
                if len(close) - 1 > loc_entry:
                    fwd_open = close.iloc[loc_entry + 1:]
                    if len(fwd_open) > 0:
                        _freeze("trade_mae", min(0.0, float(fwd_open.min()) / entry_price_f - 1.0))
                    row["outcome"] = "still_held"
                    filled = True

    if filled:
        row["last_backfill_asof"] = asof

    return filled


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with the full schema."""
    return pd.DataFrame(columns=_ALL_COLS)


def _load_close(ticker: str, stocks_dir: Path, dead_prices: dict) -> "pd.Series | None":
    """Daily close for one ticker (split- AND dividend-back-adjusted total-return —
    see the module docstring's price-store caveat; leak-neutral for splits, small
    dividend residual on forward drawdowns; not point-in-time), extended with the
    dead-name terminal series so a delisting grades as a loss instead of the row
    dropping silently. None when no usable series exists."""
    stock_fp = Path(stocks_dir) / f"{ticker}.parquet"
    try:
        close = pd.read_parquet(stock_fp)["close"].dropna()
        close = close.sort_index()
    except Exception:  # noqa: BLE001
        close = None
    return grading.resolve_series(ticker, close, dead_prices=dead_prices)


def _read_existing(out_path: Path) -> pd.DataFrame:
    """Read existing parquet or return empty DataFrame.  Safe if file absent."""
    if not out_path.exists():
        return _empty_df()
    try:
        df = pd.read_parquet(out_path)
        # Ensure all schema columns present (schema evolution guard)
        for col in _ALL_COLS:
            if col not in df.columns:
                df[col] = None
        return df[_ALL_COLS]
    except Exception as exc:
        logger.warning("Could not read existing track_record.parquet: %s — starting fresh", exc)
        return _empty_df()


def _write_parquet(df: pd.DataFrame, out_path: Path) -> None:
    """Write DataFrame to parquet via pyarrow (preserves None as null)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df[_ALL_COLS], preserve_index=False)
    pq.write_table(table, str(out_path))


def _key_tuple(row_or_dict) -> tuple:
    """Return (ticker, date, type) key."""
    if isinstance(row_or_dict, dict):
        return (row_or_dict["ticker"], row_or_dict["date"], row_or_dict["type"])
    return (row_or_dict["ticker"], row_or_dict["date"], row_or_dict["type"])


# ---------------------------------------------------------------------------
# Signal files reader
# ---------------------------------------------------------------------------

def _iter_marker_files(signals_dir: Path):
    """Yield (ticker, markers_list, anchor_era) for every signal JSON in signals_dir.

    ``anchor_era`` is the file's own §7 bucketing-era stamp (R-SQ3), None on a pre-era
    file. It is carried here rather than re-derived so a row records the era of the FILE
    it was read from, not the era of whatever engine happens to be importable.
    """
    for fp in sorted(signals_dir.glob("*.json")):
        ticker = fp.stem
        try:
            doc = json.loads(fp.read_text())
        except Exception as exc:
            logger.debug("Skipping %s: %s", fp.name, exc)
            continue
        markers = doc.get("markers") or []
        if markers:
            yield ticker, markers, doc.get("anchor_era")


def _era_index(existing_keys: dict) -> dict[tuple, list[date]]:
    """(ticker, type) -> the marker dates already logged for it (R-SQ8's boundary guard).

    Snapshotted from the ledger BEFORE ingestion on purpose: rows appended during THIS run
    must not seed the guard, or a genuine second print later in the same file would be
    suppressed by the first. ``(ticker, None)`` holds every date logged for the ticker
    under any type — the "does this name already have logged history" question.
    """
    idx: dict[tuple, list[date]] = {}
    for (ticker, dstr, mtype) in existing_keys:
        try:
            d = date.fromisoformat(str(dstr)[:10])
        except (TypeError, ValueError):
            continue
        idx.setdefault((ticker, mtype), []).append(d)
        idx.setdefault((ticker, None), []).append(d)
    return idx


def _blocked_by_era_floor(ticker: str, mtype: str, dstr: str,
                          era_index: dict[tuple, list[date]]) -> str | None:
    """Why this NEW key must not be appended, or None if it may be (R-SQ8).

    Returns a short reason string so a skip is countable and nameable rather than a silent
    ``continue``.

    THE FLOOR IS A DUPLICATION GUARD, AND IT IS SCOPED TO ITS OWN PREMISE. R-SQ8's
    reasoning is that "pre-floor history in tonight's file is the re-dated image of
    ALREADY-LOGGED events" — which is true exactly when this ledger was already recording
    the name while those dates passed. So a pre-floor key is refused only for a ticker that
    ALREADY HAS logged rows. A ticker with none is not a re-dating of anything: it is a
    fresh build, a rebuilt-from-scratch ledger, or a newly covered name, and refusing its
    history would mean this store could never be reconstructed and every backtest fixture
    would log zero rows. The protection where the premise holds is unchanged: on the live
    ledger every ticker has history, so every pre-floor re-dating is refused.

    The ±``SQ_ERA_BOUNDARY_DAYS`` leg then catches the boundary week — a marker logged just
    under the floor that re-dates to just over it, which the date test alone would let
    through as new.
    """
    stamp = str(dstr)[:10]
    try:
        d = date.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None                       # unparseable date: not this guard's call to make
    if stamp < SQ_ANCHOR_ERA_FLOOR and era_index.get((ticker, None)):
        return "pre_era_marker"           # the re-dated image of an already-logged event
    for prior in era_index.get((ticker, mtype), ()):
        if abs((d - prior).days) <= SQ_ERA_BOUNDARY_DAYS:
            return "boundary_week_duplicate"
    return None


def _load_asof(mtf_path: Path, asof_override: str | None) -> str:
    """Load asof from mtf_signals_latest.json or use the override."""
    if asof_override:
        return asof_override
    try:
        doc = json.loads(mtf_path.read_text())
        return str(doc.get("asof", ""))
    except Exception as exc:
        logger.warning("Could not read mtf_path %s: %s — using empty asof", mtf_path, exc)
        return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_track_record(
    repo_root: str | Path | None = None,
    signals_dir: str | Path | None = None,
    mtf_path: str | Path | None = None,
    stocks_dir: str | Path | None = None,
    out_path: str | Path | None = None,
    asof: str | None = None,
    *,
    data_dir: "Path | None" = None,
    stockdata_dir: "Path | None" = None,
) -> dict:
    """Append-only, idempotent track-record logger.

    Parameters
    ----------
    repo_root : path to the repo root; default = two directories above this file.
    signals_dir : path to site/signals/*.json  (per-ticker chart markers).
    mtf_path : path to data/signal_archive/mtf_signals_latest.json.
    stocks_dir : path to data/stocks/*.parquet.
    out_path : output parquet path.
    asof : override for the run's as-of string; default = mtf leaf's 'asof'.
    data_dir : (W0-stageB) override for data/ root (regime_vector parquet, species registry).
    stockdata_dir : (W0-stageB) override for site/stockdata/ (archetype source).

    Returns
    -------
    dict with keys: new_rows, matured_rows, total_rows, skipped_pending, out_path,
                    unstamped_count (rows with no regime_vector coverage — §3.4 honesty).
    """
    # --- reset per-run caches (species registry, archetype cache) ---
    _reset_per_run_caches()

    # --- resolve paths ---
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    repo_root = Path(repo_root)

    if signals_dir is None:
        signals_dir = repo_root / "site" / "signals"
    if mtf_path is None:
        mtf_path = repo_root / "data" / "signal_archive" / "mtf_signals_latest.json"
    if stocks_dir is None:
        stocks_dir = repo_root / "data" / "stocks"
    if out_path is None:
        out_path = repo_root / "data" / "signal_archive" / "track_record.parquet"
    if data_dir is None:
        data_dir = repo_root / "data"
    if stockdata_dir is None:
        stockdata_dir = repo_root / "site" / "stockdata"

    signals_dir = Path(signals_dir)
    mtf_path    = Path(mtf_path)
    stocks_dir  = Path(stocks_dir)
    out_path    = Path(out_path)
    data_dir    = Path(data_dir)

    # --- resolve asof (NEVER use wall-clock) ---
    run_asof = _load_asof(mtf_path, asof)

    # --- load existing parquet ---
    existing = _read_existing(out_path)

    # Build a mutable dict keyed by (ticker, date, type) for O(1) lookup.
    # Each value is a row dict.  We preserve insertion order (first-observed wins).
    existing_keys: dict[tuple, dict] = {}
    for _, row in existing.iterrows():
        key = (str(row["ticker"]), str(row["date"]), str(row["type"]))
        existing_keys[key] = row.to_dict()

    new_rows: list[dict] = []
    skipped_pending = 0
    matured_rows = 0
    # R-SQ8: the era floor's view of the ledger, snapshotted BEFORE ingestion.
    era_index = _era_index(existing_keys)
    era_skips: dict[str, int] = {}
    # Ticker renames: a superseded string is not a valid ledger key. The era floor cannot
    # cover this — it is scoped per-ticker-STRING and a renamed name has no logged rows,
    # so it reads as a fresh name and the whole re-dated history is admitted (SATS/ECHO,
    # 2026-06-29: BOTH strings were new in the SAME run, and `_era_index` is snapshotted
    # before ingestion by design, so neither could ever see the other). Counted and named,
    # never a silent `continue`.
    _migrations = ledger_identity.load_migrations()
    _superseded = ledger_identity.superseded_keys(_migrations)
    migration_skips: dict[str, int] = {}

    # W0-stageB: load species registry once per run and build mtype→species map
    registry = _load_species_registry(repo_root, data_dir=data_dir)
    mtype_to_species = _build_mtype_to_species(registry)

    # W0-stageB: pre-wire the stockdata dir into the archetype cache
    global _archetype_stockdata_dir  # noqa: PLW0603
    _archetype_stockdata_dir = Path(stockdata_dir)

    # dead-name terminal store (8-K Item 1.03 bankruptcy imputation) — a name that
    # delisted mid-horizon still grades at its loss instead of vanishing (W1c, audit #15).
    try:
        dead_prices = grading.load_dead_prices()
    except Exception:  # noqa: BLE001 — additive, never fatal
        dead_prices = {}

    # --- process each ticker's signal file ---
    # Tonight's stream per ticker + every key it visited: the orphan-maturation pass below
    # needs both to keep a re-dated row maturing (R-SQ8).
    tonight: dict[str, list[dict]] = {}
    visited: set[tuple] = set()
    for ticker, markers, file_era in _iter_marker_files(signals_dir):
        # Checked BEFORE the price load on purpose: at the moment of a rename BOTH files
        # exist and BOTH resolve prices (that is exactly how the double count happened),
        # so a guard that only fires once the old store rots is a guard that fires years
        # late. The map is operator-ratified — the old string is simply not a key here.
        if ticker in _superseded:
            migration_skips[ticker] = migration_skips.get(ticker, 0) + len(markers)
            continue
        close = _load_close(ticker, stocks_dir, dead_prices)
        if close is None or close.empty:
            logger.debug("No price data for %s — skipping", ticker)
            continue
        tonight[ticker] = markers

        for idx, marker in enumerate(markers):
            mtype   = marker.get("type", "")
            quality = marker.get("quality")

            # --- skip rules (CHARTER) ---
            # risk_flags is a separate date list on the doc, never a marker type → ignore
            # pending quality on buy/rebuy → skip (repaint bait)
            if mtype in _ENTRY_TYPES and quality == "pending":
                skipped_pending += 1
                continue

            # Only log: buy/rebuy (quality=take/block) and sell/cut
            if mtype not in (_ENTRY_TYPES | _EXIT_TYPES):
                continue

            key = (ticker, marker["date"], mtype)
            visited.add(key)

            if key in existing_keys:
                # Row already exists — fill NULL maturation columns only (NEVER overwrite
                # non-null identity or regime_vector columns — keep-FIRST is global).
                row = existing_keys[key]
                changed = _fill_maturation(row, markers, idx, close, run_asof)
                # W0-stageB: backfill regime_vector for historical rows where vector_asof
                # is null (PIT-safe: reads only persisted rows ≤ marker_date).
                if _is_null(row.get("vector_asof")):
                    rv_back = _regime_stamp(row["date"], data_dir=data_dir)
                    if not _is_null(rv_back.get("vector_asof")):
                        # Keep-FIRST: only fill null columns (never overwrite a non-null value)
                        for col in ("rate_pressure", "quad_hard_label", "fused_risk_label",
                                    "vol_regime", "risk_radar_state", "regime_vector_degraded",
                                    "vector_asof", "staleness_hours"):
                            if _is_null(row.get(col)):
                                row[col] = rv_back.get(col)
                                changed = True
                if changed:
                    matured_rows += 1
            else:
                # R-SQ8: the §7 anchor-era floor. A key that is new only because the grid
                # re-anchored is the RE-DATED IMAGE of a row already in this ledger, not a
                # new event — appending it would double-count the same physical fire
                # forever. Counted and named, never a silent `continue`.
                blocked = _blocked_by_era_floor(ticker, mtype, marker["date"], era_index)
                if blocked:
                    era_skips[blocked] = era_skips.get(blocked, 0) + 1
                    continue
                # New row — build identity + entry-time features + attempt maturation
                row = _build_row(
                    ticker, marker, markers, idx, close, run_asof,
                    mtype_to_species=mtype_to_species,
                    data_dir=data_dir,
                    stockdata_dir=stockdata_dir,
                    anchor_era=file_era,
                )
                _fill_maturation(row, markers, idx, close, run_asof)
                existing_keys[key] = row
                new_rows.append(row)

    # --- R-SQ8: keep a RE-DATED row maturing. The loop above is keyed on tonight's
    # markers, so a logged row whose marker moved under the anchor cutover is never visited
    # again and its forward columns would freeze as NULL forever — silently retiring the
    # ledger's whole pre-era population on the one night it must keep grading. R-SQ8
    # requires the opposite ("existing rows keep maturing normally").
    #
    # SCOPED EXACTLY TO WHAT THE FLOOR REFUSED, and for the same reason: a row is treated
    # as re-dated only when tonight's stream carries a marker of the SAME type within
    # SQ_ERA_BOUNDARY_DAYS of it — the identical relation `_blocked_by_era_floor` uses to
    # call that marker this row's image. Anything else is left exactly as before: a row
    # this ledger never matured is not this charter's to start maturing, and widening the
    # pass would back-fill legacy rows that predate the columns themselves.
    # `entry_idx` is the count of markers at or before the row's own date, so
    # `_resolve_exit` scans exactly the markers that follow it and a re-dated exit resolves
    # normally. Keep-FIRST throughout — nothing is overwritten, and no logged row is ever
    # re-dated to match the new stream.
    _orphan_close: dict[str, Any] = {}
    for key, row in list(existing_keys.items()):
        mtype = row.get("type")
        if key in visited or mtype not in (_ENTRY_TYPES | _EXIT_TYPES):
            continue
        stream = tonight.get(row["ticker"])
        if stream is None:                    # no signal file tonight: nothing to grade against
            continue
        try:
            row_d = date.fromisoformat(str(row["date"])[:10])
        except (TypeError, ValueError):
            continue
        redated = False
        for m in stream:
            if m.get("type") != mtype:
                continue
            try:
                md = date.fromisoformat(str(m.get("date"))[:10])
            except (TypeError, ValueError):
                continue
            if abs((md - row_d).days) <= SQ_ERA_BOUNDARY_DAYS:
                redated = True
                break
        if not redated:
            continue
        tkr = row["ticker"]
        if tkr not in _orphan_close:
            _orphan_close[tkr] = _load_close(tkr, stocks_dir, dead_prices)
        oc = _orphan_close[tkr]
        if oc is None or oc.empty:
            continue
        entry_idx = sum(1 for m in stream if str(m.get("date", "")) <= str(row["date"])) - 1
        if _fill_maturation(row, stream, entry_idx, oc, run_asof):
            matured_rows += 1

    # --- W0.2 Stage C: mature near-miss rows (graded as predictions, §5.2 move 3).
    # Their keys never re-appear in the §7 marker stream, so the marker loop above
    # cannot mature them; this pass fills their NULL forward columns from the same
    # price store + fill conventions. hygiene_screen rows are never graded
    # (Appendix A: hygiene is not a forecast). Keep-FIRST throughout (fill-null-only).
    _nm_close_cache: dict[str, Any] = {}
    for row in existing_keys.values():
        if row.get("type") != NEAR_MISS_TYPE:
            continue
        if row.get("primary_rejection_reason") == "hygiene_screen":
            continue
        tkr = row["ticker"]
        if tkr not in _nm_close_cache:
            _nm_close_cache[tkr] = _load_close(tkr, stocks_dir, dead_prices)
        nm_close = _nm_close_cache[tkr]
        if nm_close is None or nm_close.empty:
            continue
        nm_marker = {"date": row["date"], "type": NEAR_MISS_TYPE}
        changed = _fill_maturation(row, [nm_marker], 0, nm_close, run_asof)
        if _is_null(row.get("vector_asof")):
            rv_back = _regime_stamp(row["date"], data_dir=data_dir)
            if not _is_null(rv_back.get("vector_asof")):
                for col in ("rate_pressure", "quad_hard_label", "fused_risk_label",
                            "vol_regime", "risk_radar_state", "regime_vector_degraded",
                            "vector_asof", "staleness_hours"):
                    if _is_null(row.get(col)):
                        row[col] = rv_back.get(col)
                        changed = True
        if changed:
            matured_rows += 1

    # --- assemble final DataFrame ---
    all_rows = list(existing_keys.values())
    if not all_rows:
        out_df = _empty_df()
    else:
        out_df = pd.DataFrame(all_rows, columns=_ALL_COLS)

    # --- §3.4 honesty: count rows with no regime_vector coverage (unstamped) ---
    unstamped_count = 0
    if not out_df.empty and "vector_asof" in out_df.columns:
        unstamped_count = int(out_df["vector_asof"].isna().sum())
    logger.info(
        "track_record: %d rows have no regime_vector coverage (vector_asof=null)",
        unstamped_count,
    )
    if unstamped_count > 0:
        print(
            f"track_record: {unstamped_count} rows unstamped (no regime_vector "
            f"coverage — §3.4; these pre-date the persisted vector)",
        )

    # --- write (gated: nightly lane only) ---
    if _ledger_advance_enabled():
        _write_parquet(out_df, out_path)
    else:
        logger.debug(
            "track_record.update_track_record: ledger write skipped "
            "(COLLECT_LANE != nightly)"
        )

    # R-SQ8 disclosure: how many candidate keys the era floor refused, and why. Emitted as
    # a GitHub annotation with a BARE print at column 0 (house law — a logger prefixes the
    # line and GitHub silently drops it), so the cutover night is visible in the Actions
    # summary rather than only in a return value nobody reads.
    if era_skips:
        print(
            f"::notice title=track-record-era-floor::{sum(era_skips.values())} marker "
            f"key(s) refused by the §7 anchor-era floor ({SQ_ANCHOR_ERA_FLOOR}): "
            f"{era_skips} — re-dated images of rows already logged pre-era, not new "
            f"events (R-SQ8)",
            flush=True,
        )
        logger.info("track_record: era-floor skips %s", era_skips)

    # Same disclosure discipline for the rename guard: a signal file still rendering under
    # a superseded key is a live re-log attempt, and silence is how 128 duplicate EchoStar
    # rows accrued unnoticed for six weeks. Bare print at column 0 (house law).
    if migration_skips:
        pairs = {t: _migrations[t] for t in migration_skips}
        print(
            f"::notice title=track-record-key-migration::{sum(migration_skips.values())} "
            f"marker(s) refused under superseded ticker key(s) {pairs} — already logged "
            f"under the current key (quality.ticker_key_migrations); re-logging them "
            f"would double-weight one company",
            flush=True,
        )
        logger.info("track_record: migration skips %s", migration_skips)

    return {
        "new_rows": len(new_rows),
        "matured_rows": matured_rows,
        "total_rows": len(out_df),
        "skipped_pending": skipped_pending,
        "skipped_pre_era": sum(era_skips.values()),
        "era_floor_skips": dict(era_skips),
        "skipped_superseded_key": sum(migration_skips.values()),
        "migration_skips": dict(migration_skips),
        "out_path": str(out_path),
        "unstamped_count": unstamped_count,
    }


# --------------------------------------------------------------------------- #
# W0.2 Stage C — the near-miss capture API (masterplan §5.2 move 2, Appendix A)
# --------------------------------------------------------------------------- #
def log_near_misses(
    near: list[dict],
    repo_root: "Path | None" = None,
    *,
    out_path: "Path | None" = None,
    stocks_dir: "Path | None" = None,
    data_dir: "Path | None" = None,
    stockdata_dir: "Path | None" = None,
) -> dict:
    """Append near-miss rows to the track-record ledger, keyed
    ``(ticker, date, NEAR_MISS_TYPE)``, keep-FIRST.

    A near-miss is a candidate failing EXACTLY ONE Appendix-A condition at
    evaluation time. ``near`` rows carry:
      {ticker, date, primary_rejection_reason, reason_detail?}

    * ``primary_rejection_reason`` MUST be in ``grading.REJECTION_TAXONOMY``
      (the CLOSED set) — unknown reasons are rejected and counted, never a
      silent enum extension (§8 row required to extend).
    * rows get the same identity / regime-vector / species / archetype stamps
      as fires (via ``_build_row``) and mature under the same one-grader fill
      conventions — "grade rejections as predictions" (§5.2 move 3).
    * ``hygiene_screen`` rows are captured but NEVER graded (Appendix A:
      hygiene is not a forecast) — their maturation columns stay null.

    Pre-registered hypothesis this ledger encodes from birth (§5.2):
    **rejection ≠ blacklist** — the failed2/S6 evidence suggests some rejection
    cohorts may OUTPERFORM their accepted siblings; near-miss cohorts are the
    natural controls that make gate P&L attribution estimable at all.

    Returns {n_submitted, n_new, n_duplicate, n_rejected_reason, n_no_price}.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    repo_root = Path(repo_root)
    if out_path is None:
        out_path = repo_root / "data" / "signal_archive" / "track_record.parquet"
    if stocks_dir is None:
        stocks_dir = repo_root / "data" / "stocks"
    if data_dir is None:
        data_dir = repo_root / "data"
    if stockdata_dir is None:
        stockdata_dir = repo_root / "site" / "stockdata"
    out_path = Path(out_path)

    _reset_per_run_caches()
    global _archetype_stockdata_dir  # noqa: PLW0603
    _archetype_stockdata_dir = Path(stockdata_dir)
    registry = _load_species_registry(repo_root, data_dir=data_dir)
    mtype_to_species = _build_mtype_to_species(registry)
    try:
        dead_prices = grading.load_dead_prices()
    except Exception:  # noqa: BLE001
        dead_prices = {}

    existing = _read_existing(out_path)
    existing_keys: dict[tuple, dict] = {}
    for rec in existing.to_dict(orient="records"):
        existing_keys[(rec.get("ticker"), rec.get("date"), rec.get("type"))] = rec

    out = {"n_submitted": len(near or []), "n_new": 0, "n_duplicate": 0,
           "n_rejected_reason": 0, "n_no_price": 0, "n_key_migrated": 0}
    # Ticker renames. Unlike the marker loop above — where a superseded file carries a
    # WHOLE re-dated history and re-logging it is the double count — `near` is one live
    # observation per row, so the honest repair is to RE-KEY it onto the company's current
    # key, not to drop it. Keep-FIRST on the resolved key then collapses a submission that
    # arrives under both strings, instead of filing it twice.
    _nm_migrations = ledger_identity.load_migrations()
    close_cache: dict[str, Any] = {}
    for nm in (near or []):
        tkr = nm.get("ticker")
        d = str(nm.get("date") or "")
        reason = nm.get("primary_rejection_reason")
        if not tkr or not d:
            out["n_rejected_reason"] += 1
            continue
        resolved = ledger_identity.current_key(tkr, _nm_migrations)
        if resolved != tkr:
            logger.info("log_near_misses: %s is a superseded key — logging under %s",
                        tkr, resolved)
            out["n_key_migrated"] += 1
            tkr = resolved
        if reason not in grading.REJECTION_TAXONOMY:
            logger.warning("log_near_misses: %s carries non-taxonomy reason %r — "
                           "REJECTED (Appendix A is a closed set)", tkr, reason)
            out["n_rejected_reason"] += 1
            continue
        key = (tkr, d, NEAR_MISS_TYPE)
        if key in existing_keys:
            out["n_duplicate"] += 1        # keep-FIRST: never overwrite
            continue
        if tkr not in close_cache:
            close_cache[tkr] = _load_close(tkr, stocks_dir, dead_prices)
        close = close_cache[tkr]
        if close is None or close.empty:
            out["n_no_price"] += 1
            continue
        marker = {"date": d, "type": NEAR_MISS_TYPE}
        asof_str = str(close.index.max().date())
        row = _build_row(tkr, marker, [marker], 0, close, asof_str,
                         mtype_to_species=mtype_to_species,
                         data_dir=data_dir, stockdata_dir=stockdata_dir)
        row["primary_rejection_reason"] = reason
        row["reason_detail"] = (str(nm.get("reason_detail"))
                                if nm.get("reason_detail") else None)
        if reason != "hygiene_screen":     # hygiene is not a forecast — never graded
            _fill_maturation(row, [marker], 0, close, asof_str)
        existing_keys[key] = row
        out["n_new"] += 1

    if out["n_new"]:
        if _ledger_advance_enabled():
            all_rows = list(existing_keys.values())
            _write_parquet(pd.DataFrame(all_rows, columns=_ALL_COLS), out_path)
        else:
            logger.debug(
                "track_record.log_near_misses: ledger write skipped "
                "(COLLECT_LANE != nightly)"
            )
    logger.info("log_near_misses: %s", out)
    return out
