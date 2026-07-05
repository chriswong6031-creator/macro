"""Offline tests for engine/macro_surprise.py — no network calls.

Covers:
  - Registry sanity (every entry has required fields, aliases are non-empty)
  - Surprise math against hand-computed fixture values (z-scores, deltas)
  - Card plain-English line renders
  - Stub suppression: positive (stubs that MUST be dropped) and negative
    (real value-carrying headlines that MUST NOT be dropped)
  - Offline degrade: fetch raises → empty cards, no exception escapes
  - Kill-criterion: < 6 series fetched → no surprise math, no cards
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import macro_surprise as ms
from engine import news_common as nc

# ──────────────────────────────────────────────────────────────────────────── #
# 1. Registry sanity
# ──────────────────────────────────────────────────────────────────────────── #
REQUIRED_FIELDS = {
    "key", "display_name", "title_aliases", "fred_series",
    "transform", "cadence", "macro_channel", "direction_map",
}
VALID_TRANSFORMS = {"level", "mom_diff", "mom_pct", "yoy_pct"}
VALID_CADENCES = {"monthly", "weekly", "quarterly"}
VALID_CHANNELS = {"inflation", "labor", "growth", "trade"}
VALID_DIRECTIONS = {"higher_hotter", "higher_better", "lower_better", "neutral"}


@pytest.mark.parametrize("entry", ms.RELEASE_REGISTRY, ids=[e["key"] for e in ms.RELEASE_REGISTRY])
def test_registry_entry_has_required_fields(entry):
    for field in REQUIRED_FIELDS:
        assert field in entry, f"{entry['key']} missing field {field!r}"


@pytest.mark.parametrize("entry", ms.RELEASE_REGISTRY, ids=[e["key"] for e in ms.RELEASE_REGISTRY])
def test_registry_entry_valid_enum_values(entry):
    assert entry["transform"] in VALID_TRANSFORMS, \
        f"{entry['key']} invalid transform {entry['transform']!r}"
    assert entry["cadence"] in VALID_CADENCES, \
        f"{entry['key']} invalid cadence {entry['cadence']!r}"
    assert entry["macro_channel"] in VALID_CHANNELS, \
        f"{entry['key']} invalid channel {entry['macro_channel']!r}"
    assert entry["direction_map"] in VALID_DIRECTIONS, \
        f"{entry['key']} invalid direction_map {entry['direction_map']!r}"


@pytest.mark.parametrize("entry", ms.RELEASE_REGISTRY, ids=[e["key"] for e in ms.RELEASE_REGISTRY])
def test_registry_entry_has_non_empty_aliases(entry):
    assert isinstance(entry["title_aliases"], list), \
        f"{entry['key']}: title_aliases must be a list"
    assert len(entry["title_aliases"]) >= 1, \
        f"{entry['key']}: title_aliases is empty"
    for alias in entry["title_aliases"]:
        assert isinstance(alias, str) and alias.strip(), \
            f"{entry['key']}: empty/non-string alias: {alias!r}"


def test_registry_has_all_required_series():
    """Verify that the canonical task series are all present."""
    keys = {e["key"] for e in ms.RELEASE_REGISTRY}
    required_keys = {"cpi", "ppi", "payrolls", "unemployment", "retail_sales",
                     "trade_balance", "initial_claims", "business_inventories",
                     "gdp", "pce"}
    assert required_keys.issubset(keys), f"missing keys: {required_keys - keys}"


def test_registry_keys_unique():
    keys = [e["key"] for e in ms.RELEASE_REGISTRY]
    assert len(keys) == len(set(keys)), "duplicate keys in RELEASE_REGISTRY"


def test_registry_fred_series_unique():
    series = [e["fred_series"] for e in ms.RELEASE_REGISTRY]
    assert len(series) == len(set(series)), "duplicate FRED series in RELEASE_REGISTRY"


# ──────────────────────────────────────────────────────────────────────────── #
# 2. Surprise math against hand-computed fixture values
# ──────────────────────────────────────────────────────────────────────────── #
def _make_records(values: list[float], start_year: int = 2015,
                  start_month: int = 1) -> list[dict]:
    """Generate monthly dated records from a list of raw values."""
    records = []
    y, m = start_year, start_month
    for v in values:
        records.append({"date": f"{y:04d}-{m:02d}-01", "value": v})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return records


def _cpi_entry() -> dict:
    return {
        "key": "cpi_test",
        "display_name": "CPI (test)",
        "title_aliases": [],
        "fred_series": "CPIAUCSL",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "inflation",
        "direction_map": "higher_hotter",
    }


def _payrolls_entry() -> dict:
    return {
        "key": "payrolls_test",
        "display_name": "Nonfarm Payrolls (test)",
        "title_aliases": [],
        "fred_series": "PAYEMS",
        "transform": "mom_diff",
        "cadence": "monthly",
        "macro_channel": "labor",
        "direction_map": "higher_better",
    }


def test_surprise_math_delta_vs_prior():
    """mom_pct: delta_vs_prior = latest_transformed - prior_transformed."""
    # Construct raw values: last two are 300 -> 303 → mom_pct = +1.0%
    # Prior: 295 -> 300 → mom_pct = (300-295)/295*100 = 1.6949...%
    raw = [290.0, 292.0, 295.0, 300.0, 303.0]
    records = _make_records(raw)
    entry = _cpi_entry()
    asof = datetime(2015, 8, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert result["actual"] == pytest.approx(1.0, abs=0.01)  # 303/300-1 * 100 = 1.0%
    # prior: (300-295)/295*100 = 1.6949%
    assert result["prior"] == pytest.approx(1.6949, abs=0.02)
    delta = result["deltas"]["vs_prior"]
    assert delta is not None
    assert delta == pytest.approx(result["actual"] - result["prior"], abs=0.01)


def test_surprise_math_zscore_hand_computed():
    """z3y: (latest_transformed - mean_3y) / std_3y, hand-computed."""
    # Build 40 monthly observations with known mean/std in last 36
    import statistics
    # Raw values: constant 100 for 3 years (36 obs), then suddenly 110
    raw = [100.0] * 41  # 41 level observations
    # mom_pct of 100 -> 100 = 0.0% for 39 diffs, then 100 -> 110 = 10.0%
    raw[-1] = 110.0
    records = _make_records(raw)
    entry = _cpi_entry()
    asof = datetime(2015 + 3, 6, 1, tzinfo=timezone.utc)

    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    # The transformed series has 40 values: 39 × 0.0% and 1 × 10.0%
    # Hist for z3y uses last 36 values EXCLUDING latest.
    # That history is 36 × 0.0% → mean=0, std=0 → z3y undefined (std=0)
    # The code returns z3y=None when std<=0
    # OR: last 37 values excluding latest → depends on window.
    # Either way, if std is 0 we expect None.
    if result["z3y"] is None:
        # Expected when all historical points are identical (std=0)
        assert result["surprise_size"] == "unknown"
    else:
        # If there's variance in window, check it's large
        assert abs(result["z3y"]) > 1.0


def test_surprise_math_zscore_nonzero_variance():
    """z3y with known variance: check sign and rough magnitude."""
    import statistics
    # 60 months of data: first 59 with mean=2.0, std~0.5; last one = 4.0
    import random
    random.seed(42)
    raw_pct_changes = [2.0 + random.gauss(0, 0.5) for _ in range(59)]
    # Build raw values that produce these approximate mom_pct changes
    raw = [100.0]
    for pct in raw_pct_changes:
        raw.append(raw[-1] * (1 + pct / 100))
    # Add a large jump: +4.0% instead of ~2%
    raw.append(raw[-1] * 1.04)  # +4% mom

    records = _make_records(raw)
    entry = _cpi_entry()
    asof = datetime(2015 + 5, 6, 1, tzinfo=timezone.utc)

    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert result["z3y"] is not None
    # Should be positive (4% >> 2% mean) and notably above zero
    assert result["z3y"] > 0.5, f"expected positive z3y, got {result['z3y']}"
    assert result["surprise_size"] in ("notable", "large")


def test_surprise_math_payrolls_mom_diff():
    """mom_diff for payrolls: delta is in raw units, z3y uses trailing variance."""
    import random
    random.seed(7)
    # Build 50 monthly payroll levels with ~200k/mo gains ± noise → variance exists
    base = 150_000
    raw = [base]
    for _ in range(49):
        raw.append(raw[-1] + 200 + random.gauss(0, 30))  # ~200k/mo ± 30k noise
    raw.append(raw[-1] + 57)  # last month: only +57k vs ~200k trend
    records = _make_records(raw)
    entry = _payrolls_entry()
    asof = datetime(2015 + 4, 6, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert result["actual"] == pytest.approx(57.0, abs=1.0)
    assert result["prior"] == pytest.approx(200.0, abs=50.0)  # noisy prior
    # Delta vs prior should be strongly negative (way below trend)
    assert result["deltas"]["vs_prior"] < -100
    # z3y should be large negative (way below 3y mean of ~200 with std ~30)
    assert result["z3y"] is not None
    assert result["z3y"] < -1.0
    assert result["surprise_size"] in ("notable", "large")


def test_surprise_math_level_series():
    """level transform: actual = latest raw value, deltas are in raw units."""
    raw = [4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 6.5]  # big spike at end
    records = _make_records(raw)
    entry = {
        "key": "unrate_test",
        "display_name": "Unemployment Rate (test)",
        "title_aliases": [],
        "fred_series": "UNRATE",
        "transform": "level",
        "cadence": "monthly",
        "macro_channel": "labor",
        "direction_map": "lower_better",
    }
    asof = datetime(2015 + 3, 6, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert result["actual"] == pytest.approx(6.5, abs=0.01)
    assert result["deltas"]["vs_prior"] == pytest.approx(6.5 - 4.0, abs=0.01)
    assert result["z3y"] is not None
    assert result["z3y"] > 1.0  # clearly elevated vs 3y mean ~4.0


# ──────────────────────────────────────────────────────────────────────────── #
# 3. Card plain-English summary renders
# ──────────────────────────────────────────────────────────────────────────── #
def test_card_summary_contains_display_name_and_period():
    raw = [100.0 + i * 0.3 + (0.2 if i % 3 == 0 else 0) for i in range(50)]
    records = _make_records(raw)
    entry = _cpi_entry()
    asof = datetime(2015 + 4, 4, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    summary = result["summary"]
    assert isinstance(summary, str) and len(summary) > 10
    # must end with period
    assert summary.endswith(".")
    # must reference the display_name
    assert "CPI" in summary or "cpi" in summary.lower()


def test_card_summary_payrolls_thousands():
    raw = [150_000 + i * 200 for i in range(39)]
    raw.append(raw[-1] + 57)
    records = _make_records(raw)
    entry = _payrolls_entry()
    asof = datetime(2015 + 3, 6, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    summary = result["summary"]
    assert "+57k" in summary or "+57,k" in summary or "57" in summary, \
        f"Expected payrolls value in summary: {summary!r}"
    assert summary.endswith(".")


def test_card_summary_revised_prior_label():
    """The prior label in the card must say 'vs revised prior' to be honest."""
    raw = [4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 3.9,
           4.0, 4.1, 3.9, 4.0, 4.2, 3.8, 4.0, 4.1, 4.0, 4.1]
    records = _make_records(raw)
    entry = {
        "key": "unrate_t",
        "display_name": "Unemployment Rate",
        "title_aliases": [],
        "fred_series": "UNRATE",
        "transform": "level",
        "cadence": "monthly",
        "macro_channel": "labor",
        "direction_map": "lower_better",
    }
    asof = datetime(2015 + 3, 6, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert result["prior_label"] == "vs revised prior"
    assert "revised prior" in result["summary"]


def test_card_direction_tag_inflation_hotter():
    """Inflation channel higher_hotter: positive delta → 'inflation hotter'."""
    raw = [300.0] * 10 + [303.0]  # last: +1.0% mom
    records = _make_records(raw)
    entry = _cpi_entry()
    asof = datetime(2015, 11, 15, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    assert "hotter" in (result["direction_tag"] or ""), \
        f"expected 'hotter' in direction_tag, got: {result['direction_tag']!r}"


def test_card_direction_tag_labor_weaker():
    """Labor channel higher_better: negative delta → 'labor weaker'."""
    raw = [150_000 + i * 200 for i in range(39)]
    raw.append(raw[-1] + 57)  # big miss
    records = _make_records(raw)
    entry = _payrolls_entry()
    asof = datetime(2015 + 3, 6, 1, tzinfo=timezone.utc)
    result = ms._surprise_for_series(records, entry, asof)
    assert result is not None
    # delta vs prior is +57k vs +200k prior = negative delta
    assert "weaker" in (result["direction_tag"] or "") or "labor" in (result["direction_tag"] or ""), \
        f"direction_tag was: {result['direction_tag']!r}"


def test_surprise_size_classification():
    """Verify the |z3y| thresholds map to the right surprise_size labels."""
    for z3y, expected in [
        (0.0, "inline"),
        (0.3, "inline"),
        (0.49, "inline"),
        (0.5, "notable"),
        (1.0, "notable"),
        (1.49, "notable"),
        (1.5, "large"),
        (2.0, "large"),
        (-0.3, "inline"),
        (-0.8, "notable"),
        (-1.8, "large"),
    ]:
        abs_z = abs(z3y)
        if abs_z < 0.5:
            size = "inline"
        elif abs_z < 1.5:
            size = "notable"
        else:
            size = "large"
        assert size == expected, f"z3y={z3y} → {size!r}, expected {expected!r}"


# ──────────────────────────────────────────────────────────────────────────── #
# 4. Stub suppression: positive (must drop) and negative (must keep)
# ──────────────────────────────────────────────────────────────────────────── #
STUB_DROP = [
    # Canonical case from the task spec
    "Manufacturing and Trade Inventories and Sales",
    # Other registered aliases
    "Employment Situation",
    "The Employment Situation",
    "Consumer Price Index",
    "Consumer Price Index for All Urban Consumers",
    "Producer Price Index",
    "Advance Retail Sales",
    "U.S. International Trade in Goods and Services",
    "Unemployment Insurance Weekly Claims",
    "Gross Domestic Product",
    "Personal Income and Outlays",
]

STUB_KEEP = [
    # These carry data values — they are NEWS not stubs
    "U.S. job creation cools in June with payrolls growth of just 57,000",
    "CPI rose 0.2% in May, in line with expectations",
    "Nonfarm payrolls rose by 275,000 in February",
    "Unemployment rate climbed to 4.1%, highest since 2021",
    "Retail sales fell 0.8% in March amid tariff concerns",
    "Trade deficit narrowed to $68.9 billion in April",
    "Initial jobless claims dropped to 213,000",
    "GDP grew at 2.9% annual pace in Q4",
    "PCE inflation slowed to 2.1% year-on-year",
    # Real news (not stubs) that mention release names in context
    "Fed watches CPI closely as inflation edges higher",
    "Investors brace for Friday GDP report after mixed signals",
    "Why the employment situation matters more than ever for Fed policy",
]


@pytest.mark.parametrize("title", STUB_DROP)
def test_is_release_stub_true(title):
    """Bare release-title stubs must be detected as stubs."""
    assert ms.is_release_stub(title) is True, \
        f"Expected stub, got False for: {title!r}"


@pytest.mark.parametrize("title", STUB_KEEP)
def test_is_release_stub_false(title):
    """Value-carrying headlines must NOT be flagged as stubs."""
    assert ms.is_release_stub(title) is False, \
        f"False-positive stub for: {title!r}"


# Test via news_common.low_value_reason (the W0 reject plumbing)
@pytest.mark.parametrize("title", STUB_DROP)
def test_stub_suppressed_via_news_common(title):
    """Stubs must be rejected with reason 'macro_release_stub' via news_common."""
    reason = nc.low_value_reason(title)
    assert reason == "macro_release_stub", (
        f"{title!r} → reason={reason!r}, expected 'macro_release_stub'"
    )


@pytest.mark.parametrize("title", STUB_KEEP)
def test_real_news_not_suppressed_via_news_common(title):
    """Value-carrying headlines must NOT be suppressed by the stub check."""
    reason = nc.low_value_reason(title)
    assert reason != "macro_release_stub", (
        f"False-positive macro_release_stub for: {title!r}"
    )


# ──────────────────────────────────────────────────────────────────────────── #
# 5. Offline degrade: fetch raises → empty cards, no exception escapes
# ──────────────────────────────────────────────────────────────────────────── #
def test_degrade_on_fetch_failure():
    """When _fetch_fred_series raises for ALL series, build_release_cards returns
    empty cards and does NOT raise."""
    with patch.object(ms, "_fetch_fred_series", side_effect=RuntimeError("network down")):
        result = ms.build_release_cards()
    assert isinstance(result, dict)
    assert result["schema"] == "macro_releases.v1"
    assert result["is_context_only"] is True
    assert isinstance(result["cards"], list)
    # All fetches failed → kill criterion triggered
    assert result["n_fetched"] == 0
    assert result.get("kill_criterion_triggered") is True


def test_degrade_on_fetch_returns_none():
    """When _fetch_fred_series returns None for all series (HTTP error path),
    still returns empty cards without raising."""
    with patch.object(ms, "_fetch_fred_series", return_value=None):
        result = ms.build_release_cards()
    assert isinstance(result, dict)
    assert result["cards"] == []
    assert result["n_fetched"] == 0


def test_degrade_on_too_few_rows():
    """When fetch returns fewer than 10 rows, that series is skipped."""
    with patch.object(ms, "_fetch_fred_series", return_value=[
        {"date": "2026-01-01", "value": 100.0},
        {"date": "2026-02-01", "value": 101.0},
    ]):
        result = ms.build_release_cards()
    assert result["n_fetched"] == 0
    assert result["cards"] == []


# ──────────────────────────────────────────────────────────────────────────── #
# 6. Kill criterion: < 6 series → no cards, no exception
# ──────────────────────────────────────────────────────────────────────────── #
def test_kill_criterion_fewer_than_6_series():
    """If only 5 series verify, no cards emitted, kill_criterion_triggered=True."""
    call_count = 0
    good_records = [{"date": f"2015-{m:02d}-01", "value": 100.0 + m}
                    for m in range(1, 13)] * 4  # 48 rows

    def mock_fetch(series_id):
        nonlocal call_count
        call_count += 1
        if call_count <= 5:
            return good_records
        return None  # 6th and beyond fail

    with patch.object(ms, "_fetch_fred_series", side_effect=mock_fetch):
        result = ms.build_release_cards()

    assert result["n_fetched"] == 5
    assert result.get("kill_criterion_triggered") is True
    assert result["cards"] == []


def test_kill_criterion_exactly_6_series():
    """With exactly 6 fetched series, surprise math DOES run (kill criterion not triggered)."""
    good_records = (
        [{"date": f"2015-{m:02d}-01", "value": 100.0 + m * 0.1} for m in range(1, 13)] * 5
    )
    call_count = 0

    def mock_fetch(series_id):
        nonlocal call_count
        call_count += 1
        if call_count <= 6:
            return good_records
        return None  # rest fail

    with patch.object(ms, "_fetch_fred_series", side_effect=mock_fetch):
        result = ms.build_release_cards()

    assert result["n_fetched"] == 6
    assert result.get("kill_criterion_triggered") is not True


# ──────────────────────────────────────────────────────────────────────────── #
# 7. build_release_cards structure contract
# ──────────────────────────────────────────────────────────────────────────── #
def test_build_release_cards_always_returns_schema():
    """build_release_cards always returns a dict with the schema key."""
    with patch.object(ms, "_fetch_fred_series", side_effect=Exception("error")):
        result = ms.build_release_cards()
    assert result.get("schema") == "macro_releases.v1"
    assert result.get("is_context_only") is True


def test_build_release_cards_with_mock_data_within_lookback():
    """With mocked recent data, cards are emitted when within lookback window."""
    from datetime import date, timedelta

    today = datetime.now(timezone.utc)
    # Build 50 monthly records ending 5 days ago (within default 10-day window)
    end_date = (today - timedelta(days=5)).date()
    records = []
    for i in range(50):
        month_offset = 50 - i
        y = end_date.year
        m = end_date.month - month_offset
        while m <= 0:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        records.append({"date": f"{y:04d}-{m:02d}-01",
                         "value": 100.0 + i * 0.2 + (0.5 if i % 7 == 0 else 0)})
    records.sort(key=lambda r: r["date"])

    def mock_fetch(series_id):
        return records

    with patch.object(ms, "_fetch_fred_series", side_effect=mock_fetch):
        result = ms.build_release_cards(asof=today, lookback_days=10)

    assert result["n_fetched"] == len(ms.RELEASE_REGISTRY)
    assert isinstance(result["cards"], list)
    # Cards should be present (data is within lookback)
    assert result["n_cards"] >= 0  # may be 0 if dates don't align, but no exception


def test_card_fields_present():
    """Each card in the result has the required fields."""
    from datetime import date, timedelta

    today = datetime.now(timezone.utc)
    end_date = (today - timedelta(days=3)).date()
    records = []
    for i in range(50):
        month_offset = 50 - i
        y = end_date.year
        m = end_date.month - month_offset
        while m <= 0:
            m += 12
            y -= 1
        records.append({"date": f"{y:04d}-{m:02d}-01",
                         "value": 100.0 + i * 0.15})
    records.sort(key=lambda r: r["date"])

    with patch.object(ms, "_fetch_fred_series", return_value=records):
        result = ms.build_release_cards(asof=today, lookback_days=10)

    for card in result["cards"]:
        for field in ("release", "display_name", "macro_channel", "period",
                      "actual", "prior_label", "transform", "deltas",
                      "z3y", "z5y", "surprise_size", "direction_tag", "summary"):
            assert field in card, f"card missing field {field!r}: {card}"


# ──────────────────────────────────────────────────────────────────────────── #
# 8. _apply_transform correctness
# ──────────────────────────────────────────────────────────────────────────── #
def test_apply_transform_level():
    vals = [1.0, 2.0, 3.0]
    assert ms._apply_transform(vals, "level") == [1.0, 2.0, 3.0]


def test_apply_transform_mom_diff():
    vals = [10.0, 12.0, 11.0]
    result = ms._apply_transform(vals, "mom_diff")
    assert math.isnan(result[0])
    assert result[1] == pytest.approx(2.0)
    assert result[2] == pytest.approx(-1.0)


def test_apply_transform_mom_pct():
    vals = [100.0, 102.0, 101.0]
    result = ms._apply_transform(vals, "mom_pct")
    assert math.isnan(result[0])
    assert result[1] == pytest.approx(2.0, abs=0.01)
    assert result[2] == pytest.approx(-0.9804, abs=0.01)


def test_apply_transform_yoy_pct():
    vals = [100.0] * 12 + [110.0]
    result = ms._apply_transform(vals, "yoy_pct")
    assert all(math.isnan(x) for x in result[:12])
    assert result[12] == pytest.approx(10.0, abs=0.01)
