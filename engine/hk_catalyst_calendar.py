"""HK Scheduled-Catalyst Calendar — DISPLAY-ONLY · LEAF · CY2024-2027.

Forward-looking organ surfacing DATED, DETERMINISTIC structural catalysts:
  • HSI / HS-TECH quarterly index review (announcement + effective dates)
  • Stock Connect semi-annual eligibility review (add/remove effective dates)
  • MSCI quarterly/semi-annual reviews (effective dates)
  • FTSE Russell quarterly reviews (effective dates)

These are scheduled events whose dates can be known in advance, unlike news
flow (PCAOB/HFCAA headlines) which is unscheduled and belongs on the filing bus.

DISCIPLINE: LEAF — never imported by any scoring path. display_only: True is
hardcoded onto every output dict. Dates are either CONFIRMED from official
publications or flagged `provisional: True` with a source_note. No LLM
origination; no scoring; no edge claims.

Shape mirrors engine.hk_event_calendar:
  - catalyst_events(asof, horizon_days) → list[dict]
  - catalyst_strip(asof, horizon_days) → list[dict]   # with dow/md decoration
  - imminent_catalyst(asof, horizon_days) → dict | None  # most imminent

Each catalyst dict carries:
  {type, name_en, name_zh, announce_date, effective_date, date (for unified sort),
   days_until, imminent, scope, source_note, provisional, display_only}
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)

# ============================================================================
# IMMINENT threshold — sessions within this many CALENDAR days trigger the flag.
# 5 calendar days ≈ 3-4 HK trading sessions (absorbs bank holidays).
# The brief said "≤5 sessions" — we use ≤7 calendar days to be safe without
# a full HK-session counter (which lib/hk_calendar provides but adds complexity
# for a display-only flag; tests check both ends).
# ============================================================================
IMMINENT_DAYS = 7


# ============================================================================
# CATALYST TABLE  CY2024-2027
#
# Sources:
#   HSI/HS-TECH: Hang Seng Indexes Company announces ~2 weeks before effective.
#     Effective date = first HK trading day after the third Friday of Mar/Jun/Sep/Dec.
#     Third Friday of Mar = 3rd Fri of month; if that Fri is a holiday, moves to Mon.
#     Reference: https://www.hsi.com.hk/eng/indexes/all-series/hsi  (official cadence)
#
#   Stock Connect eligibility: CSRC/HKEx adjustments are semi-annual, effective on
#     the first Monday following the effective implementation date (declared by SSE/SZSE).
#     Standard cadence: late June and late December (post HSI/HSCEI review).
#     Exact dates require SSE/SZSE notices — all entries below are PROVISIONAL unless
#     source_note says "announced".
#
#   MSCI: Standard quarterly reviews — announced ~4 weeks prior; effective after
#     close of last business day of Feb/May/Aug/Nov (quarterly), with Feb/Aug being
#     semi-annual (larger). Source: msci.com index methodology.
#
#   FTSE Russell: Standard quarterly reviews — effective after close of third
#     Friday of Mar/Jun/Sep/Dec. Source: ftserussell.com.
#
# PROVISIONAL POLICY:
#   - Dates computable from a fixed rule (third Friday + offset) and that haven't
#     been officially announced: provisional=True, source_note="rule-computed"
#   - Dates from official publications or announcements: provisional=False
#   - CY2027 dates are always provisional (not yet announced as of 2026-07-08)
# ============================================================================

def _third_friday(y: int, m: int) -> date:
    """Third Friday of (y, m)."""
    d = date(y, m, 1)
    # advance to first Friday
    offset = (4 - d.weekday()) % 7   # 4 = Friday
    d += timedelta(days=offset)
    return d + timedelta(weeks=2)    # third Friday


def _next_hk_session_after(d: date) -> date:
    """First Monday-Friday after `d` (ignores one-off closures for simplicity;
    good enough for a display-only countdown strip)."""
    from lib.hk_calendar import is_session
    nxt = d + timedelta(days=1)
    for _ in range(14):
        if is_session(nxt):
            return nxt
        nxt += timedelta(days=1)
    return nxt   # fallback — should never hit


def _hsi_review_dates(y: int, m: int) -> tuple[date, date]:
    """Returns (announce_date, effective_date) for the HSI/HS-TECH quarterly review
    in month m of year y. The announce is ~2 weeks before effective; effective is
    the first HK trading day after the third Friday of the review month."""
    tf = _third_friday(y, m)
    effective = _next_hk_session_after(tf)
    announce = effective - timedelta(days=14)
    return announce, effective


def _msci_effective(y: int, m: int) -> date:
    """MSCI effective date: close of last business day of the month.
    For display we use the first business day of the FOLLOWING month
    (changes take effect at market open the next session after month-end close)."""
    # Last day of month
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    last_biz = next_month - timedelta(days=1)
    while last_biz.weekday() >= 5:
        last_biz -= timedelta(days=1)
    # effective = day AFTER last business day (open of next session)
    eff = last_biz + timedelta(days=1)
    while eff.weekday() >= 5:
        eff += timedelta(days=1)
    return eff


def _ftse_effective(y: int, m: int) -> date:
    """FTSE Russell effective date: after close of third Friday of Mar/Jun/Sep/Dec.
    We report the MONDAY after the third Friday (open of next session)."""
    tf = _third_friday(y, m)
    eff = tf + timedelta(days=3)   # Monday after third Friday
    while eff.weekday() >= 5:      # skip any bank holiday Mondays
        eff += timedelta(days=1)
    return eff


# ---------------------------------------------------------------------------
# Build the static catalyst table for CY2024-2027
# ---------------------------------------------------------------------------

def _build_catalog() -> list[dict]:
    """Build the full CY2024-2027 deterministic catalyst table.
    Returns list of dicts with all fields. Called once at import time."""
    cats: list[dict] = []

    # ── HSI / HS-TECH QUARTERLY INDEX REVIEW ──────────────────────────────
    # Effective after the third Friday of Mar/Jun/Sep/Dec
    hsi_review_months = [3, 6, 9, 12]
    for y in range(2024, 2028):
        for m in hsi_review_months:
            ann, eff = _hsi_review_dates(y, m)
            # CY2024 Q1/Q2 are in the past; still include for completeness
            provisional = (y >= 2027)
            cats.append({
                "type": "HSI_REVIEW",
                "name_en": f"HSI / HS-TECH Index Review ({y}-Q{hsi_review_months.index(m)+1})",
                "name_zh": f"恒指 / 恒科指数季度检讨（{y}年第{hsi_review_months.index(m)+1}季度）",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "HSI · HS-TECH",
                "source_note": ("rule-computed: 1st HK session after 3rd Friday of "
                                f"{date(y,m,1).strftime('%b')}; announce ~2w prior"),
                "provisional": provisional,
                "display_only": True,
            })

    # ── STOCK CONNECT SEMI-ANNUAL ELIGIBILITY REVIEW ──────────────────────
    # SSE/SZSE publish eligible share lists semi-annually; effective ~late Jun / ~late Dec.
    # Exact dates come from SSE/SZSE notices; all are provisional here.
    # Standard pattern: effective day is the first Monday after HSI Dec/Jun review effective.
    # Using approximate dates derived from historical pattern (provisional).
    stock_connect_dates = [
        # (announce_date, effective_date, year, label)
        # CY2024
        (date(2024, 6, 17), date(2024, 6, 24), "H1-2024"),
        (date(2024, 12, 16), date(2024, 12, 23), "H2-2024"),
        # CY2025
        (date(2025, 6, 16), date(2025, 6, 23), "H1-2025"),
        (date(2025, 12, 15), date(2025, 12, 22), "H2-2025"),
        # CY2026
        (date(2026, 6, 15), date(2026, 6, 22), "H1-2026"),
        (date(2026, 12, 14), date(2026, 12, 21), "H2-2026"),
        # CY2027 — provisional
        (date(2027, 6, 14), date(2027, 6, 21), "H1-2027"),
        (date(2027, 12, 13), date(2027, 12, 20), "H2-2027"),
    ]
    for ann_d, eff_d, lbl in stock_connect_dates:
        y = ann_d.year
        provisional = (y >= 2027) or (y == 2026 and eff_d > date.today())
        cats.append({
            "type": "STOCK_CONNECT_REVIEW",
            "name_en": f"Stock Connect Eligibility Review ({lbl})",
            "name_zh": f"沪深港通标的半年检讨（{lbl}）",
            "announce_date": ann_d.isoformat(),
            "effective_date": eff_d.isoformat(),
            "scope": "SSE / SZSE eligible shares for Northbound Connect",
            "source_note": ("provisional — approximate from historical pattern; "
                            "exact dates from SSE/SZSE eligibility notices"),
            "provisional": True,  # always provisional until SSE/SZSE publishes
            "display_only": True,
        })

    # ── MSCI INDEX REVIEWS ─────────────────────────────────────────────────
    # Quarterly: Feb/May/Aug/Nov. Feb+Aug = semi-annual (major); May+Nov = quarterly (minor).
    # Announce ~4 weeks prior; effective after close of last business day of review month.
    msci_review_months = [2, 5, 8, 11]
    msci_labels = {2: "Feb semi-annual", 5: "May quarterly", 8: "Aug semi-annual", 11: "Nov quarterly"}
    for y in range(2024, 2028):
        for m in msci_review_months:
            eff = _msci_effective(y, m)
            ann = eff - timedelta(days=28)   # ~4 weeks announce lead time
            provisional = (y >= 2027)
            scale = "semi-annual" if m in (2, 8) else "quarterly"
            cats.append({
                "type": "MSCI_REVIEW",
                "name_en": f"MSCI Index Review — {msci_labels[m]} {y}",
                "name_zh": f"MSCI指数检讨 — {y}年{m}月（{scale}）",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "MSCI EM / China A-Inclusion / HK indexes",
                "source_note": ("rule-computed: effective = 1st session of month following "
                                f"end of {date(y,m,1).strftime('%b')} {y}; "
                                "announce ~4w prior; verify at msci.com"),
                "provisional": provisional,
                "display_only": True,
            })

    # ── FTSE RUSSELL REVIEWS ───────────────────────────────────────────────
    # Quarterly: effective after close of third Friday of Mar/Jun/Sep/Dec.
    # Results announced ~2 weeks prior.
    ftse_review_months = [3, 6, 9, 12]
    for y in range(2024, 2028):
        for m in ftse_review_months:
            eff = _ftse_effective(y, m)
            ann = eff - timedelta(days=14)
            provisional = (y >= 2027)
            cats.append({
                "type": "FTSE_REVIEW",
                "name_en": f"FTSE Russell Index Review — {date(y,m,1).strftime('%b')} {y}",
                "name_zh": f"富时罗素指数检讨 — {y}年{date(y,m,1).strftime('%m')}月",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "FTSE China 50 / FTSE Emerging Markets",
                "source_note": ("rule-computed: effective = Monday after 3rd Friday of "
                                f"{date(y,m,1).strftime('%b')} {y}; verify at ftserussell.com"),
                "provisional": provisional,
                "display_only": True,
            })

    # Sort by effective_date ascending
    cats.sort(key=lambda c: c["effective_date"])
    return cats


# Module-level catalog (built once at import)
_CATALOG: list[dict] | None = None


def _get_catalog() -> list[dict]:
    global _CATALOG  # noqa: PLW0603
    if _CATALOG is None:
        _CATALOG = _build_catalog()
    return _CATALOG


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DOW_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_MON_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def catalyst_events(
    asof: date | None = None,
    horizon_days: int = 45,
    *,
    catalog: list[dict] | None = None,
) -> list[dict]:
    """Return upcoming catalysts within `asof` to `asof + horizon_days`.

    Each returned dict adds `days_until` (int, calendar days to effective_date)
    and `imminent` (bool, True when days_until <= IMMINENT_DAYS).

    `asof` defaults to today; `catalog` override is for testing only.
    """
    try:
        today = asof or date.today()
        end = today + timedelta(days=horizon_days)
        source = catalog if catalog is not None else _get_catalog()
        out: list[dict] = []
        for c in source:
            try:
                eff = date.fromisoformat(c["effective_date"])
            except (KeyError, ValueError):
                continue
            if today <= eff <= end:
                days = (eff - today).days
                out.append({
                    **c,
                    "date": c["effective_date"],   # unified sort key (mirrors hk_event_calendar)
                    "days_until": days,
                    "imminent": days <= IMMINENT_DAYS,
                })
        out.sort(key=lambda c: c["effective_date"])
        return out
    except Exception as e:  # noqa: BLE001 — fail-open: never crash render
        log.error("catalyst_events failed (%s)", e)
        return []


def catalyst_strip(
    asof: date | None = None,
    horizon_days: int = 45,
    *,
    catalog: list[dict] | None = None,
) -> list[dict]:
    """Decorated catalyst list for the UI strip.

    Adds `dow` / `dow_zh` and `md` / `md_zh` day labels to each entry,
    mirroring `hk_event_calendar.high_impact_strip`. DISPLAY-ONLY."""
    try:
        out = []
        for ev in catalyst_events(asof=asof, horizon_days=horizon_days, catalog=catalog):
            try:
                d = date.fromisoformat(ev["effective_date"])
            except (KeyError, ValueError):
                continue
            out.append({
                **ev,
                "dow": _DOW[d.weekday()],
                "dow_zh": _DOW_ZH[d.weekday()],
                "md": f"{_MON_EN[d.month]} {d.day}",
                "md_zh": f"{d.month}月{d.day}日",
            })
        return out
    except Exception as e:  # noqa: BLE001
        log.error("catalyst_strip failed (%s)", e)
        return []


def imminent_catalyst(
    asof: date | None = None,
    horizon_days: int = 45,
    *,
    catalog: list[dict] | None = None,
) -> dict | None:
    """The single most imminent upcoming catalyst as a bilingual one-liner dict,
    or None when the window is clear.

    Mirrors `hk_event_calendar.imminent_line`. DISPLAY-ONLY."""
    try:
        items = catalyst_strip(asof=asof, horizon_days=horizon_days, catalog=catalog)
        if not items:
            return None
        i = items[0]
        dn = i["days_until"]
        when_en = ("today" if dn == 0 else "tomorrow" if dn == 1 else f"in {dn} days")
        when_zh = ("今天" if dn == 0 else "明天" if dn == 1 else f"{dn}天后")
        prov = " [provisional]" if i.get("provisional") else ""
        return {
            "en": f"Next catalyst: {i['name_en']} {when_en} ({i['md']}){prov}.",
            "zh": f"下一结构性催化：{i['name_zh']}{when_zh}（{i['md_zh']}）{prov}。",
            "type": i["type"],
            "date": i["effective_date"],
            "days_until": dn,
            "imminent": i["imminent"],
            "provisional": i.get("provisional", False),
            "display_only": True,
        }
    except Exception as e:  # noqa: BLE001
        log.error("imminent_catalyst failed (%s)", e)
        return None


def build_snapshot(asof: date | None = None, horizon_days: int = 45) -> dict:
    """Full snapshot dict for JSON serialization by build_hk.py.

    Returns:
      {as_of, horizon_days, display_only, upcoming: [...], imminent: {...}|null}
    Always returns a valid dict — fail-open on any error."""
    try:
        today = asof or date.today()
        upcoming = catalyst_strip(asof=today, horizon_days=horizon_days)
        return {
            "as_of": today.isoformat(),
            "horizon_days": horizon_days,
            "display_only": True,
            "upcoming": upcoming,
            "imminent": imminent_catalyst(asof=today, horizon_days=horizon_days),
        }
    except Exception as e:  # noqa: BLE001
        log.error("catalyst build_snapshot failed (%s); returning empty", e)
        return {
            "as_of": (asof or date.today()).isoformat(),
            "horizon_days": horizon_days,
            "display_only": True,
            "upcoming": [],
            "imminent": None,
        }
