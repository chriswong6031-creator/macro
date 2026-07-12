"""Board-ORDER forward track-record for the China standout strip — the keystone the review called
for. The per-name POTENTIAL grader ([[china-name-potential-score]] → engine/name_score_grader)
scores potential_score rank-IC; it does NOT observe the ``signal_gate.blend_sorted`` BOARD ORDER
(cascade tier × setup percentile × washout/extension bonus) that actually decides which names sit
at the TOP of china_stocks.html. So nothing today measures the user's exact worry — "the top pick
already ran / underperforms". This ledger closes that gap:

  • append_board(rows, asof) — append today's ranked top-N standout rows (board_rank, ticker, tier,
    setup, extended, washout, and the as-of close `level`) to an append-only, point-in-time store,
    keep-FIRST per (date, ticker) so a logged rank is never overwritten / leaked.
  • grade() — for every matured row join the name's forward return and report, per horizon:
    TOP-decile vs rest mean forward return, the board RANK-IC (rank vs forward — a well-ordered
    board has a NEGATIVE rank-IC: rank #1 should outperform), and EXTENDED-vs-not forward (does the
    anti-chase demote actually flag underperformers?). "accruing" until enough.

GRADING CONVENTIONS (locked in the SAME pass as the store-group fix so the first number ever
published is unbiased — CN-1 masterplan §W6-CN):
  • CSI300-RELATIVE excess, never absolute. Benchmark = 510300.SS (the CSI300 ETF, data/china).
    An absolute A-share return conflates the reversal pick with the whole-market beta; the honest
    question is "did the top-of-board beat the index it was picked from".
  • FILL-REALISTIC entry. The logged reference `level` is the as-of CLOSE, which a retail user cannot
    trade — the earliest legal fill is the NEXT session (T+1). Entry = T+1 (H+L)/2 (Open is not
    collected for the whole store yet; (H+L)/2 with the high as the bound is the measured proxy —
    +4.41%/21d vs +2.13% buy-the-high, the dominant fill uncertainty). Once collectors/_stock_ohlc
    carries a real Open, upgrade the proxy to the true T+1 open (see ENTRY_BASIS below).
  • EXCLUDE locked-limit-all-day rows on the entry day (high==low==close): genuinely unfillable
    (0.22% of entries) — grading them fabricates a fill that never existed.
  • FLAG pinned-at-limit reference closes (the as-of close sat at the ±limit): the measured bias
    DOUBLES there (hit 50%→42.6%). We already grade every row from the T+1 fill (never the pinned
    reference close), so the pin only carries an informational `pinned` flag in the output.
  • NEVER grade from §7 marker dates. engine/signal_quality.py:161 resolves a 'take' label with the
    NEXT bar's close (+5.7pp/10d look-ahead). This ledger anchors ONLY on the board-date close
    (post-confirmation — verified safe 60/60), then fills T+1. The confirmation-day close is the
    earliest legal anchor; the forward window starts at the T+1 fill.

This is the honest prerequisite for promoting the anti-chase extension DEMOTE to a HARD veto: only
once grade() shows extended top-of-board names underperform (CSI300-relative, fill-realistic) should
the veto go live. Append-only, point-in-time, keep-first (leak-free). RESEARCH / display telemetry —
never a trade trigger. Mirrors engine/name_score_grader. See [[signal-track-record-logger]].

W0 Stage B-d additions (§5.1 sub-task 5, §3.4 Asia-lane stamping):
  1. CN-NATIVE SPINE AXES on top of _t1_fill (NOT via grading.fill_index — that is the US
     next-bar convention; CN uses the T+1 HL2 fill with locked-limit exclusion preserved):
     (a) terminal-state partition at clean15_126 and clean8_21 — barrier race on CN close
         path FROM the T+1 HL2 fill (straddle tie: stop wins); barrier CONSTANTS imported
         from engine.grading (STOP_BARRIER, CUSHION_BARRIER, LIFTOFF_15, LIFTOFF_8,
         LIFTOFF_HORIZON_126, LIFTOFF_HORIZON_21) so definitions are shared even though
         the fill convention differs.
     (b) fwd_mfe at horizons 5/10/21/63 from the T+1 HL2 fill.
     (c) post_cushion_breach per-fire flag (cushioned-then-stopped = True) from CN fill.
     (d) fill_basis="t1_hl2" provenance column on every row so cross-market readers can
         never confuse fill conventions with board_ledger (HK/CA) which uses grading fill.
     Locked-limit-excluded rows: all new axes null (unfillable is unfillable).
  2. _slice_table STRATIFIER COLUMNS: species_id, archetype added as nullable stratifiers.
  3. REGIME STAMPS (§3.4 Asia-lane rules):
     (a) own_market_regime=null + own_market_regime_note documenting the constraint.
         data/china_regime/regime_history.parquet is recomputed from scratch each run
         (china_run.py L41: store_df.to_parquet overwrite) — NOT PIT append-only.
         Stamping from it would produce non-PIT historical values.
     (b) US vector as explicitly-labeled context: us_rate_pressure, us_quad_hard_label,
         us_fused_risk_label, us_vol_regime, us_risk_radar_state, us_regime_vector_degraded
         + vector_asof + staleness_hours via get_vector_for_date called with the ROW'S OWN
         DATE (PIT; asia-lane: last COMMITTED vector, never recomputed mid-lane).
     (c) Backfill null stamps ONLY from the persisted vector for covered dates; residual
         unstamped count printed in grade() output.
  4. SPECIES/ARCHETYPE nullable columns:
     CN-WASHOUT and CN-REVERSAL both bind "china_standout_track" (registry.json), but
     board rows don't distinguish which species fired → species_id=null (ambiguous binding).
     T1-T4 and S1 also bind "us_board_ledger + china_standout_track" — same ambiguity.
     archetype: CN callers (build_china_library) don't pass an 'archetype' key → null.
  5. DTYPE HARDENING (_coerce_object_cols): pandas 3.x refuses string/bool cell writes to
     all-NaN columns typed float64 (loaded from legacy parquet). Coerce ALL string/bool
     nullable columns to object dtype at every frame-assembly point. Complete column set
     documented in _OBJECT_COLS_CN below."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import grading as _grading
from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months
_TOP_DECILE = 0.10
_STORE = "china_standout_track"
# A-share session settles ~07:00 UTC (15:00 CST close). A price panel collected BEFORE that on the
# board date carries a mid-session partial bar (93.9% of names differ from settled close, median
# 1.2%). The ledger's integrity today rests on a keep-first ACCIDENT (a stale panel reuses the prior
# as_of whose keys already exist, so the partial board is silently discarded). Make it explicit.
_SESSION_SETTLE_UTC_H = 7
_PANEL_SOURCE = "china_stocks"            # the run_status source whose checked_at = panel collection UTC
_BENCH = "510300.SS"                      # CSI300 ETF — the ONLY China excess benchmark (data/china)
# Board tickers are per-NAME A-shares (.SS/.SZ) that live in the china_stocks OHLC store; the small
# handful of ETFs on a board fall back to the index/ETF store. The #791 bug read only `china` (30
# ETFs) → 0/120 names resolved → n_graded=0 forever. Try names first, ETFs second.
_PRICE_GROUPS = ("china_stocks", "china")
ENTRY_BASIS = "t1_hl2"                    # T+1 (H+L)/2 proxy; upgrades to true T+1 open when collected
_MIN_GRADED = 8                           # per-horizon rows required before a number is published

# W0 Stage B-d: MFE horizons for CN-native spine (superset of _HORIZONS_D — added 5 and 10)
_MFE_HORIZONS = (5, 10, 21, 63)

# W0 Stage B-d: US-context regime stamp columns (prefixed us_* — explicitly context, not primary)
_US_STAMP_COLS = (
    "us_rate_pressure",
    "us_quad_hard_label",
    "us_fused_risk_label",
    "us_vol_regime",
    "us_risk_radar_state",
    "us_regime_vector_degraded",
    "vector_asof",
    "staleness_hours",
)

# W0 Stage B-d: CN-native spine maturation columns (all nullable)
_SPINE_COLS = (
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63",
    "terminal_state_clean15_126",
    "terminal_state_clean8_21",
    "post_cushion_breach",
    "fill_basis",
)

# W0 Stage B-d: species/archetype + regime stamp columns
_SPECIES_COLS = ("species_id", "archetype")
_OWN_REGIME_COLS = ("own_market_regime", "own_market_regime_note")

# Columns that carry strings (or bools) but are nullable: an all-NaN column loaded from parquet
# types float64 and pandas 3.x then REFUSES a string/bool cell write (TypeError: Invalid value
# 'CLEAN_LIFTOFF' for dtype 'float64'). Coerce to object at every frame-assembly point.
# Complete column set — B-c review found a missed bool column; list every string/bool nullable
# column explicitly.
_OBJECT_COLS_CN = (
    "species_id",
    "archetype",
    "own_market_regime",
    "own_market_regime_note",
    "us_rate_pressure",
    "us_quad_hard_label",
    "us_fused_risk_label",
    "us_vol_regime",
    "us_risk_radar_state",
    "us_regime_vector_degraded",   # bool but nullable — coerce to object
    "vector_asof",
    "terminal_state_clean15_126",
    "terminal_state_clean8_21",
    "post_cushion_breach",         # bool but nullable — coerce to object
    "fill_basis",
)

# Own-market regime constraint note (documented null — see module docstring §3a)
# china_run.py L41: store_df.to_parquet(p / "regime_history.parquet") — full overwrite, non-PIT.
# SA-W2: from store birth (2026-07-12+) forward, own_market_regime is stamped from the new
# PIT store (data/china_regime/regime_daily.parquet) created by engine/china_regime_store.py.
# Pre-store rows keep this null note; post-store rows use the stamped-from note below.
_OWN_REGIME_NOTE_CN = (
    "null: data/china_regime/regime_history.parquet is recomputed from scratch on each "
    "run (china_run.py: store_df.to_parquet full overwrite — NOT PIT append-only). "
    "Stamping historical rows from it would produce non-PIT values. Wire a daily-append "
    "PIT file to enable own-market stamps. CN single-macro-regime caveat applies until "
    "a second regime accrues in the forward ledger."
)
# Note used when own_market_regime IS stamped from the PIT store (SA-W2 forward-only).
_OWN_REGIME_NOTE_PIT = (
    "stamped from data/china_regime/regime_daily.parquet (SA-W2 PIT store, "
    "engine/china_regime_store.py). PIT keep-first; forward-only from store birth."
)

# Species binding note: multiple species bind this ledger; board rows don't disambiguate.
# CN-WASHOUT and CN-REVERSAL both bind 'china_standout_track'; T1-T4 and S1 bind
# 'us_board_ledger + china_standout_track'. A row's tier/marker doesn't map unambiguously
# to one species — therefore species_id=null for ambiguous rows.
# SA-W2: species_id IS derived from the row's own flags at append_board time going forward:
#   washout_2w=True  → 'cn_washout'
#   coiled=True      → 'cn_coiled'
#   else tier-cascade→ 'cn_tier'
# (CN-REVERSAL rows are not currently routed through append_board; document if they are.)
_SPECIES_NOTE = (
    "null: CN-WASHOUT, CN-REVERSAL, T1-T4, and S1 all bind 'china_standout_track'; "
    "board rows do not carry a field that disambiguates which species fired."
)

# ---------------------------------------------------------------------------
# SA-W2: species_id derivation from row flags (forward-only from 2026-07-12).
# Mapping is documented here; taxonomy_version='v2'; loop-IMMUTABLE per SA-R2.
# ---------------------------------------------------------------------------

def _derive_species_id(row: dict) -> str:
    """Derive species_id from a board row's own flags at append time.

    Precedence (most-specific first):
      washout_2w=True  → 'cn_washout'  (2W StochRSI washout-reclaim pattern)
      coiled=True      → 'cn_coiled'   (coiled cohort-washout pattern)
      else             → 'cn_tier'     (tier-cascade board row, T1/T2/T3/T4)

    CN-REVERSAL rows are not currently routed through append_board (they use a
    separate pipeline); if they are added, extend this mapping.

    This function is called at append_board time for NEW rows only (SA-W2 forward).
    Old rows in the parquet are NOT backfilled — they retain species_id=null.
    """
    if bool(row.get("washout_2w")):
        return "cn_washout"
    if bool((row.get("coiled") or {}).get("coiled") if isinstance(row.get("coiled"), dict)
            else row.get("coiled")):
        return "cn_coiled"
    return "cn_tier"


def _coerce_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Force the string-bearing and bool-nullable columns to object dtype (NaN → None).

    Pandas 3.x refuses string/bool writes to all-NaN float64 columns loaded from legacy
    parquet. Call this at every frame-assembly point where spine/regime cols may appear.
    Column set is complete: see _OBJECT_COLS_CN.
    """
    for col in _OBJECT_COLS_CN:
        if col in df.columns and df[col].dtype != object:
            coerced = df[col].astype(object)
            df[col] = coerced.where(pd.notna(coerced), None)
    return df


def _store_path():
    return config.data_dir() / _STORE / "board.parquet"


# ---------------------------------------------------------------------------
# W0 Stage B-d: US regime stamp helpers (Asia-lane rule §3.4)
# Mirrors board_ledger._regime_stamp_for_date — reuse the same get_vector_for_date
# PIT lookup so CN rows carry the same US context as HK/CA rows.
# ---------------------------------------------------------------------------

def _regime_stamp_null() -> dict:
    """Return a null US-regime stamp (used when the parquet is absent or uncovered)."""
    return {
        "us_rate_pressure": None,
        "us_quad_hard_label": None,
        "us_fused_risk_label": None,
        "us_vol_regime": None,
        "us_risk_radar_state": None,
        "us_regime_vector_degraded": None,
        "vector_asof": None,
        "staleness_hours": None,
    }


def _regime_stamp_for_date(date_str: str) -> dict:
    """Return the PIT US regime_vector stamp for ``date_str`` (§3.4 Asia-lane rule).

    Loads the last COMMITTED data/regime/regime_vector.parquet row whose date ≤
    date_str — never recomputes from latest-state sources. Returns a null stamp
    dict when the parquet is absent or no row covers the date.

    Column mapping: regime_vector stores US columns without a 'us_' prefix.
    We re-emit them prefixed 'us_*' so the schema is unambiguous (§3.4:
    'explicitly-labeled CONTEXT column set').
    """
    try:
        from engine.regime_vector import get_vector_for_date  # noqa: PLC0415
        raw = get_vector_for_date(date_str)
    except Exception as exc:  # noqa: BLE001
        log.debug("china_standout_track: regime_stamp_for_date failed for %s: %s", date_str, exc)
        return _regime_stamp_null()

    return {
        "us_rate_pressure":          raw.get("rate_pressure"),
        "us_quad_hard_label":        raw.get("quad_hard_label"),
        "us_fused_risk_label":       raw.get("fused_risk_label"),
        "us_vol_regime":             raw.get("vol_regime"),
        "us_risk_radar_state":       raw.get("risk_radar_state"),
        "us_regime_vector_degraded": raw.get("regime_vector_degraded"),
        "vector_asof":               raw.get("vector_asof"),
        "staleness_hours":           raw.get("staleness_hours"),
    }


# ---------------------------------------------------------------------------
# W0 Stage B-d: CN-native spine scan helpers
# These use the T+1 HL2 fill from _t1_fill — NOT grading.fill_index (that is the
# US next-bar convention). The barrier CONSTANTS are shared with grading.py so the
# partition DEFINITIONS are identical even though the FILL differs.
# ---------------------------------------------------------------------------

def _cn_terminal_state(
    close: pd.Series,
    d0: pd.Timestamp,
    fill: float,
    *,
    liftoff_mult: float,
    liftoff_horizon: int,
) -> str | None:
    """Terminal-state partition from the CN T+1 HL2 fill price.

    Parameters mirror grading.terminal_state but the entry price is supplied
    externally (the T+1 HL2 fill, already computed by _t1_fill) so this function
    does NOT re-run fill_index. The close series is the CN name's close path.

    Returns one of 'STOPPED' / 'DEAD_MONEY' / 'CUSHIONED' / 'CLEAN_LIFTOFF',
    or None when the horizon has not matured yet.

    Partition rules (mirroring grading.terminal_state §1.1):
      - Barrier race on close path starting from the bar AFTER the T+1 fill bar.
      - STRADDLE TIE: stop wins (checked first on each bar).
      - STOPPED:       first bar ≤ fill * STOP_BARRIER
      - CLEAN_LIFTOFF: first bar ≥ fill * liftoff_mult (before stop)
      - CUSHIONED:     first bar ≥ fill * CUSHION_BARRIER (before stop, no liftoff)
      - DEAD_MONEY:    ±DEAD_MONEY_BAND never breached AND ret < DEAD_MONEY_CAP

    CN caveat: uses the same dividend-adjusted close series as the excess return.
    Barriers as ratios to fill cancel the adjustment (consistent basis).
    CN single-macro-regime caveat: re-grade when second regime accrues.
    """
    # Forward close bars after d0 (T+1 is index[0]; the scan window is T+2 onwards for
    # the barrier race, consistent with grading.terminal_state which starts from fill+1).
    # We need the T+1 fill bar itself to know fill_date, then scan from fill+1.
    fwd_all = close[close.index > d0]  # bars strictly after board date
    if len(fwd_all) == 0:
        return None
    # T+1 fill bar is fwd_all.iloc[0]; barrier scan starts from the bar AFTER that
    scan = fwd_all.iloc[1: 1 + liftoff_horizon]  # (T+2 .. T+1+liftoff_horizon)
    if len(scan) < liftoff_horizon:
        return None  # not yet matured

    arr = scan.to_numpy(dtype=float)
    stop_b    = fill * _grading.STOP_BARRIER
    cushion_b = fill * _grading.CUSHION_BARRIER
    liftoff_b = fill * liftoff_mult
    dead_upper = fill * (1.0 + _grading.DEAD_MONEY_BAND)
    dead_lower = fill * (1.0 - _grading.DEAD_MONEY_BAND)

    stopped_at: int | None = None
    liftoff_at: int | None = None
    cushion_at: int | None = None

    for k, cl in enumerate(arr, start=1):
        if not np.isfinite(cl):
            continue
        if cl <= stop_b:
            stopped_at = k
            break
        if cl >= liftoff_b:
            liftoff_at = k
            if cushion_at is None:
                for j, c2 in enumerate(arr[:k], start=1):
                    if c2 >= cushion_b:
                        cushion_at = j
                        break
                if cushion_at is None:
                    cushion_at = k
            break
        if cushion_at is None and cl >= cushion_b:
            cushion_at = k

    band_breached = bool(np.any(arr >= dead_upper) or np.any(arr <= dead_lower))
    ret_at_read = float(arr[-1]) / fill - 1.0

    if stopped_at is not None:
        return _grading.TerminalState.STOPPED
    if liftoff_at is not None:
        return _grading.TerminalState.CLEAN_LIFTOFF
    if cushion_at is not None:
        return _grading.TerminalState.CUSHIONED
    if not band_breached and ret_at_read < _grading.DEAD_MONEY_CAP:
        return _grading.TerminalState.DEAD_MONEY
    return _grading.TerminalState.DEAD_MONEY  # conservative edge case


def _cn_post_cushion_breach(
    close: pd.Series,
    d0: pd.Timestamp,
    fill: float,
    horizon: int,
) -> bool | None:
    """Post-cushion breakeven-breach flag from the CN T+1 HL2 fill (§1.1 semantics).

    Same semantics as grading.post_cushion_breach: cushioned-then-stopped = True.
    None when the name never reached the cushion barrier within the horizon.
    Operates on the close path from T+2 onwards (consistent with _cn_terminal_state).
    """
    fwd_all = close[close.index > d0]
    if len(fwd_all) == 0:
        return None
    scan = fwd_all.iloc[1: 1 + horizon]  # T+2 .. T+1+horizon
    if len(scan) < horizon:
        return None

    arr = scan.to_numpy(dtype=float)
    stop_b    = fill * _grading.STOP_BARRIER
    cushion_b = fill * _grading.CUSHION_BARRIER

    cushion_bar: int | None = None
    stop_bar: int | None = None
    for k, cl in enumerate(arr, start=1):
        if not np.isfinite(cl):
            continue
        if cl <= stop_b:
            stop_bar = k
            break
        if cl >= cushion_b and cushion_bar is None:
            cushion_bar = k

    # Reuse board_ledger's _breach_after_cushion semantics inline (no import needed):
    # None if never cushioned (or stopped before cushion); True if cushioned then any
    # later close fell back below fill (entry_price); False if held above fill.
    if cushion_bar is None or (stop_bar is not None and stop_bar <= cushion_bar):
        return None
    for cl in arr[cushion_bar:]:
        if np.isfinite(cl) and cl < fill:
            return True
    return False


def _cn_fwd_mfe(
    close: pd.Series,
    d0: pd.Timestamp,
    fill: float,
    horizon: int,
) -> float | None:
    """Max favorable excursion from the CN T+1 HL2 fill within ``horizon`` bars.

    Window: T+2 .. T+1+horizon (consistent with _cn_terminal_state and grading.forward_metrics
    fwd_mfe_H — strictly forward from the fill bar). Always >= 0, or None if not matured.
    """
    fwd_all = close[close.index > d0]
    if len(fwd_all) == 0:
        return None
    scan = fwd_all.iloc[1: 1 + horizon]  # T+2 .. T+1+horizon
    if len(scan) < horizon:
        return None
    vals = pd.to_numeric(scan, errors="coerce").dropna()
    if vals.empty:
        return None
    return max(0.0, float(vals.max()) / fill - 1.0)


def _cn_spine_axes(ticker: str, d0: pd.Timestamp) -> dict:
    """Compute all CN-native spine axes for one board row anchored at board-date ``d0``.

    Uses _t1_fill to get the T+1 HL2 fill (with locked-limit exclusion). If the fill is
    None or locked, ALL axes are returned as None (unfillable is unfillable — we do not
    fabricate a fill). The fill_basis provenance column is always set to ENTRY_BASIS
    ("t1_hl2") so a cross-market reader can never confuse fill conventions.

    Returns a dict with keys: fill_basis, fwd_mfe_5/10/21/63,
    terminal_state_clean15_126, terminal_state_clean8_21, post_cushion_breach.
    """
    null_result = {
        "fill_basis": ENTRY_BASIS,
        "fwd_mfe_5": None, "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
        "terminal_state_clean15_126": None,
        "terminal_state_clean8_21": None,
        "post_cushion_breach": None,
    }
    df = _price_frame(ticker)
    if df is None:
        return null_result
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if close.empty:
        return null_result

    fill, locked, _pinned = _t1_fill(df, d0)
    if fill is None or locked:
        return null_result

    result = {"fill_basis": ENTRY_BASIS}

    # fwd_mfe at each MFE horizon
    for h in _MFE_HORIZONS:
        result[f"fwd_mfe_{h}"] = _cn_fwd_mfe(close, d0, fill, h)

    # Terminal-state partition (positional: clean15_126)
    try:
        result["terminal_state_clean15_126"] = _cn_terminal_state(
            close, d0, fill,
            liftoff_mult=_grading.LIFTOFF_15,
            liftoff_horizon=_grading.LIFTOFF_HORIZON_126,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("china_standout_track: terminal_state_clean15_126 failed for %s/%s: %s",
                  ticker, d0, exc)
        result["terminal_state_clean15_126"] = None

    # Terminal-state partition (rotational: clean8_21)
    try:
        result["terminal_state_clean8_21"] = _cn_terminal_state(
            close, d0, fill,
            liftoff_mult=_grading.LIFTOFF_8,
            liftoff_horizon=_grading.LIFTOFF_HORIZON_21,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("china_standout_track: terminal_state_clean8_21 failed for %s/%s: %s",
                  ticker, d0, exc)
        result["terminal_state_clean8_21"] = None

    # Post-cushion breach at the rotational horizon (horizon=21)
    try:
        result["post_cushion_breach"] = _cn_post_cushion_breach(
            close, d0, fill, _grading.LIFTOFF_HORIZON_21,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("china_standout_track: post_cushion_breach failed for %s/%s: %s",
                  ticker, d0, exc)
        result["post_cushion_breach"] = None

    return result


def session_status(asof: str | None = None) -> dict:
    """Is the board's price panel a SETTLED session or a mid-session partial bar?

    Reads run_status.json for the ``china_stocks`` source: ``checked_at`` (collection UTC) and
    ``last_date`` (newest bar in the panel). A board is a PARTIAL SESSION when the panel's newest bar
    IS the board date AND that panel was collected before ~07:00 UTC (before the A-share close
    settled). Returns {partial_session, collected_utc, collected_hour_utc, last_date, reason}.
    Fail-OPEN on missing status (treat as settled) — a missing stamp must not silently block a real
    nightly board; the asia-lane gate below is the belt-and-braces."""
    out = {"partial_session": False, "collected_utc": None, "collected_hour_utc": None,
           "last_date": None, "reason": "no run_status — assumed settled"}
    try:
        st = store.read_status()
        src = (st.get("sources") or {}).get(_PANEL_SOURCE) or {}
        checked = src.get("checked_at")
        last_date = src.get("last_date")
        out["collected_utc"] = checked
        out["last_date"] = last_date
        if not checked:
            return out
        ts = pd.Timestamp(checked)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("UTC")
        out["collected_hour_utc"] = int(ts.hour)
        # only the CURRENT session can be partial: if the panel's newest bar is the board date and it
        # was collected before the close settled, the board-date bar is mid-session.
        same_day = (asof is not None and last_date is not None and str(last_date) == str(asof))
        if same_day and ts.hour < _SESSION_SETTLE_UTC_H:
            out["partial_session"] = True
            out["reason"] = (f"panel {_PANEL_SOURCE} for {asof} collected {ts.hour:02d}:xx UTC "
                             f"(< {_SESSION_SETTLE_UTC_H:02d}:00 settle) — mid-session partial bar")
        else:
            out["reason"] = "settled (collected after session close or a prior-session board)"
    except Exception as e:  # noqa: BLE001 — a guard failure must not block the ledger
        out["reason"] = f"session-status unreadable: {e}"
    return out


def append_board(rows: list[dict], asof: str | None = None, top_n: int = 60,
                 lane: str | None = None) -> int:
    """Append today's ranked top-N standout rows. Each row is a china_standouts `buy` entry (already
    in board order); we stamp its 1-based board_rank + the fields the grade needs. Keep-FIRST per
    (date, ticker). Returns the ledger row count after the merge. Best-effort — never raises.

    LEDGER-INTEGRITY GATES (CN-1 §W6-CN), replacing the keep-first accident:
      • asia-lane gate: appends only from the asia collection lane (``lane == 'asia'``). The nightly
        render lanes must NOT persist a board (they discard data/ writes anyway); passing lane=None
        preserves the legacy call for the asia build, which is the only one that commits data/.
      • partial-session refusal: if the board's price panel was collected before the A-share close
        settled (session_status().partial_session), REFUSE the append — a mid-session board must
        never win the date in the ledger."""
    if not rows or not asof:
        return 0
    # explicit asia-lane gate: a lane was passed and it is NOT asia → refuse (render lanes never
    # persist). lane=None keeps the historical (asia-build) call working unchanged.
    if lane is not None and lane != "asia":
        log.info("china standout board-track: append gated (lane=%s, not asia)", lane)
        return 0
    sess = session_status(asof)
    if sess.get("partial_session"):
        log.warning("china standout board-track: REFUSING append — %s", sess.get("reason"))
        return 0

    # W0 Stage B-d: stamp the US regime vector once per append call (same asof for all rows)
    rv_stamp = _regime_stamp_for_date(str(asof))

    # SA-W2: stamp own_market_regime from the PIT store (engine/china_regime_store.py).
    # Forward-only from store birth; pre-store dates keep null + _OWN_REGIME_NOTE_CN.
    _cn_regime_row: dict | None = None
    _cn_regime_note: str = _OWN_REGIME_NOTE_CN
    try:
        from engine import china_regime_store as _crs  # noqa: PLC0415
        _cn_regime_row = _crs.get_regime_for_date(str(asof))
        if _cn_regime_row is not None:
            _cn_regime_note = _OWN_REGIME_NOTE_PIT
    except Exception as _crs_exc:  # noqa: BLE001
        log.debug("china_standout_track: cn_regime_store lookup failed for %s: %s", asof, _crs_exc)

    out = []
    for i, r in enumerate(rows[:top_n]):
        tk = r.get("ticker")
        if not tk:
            continue
        ext = r.get("extension") or {}
        sig = r.get("signal") or {}
        _cb = r.get("coiled") or {}
        _es = r.get("entry_signal") or {}
        out.append({
            "date": str(asof), "ticker": str(tk), "board_rank": i + 1,
            "tier": sig.get("tier_cascade"),
            "setup": r.get("setup"),
            "extended": bool(ext.get("extended")),
            "washout": bool(r.get("washout_2w")),
            "level": r.get("price"),
            # COILED wave-3 CN columns (wave-3 ship record 2026-07-02). New columns appended
            # to existing parquet rows via pd.concat schema union — old rows read fine (missing
            # cols become NaN, which pd.concat handles transparently; bool() of NaN = False).
            "coiled":        bool(_cb.get("coiled")),
            "coiled_star":   bool(_cb.get("star")),
            "coiled_cohort": _cb.get("cohort"),
            # COILED-FIRE wave-4 display chip fields (wave-4 ship record 2026-07-02).
            # Schema-union safe: old parquet rows missing these cols read as NaN (handled by concat).
            "coiled_fire":       bool(_cb.get("fire")),
            "coiled_fire_ticks": _cb.get("fire_ticks"),
            # W0.2a — tier+stage-stratified grading fields (W0 ship record 2026-07-03).
            # Schema-union safe: old parquet rows missing these cols read as NaN via pd.concat.
            # ticks / provisional: native-TF ticks since cross (None for projected T3/T4 cross).
            "ticks":        sig.get("ticks"),
            "provisional":  bool(sig.get("provisional")) if sig.get("provisional") is not None else False,
            # ext_score: extension score 0..1 at fire time (anti-chase anti-rank lever).
            "ext_score":    float((ext.get("score")) or 0.0),
            # washout_2w: explicit-name alias for the 2W StochRSI washout-reclaim flag
            # (kept alongside legacy "washout" for backward compat with existing parquet).
            "washout_2w":   bool(r.get("washout_2w")),
            # hold_state: W6-C basing-state after confluence anchor. None until the HOLD builder
            # port (W0.1) lands and begins populating rec["hold"] — wired here as a schema
            # placeholder so the ledger schema is stable before the first real value arrives.
            "hold_state":   (r.get("hold") or {}).get("state"),
            # entry_status: confluence-gated "buyable now" flag from entry_signal.status.
            "entry_status": _es.get("status"),
            # sector_turn: W0.10 sector first-tick-up flag (phase==Trough & osc_slope>0 in
            # forward_log). Schema-union safe: old parquet rows missing this col read as NaN
            # (handled by pd.concat transparently). "bottoming" when sector qualifies; None otherwise.
            "sector_turn":  (r.get("sector_turn") or {}).get("state"),
            # W1-B stage: lifecycle shelf (ENTRY / RAN_LATE / None) for board rows (rules 1-2).
            # Schema-union safe: old parquet rows missing this col read as NaN via pd.concat.
            "stage":        r.get("stage"),
            # W2-B narrative columns: per-name theme heat + A/B tier (display/ledger only).
            # Schema-union safe: old parquet rows missing these cols read as NaN via pd.concat.
            # narr_theme: basket display name (EN) of the strongest qualifying theme.
            # narr_level: "HOT" | "WARMING" | None
            # narr_rel20: basket 20d return relative to CSI300 (pp)
            # narr_breadth: fraction of basket members above their 20d MA (0..1)
            # ab_tier: "A" | "B" | None (None for RAN_LATE rows per spec)
            "narr_theme":   (r.get("narrative") or {}).get("theme"),
            "narr_level":   (r.get("narrative") or {}).get("level"),
            "narr_rel20":   (r.get("narrative") or {}).get("rel20"),
            "narr_breadth": (r.get("narrative") or {}).get("breadth"),
            "ab_tier":      r.get("ab_tier"),
            # SA-W2: species_id derived from row flags at append time (forward-only from store birth).
            # Precedence: washout_2w=True → 'cn_washout'; coiled=True → 'cn_coiled'; else → 'cn_tier'.
            # Old rows already in the parquet are NOT backfilled — they retain species_id=null.
            # See _derive_species_id for mapping documentation.
            "species_id": _derive_species_id(r),
            "archetype": None,
            # SA-W2: own_market_regime stamped from the PIT store (engine/china_regime_store.py)
            # when available (forward-only from store birth date ~2026-07-12).
            # Pre-store rows: null + _OWN_REGIME_NOTE_CN.
            # Post-store rows: stamped quad + _OWN_REGIME_NOTE_PIT.
            "own_market_regime": _cn_regime_row.get("quad") if _cn_regime_row else None,
            "own_market_regime_note": _cn_regime_note,
            # W0 Stage B-d: US context regime stamp (Asia-lane rule §3.4).
            **rv_stamp,
            # W0 Stage B-d: CN-native spine placeholders (null at birth; matured by grade()).
            # fill_basis is always "t1_hl2" — provenance for cross-market readers.
            "fill_basis": ENTRY_BASIS,
            "fwd_mfe_5": None, "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
            "terminal_state_clean15_126": None,
            "terminal_state_clean8_21": None,
            "post_cushion_breach": None,
        })
    if not out:
        return 0
    try:
        new = pd.DataFrame(out)
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            # schema union: prior frames may predate spine/regime columns — reindex both sides
            # so concat never drops a column; new columns in prior (non-B-d extras) are preserved.
            cols = list(dict.fromkeys([*new.columns, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=cols), new.reindex(columns=cols)],
                ignore_index=True,
            ).drop_duplicates(subset=["date", "ticker"], keep="first")
            combined = _coerce_object_cols(combined)
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china standout board-track append failed: %s", e)
        return 0


def _price_frame(ticker: str) -> pd.DataFrame | None:
    """OHLC frame for a board name — names resolve in china_stocks, ETFs in china. Returns the first
    store that has the ticker, else None. (The #791 dead-on-arrival bug: only `china` was read.)"""
    for g in _PRICE_GROUPS:
        df = store.read(g, str(ticker))
        if df is not None and "close" in df:
            return df
    return None


def _bench_close() -> pd.Series | None:
    """CSI300 (510300.SS) close series, for CSI300-relative excess. None if unavailable."""
    df = store.read("china", _BENCH)
    if df is None or "close" not in df:
        return None
    return pd.to_numeric(df["close"], errors="coerce").dropna()


def _t1_fill(df: pd.DataFrame, d0: pd.Timestamp) -> tuple[float | None, bool, bool]:
    """Fill-realistic entry: the FIRST session strictly AFTER the board-date close (T+1). Returns
    (fill_price, locked_limit, pinned). fill = (H+L)/2 proxy (or true Open if the column exists).
    ``locked_limit`` = T+1 bar printed high==low==close (unfillable — caller must exclude).
    ``pinned`` = the board-date reference CLOSE sat at that day's high==close (informational)."""
    idx = df.index
    after = idx[idx > d0]
    if len(after) == 0:
        return None, False, False
    t1 = after[0]
    row = df.loc[t1]
    hi, lo = row.get("high"), row.get("low")
    op = row.get("open") if "open" in df.columns else None
    close = row.get("close")
    locked = (hi is not None and lo is not None and close is not None
              and pd.notna(hi) and pd.notna(lo) and pd.notna(close)
              and float(hi) == float(lo) == float(close))
    # pinned reference close: the board-date bar closed AT its own high (limit-up-style pin) — the
    # reference the user saw was untradeable; we already grade from the T+1 fill so this is a flag.
    ref = df.loc[d0] if d0 in df.index else None
    pinned = bool(ref is not None and pd.notna(ref.get("high")) and pd.notna(ref.get("close"))
                  and float(ref.get("high")) == float(ref.get("close")))
    if op is not None and pd.notna(op):
        fill = float(op)                                  # true T+1 open once collected
    elif hi is not None and lo is not None and pd.notna(hi) and pd.notna(lo):
        fill = (float(hi) + float(lo)) / 2.0              # (H+L)/2 proxy
    elif close is not None and pd.notna(close):
        fill = float(close)
    else:
        return None, locked, pinned
    return fill, bool(locked), pinned


def _fwd_excess(ticker: str, d0: pd.Timestamp, h: int,
                bench: pd.Series | None) -> tuple[float | None, bool]:
    """Fill-realistic, CSI300-RELATIVE forward excess over ``h`` sessions from a T+1 entry.

    Returns (excess_or_None, pinned). excess = name (fill→+h close) − CSI300 (T+1→+h) return.
    None when: the name doesn't resolve, T+1 is locked-limit (unfillable), or the horizon can't
    mature. NEVER anchored on a §7 marker date — the anchor is the board-date close (post-
    confirmation) and the return is measured from the earliest legal fill (T+1)."""
    df = _price_frame(ticker)
    if df is None:
        return None, False
    fill, locked, pinned = _t1_fill(df, d0)
    if fill is None or locked:                            # unfillable → exclude, don't fabricate
        return None, pinned
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    fwd = close[close.index > d0]                         # sessions after the board date (T+1, T+2, …)
    if len(fwd) <= h:
        return None, pinned
    name_ret = float(fwd.iloc[h] / fill - 1.0)            # buy at the T+1 fill, exit +h sessions
    if bench is None:
        return name_ret, pinned                           # degrade to absolute if the ETF is missing
    bslice = bench[bench.index > d0]
    if len(bslice) <= h:
        return None, pinned
    bench_ret = float(bslice.iloc[h] / bslice.iloc[0] - 1.0)
    return name_ret - bench_ret, pinned                   # CSI300-relative excess


def grade() -> dict:
    """Score every matured board row, CSI300-relative + fill-realistic.

    Returns {available, n_rows, dates, n_graded, n_unstamped, grading, by_horizon} where each
    horizon carries top-decile vs rest mean forward EXCESS, the board RANK-IC (rank vs forward —
    NEGATIVE = a well-ordered board), extended-vs-not forward EXCESS, and a Wilson-CI hit rate vs
    CSI300.

    W0 Stage B-d additions:
      * CN-NATIVE SPINE AXES: computes fwd_mfe_{5,10,21,63}, terminal_state_clean15_126,
        terminal_state_clean8_21, post_cushion_breach from the T+1 HL2 fill via _cn_spine_axes.
        Writes back to the parquet (keep-FRESH per _fwd_excess convention).
      * REGIME BACKFILL: backfills null us_* stamp cols from the persisted vector for covered
        dates only. Never overwrites non-null stamps. Residual unstamped count in output.
      * SPECIES/ARCHETYPE in grade records for _slice_table stratification (nullable).
    """
    p = _store_path()
    if not p.exists():
        return {"available": False, "note": "no board rows logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    # Extend schema for any new columns not yet present in the stored parquet
    # (legacy rows written before B-d will be missing spine + regime + species cols).
    new_cols = [
        *_SPINE_COLS, *_US_STAMP_COLS, *_SPECIES_COLS, *_OWN_REGIME_COLS,
    ]
    for col in new_cols:
        if col not in df.columns:
            df[col] = None
    df = _coerce_object_cols(df)

    # ------------------------------------------------------------------
    # CN-NATIVE SPINE AXES (keep-FRESH: recompute on every grade() run)
    # Uses _cn_spine_axes which calls _t1_fill internally — never via grading.fill_index.
    # Locked-limit rows: all spine cols remain null (unfillable is unfillable).
    # ------------------------------------------------------------------
    spine_updates: list[tuple] = []  # (idx, patch_dict)
    for idx, row in df.iterrows():
        d0 = pd.Timestamp(str(row["date"]))
        ticker = str(row["ticker"])
        spine = _cn_spine_axes(ticker, d0)
        spine_updates.append((idx, spine))

    if spine_updates:
        for idx, patch in spine_updates:
            for col, val in patch.items():
                df.at[idx, col] = val

    # ------------------------------------------------------------------
    # REGIME BACKFILL: backfill null us_* stamp cols from persisted vector.
    # grade() only fills null slots — never overwrites non-null stamps.
    # Handles rows appended before the B-d schema change.
    # ------------------------------------------------------------------
    us_cols = list(_US_STAMP_COLS)

    def _row_is_unstamped(r) -> bool:
        return all(
            (r.get(c) is None or (isinstance(r.get(c), float) and np.isnan(r.get(c)))
             or str(r.get(c)) in ("", "nan", "None", "NaT"))
            for c in us_cols
        )

    n_backfilled = 0
    for idx, row in df.iterrows():
        if _row_is_unstamped(row):
            date_str = str(row["date"])
            stamp = _regime_stamp_for_date(date_str)
            for col, val in stamp.items():
                df.at[idx, col] = val
            n_backfilled += 1

    n_unstamped = int(df["us_rate_pressure"].isna().sum()) if "us_rate_pressure" in df.columns else 0
    if n_backfilled:
        log.info("china_standout_track: regime-backfilled %d rows; %d still unstamped",
                 n_backfilled, n_unstamped)

    # Write spine + regime updates back (keep-FRESH)
    if spine_updates or n_backfilled > 0:
        try:
            df = _coerce_object_cols(df)
            df.to_parquet(p, index=False)
        except Exception as e:  # noqa: BLE001
            log.warning("china_standout_track: grade write-back failed: %s", e)

    bench = _bench_close()
    out = {"available": True, "n_rows": int(len(df)),
           "n_unstamped": n_unstamped,
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D),
           "grading": {
               "benchmark": _BENCH, "relative": True, "entry_basis": ENTRY_BASIS,
               "excludes_locked_limit": True, "flags_pinned": True,
               "anchor": "board_close_then_t1_fill", "marker_dates": "forbidden",
               "bench_available": bench is not None,
               "spine_fill_basis": ENTRY_BASIS,  # provenance: CN-native, not grading.fill_index
           },
           "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        n_pinned = 0
        for _i, row in df.iterrows():
            ex, pinned = _fwd_excess(row["ticker"], pd.Timestamp(row["date"]), h, bench)
            if pinned:
                n_pinned += 1
            if ex is None:
                continue
            # W0.2a — carry tier + flag columns into the grade record for stratification.
            # Old rows pre-W0.2a have NaN for the new fields; _slice_table groups NaN → "None".
            recs.append({
                "date": row["date"], "rank": row.get("board_rank"),
                "extended": bool(row.get("extended")), "fwd": ex,
                # tier_cascade (T1/T2/T3/T4) — the primary stratification dimension.
                "tier": row.get("tier"),
                # washout_2w: prefer the explicit-name field (W0.2a schema); fall back to
                # the legacy "washout" column so old ledger rows are still stratified.
                "washout_2w": (
                    row.get("washout_2w")
                    if row.get("washout_2w") is not None
                    else row.get("washout")
                ),
                # coiled: COILED cohort-washout flag (wave-3).
                "coiled": row.get("coiled"),
                # hold_state: W6-C basing state (None until W0.1 HOLD port populates it).
                "hold_state": row.get("hold_state"),
                # entry_status: confluence-gated entry gate label.
                "entry_status": row.get("entry_status"),
                # sector_turn: W0.10 sector first-tick-up state ("bottoming" or None).
                # Old rows pre-W0.10 will show NaN here (grouped as "None" in _slice_table).
                "sector_turn": row.get("sector_turn"),
                # W0 Stage B-d: species_id and archetype — nullable stratifier columns.
                # Always null for this ledger (documented in _SPECIES_NOTE): multiple species
                # bind it and rows don't disambiguate which fired.
                "species_id": row.get("species_id"),
                "archetype": row.get("archetype"),
            })
        if len(recs) < _MIN_GRADED:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        # board rank-IC per date (rank vs forward excess; NEGATIVE = a well-ordered board)
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["rank"].nunique() >= 5:
                ics.append(float(sub["rank"].rank().corr(sub["fwd"].rank())))
        # top-decile (by best rank) vs the rest
        g = g.sort_values("rank")
        k = max(1, int(round(len(g) * _TOP_DECILE)))
        top_fwd = float(g.head(k)["fwd"].mean())
        rest_fwd = float(g.tail(len(g) - k)["fwd"].mean()) if len(g) > k else None
        ext = g[g["extended"]]
        non = g[~g["extended"]]
        hit = float((g["fwd"] > 0).mean())                # share beating CSI300
        lo, hi = _wilson_ci(int((g["fwd"] > 0).sum()), int(len(g)))
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "hit_vs_csi300": round(hit, 4),
            "hit_ci": [round(lo, 4), round(hi, 4)],
            "median_excess": round(float(g["fwd"].median()), 4),
            "top_decile_fwd": round(top_fwd, 4),
            "rest_fwd": round(rest_fwd, 4) if rest_fwd is not None else None,
            "board_rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "extended_fwd": round(float(ext["fwd"].mean()), 4) if len(ext) >= 5 else None,
            "not_extended_fwd": round(float(non["fwd"].mean()), 4) if len(non) >= 5 else None,
            "n_extended": int(len(ext)),
            "n_pinned": int(n_pinned),
            # W0.2a — tier+stage-stratified forward grading (F3 discipline; calibrates from ledger,
            # never by fiat). Mirrors grade_us_board._slice_table idiom. "None" = column absent in
            # pre-W0.2a rows (old ledger rows pre-schema will appear here until the ledger matures).
            "by_tier":         _slice_table(g, "tier"),
            "by_washout_2w":   _slice_table(g, "washout_2w"),
            "by_coiled":       _slice_table(g, "coiled"),
            "by_hold_state":   _slice_table(g, "hold_state"),
            "by_entry_status": _slice_table(g, "entry_status"),
            # W0.10 — sector first-tick-up stratification (display/ledger only; bonus/rank
            # change ONLY after ledger matures per F3 discipline). "bottoming" vs None.
            "by_sector_turn":  _slice_table(g, "sector_turn"),
            # W0 Stage B-d — species/archetype stratification (nullable; always null for now
            # since rows don't disambiguate which species fired — documented constraint).
            "by_species_id":   _slice_table(g, "species_id"),
            "by_archetype":    _slice_table(g, "archetype"),
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out


def _interim_excess(
    ticker: str, d0: pd.Timestamp, bench: pd.Series | None
) -> tuple[float | None, bool, int | None]:
    """UNREALIZED, open-ended cousin of ``_fwd_excess``: mark the T+1 fill to the LATEST close
    (not a fixed +h horizon), CSI300-relative. Returns (excess_or_None, pinned, sessions_held).

    None when the name doesn't resolve, T+1 is locked-limit, or no forward bar exists yet (a name
    that surfaced today has nothing to mark). Same fill/anchor discipline as the forward grade —
    never marker-dated — it is simply measured to ``iloc[-1]`` instead of ``iloc[h]``."""
    df = _price_frame(ticker)
    if df is None:
        return None, False, None
    fill, locked, pinned = _t1_fill(df, d0)
    if fill is None or locked:                            # unfillable → exclude, don't fabricate
        return None, pinned, None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    fwd = close[close.index > d0]                         # sessions after the board date
    if len(fwd) < 1:                                      # surfaced with no forward bar yet
        return None, pinned, None
    if bench is None:                                     # degrade to absolute if the ETF is missing
        return float(fwd.iloc[-1] / fill - 1.0), pinned, int(len(fwd))
    bslice = bench[bench.index > d0]
    if len(bslice) < 1:
        return None, pinned, None
    # Align the mark to a COMMON end date so a name with a staler price store isn't compared over a
    # longer CSI300 window (window mismatch would bias the excess). Mark both to the last session
    # present in BOTH series at or before their shared latest bar.
    common_last = min(fwd.index[-1], bslice.index[-1])
    fwd_c = fwd[fwd.index <= common_last]
    bsl_c = bslice[bslice.index <= common_last]
    if len(fwd_c) < 1 or len(bsl_c) < 1:
        return None, pinned, None
    name_ret = float(fwd_c.iloc[-1] / fill - 1.0)         # buy at T+1 fill, mark to common latest close
    bench_ret = float(bsl_c.iloc[-1] / bsl_c.iloc[0] - 1.0)
    days = int(len(fwd_c))                                # aligned forward sessions held so far
    return name_ret - bench_ret, pinned, days            # CSI300-relative, unrealized


def interim_grade() -> dict:
    """INTERIM (unrealized) mark-to-latest-close read over every logged pick, CSI300-relative.

    The forward ledger (``grade``) only reports at the pre-registered 21d/63d horizons, so the panel
    is a black box until the first maturities land (~21 sessions after the ledger's first date). This
    gives an honest early read in the meantime: each pick's return since its T+1 fill, marked to the
    latest close, minus CSI300 over the same window. It is explicitly UNREALISED and NOT the matured
    grade — the template must label it so, and it graduates to ``grade`` once 21d picks mature.
    Display-only telemetry; reads the ledger, never advances it."""
    store_path = _store_path()
    if not store_path.exists():
        return {"available": False}
    try:
        df = pd.read_parquet(store_path)
    except Exception as e:  # noqa: BLE001 — telemetry, never fatal
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}
    bench = _bench_close()
    exc: list[float] = []
    held: list[int] = []
    n_pinned = 0
    for _i, row in df.iterrows():
        ex, pinned, days = _interim_excess(row["ticker"], pd.Timestamp(row["date"]), bench)
        if pinned:
            n_pinned += 1
        if ex is None or days is None:
            continue
        exc.append(ex)
        held.append(days)
    n = len(exc)
    if n < _MIN_GRADED:
        return {"available": True, "n": n, "note": "accruing"}
    arr = pd.Series(exc, dtype=float)
    lo, hi = _wilson_ci(int((arr > 0).sum()), n)
    return {
        "available": True,
        "n": n,
        "unrealized": True,
        "hit_vs_csi300": round(float((arr > 0).mean()), 4),
        "hit_ci": [round(lo, 4), round(hi, 4)],
        "median_excess": round(float(arr.median()), 4),
        "mean_excess": round(float(arr.mean()), 4),
        "median_days_held": int(pd.Series(held, dtype=float).median()),
        "max_days_held": int(max(held)),
        "n_pinned": n_pinned,
        "bench_available": bench is not None,
    }


def _slice_table(df: pd.DataFrame, by: str, col: str = "fwd") -> dict:
    """Stratify a grade DataFrame by one column, returning per-stratum hit-stats.

    Mirrors grade_us_board._slice_table (same idiom, same output schema). NaN values are
    grouped under the key "None" so the JSON is always valid. Only strata with at least one
    non-null `col` row are included — thin strata report their honest n.

    Args:
        df:  per-row grade DataFrame (output of the grade() inner loop — must have `col`).
        by:  column name to stratify on (e.g. "tier", "washout_2w", "coiled").
        col: excess column to compute hit-stats on (default "fwd" — CSI300-relative excess).
    Returns:
        dict keyed by stratum value (str); each value has {n, hit_rate, wilson_lo, wilson_hi,
        median_excess, mean_excess} — honest small-sample stats with Wilson CI.
    """
    import math
    out: dict = {}
    for val, g in df.groupby(by, dropna=False):
        key = "None" if (val is None or (isinstance(val, float) and math.isnan(val))) else str(val)
        vals = g[col].dropna()
        n = len(vals)
        if n == 0:
            continue
        k = int((vals > 0).sum())
        lo, hi = _wilson_ci(k, n)
        out[key] = {
            "n": n,
            "hit_rate": round(k / n, 4),
            "wilson_lo": round(lo, 4),
            "wilson_hi": round(hi, 4),
            "median_excess": round(float(vals.median()), 5),
            "mean_excess": round(float(vals.mean()), 5),
        }
    return out


def _ripening_path():
    return config.data_dir() / _STORE / "ripening.parquet"


def append_ripening(rows: list[dict], asof: str | None = None,
                    lane: str | None = None) -> int:
    """Append today's RIPENING names as a compact log (conversion grading in W6 needs this
    history). Separate parquet from the main board so consumers of buy are unaffected.

    Row schema: date, ticker, reasons (comma-joined str), imminence (macd_bars_to_cross or None),
    w2_stoch, setup_live. Keep-FIRST per (date, ticker). Same asia-lane gate as append_board.
    Best-effort — never raises.

    W8-R1 schema additions (schema-union tolerant — old rows without these cols = NaN):
      zone          : str FALLING | READY | BASING
      evidence      : pipe-joined evidence chips
      ret_5d        : float — 5-session return (decimal)
      macd_hist_d   : float — daily MACD histogram last bar
      macd_hist_slope: int  — +1/0/-1 slope direction
      w1_cross_bars_since : int — 1W cross bars since
    """
    if not rows or not asof:
        return 0
    if lane is not None and lane != "asia":
        return 0
    out = []
    for r in rows:
        tk = r.get("ticker")
        if not tk:
            continue
        reasons = r.get("reasons") or []
        evidence = r.get("evidence") or []
        out.append({
            "date": str(asof),
            "ticker": str(tk),
            "reasons": ", ".join(reasons) if reasons else "",
            "imminence": r.get("imminence"),
            "w2_stoch": r.get("w2_stoch"),
            "setup_live": True,
            # W8-R1 zone columns (schema-union safe; old rows missing these cols = NaN).
            "zone":               r.get("zone"),
            "evidence":           " | ".join(evidence) if evidence else None,
            "ret_5d":             r.get("ret_5d"),
            "macd_hist_d":        r.get("macd_hist_d"),
            "macd_hist_slope":    r.get("macd_hist_slope"),
            "w1_cross_bars_since": r.get("w1_cross_bars_since"),
            # W2-B narrative columns (schema-union safe; old rows missing these cols = NaN).
            # Mirrors the board ledger schema so W6 can stratify RIPENING by narrative heat.
            "narr_theme":   (r.get("narrative") or {}).get("theme"),
            "narr_level":   (r.get("narrative") or {}).get("level"),
            "narr_rel20":   (r.get("narrative") or {}).get("rel20"),
            "narr_breadth": (r.get("narrative") or {}).get("breadth"),
            "ab_tier":      r.get("ab_tier"),
        })
    if not out:
        return 0
    try:
        new = pd.DataFrame(out)
        p = _ripening_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china standout ripening-track append failed: %s", e)
        return 0


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a hit rate k/n (n>0). Honest small-sample bounds."""
    if n <= 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
