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

    # Group grades by (ticker, fire_date) → ret_excess_spy at horizon=21
    grade_map: dict[tuple, float] = {}
    for g in grades:
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
    for g in grades:
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
    """Compute per-horizon stats from grade rows at a given horizon."""
    h_grades = [g for g in grades if g.get("horizon") == horizon]

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
    universe_base_rate_21d : Median 21d excess from plab_random_ctrl (the honest
                             proxy for buy-anytime base rate; PL-R5).  Passed as
                             None when no independent universe metric is available
                             — callers must not conflate it with lift_vs_ctrl
                             (both derive from the same random-ctrl distribution).
                             When caller passes the same value as ctrl_med, the
                             two lift columns will be numerically equal; callers
                             should pass None rather than duplicate the number.
    open_fire_dates        : Set of fire_dates whose horizons are not yet matured
                             (used for n_open; computed from fires/grades if None).

    Returns
    -------
    dict with all scoreboard fields.
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

    # n_open: fires at the primary horizon (21d for entry; 126d for LH) not yet graded
    primary_h = 21 if not is_lh else 126
    graded_keys = {
        (g["ticker"], g["fire_date"])
        for g in my_grades
        if g.get("horizon") == primary_h and g.get("matured")
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
    # Null until a genuinely independent universe-wide base rate is available —
    # passing ctrl_med here would make this column identical to lift_vs_ctrl.
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

    return result


# ------------------------------------------------------------------ base rate ---


def universe_base_rate(
    random_ctrl_grades: list[dict],
    horizon: int = 21,
) -> Optional[float]:
    """Median 21d excess from plab_random_ctrl.

    PL-R5 requires two independent controls: plab_random_ctrl AND the universe
    buy-anytime base rate.  Until a genuinely independent universe-wide base rate
    (graded over ALL snapshot tickers) is available, this function returns the
    random-ctrl proxy only.

    NOTE: do NOT pass this value as both ctrl_med and universe_base_rate_21d in
    all_scoreboards — doing so makes lift_vs_ctrl and lift_vs_universe_base
    numerically identical, misrepresenting two independent yardsticks.
    all_scoreboards passes universe_base_rate_21d=None when a true independent
    base rate is not yet computed.

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
    profile=None,
) -> list[dict]:
    """Compute scoreboards for all books.

    Parameters
    ----------
    fires            : All fire rows (all books).
    grades           : All grade rows (all books).
    horizon_role_map : {engine_id: horizon_role} from the registry.
    ruler_map        : {engine_id: ruler} — pre-declared ruler per book (PL-R3).
                       Defaults to '21d_spy_excess' for any book not in the map.
    ctrl_fires       : Fires from plab_random_ctrl (or cnlab_random_ctrl for CN).
    ctrl_grades      : Grades from plab_random_ctrl (or cnlab_random_ctrl for CN).
    profile          : optional MarketProfile; when supplied, uses profile.random_ctrl_id
                       as the control book id.  Omitting preserves US behaviour.

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

    # PL-R5 requires lift over BOTH plab_random_ctrl AND the universe buy-anytime
    # base rate as two INDEPENDENT controls.  Until a genuinely independent base
    # rate (graded over ALL snapshot tickers, not just the 12-name random book) is
    # available, universe_base_rate_21d is passed as None so lift_vs_universe_base
    # is honestly null rather than duplicating lift_vs_ctrl.  When an independent
    # universe_base_rate_21d is later wired in, pass it here.
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
            universe_base_rate_21d=None,  # independent base rate not yet available
        )
        boards.append(sb)

    return boards
