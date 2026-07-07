"""Tests for the SEC FTD collector (collectors/sec_ftd.py).

Pure-function level tests with tiny fixtures — no network, no disk I/O to
the canonical data store.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sec_ftd import (
    _all_file_specs,
    _availability_date,
    _file_key,
    _parse_zip,
    _period_end,
    PIT_LAG_DAYS,
)


# ──────────────────────────────────────────────────────────────────────────────
# _file_key
# ──────────────────────────────────────────────────────────────────────────────

def test_file_key_format():
    assert _file_key(2024, 6, "a") == "202406a"
    assert _file_key(2009, 7, "b") == "200907b"
    assert _file_key(2026, 12, "a") == "202612a"


# ──────────────────────────────────────────────────────────────────────────────
# _period_end
# ──────────────────────────────────────────────────────────────────────────────

def test_period_end_first_half():
    pe = _period_end(2024, 6, "a")
    assert pe == date(2024, 6, 15)


def test_period_end_second_half_midyear():
    pe = _period_end(2024, 6, "b")
    assert pe == date(2024, 6, 30)


def test_period_end_second_half_december():
    pe = _period_end(2024, 12, "b")
    assert pe == date(2024, 12, 31)


def test_period_end_february():
    pe = _period_end(2024, 2, "b")
    # 2024 is a leap year
    assert pe == date(2024, 2, 29)


def test_period_end_november():
    pe = _period_end(2023, 11, "b")
    assert pe == date(2023, 11, 30)


# ──────────────────────────────────────────────────────────────────────────────
# _availability_date (PIT lag enforcement)
# ──────────────────────────────────────────────────────────────────────────────

def test_availability_date_uniform_30d_lag():
    """Both 'a' and 'b' halves must use the same 30-day lag (conservative uniform)."""
    avail_a = _availability_date(2024, 6, "a")
    avail_b = _availability_date(2024, 6, "b")

    period_end_a = _period_end(2024, 6, "a")
    period_end_b = _period_end(2024, 6, "b")

    # Both must be period_end + exactly PIT_LAG_DAYS
    assert avail_a == period_end_a + timedelta(days=PIT_LAG_DAYS)
    assert avail_b == period_end_b + timedelta(days=PIT_LAG_DAYS)


def test_pit_lag_is_30():
    """PIT_LAG_DAYS must be exactly 30 (pre-registered)."""
    assert PIT_LAG_DAYS == 30


def test_availability_date_first_half_2024_june():
    avail = _availability_date(2024, 6, "a")
    # period_end = June 15, lag = 30 days → July 15
    assert avail == date(2024, 7, 15)


def test_availability_date_second_half_2024_june():
    avail = _availability_date(2024, 6, "b")
    # period_end = June 30, lag = 30 days → July 30
    assert avail == date(2024, 7, 30)


# ──────────────────────────────────────────────────────────────────────────────
# _all_file_specs
# ──────────────────────────────────────────────────────────────────────────────

def test_all_file_specs_starts_from_2009_july():
    """Data begins 2009-07; no specs should appear before that."""
    specs = _all_file_specs(start_year=2009)
    # All keys should be >= 200907
    years_halves = [(s["yr"], s["mo"], s["half"]) for s in specs]
    assert all((yr > 2009 or (yr == 2009 and mo >= 7))
               for yr, mo, _ in years_halves)


def test_all_file_specs_excludes_future_available():
    """Files whose availability_date is in the future should not appear."""
    import datetime
    today = datetime.date.today()
    specs = _all_file_specs()
    for s in specs:
        assert s["avail_date"] <= today, \
            f"Future file included: {s['key']} avail={s['avail_date']}"


def test_all_file_specs_has_two_halves_per_month():
    """Each covered month should have exactly two specs (a and b)."""
    specs = _all_file_specs(start_year=2020,
                             end_date=date(2020, 3, 31))
    # Filter to months fully within range (availability_date would allow)
    by_month: dict[tuple, list] = {}
    for s in specs:
        k = (s["yr"], s["mo"])
        by_month.setdefault(k, []).append(s["half"])

    # Each available month should have both halves (or just 'a' if 'b' isn't yet available)
    for (yr, mo), halves in by_month.items():
        assert len(halves) <= 2
        assert all(h in ("a", "b") for h in halves)


# ──────────────────────────────────────────────────────────────────────────────
# _parse_zip
# ──────────────────────────────────────────────────────────────────────────────

def _make_zip(content: str, filename: str = "cnsfails202406a.txt") -> bytes:
    """Helper: create an in-memory zip with a single text file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, content)
    return buf.getvalue()


def test_parse_zip_basic():
    """Standard pipe-delimited FTD file parses correctly."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20240601|594918104|MSFT|1000|MICROSOFT CORP|420.50\n"
        "20240601|037833100|AAPL|500|APPLE INC|190.25\n"
    )
    avail = date(2024, 7, 15)
    df = _parse_zip(_make_zip(content), "202406a", avail)

    assert len(df) == 2
    assert set(df.columns) == {"date", "symbol", "cusip", "ftd_shares", "price",
                               "availability_date", "_file_key"}
    assert set(df["symbol"]) == {"MSFT", "AAPL"}
    assert df.loc[df["symbol"] == "MSFT", "ftd_shares"].iloc[0] == 1000.0
    assert df.loc[df["symbol"] == "AAPL", "price"].iloc[0] == 190.25
    assert all(df["availability_date"] == pd.Timestamp(avail))
    assert all(df["_file_key"] == "202406a")


def test_parse_zip_skips_header_and_blank():
    """Header line and blank lines must be skipped."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "\n"
        "20240601|594918104|MSFT|1000|MICROSOFT CORP|420.50\n"
        "\n"
    )
    df = _parse_zip(_make_zip(content), "202406a", date(2024, 7, 15))
    assert len(df) == 1


def test_parse_zip_handles_missing_price():
    """Empty price field is stored as NaN (not a crash)."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20240601|594918104|MSFT|1000|MICROSOFT CORP|\n"
    )
    df = _parse_zip(_make_zip(content), "202406a", date(2024, 7, 15))
    assert len(df) == 1
    assert pd.isna(df["price"].iloc[0])


def test_parse_zip_bad_zip_returns_empty():
    """Garbage bytes should return an empty DataFrame (not raise)."""
    df = _parse_zip(b"not a zip", "202406a", date(2024, 7, 15))
    assert df.empty


def test_parse_zip_symbol_uppercased():
    """Symbols should be normalized to uppercase."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20240601|594918104|msft|1000|MICROSOFT CORP|420.50\n"
    )
    df = _parse_zip(_make_zip(content), "202406a", date(2024, 7, 15))
    assert df["symbol"].iloc[0] == "MSFT"


def test_parse_zip_availability_date_stamped():
    """availability_date must equal the avail_date argument (PIT stamp)."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20240601|594918104|MSFT|1000|MICROSOFT CORP|420.50\n"
    )
    avail = date(2024, 8, 14)  # arbitrary test date
    df = _parse_zip(_make_zip(content), "202406a", avail)
    assert all(df["availability_date"] == pd.Timestamp(avail))


def test_parse_zip_multiple_dates():
    """File with multiple settlement dates parses all rows."""
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20240601|594918104|MSFT|1000|MICROSOFT CORP|420.50\n"
        "20240602|594918104|MSFT|800|MICROSOFT CORP|419.00\n"
        "20240603|037833100|AAPL|200|APPLE INC|191.00\n"
    )
    df = _parse_zip(_make_zip(content), "202406a", date(2024, 7, 15))
    assert len(df) == 3
    assert df["date"].nunique() == 3


# ──────────────────────────────────────────────────────────────────────────────
# PIT invariant: no row uses data ahead of its availability_date
# ──────────────────────────────────────────────────────────────────────────────

def test_pit_invariant_all_specs():
    """availability_date must be > period_end for all specs (lag is always positive)."""
    specs = _all_file_specs(start_year=2009, end_date=date(2024, 12, 31))
    for s in specs:
        assert s["avail_date"] > s["period_end"], \
            f"PIT violation: {s['key']} avail={s['avail_date']} <= period_end={s['period_end']}"
