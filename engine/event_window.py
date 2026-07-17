"""engine/event_window.py — Macro event-window calendar seasonality (P3, RIC program).

Cloned from the engine/opex.py idiom (tag → measure → snapshot, HAC seasonality,
era split). Covers the major US macro release calendar: CPI, FOMC, NFP, PPI, plus
weekly claims day tagging and collision state detection.

DISCIPLINE (honoring RIC-R3, RIC-R6, research/DO_NOT_REBUILD.md):
  • This module tags and MEASURES calendar-phase behaviour. It does NOT score or
    gate anything. No entry may be added to risk_radar._SCARES. Calendar-gated
    risk legs are FORBIDDEN at any tier (judge-panel ruling 2026-07-13; registered
    in DO_NOT_REBUILD.md §4).
  • The pre-FOMC drift (Lucca-Moench) is measured and EXPECTED to print DEAD
    post-2016. That honest null is the correct display — the house already ruled.
  • Collision states are pure calendar math: displayed as context, never scored.
  • The ex-ante release-risk read annotates uncertainty (display chip). It NEVER
    shifts a projection value (MRI-R20) and NEVER scales any score (RIC-R3).
  • Display context: "is_context_only": True on every emitted dict.

Date spines:
  - FOMC: static 1994→ announcement-era list checked against the Fed archive.
  - CPI/PPI/NFP: _SCHED_2026 from engine/event_calendar.py (same static table).
  - OPEX expiration days: engine/opex.expiration_days() — no duplication.

Phase labels (frozen at W0, RIC-R6):
  {cpi_day, cpi_week, fomc_day, fomc_week, post_fomc_3d, nfp_day, quiet}

Collision states (frozen at W0, RIC-R6):
  {cpi_fomc_same_week, cpi_in_opex_week, fomc_in_opex_week, triple_stack}

See engine/event_risk.py (fragility overlay), engine/event_calendar.py (date
spines), engine/opex.py (sibling idiom), engine/risk_radar.py (context chip —
display-only; compute() is NOT touched by this module).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Sequence

import numpy as np
import pandas as pd

from engine.validation import newey_west_tstat

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase window constants (trading days, relative to event day = 0)
# ---------------------------------------------------------------------------
WEEK_LO = -4          # Mon of event week (earliest; 0 = event day)
WEEK_HI = 0
POST_FOMC_LO, POST_FOMC_HI = 1, 3   # "post_fomc_3d" window

# Era split boundaries (frozen, RIC-R6 sub-period sign check contract)
ERA1_SPLIT = pd.Timestamp("2010-01-01")   # pre-2010 vs 2010+
ERA2_SPLIT = pd.Timestamp("2021-01-01")   # 2021+ slice (post-pandemic)

# ---------------------------------------------------------------------------
# Static FOMC announcement dates 1994→ (announcement era)
# Source: Federal Reserve archive + event_calendar.py _FOMC for 2026.
# Only the LAST DAY (announcement / press conference day) is included.
# We include only 2000+ for the practical SPY-history window.
# ---------------------------------------------------------------------------
_FOMC_ANNOUNCEMENT_DATES: list[str] = [
    # 2000
    "2000-02-02", "2000-03-21", "2000-05-16", "2000-06-28", "2000-08-22",
    "2000-10-03", "2000-11-15", "2000-12-19",
    # 2001
    "2001-01-03", "2001-01-31", "2001-03-20", "2001-04-18", "2001-05-15",
    "2001-06-27", "2001-08-21", "2001-09-17", "2001-10-02", "2001-11-06",
    "2001-12-11",
    # 2002
    "2002-01-30", "2002-03-19", "2002-05-07", "2002-06-26", "2002-08-13",
    "2002-09-24", "2002-11-06", "2002-12-10",
    # 2003
    "2003-01-29", "2003-03-18", "2003-05-06", "2003-06-25", "2003-08-12",
    "2003-09-16", "2003-10-28", "2003-12-09",
    # 2004
    "2004-01-28", "2004-03-16", "2004-05-04", "2004-06-30", "2004-08-10",
    "2004-09-21", "2004-11-10", "2004-12-14",
    # 2005
    "2005-02-02", "2005-03-22", "2005-05-03", "2005-06-30", "2005-08-09",
    "2005-09-20", "2005-11-01", "2005-12-13",
    # 2006
    "2006-01-31", "2006-03-28", "2006-05-10", "2006-06-29", "2006-08-08",
    "2006-09-20", "2006-10-25", "2006-12-12",
    # 2007
    "2007-01-31", "2007-03-21", "2007-05-09", "2007-06-28", "2007-08-07",
    "2007-09-18", "2007-10-31", "2007-12-11",
    # 2008
    "2008-01-30", "2008-03-18", "2008-04-30", "2008-06-25", "2008-08-05",
    "2008-09-16", "2008-10-08", "2008-10-29", "2008-12-16",
    # 2009
    "2009-01-28", "2009-03-18", "2009-04-29", "2009-06-24", "2009-08-12",
    "2009-09-23", "2009-11-04", "2009-12-16",
    # 2010
    "2010-01-27", "2010-03-16", "2010-04-28", "2010-06-23", "2010-08-10",
    "2010-09-21", "2010-11-03", "2010-12-14",
    # 2011
    "2011-01-26", "2011-03-15", "2011-04-27", "2011-06-22", "2011-08-09",
    "2011-09-21", "2011-11-02", "2011-12-13",
    # 2012
    "2012-01-25", "2012-03-13", "2012-04-25", "2012-06-20", "2012-08-01",
    "2012-09-13", "2012-10-24", "2012-12-12",
    # 2013
    "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19", "2013-07-31",
    "2013-09-18", "2013-10-30", "2013-12-18",
    # 2014
    "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18", "2014-07-30",
    "2014-09-17", "2014-10-29", "2014-12-17",
    # 2015
    "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17", "2015-07-29",
    "2015-09-17", "2015-10-28", "2015-12-16",
    # 2016
    "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15", "2016-07-27",
    "2016-09-21", "2016-11-02", "2016-12-14",
    # 2017
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14", "2017-07-26",
    "2017-09-20", "2017-11-01", "2017-12-13",
    # 2018
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01",
    "2018-09-26", "2018-11-08", "2018-12-19",
    # 2019
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31",
    "2019-09-18", "2019-10-30", "2019-12-11",
    # 2020
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28",
    "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27",
    "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
    "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026 (from event_calendar.py _FOMC)
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-09",
]

# CPI release days (month -> day-of-month) for 2026 (mirrored from event_calendar)
_CPI_2026: dict[int, int] = {
    1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10,
    7: 14, 8: 12, 9: 11, 10: 14, 11: 10, 12: 10,
}
# PPI release days
_PPI_2026: dict[int, int] = {
    1: 14, 2: 12, 3: 12, 4: 14, 5: 13, 6: 11,
    7: 15, 8: 13, 9: 10, 10: 15, 11: 13, 12: 15,
}
# NFP release days (exact published dates, not naive first-Friday)
_NFP_2026: dict[int, int] = {
    1: 9, 2: 6, 3: 6, 4: 3, 5: 8, 6: 5,
    7: 2, 8: 7, 9: 4, 10: 2, 11: 6, 12: 4,
}


# ---------------------------------------------------------------------------
# Date-spine builders
# ---------------------------------------------------------------------------
def _fomc_dates(index: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """All FOMC announcement days that fall within the index range."""
    lo = index.min()
    hi = index.max()
    out: set[pd.Timestamp] = set()
    for ds in _FOMC_ANNOUNCEMENT_DATES:
        t = pd.Timestamp(ds)
        if lo <= t <= hi:
            out.add(t)
    return out


def _static_release_dates(sched: dict[int, int],
                          index: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """Build release-date set for a given monthly schedule (day_of_month per month).

    The schedule is keyed month→day-of-month for a SINGLE year (2026).  Applying
    the same day-of-month to earlier years is invalid (CPI/PPI/NFP release days
    drift year to year), so this function only stamps dates for years covered by
    the schedule (2026).  Pre-2026 dates are left untagged — the phase tag for
    those rows falls through to 'quiet' for CPI/PPI/NFP phases, which is the
    honest result given we do not have the real historical release calendar.
    FOMC phases (sourced from _FOMC_ANNOUNCEMENT_DATES) are unaffected.
    """
    lo = index.min()
    hi = index.max()
    out: set[pd.Timestamp] = set()
    # Only stamp years for which the schedule is authoritative (2026 only).
    # Extending sched to other years would back-project wrong day-of-month values.
    for m, day in sched.items():
        for y in (2026,):
            if y < lo.year or y > hi.year:
                continue
            try:
                t = pd.Timestamp(date(y, m, day))
            except ValueError:
                continue
            if lo <= t <= hi:
                out.add(t)
    return out


def _claims_days(index: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """All Thursdays (weekly initial jobless claims) in the index range."""
    out: set[pd.Timestamp] = set()
    lo = index.min().date()
    hi = index.max().date()
    d = lo
    while d <= hi:
        if d.weekday() == 3:  # Thursday
            t = pd.Timestamp(d)
            if t in set(index):
                out.add(t)
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Expiration days (delegate to opex.py — no duplication)
# ---------------------------------------------------------------------------
def _opex_days(index: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """OPEX expiration days for the given index (delegates to engine.opex)."""
    try:
        from engine.opex import expiration_days
        exp = expiration_days(index)
        return set(exp.index)
    except Exception:  # noqa: BLE001 — degrade to empty
        log.debug("event_window: could not load opex expiration days")
        return set()


# ---------------------------------------------------------------------------
# Core tag() function
# ---------------------------------------------------------------------------
def tag(dates: pd.DatetimeIndex | Sequence) -> pd.DataFrame:
    """Per-trading-day event-window tags.

    Columns emitted:
      td_to_cpi   — trading days to next CPI release (0 = CPI day; NaN beyond window)
      td_to_fomc  — trading days to next FOMC announcement
      td_to_nfp   — trading days to next NFP release
      td_to_ppi   — trading days to next PPI release
      claims_day  — bool: is this a Thursday claims day?
      phase       — str: one of {cpi_day, cpi_week, fomc_day, fomc_week,
                                  post_fomc_3d, nfp_day, quiet}
      cpi_fomc_same_week   — bool collision
      cpi_in_opex_week     — bool collision
      fomc_in_opex_week    — bool collision
      triple_stack         — bool collision (release + FOMC + OPEX in same week)

    Causal: purely calendar-derived from date arithmetic and the static
    release/FOMC schedules. No market data consumed.
    """
    if not isinstance(dates, pd.DatetimeIndex):
        dates = pd.DatetimeIndex(dates)
    idx = pd.DatetimeIndex(sorted(set(dates)))
    if len(idx) == 0:
        return pd.DataFrame()

    # Integer position map (for distance arithmetic)
    pos: dict[pd.Timestamp, int] = {t: i for i, t in enumerate(idx)}
    n = len(idx)

    # Build event-day sets
    fomc_set = _fomc_dates(idx)
    cpi_set = _static_release_dates(_CPI_2026, idx)
    ppi_set = _static_release_dates(_PPI_2026, idx)
    nfp_set = _static_release_dates(_NFP_2026, idx)
    claims_set = _claims_days(idx)
    opex_set = _opex_days(idx)

    # Sorted arrays of integer positions for each event type
    def _event_pos(evt_set: set) -> np.ndarray:
        return np.array(sorted(pos[t] for t in evt_set if t in pos))

    fomc_pos = _event_pos(fomc_set)
    cpi_pos = _event_pos(cpi_set)
    ppi_pos = _event_pos(ppi_set)
    nfp_pos = _event_pos(nfp_set)
    opex_pos = _event_pos(opex_set)

    i_all = np.arange(n)

    def _td_to_next(event_positions: np.ndarray) -> np.ndarray:
        """Trading days to next event for each day in i_all. NaN if none ahead."""
        if len(event_positions) == 0:
            return np.full(n, np.nan)
        nxt_idx = np.searchsorted(event_positions, i_all, side="left")
        td = np.where(
            nxt_idx < len(event_positions),
            event_positions[np.clip(nxt_idx, 0, len(event_positions) - 1)] - i_all,
            np.nan,
        )
        return td

    def _td_since_last(event_positions: np.ndarray) -> np.ndarray:
        """Trading days since last event. NaN if none before."""
        if len(event_positions) == 0:
            return np.full(n, np.nan)
        prev_idx = np.searchsorted(event_positions, i_all, side="right") - 1
        td = np.where(
            prev_idx >= 0,
            i_all - event_positions[np.clip(prev_idx, 0, len(event_positions) - 1)],
            np.nan,
        )
        return td

    td_to_cpi = _td_to_next(cpi_pos)
    td_to_fomc = _td_to_next(fomc_pos)
    td_to_nfp = _td_to_next(nfp_pos)
    td_to_ppi = _td_to_next(ppi_pos)
    td_since_fomc = _td_since_last(fomc_pos)
    td_to_opex = _td_to_next(opex_pos)

    # Phase assignment (priority order: fomc_day > cpi_day > nfp_day >
    # post_fomc_3d > fomc_week > cpi_week > quiet)
    claims_flag = np.array([idx[i] in claims_set for i in range(n)], dtype=bool)

    fomc_day = (td_to_fomc == 0)
    cpi_day = (~fomc_day) & (td_to_cpi == 0)
    nfp_day = (~fomc_day) & (~cpi_day) & (td_to_nfp == 0)
    post_fomc_3d = (
        (~fomc_day) & (~cpi_day) & (~nfp_day)
        & (td_since_fomc >= POST_FOMC_LO)
        & (td_since_fomc <= POST_FOMC_HI)
    )
    # fomc_week: 1–4 trading days before FOMC announcement (fomc_day=0 already excluded above).
    fomc_week = (
        (~fomc_day) & (~cpi_day) & (~nfp_day) & (~post_fomc_3d)
        & (td_to_fomc >= 1) & (td_to_fomc <= abs(WEEK_LO))
    )
    cpi_week = (
        (~fomc_day) & (~cpi_day) & (~nfp_day) & (~post_fomc_3d) & (~fomc_week)
        & (td_to_cpi >= 1) & (td_to_cpi <= abs(WEEK_LO))
    )

    phase = np.where(
        fomc_day, "fomc_day",
        np.where(
            cpi_day, "cpi_day",
            np.where(
                nfp_day, "nfp_day",
                np.where(
                    post_fomc_3d, "post_fomc_3d",
                    np.where(
                        fomc_week, "fomc_week",
                        np.where(
                            cpi_week, "cpi_week",
                            "quiet"
                        )
                    )
                )
            )
        )
    )

    # ----- Collision states -----
    # "Same week" = both events within 0-4 trading days of each other forward
    # CPI+FOMC same week: CPI is within 4 trading days of FOMC (either direction)
    cpi_fomc_same_week = (
        (td_to_fomc <= abs(WEEK_LO)) & (td_to_fomc >= 0)
        & (td_to_cpi <= abs(WEEK_LO)) & (td_to_cpi >= 0)
    )
    # CPI in OPEX week: CPI within 4 days of OPEX expiration
    cpi_in_opex_week = (
        (td_to_cpi <= abs(WEEK_LO)) & (td_to_cpi >= 0)
        & (td_to_opex <= abs(WEEK_LO)) & (td_to_opex >= 0)
    )
    # FOMC in OPEX week
    fomc_in_opex_week = (
        (td_to_fomc <= abs(WEEK_LO)) & (td_to_fomc >= 0)
        & (td_to_opex <= abs(WEEK_LO)) & (td_to_opex >= 0)
    )
    # Triple stack: CPI or NFP + FOMC + OPEX all in same week
    release_close = (
        ((td_to_cpi <= abs(WEEK_LO)) & (td_to_cpi >= 0))
        | ((td_to_nfp <= abs(WEEK_LO)) & (td_to_nfp >= 0))
    )
    triple_stack = release_close & fomc_in_opex_week

    out = pd.DataFrame({
        "td_to_cpi": td_to_cpi,
        "td_to_fomc": td_to_fomc,
        "td_to_nfp": td_to_nfp,
        "td_to_ppi": td_to_ppi,
        "claims_day": claims_flag,
        "phase": phase,
        "cpi_fomc_same_week": cpi_fomc_same_week.astype(bool),
        "cpi_in_opex_week": cpi_in_opex_week.astype(bool),
        "fomc_in_opex_week": fomc_in_opex_week.astype(bool),
        "triple_stack": triple_stack.astype(bool),
    }, index=idx)
    return out


# ---------------------------------------------------------------------------
# Seasonality measurement (cloned from opex.py measurement contract)
# ---------------------------------------------------------------------------
def seasonality(close: pd.Series, fwd_days: int = 5) -> dict:
    """Measured forward-return AND forward realized-vol per event-window phase over
    the full history, with Newey-West HAC t-stat (overlapping windows), era split at
    2010 + 2021+ slice, and sub-period sign check — exact opex.py measurement contract.

    The Lucca-Moench pre-FOMC drift is measured and expected to print DEAD post-2016.
    That null is the HONEST display (house ruling). Significance gate: |t| >= 2.0
    AND same sign in both sub-periods. Returns in-sample display context only.
    """
    close = close.dropna().astype(float)
    if len(close) < 500:
        return {"available": False}
    t = tag(close.index)
    fwd = close.pct_change(fwd_days, fill_method=None).shift(-fwd_days) * 100
    fwd_rv = (
        close.pct_change(fill_method=None)
        .rolling(fwd_days)
        .std()
        .shift(-fwd_days)
        * np.sqrt(252) * 100
    )
    df = pd.concat(
        [t["phase"], fwd.rename("fwd"), fwd_rv.rename("rv")],
        axis=1
    ).dropna(subset=["fwd"])

    base = float(df["fwd"].mean())
    # Era split midpoints
    half = df.index[len(df) // 2]  # simple midpoint split (pre/post)

    out: dict = {
        "available": True, "fwd_days": fwd_days,
        "base_fwd_pct": round(base, 3),
        "n": int(len(df)), "phases": {},
        "pre_fomc_drift_note": (
            "Pre-FOMC drift (Lucca-Moench) expected DEAD post-2016 — house ruling. "
            "Null printed, not hidden."
        ),
    }
    phases = ("cpi_day", "cpi_week", "fomc_day", "fomc_week",
              "post_fomc_3d", "nfp_day", "quiet")
    for ph in phases:
        sub = df[df["phase"] == ph]
        if len(sub) < 30:   # fewer observations than opex phases — tolerate thinner
            continue
        excess = sub["fwd"] - base
        nw = newey_west_tstat(excess.to_numpy(), lags=max(2, fwd_days))
        # Sub-period sign check (era split)
        s1 = np.sign(df[(df["phase"] == ph) & (df.index < half)]["fwd"].mean() - base)
        s2 = np.sign(df[(df["phase"] == ph) & (df.index >= half)]["fwd"].mean() - base)
        # 2021+ era slice
        post2021 = df[(df["phase"] == ph) & (df.index >= ERA2_SPLIT)]
        post2021_excess = float(post2021["fwd"].mean() - base) if len(post2021) >= 10 else None
        out["phases"][ph] = {
            "mean_fwd_pct": round(float(sub["fwd"].mean()), 3),
            "excess_pct": round(float(excess.mean()), 3),
            "fwd_vol": round(float(sub["rv"].mean()), 2) if sub["rv"].notna().any() else None,
            "t_hac": nw.get("t"),
            "n": int(len(sub)),
            "sign_stable": bool(s1 == s2 and s1 != 0),
            "significant": bool(
                nw.get("t") is not None
                and abs(nw["t"]) >= 2.0
                and s1 == s2
            ),
            "post_2021_excess_pct": round(post2021_excess, 3) if post2021_excess is not None else None,
            "post_2021_n": int(len(post2021)),
        }
    return out


# ---------------------------------------------------------------------------
# Ex-ante release-risk read (night before a print, T-1 stamp)
# ---------------------------------------------------------------------------
def _read_mri_surprise_dispersion(release_type: str) -> dict | None:
    """Read MRI surprise-dispersion (predicted vs benchmark spread in σ-surprise units)
    from the committed release_forecast artifact. Returns None on any failure.

    Deterministic read — no network, no new math. The release_forecast.v2 artifact
    is written by scripts/build_release_forecast.py (MRI program); this function
    reads the committed site payload for display annotation.

    MRI-R20 law: this read NEVER shifts a projection value. Display context only."""
    try:
        import json
        from lib import config
        p = config.ROOT / "site" / "release_forecast" / "latest.json"
        if not p.exists():
            return None
        payload = json.loads(p.read_text())
        # Navigate to the release-type sub-section
        # Schema: release_forecast.v2 has sections keyed by release type (CPI, NFP, etc.)
        section = (payload or {}).get(release_type.upper())
        if not section:
            return None
        surprise_skew = section.get("surprise_skew") or {}
        sigma = surprise_skew.get("sigma") or surprise_skew.get("sigma_scale_pp")
        pred_spread = section.get("prediction_spread_sigma")
        # Expectation read (MRI-R22): predicted vs market+nowcast expectation
        expectation = section.get("expectation_read")
        return {
            "release_type": release_type,
            "sigma_surprise": float(sigma) if sigma is not None else None,
            "pred_spread_sigma": float(pred_spread) if pred_spread is not None else None,
            "expectation_read": expectation,
            "asof": payload.get("asof") or section.get("asof"),
            "available": sigma is not None,
        }
    except Exception:  # noqa: BLE001
        return None


def _read_implied_event_move(spy_vol_payload: dict | None = None) -> dict | None:
    """Extract the implied event move from the T1 near-dated SPY straddle.

    Method: reads the already-committed options_hub vol payload for SPY (schema
    options_hub.vol/v1). The front-expiry ATM IV is used to back out the implied
    1-day event move: implied_move = ATM_IV * sqrt(1/252) * sqrt(2/pi) * spot.
    This is the standard straddle-approximation (delta-neutral ATM straddle price ≈
    ATM_IV / sqrt(252/DTE * 2*pi)).

    The method is frozen in this PR (RIC-R6). EOD read — off the render path.
    Printed vs trailing realized event-move distribution (stored in the forward ledger).

    Justification for options_hub vol payloads (not raw T1 store):
      - The options_hub SPY vol payload is already committed nightly by the theta-ops
        lane (build_options_surface.py). Re-reading the raw T1 ThetaData parquet from
        a render lane would breach the write-isolation law (theta-ops is sole writer).
      - The committed payload already has ATM IV per expiry (term structure), which is
        all we need for the straddle approximation.
      - The raw T1 straddle computation is reserved for the off-render theta-ops lane
        (when deeper precision is needed for forward-ledger accrual).

    Returns None on any failure (null degrades gracefully, MRI-R20 honesty)."""
    try:
        if spy_vol_payload is None:
            # Try loading from committed site artifact
            import json
            from lib import config
            p = config.ROOT / "site" / "options_hub" / "vol" / "SPY.json"
            if not p.exists():
                return None
            spy_vol_payload = json.loads(p.read_text())
        term = spy_vol_payload.get("term") or []
        spot = None
        # term: [{dte, exp, atm_iv}, ...] sorted by dte
        if not term:
            return None
        # Find front expiry >= 1 DTE (day-of-release spanning straddle)
        front = next((r for r in term if r.get("dte", 0) >= 1), None)
        if front is None or not front.get("atm_iv"):
            return None
        atm_iv_pct = front["atm_iv"]   # already in % (e.g. 18.5 = 18.5% annualized)
        dte = int(front["dte"])
        # Delta-neutral ATM straddle expected absolute move (E|move|):
        #   E|move| = ATM_IV * sqrt(dte/252) * sqrt(2/pi)
        # This is the standard straddle approximation (not a 1-sigma move).
        # sqrt(2/pi) ≈ 0.7979 converts the 1-sigma Gaussian to E|X| where X~N(0,σ).
        _sqrt_2_over_pi = (2.0 / np.pi) ** 0.5
        implied_move_pct = atm_iv_pct / 100.0 * (dte / 252.0) ** 0.5 * _sqrt_2_over_pi * 100.0
        # 1-day equivalent: ATM_IV * sqrt(1/252) * sqrt(2/pi)
        implied_1d_pct = atm_iv_pct / 100.0 * (1.0 / 252.0) ** 0.5 * _sqrt_2_over_pi * 100.0
        return {
            "method": "atm_straddle_approx",  # E|move| via delta-neutral straddle, not 1-sigma
            "source": "options_hub.vol/v1 (SPY)",
            "atm_iv_pct": round(atm_iv_pct, 2),
            "dte": dte,
            "exp": front.get("exp"),
            "implied_move_pct": round(implied_move_pct, 2),
            "implied_1d_move_pct": round(implied_1d_pct, 2),
            "available": True,
            "dealer_sign_note": (
                "long_call_short_put assumption (unobservable, printed per W2 passport)"
            ),
        }
    except Exception:  # noqa: BLE001
        return None


def ex_ante_read(
    release_type: str,
    phase_stats: dict | None = None,
    gamma_regime: str | None = None,
    spy_vol_payload: dict | None = None,
    print_integrity_chip: dict | None = None,
    today: date | None = None,
) -> dict:
    """Ex-ante release-risk read (night before a print, T-1 stamp).

    Deterministic composition:
      1. MRI surprise-dispersion (predicted vs benchmark spread in σ-surprise units)
      2. Implied event move from T1 near-dated SPY straddle (ATM straddle approx)
      3. Current gamma regime + window phase (from P2 / opex snapshot)
      4. Print-integrity chip (from existing MRI surfaces)

    LAWS (non-negotiable):
      - MRI-R20: NEVER shifts a projection value — annotates uncertainty only
      - RIC-R3 (no-dampener): NEVER scales any score
      - display_only=True, is_context_only=True

    Returns a dict with is_context_only=True always. All sub-fields nullable (null
    degrades gracefully — the chip renders with available=False when inputs absent)."""
    today = today or date.today()
    mri = _read_mri_surprise_dispersion(release_type)
    implied = _read_implied_event_move(spy_vol_payload)
    read: dict = {
        "schema": "event_window.ex_ante.v1",
        "release_type": release_type,
        "asof": today.isoformat(),
        "is_context_only": True,
        "display_only": True,
        "available": False,
        "mri_surprise_dispersion": mri,
        "implied_event_move": implied,
        "gamma_regime": gamma_regime,
        "window_phase_stats": phase_stats,
        "print_integrity": print_integrity_chip,
        "laws": {
            "mri_r20": "no projection shift",
            "ric_r3": "no score dampener",
            "display_only": True,
        },
    }
    # Compose glance copy (bilingual; stance-verb style)
    parts_en: list[str] = []
    parts_zh: list[str] = []
    if mri and mri.get("available"):
        sigma = mri.get("sigma_surprise")
        if sigma is not None:
            parts_en.append(f"Trailing surprise σ: {sigma:.2f}pp")
            parts_zh.append(f"历史惊喜标准差：{sigma:.2f}个百分点")
        pred_spread = mri.get("pred_spread_sigma")
        if pred_spread is not None:
            parts_en.append(f"Model spread vs benchmark: {pred_spread:+.1f}σ")
            parts_zh.append(f"模型预测 vs 基准偏差：{pred_spread:+.1f}σ")
    if implied and implied.get("available"):
        m = implied.get("implied_1d_move_pct")
        if m is not None:
            parts_en.append(f"Implied event move: ±{m:.1f}%")
            parts_zh.append(f"隐含事件波动：±{m:.1f}%")
    if gamma_regime:
        parts_en.append(f"Gamma regime: {gamma_regime}")
        parts_zh.append(f"Gamma 状态：{gamma_regime}")
    if phase_stats and phase_stats.get("fwd_vol"):
        rv = phase_stats["fwd_vol"]
        parts_en.append(f"Phase base-rate fwd-vol: {rv:.1f}%")
        parts_zh.append(f"阶段基准前向波动率：{rv:.1f}%")

    read["available"] = bool(parts_en)
    read["glance_en"] = " · ".join(parts_en) if parts_en else "Context unavailable — inputs absent"
    read["glance_zh"] = " · ".join(parts_zh) if parts_zh else "上下文不可用——输入缺失"
    read["disclaimer_en"] = (
        "This read annotates uncertainty — it NEVER shifts a projection (MRI-R20) "
        "and NEVER scales a score (RIC-R3). Display context only."
    )
    read["disclaimer_zh"] = (
        "此读数用于标注不确定性——不会修改任何预测值（MRI-R20），不会缩放任何评分（RIC-R3）。仅供展示参考。"
    )
    return read


# ---------------------------------------------------------------------------
# Snapshot (current phase + measured stats + collision read)
# ---------------------------------------------------------------------------
def snapshot(
    close: pd.Series | None,
    spy_vol_payload: dict | None = None,
    gamma_regime: str | None = None,
    print_integrity_chip: dict | None = None,
    today: date | None = None,
) -> dict:
    """Current event-window phase + measured stats + collision read + ex-ante read.

    None-safe (returns available=False when inputs insufficient).
    is_context_only=True always — display, never scored or gated."""
    today = today or date.today()
    today_ts = pd.Timestamp(today)

    close_ok = close is not None and len(close.dropna()) >= 500
    if not close_ok:
        return {
            "available": False, "is_context_only": True,
            "reason": "Insufficient price history (need >= 500 days)",
        }
    close = close.dropna().astype(float)
    t = tag(close.index)
    if today_ts not in t.index:
        # Use last available row
        t_row = t.iloc[-1]
    else:
        t_row = t.loc[today_ts]

    seas = seasonality(close)
    phase = str(t_row["phase"])
    ph_stats = (seas.get("phases") or {}).get(phase, {})

    # Glance copy (significant phases get an honest edge read)
    if ph_stats.get("significant"):
        ex = ph_stats["excess_pct"]
        read = (
            f"{phase.replace('_', ' ')}: historically {'+' if ex >= 0 else ''}{ex:.2f}% "
            f"excess fwd-{seas['fwd_days']}d return "
            f"(HAC t={ph_stats['t_hac']:.2f}, n={ph_stats['n']}). "
            "Display context — not a buy/sell signal."
        )
        read_zh = (
            f"{phase}阶段：历史超额前向收益 {'+' if ex >= 0 else ''}{ex:.2f}%"
            f"（HAC t={ph_stats['t_hac']:.2f}，n={ph_stats['n']}）。"
            "仅供展示参考，非买卖信号。"
        )
    else:
        read = (
            f"{phase.replace('_', ' ')}: no statistically robust calendar edge "
            "measured (display context)."
        )
        read_zh = f"{phase}阶段：未测得统计显著的日历效应（仅供参考）。"

    # Collision state(s)
    collision_states = {
        "cpi_fomc_same_week": bool(t_row["cpi_fomc_same_week"]),
        "cpi_in_opex_week": bool(t_row["cpi_in_opex_week"]),
        "fomc_in_opex_week": bool(t_row["fomc_in_opex_week"]),
        "triple_stack": bool(t_row["triple_stack"]),
    }
    active_collisions = [k for k, v in collision_states.items() if v]

    # Ex-ante read (night-before chip)
    # Only compose for high-impact release types approaching within 1 day
    ex_ante = None
    for rtype, td_col in [("CPI", "td_to_cpi"), ("NFP", "td_to_nfp"),
                           ("FOMC", "td_to_fomc"), ("PPI", "td_to_ppi")]:
        td_val = t_row.get(td_col)
        if td_val is not None and not (isinstance(td_val, float) and np.isnan(td_val)):
            if int(td_val) <= 1:  # tonight or tomorrow
                ex_ante = ex_ante_read(
                    rtype,
                    phase_stats=ph_stats,
                    gamma_regime=gamma_regime,
                    spy_vol_payload=spy_vol_payload,
                    print_integrity_chip=print_integrity_chip,
                    today=today,
                )
                break

    return {
        "schema": "event_window.snapshot.v1",
        "asof": today.isoformat(),
        "available": True,
        "is_context_only": True,
        "phase": phase,
        "td_to_cpi": _int_or_none(t_row["td_to_cpi"]),
        "td_to_fomc": _int_or_none(t_row["td_to_fomc"]),
        "td_to_nfp": _int_or_none(t_row["td_to_nfp"]),
        "td_to_ppi": _int_or_none(t_row["td_to_ppi"]),
        "claims_day": bool(t_row["claims_day"]),
        "collision_states": collision_states,
        "active_collisions": active_collisions,
        "read": read,
        "read_zh": read_zh,
        "phase_stats": ph_stats,
        "ex_ante": ex_ante,
        "seasonality": seas,
        "doctrine": (
            "Event-window calendar seasonality — thin, widely-known calendar tilts "
            "measured on price history. Context only, never a buy/sell. "
            "Pre-FOMC drift expected DEAD post-2016 (house ruling)."
        ),
    }


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Forward ledger (nightly-gated, keep-FIRST)
# ---------------------------------------------------------------------------
def ledger_lane_armed() -> bool:
    """True only on COLLECT_LANE=nightly (sole forward-ledger advancer, house law)."""
    import os
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def _ledger_path(path=None):
    """Resolve the forward-log path.

    If `path` is supplied and ends with '.jsonl' (or is a file path), return it
    directly — this allows test callers to pass a tmp_path file directly.
    If `path` is a directory root (no extension), append the standard sub-path.
    If `path` is None, use config.data_dir()."""
    from pathlib import Path
    if path is not None:
        p = Path(path)
        # If the caller passed a file path (has a suffix or ends with .jsonl)
        if p.suffix == ".jsonl" or p.name.endswith(".jsonl"):
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        # Otherwise treat as a data root directory
        p = p / "data" / "event_windows" / "forward_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    try:
        from lib import config
        p = config.data_dir() / "event_windows" / "forward_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:  # noqa: BLE001
        p = Path("data/event_windows/forward_log.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def _read_ledger(p) -> list[dict]:
    import json
    from pathlib import Path
    p = Path(p)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def _write_ledger(p, rows: list[dict]) -> None:
    import json
    from pathlib import Path
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    )


def stamp_ex_ante(
    release_type: str,
    release_date: str,
    ex_ante_dict: dict,
    t_minus_1_snap: dict,
    path=None,
) -> bool:
    """Stamp one T-1 (night-before) row into the forward ledger.

    Keep-FIRST: if a row for (release_type, release_date) already exists, the
    existing row is preserved (first-writer-wins idempotency).
    Self-gates on ledger_lane_armed() — off-lane calls no-op and return False.

    Returns True if a new row was written, False otherwise.

    Rulers (frozen in this PR, RIC-R6):
      - Primary: realized event-day move vs implied (ex-ante read)
      - Secondary: realized vol vs phase base-rate fwd-vol
      - Descriptive: surprise-direction × reaction sign by regime
    """
    if not ledger_lane_armed():
        return False
    p = _ledger_path(path)
    rows = _read_ledger(p)
    # Keep-FIRST: skip if already present
    if any(r.get("release_type") == release_type and r.get("release_date") == release_date
           for r in rows):
        return False
    import json
    row: dict = {
        "release_type": release_type,
        "release_date": release_date,
        "stamped_at": ex_ante_dict.get("asof"),
        # Ex-ante read (frozen at T-1)
        "implied_1d_move_pct": (
            (ex_ante_dict.get("implied_event_move") or {}).get("implied_1d_move_pct")
        ),
        "implied_move_pct": (
            (ex_ante_dict.get("implied_event_move") or {}).get("implied_move_pct")
        ),
        "atm_iv_pct": (
            (ex_ante_dict.get("implied_event_move") or {}).get("atm_iv_pct")
        ),
        "mri_sigma": (
            (ex_ante_dict.get("mri_surprise_dispersion") or {}).get("sigma_surprise")
        ),
        "mri_pred_spread_sigma": (
            (ex_ante_dict.get("mri_surprise_dispersion") or {}).get("pred_spread_sigma")
        ),
        "phase": t_minus_1_snap.get("phase"),
        "active_collisions": t_minus_1_snap.get("active_collisions"),
        "gamma_regime": ex_ante_dict.get("gamma_regime"),
        # Grade fields (filled post-release by grade_forward_log)
        "realized_1d_move_pct": None,
        "realized_fwd_vol": None,
        "surprise_direction": None,  # "hot" | "cold" | "inline" | None
        "reaction_sign": None,       # "up" | "down" | None
        "implied_vs_realized": None, # signed ratio: realized / implied
        # Rulers (frozen)
        "rulers": {
            "primary": "realized_event_day_move_vs_implied",
            "secondary": "realized_vol_vs_phase_base_rate",
            "descriptive": "surprise_direction_x_reaction_sign_by_regime",
        },
        "schema": "event_windows.forward_log.v1",
    }
    rows.append(row)
    _write_ledger(p, rows)
    return True


def grade_forward_log(
    spy_closes: dict,
    realized_vol_map: dict | None = None,
    path=None,
) -> int:
    """Fill realized move and vol for ungraded ledger rows where price data is available.

    spy_closes: {iso_date: close_price}
    realized_vol_map: {iso_date: realized_vol_pct} (optional; 5-day realized vol)
    Returns number of rows graded.
    Self-gates on ledger_lane_armed()."""
    if not ledger_lane_armed():
        return 0
    p = _ledger_path(path)
    rows = _read_ledger(p)
    if not rows or not spy_closes:
        return 0
    dates = sorted(spy_closes)
    n = 0
    for r in rows:
        if r.get("realized_1d_move_pct") is not None:
            continue  # already graded
        rd = r.get("release_date")
        if not rd or rd not in spy_closes:
            continue
        i = dates.index(rd)
        if i == 0:
            continue
        prev, cur = spy_closes[dates[i - 1]], spy_closes[rd]
        if not prev:
            continue
        ret_pct = (cur / prev - 1.0) * 100.0
        r["realized_1d_move_pct"] = round(ret_pct, 3)
        r["reaction_sign"] = "up" if ret_pct >= 0 else "down"
        # Implied vs realized
        impl = r.get("implied_1d_move_pct")
        if impl and impl > 0:
            r["implied_vs_realized"] = round(abs(ret_pct) / impl, 3)
        # Realized vol
        if realized_vol_map and rd in realized_vol_map:
            r["realized_fwd_vol"] = realized_vol_map[rd]
        n += 1
    if n:
        _write_ledger(p, rows)
    return n


def ledger_summary(path=None) -> dict:
    """Summarize graded forward-log rows (context: for display / admin)."""
    rows = [r for r in _read_ledger(_ledger_path(path))
            if r.get("realized_1d_move_pct") is not None]
    if not rows:
        return {"n": 0, "available": False}
    moves = [abs(r["realized_1d_move_pct"]) for r in rows]
    impls = [r["implied_1d_move_pct"] for r in rows if r.get("implied_1d_move_pct")]
    ratios = [r["implied_vs_realized"] for r in rows if r.get("implied_vs_realized")]
    ups = [1 for r in rows if r.get("reaction_sign") == "up"]
    return {
        "available": True,
        "n": len(rows),
        "avg_abs_move_pct": round(sum(moves) / len(moves), 2),
        "up_rate": round(len(ups) / len(rows), 2),
        "n_with_implied": len(impls),
        "avg_implied_1d_pct": round(sum(impls) / len(impls), 2) if impls else None,
        "avg_impl_vs_realized": round(sum(ratios) / len(ratios), 3) if ratios else None,
        "is_context_only": True,
    }
