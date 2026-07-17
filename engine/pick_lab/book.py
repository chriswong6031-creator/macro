"""Pick Lab scoreboard computation per book (spec §4).

scoreboard(engine_id, fires, grades, all_fires=None, all_grades=None,
           universe_base_rate=None) -> dict

Computes:
  n_fires, n_open, n_distinct_fire_dates, months_span
  Per-horizon WR (abs + excess), median excess, median MFE, median |MAE|, asym
  Equal-weight 21d-cohort overlapping NAV on excess returns
  Max drawdown of that NAV
  Lift vs plab_random_ctrl and vs universe buy-anytime base rate
  Status: ACCRUING until PL-R4 floor (n>=25, >=3 months, >=6 distinct fire dates)

Avoid-book (plab_topping_avoid): scoreboard flips sign into avoid_accuracy.
LH books: per-horizon medians + first-maturation ETA date only.

Metric definitions
------------------
universe_base_rate_21d : float | None
    Panel-median 21d SPY-excess across ALL snapshot tickers per fire-date, pooled
    over all mature fire-dates.  Answers: "what does a random pick from tonight's
    full universe return over 21 sessions?"  Independent of the 12-name random ctrl.

timing_lift_21d : float | None
    For each matured fire, the ticker's OWN baseline is computed as the median 21d
    SPY-excess across all panel start dates where the full 21-session window fits,
    EXCLUDING start dates within 21 sessions of the fire's exec_date (so the fire's
    own move does not contaminate its own baseline).
    timing_lift_21d = median over fires of (fire's ret_excess_spy - ticker_baseline).
    Isolates WHEN-skill from WHICH-skill: a book that picks good names but times them
    no better than their any-day median will show timing_lift_21d ≈ 0.

Public API
----------
scoreboard(engine_id, fires, grades, ...) -> dict
all_scoreboards(fires, grades, ...) -> list[dict]
universe_base_rate(grades) -> float | None
  Median 21d excess of ALL snapshot tickers (computed from grades of
  plab_random_ctrl as the honest proxy for buy-anytime, per spec §4).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ constants -

# Floors for ACCRUING → scoreable transition (PL-R4)
FLOOR_N_FIRES = 25
FLOOR_MONTHS_SPAN = 3
FLOOR_DISTINCT_FIRE_DATES = 6

# NAV ladder parameters
NAV_HOLD_SESSIONS = 21   # each cohort held 21 sessions
NAV_DAILY_WEIGHT = 1 / NAV_HOLD_SESSIONS  # equal-weight over 21d overlap

# Avoid book id
AVOID_ENGINE_ID = "plab_topping_avoid"

# LH horizon_roles
LH_HORIZON_ROLE = "hold_thesis"

# Primary horizons for WR / median (entry = 21d primary per PL-R3)
ENTRY_HORIZONS = (5, 10, 21, 63)
LH_HORIZONS = (126, 252)


# ------------------------------------------------------------------ helpers ---


def _filter(rows: list[dict], engine_id: str) -> list[dict]:
    return [r for r in rows if r.get("engine_id") == engine_id]


def _filter_path(grades: list[dict], horizon: int) -> list[dict]:
    """Return path rows (kind='path') at the given window horizon."""
    return [
        g for g in grades
        if g.get("kind") == "path" and g.get("horizon") == horizon
    ]


def _filter_ret(grades: list[dict]) -> list[dict]:
    """Return return rows (kind='ret' or kind absent — legacy)."""
    return [
        g for g in grades
        if g.get("kind") in ("ret", None)
    ]


def _wr(rets: list[float]) -> Optional[float]:
    """Win rate (fraction > 0); None if empty."""
    if not rets:
        return None
    return float(np.mean([r > 0 for r in rets]))


def _med(vals: list[Optional[float]]) -> Optional[float]:
    clean = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.median(clean)) if clean else None


def _months_span(fire_dates: list[str]) -> float:
    """Calendar months between earliest and latest fire_date."""
    if not fire_dates:
        return 0.0
    ts = sorted(pd.Timestamp(d) for d in fire_dates)
    delta = ts[-1] - ts[0]
    return delta.days / 30.4375  # average days per month


def _distinct_fire_dates(fire_dates: list[str]) -> int:
    return len(set(fire_dates))


# ------------------------------------------------------------------ NAV -------


def _nav_ladder(
    fires: list[dict],
    grades: list[dict],
    horizon: int = NAV_HOLD_SESSIONS,
) -> tuple[pd.Series, float]:
    """Compute equal-weight 21d-cohort overlapping NAV on excess returns.

    Each fire-date cohort is held for 21 sessions; daily book return =
    mean over active cohorts of their daily excess return for that day.

    Parameters
    ----------
    fires  : Fire rows for this book.
    grades : Grade rows for this book.
    horizon: Session hold length (default 21).

    Returns
    -------
    (nav_series, max_drawdown)
      nav_series    : pd.Series indexed by exec_date (calendar), NAV starting at 1.0
      max_drawdown  : float max peak-to-trough drawdown of nav_series
    """
    # Build dict: (ticker, fire_date) -> {exec_date, daily_rets}
    # We use ret_excess_spy at h=21 as the terminal return; for daily ladder
    # we approximate each day's excess as terminal / 21 (uniform attribution).
    # This is the "1/21-overlap portfolio" described in spec §4: equal-weight
    # 21d-cohort ladder; daily book return = mean over active cohorts.

    # Only ret rows carry ret_excess_spy; exclude path rows explicitly.
    ret_grades = _filter_ret(grades)

    # Group grades by (ticker, fire_date) → ret_excess_spy at horizon=21
    grade_map: dict[tuple, float] = {}
    for g in ret_grades:
        if g.get("horizon") != horizon:
            continue
        ex = g.get("ret_excess_spy")
        if ex is None:
            continue
        k = (g["ticker"], g["fire_date"])
        grade_map[k] = float(ex)

    if not grade_map:
        return pd.Series(dtype=float), 0.0

    # Build cohort list: (exec_date, ret_excess_spy)
    cohorts: list[tuple[pd.Timestamp, float]] = []
    exec_date_map: dict[tuple, pd.Timestamp] = {}
    for g in ret_grades:
        if g.get("horizon") != horizon:
            continue
        k = (g["ticker"], g["fire_date"])
        if k in grade_map:
            try:
                ed = pd.Timestamp(g.get("exec_date") or g.get("fire_date"))
            except Exception:  # noqa: BLE001
                continue
            exec_date_map[k] = ed

    for k, ret in grade_map.items():
        if k in exec_date_map:
            cohorts.append((exec_date_map[k], ret))

    if not cohorts:
        return pd.Series(dtype=float), 0.0

    # Build a daily NAV. Each cohort contributes 1/horizon of its total return per
    # TRADING SESSION over [exec_date, exec_date + horizon - 1 sessions].
    # Use business-day offsets (pd.offsets.BDay) so weekends are excluded and the
    # 21-session hold window matches the spec (21 trading sessions, not 21 calendar days).
    all_dates: set[pd.Timestamp] = set()
    for exec_date, _ in cohorts:
        for d in range(horizon):
            all_dates.add(exec_date + pd.offsets.BDay(d))

    if not all_dates:
        return pd.Series(dtype=float), 0.0

    date_series = pd.Series(0.0, index=sorted(all_dates))

    for exec_date, total_ret in cohorts:
        daily_ret = total_ret / horizon
        for d in range(horizon):
            day = exec_date + pd.offsets.BDay(d)
            if day in date_series.index:
                date_series[day] += daily_ret

    # Divide by number of active cohorts per day to get mean (not sum)
    # Count active cohorts per day
    cohort_count = pd.Series(0, index=date_series.index, dtype=float)
    for exec_date, _ in cohorts:
        for d in range(horizon):
            day = exec_date + pd.offsets.BDay(d)
            if day in cohort_count.index:
                cohort_count[day] += 1

    # Mean daily excess over active cohorts
    active_mask = cohort_count > 0
    mean_daily = pd.Series(0.0, index=date_series.index)
    mean_daily[active_mask] = date_series[active_mask] / cohort_count[active_mask]

    # NAV: cumulative product of (1 + mean_daily_ret)
    nav = (1 + mean_daily).cumprod()

    # Max drawdown
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    return nav, max_dd


# ------------------------------------------------------------------ per-horizon stats ---


def _horizon_stats(
    grades: list[dict],
    horizon: int,
    is_avoid: bool = False,
) -> dict:
    """Compute per-horizon stats from return rows (kind='ret') at a given horizon."""
    # Only ret rows carry ret_abs/ret_excess_spy; path rows at the same horizon
    # carry different fields and must not pollute the return stats.
    h_grades = [
        g for g in grades
        if g.get("horizon") == horizon and g.get("kind") in ("ret", None)
    ]

    rets_abs = [g["ret_abs"] for g in h_grades if g.get("ret_abs") is not None]
    rets_exc = [g["ret_excess_spy"] for g in h_grades if g.get("ret_excess_spy") is not None]
    mfes = [g["mfe"] for g in h_grades if g.get("mfe") is not None]
    maes = [g["mae"] for g in h_grades if g.get("mae") is not None]
    abs_maes = [abs(v) for v in maes]

    wr_abs = _wr(rets_abs)
    wr_exc = _wr(rets_exc)
    med_exc = _med(rets_exc)
    med_mfe = _med(mfes)
    med_abs_mae = _med(abs_maes)

    # Asymmetry = median_MFE / median_|MAE| (null if either null or MAE=0)
    asym = None
    if med_mfe is not None and med_abs_mae:
        asym = round(med_mfe / med_abs_mae, 4)

    result = {
        f"h{horizon}_n": len(h_grades),
        f"h{horizon}_wr_abs": round(wr_abs, 4) if wr_abs is not None else None,
        f"h{horizon}_wr_exc": round(wr_exc, 4) if wr_exc is not None else None,
        f"h{horizon}_med_exc": round(med_exc, 6) if med_exc is not None else None,
        f"h{horizon}_med_mfe": round(med_mfe, 6) if med_mfe is not None else None,
        f"h{horizon}_med_abs_mae": round(med_abs_mae, 6) if med_abs_mae is not None else None,
        f"h{horizon}_asym": asym,
    }

    if is_avoid:
        # Avoid-book: flip sign interpretation — expected negative excess
        # Label fields so UI can present as avoid_accuracy, not buy performance
        result[f"h{horizon}_avoid_accuracy"] = (
            round(1.0 - wr_exc, 4) if wr_exc is not None else None
        )

    return result


# ------------------------------------------------------------------ path stats --


def _path_stats(grades: list[dict], window: int) -> dict:
    """Compute path-row-based stats for a given window (25 or 63).

    Path rows carry mfe/mae/t_mfe/t_mae/mae_before_mfe/sessions_underwater.
    All stats are null-honest when path rows are absent or not yet mature.

    Returns fields prefixed with path{window}_*.
    """
    p_rows = _filter_path(grades, window)
    pfx = f"path{window}"

    mfes = [g["mfe"] for g in p_rows if g.get("mfe") is not None]
    maes = [g["mae"] for g in p_rows if g.get("mae") is not None]
    abs_maes = [abs(v) for v in maes]
    t_mfes = [g["t_mfe"] for g in p_rows if g.get("t_mfe") is not None]
    t_maes = [g["t_mae"] for g in p_rows if g.get("t_mae") is not None]
    mae_firsts = [g["mae_before_mfe"] for g in p_rows if g.get("mae_before_mfe") is not None]
    underwaters = [g["sessions_underwater"] for g in p_rows if g.get("sessions_underwater") is not None]

    med_mfe = _med(mfes)
    med_abs_mae = _med(abs_maes)

    # Asymmetry from path rows: median_MFE / median_|MAE|
    asym = None
    if med_mfe is not None and med_abs_mae:
        asym = round(med_mfe / med_abs_mae, 4)

    pct_mae_first = (
        float(np.mean(mae_firsts)) if mae_firsts else None
    )

    return {
        f"{pfx}_n": len(p_rows),
        f"{pfx}_med_mfe": round(med_mfe, 6) if med_mfe is not None else None,
        f"{pfx}_med_abs_mae": round(med_abs_mae, 6) if med_abs_mae is not None else None,
        f"{pfx}_asym": asym,
        f"{pfx}_med_t_mfe": round(float(np.median(t_mfes)), 2) if t_mfes else None,
        f"{pfx}_med_t_mae": round(float(np.median(t_maes)), 2) if t_maes else None,
        f"{pfx}_pct_mae_first": round(pct_mae_first, 4) if pct_mae_first is not None else None,
        f"{pfx}_med_underwater": round(float(np.median(underwaters)), 2) if underwaters else None,
    }


def _capture_ratio(
    fires: list[dict],
    grades: list[dict],
    entry_horizon: int,
    path_window: int = 25,
) -> Optional[float]:
    """Compute median capture ratio for fires at a given entry horizon.

    Capture ratio = ret_abs_h / mfe_path25 for fires where mfe > 0.
    Joins return rows at entry_horizon with the fire's path-25 row by
    (ticker, fire_date).

    Returns None when insufficient matched pairs exist.
    """
    # Build path-25 map: (ticker, fire_date) → mfe
    path_mfe: dict[tuple, float] = {}
    for g in grades:
        if g.get("kind") == "path" and g.get("horizon") == path_window:
            mfe = g.get("mfe")
            if mfe is not None and mfe > 0:
                path_mfe[(g["ticker"], g["fire_date"])] = float(mfe)

    if not path_mfe:
        return None

    # Build return map: (ticker, fire_date) → ret_abs at entry_horizon
    ret_map: dict[tuple, float] = {}
    for g in grades:
        if g.get("kind") in ("ret", None) and g.get("horizon") == entry_horizon:
            ret_abs = g.get("ret_abs")
            if ret_abs is not None:
                ret_map[(g["ticker"], g["fire_date"])] = float(ret_abs)

    ratios = []
    for key, ret_abs in ret_map.items():
        mfe = path_mfe.get(key)
        if mfe is not None:
            ratios.append(ret_abs / mfe)

    return float(np.median(ratios)) if ratios else None


# ------------------------------------------------------------------ scoreboard ---


def scoreboard(
    engine_id: str,
    fires: list[dict],
    grades: list[dict],
    *,
    horizon_role: str = "entry",
    ruler: str = "21d_spy_excess",
    ctrl_fires: Optional[list[dict]] = None,
    ctrl_grades: Optional[list[dict]] = None,
    universe_base_rate_21d: Optional[float] = None,
    open_fire_dates: Optional[set[str]] = None,
    close_panel: Optional[pd.DataFrame] = None,
    spy_closes: Optional[pd.Series] = None,
    profile=None,
) -> dict:
    """Compute the scoreboard for one book.

    Parameters
    ----------
    engine_id              : Book identifier.
    fires                  : Fire rows for this book (from ledger, keep-first).
    grades                 : Grade rows for this book (from ledger, keep-first).
    horizon_role           : 'entry' | 'hold_thesis'
    ruler                  : Pre-declared ruler for this book family (PL-R3).
                             '21d_spy_excess' (default) — momentum/quality/flagship
                             families; lift computed from h21_med_exc.
                             '21d_abs_reversion_capture_mfe_mae' — washout/reversion
                             family; lift computed from h21_wr_abs and h21_med_abs
                             (absolute reversion-capture), not SPY-excess.
    ctrl_fires             : plab_random_ctrl fire rows (for lift calculation).
    ctrl_grades            : plab_random_ctrl grade rows.
    universe_base_rate_21d : Median 21d excess computed from the close panel across
                             ALL snapshot tickers per fire-date (PL-R5 second
                             independent control; spec §9 follow-up).  Passed as
                             None when no fire-date has matured (honest null) or
                             when the panel is unavailable.
                             NOTE: callers must not conflate this with lift_vs_ctrl
                             (which derives from the 12-name random-ctrl book).
                             lift_vs_universe_base derives from a different,
                             much larger population (the full snapshot universe).
    open_fire_dates        : Set of fire_dates whose horizons are not yet matured
                             (used for n_open; computed from fires/grades if None).
    close_panel            : Optional DataFrame[date_index x ticker] of closes.
                             When provided together with spy_closes (or 'SPY' column
                             present in close_panel), enables timing_lift_21d
                             computation.
    spy_closes             : Optional Series of SPY closes.  May be omitted when
                             'SPY' is a column in close_panel.

    Returns
    -------
    dict with all scoreboard fields.  Includes:
      timing_lift_21d — float | None
          WHEN-skill vs WHICH-skill baseline.  For each matured h21 fire, the
          ticker's own any-day median 21d SPY-excess (all panel start dates with a
          full window, excluding start dates within 21 sessions of exec_date) is
          subtracted from the fire's ret_excess_spy.  timing_lift_21d is the median
          of those per-fire deltas.  Null when close_panel absent or no h21 rows
          have matured.
    """
    _avoid_id = (
        profile.avoid_engine_id if profile is not None else AVOID_ENGINE_ID
    )
    is_lh = (horizon_role == LH_HORIZON_ROLE)
    # is_avoid: primary check = avoid_engine_id (or set of ids on the profile);
    # secondary check = ruler suffix "_avoid_accuracy" (catches books like
    # hklab_knife_avoid that share the inverse grading contract but are not
    # the single profile.avoid_engine_id string — HKPL-R3 / spec §3 book 10).
    _avoid_ids = (
        set(_avoid_id) if isinstance(_avoid_id, (set, frozenset, list, tuple))
        else {_avoid_id}
    )
    is_avoid = (engine_id in _avoid_ids) or ruler.endswith("_avoid_accuracy")
    horizons = LH_HORIZONS if is_lh else ENTRY_HORIZONS

    my_fires = _filter(fires, engine_id)
    my_grades = _filter(grades, engine_id)

    fire_dates = [f.get("fire_date") for f in my_fires if f.get("fire_date")]
    n_fires = len(my_fires)
    n_distinct_dates = _distinct_fire_dates(fire_dates)
    months = _months_span(fire_dates)

    # n_open: fires at the primary horizon (21d for entry; 126d for LH) not yet graded.
    # Only count ret rows (kind='ret' or legacy None) — path rows at the same horizon
    # are a different kind and don't indicate the return has matured.
    primary_h = 21 if not is_lh else 126
    graded_keys = {
        (g["ticker"], g["fire_date"])
        for g in my_grades
        if g.get("horizon") == primary_h
        and g.get("matured")
        and g.get("kind") in ("ret", None)
    }
    n_open = sum(
        1 for f in my_fires
        if (f.get("ticker"), f.get("fire_date")) not in graded_keys
    )

    # Status
    at_floor = (
        n_fires >= FLOOR_N_FIRES
        and months >= FLOOR_MONTHS_SPAN
        and n_distinct_dates >= FLOOR_DISTINCT_FIRE_DATES
    )
    status = "SCOREABLE" if at_floor else "ACCRUING"

    result: dict = {
        "engine_id": engine_id,
        "horizon_role": horizon_role,
        "ruler": ruler,
        "is_avoid": is_avoid,
        "n_fires": n_fires,
        "n_open": n_open,
        "n_distinct_fire_dates": n_distinct_dates,
        "months_span": round(months, 2),
        "status": status,
        "authority": "display_only",
    }

    # LH books: per-horizon medians + ETA only (spec §4)
    if is_lh:
        for h in horizons:
            stats = _horizon_stats(my_grades, h, is_avoid=False)
            result.update(stats)
        # First maturation ETA: earliest fire exec_date + 126 sessions
        # Approximate using calendar days: 126 sessions ≈ 126 * 7/5 calendar days
        eta_dates = []
        for f in my_fires:
            ed = f.get("exec_date") or f.get("fire_date")
            if ed:
                try:
                    eta_dates.append(pd.Timestamp(ed) + pd.DateOffset(days=int(126 * 1.4)))
                except Exception:  # noqa: BLE001
                    pass
        result["first_maturation_eta"] = (
            str(min(eta_dates).date()) if eta_dates else None
        )
        return result

    # Entry books: full scoreboard
    for h in horizons:
        stats = _horizon_stats(my_grades, h, is_avoid=is_avoid)
        result.update(stats)

    # Path-row stats (path25_* and path63_*) — read from kind='path' rows
    for w in (25, 63):
        result.update(_path_stats(my_grades, w))

    # Per-horizon capture ratio (ret_abs_h / path25_mfe, median over fires where mfe>0)
    for h in horizons:
        result[f"h{h}_capture"] = _capture_ratio(my_fires, my_grades, h, path_window=25)

    # NAV ladder (only entry, using h=21 as primary)
    nav, max_dd = _nav_ladder(my_fires, my_grades, horizon=NAV_HOLD_SESSIONS)
    result["nav_max_drawdown"] = round(max_dd, 4)
    if not nav.empty:
        result["nav_final"] = round(float(nav.iloc[-1]), 4)
        result["nav_n_days"] = len(nav)
    else:
        result["nav_final"] = None
        result["nav_n_days"] = 0

    # Lift vs random_ctrl (ctrl_fires may be empty list on first day; check ctrl_grades)
    # PL-R3: ruler-aware primary metric.
    # Momentum/quality/flagship (ruler=21d_spy_excess): lift on SPY-excess (h21_med_exc).
    # Washout/reversion (ruler=21d_abs_reversion_capture_mfe_mae): lift on absolute
    # reversion-capture — wr_abs at h21 vs ctrl wr_abs (not excess), per spec §3/§4 and
    # oracle-reversion convention (#1458).
    _is_reversion_ruler = (ruler == "21d_abs_reversion_capture_mfe_mae")

    lift_vs_ctrl = None
    if ctrl_grades:
        if _is_reversion_ruler:
            # Primary metric: absolute win-rate (fraction of fires with ret_abs > 0)
            ctrl_wr_abs = _wr([
                g.get("ret_abs")
                for g in ctrl_grades
                if g.get("horizon") == 21 and g.get("ret_abs") is not None
            ])
            my_wr_abs = result.get("h21_wr_abs")
            if ctrl_wr_abs is not None and my_wr_abs is not None:
                lift_vs_ctrl = round(my_wr_abs - ctrl_wr_abs, 6)
        else:
            ctrl_med = _med([
                g.get("ret_excess_spy")
                for g in ctrl_grades
                if g.get("horizon") == 21 and g.get("ret_excess_spy") is not None
            ])
            my_med_21 = result.get("h21_med_exc")
            if ctrl_med is not None and my_med_21 is not None:
                lift_vs_ctrl = round(my_med_21 - ctrl_med, 6)
    result["lift_vs_ctrl"] = lift_vs_ctrl

    # Lift vs universe buy-anytime base rate (PL-R5 second independent control).
    # Derives from the close panel across ALL snapshot tickers (not from the 12-name
    # random ctrl) — a genuinely different population.  Null when panel unavailable
    # or no fire-date has matured.
    lift_vs_base = None
    if universe_base_rate_21d is not None:
        if _is_reversion_ruler:
            my_wr_abs = result.get("h21_wr_abs")
            if my_wr_abs is not None:
                lift_vs_base = round(my_wr_abs - universe_base_rate_21d, 6)
        else:
            my_med_21 = result.get("h21_med_exc")
            if my_med_21 is not None:
                lift_vs_base = round(my_med_21 - universe_base_rate_21d, 6)
    result["lift_vs_universe_base"] = lift_vs_base

    # Timing lift (WHEN-skill vs WHICH-skill, PL-R5 / Amendment §A7).
    # Null for LH books (scored by scoreboard returning early above) and when
    # close_panel is absent.  Not applicable to the reversion ruler (absolute
    # capture, not SPY-excess).
    timing_lift: Optional[float] = None
    if (
        not is_lh
        and not _is_reversion_ruler
        and close_panel is not None
        and not close_panel.empty
    ):
        _spy = spy_closes if spy_closes is not None else pd.Series(dtype=float)
        try:
            timing_lift = _timing_lift(
                my_fires,
                my_grades,
                close_panel,
                _spy,
                horizon=NAV_HOLD_SESSIONS,
                exclusion_sessions=NAV_HOLD_SESSIONS,
            )
            if timing_lift is not None:
                timing_lift = round(timing_lift, 6)
        except Exception as exc:  # noqa: BLE001
            log.debug("scoreboard: timing_lift error for %s (%s)", engine_id, exc)
    result["timing_lift_21d"] = timing_lift

    return result


# ------------------------------------------------------------------ timing lift ---


def _timing_lift(
    fires: list[dict],
    grades: list[dict],
    close_panel: pd.DataFrame,
    spy_closes: pd.Series,
    horizon: int = 21,
    exclusion_sessions: int = 21,
) -> Optional[float]:
    """Compute timing_lift_21d for a single book's fires/grades.

    For each matured fire, compute the ticker's OWN baseline = median 21-session
    SPY-excess across ALL panel start dates where the full 21-session window fits,
    EXCLUDING start dates within ``exclusion_sessions`` sessions of the fire's
    exec_date (both before and after, so the fire's own move does not contaminate).

    timing_lift_21d = median over fires of (fire ret_excess_spy − ticker_baseline).

    Vectorized: the full 21-session excess-return matrix is computed ONCE per call
    (all tickers × all valid start dates), then sliced per (ticker, exec_date).

    Parameters
    ----------
    fires            : Fire rows for this book.
    grades           : Grade rows for this book (kind='ret' only).
    close_panel      : DataFrame[date_index x ticker] of closes.  Must include 'SPY'.
    spy_closes       : Series of SPY closes (same index as close_panel).
    horizon          : Session hold length (default 21).
    exclusion_sessions: Start dates within this many sessions of exec_date are
                        excluded from the ticker's baseline (default 21).

    Returns
    -------
    float | None — None when panel absent, SPY absent, or no matured fires.
    """
    if close_panel is None or close_panel.empty:
        return None
    if "SPY" not in close_panel.columns and spy_closes.empty:
        return None

    # Resolve SPY series
    if "SPY" in close_panel.columns:
        spy = close_panel["SPY"].dropna()
    else:
        spy = spy_closes.dropna()

    date_index = close_panel.index
    if not isinstance(date_index, pd.DatetimeIndex):
        date_index = pd.DatetimeIndex(date_index)
    date_index = date_index.sort_values()
    n_dates = len(date_index)

    if n_dates < horizon + 1:
        return None

    # Build matured-fire map: (ticker, fire_date) -> (exec_date_ts, ret_excess_spy)
    grade_map: dict[tuple, tuple] = {}
    ret_grades = _filter_ret(grades)
    for g in ret_grades:
        if g.get("horizon") != horizon:
            continue
        ex = g.get("ret_excess_spy")
        if ex is None:
            continue
        k = (g["ticker"], g["fire_date"])
        if k not in grade_map:
            try:
                ed = pd.Timestamp(g.get("exec_date") or g.get("fire_date"))
            except Exception:  # noqa: BLE001
                continue
            grade_map[k] = (ed, float(ex))

    if not grade_map:
        return None

    # Build (ticker, fire_date) -> exec_date from fires (falls back to grade)
    exec_date_map: dict[tuple, pd.Timestamp] = {}
    for f in fires:
        k = (f.get("ticker"), f.get("fire_date"))
        if k in grade_map:
            ed_raw = f.get("exec_date") or f.get("fire_date")
            try:
                exec_date_map[k] = pd.Timestamp(ed_raw)
            except Exception:  # noqa: BLE001
                exec_date_map[k] = grade_map[k][0]

    # Fill any missing exec_dates from grade rows
    for k, (ed, _) in grade_map.items():
        if k not in exec_date_map:
            exec_date_map[k] = ed

    # Collect unique tickers needed
    needed_tickers = {k[0] for k in grade_map}

    # Precompute SPY returns for all valid start positions (vectorized).
    # spy_ret_arr[i] = (spy[i+horizon] - spy[i]) / spy[i] for i where window fits.
    # valid_mask[i] = True when spy_ret_arr[i] is not NaN and spy[i] > 0.
    spy_arr = spy.reindex(date_index).values.astype(float)  # aligned to date_index
    # Shift: spy_h[i] = spy_arr[i+horizon] for i < n_dates-horizon, else NaN
    spy_h = np.full(n_dates, np.nan)
    spy_h[:n_dates - horizon] = spy_arr[horizon:]
    spy0 = spy_arr.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        spy_ret_arr = np.where(spy0 > 0, (spy_h - spy0) / spy0, np.nan)
    valid_mask = np.isfinite(spy_ret_arr)  # True where both spy[i] and spy[i+h] valid

    # Precompute per-ticker excess arrays (vectorized).
    # ticker_excess[ticker][i] = close_ret[i] - spy_ret[i] where valid.
    ticker_excess: dict[str, np.ndarray] = {}
    for ticker in needed_tickers:
        if ticker not in close_panel.columns:
            continue
        c = close_panel[ticker].reindex(date_index).values.astype(float)
        c_h = np.full(n_dates, np.nan)
        c_h[:n_dates - horizon] = c[horizon:]
        with np.errstate(divide="ignore", invalid="ignore"):
            c_ret = np.where(c > 0, (c_h - c) / c, np.nan)
        exc = np.where(valid_mask, c_ret - spy_ret_arr, np.nan)
        ticker_excess[ticker] = exc

    # Compute timing lift per matured fire.
    # For each fire: exclude start positions within exclusion_sessions of exec_pos;
    # baseline = median of remaining valid excess values for that ticker.
    positions = np.arange(n_dates, dtype=int)
    lifts: list[float] = []
    for k in grade_map:
        ticker = k[0]
        if ticker not in ticker_excess:
            continue
        exc_arr = ticker_excess[ticker]
        exec_date_ts = exec_date_map[k]
        fire_ret = grade_map[k][1]

        # exec position in date_index
        exec_pos = int(date_index.searchsorted(exec_date_ts, side="left"))
        if exec_pos >= n_dates:
            exec_pos = n_dates - 1

        # Exclusion mask: keep positions where distance from exec_pos >= exclusion_sessions
        keep = (np.abs(positions - exec_pos) >= exclusion_sessions) & np.isfinite(exc_arr)
        baseline_vals = exc_arr[keep]

        if len(baseline_vals) == 0:
            continue

        baseline = float(np.median(baseline_vals))
        lifts.append(fire_ret - baseline)

    return float(np.median(lifts)) if lifts else None


# ------------------------------------------------------------------ base rate ---


def universe_base_rate(
    random_ctrl_grades: list[dict],
    horizon: int = 21,
) -> Optional[float]:
    """Median 21d excess from plab_random_ctrl (random-ctrl proxy).

    This function returns the RANDOM-CTRL median, not the full-universe panel
    base rate.  It is retained for spec continuity and may be used as a diagnostic
    proxy, but it is NOT the same as universe_base_rate_21d passed to scoreboard().

    universe_base_rate_21d (the PL-R5 second independent control) is computed from
    the close panel across ALL snapshot tickers per fire-date in build_pick_lab.py
    and passed directly to all_scoreboards() / scoreboard().  The two controls
    derive from different populations:
      - lift_vs_ctrl         : book median vs 12-name random-ctrl median
      - lift_vs_universe_base: book median vs full-universe panel median (per fire-date)

    NOTE: do NOT pass the value returned here as universe_base_rate_21d in
    all_scoreboards — that would make the two lift columns derive from the same
    12-name population, misrepresenting independent yardsticks.

    Parameters
    ----------
    random_ctrl_grades : Grade rows from plab_random_ctrl book.
    horizon            : Horizon to use (default 21d).

    Returns
    -------
    Median ret_excess_spy or None if insufficient data.
    """
    rets = [
        g["ret_excess_spy"]
        for g in random_ctrl_grades
        if g.get("horizon") == horizon and g.get("ret_excess_spy") is not None
    ]
    return _med(rets)


# ------------------------------------------------------------------ all books --


def all_scoreboards(
    fires: list[dict],
    grades: list[dict],
    horizon_role_map: dict[str, str],
    *,
    ruler_map: Optional[dict[str, str]] = None,
    ctrl_fires: Optional[list[dict]] = None,
    ctrl_grades: Optional[list[dict]] = None,
    universe_base_rate_21d: Optional[float] = None,
    close_panel: Optional[pd.DataFrame] = None,
    spy_closes: Optional[pd.Series] = None,
    profile=None,
) -> list[dict]:
    """Compute scoreboards for all books.

    Parameters
    ----------
    fires                  : All fire rows (all books).
    grades                 : All grade rows (all books).
    horizon_role_map       : {engine_id: horizon_role} from the registry.
    ruler_map              : {engine_id: ruler} — pre-declared ruler per book (PL-R3).
                             Defaults to '21d_spy_excess' for any book not in the map.
    ctrl_fires             : Fires from plab_random_ctrl (or cnlab_random_ctrl for CN).
    ctrl_grades            : Grades from plab_random_ctrl (or cnlab_random_ctrl for CN).
    universe_base_rate_21d : Median 21d SPY-excess across ALL snapshot tickers per
                             fire-date (PL-R5 second independent control; computed by
                             build_pick_lab and passed here).  Null when no fire-date
                             has matured or close panel is unavailable.
    close_panel            : Optional DataFrame[date_index x ticker] closes.  When
                             provided, enables timing_lift_21d on each book's
                             scoreboard.
    spy_closes             : Optional SPY close series.  May be omitted when 'SPY'
                             is a column in close_panel.
    profile                : optional MarketProfile; when supplied, uses
                             profile.random_ctrl_id as the control book id.

    Returns
    -------
    List of scoreboard dicts, one per engine_id in horizon_role_map.
    """
    _ctrl_id = (
        profile.random_ctrl_id if profile is not None else "plab_random_ctrl"
    )
    ctrl_g = ctrl_grades or _filter(grades, _ctrl_id)
    ctrl_f = ctrl_fires or _filter(fires, _ctrl_id)
    ruler_map = ruler_map or {}

    _spy = spy_closes if spy_closes is not None else pd.Series(dtype=float)

    boards = []
    for engine_id, role in horizon_role_map.items():
        book_ruler = ruler_map.get(engine_id, "21d_spy_excess")
        sb = scoreboard(
            engine_id=engine_id,
            fires=fires,
            grades=grades,
            horizon_role=role,
            ruler=book_ruler,
            ctrl_fires=ctrl_f,
            ctrl_grades=ctrl_g,
            universe_base_rate_21d=universe_base_rate_21d,
            close_panel=close_panel,
            spy_closes=_spy if close_panel is not None else None,
        )
        boards.append(sb)

    return boards
