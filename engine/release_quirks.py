"""MRI PR-I — Release quirk flags (MRI-R20) + W11-E Track S additions (MRI-R38).

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

W11-E Track S additions (MRI-R38):
  active_strike             — BLS work-stoppages: active stoppage ≥25k workers
                              overlapping the NFP reference week. Reads from
                              data/bls_work_stoppages/stoppages.parquet (fail-open:
                              falls back to collectors/bls_work_stoppages.SEED_ROWS).
  nfp_preliminary_benchmark — September BLS preliminary benchmark magnitude >|100k|
                              → flag the following January print.  Reads
                              data/release_forecast/quirk_calendars/nfp_preliminary_benchmarks.yml;
                              seeded with known episodes through 2024.
  government_shutdown       — Appropriations gap / government shutdown overlapping
                              the NFP reference week or CPI survey window.  Reads
                              data/release_forecast/quirk_calendars/government_shutdowns.yml.
  census_hiring             — Decennial census temporary worker peak / drawdown months.
                              Currently inactive (next decennial: 2030).  Implemented
                              as a pure-calendar check on known decennial years.
  hurricane_landfall        — Hurricane landfall within 30 calendar days before the
                              NFP reference week.  Reads
                              data/release_forecast/quirk_calendars/hurricane_landfalls.yml.
                              Live NHC collector is comeback scope.

Citations:
  BLS CPI weight / seasonal: https://www.bls.gov/cpi/additional-resources/chained-cpi-methodology.htm
                               (annual weight update each January release)
  BLS health-insurance:       https://www.bls.gov/opub/mlr/2023/article/incorporating-new-estimates-into-the-cpi.htm
                               Semiannual update: Oct (first landing) and Apr prints since Oct 2023.
  BLS CES benchmark:          https://www.bls.gov/ces/publications/benchmark.htm
                               (annual benchmark revision, usually released Feb, covering January data)
  BLS population controls:    https://www.bls.gov/cps/documentation.htm#pop-controls
                               (CPS population controls updated each January)
  BLS Work Stoppages:         https://www.bls.gov/wsp/
  NOAA NHC:                   https://www.nhc.noaa.gov/
  Decennial census:           https://www.census.gov/programs-surveys/decennial-census.html
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
    # --- W11-E Track S additions ---
    "active_strike": {
        "en": "Active work stoppage: major strike (≥25k workers) overlaps NFP reference week (BLS Work Stoppages listing)",
        "zh": "罢工影响：重大劳资纠纷（≥2.5万人）与NFP参考周重叠（BLS停工记录）",
        "cite": "https://www.bls.gov/wsp/",
    },
    "nfp_preliminary_benchmark": {
        "en": "BLS September preliminary benchmark revision >|100k|: January NFP will include large CES revision",
        "zh": "BLS 9月基准修订初步估计>|10万|：1月NFP将包含较大CES年度修订",
        "cite": "https://www.bls.gov/ces/publications/benchmark.htm",
    },
    "government_shutdown": {
        "en": "Government shutdown / appropriations gap may disrupt BLS data collection or publication schedule",
        "zh": "政府停摆/拨款中断可能干扰BLS数据采集或发布时间表",
        "cite": "https://www.bls.gov/",
    },
    "census_hiring": {
        "en": "Decennial census hiring cycle: temporary government workers inflate/deflate government payrolls",
        "zh": "十年人口普查雇用周期：临时政府雇员影响政府就业人数",
        "cite": "https://www.census.gov/programs-surveys/decennial-census.html",
    },
    "hurricane_landfall": {
        "en": "Hurricane landfall within 30 days before NFP reference week may cause displacement / missed workdays",
        "zh": "NFP参考周前30日内飓风登陆，可能导致工人转移和工作日损失",
        "cite": "https://www.nhc.noaa.gov/",
    },
}


# ---------------------------------------------------------------------------
# Repo-root discovery
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Best-effort repo-root from this file's location."""
    return Path(__file__).resolve().parents[1]


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
# W11-E Track S helpers
# ---------------------------------------------------------------------------

_WORK_STOPPAGE_MIN_WORKERS: int = 25_000
# ≤30 calendar days before the NFP reference week's Saturday (start of window)
_HURRICANE_LOOKBACK_DAYS: int = 30
# Decennial census years (active hiring months: Apr–Jun; drawdown: Jul–Sep)
_DECENNIAL_YEARS: set[int] = {1990, 2000, 2010, 2020, 2030, 2040}
_CENSUS_ACTIVE_MONTHS: set[int] = {4, 5, 6}    # peak hiring
_CENSUS_DRAWDOWN_MONTHS: set[int] = {7, 8, 9}  # drawdown


def _load_yaml(path: Path) -> Any:
    """Load YAML file; return None on failure (fail-open)."""
    try:
        import yaml  # type: ignore[import-untyped]
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as exc:
        log.warning("release_quirks: could not load YAML %s: %s", path, exc)
        return None


def _check_active_strike(ref_month: date, root: Path | None = None) -> bool:
    """Return True when an active major work stoppage (≥25k workers) overlaps
    the NFP reference week for ref_month.

    Logic:
      - NFP reference week = Sun through Sat ending on _nfp_reference_saturday(ref_month)
      - A stoppage overlaps if: start_date <= ref_week_end AND (end_date is NaT OR end_date >= ref_week_start)
      - workers >= WORK_STOPPAGE_MIN_WORKERS

    Reads from data/bls_work_stoppages/stoppages.parquet via
    collectors/bls_work_stoppages.load_stoppages() (fail-open: uses SEED_ROWS
    if parquet absent).
    """
    try:
        import sys
        if root is not None:
            _r = str(root)
            if _r not in sys.path:
                sys.path.insert(0, _r)

        from collectors.bls_work_stoppages import load_stoppages  # type: ignore[import]
        df = load_stoppages(root=root or _repo_root())
        if df.empty:
            return False

        import pandas as pd

        ref_sat = _nfp_reference_saturday(ref_month)
        ref_sun = ref_sat - timedelta(days=6)

        # Normalise dates
        df = df.copy()
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date
        df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce").dt.date
        df["workers"] = pd.to_numeric(df.get("workers", 0), errors="coerce").fillna(0)

        large = df[df["workers"] >= _WORK_STOPPAGE_MIN_WORKERS]

        for _, row in large.iterrows():
            start = row["start_date"]
            end = row["end_date"]
            if start is None or (hasattr(start, '__class__') and str(start) == 'NaT'):
                continue
            # Convert pandas NaT/None to None for comparison
            try:
                import math
                if end is not None and hasattr(end, '__class__') and not isinstance(end, date):
                    end = None
                if isinstance(start, date) and start != date(1900, 1, 1):
                    # Overlap: start <= ref_sat AND (end is None OR end >= ref_sun)
                    if start <= ref_sat:
                        if end is None or end >= ref_sun:
                            return True
            except Exception:
                continue

        return False
    except Exception as exc:
        log.warning("release_quirks active_strike check failed: %s", exc)
        return False


def _check_preliminary_benchmark(ref_month: date, root: Path | None = None) -> bool:
    """Return True when the September BLS preliminary benchmark for the year
    preceding ref_month's January has magnitude >|100k|.

    The preliminary is published in October; the flag fires for the following
    January NFP print.  Reads nfp_preliminary_benchmarks.yml.
    """
    if ref_month.month != 1:
        return False  # only relevant for January prints

    if root is None:
        root = _repo_root()
    yml_path = root / "data" / "release_forecast" / "quirk_calendars" / "nfp_preliminary_benchmarks.yml"
    data = _load_yaml(yml_path)
    if not data:
        return False

    # The preliminary published in October of the prior year flags the January print
    # Example: preliminary_month="2022-10" → flags January 2023 NFP
    target_pub_year = ref_month.year - 1
    target_pub_month = f"{target_pub_year}-10"

    for entry in data.get("preliminary_benchmarks", []):
        pub = str(entry.get("published_month", ""))
        if pub == target_pub_month:
            est = entry.get("preliminary_estimate", 0)
            try:
                # Values stored in thousands (e.g., -818 means 818k jobs).
                # Threshold: |estimate| > 100 (thousands) = 100k jobs.
                return abs(int(est)) > 100
            except (TypeError, ValueError):
                return False
    return False


def _check_government_shutdown(ref_month: date, root: Path | None = None) -> bool:
    """Return True when a government shutdown overlaps the NFP reference week
    or the CPI survey month (calendar match from YAML).

    A shutdown overlaps if:
      shutdown.start <= ref_week_sat AND (shutdown.end is None OR shutdown.end >= ref_month_first_day)
    """
    if root is None:
        root = _repo_root()
    yml_path = root / "data" / "release_forecast" / "quirk_calendars" / "government_shutdowns.yml"
    data = _load_yaml(yml_path)
    if not data:
        return False

    ref_month_start = date(ref_month.year, ref_month.month, 1)
    ref_sat = _nfp_reference_saturday(ref_month)

    for entry in data.get("shutdowns", []):
        try:
            start_str = entry.get("start", "")
            end_str = entry.get("end")
            if not start_str:
                continue
            shutdown_start = date.fromisoformat(str(start_str))
            shutdown_end: date | None = date.fromisoformat(str(end_str)) if end_str else None

            # Overlap with NFP reference week or month
            if shutdown_start <= ref_sat:
                if shutdown_end is None or shutdown_end >= ref_month_start:
                    return True
        except Exception as exc:
            log.debug("Shutdown entry parse error: %s", exc)
            continue

    return False


def _check_census_hiring(ref_month: date) -> bool:
    """Return True when ref_month falls in a decennial census hiring or
    drawdown window.

    Decennial census: 1990, 2000, 2010, 2020, 2030, 2040 ...
    Active hiring: Apr, May, Jun (of decennial year)
    Drawdown: Jul, Aug, Sep (of decennial year)

    Currently inactive for 2026 — next relevant window is 2030.
    """
    if ref_month.year not in _DECENNIAL_YEARS:
        return False
    return ref_month.month in _CENSUS_ACTIVE_MONTHS or ref_month.month in _CENSUS_DRAWDOWN_MONTHS


def _check_hurricane_landfall(ref_month: date, root: Path | None = None) -> tuple[bool, str]:
    """Return (True, storm_name) when a hurricane made landfall within 30 days
    before the NFP reference week for ref_month.

    Returns (False, '') if no match.
    Reads hurricane_landfalls.yml; uses nfp_ref_month field for fast lookup.
    """
    if root is None:
        root = _repo_root()
    yml_path = root / "data" / "release_forecast" / "quirk_calendars" / "hurricane_landfalls.yml"
    data = _load_yaml(yml_path)
    if not data:
        return False, ""

    ref_month_str = f"{ref_month.year}-{ref_month.month:02d}"
    ref_sat = _nfp_reference_saturday(ref_month)
    window_start = ref_sat - timedelta(days=_HURRICANE_LOOKBACK_DAYS)

    for entry in data.get("landfalls", []):
        # Fast path: check nfp_ref_month field if present
        nfp_ref = entry.get("nfp_ref_month", "")
        if nfp_ref and nfp_ref != ref_month_str:
            continue

        try:
            landfall_date = date.fromisoformat(str(entry.get("landfall_date", "")))
        except (ValueError, TypeError):
            continue

        if window_start <= landfall_date <= ref_sat:
            return True, entry.get("name", "Hurricane")

    return False, ""


# ---------------------------------------------------------------------------
# Public API: compute_quirk_flags
# ---------------------------------------------------------------------------

def compute_quirk_flags(
    release_type: str,
    period_str: str,
    root: Path | str | None = None,
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
    root : Path or str or None
        Repository root for loading YAML/parquet data.  Defaults to the parent
        of the engine/ directory (auto-detected from this file's location).

    Returns
    -------
    list[dict]
        Each dict has keys: code, en, zh, cite
        Empty list if no quirks apply or inputs are malformed.

    Notes
    -----
    Flags are PURE ANNOTATIONS — they never alter point estimates, intervals,
    or skew (MRI-R20 enforcement).  All logic is deterministic calendar math
    or deterministic reads of seeded reference data; no LLM-originated values.
    """
    if root is not None:
        root = Path(root)

    flags: list[dict[str, str]] = []

    def _add(code: str, **overrides: str) -> None:
        meta = _FLAG_META[code]
        entry = {
            "code": code,
            "en": meta["en"],
            "zh": meta["zh"],
            "cite": meta["cite"],
        }
        entry.update(overrides)
        flags.append(entry)

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

        # government_shutdown: check if shutdown overlaps CPI survey month
        if _check_government_shutdown(period_month, root=root):
            _add("government_shutdown")

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

        # active_strike: work stoppage overlapping NFP reference week
        if _check_active_strike(ref_month, root=root):
            _add("active_strike")

        # nfp_preliminary_benchmark: large September preliminary → flag January
        if _check_preliminary_benchmark(ref_month, root=root):
            _add("nfp_preliminary_benchmark")

        # government_shutdown: check if shutdown overlaps NFP reference week month
        if _check_government_shutdown(ref_month, root=root):
            _add("government_shutdown")

        # census_hiring: decennial census active hiring / drawdown
        if _check_census_hiring(ref_month):
            _add("census_hiring")

        # hurricane_landfall: landfall within 30 days before reference week
        hit, storm_name = _check_hurricane_landfall(ref_month, root=root)
        if hit:
            _add(
                "hurricane_landfall",
                en=f"Hurricane landfall within 30 days before NFP reference week: {storm_name} — may cause displacement / missed workdays",
                zh=f"NFP参考周前30日内飓风登陆：{storm_name} — 可能导致工人转移和工作日损失",
            )

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
