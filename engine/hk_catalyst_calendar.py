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
# The brief called for "≤5 sessions"; we use ≤7 calendar days (5 sessions +
# one weekend buffer) so a Monday effective flagged on the prior Wednesday still
# shows. lib/hk_calendar provides a session counter but session-counting adds
# complexity for a display-only flag.
# ============================================================================
IMMINENT_DAYS = 7


# ============================================================================
# CATALYST TABLE  CY2024-2027
#
# Sources and verified dates (session 2026-07-08):
#
#   HSI / HS-TECH:
#     Hang Seng Indexes publishes quarterly review results ~2 weeks before
#     effective.  Historically effective = 2nd Monday of Mar/Jun/Sep/Dec.
#     VERIFIED from official press releases:
#       2025-03-10 — Q4-2024 review (announced 2025-02-21)
#         https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20250221T174505.pdf
#       2025-09-08 — Q3-2025 review date announced 2025-07-02
#         https://www.hsi.com.hk/static/uploads/contents/en/news/indexChgNotice/20250702T163005.pdf
#       2026-06-08 — Q2-2026 review (announced 2026-05-22, effective after
#         close of June 5, 2026 / start of June 8, 2026)
#         https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20260522T174500.pdf
#     All other HSI dates: rule-computed (2nd Monday of review month),
#     provisional=True.
#
#   Stock Connect eligibility: CSRC/HKEx adjustments are semi-annual; exact
#     dates come from SSE/SZSE notices — all entries are PROVISIONAL.
#
#   MSCI: Quarterly reviews effective on the last business day of
#     Feb/May/Aug/Nov.  VERIFIED 2025 dates from msci.com:
#       2025-02-28 (Feb semi-annual, announced 2025-02-11)
#         https://app2.msci.com/webapp/index_ann/DocGet?pub_key=nZnpr0ioyUo%3D&lang=en&format=html
#       2025-05-30 (May quarterly, announced 2025-05-13)
#         https://www.msci.com/documents/10199/4152f640-34b6-b35e-0ccc-a2711696d95a
#       2025-08-27 (Aug semi-annual, announced 2025-08-07; moved earlier per
#         MSCI feedback process)
#         https://app2.msci.com/webapp/index_ann/DocGet?pub_key=iVkAtYHOgSA%3D&lang=en&format=html
#       2025-11-25 (Nov quarterly, per MSCI update)
#         https://app2.msci.com/webapp/index_ann/DocGet?pub_key=dJ1N3ASUmHE%3D&lang=en&format=html
#     All other MSCI dates: rule-computed (last business day of review month),
#     provisional=True.
#
#   FTSE Russell: Quarterly reviews effective after close of third Friday of
#     Mar/Jun/Sep/Dec; we report the Monday after (start of next session).
#     VERIFIED: 2025-09-22 (Sep Q3-2025)
#       https://www.lseg.com/en/media-centre/press-releases/ftse-russell/2025/ftse-china-index-series-quarterly-review-q3-2025
#     Rule matches methodology; FTSE publishes its schedule in advance.
#
# PROVISIONAL POLICY (house epistemics — "uncertainty is printed, not hidden"):
#   provisional=False ONLY for dates verified against an official published
#   notice in this session (listed above). Everything else is provisional=True,
#   displayed with a "~" caveat in the UI. CY2027 is always provisional.
# ============================================================================

# ---------------------------------------------------------------------------
# Verified effective dates — (year, review_month) → effective_date
# These are the ONLY entries that may carry provisional=False.
# ---------------------------------------------------------------------------

_HSI_VERIFIED: dict[tuple[int, int], date] = {
    # Q4-2024 review → Mar-2025 effective
    (2025, 3): date(2025, 3, 10),
    # Q3-2025 review → Sep-2025 effective
    (2025, 9): date(2025, 9, 8),
    # Q2-2026 review → Jun-2026 effective
    (2026, 6): date(2026, 6, 8),
}

_MSCI_VERIFIED: dict[tuple[int, int], date] = {
    (2025, 2):  date(2025, 2, 28),
    (2025, 5):  date(2025, 5, 30),
    (2025, 8):  date(2025, 8, 27),
    (2025, 11): date(2025, 11, 25),
}

_FTSE_VERIFIED: dict[tuple[int, int], date] = {
    (2025, 9): date(2025, 9, 22),
}


def _third_friday(y: int, m: int) -> date:
    """Third Friday of (y, m)."""
    d = date(y, m, 1)
    # advance to first Friday
    offset = (4 - d.weekday()) % 7   # 4 = Friday
    d += timedelta(days=offset)
    return d + timedelta(weeks=2)    # third Friday


def _second_monday(y: int, m: int) -> date:
    """Second Monday of (y, m).  Rule-of-thumb for HSI effective dates."""
    d = date(y, m, 1)
    offset = (0 - d.weekday()) % 7   # 0 = Monday
    first_mon = d + timedelta(days=offset)
    return first_mon + timedelta(weeks=1)


def _hsi_review_dates(y: int, m: int) -> tuple[date, date, bool]:
    """Returns (announce_date, effective_date, provisional) for the
    HSI/HS-TECH quarterly review in month m of year y.

    Effective date: 2nd Monday of the review month (rule), overridden by
    a verified date where available.  Announce is ~2 weeks before effective.
    """
    if (y, m) in _HSI_VERIFIED:
        effective = _HSI_VERIFIED[(y, m)]
        provisional = False
    else:
        effective = _second_monday(y, m)
        provisional = True
    announce = effective - timedelta(days=14)
    return announce, effective, provisional


def _msci_effective(y: int, m: int) -> tuple[date, bool]:
    """MSCI effective date: last business day of the review month.
    Returns (effective_date, provisional).

    MSCI confirms changes 'effective as of the close of [last biz day] of
    [month]'.  The verified 2025 dates are hardcoded; others are rule-computed.
    """
    if (y, m) in _MSCI_VERIFIED:
        return _MSCI_VERIFIED[(y, m)], False
    # Rule: last business day of month
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    last_biz = next_month - timedelta(days=1)
    while last_biz.weekday() >= 5:
        last_biz -= timedelta(days=1)
    return last_biz, True


def _ftse_effective(y: int, m: int) -> tuple[date, bool]:
    """FTSE Russell effective date: after close of third Friday of Mar/Jun/Sep/Dec.
    We report the MONDAY after the third Friday (open of next session).
    Returns (effective_date, provisional).

    The 3rd-Friday rule is FTSE's documented methodology.  Sep-2025 is verified;
    others are rule-computed (rule is correct per FTSE methodology, provisional
    only because no official advance notice was checked per entry).
    """
    if (y, m) in _FTSE_VERIFIED:
        return _FTSE_VERIFIED[(y, m)], False
    tf = _third_friday(y, m)
    eff = tf + timedelta(days=3)   # Monday after third Friday
    while eff.weekday() >= 5:      # skip any bank holiday Mondays
        eff += timedelta(days=1)
    return eff, True


# ---------------------------------------------------------------------------
# Build the static catalyst table for CY2024-2027
# ---------------------------------------------------------------------------

def _build_catalog() -> list[dict]:
    """Build the full CY2024-2027 deterministic catalyst table.
    Returns list of dicts with all fields. Called once at import time."""
    cats: list[dict] = []

    # ── HSI / HS-TECH QUARTERLY INDEX REVIEW ──────────────────────────────
    # Effective on the 2nd Monday of Mar/Jun/Sep/Dec (verified for select
    # quarters; rule-computed / provisional for others).
    hsi_review_months = [3, 6, 9, 12]
    for y in range(2024, 2028):
        for m in hsi_review_months:
            ann, eff, provisional = _hsi_review_dates(y, m)
            if y >= 2027:
                provisional = True  # CY2027 not yet announced
            source = (
                f"verified: hsi.com.hk press release — effective {eff}"
                if not provisional
                else (
                    "rule-computed: 2nd Monday of "
                    f"{date(y,m,1).strftime('%b')} {y}; verify at hsi.com.hk"
                )
            )
            cats.append({
                "type": "HSI_REVIEW",
                "name_en": f"HSI / HS-TECH Index Review ({y}-Q{hsi_review_months.index(m)+1})",
                "name_zh": f"恒指 / 恒科指数季度检讨（{y}年第{hsi_review_months.index(m)+1}季度）",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "HSI · HS-TECH",
                "source_note": source,
                "provisional": provisional,
                "display_only": True,
            })

    # ── STOCK CONNECT SEMI-ANNUAL ELIGIBILITY REVIEW ──────────────────────
    # SSE/SZSE publish eligible share lists semi-annually; effective ~late Jun / ~late Dec.
    # Exact dates come from SSE/SZSE notices; all are provisional here.
    # Approximate dates derived from historical pattern (provisional).
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
    # Announce ~4 weeks prior; effective = last business day of review month
    # (per MSCI methodology; MSCI may move dates earlier — see _MSCI_VERIFIED).
    msci_review_months = [2, 5, 8, 11]
    msci_labels = {2: "Feb semi-annual", 5: "May quarterly", 8: "Aug semi-annual", 11: "Nov quarterly"}
    for y in range(2024, 2028):
        for m in msci_review_months:
            eff, provisional = _msci_effective(y, m)
            if y >= 2027:
                provisional = True  # CY2027 not yet announced
            ann = eff - timedelta(days=28)   # ~4 weeks announce lead time
            scale = "semi-annual" if m in (2, 8) else "quarterly"
            source = (
                f"verified: msci.com announcement — effective {eff}"
                if not provisional
                else (
                    "rule-computed: effective = last business day of "
                    f"{date(y,m,1).strftime('%b')} {y}; verify at msci.com"
                )
            )
            cats.append({
                "type": "MSCI_REVIEW",
                "name_en": f"MSCI Index Review — {msci_labels[m]} {y}",
                "name_zh": f"MSCI指数检讨 — {y}年{m}月（{scale}）",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "MSCI EM / China A-Inclusion / HK indexes",
                "source_note": source,
                "provisional": provisional,
                "display_only": True,
            })

    # ── FTSE RUSSELL REVIEWS ───────────────────────────────────────────────
    # Quarterly: effective after close of third Friday of Mar/Jun/Sep/Dec.
    # Results announced ~2 weeks prior.  Rule matches FTSE methodology.
    # Sep-2025 (2025-09-22) is verified; others are rule-computed.
    ftse_review_months = [3, 6, 9, 12]
    for y in range(2024, 2028):
        for m in ftse_review_months:
            eff, provisional = _ftse_effective(y, m)
            if y >= 2027:
                provisional = True  # CY2027 not yet announced
            ann = eff - timedelta(days=14)
            source = (
                f"verified: ftserussell.com press release — effective {eff}"
                if not provisional
                else (
                    "rule-computed: effective = Monday after 3rd Friday of "
                    f"{date(y,m,1).strftime('%b')} {y}; verify at ftserussell.com"
                )
            )
            cats.append({
                "type": "FTSE_REVIEW",
                "name_en": f"FTSE Russell Index Review — {date(y,m,1).strftime('%b')} {y}",
                "name_zh": f"富时罗素指数检讨 — {y}年{date(y,m,1).strftime('%m')}月",
                "announce_date": ann.isoformat(),
                "effective_date": eff.isoformat(),
                "scope": "FTSE China 50 / FTSE Emerging Markets",
                "source_note": source,
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
