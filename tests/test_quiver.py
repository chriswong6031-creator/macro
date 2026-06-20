"""QuiverQuant collector parsing tests (hermetic — fixtures, no network/key)."""
from __future__ import annotations

import math

from collectors import quiver
from collectors.quiver import DATASETS, rows_to_monthly


def test_govcontracts_monthly_sum():
    rows = [{"Date": "2026-03-01", "Amount": "1000000"},
            {"Date": "2026-03-20", "Amount": 500000},
            {"Date": "2026-02-10", "Amount": 250000}]
    s = rows_to_monthly(DATASETS["govcontracts"], rows)
    assert s.loc["2026-03-01"] == 1_500_000
    assert s.loc["2026-02-01"] == 250_000


def test_congress_net_buy_is_signed():
    rows = [{"TransactionDate": "2026-03-01", "Transaction": "Purchase", "Range": "$1,001 - $15,000"},
            {"TransactionDate": "2026-03-02", "Transaction": "Sale", "Range": "$1,001 - $15,000"},
            {"TransactionDate": "2026-03-03", "Transaction": "Purchase", "Amount": 50000}]
    s = rows_to_monthly(DATASETS["congress"], rows)
    # purchase(+8000) + sale(−8000) cancel; +50000 numeric Amount remains
    assert abs(s.loc["2026-03-01"] - 50_000) < 1e-6


def test_congress_prefers_numeric_amount_over_range():
    rows = [{"Traded": "2026-04-01", "Transaction": "Purchase", "Amount": 12345, "Range": "$1 - $9"}]
    s = rows_to_monthly(DATASETS["congress"], rows)
    assert s.loc["2026-04-01"] == 12345


def test_offexchange_short_ratio_mean():
    rows = [{"Date": "2026-03-01", "Short_Volume": 40, "Total_Volume": 100},
            {"Date": "2026-03-15", "Short_Volume": 60, "Total_Volume": 100}]
    s = rows_to_monthly(DATASETS["offexchange"], rows)
    assert abs(s.loc["2026-03-01"] - 0.5) < 1e-9          # mean(0.4, 0.6)


def test_offexchange_falls_back_to_dpi():
    rows = [{"Date": "2026-03-01", "DPI": 0.55}, {"Date": "2026-03-09", "DPI": 0.45}]
    s = rows_to_monthly(DATASETS["offexchange"], rows)
    assert abs(s.loc["2026-03-01"] - 0.5) < 1e-9


def test_patents_counts_rows_when_no_value_field():
    rows = [{"Date": "2026-03-01"}, {"Date": "2026-03-02"}, {"Date": "2026-02-01"}]
    s = rows_to_monthly(DATASETS["patents"], rows)
    assert s.loc["2026-03-01"] == 2 and s.loc["2026-02-01"] == 1


def test_lobbying_sum():
    rows = [{"Date": "2026-01-15", "Amount": 70000}, {"Date": "2026-01-20", "Amount": 30000}]
    assert rows_to_monthly(DATASETS["lobbying"], rows).loc["2026-01-01"] == 100_000


def test_empty_or_missing_field_returns_none():
    assert rows_to_monthly(DATASETS["govcontracts"], []) is None
    assert rows_to_monthly(DATASETS["govcontracts"], [{"NoDate": 1, "NoAmount": 2}]) is None


def test_range_midpoint():
    assert quiver._range_mid("$1,001 - $15,000") == (1001 + 15000) / 2
    assert math.isnan(quiver._range_mid("n/a"))


def test_no_key_fetch_is_noop():
    a = quiver.QuiverAdapter()
    a.key = None
    assert a.fetch() == {}                                # graceful no-op without the key
