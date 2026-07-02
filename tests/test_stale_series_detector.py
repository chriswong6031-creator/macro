"""Tests for the frozen-tail stale_series detector (collectors/base.py).

The failure mode: a 200-OK FRED fetch whose last observation never advances
(series discontinued upstream) is invisible to is_connection_error and to the
adapter-level stale check (which only looks at the *adapter's* max last_date,
not per-series dates).  detect_stale_series catches it by comparing each
series' last observation against the expected cadence × multiplier.

These tests also cover the intl macro config changes (W0 items 2+3):
  - dead M2 series removed from config (JP/KR/EZ/GB)
  - JP cpi_yoy removed (no live FRED replacement)
  - KR cpi_yoy remapped: CPALTT01KRM659N → KORCPICORMINMEI
  - EZ unemployment removed (no live FRED replacement)
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.base import detect_stale_series, _write_stale_series  # noqa: E402
from lib import config  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _frame(last_date: date, n: int = 100) -> pd.DataFrame:
    idx = pd.date_range(end=last_date, periods=n, freq="MS")
    return pd.DataFrame({"value": range(n)}, index=idx)


def _frames_with_age(ages_days: dict[str, int]) -> dict[str, pd.DataFrame]:
    today = datetime.now(timezone.utc).date()
    return {
        name: _frame(today - timedelta(days=age))
        for name, age in ages_days.items()
    }


# ---------------------------------------------------------------------------
# detect_stale_series core behaviour
# ---------------------------------------------------------------------------

def test_no_stale_when_all_fresh():
    """Series updated within cadence × multiplier are not flagged."""
    frames = _frames_with_age({"JP_yield_10y": 10, "EZ_cpi_yoy": 20})
    result = detect_stale_series("intl_macro", frames, cadence_days=45)
    assert result == []


def test_detects_frozen_tail():
    """A series whose last obs is older than cadence × 3 is flagged."""
    frames = _frames_with_age({"JP_cpi_yoy": 1800, "JP_yield_10y": 5})
    result = detect_stale_series("intl_macro", frames, cadence_days=45)
    assert len(result) == 1
    entry = result[0]
    assert entry["series"] == "JP_cpi_yoy"
    assert entry["group"] == "intl_macro"
    assert entry["age_days"] >= 1800
    assert entry["cadence_days"] == 45


def test_detects_multiple_frozen_tails():
    """All series beyond the threshold are reported."""
    frames = _frames_with_age({
        "JP_cpi_yoy": 1800,    # dead since 2021-06
        "KR_cpi_yoy": 950,     # dead since 2023-11
        "EZ_unemployment": 1250,  # dead since 2023-01
        "EZ_m2": 3400,         # dead since 2017-03
        "JP_yield_10y": 30,    # live
    })
    result = detect_stale_series("intl_macro", frames, cadence_days=45)
    stale_names = {e["series"] for e in result}
    assert stale_names == {"JP_cpi_yoy", "KR_cpi_yoy", "EZ_unemployment", "EZ_m2"}
    assert "JP_yield_10y" not in stale_names


def test_threshold_uses_multiplier():
    """Multiplier scales the threshold; default 3× cadence."""
    cadence = 45
    # Just outside default 3× window (46*3=138 days -> stale if age > 135)
    frames = _frames_with_age({"borderline": 140})
    result = detect_stale_series("intl_macro", frames, cadence_days=cadence)
    assert len(result) == 1, "140d > 45×3=135 should be stale"

    frames2 = _frames_with_age({"borderline": 100})
    result2 = detect_stale_series("intl_macro", frames2, cadence_days=cadence)
    assert result2 == [], "100d < 45×3=135 should be fresh"


def test_custom_multiplier():
    frames = _frames_with_age({"s": 60})
    # 2× cadence=45 → threshold=90; age=60 is fresh
    assert detect_stale_series("intl_macro", frames, cadence_days=45, multiplier=2.0) == []
    # 1× cadence=45 → threshold=45; age=60 is stale
    result = detect_stale_series("intl_macro", frames, cadence_days=45, multiplier=1.0)
    assert len(result) == 1


def test_empty_frame_does_not_crash():
    """Empty or all-NaN frames are silently skipped (non-fatal)."""
    today = datetime.now(timezone.utc).date()
    frames = {
        "empty": pd.DataFrame({"v": []}, index=pd.DatetimeIndex([])),
        "all_nan": pd.DataFrame({"v": [float("nan")]},
                                index=pd.DatetimeIndex([today])),
        "live": _frame(today, n=10),
    }
    result = detect_stale_series("intl_macro", frames, cadence_days=45)
    assert result == [], "empty/NaN frames must not produce false stale entries"


def test_result_fields_complete():
    """Each stale entry must carry group, series, last_obs, cadence_days, age_days."""
    frames = _frames_with_age({"dead": 500})
    result = detect_stale_series("test_group", frames, cadence_days=30)
    assert len(result) == 1
    e = result[0]
    for key in ("group", "series", "last_obs", "cadence_days", "age_days"):
        assert key in e, f"missing field: {key}"
    assert e["group"] == "test_group"
    assert e["series"] == "dead"
    assert e["age_days"] >= 500


# ---------------------------------------------------------------------------
# Intl macro config validation — dead series removed, KR cpi remapped
# ---------------------------------------------------------------------------

def test_m2_removed_from_intl_config():
    """Dead M2 series (frozen since 2017) must not appear in config.

    M2 is not rendered in the intl template; removing it from the collection
    plan is an honest deprecation, not a data loss.
    """
    countries = config.load()["intl"]["countries"]
    for cc in ("JP", "KR", "EZ", "GB"):
        fred = countries.get(cc, {}).get("fred", {})
        assert "m2" not in fred, (
            f"{cc}.fred.m2 still in config — dead series (frozen since 2017) "
            f"should be removed"
        )


def test_jp_cpi_removed_from_intl_config():
    """JP cpi_yoy (CPALTT01JPM659N, frozen 2021-06) has no live FRED replacement.
    It must be removed so the frozen-tail detector doesn't fire on every collect.
    """
    jp_fred = config.load()["intl"]["countries"]["JP"]["fred"]
    assert "cpi_yoy" not in jp_fred, (
        "JP cpi_yoy still in config — CPALTT01JPM659N is frozen at 2021-06 "
        "with no live keyless FRED replacement"
    )


def test_ez_unemployment_removed_from_intl_config():
    """EZ unemployment (LRHUTTTTEZM156S, frozen 2023-01) has no live FRED
    replacement. It must be removed so the frozen-tail detector doesn't fire.
    """
    ez_fred = config.load()["intl"]["countries"]["EZ"]["fred"]
    assert "unemployment" not in ez_fred, (
        "EZ unemployment still in config — LRHUTTTTEZM156S is frozen at 2023-01 "
        "with no live keyless FRED replacement"
    )


def test_kr_cpi_remapped_to_live_id():
    """KR cpi_yoy remapped from CPALTT01KRM659N (frozen 2023-11) to
    KORCPICORMINMEI (OECD core CPI, current through 2025-04).
    """
    kr_fred = config.load()["intl"]["countries"]["KR"]["fred"]
    assert kr_fred.get("cpi_yoy") == "KORCPICORMINMEI", (
        f"KR cpi_yoy should be KORCPICORMINMEI, got {kr_fred.get('cpi_yoy')!r}"
    )


def test_live_intl_series_ids_unchanged():
    """Sanity: the live yield/unemployment/gdp series that are NOT dead must
    still be present after the triage edits.
    """
    countries = config.load()["intl"]["countries"]
    # JP: yields, rates, unemployment, gdp all still present
    jp = countries["JP"]["fred"]
    for key in ("yield_10y", "short_3m", "unemployment", "gdp"):
        assert key in jp, f"JP.{key} missing — should not have been removed"
    # EZ: cpi, yield, gdp still present; only unemployment removed
    ez = countries["EZ"]["fred"]
    for key in ("yield_10y", "short_3m", "cpi_yoy", "gdp"):
        assert key in ez, f"EZ.{key} missing — should not have been removed"
    # GB: no m2, but the rest intact
    gb = countries["GB"]["fred"]
    for key in ("yield_10y", "short_3m", "cpi_yoy", "unemployment", "gdp"):
        assert key in gb, f"GB.{key} missing — should not have been removed"
