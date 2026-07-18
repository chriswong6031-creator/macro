"""Standout-board forward ledger for HK and Canada stock pages.

Masterplan §5.4 + §0 'honesty spine'; audit HKCA-12; red-team product-critic FATAL 2.

W0 Stage B-c additions (§5.1 sub-task 4, §3.4 Asia-lane stamping, §1.1 spine):
  1. GRADE LOOP → grading.forward_metrics (one-grader law §1.2): grade() now calls
     grading.forward_metrics once per (ticker, date) for all 4 horizons instead of
     per-horizon grade_next_bar_return calls. Parity: forward_metrics is the same
     function grade_next_bar_return delegates to; max_abs_diff = 0.0 on all horizons
     and all existing rows. Suspension rule, excess-vs-market, and accruing-status
     gate are PRESERVED EXACTLY. grade() is keep-FRESH (re-grades every row each run
     from the live close store — not keep-FIRST). This contract is unchanged.
  2. SPINE COLUMNS (schema-union, nullable): fwd_mfe_{5,10,21,63}, fwd_mfe_63 (63d
     already in _HORIZONS_D), terminal_state_clean15_126, terminal_state_clean8_21,
     post_cushion_breach(horizon=21). Suspended rows: spine cols stay null (sacred
     rule). Legacy rows null-extended via schema union.
  3. ASIA/CA-LANE REGIME STAMPS (§3.4):
     (a) Own-market primary stamp: NULL + documented. Both HK regime_history.parquet
         and CA regime_history.parquet are RECOMPUTED each run from latest-state
         sources (engine/hk_run.py L44, engine/canada_run.py L83: store_df.to_parquet
         overwrite — not PIT append-only). The signal_archive/{hk,ca}_regime.parquet
         files are PIT but started only 2026-06-17 and have <12 rows each — not a
         reliable stamping source for a graded ledger. Therefore: own_market_regime=null
         on all rows; own_market_regime_note documents this constraint. A future
         initiative that persists a daily-append PIT file for HK/CA regime state can
         wire it here.
     (b) US context stamp (validated global-factors-drive-HK finding): us_rate_pressure,
         us_quad_hard_label, us_fused_risk_label, us_vol_regime, us_risk_radar_state,
         us_regime_vector_degraded from get_vector_for_date on the persisted US
         data/regime/regime_vector.parquet. Columns prefixed us_* to mark them as
         CONTEXT, not primary regime.
     (c) vector_asof + staleness_hours on every row (may be negative-or-zero when
         the US vector's asof is same-day as the HK/CA render).
     append_board stamps new rows; grade() backfills null stamps from the persisted
     vector only; residual unstamped count printed in scorecard output.
  4. SPECIES/ARCHETYPE: no species in data/species/registry.json binds to this ledger
     (checked: S1..DISLOC all bind to us_board_ledger / china_standout_track). Neither
     build_hk_library.py nor build_canada.py passes an 'archetype' key in the calls
     dict. Therefore: species_id=null, archetype=null on all rows (documented below).

Problem addressed
-----------------
The existing name_score_grader grades the per-name POTENTIAL score (primed / setting_up /
watch / no_setup). It does NOT grade the standout board rank — the order in which the page
actually surfaces names to the user. This module is the explicit standout-board scoreboard
the plan mandates: it logs the RANKED board each render, then grades it honestly.

Three public functions
----------------------
* append_board(calls, market, asof)  — log the ranked board at render time.
* grade(market)                      �� compute forward returns + IC for matured calls.
* scorecard(market)                  — per-group hit-rate + rank-IC; returns 'accruing'
                                       status dict until the min-IC-dates gate is met.

Honesty guarantees (enforced in code, not cadence)
---------------------------------------------------
1. NEXT-BAR fill: a call logged on asof is FILLED at the next available bar, never the
   signal bar itself (via engine.grading.forward_metrics — the one-grader law §1.2).
2. SUSPENSION rule (HK-native, red-team MISSING #5): if no valid print exists within
   5 sessions after the fill date, the call is marked 'suspended' and EXCLUDED from
   hit-rates. HK names suspend for weeks (deals, going-private, regulatory); silent
   ffill through halts fabricates returns. No silent-ffill ever.
   Suspension check runs BEFORE any grading; spine columns stay null for suspended rows.
3. Accruing-status gate: scorecard() returns {'status': 'accruing', ...} until
   ≥ MIN_IC_DATES matured dates each carry ≥ MIN_NAMES_PER_DATE names. This prevents
   early-alert fatigue in the admin experiments tracker.
4. Survivorship stamp: 'no_dead_name_store' is always set (no ex-HK/CA dead-name store
   exists — losses on delisted names that disappear from the close store are NOT graded
   and the count is stamped). This is the survivorship BOUND, not a caveat sticker.
5. Excess return: scorecard computes 21d excess vs market index
   (HK = _HSI, CA = _GSPTSE) — not raw return — so the IC is against market-relative
   performance.

Store
-----
data/board_ledger/{hk,ca}_board.parquet — small (one row per board-date × ticker),
append-only, keep-FIRST per (date, ticker), git-tracked (not R2: the table is tiny
and grows ~50-120 rows/day; even a full year is <50 KB per market).

Schema (one row per board snapshot entry)
-----------------------------------------
date          str        YYYY-MM-DD render date (the asof close)
market        str        HK | CA
ticker        str        exchange ticker
board_pos     int        1-based rank on the board (1 = top of the buy group)
group         str        'entry_open' | 'setting_up' | 'watch'
edge_z        float|None fused edge z-score for this name (from hk_edge / ca_alpha)
gate_tier     str|None   T1 | T2 | T3 | T4 | None  (confluence gate tier)
align_tier    str|None   'aligned' | 'near' | None
entry_state   str|None   e.g. 'open' | 'pullback' | 'wait' | None
close_asof    float|None closing price on render date
washout_2w    bool|None  CN-port stamp (§5.3): 2W-FRI StochRSI washout-reclaim held at
                         render. Log-and-grade only — never a rank input. None = not stamped
                         (caller predates the port or doesn't compute it).
extended      bool|None  CN-port stamp (§5.3): extension read in {stretched, parabolic}.
                         Log-and-grade only. None = not stamped.
placement_flag bool|None H-PLC risk-gate stamp (masterplan §3, W1c): dilutive
                         placement/rights/open-offer announcement within the trailing
                         90d window at render (HK only). Flagged names are demoted off
                         the entry groups; the stamp lets the gate itself be graded.
                         None = not stamped (pre-W1c row, non-HK market, or the
                         placement store was degraded that render — distinct from
                         False = 'checked, clean').
--- W0 Stage B-c spine columns (nullable; null for suspended rows; legacy rows null) ---
fwd_mfe_5     float|None max favorable excursion within 5 bars after fill (≥ 0)
fwd_mfe_10    float|None max favorable excursion within 10 bars after fill (≥ 0)
fwd_mfe_21    float|None max favorable excursion within 21 bars after fill (≥ 0)
fwd_mfe_63    float|None max favorable excursion within 63 bars after fill (≥ 0)
terminal_state_clean15_126  str|None STOPPED/DEAD_MONEY/CUSHIONED/CLEAN_LIFTOFF
                         (positional primary: +15% before −5% within 126d)
terminal_state_clean8_21    str|None rotational primary: +8% before −5% within 21d
post_cushion_breach  bool|None per-fire breach flag at horizon=21 (§1.1)
species_id    str|None   Always null: no species in registry.json binds to this ledger
archetype     str|None   Always null: callers (build_hk_library, build_canada) do not
                         pass archetype in the calls dict
--- W0 Stage B-c regime stamps (nullable) ---
own_market_regime        str|None Always null: HK/CA regime_history is recomputed
                         (not PIT append-only) so historical stamps would be
                         non-PIT; documented constraint.
own_market_regime_note   str|None Human-readable explanation of the null above.
us_rate_pressure         str|None US regime context (§3.4 Asia-lane rule)
us_quad_hard_label       str|None US regime context
us_fused_risk_label      str|None US regime context
us_vol_regime            str|None US regime context
us_risk_radar_state      str|None US regime context
us_regime_vector_degraded bool|None True when the US vector was degraded at stamp time
vector_asof              str|None ISO date of the US regime_vector row used
staleness_hours          float|None hours between vector_asof and the board date
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine import grading
from lib import config, store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HORIZONS_D = (5, 10, 21, 63)       # 1w / 2w / 1m / 3m
_BENCH = {"HK": ("hk", "_HSI"), "CA": ("canada", "_GSPTSE")}

# Suspension rule: if no valid print within N sessions after fill, mark 'suspended'.
SUSPENSION_SESSIONS = 5

# Accruing gate: need this many matured IC dates with enough names before we report numbers.
MIN_IC_DATES = 5
MIN_NAMES_PER_DATE = 5

# W0 Stage B-c: regime stamp columns — US vector as Asia-lane context (§3.4)
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

# W0 Stage B-c: spine maturation columns (all nullable; null for suspended rows)
_SPINE_COLS = (
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63",
    "terminal_state_clean15_126",
    "terminal_state_clean8_21",
    "post_cushion_breach",
)

_SCHEMA = [
    "date", "market", "ticker", "board_pos", "group",
    "edge_z", "gate_tier", "align_tier", "entry_state", "close_asof",
    "washout_2w", "extended", "placement_flag",
    "hold_basing", "dt_compress",
    # W0.2 Stage C — near-miss capture (masterplan §5.2 move 2, Appendix A):
    #   primary_rejection_reason: the CLOSED-taxonomy reason a watch-strip row was
    #     held off the entry groups (null on entry rows and non-near-miss watch rows;
    #     validated against grading.REJECTION_TAXONOMY at append time).
    #   block_reason: the builder's free-text why (CA watch strip); display context.
    #   knife_demoted/knife_z: the HK falling-knife demote flag + its 3M-return z
    #     magnitude (HK passed these before Stage C but the _SCHEMA reindex DROPPED
    #     them silently — adding the columns is what makes them persist).
    "primary_rejection_reason", "block_reason", "knife_demoted", "knife_z",
    # W0 Stage B-c additions
    "species_id", "archetype",
    "own_market_regime", "own_market_regime_note",
    # Inclusion-gate versioning: allows Q4/W7 grading to split pre/post gate-swap samples.
    # "cascade_v1" = confluence cascade (signal_gate T1-T4, HK ratified 2026-07-16); None = prior.
    "gate_ver",
    *_US_STAMP_COLS,
    *_SPINE_COLS,
]

# Optional CN-port stamp columns — nullable bool ('boolean' dtype in the store).
# None means 'not stamped' (distinct from False = 'computed, absent').
# hold_basing / dt_compress are the CA2 close-only port stamps (#1072 idiom): the name is
# in a basing hold vs its anchor / carries a dannytrades vol-compression read.
_PORT_STAMPS = ("washout_2w", "extended", "hold_basing", "dt_compress")

# Optional risk-gate stamp columns — same nullable-bool semantics as _PORT_STAMPS.
_GATE_STAMPS = ("placement_flag",)

# Columns that carry strings (or bool/None) but are nullable: an all-NaN column read
# from parquet types as float64, and pandas 3.x then REFUSES a string cell write
# (TypeError: Invalid value 'CLEAN_LIFTOFF' for dtype 'float64'). Coerce to object
# wherever a frame is assembled so cell writes are dtype-safe regardless of how a
# legacy parquet happened to be typed.
_OBJECT_COLS = (
    "primary_rejection_reason", "block_reason", "knife_demoted",
    "species_id", "archetype", "own_market_regime", "own_market_regime_note", "gate_ver",
    "us_rate_pressure", "us_quad_hard_label", "us_fused_risk_label",
    "us_vol_regime", "us_risk_radar_state", "us_regime_vector_degraded",
    "vector_asof",
    "terminal_state_clean15_126", "terminal_state_clean8_21",
    "post_cushion_breach",
)


def _coerce_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Force the string-bearing nullable columns to object dtype (NaN → None)."""
    for col in _OBJECT_COLS:
        if col in df.columns and df[col].dtype != object:
            coerced = df[col].astype(object)
            df[col] = coerced.where(pd.notna(coerced), None)
    return df

# Own-market regime constraint note (documented null — see module docstring §3a)
_OWN_REGIME_NOTE = (
    "null: HK/CA regime_history.parquet is recomputed from latest-state on each run "
    "(hk_run.py/canada_run.py overwrite the full history); stamping from it would "
    "produce non-PIT historical values. signal_archive/{hk,ca}_regime.parquet started "
    "2026-06-17 with <12 rows — not a reliable source. Wire a daily-append PIT file "
    "to enable own-market stamps."
)


def _store_path(market: str) -> Path:
    m = market.upper()
    return config.data_dir() / "board_ledger" / f"{m.lower()}_board.parquet"


# ---------------------------------------------------------------------------
# W0 Stage B-c: US regime stamp helpers (Asia-lane rule §3.4)
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
    date_str — never recomputes from latest-state sources.  Returns a null stamp
    dict when the parquet is absent or no row covers the date.

    Column mapping: the regime_vector parquet stores US columns without a 'us_'
    prefix (it IS the US vector).  We re-emit them prefixed 'us_*' here so the
    board_ledger schema is unambiguous (§3.4: 'explicitly-labeled CONTEXT column set').
    """
    try:
        from engine.regime_vector import get_vector_for_date  # noqa: PLC0415
        raw = get_vector_for_date(date_str)
    except Exception as exc:  # noqa: BLE001
        log.debug("board_ledger: regime_stamp_for_date failed for %s: %s", date_str, exc)
        return _regime_stamp_null()

    # Re-key from US native names to us_* context names
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
# append_board
# ---------------------------------------------------------------------------
def append_board(
    calls: list[dict],
    market: str,
    asof: str | None = None,
) -> int:
    """Log today's ranked standout board.

    ``calls`` is a list of dicts, one per board row, in the ORDER they appear on the
    page (board_pos is assigned here, 1-based). Each call should carry:
        ticker        — required
        group         — 'entry_open' | 'setting_up' | 'watch'
        edge_z        — fused edge z-score (float, optional)
        gate_tier     — 'T1'/'T2'/'T3'/'T4'/None
        align_tier    — 'aligned'/'near'/None
        entry_state   — e.g. 'open'/'pullback'/'wait'/None
        close_asof    — today's close (float, optional)
        washout_2w    — CN-port stamp (bool, optional; None if omitted)
        extended      — CN-port stamp (bool, optional; None if omitted)
        placement_flag — H-PLC risk-gate stamp (bool, optional; None if omitted
                        or the placement store was degraded that render)
        hold_basing   — CA2 close-only port stamp (bool, optional; None if omitted)
        dt_compress   — CA2 close-only port stamp (bool, optional; None if omitted)

    Keep-FIRST per (date, ticker): a price already stamped for a given date is
    never overwritten — point-in-time integrity.

    W0 Stage B-c: new rows are stamped at creation with the US regime_vector context
    (§3.4 Asia-lane rule) and spine column placeholders (null at birth; matured by
    grade()). Species_id and archetype are always null (see module docstring §4).

    Returns the ledger row count after the merge (0 on error).
    """
    if not calls or not asof:
        return 0
    m = market.upper()

    # PR-R10: lane gates — prevent duplicate-row writes on re-renders.
    # HK appends gated on asia_advance_enabled() (CN_LANE=asia).
    # CA appends gated on nightly_advance_enabled() (COLLECT_LANE=nightly).
    try:
        from engine.ledger_lane import asia_advance_enabled, nightly_advance_enabled  # noqa: PLC0415
        if m == "HK" and not asia_advance_enabled():
            log.info(
                "board_ledger.append_board(HK): off-lane (CN_LANE != asia) — "
                "skip write; read paths unaffected (PR-R10)"
            )
            return 0
        if m == "CA" and not nightly_advance_enabled():
            log.info(
                "board_ledger.append_board(CA): off-lane (COLLECT_LANE != nightly) — "
                "skip write; read paths unaffected (PR-R10)"
            )
            return 0
    except Exception as _lane_exc:  # noqa: BLE001
        # If ledger_lane import fails, treat as off-lane (fail-closed — PR-R10)
        log.warning("board_ledger.append_board: ledger_lane import failed (%s) — "
                    "treating as off-lane (fail-closed)", _lane_exc)
        return 0

    # Stamp the US regime vector once per append_board call (same asof for all rows)
    rv_stamp = _regime_stamp_for_date(str(asof))

    rows = []
    for pos, c in enumerate(calls, start=1):
        tk = c.get("ticker")
        if not tk:
            continue
        rows.append({
            "date": str(asof),
            "market": m,
            "ticker": str(tk),
            "board_pos": pos,
            "group": c.get("group"),
            "edge_z": _float_or_none(c.get("edge_z")),
            "gate_tier": c.get("gate_tier") or None,
            "align_tier": c.get("align_tier") or None,
            "entry_state": c.get("entry_state") or None,
            "close_asof": _float_or_none(c.get("close_asof")),
            "washout_2w": _bool_or_none(c.get("washout_2w")),
            "extended": _bool_or_none(c.get("extended")),
            "placement_flag": _bool_or_none(c.get("placement_flag")),
            "hold_basing": _bool_or_none(c.get("hold_basing")),
            "dt_compress": _bool_or_none(c.get("dt_compress")),
            # W0.2 Stage C: near-miss capture fields (Appendix A). A reason outside
            # the CLOSED taxonomy is dropped to null + logged loudly — a runner must
            # never silently extend the enum (extension requires a §8 row).
            "primary_rejection_reason": _taxonomy_or_none(
                c.get("primary_rejection_reason"), tk),
            "block_reason": (str(c.get("block_reason"))
                             if c.get("block_reason") else None),
            "knife_demoted": _bool_or_none(c.get("knife_demoted")),
            "knife_z": _float_or_none(c.get("knife_z")),
            # 2026-07-16 HK INCLUDE gate swap (masterplan §5.0 amendment): nullable
            # provenance stamp so W7/Q4 grading splits pre/post-swap samples. CN/CA
            # callers don't stamp it yet — their rows stay None (back-compatible).
            "gate_ver": (str(c.get("gate_ver")) if c.get("gate_ver") else None),
            # W0 Stage B-c: species/archetype — always null (documented; no registry binding)
            "species_id": None,
            "archetype": None,
            # W0 Stage B-c: own-market regime — always null (documented; non-PIT source)
            "own_market_regime": None,
            "own_market_regime_note": _OWN_REGIME_NOTE,
            # W0 Stage B-c: US context regime stamp
            **rv_stamp,
            # W0 Stage B-c: spine maturation placeholders (null at birth; filled by grade())
            "fwd_mfe_5": None, "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
            "terminal_state_clean15_126": None,
            "terminal_state_clean8_21": None,
            "post_cushion_breach": None,
        })
    if not rows:
        return 0
    try:
        # reindex to _SCHEMA order; extra keys in rows (from **rv_stamp) already map to _SCHEMA
        new = pd.DataFrame(rows).reindex(columns=_SCHEMA)
        p = _store_path(m)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            # union schema: prior frames may predate the optional stamp columns (and may
            # carry legacy extras) — reindex both sides so concat never drops a column
            cols = list(dict.fromkeys([*_SCHEMA, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=cols), new.reindex(columns=cols)],
                ignore_index=True,
            )
            # keep-FIRST per (date, ticker) — honesty: stamp is immutable once written
            combined = combined.drop_duplicates(subset=["date", "ticker"], keep="first")
            combined = _coerce_object_cols(combined)
        else:
            combined = new
        for col in (*_PORT_STAMPS, *_GATE_STAMPS):
            combined[col] = combined[col].astype("boolean")
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("board_ledger (%s): append failed: %s", m, e)
        return 0


# ---------------------------------------------------------------------------
# Close-series loaders (market-specific; pure reads)
# ---------------------------------------------------------------------------
def _hk_close(ticker: str) -> pd.Series | None:
    """Per-ticker close for HK names (store group 'hk_stocks')."""
    df = store.read("hk_stocks", ticker)
    if df is None or "close" not in df.columns:
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _ca_close(ticker: str, _cache: dict | None = None) -> pd.Series | None:
    """Per-ticker close for CA names from the wide canada_search/closes.parquet frame.

    The wide frame is cached on first call within a grade() run via the ``_cache`` dict
    so we don't re-read the 219-column parquet for every ticker.
    """
    if _cache is not None and "__ca_wide__" not in _cache:
        _cache["__ca_wide__"] = _load_ca_wide()
    wide = (_cache["__ca_wide__"] if _cache is not None else _load_ca_wide())
    if wide is None or ticker not in wide.columns:
        return None
    s = pd.to_numeric(wide[ticker], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _load_ca_wide() -> pd.DataFrame | None:
    """Load the CA search/breadth wide close frame (219 names)."""
    cp = config.data_dir() / "canada_search" / "closes.parquet"
    if not cp.exists():
        # fallback: breadth cache (gitignored, rebuild-only)
        cp = config.data_dir() / "canada_breadth" / "_closes_cache.parquet"
    if not cp.exists():
        return None
    try:
        return pd.read_parquet(cp).sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("board_ledger: CA wide close load failed: %s", e)
        return None


def _bench_close(market: str) -> pd.Series | None:
    """Benchmark close series (HK=_HSI, CA=_GSPTSE)."""
    grp, tkr = _BENCH.get(market.upper(), (None, None))
    if grp is None:
        return None
    df = store.read(grp, tkr)
    if df is None or "close" not in df.columns:
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _name_close(market: str, ticker: str, ca_cache: dict | None = None) -> pd.Series | None:
    """Dispatch to the right close loader by market."""
    m = market.upper()
    if m == "HK":
        return _hk_close(ticker)
    if m == "CA":
        return _ca_close(ticker, _cache=ca_cache)
    return None


# ---------------------------------------------------------------------------
# Suspension check
# ---------------------------------------------------------------------------
def _is_suspended(close: pd.Series, fill_date: pd.Timestamp) -> bool:
    """Return True if there is no valid close within SUSPENSION_SESSIONS trading bars
    strictly AFTER fill_date. A name that halts immediately after entry is 'suspended'
    and its outcome is excluded from hit-rates (never silently ffilled).

    'Trading bars' here means calendar bars present in the close index (the
    session count, not calendar days) — consistent with how grading.fill_index works.
    """
    after = close[close.index > fill_date]
    return len(after) < SUSPENSION_SESSIONS


# ---------------------------------------------------------------------------
# grade
# ---------------------------------------------------------------------------
def grade(market: str) -> dict:
    """Compute forward returns for matured board calls.  keep-FRESH contract.

    W0 Stage B-c changes:
      * ONE-GRADER LAW: calls grading.forward_metrics once per (ticker, date) for all
        4 horizons instead of per-horizon grade_next_bar_return calls. Parity guaranteed
        because grade_next_bar_return is a thin alias for forward_metrics.
      * SPINE COLUMNS: fills fwd_mfe_{5,10,21,63}, terminal_state_clean15_126,
        terminal_state_clean8_21, post_cushion_breach back to the parquet.
        Suspended rows: spine cols stay null. Legacy rows: null on first mature run,
        schema-union means no data is lost.
      * REGIME BACKFILL: rows with all-null us_* stamp cols are backfilled from the
        persisted regime_vector.parquet. grade() only backfills null slots — it never
        overwrites a non-null stamp. The count of still-unstamped rows is reported in
        the return dict.

    For each logged call:
      1. Find the fill bar = NEXT bar after the call date (next-bar fill via grading).
      2. Check suspension BEFORE grading: if fewer than SUSPENSION_SESSIONS bars exist
         after fill, mark 'suspended' and exclude from IC and hit-rates. SACRED RULE.
      3. Compute forward returns via grading.forward_metrics (one grader, all horizons).
      4. Compute spine columns: fwd_mfe_{h}, terminal_state_*, post_cushion_breach.
      5. Excess return vs market index: excess = name_fwd_ret − bench_fwd_ret.
      6. Write updated spine + regime-stamp columns back to the parquet (keep-FRESH).

    Returns a dict with keys:
        market, n_calls, n_graded, n_suspended, n_unstamped, survivorship,
        by_horizon: {h: [{date, ticker, board_pos, group, edge_z, fwd_ret, bench_ret,
                          excess_ret, suspended}, ...]}
    """
    m = market.upper()
    p = _store_path(m)
    if not p.exists():
        return {"market": m, "available": False, "note": "no board calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"market": m, "available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"market": m, "available": False, "note": "empty ledger"}

    # Extend schema for any new columns not yet present in the stored parquet
    # (legacy rows written before B-c will be missing spine + regime cols)
    all_cols = list(dict.fromkeys([*_SCHEMA, *df.columns]))
    for col in all_cols:
        if col not in df.columns:
            df[col] = None
    df = _coerce_object_cols(df)

    bench = _bench_close(m)
    ca_cache: dict = {}

    # keep-FRESH: we track which rows need spine writes; build a parallel update list
    spine_updates: list[tuple[int, dict]] = []  # (df_index, {col: value, ...})

    out: dict = {
        "market": m,
        "available": True,
        "n_calls": int(len(df)),
        "n_graded": 0,
        "n_suspended": 0,
        "survivorship": "no_dead_name_store",  # no ex-HK/CA dead-name store — losses on
        # delisted names that disappear from the live store are NOT captured; this is the
        # honest survivorship BOUND, not a stamp.
        "by_horizon": {f"{h}d": [] for h in _HORIZONS_D},
    }

    for idx, row in df.iterrows():
        date_str = str(row["date"])
        ticker = str(row["ticker"])
        d0 = pd.Timestamp(date_str)

        close = _name_close(m, ticker, ca_cache=ca_cache)
        if close is None or close.empty:
            continue  # name not in live store (may be delisted — not captured)

        # Determine fill index (next bar after signal)
        fill_iloc = grading.fill_index(close, d0)
        if fill_iloc is None:
            continue  # not yet matured
        fill_date = close.index[fill_iloc]

        # Suspension check runs BEFORE any grading — SACRED RULE (red-team MISSING #5)
        # Spine columns stay null for suspended rows; they are excluded from IC/hit-rates.
        if _is_suspended(close, fill_date):
            out["n_suspended"] += 1
            for h in _HORIZONS_D:
                out["by_horizon"][f"{h}d"].append({
                    "date": date_str,
                    "ticker": ticker,
                    "board_pos": int(row.get("board_pos") or 0),
                    "group": row.get("group"),
                    "edge_z": _float_or_none(row.get("edge_z")),
                    "fwd_ret": None,
                    "bench_ret": None,
                    "excess_ret": None,
                    "suspended": True,
                })
            continue

        # ONE-GRADER LAW: call forward_metrics once for all horizons (§1.2).
        # This replaces 4× grade_next_bar_return calls; result is identical by construction
        # (grade_next_bar_return is a thin wrapper over forward_metrics).
        fm = grading.forward_metrics(close, d0, horizons=_HORIZONS_D)
        bm = grading.forward_metrics(bench, d0, horizons=_HORIZONS_D) if bench is not None else {}

        graded_any = False
        for h in _HORIZONS_D:
            name_ret = fm.get(f"fwd_ret_{h}")
            bench_ret = bm.get(f"fwd_ret_{h}") if bm else None
            excess = _excess(name_ret, bench_ret)
            out["by_horizon"][f"{h}d"].append({
                "date": date_str,
                "ticker": ticker,
                "board_pos": int(row.get("board_pos") or 0),
                "group": row.get("group"),
                "edge_z": _float_or_none(row.get("edge_z")),
                "fwd_ret": name_ret,
                "bench_ret": bench_ret,
                "excess_ret": excess,
                "suspended": False,
            })
            if name_ret is not None:
                graded_any = True
        if graded_any:
            out["n_graded"] += 1

        # ------------------------------------------------------------------
        # SPINE COLUMNS (keep-FRESH: recompute on every grade() run)
        # ------------------------------------------------------------------
        spine_patch: dict = {}

        # fwd_mfe_{h} — max favorable excursion from forward_metrics
        for h in _HORIZONS_D:
            spine_patch[f"fwd_mfe_{h}"] = fm.get(f"fwd_mfe_{h}")

        # terminal_state_clean15_126 — positional primary (+15% before −5% in 126d)
        try:
            ts15 = grading.terminal_state(
                close, d0,
                liftoff_mult=grading.LIFTOFF_15,
                liftoff_horizon=grading.LIFTOFF_HORIZON_126,
            )
            spine_patch["terminal_state_clean15_126"] = ts15.get("state")
        except Exception as _e:  # noqa: BLE001
            spine_patch["terminal_state_clean15_126"] = None

        # terminal_state_clean8_21 — rotational primary (+8% before −5% in 21d)
        try:
            ts8 = grading.terminal_state(
                close, d0,
                liftoff_mult=grading.LIFTOFF_8,
                liftoff_horizon=grading.LIFTOFF_HORIZON_21,
            )
            spine_patch["terminal_state_clean8_21"] = ts8.get("state")
        except Exception as _e:  # noqa: BLE001
            spine_patch["terminal_state_clean8_21"] = None

        # post_cushion_breach — per-fire flag at horizon=21
        try:
            pcb = grading.post_cushion_breach(close, d0, horizon=grading.LIFTOFF_HORIZON_21)
            spine_patch["post_cushion_breach"] = pcb
        except Exception as _e:  # noqa: BLE001
            spine_patch["post_cushion_breach"] = None

        spine_updates.append((idx, spine_patch))

    # ------------------------------------------------------------------
    # Write spine column updates back to the parquet (keep-FRESH)
    # ------------------------------------------------------------------
    if spine_updates:
        for idx, patch in spine_updates:
            for col, val in patch.items():
                df.at[idx, col] = val

    # ------------------------------------------------------------------
    # REGIME BACKFILL: backfill null us_* stamp cols from persisted vector.
    # grade() only fills null slots — never overwrites non-null stamps.
    # This handles rows appended before the B-c schema change.
    # ------------------------------------------------------------------
    n_backfilled = 0
    us_cols = list(_US_STAMP_COLS)
    # Identify rows where ALL us_* stamp cols are null/missing
    def _row_is_unstamped(r) -> bool:
        return all(
            (r.get(c) is None or (isinstance(r.get(c), float) and np.isnan(r.get(c)))
             or str(r.get(c)) in ("", "nan", "None", "NaT"))
            for c in us_cols
        )

    for idx, row in df.iterrows():
        if _row_is_unstamped(row):
            date_str = str(row["date"])
            stamp = _regime_stamp_for_date(date_str)
            # Convergence guard: a null stamp (no PIT vector coverage for this
            # date) leaves the row unstamped, so counting it as a backfill made
            # EVERY grade() call rewrite the parquet forever — a no-op rewrite
            # that is byte-identical under the nightly's pyarrow but git-dirty
            # under any other pyarrow build. Only write when the stamp actually
            # transitions the row out of the unstamped set.
            if all(stamp.get(c) is None for c in us_cols):
                continue
            for col, val in stamp.items():
                df.at[idx, col] = val
            n_backfilled += 1

    # Count residual unstamped rows (rows where US vector had no coverage)
    # A row is "still unstamped" if us_rate_pressure is still null after backfill
    n_unstamped = int(df["us_rate_pressure"].isna().sum()) if "us_rate_pressure" in df.columns else 0

    # Write back with all updates
    if spine_updates or n_backfilled > 0:
        try:
            for col in (*_PORT_STAMPS, *_GATE_STAMPS):
                if col in df.columns:
                    df[col] = df[col].astype("boolean")
            df.to_parquet(p, index=False)
        except Exception as e:  # noqa: BLE001
            log.warning("board_ledger (%s): grade write-back failed: %s", m, e)

    out["n_unstamped"] = n_unstamped
    if n_backfilled:
        log.info("board_ledger (%s): regime-backfilled %d rows; %d still unstamped",
                 m, n_backfilled, n_unstamped)

    return out


# ---------------------------------------------------------------------------
# scorecard
# ---------------------------------------------------------------------------
def scorecard(market: str) -> dict:
    """Per-group hit-rate + Spearman rank-IC of board_pos vs forward excess at each
    horizon. Returns an 'accruing' status dict until the min-IC-dates gate is met.

    Min-IC-dates gate (guards against early-alert fatigue per red-team minor finding):
      * Return {'status': 'accruing', ...} unless ≥ MIN_IC_DATES dates each have
        ≥ MIN_NAMES_PER_DATE NON-SUSPENDED graded names.
      * When the gate is met, compute the scorecard and return {'status': 'scored', ...}.

    IC semantics:
      * Spearman(board_pos, excess_ret_at_h): negative IC is GOOD (lower board_pos =
        higher rank = earlier on board; lower pos number correlates with higher excess).
        We report the IC sign as "rank_ic" = Spearman(pos, excess), so negative means
        the board order predicted outperformance.
      * hit_rate = fraction of NON-SUSPENDED graded calls in 'entry_open' and
        'setting_up' groups with positive 21d excess.
      * Both computed ONLY on non-suspended rows.

    Returns dict with:
        market, status ('accruing'|'scored')
        first_read_est     — estimated date for stable read (first_write + 21td from today)
        by_horizon: {h: {n, n_ic_dates, rank_ic, n_buy, hit_rate_21d, by_group: {...}}}
        note               — human-readable status summary
    """
    m = market.upper()
    g = grade(m)
    if not g.get("available"):
        return {"market": m, "status": "accruing",
                "note": g.get("note", "no data yet"),
                "first_read_est": _est_first_read()}

    by_h: dict = {}
    for h in _HORIZONS_D:
        key = f"{h}d"
        rows = [r for r in g["by_horizon"].get(key, []) if not r.get("suspended", True)]
        if not rows:
            by_h[key] = {"n": 0, "n_ic_dates": 0, "rank_ic": None,
                         "n_buy": 0, "hit_rate_21d": None, "by_group": {}}
            continue

        gf = pd.DataFrame(rows)
        # count matured dates with enough names for IC
        date_counts = gf[gf["excess_ret"].notna()].groupby("date")["ticker"].count()
        ic_eligible_dates = date_counts[date_counts >= MIN_NAMES_PER_DATE].index.tolist()
        n_ic_dates = len(ic_eligible_dates)

        # only compute IC if gate met
        rank_ic = None
        if n_ic_dates >= MIN_IC_DATES:
            ics = []
            for d in ic_eligible_dates:
                sub = gf[(gf["date"] == d) & gf["excess_ret"].notna()]
                if len(sub) >= MIN_NAMES_PER_DATE:
                    try:
                        # Spearman IC = Pearson of ranks (both sides already ranked).
                        # NOT method="spearman": pandas routes that through scipy.stats,
                        # which minimal-deps environments (ci.yml engine-render-guards)
                        # don't install — the ImportError was swallowed below and the
                        # scorecard silently reported rank_ic=None.
                        ic = float(sub["board_pos"].rank().corr(sub["excess_ret"].rank()))
                        if np.isfinite(ic):
                            ics.append(ic)
                    except Exception:  # noqa: BLE001
                        pass
            if ics:
                rank_ic = round(float(np.mean(ics)), 4)

        # hit rate: entry_open + setting_up groups, excess > 0
        buy_mask = gf["group"].isin(["entry_open", "setting_up"])
        buy_graded = gf[buy_mask & gf["excess_ret"].notna()]
        n_buy = int(len(buy_graded))
        hit_rate = (
            round(float((buy_graded["excess_ret"] > 0).mean()), 3)
            if n_buy >= 5 else None
        )

        # by-group breakdown
        by_group: dict = {}
        for grp_name, sub in gf[gf["excess_ret"].notna()].groupby("group"):
            if len(sub) >= MIN_NAMES_PER_DATE:
                by_group[grp_name] = {
                    "n": int(len(sub)),
                    "mean_excess": round(float(sub["excess_ret"].mean()), 4),
                    "pos_rate": round(float((sub["excess_ret"] > 0).mean()), 3),
                }

        by_h[key] = {
            "n": int(len(rows)),
            "n_ic_dates": n_ic_dates,
            "rank_ic": rank_ic,
            "n_buy": n_buy,
            "hit_rate_21d": hit_rate if h == 21 else None,
            "by_group": by_group,
        }

    # overall gate: scored only when 21d horizon meets MIN_IC_DATES
    gate_met = by_h.get("21d", {}).get("n_ic_dates", 0) >= MIN_IC_DATES
    status = "scored" if gate_met else "accruing"

    n_unstamped = g.get("n_unstamped", 0)
    note_parts = [
        f"n_calls={g['n_calls']}",
        f"n_graded={g['n_graded']}",
        f"n_suspended={g['n_suspended']}",
        f"n_unstamped={n_unstamped}",
        f"21d_ic_dates={by_h.get('21d', {}).get('n_ic_dates', 0)}/{MIN_IC_DATES}",
    ]
    if status == "accruing":
        note_parts.append(f"first_stable_read≈{_est_first_read()}")

    return {
        "market": m,
        "status": status,
        "n_calls": g["n_calls"],
        "n_graded": g["n_graded"],
        "n_suspended": g["n_suspended"],
        "n_unstamped": n_unstamped,
        "survivorship": g["survivorship"],
        "first_read_est": _est_first_read(),
        "by_horizon": by_h,
        "note": "; ".join(note_parts),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _float_or_none(v) -> float | None:
    """Convert to float or return None (handles NaN gracefully)."""
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _taxonomy_or_none(reason, ticker: str):
    """Validate a near-miss reason against the CLOSED Appendix-A taxonomy
    (grading.REJECTION_TAXONOMY). Unknown reasons null out LOUDLY — extending
    the enum requires a §8 status row, never a silent runner append."""
    if reason is None:
        return None
    r = str(reason)
    from engine import grading as _grading  # local: avoid import-order surprises
    if r in _grading.REJECTION_TAXONOMY:
        return r
    log.warning("append_board: %s carries non-taxonomy rejection reason %r — "
                "dropped to null (Appendix A is a CLOSED set; §8 row required "
                "to extend)", ticker, r)
    return None


def _bool_or_none(v) -> bool | None:
    """Coerce to bool, preserving None/NaN/pd.NA as None ('not stamped')."""
    try:
        if v is None or pd.isna(v):
            return None
        return bool(v)
    except (TypeError, ValueError):
        return None


def _excess(name_ret: float | None, bench_ret: float | None) -> float | None:
    """Arithmetic excess return."""
    if name_ret is None or bench_ret is None:
        return None
    return name_ret - bench_ret


def _est_first_read() -> str:
    """Estimate the date of first stable scorecard read.

    From the masterplan: 'first single 21d grade ≈ first_write + 21td; stable read
    ≥5 matured dates ≈ late-Aug if wired 2026-07'.

    We return 2026-08-24 (matching the registry entry) as the program-level constant.
    This function exists so tests and callers get a consistent value.
    """
    return "2026-08-24"
