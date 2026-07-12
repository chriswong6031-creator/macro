"""Unified US event / catalyst calendar — DISPLAY-ONLY · CONTEXT-ONLY · LEAF.

The single source of truth for "what scheduled events are coming up". It replaces
the two ad-hoc skeletons that previously lived inside `engine.macro_news`
(FOMC + first-Friday jobs) and `engine.commodity_news` (FOMC + OPEC + EIA WPSR) —
both of which now delegate here. Folding them together fixes a latent bug: the two
copies DISAGREED on which FOMC meetings carry the SEP/dot-plot (the macro copy
flagged Jan/Apr/Jul/Oct; the correct set is Mar/Jun/Sep/Dec).

What it adds on top of the old skeletons:
  • scheduled CPI / PPI / jobs / GDP / Personal-Income-&-Outlays(PCE) release dates
    from the FRED `release/dates` API (key wired) with a hard-coded, authoritative
    CY2026 fallback (OMB "Schedule of Release Dates for Principal Federal Economic
    Indicators") so the calendar is never empty when FRED is unreachable/keyless;
  • upcoming Treasury coupon-auction dates from the keyless, reachable
    TreasuryDirect `TA_WS/securities/upcoming` feed (Notes/Bonds/TIPS/FRN);
  • pure date-arithmetic events: weekly jobless claims (Thu), ISM Mfg/Services
    (1st/3rd business day), monthly options expiry / quad-witching (3rd Friday).

DISCIPLINE (enforced, not aspirational):
  • This is a LEAF module — it imports nothing from the mechanical core
    (conditions/regime/run/inputs/equity_alloc/*_signals/calibrate) and nothing in
    any scoring path imports it. Every event carries `is_context_only=True`.
  • There is deliberately **no** event-risk score / conviction dampener. Per
    research/DATA_SIGNAL_EXPANSION_2026.md #11: pre-FOMC drift died after 2016 and
    the Savor-Wilson announcement premium is *positive*, so cutting exposure into
    FOMC/CPI/jobs days is wrong-signed. The `impact` field is a DISPLAY tier
    (visual emphasis / strip filter) ONLY — never a multiplier on anything.
  • Every public function returns plain data and NEVER raises into the build; all
    network/parse failures degrade to the static schedule or an empty list.

`impact` legend (display tier only): "high" = FOMC / CPI / jobs / GDP / PCE / PPI;
"med" = jobless claims / ISM / Treasury auctions / opex / OPEC / EIA.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# static schedules — refresh ~annually (FRED override keeps them honest in CI)
# --------------------------------------------------------------------------- #
# Fed-published 2026 FOMC decision dates. SEP/dot-plot meetings are Mar/Jun/Sep/Dec.
_FOMC: list[tuple[str, bool]] = [
    ("2026-01-28", False), ("2026-03-18", True), ("2026-04-29", False),
    ("2026-06-17", True),  ("2026-07-29", False), ("2026-09-16", True),
    ("2026-10-28", False), ("2026-12-09", True),
]

# Authoritative CY2026 release days (month -> day-of-month), transcribed from the
# OMB/OIRA "Schedule of Release Dates for Principal Federal Economic Indicators for
# 2026". Used as the static fallback; FRED `release/dates` overrides when reachable.
_SCHED_2026: dict[str, dict[int, int]] = {
    # Consumer Price Index (BLS) — 08:30 ET
    "CPI": {1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10,
            7: 14, 8: 12, 9: 11, 10: 14, 11: 10, 12: 10},
    # Producer Price Index (BLS) — 08:30 ET
    "PPI": {1: 14, 2: 12, 3: 12, 4: 14, 5: 13, 6: 11,
            7: 15, 8: 13, 9: 10, 10: 15, 11: 13, 12: 15},
    # Employment Situation / nonfarm payrolls (BLS) — 08:30 ET. NOTE: these are the
    # PUBLISHED dates, which are NOT always the naive "first Friday" (e.g. the April
    # report prints 2026-05-08, not 2026-05-01) — that bug is why we tabulate them.
    "NFP": {1: 9, 2: 6, 3: 6, 4: 3, 5: 8, 6: 5,
            7: 2, 8: 7, 9: 4, 10: 2, 11: 6, 12: 4},
    # Gross Domestic Product (BEA) — rotating advance/2nd/3rd estimate — 08:30 ET
    "GDP": {1: 29, 2: 26, 3: 27, 4: 30, 5: 28, 6: 25,
            7: 30, 8: 26, 9: 30, 10: 29, 11: 25, 12: 23},
    # Personal Income & Outlays incl. the PCE deflator (BEA) — 08:30 ET
    "PCE": {1: 29, 2: 26, 3: 27, 4: 30, 5: 28, 6: 25,
            7: 30, 8: 26, 9: 30, 10: 29, 11: 25, 12: 23},
}

# FRED release ids -> our event type (for the optional live override).
_FRED_RELEASE_ID: dict[str, int] = {
    "CPI": 10, "PPI": 46, "NFP": 50, "GDP": 53, "PCE": 54,
}

# per-type display metadata. impact = DISPLAY tier only (see module docstring).
# label_zh = ZH display twin (bilingual parity, docs/DESIGN_DOCTRINE.md) — every
# emitted event carries label + label_zh so no template needs its own enum map.
_META: dict[str, dict] = {
    "FOMC":     {"time_et": "14:00", "impact": "high", "label": "FOMC rate decision",
                 "label_zh": "美联储议息会议"},
    "CPI":      {"time_et": "08:30", "impact": "high", "label": "CPI (consumer prices)",
                 "label_zh": "消费者物价指数（CPI）"},
    "PPI":      {"time_et": "08:30", "impact": "high", "label": "PPI (producer prices)",
                 "label_zh": "生产者物价指数（PPI）"},
    "NFP":      {"time_et": "08:30", "impact": "high", "label": "Jobs report (nonfarm payrolls)",
                 "label_zh": "非农就业报告"},
    "GDP":      {"time_et": "08:30", "impact": "high", "label": "GDP (BEA estimate)",
                 "label_zh": "GDP 数据"},
    "PCE":      {"time_et": "08:30", "impact": "high", "label": "PCE / personal income (BEA)",
                 "label_zh": "PCE 物价指数"},
    "CLAIMS":   {"time_et": "08:30", "impact": "med",  "label": "Initial jobless claims",
                 "label_zh": "初请失业金"},
    "ISM_MFG":  {"time_et": "10:00", "impact": "med",  "label": "ISM Manufacturing PMI",
                 "label_zh": "ISM 制造业 PMI"},
    "ISM_SVC":  {"time_et": "10:00", "impact": "med",  "label": "ISM Services PMI",
                 "label_zh": "ISM 服务业 PMI"},
    "OPEX":     {"time_et": "16:00", "impact": "med",  "label": "Options expiration",
                 "label_zh": "期权到期日"},
    "AUCTION":  {"time_et": "13:00", "impact": "med",  "label": "Treasury auction",
                 "label_zh": "国债拍卖"},
    "OPEC":     {"time_et": "",      "impact": "med",  "label": "OPEC ministerial meeting",
                 "label_zh": "OPEC 部长级会议"},
    "EIA_WPSR": {"time_et": "10:30", "impact": "med",  "label": "EIA crude/petroleum inventories",
                 "label_zh": "EIA 原油库存周报"},
}

# OPEC + EIA holiday-slip skeleton (commodity scope; refresh annually).
_OPEC_2026 = ["2026-06-07"]
_EIA_SLIP_WEEKS = {"2026-01-16", "2026-02-13", "2026-05-22", "2026-09-04",
                   "2026-10-09", "2026-11-06"}  # holiday weeks -> Thu instead of Wed

_UA = {"User-Agent": "macro-dashboard/1.0 (research)"}


# --------------------------------------------------------------------------- #
# pure date arithmetic helpers
# --------------------------------------------------------------------------- #
def first_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)   # weekday 4 == Friday


def third_friday(y: int, m: int) -> date:
    return first_friday(y, m) + timedelta(days=14)


def is_quad_witching(d: date) -> bool:
    """Quarterly triple/quad-witching expiry: 3rd Friday of Mar/Jun/Sep/Dec."""
    return d.month in (3, 6, 9, 12) and d == third_friday(d.year, d.month)


def nth_business_day(y: int, m: int, n: int) -> date:
    """The n-th weekday (Mon-Fri) of month m. Weekends only (holidays not modelled —
    ISM occasionally slips a day around a federal holiday; this is display context)."""
    d, seen = date(y, m, 1), 0
    while True:
        if d.weekday() < 5:
            seen += 1
            if seen == n:
                return d
        d += timedelta(days=1)


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
# FRED release/dates override (optional, key-gated, degrade-never-raise)
# --------------------------------------------------------------------------- #
def parse_fred_release_dates(payload: dict, today: date, end: date) -> list[date]:
    """PURE: pull in-window dates out of a FRED `release/dates` JSON payload. Tested
    with a synthetic scaffold because FRED needs a key + is sandbox-unreachable."""
    out: list[date] = []
    for rec in (payload or {}).get("release_dates", []) or []:
        try:
            d = date.fromisoformat((rec.get("date") or "")[:10])
        except (ValueError, TypeError):
            continue
        if today <= d <= end:
            out.append(d)
    return sorted(set(out))


def _fred_release_dates(release_id: int, today: date, end: date) -> list[date] | None:
    """Live FRED `release/dates` for one release id, cached. Returns None (NOT [])
    when unavailable so callers fall back to the static schedule. Never raises."""
    key = config.secret("FRED_API_KEY")
    if not key:
        return None
    cdir = config.ROOT / "data/macro/release_cache"
    try:
        cdir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    cache = cdir / f"rel_{release_id}_{today.isoformat()}.json"
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < 12 * 3600:
                return parse_fred_release_dates(json.loads(cache.read_text()), today, end)
        except Exception:  # noqa: BLE001
            pass
    try:
        import requests
        # include_release_dates_with_no_data=true surfaces the NEXT scheduled date
        # (which has no data yet); we filter to the [today, end] window in the parser.
        # No realtime_* params — they restrict to published vintages and would drop
        # the upcoming dates we want.
        r = requests.get(
            "https://api.stlouisfed.org/fred/release/dates",
            params={"release_id": release_id, "api_key": key, "file_type": "json",
                    "include_release_dates_with_no_data": "true", "sort_order": "asc"},
            timeout=20, headers=_UA)
        if r.status_code != 200 or "json" not in r.headers.get("Content-Type", ""):
            return None
        payload = r.json()
        try:
            cache.write_text(json.dumps(payload))
        except Exception:  # noqa: BLE001
            pass
        return parse_fred_release_dates(payload, today, end)
    except Exception as e:  # noqa: BLE001 — degrade to static schedule
        log.debug("FRED release/dates %s unreachable (%s)", release_id, e)
        return None


def _scheduled_release_dates(etype: str, today: date, end: date,
                             use_fred: bool = True) -> tuple[list[date], str]:
    """In-window dates for a tabulated release (CPI/PPI/NFP/GDP/PCE) plus their
    provenance: the live FRED override when reachable ("fred"), else the
    authoritative static CY2026 schedule ("static")."""
    if use_fred and etype in _FRED_RELEASE_ID:
        live = _fred_release_dates(_FRED_RELEASE_ID[etype], today, end)
        if live is not None:
            return live, "fred"
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
    return out, "static"


# --------------------------------------------------------------------------- #
# Treasury upcoming auctions — keyless, reachable (TreasuryDirect TA_WS feed)
# --------------------------------------------------------------------------- #
_TD_UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming"
_COUPON_TYPES = {"Note", "Bond", "TIPS", "FRN"}          # exclude Bills / CMBs (low-impact)
_BENCH_TENORS = (2, 3, 5, 7, 10, 20, 30)


def _normalize_term(security_type: str, term: str) -> str:
    """Map a raw TreasuryDirect term ('19-Year 11-Month', '4-Year 10-Month', '2-Year')
    to a clean benchmark label ('20-Year Bond', '5-Year Note')."""
    import re
    yrs = months = 0.0
    if (mm := re.search(r"(\d+)\s*-?\s*Year", term or "")):
        yrs = float(mm.group(1))
    if (mm := re.search(r"(\d+)\s*-?\s*Month", term or "")):
        months = float(mm.group(1))
    total = yrs + months / 12.0
    if total <= 0:
        return f"{term} {security_type}".strip()
    bench = min(_BENCH_TENORS, key=lambda b: abs(b - total))
    return f"{bench}-Year {security_type}"


_SEC_TYPE_ZH = {"Note": "国债", "Bond": "国债",
                "TIPS": "通胀保值国债（TIPS）", "FRN": "浮息国债（FRN）"}


def _normalize_term_zh(security_type: str, term: str) -> str:
    """ZH twin of _normalize_term ('20-Year Bond' -> '20年期国债')."""
    import re
    label = _normalize_term(security_type, term)
    m = re.match(r"(\d+)-Year (Note|Bond|TIPS|FRN)$", label)
    if not m:
        return label
    return f"{m.group(1)}年期{_SEC_TYPE_ZH[m.group(2)]}"


def _auction_cache_path(today: date) -> Path:
    cdir = config.ROOT / "data/macro/auction_cache"
    try:
        cdir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return cdir / f"upcoming_{today.isoformat()}.json"


def _fetch_upcoming_auctions(today: date) -> list[dict]:
    """Raw upcoming-auction records from TreasuryDirect, cached 12h. Never raises."""
    cache = _auction_cache_path(today)
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < 12 * 3600:
                return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    try:
        import requests
        r = requests.get(_TD_UPCOMING, params={"format": "json"}, timeout=20, headers=_UA)
        if r.status_code != 200 or "json" not in r.headers.get("Content-Type", ""):
            return []
        data = r.json() or []
        try:
            cache.write_text(json.dumps(data))
        except Exception:  # noqa: BLE001
            pass
        return data
    except Exception as e:  # noqa: BLE001 — degrade to no auctions
        log.debug("TreasuryDirect upcoming auctions unreachable (%s)", e)
        return []


def _auction_events(today: date, end: date) -> list[dict]:
    """In-window coupon (Note/Bond/TIPS/FRN) auctions, deduped by (date, term)."""
    out, seen = [], set()
    for rec in _fetch_upcoming_auctions(today):
        if (rec.get("securityType") or "") not in _COUPON_TYPES:
            continue
        try:
            d = date.fromisoformat((rec.get("auctionDate") or "")[:10])
        except (ValueError, TypeError):
            continue
        if not (today <= d <= end):
            continue
        label_term = _normalize_term(rec["securityType"], rec.get("securityTerm", ""))
        reopen = (rec.get("reopening") or "").strip().lower() == "yes"
        key = (d.isoformat(), label_term, reopen)
        if key in seen:
            continue
        seen.add(key)
        out.append(_event("AUCTION", d,
                          label=f"{label_term} auction" + (" (reopening)" if reopen else ""),
                          label_zh=_normalize_term_zh(rec["securityType"], rec.get("securityTerm", ""))
                                   + "拍卖" + ("（续发行）" if reopen else ""),
                          assets=["bonds"]))
    return out


# --------------------------------------------------------------------------- #
# event constructor
# --------------------------------------------------------------------------- #
def _event(etype: str, d: date, *, label: str | None = None, tag: str = "",
           label_zh: str | None = None, tag_zh: str | None = None,
           assets: list[str] | None = None, time_et: str | None = None,
           source: str = "computed") -> dict:
    meta = _META.get(etype, {})
    en = (label if label is not None else meta.get("label", etype))
    # ZH twin: explicit > per-type meta > EN label (never empty). tag_zh mirrors tag
    # unless the call site supplies a translated one.
    zh = (label_zh if label_zh is not None else meta.get("label_zh") or en)
    ev = {
        "type": etype,
        "date": d.isoformat(),
        "time_et": meta.get("time_et", "") if time_et is None else time_et,
        "label": en + tag,
        "label_zh": zh + (tag_zh if tag_zh is not None else tag),
        "impact": meta.get("impact", "med"),
        "source": source,
        "is_context_only": True,
    }
    if assets:
        ev["assets"] = assets
    return ev


# --------------------------------------------------------------------------- #
# public: US macro events (macro.html scope)
# --------------------------------------------------------------------------- #
def us_macro_events(today: date | None = None, horizon_days: int = 14,
                    use_fred: bool = True) -> list[dict]:
    """Unified forward US macro-event list for the next `horizon_days`. Scheduling
    info, context-only — see module docstring for the no-dampener discipline."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    out: list[dict] = []

    # FOMC (with correct SEP/dot-plot tag)
    for ds, is_sep in _FOMC:
        d = date.fromisoformat(ds)
        if today <= d <= end:
            out.append(_event("FOMC", d, tag=" (SEP · dot-plot)" if is_sep else "",
                              tag_zh="（SEP · 点阵图）" if is_sep else "",
                              source="static"))

    # tabulated releases (FRED override -> static CY2026 fallback)
    for etype in ("CPI", "PPI", "NFP", "GDP", "PCE"):
        dates, src = _scheduled_release_dates(etype, today, end, use_fred=use_fred)
        for d in dates:
            out.append(_event(etype, d, source=src))

    # weekly initial jobless claims — every Thursday 08:30 ET (computed)
    d = today
    while d <= end:
        if d.weekday() == 3:  # Thursday
            out.append(_event("CLAIMS", d))
        d += timedelta(days=1)

    # ISM Mfg (1st business day) + Services (3rd business day), computed
    for (y, m) in _months_in_window(today, end):
        for etype, nbd in (("ISM_MFG", 1), ("ISM_SVC", 3)):
            d = nth_business_day(y, m, nbd)
            if today <= d <= end:
                out.append(_event(etype, d))

    # monthly options expiry / quad-witching — 3rd Friday (computed)
    for (y, m) in _months_in_window(today, end):
        d = third_friday(y, m)
        if today <= d <= end:
            quad = is_quad_witching(d)
            out.append(_event("OPEX", d,
                              label="Quad-witching expiration" if quad else "Options expiration",
                              label_zh="四巫日期权到期" if quad else "期权到期日"))

    # Treasury coupon auctions (keyless TreasuryDirect feed)
    out.extend(_auction_events(today, end))

    out.sort(key=lambda c: (c["date"], c["time_et"] or "99:99"))
    return out


# --------------------------------------------------------------------------- #
# public: commodity events (commodities.html scope — FOMC + OPEC + EIA WPSR)
# --------------------------------------------------------------------------- #
def commodity_events(today: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Forward OPEC / FOMC / EIA-WPSR watch list (oil-centric), context-only."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    metals_energy = ["gold", "silver", "oil", "copper"]
    out: list[dict] = []

    for ds, is_sep in _FOMC:
        d = date.fromisoformat(ds)
        if today <= d <= end:
            out.append(_event("FOMC", d, label="FOMC decision",
                              label_zh="美联储议息决议",
                              tag=" (SEP)" if is_sep else "",
                              tag_zh="（SEP）" if is_sep else "",
                              assets=metals_energy, source="static"))
    for ds in _OPEC_2026:
        d = date.fromisoformat(ds)
        if today <= d <= end:
            out.append(_event("OPEC", d, assets=["oil"], source="static"))
    # EIA WPSR — every Wednesday 10:30 ET (Thu 12:00 on holiday-slip weeks)
    d = today
    while d <= end:
        if d.weekday() == 2:  # Wednesday
            slip = d.isoformat() in _EIA_SLIP_WEEKS
            day = d + timedelta(days=1) if slip else d
            out.append(_event("EIA_WPSR", day, time_et="12:00" if slip else "10:30",
                              assets=["oil"], source="static"))
        d += timedelta(days=1)
    out.sort(key=lambda c: c["date"])
    return out


# --------------------------------------------------------------------------- #
# public: the compact "US high-impact next 14 days" strip + LLM context line
# --------------------------------------------------------------------------- #
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def high_impact_strip(today: date | None = None, horizon_days: int = 14) -> list[dict]:
    """The macro.html glance strip: HIGH-impact US macro events only, next N days,
    each tagged with a friendly day-of-week / month-day for chip rendering."""
    out = []
    for ev in us_macro_events(today, horizon_days):
        if ev["impact"] != "high":
            continue
        d = date.fromisoformat(ev["date"])
        out.append({**ev, "dow": _DOW[d.weekday()],
                    "md": f"{_MON[d.month]} {d.day}",
                    "md_zh": f"{d.month}月{d.day}日"})
    return out


def imminent_line(today: date | None = None, horizon_days: int = 14) -> str:
    """One short text line of imminent high-impact catalysts for the LLM context
    layer (narration only; the model reads it, never scores it)."""
    items = high_impact_strip(today, horizon_days)
    if not items:
        return ""
    parts = [f"{i['md']} {i['type']}" + (f" {i['time_et']}ET" if i['time_et'] else "")
             for i in items[:6]]
    return f"Imminent US catalysts (next {horizon_days}d): " + "; ".join(parts) + "."
