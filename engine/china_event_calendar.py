"""China high-impact macro / policy calendar — DISPLAY-ONLY · CONTEXT-ONLY · LEAF.

A pure date-arithmetic engine that tells the user which scheduled China macro and
PBoC events are imminent. NO data fetch — the underlying series (PMI, CPI/PPI, M1/M2,
TSF, customs trade, IP/FAI/retail, GDP, LPR) are already collected elsewhere; this
module only encodes their *release cadence* and answers "what prints next, and when".

It is the China sibling of engine.event_calendar (the US/commodity calendar) and
deliberately replicates its shape: a static-schedule + date-arithmetic core, a
[asof, asof+horizon] window filter, a `high_impact_strip()` glance list and an
`imminent_line()` one-liner for the LLM narration layer.

CADENCE (Beijing time; encoded as date arithmetic where the cadence is regular, and
as a small authoritative CY2026 table only where it slips around holidays):
  • NBS Manufacturing + Non-mfg PMI — last CALENDAR day of each month (date arith).
  • Caixin Manufacturing PMI — 1st business day of the month; Caixin Services — 3rd
    business day (date arith).
  • CPI + PPI (NBS) — ~9th-10th; slips around Chinese New Year -> static CY2026 table.
  • Money supply M1/M2 + new RMB loans + TSF/社融 (PBoC) — a ~10th-15th window; the
    PBoC publishes on an irregular day inside it, so we surface the WINDOW OPEN day.
  • Customs trade balance / exports / imports — a ~7th-14th window (window-open day).
  • Industrial production + Fixed-asset investment + Retail sales (NBS monthly
    "活动数据" bundle) — ~15th-18th; CNY slip -> static CY2026 table.
  • GDP (quarterly, NBS) — released WITH the Jan/Apr/Jul/Oct activity bundle (static).
  • LPR fix (PBoC) — the 20th of every month (date arith; rolls off weekends to the
    next business day, mirroring the real fix which posts ~09:15 on a working day).
  • MLF operation (PBoC) — ~15th of each month (date arith). RRR / policy-rate moves
    are EVENT-DRIVEN with no public schedule, so they are deliberately NOT modelled.
  • SAFE FX reserves — ~7th of each month (date arith, window-style).

DISCIPLINE (enforced, not aspirational):
  • LEAF module: it imports only `lib.store` (for an optional asof read) + stdlib,
    and NOTHING in any scoring path imports it. It must NEVER feed engine.china_axes,
    engine.china_regime or engine.china_playbook — those are the scored core; this is
    a descriptive panel. Every event carries `is_context_only=True`.
  • There is deliberately NO event-risk score / conviction dampener. The `importance`
    field ("high"/"med") is a DISPLAY tier (visual emphasis / strip filter) ONLY —
    never a multiplier on anything. Dates are scheduling info, not forecasts.
  • Every public function returns plain-Python data (dates as ISO strings, numbers
    float/int/None) and NEVER raises into the build; the optional asof read degrades
    to date.today() and the schedule is otherwise always populated.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# per-type display metadata. importance = DISPLAY tier only (see docstring).
# Each label carries an EN + a paired ZH string (bilingual contract).
# --------------------------------------------------------------------------- #
_META: dict[str, dict] = {
    "PMI":       {"importance": "high", "label_en": "NBS PMI (mfg + non-mfg)",      "label_zh": "国家统计局 PMI（制造业＋非制造业）", "category": "activity"},
    "CAIXIN_M":  {"importance": "med",  "label_en": "Caixin Manufacturing PMI",     "label_zh": "财新制造业 PMI",                   "category": "activity"},
    "CAIXIN_S":  {"importance": "med",  "label_en": "Caixin Services PMI",          "label_zh": "财新服务业 PMI",                   "category": "activity"},
    "CPI":       {"importance": "high", "label_en": "CPI (consumer prices)",        "label_zh": "CPI（居民消费价格）",              "category": "inflation"},
    "PPI":       {"importance": "high", "label_en": "PPI (producer prices)",        "label_zh": "PPI（工业生产者价格）",            "category": "inflation"},
    "CREDIT":    {"importance": "high", "label_en": "Money supply, RMB loans & TSF","label_zh": "货币供应、人民币贷款与社融",       "category": "credit"},
    "TRADE":     {"importance": "high", "label_en": "Customs trade (exports/imports)","label_zh": "海关进出口数据",                 "category": "trade"},
    "ACTIVITY":  {"importance": "high", "label_en": "IP, FAI & retail sales",       "label_zh": "工业增加值、固投与社零",           "category": "activity"},
    "GDP":       {"importance": "high", "label_en": "GDP (quarterly)",              "label_zh": "GDP（季度）",                       "category": "growth"},
    "LPR":       {"importance": "high", "label_en": "LPR fix (loan prime rate)",    "label_zh": "LPR 报价（贷款市场报价利率）",     "category": "policy"},
    "MLF":       {"importance": "med",  "label_en": "MLF operation (PBoC)",         "label_zh": "MLF 操作（央行中期借贷便利）",     "category": "policy"},
    "FXRES":     {"importance": "med",  "label_en": "FX reserves (SAFE)",           "label_zh": "外汇储备（外管局）",               "category": "external"},
}

# Authoritative CY2026 release days (month -> day-of-month) for the NBS releases whose
# cadence is IRREGULAR (they slip around the Chinese New Year holiday and odd weekends,
# so naive arithmetic would mis-date them). These are the published / scheduled days;
# the regular-cadence events (PMI last-day, LPR 20th, etc.) are computed, not tabled.
#
# CPI/PPI normally print 9th-10th; in the Feb CNY window they slip to mid-month.
# The activity bundle (IP/FAI/retail, + GDP in quarter-end months) normally prints
# 15th-18th; the Jan release is combined with Dec and lands ~mid-Jan with annual GDP,
# and the Feb data is bundled into the March release (no standalone Jan/Feb activity).
_SCHED_2026: dict[str, dict[int, int]] = {
    # Consumer Price Index / Producer Price Index (NBS) — released together ~09:30 CST.
    "CPI": {1: 9, 2: 10, 3: 9, 4: 10, 5: 11, 6: 10,
            7: 9, 8: 10, 9: 10, 10: 16, 11: 10, 12: 10},
    "PPI": {1: 9, 2: 10, 3: 9, 4: 10, 5: 11, 6: 10,
            7: 9, 8: 10, 9: 10, 10: 16, 11: 10, 12: 10},
    # NBS monthly activity bundle: Industrial Production + Fixed-Asset Investment +
    # Retail Sales (社会消费品零售). NOTE China does NOT publish standalone Jan/Feb
    # activity — Jan+Feb are combined into the March release — so months 1 & 2 are
    # intentionally absent; the March entry carries the Jan-Feb cumulative print.
    "ACTIVITY": {3: 16, 4: 16, 5: 18, 6: 16,
                 7: 15, 8: 17, 9: 15, 10: 19, 11: 16, 12: 15},
    # GDP (quarterly): Q4/full-year ~mid-Jan, Q1 ~mid-Apr, Q2 ~mid-Jul, Q3 ~mid-Oct,
    # released WITH that month's activity bundle.
    "GDP": {1: 19, 4: 16, 7: 15, 10: 19},
}


# --------------------------------------------------------------------------- #
# pure date-arithmetic helpers
# --------------------------------------------------------------------------- #
def last_day_of_month(y: int, m: int) -> date:
    """Last CALENDAR day of month m (NBS PMI release day)."""
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)


def nth_business_day(y: int, m: int, n: int) -> date:
    """The n-th weekday (Mon-Fri) of month m. Weekends only (PRC public holidays are
    not modelled — Caixin occasionally slips a day around CNY; this is display context)."""
    d, seen = date(y, m, 1), 0
    while True:
        if d.weekday() < 5:
            seen += 1
            if seen == n:
                return d
        d += timedelta(days=1)


def next_business_day_onward(d: date) -> date:
    """`d` if it is a weekday, else roll forward to the next Mon-Fri. The LPR fix and
    MLF post on a working day, so a 20th/15th that lands on a weekend rolls forward."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _months_in_window(today: date, end: date) -> list[tuple[int, int]]:
    """(year, month) pairs spanning [today, end] inclusive."""
    out, y, m = [], today.year, today.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m = m % 12 + 1
        if m == 1:
            y += 1
    return out


# --------------------------------------------------------------------------- #
# asof sourcing — derive "today" from the live China regime date when available
# (the dashboard is built daily, so the regime's last classified day is the natural
# "now"). Falls back to the wall clock. Mirrors how the build wires its asof.
# --------------------------------------------------------------------------- #
def _regime_asof() -> date | None:
    """The latest classified China-regime date, or None if unreadable. Never raises."""
    try:
        from lib import store
        df = store.read("china_regime", "regime_history")
        if df is None or getattr(df, "empty", True):
            return None
        return df.index.max().date()
    except Exception as e:  # noqa: BLE001 — degrade to wall clock
        log.debug("china regime asof unreadable (%s)", e)
        return None


def resolve_asof(asof: date | None = None) -> date:
    """Resolution order: explicit `asof` (testing) -> live regime date -> today."""
    if asof is not None:
        return asof
    return _regime_asof() or date.today()


# --------------------------------------------------------------------------- #
# event constructor
# --------------------------------------------------------------------------- #
def _event(etype: str, d: date, asof: date, *, source: str = "computed") -> dict:
    meta = _META.get(etype, {})
    return {
        "type": etype,
        "date": d.isoformat(),
        "days_until": (d - asof).days,
        "name_en": meta.get("label_en", etype),
        "name_zh": meta.get("label_zh", etype),
        "importance": meta.get("importance", "med"),
        "category": meta.get("category", ""),
        "source": source,
        "is_context_only": True,
    }


def _tabled(etype: str, today: date, end: date) -> list[date]:
    """In-window dates for an irregular-cadence release from the static CY2026 table."""
    out: list[date] = []
    for (y, m) in _months_in_window(today, end):
        day = _SCHED_2026.get(etype, {}).get(m)
        if not day:
            continue
        try:
            d = date(y, m, day)
        except ValueError:
            continue
        if today <= d <= end:
            out.append(d)
    return out


# --------------------------------------------------------------------------- #
# public: the full forward China macro-event list
# --------------------------------------------------------------------------- #
def china_macro_events(asof: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Unified forward China macro/policy event list for the next `horizon_days`,
    sorted by date. Scheduling info, context-only — see module docstring discipline.
    `asof` is injectable for testing; default derives from the live regime date."""
    today = resolve_asof(asof)
    end = today + timedelta(days=horizon_days)
    out: list[dict] = []

    months = _months_in_window(today, end)

    # --- date-arithmetic (regular-cadence) events ---------------------------- #
    for (y, m) in months:
        # NBS PMI — last calendar day of the month
        d = last_day_of_month(y, m)
        if today <= d <= end:
            out.append(_event("PMI", d, today))
        # Caixin PMIs — 1st (mfg) and 3rd (services) business day
        for etype, nbd in (("CAIXIN_M", 1), ("CAIXIN_S", 3)):
            d = nth_business_day(y, m, nbd)
            if today <= d <= end:
                out.append(_event(etype, d, today))
        # PBoC credit aggregates (M1/M2 + new loans + TSF) — window opens ~10th
        d = next_business_day_onward(date(y, m, 10))
        if today <= d <= end:
            out.append(_event("CREDIT", d, today))
        # Customs trade balance — window opens ~7th
        d = next_business_day_onward(date(y, m, 7))
        if today <= d <= end:
            out.append(_event("TRADE", d, today))
        # SAFE FX reserves — ~7th
        d = next_business_day_onward(date(y, m, 7))
        if today <= d <= end:
            out.append(_event("FXRES", d, today))
        # MLF operation — ~15th
        d = next_business_day_onward(date(y, m, 15))
        if today <= d <= end:
            out.append(_event("MLF", d, today))
        # LPR fix — the 20th (rolls to next business day if on a weekend)
        d = next_business_day_onward(date(y, m, 20))
        if today <= d <= end:
            out.append(_event("LPR", d, today))

    # --- irregular-cadence (CNY-slipping) events from the static CY2026 table -- #
    for etype in ("CPI", "PPI", "ACTIVITY", "GDP"):
        for d in _tabled(etype, today, end):
            out.append(_event(etype, d, today, source="static"))

    out.sort(key=lambda c: (c["date"], -1 if c["importance"] == "high" else 0, c["type"]))
    return out


# --------------------------------------------------------------------------- #
# public: the compact "China high-impact" strip + the LLM context one-liner
# --------------------------------------------------------------------------- #
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DOW_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def high_impact_strip(asof: date | None = None, horizon_days: int = 14) -> list[dict]:
    """The china.html glance strip: HIGH-importance China macro/policy events only,
    next N days, each tagged with a friendly day-of-week / month-day (EN + ZH) for
    chip rendering. DISPLAY-ONLY."""
    out = []
    for ev in china_macro_events(asof, horizon_days):
        if ev["importance"] != "high":
            continue
        d = date.fromisoformat(ev["date"])
        out.append({**ev,
                    "dow": _DOW[d.weekday()], "dow_zh": _DOW_ZH[d.weekday()],
                    "md": f"{_MON[d.month]} {d.day}", "md_zh": f"{d.month}月{d.day}日"})
    return out


def imminent_line(asof: date | None = None, horizon_days: int = 14) -> dict | None:
    """The single most imminent high-impact item as a bilingual one-liner for the LLM
    context layer (narration only; the model reads it, never scores it). Returns a
    {en, zh} dict, or None when the window is clear."""
    items = high_impact_strip(asof, horizon_days)
    if not items:
        return None
    i = items[0]
    dn = i["days_until"]
    when_en = ("today" if dn == 0 else "tomorrow" if dn == 1 else f"in {dn} days")
    when_zh = ("今天" if dn == 0 else "明天" if dn == 1 else f"{dn}天后")
    return {
        "en": f"Next high-impact China print: {i['name_en']} {when_en} ({i['md']}).",
        "zh": f"下一项高影响中国数据：{i['name_zh']}{when_zh}（{i['md_zh']}）。",
        "type": i["type"],
        "date": i["date"],
        "days_until": dn,
    }
