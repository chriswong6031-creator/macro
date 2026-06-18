"""Hong Kong high-impact macro / policy calendar — DISPLAY-ONLY · CONTEXT-ONLY · LEAF.

A pure date-arithmetic engine telling the user which scheduled events that move the
Hang Seng are imminent. NO data fetch — only the *release cadence* is encoded. HK is
driven by three planes, so the calendar merges them:
  • HK-native (Census & Statistics Dept / HKMA): HK CPI, GDP, retail sales, external
    trade, unemployment, the S&P Global HK PMI, and the HKMA base rate.
  • US (the peg + global risk): FOMC, US CPI, US payrolls (NFP). HK rates shadow the
    Fed via the peg and HK trades at ~2x the Mainland's global beta.
  • China (HSI earnings are ~75% China-driven): the high-impact Mainland prints, re-
    exported from engine.china_event_calendar.

It is the HK sibling of engine.china_event_calendar and replicates its shape:
date-arithmetic core, [asof, asof+horizon] window filter, `high_impact_strip()` and
`imminent_line()`. Each event carries a `region` (HK/US/CN) for the chip.

DISCIPLINE (enforced): LEAF module — nothing in any scoring path imports it; it must
NEVER feed engine.hk_axes / hk_regime / hk_playbook. There is deliberately NO event-
risk score / dampener; `importance` is a DISPLAY tier only. Every public function
returns plain-Python data and NEVER raises into the build.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

# reuse the China calendar's pure date-arithmetic helpers (same package)
from engine.china_event_calendar import (last_day_of_month, next_business_day_onward,
                                         nth_business_day, _months_in_window)
from engine.china_event_calendar import high_impact_strip as _cn_high_impact

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# per-type display metadata. importance = DISPLAY tier only. region = HK/US/CN.
# --------------------------------------------------------------------------- #
_META: dict[str, dict] = {
    # --- Hong Kong (Census & Statistics Dept / HKMA) ---
    "HK_PMI":    {"importance": "med",  "region": "HK", "label_en": "S&P Global HK PMI",        "label_zh": "标普全球香港 PMI",        "category": "activity"},
    "HK_CPI":    {"importance": "high", "region": "HK", "label_en": "HK CPI (composite)",       "label_zh": "香港 CPI（综合）",         "category": "inflation"},
    "HK_GDP":    {"importance": "high", "region": "HK", "label_en": "HK GDP",                   "label_zh": "香港 GDP",                  "category": "growth"},
    "HK_TRADE":  {"importance": "med",  "region": "HK", "label_en": "HK external trade",        "label_zh": "香港对外商品贸易",          "category": "trade"},
    "HK_RETAIL": {"importance": "med",  "region": "HK", "label_en": "HK retail sales",          "label_zh": "香港零售业销货",            "category": "activity"},
    "HK_UNEMP":  {"importance": "med",  "region": "HK", "label_en": "HK unemployment",          "label_zh": "香港失业率",                "category": "activity"},
    "HKMA_RATE": {"importance": "high", "region": "HK", "label_en": "HKMA base rate (post-FOMC)","label_zh": "金管局基本利率（FOMC 次日）","category": "policy"},
    # --- United States (the peg + global risk) ---
    "FOMC":      {"importance": "high", "region": "US", "label_en": "US FOMC decision",         "label_zh": "美联储 FOMC 决议",          "category": "policy"},
    "US_CPI":    {"importance": "high", "region": "US", "label_en": "US CPI",                   "label_zh": "美国 CPI",                  "category": "inflation"},
    "US_NFP":    {"importance": "high", "region": "US", "label_en": "US payrolls (NFP)",        "label_zh": "美国非农就业",              "category": "activity"},
}

# Authoritative CY2026 static tables for irregular-cadence releases (month -> day).
_HK_SCHED_2026: dict[str, dict[int, int]] = {
    # HK composite CPI — published ~21st-23rd for the prior month.
    "HK_CPI": {1: 22, 2: 20, 3: 23, 4: 22, 5: 21, 6: 22,
               7: 21, 8: 20, 9: 22, 10: 22, 11: 20, 12: 22},
    # HK GDP (C&SD): Q4/full-year advance ~end-Feb, Q1 ~early-May, Q2 ~mid-Aug, Q3 ~mid-Nov.
    "HK_GDP": {2: 26, 5: 15, 8: 14, 11: 13},
    # HK external merchandise trade — ~25th-28th for the prior month.
    "HK_TRADE": {1: 27, 2: 25, 3: 26, 4: 27, 5: 26, 6: 25,
                 7: 27, 8: 26, 9: 25, 10: 27, 11: 26, 12: 23},
    # HK retail sales — ~end of month for the prior month.
    "HK_RETAIL": {1: 30, 2: 27, 3: 31, 4: 30, 5: 29, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 30, 11: 27, 12: 31},
    # HK unemployment (3-month rolling) — ~17th-19th.
    "HK_UNEMP": {1: 19, 2: 17, 3: 18, 4: 17, 5: 19, 6: 18,
                 7: 17, 8: 18, 9: 17, 10: 19, 11: 18, 12: 17},
    # US CPI — ~mid-month (10th-13th).
    "US_CPI": {1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10,
               7: 14, 8: 12, 9: 11, 10: 13, 11: 12, 12: 10},
}
# US FOMC 2026 decision days (the 2nd day of each two-day meeting).
_FOMC_2026 = [date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
              date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9)]


def _first_friday(y: int, m: int) -> date:
    """1st Friday of the month — the US non-farm payrolls release day."""
    d = date(y, m, 1)
    while d.weekday() != 4:    # 4 = Friday
        d += timedelta(days=1)
    return d


def _regime_asof() -> date | None:
    try:
        from lib import store
        df = store.read("hk_regime", "regime_history")
        if df is None or getattr(df, "empty", True):
            return None
        return df.index.max().date()
    except Exception as e:  # noqa: BLE001
        log.debug("hk regime asof unreadable (%s)", e)
        return None


def resolve_asof(asof: date | None = None) -> date:
    if asof is not None:
        return asof
    return _regime_asof() or date.today()


def _event(etype: str, d: date, asof: date, *, source: str = "computed") -> dict:
    meta = _META.get(etype, {})
    return {
        "type": etype,
        "date": d.isoformat(),
        "days_until": (d - asof).days,
        "name_en": meta.get("label_en", etype),
        "name_zh": meta.get("label_zh", etype),
        "importance": meta.get("importance", "med"),
        "region": meta.get("region", ""),
        "category": meta.get("category", ""),
        "source": source,
        "is_context_only": True,
    }


def _tabled(etype: str, today: date, end: date) -> list[date]:
    out: list[date] = []
    for (y, m) in _months_in_window(today, end):
        day = _HK_SCHED_2026.get(etype, {}).get(m)
        if not day:
            continue
        try:
            d = date(y, m, day)
        except ValueError:
            continue
        if today <= d <= end:
            out.append(d)
    return out


def hk_macro_events(asof: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Unified forward HK/US/CN macro-event list for the next `horizon_days`, sorted
    by date. Scheduling info, context-only. `asof` injectable for testing."""
    today = resolve_asof(asof)
    end = today + timedelta(days=horizon_days)
    out: list[dict] = []

    # --- HK-native date-arithmetic events ----------------------------------- #
    for (y, m) in _months_in_window(today, end):
        d = nth_business_day(y, m, 1)               # S&P Global HK PMI — 1st business day
        if today <= d <= end:
            out.append(_event("HK_PMI", d, today))

    # --- HK irregular-cadence (static CY2026 table) ------------------------- #
    for etype in ("HK_CPI", "HK_GDP", "HK_TRADE", "HK_RETAIL", "HK_UNEMP"):
        for d in _tabled(etype, today, end):
            out.append(_event(etype, d, today, source="static"))

    # --- US drivers (peg + global risk) ------------------------------------- #
    for fomc in _FOMC_2026:
        if today <= fomc <= end:
            out.append(_event("FOMC", fomc, today, source="static"))
            hkma = next_business_day_onward(fomc + timedelta(days=1))   # HKMA adjusts next morning
            if today <= hkma <= end:
                out.append(_event("HKMA_RATE", hkma, today, source="static"))
    for (y, m) in _months_in_window(today, end):
        d = _first_friday(y, m)                     # US payrolls — 1st Friday
        if today <= d <= end:
            out.append(_event("US_NFP", d, today))
    for d in _tabled("US_CPI", today, end):
        out.append(_event("US_CPI", d, today, source="static"))

    # --- China high-impact prints that drive HSI (re-exported) -------------- #
    # Pass the RESOLVED HK as-of (not raw `asof`) so the re-exported CN events share
    # the SAME date basis as the HK/US events — otherwise days_until / the window
    # filter desync whenever the HK and China regime feeds land on different days.
    for ev in _cn_high_impact(today, horizon_days):
        out.append({**ev, "region": "CN", "type": "CN_" + ev["type"],
                    "is_context_only": True})

    out.sort(key=lambda c: (c["date"], -1 if c["importance"] == "high" else 0, c["type"]))
    return out


_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DOW_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def high_impact_strip(asof: date | None = None, horizon_days: int = 14) -> list[dict]:
    """HIGH-importance HK/US/CN events only, next N days, each with a friendly
    day-of-week / month-day (EN + ZH) for chip rendering. DISPLAY-ONLY."""
    out = []
    for ev in hk_macro_events(asof, horizon_days):
        if ev["importance"] != "high":
            continue
        d = date.fromisoformat(ev["date"])
        out.append({**ev,
                    "dow": _DOW[d.weekday()], "dow_zh": _DOW_ZH[d.weekday()],
                    "md": f"{_MON[d.month]} {d.day}", "md_zh": f"{d.month}月{d.day}日"})
    return out


def imminent_line(asof: date | None = None, horizon_days: int = 14) -> dict | None:
    """The single most imminent high-impact item as a bilingual one-liner. Returns a
    {en, zh} dict, or None when the window is clear."""
    items = high_impact_strip(asof, horizon_days)
    if not items:
        return None
    i = items[0]
    dn = i["days_until"]
    when_en = ("today" if dn == 0 else "tomorrow" if dn == 1 else f"in {dn} days")
    when_zh = ("今天" if dn == 0 else "明天" if dn == 1 else f"{dn}天后")
    return {
        "en": f"Next high-impact print: {i['name_en']} {when_en} ({i['md']}).",
        "zh": f"下一项高影响数据：{i['name_zh']}{when_zh}（{i['md_zh']}）。",
        "type": i["type"],
        "date": i["date"],
        "days_until": dn,
    }
