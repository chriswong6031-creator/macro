"""engine/options_stamp.py — point-in-time options-state stamp for the US board ledger.

Part of the Options Alpha program (research/OPTIONS_ALPHA_MASTERPLAN.md, waves W1.3 / W-C).

Given a fire ``(as_of, ticker)`` on ``data/us_board_ledger/retro_grades.parquet`` this
module returns a nullable options-state row from the PINNED positioning stores (ruling A6):

  * ``data/polygon_gex/summary_{SYM}.parquet`` — one row per date (DatetimeIndex), supplies
    ``opt_gamma_regime`` (gamma_regime), ``opt_dist_to_flip_pct`` (dist_to_flip_pct),
    ``opt_wall_up`` (magnet_up), ``opt_wall_down`` (magnet_down), ``opt_iv30`` (iv30).
  * ``data/polygon_gex/chains/{date}.parquet`` — per-contract OI/volume, supplies
    ``opt_doi_slope_5d`` (5-day normalized near-money call-OI slope; null when < 5 prior
    chain days exist) and ``opt_voi_flag`` (today's chain volume > yesterday's OI on ≥1
    near-money contract — a fresh-positioning marker).
  * ``data/options_skew/snapshots.parquet`` — per-ticker/date (date str column, underlying
    str column, skew float), supplies ``opt_skew`` (latest-PIT skew on fire date) and
    ``opt_skew_5d_chg`` (skew change over the prior 5 calendar days of available snapshots).
  * ``data/options_ivspread/snapshots.parquet`` — per-ticker/date, supplies
    ``opt_ivspread_rel`` (latest-PIT ivspread_rel on fire date).
  * ``engine/opex.py`` — calendar-based OPEX tagging (no OI needed), supplies
    ``opt_opex_days`` (trading days to next monthly OPEX, td_to_opex from opex.tag()).
  * Wall distances (derived from summary ``opt_wall_up``/``opt_wall_down`` vs the summary
    spot): ``opt_wall_dist_up_pct`` = (wall_up / spot − 1) × 100, positive = above spot;
    ``opt_wall_dist_down_pct`` = (wall_down / spot − 1) × 100, negative = below spot.
  * ``opt_pin_risk`` (bool): True when OPEX proximity + long gamma + near wall converge
    (``opt_opex_days ≤ 5 AND opt_gamma_regime = 'long' AND
    min(|opt_wall_dist_up_pct|, |opt_wall_dist_down_pct|) ≤ 2%``).

``opt_iv_rank_252`` is created ALWAYS-NULL here (ruling A9): a separate post-merge PR
backfills it once the W1.1 IV-backfill series lands. This module NEVER computes it, even
if ``data/iv_history/`` appears.

PIT DISCIPLINE (hard rule, tested): a stamp for a fire on date ``D`` uses ONLY store data
with an as-of date ``≤ D``. summary rows are selected by the latest index date ``≤ D``;
chain days are the trading days whose ``asof ≤ D``; skew/ivspread rows are selected by the
latest ``date`` column value ``≤ D``; opex uses only the calendar date D. No lookahead.

SESSION DISCIPLINE (hard rule, tested — the #3721 weekend-row class): both PINNED
positioning stores accrue NON-SESSION entries, because the collector runs once per
CALENDAR day and a weekend/holiday run re-fetches the prior session's reading. Measured
2026-07-30: 11 of the 40 ``chains/{date}.parquet`` files are non-sessions, and 3,281 of
12,472 rows across the 403 ``summary_*.parquet`` files (26.3%). A non-session entry is not
a harmless duplicate — the builder recomputes IV, spot, walls and net-GEX off a stale
carried-forward price, so the row is a fabricated observation — and EVERY chain/summary
reader below slices its input POSITIONALLY (``usable[-1]``, ``usable[-2]``, ``usable[-6:]``,
``iloc[-1]``, ``iloc[-6]``), where a fabricated entry silently redefines what "yesterday"
and "5 sessions ago" mean.

The filter therefore lives in the two READERS, not in the seven consumers:
``_default_chain_dates`` (via ``lib.nyse_calendar.session_dates``) and
``_default_read_summary`` (via ``lib.nyse_calendar.session_rows``). One choke point each,
so every positional consumer inherits it. See each function's docstring for the measured
corruption it removes.

GAP DISCIPLINE (hard rule, tested — the 2026-08-03..08-05 outage class): session-filtering
guarantees every snapshot IS a session; it does not guarantee every session HAS a snapshot.
``polygon_gex`` is chronically gappy and always has been — measured on the committed chain
store at 2026-08-06, four interior gaps (2026-07-06, 07-15, 07-17, and the three-session
08-03..08-05 collection outage) punch holes in 31 snapshot dates, and the snapshot API is
current-only so NONE of them can ever be backfilled. Positional slicing then lies a second
way, independent of the weekend-row class above: ``usable[-6:]`` still returns six rows, but
they span NINE sessions at as_of 2026-08-06, and ``usable[-2]`` is FOUR sessions back rather
than one. The two chain readers answer this differently, because the honest answer differs:

  * ``_doi_slope_stamp`` FITS — and an OLS fit does not require evenly spaced x. Fitting
    against SESSION ORDINALS (``[0,1,2,3,4,8]`` rather than ``np.arange``) makes the slope
    genuinely per-session across the hole instead of charging a nine-session move to five
    steps. This is the correct estimator under irregular sampling, not a patch: on a dense
    window the ordinals ARE ``np.arange`` and the value is unchanged. Measured over 14
    liquid names at as_of 2026-08-06, positional overstated the per-session rate by ~1.6x
    and flipped META's SIGN (−0.0028 → +0.0348) — and ``S-DOI`` buckets on ``slope > 0``.
  * ``_voi_flag_stamp`` / ``_ovc_from_chain`` COMPARE TWO SNAPSHOTS, and both pin the older
    one to a specific meaning: "YESTERDAY's open interest". There is no re-weighting that
    rescues a boolean or an OI-weighted share whose baseline is four sessions stale — and
    the staleness is not neutral (OI accrues, so an older baseline is a LOWER bar and the
    vol>OI flag biases toward True). They therefore REFUSE: null unless ``usable[-2]`` is
    the session immediately before ``usable[-1]``.

Nulls printed, never a mislabeled basis. Refusing costs one as_of per gap for the two
comparisons (4 of 30 measured), where refusing the FIT would have cost 46% of all as_of
dates (12 of 26 windows are wider than six sessions) — a stat that is null half the time is
not a ledger primitive, and no repo change heals a collector outage.

The ledger's ``as_of`` column is a STRING (``YYYY-MM-DD``); store dates are datetimes.
All comparisons are done on ``date`` objects to avoid tz / ms-precision traps.

Pure, side-effect-free, trivially testable: all heavy readers are injectable so tests
feed synthetic frames without touching disk.
"""
from __future__ import annotations

import datetime as _dt
import glob
import math
import re
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from lib import config, nyse_calendar
from lib.nyse_calendar import session_dates, session_rows

# ── nullable stamp schema (ruling A6/A9; W-C additions 2026-07-05; W-OVC 2026-07-17) ─
# Order is the canonical column order for the ledger schema-union.
STAMP_COLS: list[str] = [
    "opt_gamma_regime",          # str: 'long'|'short' (summary gamma_regime)
    "opt_dist_to_flip_pct",      # float: dist_to_flip_pct
    "opt_wall_up",               # float: magnet_up (call/upside wall level)
    "opt_wall_down",             # float: magnet_down (put/downside wall level)
    "opt_iv30",                  # float: iv30
    "opt_iv_rank_252",           # float: ALWAYS NULL here (A9 — post-merge PR backfills)
    "opt_doi_slope_5d",          # float: 5d normalized near-money call-OI slope (null if <5 prior days)
    "opt_voi_flag",              # bool: today's vol > yesterday's OI on ≥1 near-money contract
    # W-C additions (2026-07-05) — new buckets S-IVSPREAD-F/S-SKEW_DECEL/S-TOP_RISK/S-PIN_RISK/S-VOI2
    "opt_ivspread_rel",          # float: call-put IV spread (rel, from ivspread snapshots); PIT ≤ as_of
    "opt_skew",                  # float: 30d OTM put IV minus ATM call IV (from skew snapshots); PIT ≤ as_of
    "opt_skew_5d_chg",           # float: opt_skew change over prior 5 calendar days of available snapshots
    "opt_opex_days",             # int: trading days to next monthly OPEX (td_to_opex from opex.tag())
    "opt_pin_risk",              # bool: opex_days<=5 AND gamma='long' AND min wall dist <=2% (S-PIN_RISK)
    "opt_wall_dist_up_pct",      # float: (wall_up/spot - 1)*100 — positive = how far above spot
    "opt_wall_dist_down_pct",    # float: (wall_down/spot - 1)*100 — negative = how far below spot
    # W-OVC additions (2026-07-17) — S-VANNA-RELIEF / S-FRONT-CHARM gate primitives
    "opt_vanna_relief",          # bool: iv30_5d_chg < 0 AND vanna_hedge_5d in top cross-sectional tercile
                                 #       per as_of (holdability / de-escalation state; caution-only RO-3)
    "opt_front7_charm_share",    # float: |charm| OI-weighted notional share for expiries ≤7 calendar days
                                 #        as fraction of total board; null when chain absent; S-FRONT-CHARM
    "opt_root_class",            # str: index_etf | sector_etf | industry_etf | single_name (display context)
                                 #      mandatory alongside opt_front7_charm_share (ETF sign era-unstable)
]

# Coverage-gated columns: these require an external data store (polygon_gex, skew snapshots,
# ivspread snapshots) to be non-null.  opt_opex_days is EXCLUDED because it is computed from
# a local calendar (engine/opex.py) and will be non-null on virtually every valid business date
# regardless of whether any options store has coverage for the ticker.
#
# The stamp_ledger retry gate (scripts/stamp_options_state.py) uses STAMP_COVERAGE_COLS — NOT
# STAMP_COLS — to decide whether a row is "unstamped" and eligible for future re-stamping.
# This preserves the W1.3 design: rows with only calendar-derived columns (opt_opex_days) remain
# fully retryable when GEX/skew/ivspread coverage later arrives.
# opt_opex_days: excluded because it is calendar-derived (non-null on every business date).
# opt_root_class: excluded because it is taxonomy-derived from the ticker alone (non-null
#   for every ticker; equivalent to opt_opex_days in that it needs no data store).
STAMP_COVERAGE_COLS: list[str] = [
    c for c in STAMP_COLS if c not in ("opt_opex_days", "opt_root_class")
]

# Ledger stamp column → its twin in the display store (data/options_entry/state.parquet,
# engine/options_entry_state.py).  Both sides are computed from the SAME pinned stores, so
# "ledger column 100% null while the display twin is populated" can only mean the ledger
# stamp path is dead — the compute works, the write never lands.  That is the exact
# silent-permanent-null signature that hid the W-OVC defect for six weeks (2026-07-17 →
# 2026-08-02: opt_front7_charm_share and opt_root_class at 0/2282 while the display store
# carried 370/415 and 415/415).  tests/test_options_stamp.py asserts this invariant on the
# committed parquets and scripts/stamp_options_state.py prints a ::warning nightly.
#
# Deliberately EXCLUDED (do not add without reading why):
#   opt_iv_rank_252   — designed-null in the ledger until the thetadata dedup repair
#                       lands (ruling A9); its display twin iv_rank_252 populates first.
#   opt_vanna_relief  — ledger-only cross-sectional construction (tercile per as_of over
#                       stamped fires); the display store carries raw vanna_hedge_5d, not
#                       the flag, so there is no twin to compare.
#   opt_doi_slope_5d / opt_voi_flag / opt_wall_up / opt_wall_down — no display twin
#                       (the display store carries different chain-derived fields).
DISPLAY_TWIN_COLS: dict[str, str] = {
    "opt_gamma_regime": "gamma_regime",
    "opt_dist_to_flip_pct": "dist_to_flip_pct",
    "opt_iv30": "iv30",
    "opt_ivspread_rel": "ivspread_rel",
    "opt_skew": "skew",
    "opt_skew_5d_chg": "skew_5d_chg",
    "opt_opex_days": "opex_days",
    "opt_pin_risk": "pin_risk",
    "opt_wall_dist_up_pct": "wall_up_dist_pct",
    "opt_wall_dist_down_pct": "wall_down_dist_pct",
    "opt_front7_charm_share": "front7_charm_share",
    "opt_root_class": "root_class",
}

# every stamp starts as all-None so a name with no options coverage yields a clean null row
_NULL_STAMP: dict = {c: None for c in STAMP_COLS}

# near-money band (fraction of spot) for the chain-derived signals
_NEAR_MONEY_FRAC = 0.10
# window length for the ΔOI slope: today + 5 prior trading snapshots = 6 points
_DOI_WINDOW = 6
# ...but the six snapshots are only SIX SESSIONS apart when the collector ran every
# session, and it does not (GAP DISCIPLINE, module header).  The fit is therefore taken
# against session ordinals, and the window is allowed to stretch only so far: at most as
# many sessions may be MISSING from it as the fit has steps (``_DOI_WINDOW - 1`` = 5), so
# six snapshots must span ≤ 11 sessions.  Past that the sample is more gap than
# observation and no re-weighting makes "5d" describe it → None.
_DOI_MAX_SPAN = 2 * _DOI_WINDOW - 1
# roots with a numeric suffix (e.g. AAPL1) are corporate-action-adjusted — never mis-parse
_ADJUSTED_ROOT = re.compile(r"\d$")


def _summary_dir() -> Path:
    return config.data_dir() / "polygon_gex"


def _chains_dir() -> Path:
    return config.data_dir() / "polygon_gex" / "chains"


def _as_date(x) -> _dt.date | None:
    """Coerce a string/date/Timestamp to a plain date, or None."""
    if x is None:
        return None
    if isinstance(x, _dt.date) and not isinstance(x, _dt.datetime):
        return x
    try:
        return pd.Timestamp(x).date()
    except (ValueError, TypeError):
        return None


# ── injectable readers (default = disk; tests pass fakes) ────────────────────
def _default_read_summary(ticker: str) -> pd.DataFrame | None:
    """The per-name GEX summary frame, SESSION-FILTERED (see module header).

    ``summary_*.parquet`` carries one row per CALENDAR day, so weekend/holiday rows are
    present: measured 2026-07-30, 3,281 of 12,472 rows across the 403 files are
    non-sessions (26.3%). Those rows are fabricated observations — the builder recomputes
    iv30/spot/walls/net-GEX off a stale carried-forward price — and four readers slice this
    frame positionally, so leaving them in corrupts each one:

      * ``_summary_stamp`` / ``_spot_from_summary`` — ``iloc[-1]``; the "latest" reading
        becomes a Saturday whenever the store has no row for the fire's own session.
      * ``_vanna_hedge_5d_from_summary`` — historically ``iloc[-6]``, which stops meaning
        "5 sessions ago". Measured on the store at as_of 2026-07-21, the raw ``iloc[-6]``
        resolved to 2026-07-14 where the true 5-sessions-back row is 2026-07-10, and the
        resulting vanna_hedge_5d changed for 10 of 10 sampled names WITH SIGN FLIPS (META
        +5.51e6 → −2.54e7, IWM +3.28e6 → −1.68e6). ``opt_vanna_relief`` gates on a
        cross-sectional tercile of that value, so a sign flip moves names across the gate.
        Since 2026-08-06 its 5-back endpoint is resolved by CALENDAR
        (``_row_n_sessions_back``), which splits the two gap shapes that positional
        slicing conflated. A gap INTERIOR to the window (the 08-03..08-05 collection
        outage, at as_of 08-06) no longer widens the basis at all — only the endpoints
        enter a difference and the 5-back session 07-30 is stored, so the stat recovers
        exactly. A gap AT THE TARGET SESSION is the unmeasurable case and returns None:
        measured over the committed store that is as_of 07-13 / 07-22 / 07-24, whose
        5-back targets 07-06 / 07-15 / 07-17 have no row in ANY store. This filter
        remains the first line of defence against weekend rows reaching that resolver.
      * ``scripts/stamp_options_state._get_iv30_5d_chg_from_summary`` — the same 5-back
        read; it reads through THIS function and ``_row_n_sessions_back``, so it
        inherits both fixes.

    ``session_rows`` is fail-open by contract: if filtering would empty the frame it
    returns the input unchanged, so a calendar surprise degrades to the old behaviour
    rather than to a blank stamp."""
    p = _summary_dir() / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        return session_rows(pd.read_parquet(p), label=f"polygon_gex/summary_{ticker}")
    except Exception:  # noqa: BLE001 — a corrupt per-name store must not break the whole pass
        return None


def _default_chain_dates() -> list[_dt.date]:
    """Sorted list of available chain snapshot SESSION dates (from the filenames).

    SESSION-FILTERED (see module header) — mirrors the #4018 repair of
    ``scripts/build_flow_leaders._load_two_chain_days``. The collector writes one file per
    CALENDAR day and a weekend/holiday run re-fetches the prior session's reading, so the
    raw glob returns non-session snapshots: measured 2026-07-30, 11 of the 40 files on disk
    are non-sessions (Saturdays, Sundays, and Juneteenth 2026-06-19).

    All three consumers slice this list positionally, so an unfiltered list corrupts each:

      * ``_voi_flag_stamp`` — ``usable[-1]`` vs ``usable[-2]``, the exact shape #4018
        repaired. On a weekend as_of those two files are ONE vintage (2026-07-25 and
        2026-07-26 are byte-identical: 163,564 rows, 117,303,840 total OI), so "today's
        volume > yesterday's OI" compares a snapshot against a copy of itself.
      * ``_doi_slope_stamp`` — OLS slope over ``usable[-6:]``. Measured on the store at
        as_of 2026-07-30 the raw window 07-25..07-30 spans only FOUR distinct sessions,
        because the 07-25 / 07-26 / 07-27 files all carry the 2026-07-24 reading — half
        the fit is duplicated points and the normalised slope is biased toward zero. The
        filtered window is 07-23, 07-24, 07-27, 07-28, 07-29, 07-30: six distinct
        sessions. Sampled across 10 liquid names the slope changed on 10/10 for every
        as_of tested, including sign flips (TSLA at 07-30: +0.0547 → −0.0550).
      * ``_ovc_from_chain`` — ``usable[-1]`` greeks against ``usable[-2]`` OI, the same
        shape as the voi flag.

    The filename is a RUN stamp, not the OI vintage (file *D* carries session *D−1*'s
    snapshot, since the collector runs pre-open). Session-filtering nonetheless yields one
    file per session with no duplicates — verified on the store at 2026-07-30: the raw
    store has 4 adjacent byte-identical file pairs, the filtered store has 0. Weekend
    files are not lost information: each carries the same vintage as the Monday file that
    follows it.

    Filtering HERE rather than in each reader is deliberate — one choke point, so every
    positional consumer inherits the fix. Tests that inject an explicit ``chain_dates``
    list are exercising the positional arithmetic itself and are unaffected."""
    out: list[_dt.date] = []
    for f in glob.glob(str(_chains_dir() / "*.parquet")):
        stem = Path(f).stem
        d = _as_date(stem)
        if d is not None:
            out.append(d)
    return sorted(session_dates(out))


def _default_read_chain(d: _dt.date) -> pd.DataFrame | None:
    p = _chains_dir() / f"{d.isoformat()}.parquet"
    if not p.exists():
        return None
    try:
        # only the columns the chain signals need.  expiry/T/iv are REQUIRED by
        # _ovc_from_chain's column check: from 2026-07-17 to 2026-08-02 this list
        # lacked them, so every default-path call silently nulled
        # opt_front7_charm_share (0/2282 ledger rows while the display store
        # carried 370/415 — registry defect opex-vanna-charm-wovc).
        return pd.read_parquet(
            p, columns=["underlying", "K", "expiry", "T", "iv",
                        "is_call", "oi", "volume", "spot"]
        )
    except Exception:  # noqa: BLE001
        return None


def _default_read_skew_snapshots() -> pd.DataFrame | None:
    """Load data/options_skew/snapshots.parquet (all dates).

    W-C: supplies opt_skew + opt_skew_5d_chg for S-SKEW_DECEL / S-TOP_RISK buckets.
    Columns we use: date (str), underlying (str), skew (float).
    Returns None if file absent (not on the render path; gitignored R2 store)."""
    p = config.data_dir() / "options_skew" / "snapshots.parquet"
    if not p.exists():
        return None
    try:
        return nyse_calendar.session_rows(
            pd.read_parquet(p, columns=["date", "underlying", "skew"]),
            "date", label="options_skew/snapshots")
    except Exception:  # noqa: BLE001
        return None


def _default_read_ivspread_snapshots() -> pd.DataFrame | None:
    """Load data/options_ivspread/snapshots.parquet (all dates).

    W-C: supplies opt_ivspread_rel for S-IVSPREAD-F / S-TOP_RISK buckets.
    Columns we use: date (str), underlying (str), ivspread_rel (float).
    Returns None if file absent."""
    p = config.data_dir() / "options_ivspread" / "snapshots.parquet"
    if not p.exists():
        return None
    try:
        return nyse_calendar.session_rows(
            pd.read_parquet(p, columns=["date", "underlying", "ivspread_rel"]),
            "date", label="options_ivspread/snapshots")
    except Exception:  # noqa: BLE001
        return None


# ── summary-derived stamp (positioning state at the fire) ────────────────────
def _summary_stamp(as_of: _dt.date, sdf: pd.DataFrame | None) -> dict:
    """Latest summary row with index date ≤ as_of (PIT)."""
    out = {
        "opt_gamma_regime": None, "opt_dist_to_flip_pct": None,
        "opt_wall_up": None, "opt_wall_down": None, "opt_iv30": None,
    }
    if sdf is None or sdf.empty:
        return out
    idx_dates = pd.Index([_as_date(d) for d in sdf.index])
    mask = np.array([d is not None and d <= as_of for d in idx_dates])
    if not mask.any():
        return out
    # the last row on/before as_of
    row = sdf[mask].iloc[-1]

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    reg = row.get("gamma_regime")
    out["opt_gamma_regime"] = str(reg) if reg is not None and not (isinstance(reg, float) and math.isnan(reg)) else None
    out["opt_dist_to_flip_pct"] = _f(row.get("dist_to_flip_pct"))
    out["opt_wall_up"] = _f(row.get("magnet_up"))
    out["opt_wall_down"] = _f(row.get("magnet_down"))
    out["opt_iv30"] = _f(row.get("iv30"))
    return out


def _near_money_call_oi(chain: pd.DataFrame, ticker: str) -> float | None:
    """Near-money (±10% of spot) total call OI for one name in one chain snapshot."""
    sub = chain[chain["underlying"] == ticker]
    if sub.empty:
        return None
    spot = sub["spot"].iloc[0]
    try:
        spot = float(spot)
    except (TypeError, ValueError):
        return None
    if not (spot > 0):
        return None
    lo, hi = spot * (1 - _NEAR_MONEY_FRAC), spot * (1 + _NEAR_MONEY_FRAC)
    nm = sub[(sub["K"] >= lo) & (sub["K"] <= hi)]
    calls = nm[nm["is_call"]]
    if calls.empty:
        return None
    return float(calls["oi"].fillna(0).sum())


def _session_span(first: _dt.date, last: _dt.date) -> int:
    """Sessions in the INCLUSIVE range — 1 for a single session, 0 when ``last < first``."""
    return len(nyse_calendar.sessions_between(first, last))


def _is_prior_session(prev_d: _dt.date, cur_d: _dt.date) -> bool:
    """True only when ``prev_d`` is the session IMMEDIATELY before ``cur_d``.

    The two-snapshot chain readers mean a literal "yesterday" by their older snapshot (see
    GAP DISCIPLINE in the module header), and after a collection gap it is not one. Also
    False when either date is a non-session, so a fabricated snapshot that slipped past the
    session filter cannot be read as yesterday either — fail-closed in both directions."""
    return _session_span(prev_d, cur_d) == 2


def _session_ordinals(dates: list[_dt.date]) -> list[float] | None:
    """0-based SESSION index of each date, counted from ``dates[0]``.

    A dense window yields ``[0,1,2,3,4,5]`` — exactly ``np.arange``, so the fit is
    unchanged wherever the collector ran every session. The 2026-08-06 window yields
    ``[0,1,2,3,4,8]``: the three sessions the outage lost are counted as elapsed time
    rather than silently collapsed into one step.

    None when any date is not a session or the list is not strictly ascending. A caller
    handing over unsorted or fabricated dates gets a null rather than a silent mis-fit."""
    if not dates:
        return None
    base = dates[0]
    out: list[float] = []
    for d in dates:
        span = nyse_calendar.sessions_between(base, d)
        if not span or span[-1] != d:
            return None          # d precedes base, or is not a session
        out.append(float(len(span) - 1))
    if any(b <= a for a, b in zip(out, out[1:])):
        return None              # duplicate or out-of-order snapshot dates
    return out


def _doi_slope_stamp(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> float | None:
    """5-day normalized near-money call-OI slope over the ``_DOI_WINDOW`` most-recent chain
    snapshots with date ≤ as_of. Needs ≥ 5 prior days (6 points total) or returns None.

    Normalized = OLS slope / mean(series) so it is comparable across names. Positive =
    call-OI accumulating (informed-accumulation proxy, Garleanu-Pedersen-Poteshman).

    TIME-TRUE ACROSS COLLECTION GAPS (see GAP DISCIPLINE in the module header). The fit is
    taken against SESSION ORDINALS, not snapshot positions, so the slope is a per-SESSION
    rate whether or not the collector ran every session: the units the ``_5d`` name and the
    ``S-DOI`` ``slope > 0`` bucket both assume. On a dense window the ordinals are
    ``np.arange`` and the value is byte-identical to the positional fit; only gapped
    windows change, where the positional number was wrong. The window may stretch to
    ``_DOI_MAX_SPAN`` sessions; past that no re-weighting makes it a 5-day read → None.

    That the chain filename is a RUN stamp carrying the PRIOR session's snapshot does not
    disturb the ordinals: ``D → previous session`` shifts every session index by exactly
    one, and OLS is invariant to a constant x offset, so the SPACING is identical whether
    ordinals are counted over run dates or over vintages."""
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < _DOI_WINDOW:
        return None
    window = usable[-_DOI_WINDOW:]
    if _session_span(window[0], window[-1]) > _DOI_MAX_SPAN:
        return None
    x_vals = _session_ordinals(window)
    if x_vals is None:
        return None
    series: list[float] = []
    for d in window:
        ch = read_chain(d)
        if ch is None:
            return None
        v = _near_money_call_oi(ch, ticker)
        if v is None:
            return None
        series.append(v)
    y = np.asarray(series, dtype=float)
    mean = float(y.mean())
    if not (mean > 0):
        return None
    x = np.asarray(x_vals, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope / mean, 6)


def _voi_flag_stamp(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> bool | None:
    """Vol>OI fresh-positioning marker: True if, on the most-recent chain snapshot ≤ as_of,
    at least one near-money contract has today's volume > YESTERDAY's open interest.

    Requires the current + one prior snapshot; None when unavailable. Uses prior-day OI so
    the comparison is genuinely 'fresh volume against pre-existing positioning' (not vol vs
    same-day OI, which trivially includes the new trades).

    PRIOR-SESSION-STRICT (see GAP DISCIPLINE in the module header): the prior snapshot must
    be the session immediately before the current one, else None. After a collection gap
    ``usable[-2]`` is several sessions back — at as_of 2026-08-06 it is four — and OI accrues
    over the sessions in between, so a stale baseline is a systematically LOWER bar and this
    flag biases toward True. A boolean has no re-weighting escape the way the ΔOI fit does:
    the honest output is a null, which ``S-VOI`` excludes from both buckets rather than
    scoring as False."""
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < 2:
        return None
    today_d, prev_d = usable[-1], usable[-2]
    if not _is_prior_session(prev_d, today_d):
        return None
    today = read_chain(today_d)
    prev = read_chain(prev_d)
    if today is None or prev is None:
        return None
    t = today[today["underlying"] == ticker]
    p = prev[prev["underlying"] == ticker]
    if t.empty or p.empty:
        return None
    try:
        spot = float(t["spot"].iloc[0])
    except (TypeError, ValueError):
        return None
    if not (spot > 0):
        return None
    lo, hi = spot * (1 - _NEAR_MONEY_FRAC), spot * (1 + _NEAR_MONEY_FRAC)
    t_nm = t[(t["K"] >= lo) & (t["K"] <= hi)].copy()
    if t_nm.empty:
        return None
    # prior-day OI keyed by (K, is_call) so we compare like contracts
    p_oi = (
        p.assign(_k=p["K"].round(4))
        .groupby(["_k", "is_call"])["oi"].sum()
    )
    t_nm["_k"] = t_nm["K"].round(4)
    fresh = False
    for _, r in t_nm.iterrows():
        vol = r.get("volume")
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            continue
        prior_oi = p_oi.get((r["_k"], r["is_call"]))
        # prior OI of 0 (or missing) with real volume = brand-new positioning → fresh
        prior_oi = float(prior_oi) if prior_oi is not None else 0.0
        if vol > prior_oi and vol > 0:
            fresh = True
            break
    return bool(fresh)


# ── W-C: skew/ivspread/opex/wall-dist stamps ────────────────────────────────
# These are PIT-disciplined reads from the W-C snapshot stores.  They mirror the
# summary-derived stamp pattern: latest row with date ≤ as_of, null on absence.

def _skew_stamp(
    as_of: _dt.date,
    ticker: str,
    skew_df: pd.DataFrame | None,
) -> dict:
    """opt_skew + opt_skew_5d_chg from data/options_skew/snapshots.parquet.

    PIT: only rows with date ≤ as_of used. skew_5d_chg = latest minus the snapshot
    from ≥ 5 calendar days earlier (the earliest qualifying row that is ≥ 5 days back
    from the latest row date); None when fewer than 2 qualifying rows exist.

    Returns a dict with keys opt_skew, opt_skew_5d_chg (both float | None)."""
    out: dict = {"opt_skew": None, "opt_skew_5d_chg": None}
    if skew_df is None or skew_df.empty:
        return out
    sub = skew_df[skew_df["underlying"] == ticker].copy()
    if sub.empty:
        return out
    # PIT filter: date column is a string 'YYYY-MM-DD'
    sub["_d"] = sub["date"].apply(_as_date)
    sub = sub[sub["_d"].apply(lambda d: d is not None and d <= as_of)]
    if sub.empty:
        return out
    sub = sub.sort_values("_d")

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    latest = sub.iloc[-1]
    skew_val = _f(latest["skew"])
    out["opt_skew"] = skew_val

    if skew_val is not None and len(sub) >= 2:
        latest_date = latest["_d"]
        # look for a row at least 5 calendar days earlier than the latest snapshot date
        cutoff = latest_date - _dt.timedelta(days=5)
        earlier = sub[sub["_d"] <= cutoff]
        if not earlier.empty:
            prior_skew = _f(earlier.iloc[-1]["skew"])
            if prior_skew is not None:
                out["opt_skew_5d_chg"] = round(skew_val - prior_skew, 6)
    return out


def _ivspread_stamp(
    as_of: _dt.date,
    ticker: str,
    ivspread_df: pd.DataFrame | None,
) -> dict:
    """opt_ivspread_rel from data/options_ivspread/snapshots.parquet.

    PIT: only rows with date ≤ as_of. Returns dict with key opt_ivspread_rel."""
    out: dict = {"opt_ivspread_rel": None}
    if ivspread_df is None or ivspread_df.empty:
        return out
    sub = ivspread_df[ivspread_df["underlying"] == ticker].copy()
    if sub.empty:
        return out
    sub["_d"] = sub["date"].apply(_as_date)
    sub = sub[sub["_d"].apply(lambda d: d is not None and d <= as_of)]
    if sub.empty:
        return out
    sub = sub.sort_values("_d")

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    out["opt_ivspread_rel"] = _f(sub.iloc[-1]["ivspread_rel"])
    return out


def _opex_stamp(as_of: _dt.date) -> dict:
    """opt_opex_days from engine/opex.py calendar tags (no OI needed; PIT by construction).

    Returns dict with key opt_opex_days (int | None). Wraps in try/except so a missing
    or malformed calendar never breaks the whole stamp pass."""
    out: dict = {"opt_opex_days": None}
    try:
        from engine import opex as _opex  # local import — avoid circular at module level
        # build a small index spanning today ± 60 days to ensure we have a next-OPEX
        today_ts = pd.Timestamp(as_of)
        idx = pd.date_range(today_ts - pd.offsets.BDay(2), today_ts + pd.offsets.BDay(45), freq="B")
        tagged = _opex.tag(idx)
        row = tagged[tagged.index.date == as_of]
        if row.empty:
            return out
        td_to = row.iloc[0].get("td_to") if hasattr(row.iloc[0], "get") else row.iloc[0]["td_to"]
        if td_to is not None and not (isinstance(td_to, float) and math.isnan(td_to)):
            out["opt_opex_days"] = int(td_to)
    except Exception:  # noqa: BLE001 — opex calc failure must not break stamp pass
        pass
    return out


def _wall_dist_stamp(
    opt_wall_up: float | None,
    opt_wall_down: float | None,
    spot: float | None,
) -> dict:
    """Compute wall distance percentages from already-computed summary wall levels + spot.

    opt_wall_dist_up_pct  = (wall_up / spot - 1) * 100  (positive when wall is above spot)
    opt_wall_dist_down_pct = (wall_down / spot - 1) * 100  (negative when wall is below spot)

    The spot is taken from the summary row's spot column (not chain spot) to stay consistent
    with the GEX model's reference frame.  Returns dict with both keys."""
    out: dict = {"opt_wall_dist_up_pct": None, "opt_wall_dist_down_pct": None}
    if spot is None or not (spot > 0):
        return out
    if opt_wall_up is not None:
        out["opt_wall_dist_up_pct"] = round((opt_wall_up / spot - 1.0) * 100.0, 4)
    if opt_wall_down is not None:
        out["opt_wall_dist_down_pct"] = round((opt_wall_down / spot - 1.0) * 100.0, 4)
    return out


# ── W-OVC stamp functions (2026-07-17) ──────────────────────────────────────
# (A full-width `_default_read_chain_by_date` reader lived here 2026-07-17..2026-08-02
# but was never wired — `stamp_options_state` handed `_ovc_from_chain` the pruned
# `_default_read_chain` instead, whose column list lacked expiry/T/iv.  The pruned
# reader now carries those columns and the dead twin is removed.)


def _ovc_from_chain(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> dict:
    """Compute W-OVC display columns from the chain snapshot on/before as_of.

    Returns dict with keys:
      opt_front7_charm_share  — float | None: |charm|-notional share for ≤7-calendar-day expiries
      opt_root_class          — str: index_etf | sector_etf | industry_etf | single_name

    PIT-disciplined: only the latest chain snapshot with date ≤ as_of is used.
    Null-safe: bs_greeks NaN on bad inputs; those contracts skipped silently.

    This function intentionally does NOT compute opt_vanna_relief (that requires cross-
    sectional tercile ranking across multiple tickers on the same as_of — done in the
    stamp_ledger pass, not here).

    OI TIMING (PIT-clean, matching the frozen study construction):
    The adjudicated study (options_opex_vanna_charm_study.py §340-343) builds front7_abs_charm_share
    from oi_signal = oi.groupby([expiration,strike,right])['open_interest'].shift(1) — prior-day OI
    per contract.  The adjudication §2 PIT-verification certifies the metric as clean precisely
    because of this shift.  This function replicates that construction:

      - Greeks (charm/T/iv) are taken from the CURRENT chain snapshot (usable[-1]) — same-day
        quote-derived inputs, matching the study merge of same-date greeks against shifted OI.
      - OI is taken from the PRIOR chain snapshot (usable[-2]) — pre-trade-day positions that
        do NOT include same-day fire-date trades (look-ahead).

    This matches _voi_flag_stamp's pattern (today chain for volume, prior chain for OI).
    When fewer than 2 usable snapshots exist the metric is null (cannot form prior-day OI).

    PRIOR-SESSION-STRICT (see GAP DISCIPLINE in the module header): what certifies this
    metric PIT-clean is that its OI is the study's ``shift(1)`` — the PRIOR SESSION's book.
    Across a collection gap ``usable[-2]`` is a shift(4), which is a different construction
    from the frozen one, and not a uniformly conservative one: front-week OI builds steeply
    into expiry, so a stale book understates exactly the ≤7-day weights this share is made
    of, by an amount that varies with each name's expiry ladder. That distorts the
    per-as_of tercile ``S-FRONT-CHARM`` buckets on, so the share goes null rather than
    mixed-basis. ``opt_root_class`` is unaffected — it is taxonomy from the ticker alone and
    needs no chain at all.
    """
    # Import here to avoid circular dependency at module level
    from engine.greeks import bs_greeks
    from engine.options_entry_state import _root_class

    out: dict = {"opt_front7_charm_share": None, "opt_root_class": _root_class(ticker)}

    # Need at least 2 usable snapshots: current for greeks, prior for OI
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < 2:
        return out
    chain_date = usable[-1]   # current snapshot — provides greeks (T, iv, spot, expiry)
    prev_date = usable[-2]    # prior snapshot — provides OI (pre-fire-day positions)
    if not _is_prior_session(prev_date, chain_date):
        return out            # gap: the OI book is not the study's shift(1) — null, not mixed-basis

    cdf = read_chain(chain_date)
    if cdf is None or cdf.empty:
        return out
    prev_cdf = read_chain(prev_date)
    if prev_cdf is None or prev_cdf.empty:
        return out

    # required columns
    required = {"underlying", "K", "T", "iv", "oi", "is_call", "spot", "expiry"}
    if not required.issubset(set(cdf.columns)):
        return out
    if not required.issubset(set(prev_cdf.columns)):
        return out

    sub = cdf[cdf["underlying"] == ticker].copy()
    if sub.empty:
        return out

    # Build prior-OI lookup keyed by (expiry, K, is_call) — the full contract key, matching
    # the study's groupby([expiration, strike, right]).shift(1). Keying without expiry would
    # sum OI across every expiry listed at a strike, contaminating front-week weights with
    # back-month positions.
    def _exp_key(expiry_val):
        try:
            return pd.Timestamp(expiry_val).date().isoformat()
        except Exception:
            return None

    prev_sub = prev_cdf[prev_cdf["underlying"] == ticker].copy()
    if not prev_sub.empty:
        prev_sub["_k"] = pd.to_numeric(prev_sub["K"], errors="coerce").round(4)
        prev_sub["oi"] = pd.to_numeric(prev_sub["oi"], errors="coerce")
        prev_sub["_exp"] = prev_sub["expiry"].apply(_exp_key)
        prior_oi_map = (
            prev_sub.dropna(subset=["_k", "oi", "_exp"])
            .groupby(["_exp", "_k", "is_call"])["oi"]
            .sum()
        )
    else:
        prior_oi_map = pd.Series(dtype=float)

    for col in ("K", "T", "iv", "spot"):
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub["_k"] = sub["K"].round(4)
    sub["_exp"] = sub["expiry"].apply(_exp_key)

    # days to expiry from the chain snapshot date
    def _dte(expiry_val) -> int | None:
        try:
            return (pd.Timestamp(expiry_val).date() - chain_date).days
        except Exception:
            return None

    sub = sub.copy()
    sub["_dte"] = sub["expiry"].apply(_dte)

    _MULT = 100.0
    abs_charm_total = 0.0
    abs_charm_front7 = 0.0

    for _, row in sub.iterrows():
        S, K_, T_, sigma = row["spot"], row["K"], row["T"], row["iv"]
        is_call = bool(row["is_call"])
        dte = row["_dte"]
        # Look up prior-day OI for this exact contract (expiry + rounded K + is_call)
        exp_k = row["_exp"]
        if exp_k is None:
            continue
        prior_oi = prior_oi_map.get((exp_k, row["_k"], is_call))
        if prior_oi is None:
            continue
        try:
            oi_f = float(prior_oi)
            s_f = float(S)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(oi_f) and oi_f > 0 and math.isfinite(s_f) and s_f > 0):
            continue
        try:
            _delta, _gamma, _vanna, charm = bs_greeks(S, K_, T_, sigma, is_call)
        except Exception:
            continue
        if not math.isfinite(charm):
            continue
        sign = 1.0 if is_call else -1.0
        charm_not = abs(sign * (charm / 365.0) * oi_f * _MULT * s_f)
        abs_charm_total += charm_not
        if dte is not None and 0 <= dte <= 7:
            abs_charm_front7 += charm_not

    if abs_charm_total > 0:
        out["opt_front7_charm_share"] = round(abs_charm_front7 / abs_charm_total, 6)

    return out


def _row_n_sessions_back(usable: pd.DataFrame, n: int) -> pd.Series | None:
    """The row exactly ``n`` NYSE sessions before ``usable``'s last row, resolved by DATE.

    A two-endpoint "n-session change" needs endpoints ``n`` SESSIONS apart, not ``n``
    ROWS apart — the two differ whenever the store took a collection outage. The
    2026-08-03..08-05 outage left every summary store's 6 trailing rows spanning 9
    sessions inclusive, i.e. EIGHT steps between the endpoints, so the positional
    ``iloc[-(n+1)]`` shipped an eight-session change under a five-session label.
    Calendar resolution stays exact across an interior gap (only the endpoints matter
    for a difference) and returns None when the target session has no row —
    unmeasurable, never mislabeled."""
    last_d = _as_date(usable.index[-1])
    if last_d is None:
        return None
    sess = nyse_calendar.sessions_between(last_d - _dt.timedelta(days=3 * n + 10), last_d)
    if len(sess) < n + 1:
        return None
    target = sess[-(n + 1)]
    for pos in range(len(usable) - 1, -1, -1):
        d = _as_date(usable.index[pos])
        if d == target:
            return usable.iloc[pos]
        if d is not None and d < target:
            break
    return None


# Why the 5-session basis was unavailable — the cross-sectional ranker in
# scripts/stamp_options_state.py needs these apart, because they mean opposite things
# for its tercile denominator:
#   BASIS_NO_HISTORY — the name has no options coverage at this as_of.  It was never a
#     candidate; counting it would depress the coverage ratio on a perfectly healthy
#     date (most ledger rows are names with no options store at all: 214 of 2,287).
#   BASIS_GAP — the name HAS history, but the store is missing the one session the
#     basis needs.  That is a collection MISS, and a date where most names miss is a
#     date whose surviving cross-section is coverage-SELECTED, not representative.
BASIS_OK = "ok"
BASIS_NO_HISTORY = "no_history"
BASIS_GAP = "gap"


def _vanna_hedge_5d_basis(
    as_of: _dt.date,
    sdf: pd.DataFrame | None,
) -> tuple[float | None, str]:
    """``(vanna_hedge_5d, status)`` — the value plus WHY it is null when it is null.

    Same computation as ``_vanna_hedge_5d_from_summary`` (which wraps this); the status
    exists so a caller ranking these values cross-sectionally can measure its own
    coverage.  See the BASIS_* constants above.
    """
    if sdf is None or sdf.empty:
        return None, BASIS_NO_HISTORY
    if "net_vex" not in sdf.columns or "iv30" not in sdf.columns:
        return None, BASIS_NO_HISTORY
    idx_dates = [_as_date(d) for d in sdf.index]
    mask = [d is not None and d <= as_of for d in idx_dates]
    usable = sdf[mask]
    if len(usable) < 6:
        return None, BASIS_NO_HISTORY
    latest = usable.iloc[-1]
    prior = _row_n_sessions_back(usable, 5)
    if prior is None:
        # ≥6 sessions of history, but not a row AT the 5-back session: a store gap.
        return None, BASIS_GAP

    def _f(v) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return None if not math.isfinite(x) else x

    net_vex = _f(latest.get("net_vex"))
    iv30_latest = _f(latest.get("iv30"))
    iv30_prior = _f(prior.get("iv30"))
    if net_vex is None or iv30_latest is None or iv30_prior is None:
        return None, BASIS_GAP
    iv30_5d_chg = iv30_latest - iv30_prior
    return round(-net_vex * iv30_5d_chg, 6), BASIS_OK


def _vanna_hedge_5d_from_summary(
    as_of: _dt.date,
    sdf: pd.DataFrame | None,
) -> float | None:
    """Compute vanna_hedge_5d = −net_vex × iv30_5d_chg from summary frame.

    PIT: uses only rows with index date ≤ as_of. Needs ≥ 6 such rows, and a row AT the
    session exactly 5 sessions before the latest usable row — resolved by CALENDAR via
    ``_row_n_sessions_back``, not by position, so a collection outage degrades this
    stat to None instead of silently widening its basis.
    Returns None when insufficient history, the 5-back session's row is absent,
    columns absent, or any value non-finite.
    """
    return _vanna_hedge_5d_basis(as_of, sdf)[0]


def _pin_risk_flag(
    opt_opex_days: int | None,
    opt_gamma_regime: str | None,
    opt_wall_dist_up_pct: float | None,
    opt_wall_dist_down_pct: float | None,
) -> bool | None:
    """S-PIN_RISK: True when OPEX proximity + long-gamma + near-wall converge.

    Condition (per pre-registration §4 W-C):
      opt_opex_days <= 5
      AND opt_gamma_regime == 'long'
      AND min(|opt_wall_dist_up_pct|, |opt_wall_dist_down_pct|) <= 2%

    Returns None when any required input is None (cannot evaluate the condition)."""
    if opt_opex_days is None or opt_gamma_regime is None:
        return None
    if opt_wall_dist_up_pct is None and opt_wall_dist_down_pct is None:
        return None
    if not (opt_opex_days <= 5):
        return False
    if opt_gamma_regime != "long":
        return False
    dists = [abs(d) for d in (opt_wall_dist_up_pct, opt_wall_dist_down_pct) if d is not None]
    if not dists:
        return None
    return bool(min(dists) <= 2.0)


def stamp_options_state(
    as_of,
    ticker: str,
    *,
    read_summary: Callable[[str], pd.DataFrame | None] | None = None,
    chain_dates: list[_dt.date] | None = None,
    read_chain: Callable[[_dt.date], pd.DataFrame | None] | None = None,
    skew_df: pd.DataFrame | None = None,
    ivspread_df: pd.DataFrame | None = None,
    _skew_loader: Callable[[], pd.DataFrame | None] | None = None,
    _ivspread_loader: Callable[[], pd.DataFrame | None] | None = None,
) -> dict:
    """Return the nullable options-state stamp for a fire ``(as_of, ticker)``.

    All ``STAMP_COLS`` are always present; any that cannot be computed from PIT data
    are None. ``opt_iv_rank_252`` is ALWAYS None here (ruling A9).

    Readers are injectable for testing; defaults read the pinned disk stores. Adjusted roots
    (numeric-suffixed, e.g. ``AAPL1``) are dropped rather than mis-parsed → all-null stamp.

    Injectable parameters for W-C snapshot stores:
      skew_df       — pre-loaded skew snapshots DataFrame (or None to load from disk)
      ivspread_df   — pre-loaded ivspread snapshots DataFrame (or None to load from disk)
      _skew_loader  — callable that returns the DataFrame (overrides disk default)
      _ivspread_loader — same for ivspread

    The stamp_ledger pass pre-loads these DataFrames once and passes them in to avoid
    re-reading the parquet files for every (as_of, ticker) pair.
    """
    d = _as_date(as_of)
    if d is None or not ticker or _ADJUSTED_ROOT.search(ticker):
        return dict(_NULL_STAMP)

    read_summary = read_summary or _default_read_summary
    read_chain = read_chain or _default_read_chain
    if chain_dates is None:
        chain_dates = _default_chain_dates()

    # W-C snapshot frames: load once from disk if not pre-supplied
    if skew_df is None:
        loader = _skew_loader or _default_read_skew_snapshots
        skew_df = loader()
    if ivspread_df is None:
        loader = _ivspread_loader or _default_read_ivspread_snapshots
        ivspread_df = loader()

    # ── SESSION GUARD (#3721 class, OIP E8 2026-07-29) ───────────────────────
    # Every dated store this stamp reads accrues non-session rows, and those rows
    # RECOMPUTE iv30 / spot / walls / skew off a stale carried-forward price — they are
    # fabricated observations, not genuine closes.  Measured 2026-07-29:
    # polygon_gex/summary_* ~11 of 39 dates, options_skew 8 of 28, options_ivspread
    # 6 of 21, polygon_gex/chains 11 of 39 snapshot files.  Unfiltered they corrupt this
    # module three ways: the PIT `date <= as_of` + `.iloc[-1]` pick can land on a
    # Saturday recompute; `_DOI_WINDOW`'s "today + 5 prior TRADING snapshots" stops
    # meaning sessions (`_vanna_hedge_5d_from_summary` resolves its 5-back endpoint by
    # calendar since 2026-08-06, but weekend rows would still pad its ≥6-row floor); and a
    # weekend chain snapshot enters the ΔOI slope as a duplicate day.
    # The DISK readers filter at their own source (_default_read_summary and the two
    # snapshot loaders) because two ledger-writing call paths in
    # scripts/stamp_options_state.py bypass this funnel entirely — see the docstring on
    # _default_read_summary.  The filters below therefore exist for INJECTED readers and
    # pre-loaded frames (the stamp_ledger pass hands both in); re-filtering an
    # already-session-true frame is a no-op.  Fail-open.
    _raw_read_summary = read_summary
    read_summary = lambda tk: nyse_calendar.session_rows(  # noqa: E731
        _raw_read_summary(tk), label=f"injected summary_{tk}")
    skew_df = (nyse_calendar.session_rows(skew_df, "date", label="injected options_skew")
               if skew_df is not None else None)
    ivspread_df = (nyse_calendar.session_rows(ivspread_df, "date",
                                              label="injected options_ivspread")
                   if ivspread_df is not None else None)
    # keep_unparseable=False: chain_dates are real date objects, so anything unreadable
    # here is a bug, not data we must preserve (contrast altdata, which passes PATHS).
    chain_dates = (nyse_calendar.session_dates(
        chain_dates, keep_unparseable=False, label="polygon_gex/chains")
        if chain_dates else chain_dates)

    stamp = dict(_NULL_STAMP)
    # W1.3 fields from GEX summary
    summary_s = _summary_stamp(d, read_summary(ticker))
    stamp.update(summary_s)
    stamp["opt_doi_slope_5d"] = _doi_slope_stamp(d, ticker, chain_dates, read_chain)
    stamp["opt_voi_flag"] = _voi_flag_stamp(d, ticker, chain_dates, read_chain)
    # opt_iv_rank_252 stays None by construction (A9)

    # W-C fields: skew / ivspread / opex / wall-dist / pin-risk
    stamp.update(_skew_stamp(d, ticker, skew_df))
    stamp.update(_ivspread_stamp(d, ticker, ivspread_df))
    stamp.update(_opex_stamp(d))

    # wall distances need spot from the summary row (same row as wall levels)
    spot = _spot_from_summary(d, read_summary(ticker))
    stamp.update(_wall_dist_stamp(stamp.get("opt_wall_up"), stamp.get("opt_wall_down"), spot))

    stamp["opt_pin_risk"] = _pin_risk_flag(
        stamp.get("opt_opex_days"),
        stamp.get("opt_gamma_regime"),
        stamp.get("opt_wall_dist_up_pct"),
        stamp.get("opt_wall_dist_down_pct"),
    )

    # W-OVC fields: front7_charm_share, root_class
    # opt_vanna_relief is NOT set here — it requires cross-sectional tercile ranking
    # across all fires on the same as_of, which is done in the stamp_ledger pass.
    ovc_data = _ovc_from_chain(d, ticker, chain_dates, read_chain)
    stamp["opt_front7_charm_share"] = ovc_data.get("opt_front7_charm_share")
    stamp["opt_root_class"] = ovc_data.get("opt_root_class")
    # opt_vanna_relief stays None; stamp_ledger sets it after cross-sectional ranking.
    # stamp["opt_vanna_relief"] is already None from _NULL_STAMP.

    return stamp


def _spot_from_summary(as_of: _dt.date, sdf: pd.DataFrame | None) -> float | None:
    """Extract spot price from the summary frame's 'spot' column (latest PIT row ≤ as_of).

    The GEX summary parquet may or may not carry a spot column; returns None if absent.
    This is used by _wall_dist_stamp to compute wall distances in percentage terms."""
    if sdf is None or sdf.empty:
        return None
    idx_dates = pd.Index([_as_date(d) for d in sdf.index])
    mask = np.array([d is not None and d <= as_of for d in idx_dates])
    if not mask.any():
        return None
    row = sdf[mask].iloc[-1]
    spot = row.get("spot")
    if spot is None:
        return None
    try:
        f = float(spot)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None
