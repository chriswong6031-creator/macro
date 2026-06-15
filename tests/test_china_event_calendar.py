"""Pure-logic tests for engine.china_event_calendar — no network, no data fetch.

The module is pure date arithmetic over a hand-authored China release cadence, so the
suite is hermetic and deterministic for a fixed `asof`. We assert: the date-arithmetic
helpers, the recurring-cadence placement (LPR on the 20th, PMI on the last calendar
day), the horizon-window filter, the sort order, the bilingual fields, the
imminent-line one-liner, and the DISPLAY-only / no-dampener contract.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_event_calendar as cc  # noqa: E402

# A fixed Monday in mid-June 2026 (matches the live regime date used in the smoke).
T = date(2026, 6, 15)


# --------------------------------------------------------------------------- #
# date arithmetic helpers
# --------------------------------------------------------------------------- #
def test_last_day_of_month():
    assert cc.last_day_of_month(2026, 6) == date(2026, 6, 30)
    assert cc.last_day_of_month(2026, 2) == date(2026, 2, 28)   # 2026 not a leap year
    assert cc.last_day_of_month(2026, 12) == date(2026, 12, 31)


def test_nth_business_day():
    # June 2026: 1st is a Monday -> 1st biz day = Jun 1, 3rd biz day = Jun 3
    assert cc.nth_business_day(2026, 6, 1) == date(2026, 6, 1)
    assert cc.nth_business_day(2026, 6, 3) == date(2026, 6, 3)
    # Aug 2026: 1st is a Saturday -> 1st biz day rolls to Mon Aug 3
    assert cc.nth_business_day(2026, 8, 1) == date(2026, 8, 3)


def test_next_business_day_onward():
    assert cc.next_business_day_onward(date(2026, 6, 15)) == date(2026, 6, 15)  # Monday stays
    # 2026-06-20 is a Saturday -> LPR fix rolls forward to Mon 2026-06-22
    assert date(2026, 6, 20).weekday() == 5
    assert cc.next_business_day_onward(date(2026, 6, 20)) == date(2026, 6, 22)


# --------------------------------------------------------------------------- #
# event placement
# --------------------------------------------------------------------------- #
def test_lpr_lands_on_or_after_the_20th():
    """The LPR fix is the 20th every month; on a weekend it rolls to the next biz day.
    June 2026's 20th is a Saturday -> the event must be the 22nd."""
    evs = cc.china_macro_events(asof=T, horizon_days=14)
    lpr = [e for e in evs if e["type"] == "LPR"]
    assert len(lpr) == 1
    assert lpr[0]["date"] == "2026-06-22"          # 20th was Sat -> Mon 22nd
    assert lpr[0]["importance"] == "high"


def test_pmi_on_last_calendar_day():
    evs = cc.china_macro_events(asof=T, horizon_days=20)        # reach Jun 30
    pmi = [e for e in evs if e["type"] == "PMI"]
    assert any(e["date"] == "2026-06-30" for e in pmi)


def test_events_sorted_by_date():
    evs = cc.china_macro_events(asof=T, horizon_days=21)
    assert evs == sorted(evs, key=lambda e: e["date"]) or \
        [e["date"] for e in evs] == sorted(e["date"] for e in evs)


def test_horizon_filter_is_inclusive_and_bounded():
    short = cc.china_macro_events(asof=T, horizon_days=3)       # Jun 15-18 only
    for e in short:
        d = date.fromisoformat(e["date"])
        assert T <= d <= date(2026, 6, 18)
    long = cc.china_macro_events(asof=T, horizon_days=21)
    assert len(long) > len(short)                              # wider window -> more events


def test_days_until_is_nonnegative_and_correct():
    evs = cc.china_macro_events(asof=T, horizon_days=14)
    for e in evs:
        assert e["days_until"] >= 0
        assert e["days_until"] == (date.fromisoformat(e["date"]) - T).days


def test_deterministic_for_fixed_asof():
    a = cc.china_macro_events(asof=T, horizon_days=14)
    b = cc.china_macro_events(asof=T, horizon_days=14)
    assert a == b


# --------------------------------------------------------------------------- #
# bilingual + display-only contract
# --------------------------------------------------------------------------- #
def test_bilingual_fields_present():
    evs = cc.china_macro_events(asof=T, horizon_days=21)
    assert evs, "expected at least one event in a 21-day window"
    for e in evs:
        assert e["name_en"] and isinstance(e["name_en"], str)
        assert e["name_zh"] and isinstance(e["name_zh"], str)
        assert e["name_en"] != e["name_zh"]                    # genuinely translated


def test_display_only_invariant():
    """Every event is context-only and carries no scored field — this panel must never
    feed china_axes / china_regime / china_playbook."""
    for e in cc.china_macro_events(asof=T, horizon_days=21):
        assert e["is_context_only"] is True
        assert e["importance"] in ("high", "med")              # a DISPLAY tier, not a score
        assert "score" not in e and "weight" not in e and "dampener" not in e


def test_high_impact_strip_filters_and_decorates():
    strip = cc.high_impact_strip(asof=T, horizon_days=21)
    assert strip, "expected high-impact items in a 21-day window"
    for s in strip:
        assert s["importance"] == "high"                       # med items filtered out
        assert s["dow"] in cc._DOW and s["dow_zh"] in cc._DOW_ZH
        assert s["md"] and s["md_zh"]                          # bilingual day labels


def test_imminent_line_bilingual_and_points_at_first_item():
    line = cc.imminent_line(asof=T, horizon_days=21)
    assert line is not None
    assert line["en"] and line["zh"] and line["en"] != line["zh"]
    strip = cc.high_impact_strip(asof=T, horizon_days=21)
    assert line["date"] == strip[0]["date"]                    # most imminent high-impact item
    assert line["days_until"] >= 0


def test_imminent_line_none_when_window_clear():
    # A 1-day window starting on a quiet Tuesday with no high-impact print.
    quiet = date(2026, 6, 23)                                  # day after the LPR fix
    line = cc.imminent_line(asof=quiet, horizon_days=0)
    assert line is None
