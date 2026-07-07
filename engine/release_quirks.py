"""MRI PR-I — Release quirk flags (MRI-R20).

Deterministic calendar-fact flags for upcoming macro releases.  Each flag is a
pure annotation {code, en, zh, cite}; flags NEVER alter point, intervals, or
skew — enforced by construction (this module emits metadata only).

Flags implemented:
  cpi_weight_update        — CPI January print (published mid-Feb): annual
                             BLS expenditure-weight update + seasonal-factor revision.
  cpi_health_insurance_reset — CPI months when BLS's semiannual health-insurance
                             retained-earnings update lands (Apr and Oct prints
                             since Oct 2023).
  nfp_benchmark_revision   — NFP January print (published early Feb): CES annual
                             benchmark revision + CPS population controls.
  nfp_five_week_gap        — months where the gap between consecutive NFP survey
                             reference weeks (week containing the 12th) is 5 weeks
                             instead of 4 (pure calendar computation).
  claims_holiday_week      — claims week whose period end-date falls within 3
                             calendar days of New Year's Day, July 4, Thanksgiving
                             (4th Thursday of November), or Christmas.

Citations:
  BLS CPI weight / seasonal: https://www.bls.gov/cpi/additional-resources/chained-cpi-methodology.htm
                               (annual weight update each January release)
  BLS health-insurance:       https://www.bls.gov/opub/mlr/2023/article/incorporating-new-estimates-into-the-cpi.htm
                               Semiannual update: Oct (first landing) and Apr prints since Oct 2023.
  BLS CES benchmark:          https://www.bls.gov/ces/publications/benchmark.htm
                               (annual benchmark revision, usually released Feb, covering January data)
  BLS population controls:    https://www.bls.gov/cps/documentation.htm#pop-controls
                               (CPS population controls updated each January)
"""
from __future__ import annotations

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Flag definitions (code -> {en, zh, cite})
# ---------------------------------------------------------------------------

_FLAG_META: dict[str, dict[str, str]] = {
    "cpi_weight_update": {
        "en": "January CPI: BLS annual expenditure-weight update + seasonal-factor revision",
        "zh": "1月CPI：BLS年度支出权重更新 + 季节性调整修订",
        "cite": "https://www.bls.gov/cpi/methods/weight-update-faqs.htm",
    },
    "cpi_health_insurance_reset": {
        "en": "CPI health-insurance retained-earnings update (BLS semiannual, Apr + Oct prints since Oct 2023)",
        "zh": "CPI医疗保险留存收益更新（BLS半年度，2023年10月起适用于4月和10月数据）",
        "cite": "https://www.bls.gov/opub/mlr/2023/article/incorporating-new-estimates-into-the-cpi.htm",
    },
    "nfp_benchmark_revision": {
        "en": "January NFP: CES annual benchmark revision + CPS population controls update",
        "zh": "1月NFP：CES年度基准修订 + CPS人口控制更新",
        "cite": "https://www.bls.gov/ces/publications/benchmark.htm",
    },
    "nfp_five_week_gap": {
        "en": "5-week survey gap: 5 weeks between consecutive NFP reference weeks (week containing the 12th)",
        "zh": "5周调查间隔：相邻两次NFP参考周（含12日的那周）间隔5周而非4周",
        "cite": "BLS CES survey reference week definition (week containing the 12th of the month)",
    },
    "claims_holiday_week": {
        "en": "Holiday week: claims period near New Year's, July 4, Thanksgiving, or Christmas",
        "zh": "假日周：申报失业金数据接近元旦、7月4日、感恩节或圣诞节",
        "cite": "BLS initial claims — holiday-week adjustment note (DOL ETA 5159)",
    },
}


# ---------------------------------------------------------------------------
# NFP survey reference week: week containing the 12th of ref_month
# ---------------------------------------------------------------------------

def _nfp_reference_saturday(ref_month: date) -> date:
    """Return the Saturday ending the NFP survey reference week for ref_month.

    The BLS survey reference week is the week (Sun-Sat) that contains the 12th.
    We return the Saturday ending that week.
    """
    the_12th = date(ref_month.year, ref_month.month, 12)
    # weekday(): Mon=0 ... Sun=6; Saturday=5
    # Days to next Saturday (or today if already Saturday)
    days_to_sat = (5 - the_12th.weekday()) % 7
    return the_12th + timedelta(days=days_to_sat)


def _nfp_five_week_gap(ref_month: date) -> bool:
    """Return True when the gap from the prior month's NFP reference Saturday to
    this month's is 5 weeks (35 days) instead of the typical 4 weeks (28 days).

    Pure calendar computation.  The gap is 5 weeks for the ref_month when the
    distance between consecutive reference Saturdays is 35 days.
    """
    prior_month_first = (date(ref_month.year, ref_month.month, 1) - timedelta(days=1))
    prior_month = date(prior_month_first.year, prior_month_first.month, 1)
    sat_cur = _nfp_reference_saturday(ref_month)
    sat_prior = _nfp_reference_saturday(prior_month)
    gap_days = (sat_cur - sat_prior).days
    return gap_days == 35


# ---------------------------------------------------------------------------
# Thanksgiving: 4th Thursday of November
# ---------------------------------------------------------------------------

def _thanksgiving(year: int) -> date:
    """Return Thanksgiving date (4th Thursday of November) for the given year."""
    # Find first Thursday of November
    nov1 = date(year, 11, 1)
    days_to_thu = (3 - nov1.weekday()) % 7  # Thursday = weekday 3
    first_thu = nov1 + timedelta(days=days_to_thu)
    return first_thu + timedelta(weeks=3)  # 4th Thursday = first + 3 weeks


# ---------------------------------------------------------------------------
# Claims holiday week
# Holidays that disrupt the weekly initial-claims filing pattern:
#   New Year's Day: Jan 1
#   Independence Day: Jul 4
#   Thanksgiving: 4th Thursday of November
#   Christmas: Dec 25
#
# A claims week is "holiday" when the week-ending date (Saturday) falls within
# 3 calendar days of any of the above (i.e. the holiday is Mon-Tue of that week
# or Fri-Sat of the prior week, both of which depress filing counts).
# We use a ±3 day window as a simple empirical rule; the exact impact depends
# on the day-of-week the holiday lands.
# ---------------------------------------------------------------------------

def _claims_is_holiday_week(period_end: date) -> bool:
    """Return True when the claims week-ending date (Saturday) is within 3
    calendar days of a major US federal holiday that distorts initial-claims.

    period_end: the Saturday (week-ending date) for the claims observation.
    """
    year = period_end.year

    holidays: list[date] = [
        date(year, 1, 1),                # New Year's Day
        date(year, 7, 4),                # Independence Day
        _thanksgiving(year),             # Thanksgiving
        date(year, 12, 25),              # Christmas
    ]
    # Also check prior/next year for edge cases near Jan 1 and Dec 25
    holidays += [
        date(year - 1, 12, 25),
        date(year + 1, 1, 1),
    ]

    for holiday in holidays:
        if abs((period_end - holiday).days) <= 3:
            return True
    return False


# ---------------------------------------------------------------------------
# Public API: compute_quirk_flags
# ---------------------------------------------------------------------------

def compute_quirk_flags(
    release_type: str,
    period_str: str,
) -> list[dict[str, str]]:
    """Return a list of quirk flag dicts for the given (release_type, period_str).

    Parameters
    ----------
    release_type : str
        One of: 'cpi_headline', 'cpi_core', 'nfp', 'claims'
    period_str : str
        For monthly releases: 'YYYY-MM' (the reference period month).
        For claims: 'YYYY-MM-DD' (the Thursday release date / period end is
        derived as Thu - 5 days = preceding Saturday, same as ALFRED convention).

    Returns
    -------
    list[dict]
        Each dict has keys: code, en, zh, cite
        Empty list if no quirks apply or inputs are malformed.

    Notes
    -----
    Flags are PURE ANNOTATIONS — they never alter point estimates, intervals,
    or skew (MRI-R20 enforcement).  All logic is deterministic calendar math;
    no external data is read.
    """
    flags: list[dict[str, str]] = []

    def _add(code: str) -> None:
        meta = _FLAG_META[code]
        flags.append({
            "code": code,
            "en": meta["en"],
            "zh": meta["zh"],
            "cite": meta["cite"],
        })

    # --- CPI family ---
    if release_type in ("cpi_headline", "cpi_core"):
        try:
            period_month = date.fromisoformat(period_str + "-01")
        except (ValueError, TypeError):
            return flags

        # cpi_weight_update: January print (reference period = January)
        if period_month.month == 1:
            _add("cpi_weight_update")

        # cpi_health_insurance_reset: April and October prints (since Oct 2023)
        # BLS semiannual health-insurance retained-earnings update first landed
        # in the Oct 2023 CPI print; cadence is Apr and Oct thereafter.
        # Cite: https://www.bls.gov/opub/mlr/2023/article/incorporating-new-estimates-into-the-cpi.htm
        if period_month.month in (4, 10) and period_month >= date(2023, 10, 1):
            _add("cpi_health_insurance_reset")

    # --- NFP ---
    elif release_type == "nfp":
        try:
            ref_month = date.fromisoformat(period_str + "-01")
        except (ValueError, TypeError):
            return flags

        # nfp_benchmark_revision: January NFP print (reference period = January)
        if ref_month.month == 1:
            _add("nfp_benchmark_revision")

        # nfp_five_week_gap: pure calendar check
        if _nfp_five_week_gap(ref_month):
            _add("nfp_five_week_gap")

    # --- Claims ---
    elif release_type == "claims":
        # period_str = Thursday release date (YYYY-MM-DD); period_end = Thu - 5 days
        # (preceding Saturday) — same ALFRED convention as _get_initial_print.
        try:
            thursday = date.fromisoformat(period_str)
        except (ValueError, TypeError):
            return flags
        period_end = thursday - timedelta(days=5)  # preceding Saturday

        if _claims_is_holiday_week(period_end):
            _add("claims_holiday_week")

    return flags
