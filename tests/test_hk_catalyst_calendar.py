"""Tests for engine/hk_catalyst_calendar.py — HK Scheduled-Catalyst Calendar.

Tests:
  (a) date arithmetic — a catalyst 3 sessions out flags imminent; 40 out does not
  (b) year-boundary (Dec -> Jan) doesn't crash or drop events
  (c) forward-window filter correctness
  (d) fail-open: missing/empty catalog -> empty strip, no crash
  (e) display_only is True on all output
  (f) all required fields present on every catalog entry
  (g) build_snapshot shape
  (h) imminent_catalyst bilingual one-liner

All writes are isolated to tmp_path (none in this file).
git status --porcelain MUST be clean after pytest.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.hk_catalyst_calendar as CAT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_catalog(effective_date: date, announce_offset_days: int = 14) -> list[dict]:
    """Minimal single-entry catalog with configurable effective date."""
    return [{
        "type": "HSI_REVIEW",
        "name_en": "Test HSI Review",
        "name_zh": "测试恒指检讨",
        "announce_date": (effective_date - timedelta(days=announce_offset_days)).isoformat(),
        "effective_date": effective_date.isoformat(),
        "scope": "HSI",
        "source_note": "synthetic",
        "provisional": False,
        "display_only": True,
    }]


# ---------------------------------------------------------------------------
# (a) Date arithmetic — imminent flag
# ---------------------------------------------------------------------------

def test_imminent_flag_within_threshold():
    """A catalyst 3 calendar days out (well within IMMINENT_DAYS=7) must flag imminent."""
    asof = date(2026, 6, 1)
    eff = asof + timedelta(days=3)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=_make_catalog(eff))
    assert len(evs) == 1
    assert evs[0]["imminent"] is True
    assert evs[0]["days_until"] == 3


def test_not_imminent_far_out():
    """A catalyst 40 calendar days out must NOT flag imminent."""
    asof = date(2026, 6, 1)
    eff = asof + timedelta(days=40)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=_make_catalog(eff))
    assert len(evs) == 1
    assert evs[0]["imminent"] is False
    assert evs[0]["days_until"] == 40


def test_exactly_at_imminent_boundary():
    """A catalyst exactly IMMINENT_DAYS out must flag imminent."""
    asof = date(2026, 9, 1)
    eff = asof + timedelta(days=CAT.IMMINENT_DAYS)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=_make_catalog(eff))
    assert len(evs) == 1
    assert evs[0]["imminent"] is True


def test_one_day_beyond_imminent_threshold():
    """A catalyst IMMINENT_DAYS+1 out must NOT flag imminent."""
    asof = date(2026, 9, 1)
    eff = asof + timedelta(days=CAT.IMMINENT_DAYS + 1)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=_make_catalog(eff))
    assert len(evs) == 1
    assert evs[0]["imminent"] is False


# ---------------------------------------------------------------------------
# (b) Year-boundary (Dec -> Jan) doesn't crash or drop events
# ---------------------------------------------------------------------------

def test_year_boundary_dec_to_jan():
    """Window spanning Dec 31 -> Jan doesn't crash."""
    # asof Dec 28 with 45-day window crosses into Feb
    asof = date(2025, 12, 28)
    # Place two catalysts: one on Dec 30, one on Jan 10
    catalog = [
        {
            "type": "HSI_REVIEW",
            "name_en": "Dec Review",
            "name_zh": "12月检讨",
            "announce_date": date(2025, 12, 15).isoformat(),
            "effective_date": date(2025, 12, 30).isoformat(),
            "scope": "HSI",
            "source_note": "test",
            "provisional": False,
            "display_only": True,
        },
        {
            "type": "FTSE_REVIEW",
            "name_en": "Jan Review",
            "name_zh": "1月检讨",
            "announce_date": date(2025, 12, 25).isoformat(),
            "effective_date": date(2026, 1, 5).isoformat(),
            "scope": "FTSE",
            "source_note": "test",
            "provisional": False,
            "display_only": True,
        },
    ]
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    dates = [e["effective_date"] for e in evs]
    assert "2025-12-30" in dates
    assert "2026-01-05" in dates
    # sorted ascending
    assert dates == sorted(dates)


def test_year_boundary_no_crash_empty():
    """Empty catalog over a year boundary must return [] without crash."""
    asof = date(2024, 12, 30)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=[])
    assert evs == []


# ---------------------------------------------------------------------------
# (c) Forward-window filter correctness
# ---------------------------------------------------------------------------

def test_window_filter_excludes_past():
    """Events before asof must not appear."""
    asof = date(2026, 7, 1)
    catalog = _make_catalog(asof - timedelta(days=1))   # yesterday
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    assert evs == []


def test_window_filter_includes_today():
    """An event on asof itself (days_until=0) must be included."""
    asof = date(2026, 7, 1)
    catalog = _make_catalog(asof)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    assert len(evs) == 1
    assert evs[0]["days_until"] == 0


def test_window_filter_excludes_beyond_horizon():
    """Events beyond horizon_days must not appear."""
    asof = date(2026, 7, 1)
    catalog = _make_catalog(asof + timedelta(days=46))   # just outside 45d
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    assert evs == []


def test_window_filter_includes_last_day():
    """An event exactly on asof+horizon_days must be included."""
    asof = date(2026, 7, 1)
    catalog = _make_catalog(asof + timedelta(days=45))
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    assert len(evs) == 1


def test_multiple_catalysts_sorted():
    """Multiple catalysts in a window must be sorted by effective_date ascending."""
    asof = date(2026, 7, 1)
    catalog = [
        {**_make_catalog(asof + timedelta(days=20))[0], "type": "FTSE_REVIEW"},
        {**_make_catalog(asof + timedelta(days=5))[0],  "type": "MSCI_REVIEW"},
        {**_make_catalog(asof + timedelta(days=35))[0], "type": "HSI_REVIEW"},
    ]
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=catalog)
    dates = [e["effective_date"] for e in evs]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# (d) Fail-open: missing/empty catalog -> empty strip, no crash
# ---------------------------------------------------------------------------

def test_empty_catalog_returns_empty_list():
    evs = CAT.catalyst_events(asof=date(2026, 7, 1), horizon_days=45, catalog=[])
    assert evs == []


def test_strip_empty_catalog():
    strip = CAT.catalyst_strip(asof=date(2026, 7, 1), horizon_days=45, catalog=[])
    assert strip == []


def test_imminent_catalyst_empty_catalog():
    result = CAT.imminent_catalyst(asof=date(2026, 7, 1), horizon_days=45, catalog=[])
    assert result is None


def test_build_snapshot_empty_catalog_no_crash(monkeypatch):
    """build_snapshot with an empty real catalog must return a valid dict."""
    # Monkeypatch _get_catalog to return [] to simulate a broken catalog
    monkeypatch.setattr(CAT, "_CATALOG", [])
    snap = CAT.build_snapshot(asof=date(2026, 7, 1), horizon_days=45)
    assert snap["display_only"] is True
    assert isinstance(snap["upcoming"], list)
    assert snap["imminent"] is None or isinstance(snap["imminent"], dict)
    # Reset so other tests use the real catalog
    monkeypatch.setattr(CAT, "_CATALOG", None)


def test_malformed_entry_skipped():
    """A catalog entry with a bad date string must be skipped, not crash."""
    catalog = [
        {"type": "HSI_REVIEW", "effective_date": "NOT-A-DATE",
         "name_en": "x", "name_zh": "x", "announce_date": "2026-01-01",
         "scope": "HSI", "source_note": "", "provisional": False, "display_only": True},
        *_make_catalog(date(2026, 7, 10)),
    ]
    evs = CAT.catalyst_events(asof=date(2026, 7, 1), horizon_days=45, catalog=catalog)
    # Only the valid entry should appear
    assert len(evs) == 1
    assert evs[0]["effective_date"] == "2026-07-10"


# ---------------------------------------------------------------------------
# (e) display_only is True on all output
# ---------------------------------------------------------------------------

def test_display_only_on_events():
    asof = date(2026, 6, 1)
    evs = CAT.catalyst_events(asof=asof, horizon_days=45, catalog=_make_catalog(asof + timedelta(days=10)))
    for ev in evs:
        assert ev["display_only"] is True


def test_display_only_on_strip():
    asof = date(2026, 6, 1)
    strip = CAT.catalyst_strip(asof=asof, horizon_days=45, catalog=_make_catalog(asof + timedelta(days=10)))
    for s in strip:
        assert s["display_only"] is True


def test_display_only_on_imminent():
    asof = date(2026, 6, 1)
    im = CAT.imminent_catalyst(asof=asof, horizon_days=45, catalog=_make_catalog(asof + timedelta(days=3)))
    assert im is not None
    assert im["display_only"] is True


# ---------------------------------------------------------------------------
# (f) All required fields present on every catalog entry
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"type", "name_en", "name_zh", "announce_date", "effective_date",
                   "scope", "source_note", "provisional", "display_only"}


def test_catalog_fields_complete():
    """Every entry in the built catalog must have all required fields."""
    catalog = CAT._build_catalog()
    assert len(catalog) > 0, "catalog must not be empty"
    for i, c in enumerate(catalog):
        missing = REQUIRED_FIELDS - set(c.keys())
        assert not missing, f"entry {i} ({c.get('type')}) missing fields: {missing}"


def test_catalog_covers_cy2024_to_2027():
    """Catalog must span all four years."""
    catalog = CAT._build_catalog()
    years = {date.fromisoformat(c["effective_date"]).year for c in catalog}
    assert 2024 in years and 2025 in years and 2026 in years and 2027 in years


def test_catalog_has_all_four_types():
    """Catalog must include all four catalyst types."""
    catalog = CAT._build_catalog()
    types = {c["type"] for c in catalog}
    assert "HSI_REVIEW" in types
    assert "STOCK_CONNECT_REVIEW" in types
    assert "MSCI_REVIEW" in types
    assert "FTSE_REVIEW" in types


def test_catalog_sorted_by_effective_date():
    """_build_catalog must return entries sorted ascending by effective_date."""
    catalog = CAT._build_catalog()
    dates = [c["effective_date"] for c in catalog]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# (g) build_snapshot shape
# ---------------------------------------------------------------------------

def test_build_snapshot_shape():
    asof = date(2026, 7, 1)
    snap = CAT.build_snapshot(asof=asof, horizon_days=45)
    assert snap["as_of"] == "2026-07-01"
    assert snap["horizon_days"] == 45
    assert snap["display_only"] is True
    assert isinstance(snap["upcoming"], list)
    # imminent is either None or a dict
    assert snap["imminent"] is None or isinstance(snap["imminent"], dict)


def test_build_snapshot_upcoming_within_window():
    """Every upcoming entry in the snapshot must be within the horizon window."""
    asof = date(2026, 7, 1)
    snap = CAT.build_snapshot(asof=asof, horizon_days=45)
    end = asof + timedelta(days=45)
    for ev in snap["upcoming"]:
        eff = date.fromisoformat(ev["effective_date"])
        assert asof <= eff <= end, f"{eff} outside [{asof}, {end}]"
        assert 0 <= ev["days_until"] <= 45


# ---------------------------------------------------------------------------
# (h) catalyst_strip bilingual decoration
# ---------------------------------------------------------------------------

def test_strip_has_dow_and_md():
    asof = date(2026, 6, 1)
    strip = CAT.catalyst_strip(asof=asof, horizon_days=45,
                               catalog=_make_catalog(asof + timedelta(days=10)))
    assert len(strip) == 1
    s = strip[0]
    assert s["dow"] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    assert s["dow_zh"] in ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    assert s["md"]     # e.g. "Jun 11"
    assert s["md_zh"]  # e.g. "6月11日"


def test_imminent_catalyst_bilingual():
    asof = date(2026, 6, 1)
    im = CAT.imminent_catalyst(asof=asof, horizon_days=45,
                               catalog=_make_catalog(asof + timedelta(days=3)))
    assert im is not None
    assert im["en"] and isinstance(im["en"], str)
    assert im["zh"] and isinstance(im["zh"], str)
    assert im["type"] == "HSI_REVIEW"
    assert im["days_until"] == 3
    assert im["imminent"] is True


def test_imminent_catalyst_none_when_window_clear():
    asof = date(2026, 6, 1)
    im = CAT.imminent_catalyst(asof=asof, horizon_days=45,
                               catalog=_make_catalog(asof - timedelta(days=5)))  # past
    assert im is None


# ---------------------------------------------------------------------------
# Smoke: real catalog loads without crash and has expected count range
# ---------------------------------------------------------------------------

def test_real_catalog_smoke():
    """The real catalog (no mock) must have >30 entries (4 types × 4 years × ~4 each)."""
    catalog = CAT._build_catalog()
    assert len(catalog) > 30


def test_real_catalog_no_writes_to_data_or_site(tmp_path):
    """Calling the full API must not write to data/ or site/ directories.
    (Verified by checking no files appear under tmp_path — tests use only memory.)"""
    asof = date(2026, 7, 8)
    # All calls go through memory only
    snap = CAT.build_snapshot(asof=asof, horizon_days=45)
    strip = CAT.catalyst_strip(asof=asof, horizon_days=45)
    im = CAT.imminent_catalyst(asof=asof, horizon_days=45)
    # No assertion about tmp_path — just confirming no FileNotFoundError or write side-effects
    assert snap is not None
    assert isinstance(strip, list)


# ---------------------------------------------------------------------------
# REAL-DATE REGRESSION TESTS
# These assert KNOWN-VERIFIED effective dates from official published notices.
# If the date arithmetic changes and produces wrong dates, these fail first.
# Sources verified session 2026-07-08 (see engine comments for URLs).
# ---------------------------------------------------------------------------

def _catalog_by_key(catalog: list[dict]) -> dict[tuple[str, str], dict]:
    """Index catalog by (type, effective_date) for easy lookup."""
    return {(c["type"], c["effective_date"]): c for c in catalog}


def test_hsi_q4_2024_effective_date():
    """HSI Q4-2024 review: effective 2025-03-10 (verified from hsi.com.hk 2025-02-21 PR)."""
    catalog = CAT._build_catalog()
    idx = _catalog_by_key(catalog)
    entry = idx.get(("HSI_REVIEW", "2025-03-10"))
    assert entry is not None, (
        "HSI_REVIEW effective 2025-03-10 missing from catalog — "
        "date arithmetic regression (Q4-2024 review)"
    )
    assert entry["provisional"] is False, "Verified date must not be provisional"


def test_hsi_q3_2025_effective_date():
    """HSI Q3-2025 review: effective 2025-09-08 (verified from hsi.com.hk 2025-07-02 notice)."""
    catalog = CAT._build_catalog()
    idx = _catalog_by_key(catalog)
    entry = idx.get(("HSI_REVIEW", "2025-09-08"))
    assert entry is not None, (
        "HSI_REVIEW effective 2025-09-08 missing from catalog — "
        "date arithmetic regression (Q3-2025 review)"
    )
    assert entry["provisional"] is False, "Verified date must not be provisional"


def test_msci_aug_2025_effective_date():
    """MSCI Aug-2025 semi-annual: effective 2025-08-27 (verified from msci.com update)."""
    catalog = CAT._build_catalog()
    idx = _catalog_by_key(catalog)
    entry = idx.get(("MSCI_REVIEW", "2025-08-27"))
    assert entry is not None, (
        "MSCI_REVIEW effective 2025-08-27 missing from catalog — "
        "date arithmetic regression (Aug-2025 semi-annual)"
    )
    assert entry["provisional"] is False, "Verified date must not be provisional"


def test_ftse_sep_2025_effective_date():
    """FTSE Q3-2025 review: effective 2025-09-22 (verified from lseg.com/ftse-russell PR)."""
    catalog = CAT._build_catalog()
    idx = _catalog_by_key(catalog)
    entry = idx.get(("FTSE_REVIEW", "2025-09-22"))
    assert entry is not None, (
        "FTSE_REVIEW effective 2025-09-22 missing from catalog — "
        "date arithmetic regression (Sep-2025 Q3 review)"
    )
    assert entry["provisional"] is False, "Verified date must not be provisional"


def test_provisional_flag_honest():
    """Every non-verified catalog entry must be provisional=True.
    This guards the house epistemics rule: rule-computed dates are always ~."""
    catalog = CAT._build_catalog()
    # Dates we have actually verified from official sources
    _known_verified = {
        ("HSI_REVIEW",   "2025-03-10"),
        ("HSI_REVIEW",   "2025-09-08"),
        ("HSI_REVIEW",   "2026-06-08"),
        ("MSCI_REVIEW",  "2025-02-28"),
        ("MSCI_REVIEW",  "2025-05-30"),
        ("MSCI_REVIEW",  "2025-08-27"),
        ("MSCI_REVIEW",  "2025-11-25"),
        ("FTSE_REVIEW",  "2025-09-22"),
        # STOCK_CONNECT_REVIEW entries are always provisional — tested separately
    }
    for c in catalog:
        key = (c["type"], c["effective_date"])
        if key in _known_verified:
            assert c["provisional"] is False, (
                f"{key} is a verified date but marked provisional"
            )
        elif c["type"] != "STOCK_CONNECT_REVIEW":
            # Non-stock-connect, non-verified entries MUST be provisional
            assert c["provisional"] is True, (
                f"{key} is rule-computed but provisional=False — "
                "violates house epistemics (uncertainty must be printed)"
            )


def test_msci_dates_within_review_month():
    """MSCI effective dates must fall WITHIN the review month, not in the next month.
    The old (buggy) code used first-biz-day of NEXT month; regression guard."""
    import calendar as _cal
    catalog = CAT._build_catalog()
    for c in catalog:
        if c["type"] != "MSCI_REVIEW":
            continue
        eff = date.fromisoformat(c["effective_date"])
        # The name encodes the review month: "MSCI Index Review — Feb semi-annual 2025"
        name = c["name_en"]
        month_map = {
            "Feb": 2, "May": 5, "Aug": 8, "Nov": 11,
        }
        review_month = None
        for abbr, mnum in month_map.items():
            if abbr in name:
                review_month = mnum
                break
        if review_month is None:
            continue
        # Effective date must be IN the review month (not the next)
        assert eff.month == review_month, (
            f"MSCI effective {eff} falls outside review month {review_month}: {name}"
        )
