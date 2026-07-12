"""tests/test_flow_cohorts.py — FL-B cohort flow aggregation unit tests.

Covers:
1. Aggregation correctness on synthetic fixtures (multi-member cohort)
2. Missing-member coverage honesty counts (some members lack summary files)
3. Idempotence: two consecutive build_cohorts() calls produce byte-equal JSON
4. JSON schema contract: required keys present, direction_reliable=False
5. No-history raw_fallback flag: raw_fallback=True when < MIN_PCT_HISTORY obs
6. Volume-weighted P/C ratio computation
7. P/C tone labels (call-tilted / put-tilted / balanced)
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Allow running standalone without installing the package
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.flow_cohorts import (
    COHORTS,
    MIN_PCT_HISTORY,
    _aggregate_day,
    _pc_tone,
    _percentile_vs_history,
    _net_soft_tone,
    build_cohorts,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_summary(tmp_data: Path, ticker: str, rows: list[dict]) -> None:
    """Write a synthetic summary_<TICKER>.parquet to tmp_data/options_flow/."""
    d = tmp_data / "options_flow"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["date"])
    df = df.drop(columns=["date"])
    df.to_parquet(d / f"summary_{ticker}.parquet")


def _make_membership(tmp_data: Path, cohort_key: str, tickers: list[str]) -> None:
    """Write a minimal baskets/membership.json with the given cohort -> tickers."""
    d = tmp_data / "baskets"
    d.mkdir(parents=True, exist_ok=True)
    members = [{"ticker": t, "removed": None} for t in tickers]
    payload: dict = {"baskets": {}}
    # Seed all four basket keys to avoid KeyError in _load_cohort_members
    for c in COHORTS:
        payload["baskets"][c["basket_key"]] = {"members": []}
    payload["baskets"][cohort_key] = {"members": members}
    (d / "membership.json").write_text(json.dumps(payload))


# ── Test 1: Aggregation correctness ───────────────────────────────────────────

def test_aggregate_day_sums_correctly():
    """gross_premium_mn and net_premium_mn should be sums across covered members."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp)
        asof = date(2026, 7, 6)
        _make_summary(tmp_data, "AAA", [
            {"date": str(asof), "premium_mn": 100.0, "net_premium_mn": 30.0,
             "pc_ratio": 0.5, "volume": 1000.0, "zerodte_share": 0.4,
             "net_doi": 5000.0}
        ])
        _make_summary(tmp_data, "BBB", [
            {"date": str(asof), "premium_mn": 200.0, "net_premium_mn": -10.0,
             "pc_ratio": 1.0, "volume": 2000.0, "zerodte_share": 0.6,
             "net_doi": -2000.0}
        ])

        row = _aggregate_day(tmp_data, "test_cohort", ["AAA", "BBB"], asof)

        assert row["n_members"] == 2
        assert row["n_members_covered"] == 2
        assert row["gross_premium_mn"] == pytest.approx(300.0, abs=0.1)
        assert row["net_premium_mn"] == pytest.approx(20.0, abs=0.1)  # 30 - 10
        # net_doi = 5000 + (-2000) = 3000
        assert row["net_doi"] == pytest.approx(3000.0, abs=1)


# ── Test 2: Missing-member coverage count ─────────────────────────────────────

def test_missing_member_coverage_count():
    """Members without summary files must still count in n_members but not n_members_covered."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp)
        asof = date(2026, 7, 6)
        # Only write summary for AAA; BBB and CCC have no file
        _make_summary(tmp_data, "AAA", [
            {"date": str(asof), "premium_mn": 50.0, "net_premium_mn": 10.0,
             "pc_ratio": 0.6, "volume": 500.0, "zerodte_share": 0.3, "net_doi": None}
        ])

        row = _aggregate_day(tmp_data, "test_cohort", ["AAA", "BBB", "CCC"], asof)

        assert row["n_members"] == 3
        assert row["n_members_covered"] == 1
        assert row["gross_premium_mn"] == pytest.approx(50.0, abs=0.1)


def test_all_missing_returns_none_values():
    """When no member has a summary file, all numeric fields should be None."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp)
        asof = date(2026, 7, 6)
        (tmp_data / "options_flow").mkdir(parents=True, exist_ok=True)

        row = _aggregate_day(tmp_data, "test_cohort", ["X1", "X2"], asof)

        assert row["n_members"] == 2
        assert row["n_members_covered"] == 0
        assert row["gross_premium_mn"] is None
        assert row["net_premium_mn"] is None
        assert row["pc_ratio"] is None


# ── Test 3: Idempotence ────────────────────────────────────────────────────────

def test_build_cohorts_idempotent_json():
    """Two consecutive build_cohorts() calls must produce byte-equal cohorts.json."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp) / "data"
        tmp_site = Path(tmp) / "site" / "flowdata"

        asof = date(2026, 7, 6)
        _make_membership(tmp_data, "mag7", ["AAPL", "MSFT"])
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof), "premium_mn": 300.0, "net_premium_mn": 80.0,
             "pc_ratio": 0.6, "volume": 2000.0, "zerodte_share": 0.55, "net_doi": 10000.0}
        ])
        _make_summary(tmp_data, "MSFT", [
            {"date": str(asof), "premium_mn": 150.0, "net_premium_mn": 40.0,
             "pc_ratio": 0.5, "volume": 1000.0, "zerodte_share": 0.45, "net_doi": 5000.0}
        ])

        # Patch config.data_dir so store.upsert writes to tmp (store uses config.data_dir)
        import unittest.mock as mock
        import lib.config as cfg_mod

        def patched_data_dir():
            return tmp_data

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)
            json1 = (tmp_site / "cohorts.json").read_text()
            build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)
            json2 = (tmp_site / "cohorts.json").read_text()

        # Parse and compare (ignore built_utc timestamp)
        d1 = json.loads(json1)
        d2 = json.loads(json2)
        d1.pop("built_utc", None)
        d2.pop("built_utc", None)
        assert d1 == d2, "Second call produced different cohorts.json content"


# ── Test 4: JSON schema ────────────────────────────────────────────────────────

def test_cohorts_json_schema():
    """cohorts.json must have the required top-level keys and direction_reliable=False."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp) / "data"
        tmp_site = Path(tmp) / "site" / "flowdata"

        asof = date(2026, 7, 6)
        _make_membership(tmp_data, "mag7", ["AAPL"])
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof), "premium_mn": 500.0, "net_premium_mn": 100.0,
             "pc_ratio": 0.55, "volume": 3000.0, "zerodte_share": 0.50, "net_doi": None}
        ])

        import unittest.mock as mock
        import lib.config as cfg_mod

        def patched_data_dir():
            return tmp_data

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)

        payload = json.loads((tmp_site / "cohorts.json").read_text())

        # Required top-level keys
        for key in ("schema", "built", "built_utc", "asof", "direction_reliable",
                    "magnitude_reliable", "direction_note", "cohorts"):
            assert key in payload, f"Missing required key: {key}"

        assert payload["direction_reliable"] is False, "direction_reliable must be False"
        assert payload["magnitude_reliable"] is True, "magnitude_reliable must be True"
        assert payload["schema"] == "flow_cohorts.v1"

        # Each cohort entry must have required fields
        for c in payload["cohorts"]:
            for field in ("key", "name_en", "name_zh", "n_members", "n_members_covered",
                          "coverage_label", "pc_tone", "net_tone", "raw_fallback",
                          "spark_gross", "spark_net"):
                assert field in c, f"Cohort missing field: {field}"


# ── Test 5: Raw fallback when no history ─────────────────────────────────────

def test_raw_fallback_flag_no_history():
    """raw_fallback must be True when fewer than MIN_PCT_HISTORY obs exist."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp) / "data"
        tmp_site = Path(tmp) / "site" / "flowdata"

        asof = date(2026, 7, 6)
        _make_membership(tmp_data, "mag7", ["AAPL"])
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof), "premium_mn": 500.0, "net_premium_mn": 100.0,
             "pc_ratio": 0.55, "volume": 3000.0, "zerodte_share": 0.50, "net_doi": None}
        ])

        import unittest.mock as mock
        import lib.config as cfg_mod

        def patched_data_dir():
            return tmp_data

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            rows = build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)

        mag7_row = next(r for r in rows if r["key"] == "mag7")
        # Only 1 obs = raw_fallback=True
        assert mag7_row["raw_fallback"] is True
        assert mag7_row["gross_pct"] is None


def test_raw_fallback_false_with_sufficient_history():
    """raw_fallback must be False when >= MIN_PCT_HISTORY obs exist in the cohorts store."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp) / "data"
        tmp_site = Path(tmp) / "site" / "flowdata"

        asof_end = date(2026, 7, 6)
        _make_membership(tmp_data, "mag7", ["AAPL"])

        # Write AAPL ticker summary (for today's aggregation)
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof_end), "premium_mn": float(200), "net_premium_mn": float(30),
             "pc_ratio": 0.6, "volume": float(1500), "zerodte_share": 0.4, "net_doi": None}
        ])

        import unittest.mock as mock
        import lib.config as cfg_mod

        def patched_data_dir():
            return tmp_data

        # Pre-seed the cohorts accrual parquet with MIN_PCT_HISTORY + 5 days of data
        # so the percentile lookup has sufficient history (otherwise raw_fallback=True).
        cohorts_dir = tmp_data / "options_flow"
        cohorts_dir.mkdir(parents=True, exist_ok=True)
        hist_rows = []
        hist_dates = []
        for i in range(MIN_PCT_HISTORY + 5):
            d = asof_end - timedelta(days=(MIN_PCT_HISTORY + 5 - i))
            hist_dates.append(pd.Timestamp(d))
            hist_rows.append({
                "gross_premium_mn": float(100 + i * 5),
                "net_premium_mn": float(i * 2 - 10),
                "pc_ratio": 0.6,
                "zerodte_share": 0.4,
                "net_doi": None,
                "n_members": 7,
                "n_members_covered": 1,
            })
        hist_df = pd.DataFrame(hist_rows, index=hist_dates)
        hist_df.to_parquet(cohorts_dir / "cohorts_mag7.parquet")

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            result_rows = build_cohorts(tmp_data, asof=asof_end, site_flowdata_dir=tmp_site)

        mag7_row = next(r for r in result_rows if r["key"] == "mag7")
        assert mag7_row["raw_fallback"] is False, (
            f"Expected raw_fallback=False with {MIN_PCT_HISTORY + 5} seeded obs"
        )
        # gross_pct should be a number 0-100
        assert mag7_row["gross_pct"] is not None
        assert 0 <= mag7_row["gross_pct"] <= 100


# ── Test 6: Volume-weighted P/C ratio ─────────────────────────────────────────

def test_volume_weighted_pc_ratio():
    """P/C ratio must be weighted by volume, not a simple average."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp)
        asof = date(2026, 7, 6)
        # AAA: volume=1000, pc=0.4  BBB: volume=3000, pc=1.2
        # VW pc = (1000*0.4 + 3000*1.2) / 4000 = (400 + 3600) / 4000 = 1.0
        _make_summary(tmp_data, "AAA", [
            {"date": str(asof), "premium_mn": 50.0, "net_premium_mn": 10.0,
             "pc_ratio": 0.4, "volume": 1000.0, "zerodte_share": 0.3, "net_doi": None}
        ])
        _make_summary(tmp_data, "BBB", [
            {"date": str(asof), "premium_mn": 150.0, "net_premium_mn": -5.0,
             "pc_ratio": 1.2, "volume": 3000.0, "zerodte_share": 0.5, "net_doi": None}
        ])

        row = _aggregate_day(tmp_data, "test_cohort", ["AAA", "BBB"], asof)

        assert row["pc_ratio"] == pytest.approx(1.0, abs=0.001)


# ── Test 7: P/C tone labels ────────────────────────────────────────────────────

@pytest.mark.parametrize("pc_ratio,expected_tone", [
    (0.5, "call-tilted"),
    (0.69, "call-tilted"),
    (0.7, "balanced"),
    (1.0, "balanced"),
    (1.29, "balanced"),
    (1.3, "balanced"),
    (1.31, "put-tilted"),
    (2.0, "put-tilted"),
    (None, "balanced"),
])
def test_pc_tone_labels(pc_ratio, expected_tone):
    assert _pc_tone(pc_ratio) == expected_tone


# ── Test 8: Net soft tone labels ─────────────────────────────────────────────

@pytest.mark.parametrize("net_pm,expected_tone", [
    (100.0, "pos~"),
    (31.0, "pos~"),
    (30.0, "neutral~"),
    (0.0, "neutral~"),
    (-30.0, "neutral~"),
    (-31.0, "neg~"),
    (-200.0, "neg~"),
    (None, "neutral~"),
])
def test_net_soft_tone_labels(net_pm, expected_tone):
    assert _net_soft_tone(net_pm) == expected_tone


# ── Test 9: Percentile helper ─────────────────────────────────────────────────

def test_percentile_vs_history_below_minimum():
    """Returns None when fewer than MIN_PCT_HISTORY obs."""
    s = pd.Series([100.0, 200.0, 300.0])  # only 3 obs
    result = _percentile_vs_history(s, 150.0, min_obs=MIN_PCT_HISTORY)
    assert result is None


def test_percentile_vs_history_median():
    """A value at the median should return ~50th percentile."""
    import numpy as np
    rng = np.random.default_rng(42)
    s = pd.Series(rng.uniform(0, 100, 50))
    median_val = float(s.median())
    pct = _percentile_vs_history(s, median_val, min_obs=20)
    assert pct is not None
    assert 30 <= pct <= 70  # median is around 50th, some variance OK


# ── Test 10: Coverage label format ───────────────────────────────────────────

def test_coverage_label_format():
    """coverage_label must contain 'of' and count integers."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_data = Path(tmp) / "data"
        tmp_site = Path(tmp) / "site" / "flowdata"
        asof = date(2026, 7, 6)
        # Only 2 of 7 Mag7 members have data
        _make_membership(tmp_data, "mag7", ["A", "B", "C", "D", "E", "F", "G"])
        _make_summary(tmp_data, "A", [
            {"date": str(asof), "premium_mn": 10.0, "net_premium_mn": 2.0,
             "pc_ratio": 0.6, "volume": 100.0, "zerodte_share": 0.3, "net_doi": None}
        ])
        _make_summary(tmp_data, "B", [
            {"date": str(asof), "premium_mn": 20.0, "net_premium_mn": 5.0,
             "pc_ratio": 0.7, "volume": 200.0, "zerodte_share": 0.4, "net_doi": None}
        ])

        import unittest.mock as mock
        import lib.config as cfg_mod

        def patched_data_dir():
            return tmp_data

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            rows = build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)

        mag7_row = next(r for r in rows if r["key"] == "mag7")
        label = mag7_row["coverage_label"]
        assert "2 of 7" in label, f"Expected '2 of 7' in label, got: {label!r}"
