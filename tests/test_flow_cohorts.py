"""tests/test_flow_cohorts.py — FL-B cohort flow aggregation unit tests.

Covers:
1. Aggregation correctness on synthetic fixtures (multi-member cohort)
2. Missing-member coverage honesty counts (some members lack summary files)
3. Idempotence: two consecutive build_cohorts() calls produce byte-equal JSON
4. JSON schema contract: required keys present, direction_reliable=False
5. No-history raw_fallback flag: raw_fallback=True when < MIN_PCT_HISTORY obs
6. Volume-weighted P/C ratio computation
7. P/C tone labels (call-tilted / put-tilted / balanced)
8. HOUSE-U5 accrual lane gate (TestCohortAccrualLaneGate)
9. Sparkline selects the last N sessions that carry a READING, not the last N
   rows — a null row never eats a slot (TestSparklineSkipsNullRows)
10. Bounded nightly backfill of sessions the single-asof upsert stranded, and
    the three limits that keep it honest: summary coverage only, never a
    zero-coverage row, never outside the lookback (TestCohortBackfill)
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Allow running standalone without installing the package
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.flow_cohorts import (
    BACKFILL_LOOKBACK_DAYS,
    COHORTS,
    MIN_PCT_HISTORY,
    SPARKLINE_SESSIONS,
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


# ── Test 11: HOUSE-U5 accrual lane gate ──────────────────────────────────────

class TestCohortAccrualLaneGate:
    """HOUSE-U5: build_cohorts() UPSERTS committed data/options_flow/cohorts_<key>.parquet,
    so the accrual must run ONLY in the nightly collector lane. Express/intraday lanes
    bake site/ from the committed vintage and must leave data/ untouched.

    The returned rows and cohorts.json stay unconditional — only the parquet
    accrual is gated.
    """

    def _run(self, tmp: Path, env: dict[str, str] | None) -> Path:
        """Build cohorts against a tmp data root; return that root.

        lib.config.data_dir is patched (the idiom the other tests in this file
        use) so lib.store._path resolves every parquet under tmp — nothing can
        reach the repo's committed stores.
        env=None → COLLECT_LANE/US_LANE removed entirely (express/dev run).
        """
        import unittest.mock as mock
        import os
        import lib.config as cfg_mod

        tmp_data = tmp / "data"
        tmp_site = tmp / "site" / "flowdata"
        asof = date(2026, 7, 6)
        _make_membership(tmp_data, "mag7", ["AAPL"])
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof), "premium_mn": 500.0, "net_premium_mn": 100.0,
             "pc_ratio": 0.55, "volume": 3000.0, "zerodte_share": 0.50, "net_doi": None}
        ])

        def patched_data_dir():
            return tmp_data

        saved: dict[str, str] = {}
        try:
            for k in ("COLLECT_LANE", "US_LANE"):
                if k in os.environ:
                    saved[k] = os.environ.pop(k)
            if env:
                os.environ.update(env)
            with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
                rows = build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)
        finally:
            if env:
                for k in env:
                    os.environ.pop(k, None)
            os.environ.update(saved)

        # site/ output is ungated in every lane — the gate must not cost the display.
        assert (tmp_site / "cohorts.json").exists(), "cohorts.json must be written in any lane"
        assert len(rows) == len(COHORTS)
        return tmp_data

    @staticmethod
    def _accrued(tmp_data: Path) -> list[str]:
        d = tmp_data / "options_flow"
        return sorted(p.name for p in d.glob("cohorts_*.parquet")) if d.exists() else []

    def test_no_accrual_without_lane(self, tmp_path):
        """COLLECT_LANE unset → no cohorts_<key>.parquet is written."""
        tmp_data = self._run(tmp_path, None)
        # File-absence IS the load-bearing signal here (unlike the flow_desk proxy
        # gate): build_cohorts always attempts the upsert when ungated, even with a
        # single-member cohort and no history, so an ungated run leaves all four
        # parquets behind. Verified by the mutation check — this assertion fires on
        # the pre-gate code.
        assert self._accrued(tmp_data) == [], (
            f"no cohort parquet may be written off-nightly, got {self._accrued(tmp_data)}"
        )

    def test_accrual_runs_on_nightly_lane(self, tmp_path):
        """COLLECT_LANE=nightly → all four cohort stores accrue (pins against inverted logic)."""
        tmp_data = self._run(tmp_path, {"COLLECT_LANE": "nightly"})
        got = self._accrued(tmp_data)
        assert got == sorted(f"cohorts_{c['key']}.parquet" for c in COHORTS), got
        # the accrued row must carry the asof we asked for
        df = pd.read_parquet(tmp_data / "options_flow" / "cohorts_mag7.parquet")
        assert pd.Timestamp(2026, 7, 6) in pd.to_datetime(df.index)

    def test_accrual_runs_on_legacy_us_lane_alias(self, tmp_path):
        """US_LANE=nightly is the legacy alias engine.ledger_lane still honours."""
        tmp_data = self._run(tmp_path, {"US_LANE": "nightly"})
        assert "cohorts_mag7.parquet" in self._accrued(tmp_data)


# ── Test 12: Sparkline null-row selection (FL-B sparkline repair) ─────────────

class TestSparklineSkipsNullRows:
    """The sparkline must show the last SPARKLINE_SESSIONS sessions that carry a
    READING, not the last SPARKLINE_SESSIONS rows.

    Measured defect (committed 2026-07-28 vintage): nine all-null rows an
    off-nightly run had left in cohorts_<key>.parquet sat inside the window, so
    `hist_df.tail(10)` returned mag7 spark_gross
    [5777.8, null, null, null, null, null, null, 4877.0, 4893.9, 4012.3]
    — 4 real points in 10 slots. The percentile path was already immune via its
    own .dropna(); these pin the sparkline to the same standard so ANY future
    null row costs the strip nothing.
    """

    @staticmethod
    def _build(tmp: Path, ledger: pd.DataFrame, asof: date) -> dict:
        """Seed cohorts_mag7.parquet with `ledger`, build, return the mag7 row.

        lib.config.data_dir is patched to tmp so lib.store._path resolves every
        parquet under tmp — tests/conftest.py arms COLLECT_LANE=nightly for every
        test, so an UNPATCHED build_cohorts() upserts into the repo's real
        committed stores (this is the idiom TestCohortAccrualLaneGate._run
        documents; #4041 was bitten by skipping it).
        """
        import unittest.mock as mock
        import lib.config as cfg_mod

        tmp_data = tmp / "data"
        tmp_site = tmp / "site" / "flowdata"
        _make_membership(tmp_data, "mag7", ["AAPL"])
        _make_summary(tmp_data, "AAPL", [
            {"date": str(asof), "premium_mn": 900.0, "net_premium_mn": 120.0,
             "pc_ratio": 0.6, "volume": 4000.0, "zerodte_share": 0.5, "net_doi": None}
        ])
        cdir = tmp_data / "options_flow"
        cdir.mkdir(parents=True, exist_ok=True)
        ledger.to_parquet(cdir / "cohorts_mag7.parquet")

        def patched_data_dir():
            return tmp_data

        with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
            rows = build_cohorts(tmp_data, asof=asof, site_flowdata_dir=tmp_site)
        return next(r for r in rows if r["key"] == "mag7")

    @staticmethod
    def _ledger(entries: list[tuple[str, float | None, float | None]]) -> pd.DataFrame:
        """Build a cohort ledger frame from (iso_date, gross, net) triples."""
        return pd.DataFrame(
            {
                "gross_premium_mn": [g for _, g, _ in entries],
                "net_premium_mn": [n for _, _, n in entries],
                "pc_ratio": [0.6 if g is not None else None for _, g, _ in entries],
                "zerodte_share": [0.4 if g is not None else None for _, g, _ in entries],
                "net_doi": [None] * len(entries),
                "n_members": [1] * len(entries),
                "n_members_covered": [1 if g is not None else 0 for _, g, _ in entries],
            },
            index=[pd.Timestamp(d) for d, _, _ in entries],
        )

    def test_null_rows_never_consume_sparkline_slots(self, tmp_path):
        """The exact committed shape: 4 real sessions buried under 9 null rows.

        Reproduces the measured mag7 ledger (07-15/24/27 real, 07-11..07-21 null)
        and asserts the strip comes back all-real. On the pre-fix .tail() this
        returns 3 reals + 7 nulls, so the assertion pins the defect.
        """
        asof = date(2026, 7, 28)
        row = self._build(tmp_path, self._ledger([
            ("2026-07-11", None, None),
            ("2026-07-13", None, None),
            ("2026-07-14", None, None),
            ("2026-07-15", 5777.8, 1542.0),
            ("2026-07-16", None, None),
            ("2026-07-17", None, None),
            ("2026-07-18", None, None),
            ("2026-07-19", None, None),
            ("2026-07-20", None, None),
            ("2026-07-21", None, None),
            ("2026-07-24", 4877.0, 521.9),
            ("2026-07-27", 4893.9, 304.1),
        ]), asof)

        assert None not in row["spark_gross"], (
            f"a null ledger row ate a sparkline slot: {row['spark_gross']}"
        )
        # 07-15, 07-24, 07-27 from the seed + the 07-28 asof the build accrued.
        assert row["spark_gross"] == [5777.8, 4877.0, 4893.9, 900.0], row["spark_gross"]

    def test_selects_last_ten_real_sessions_not_last_ten_rows(self, tmp_path):
        """With >10 real sessions available, nulls must not cost the strip any.

        Shape: 12 real sessions (06-01..06-12) followed by 12 null rows
        (06-13..06-24), so the pre-fix .tail(10) window lands entirely inside the
        null block and returns TEN nulls — a fully blank strip on a store holding
        a dozen good sessions.
        """
        asof = date(2026, 7, 28)
        entries: list[tuple[str, float | None, float | None]] = []
        for i in range(12):
            entries.append((f"2026-06-{i + 1:02d}", float(100 + i), float(i)))
            entries.append((f"2026-06-{i + 13:02d}", None, None))
        entries.sort()
        row = self._build(tmp_path, self._ledger(entries), asof)

        assert len(row["spark_gross"]) == SPARKLINE_SESSIONS, row["spark_gross"]
        assert None not in row["spark_gross"], row["spark_gross"]
        # The 3 oldest reals (100/101/102) drop out; the 07-28 asof is the newest.
        assert row["spark_gross"] == [103.0, 104.0, 105.0, 106.0, 107.0,
                                      108.0, 109.0, 110.0, 111.0, 900.0], row["spark_gross"]

    def test_spark_pairs_stay_index_aligned(self, tmp_path):
        """spark_gross / spark_net must index the SAME sessions.

        A real session whose net signing failed keeps its null in spark_net — the
        arrays are read off one selected frame, never dropna'd independently
        (which would shift net by a slot and mis-label every point).
        """
        asof = date(2026, 7, 28)
        row = self._build(tmp_path, self._ledger([
            ("2026-07-13", 300.0, 40.0),
            ("2026-07-14", None, None),      # null row — drops out entirely
            ("2026-07-15", 400.0, None),     # real gross, unsigned net — slot KEPT
            ("2026-07-16", 500.0, 60.0),
        ]), asof)

        assert row["spark_gross"] == [300.0, 400.0, 500.0, 900.0], row["spark_gross"]
        assert row["spark_net"] == [40.0, None, 60.0, 120.0], row["spark_net"]
        assert len(row["spark_gross"]) == len(row["spark_net"])

    def test_all_null_history_yields_empty_strip_not_nulls(self, tmp_path):
        """A store holding only null rows must yield the asof point alone.

        The honest empty case: no fabricated placeholder points.
        """
        asof = date(2026, 7, 28)
        row = self._build(tmp_path, self._ledger([
            ("2026-07-18", None, None),
            ("2026-07-19", None, None),
        ]), asof)
        assert row["spark_gross"] == [900.0], row["spark_gross"]


# ── Test 13: Bounded backfill of stranded sessions ───────────────────────────

class TestCohortBackfill:
    """build_cohorts() only ever upserts the SINGLE requested asof, so nothing
    ever revisits a session the nightly did not run at — and nothing revisited
    the all-null rows an off-nightly run left behind before #4007 gated them.
    Measured on the committed store: five of the nine null rows (07-13/14/16/17/20)
    sat at dates the per-ticker summary store covers in FULL, so the readings were
    recoverable all along and a blind purge would have destroyed them.

    The backfill closes both shapes under one rule: an in-window session with
    summary coverage but no usable ledger row gets re-aggregated. Nightly-gated,
    bounded to BACKFILL_LOOKBACK_DAYS, and it never writes a zero-coverage date.
    """

    ASOF = date(2026, 7, 28)

    @staticmethod
    def _run(tmp: Path, summary_dates: list[str], ledger: pd.DataFrame | None,
             env: dict[str, str] | None = {"COLLECT_LANE": "nightly"}) -> pd.DataFrame:
        """Seed AAPL summary rows + an optional ledger, build, return the ledger.

        lib.config.data_dir is patched to tmp so lib.store._path resolves every
        parquet under tmp — tests/conftest.py arms COLLECT_LANE=nightly for every
        test, so an UNPATCHED build_cohorts() upserts into the repo's real
        committed stores (the idiom TestCohortAccrualLaneGate._run documents).
        """
        import unittest.mock as mock
        import os
        import lib.config as cfg_mod

        tmp_data = tmp / "data"
        tmp_site = tmp / "site" / "flowdata"
        _make_membership(tmp_data, "mag7", ["AAPL"])
        _make_summary(tmp_data, "AAPL", [
            {"date": d, "premium_mn": 100.0 + i, "net_premium_mn": 10.0 + i,
             "pc_ratio": 0.6, "volume": 1000.0, "zerodte_share": 0.4, "net_doi": None}
            for i, d in enumerate(summary_dates)
        ])
        cdir = tmp_data / "options_flow"
        cdir.mkdir(parents=True, exist_ok=True)
        if ledger is not None:
            ledger.to_parquet(cdir / "cohorts_mag7.parquet")

        def patched_data_dir():
            return tmp_data

        saved: dict[str, str] = {}
        try:
            for k in ("COLLECT_LANE", "US_LANE"):
                if k in os.environ:
                    saved[k] = os.environ.pop(k)
            if env:
                os.environ.update(env)
            with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
                build_cohorts(tmp_data, asof=TestCohortBackfill.ASOF,
                              site_flowdata_dir=tmp_site)
        finally:
            if env:
                for k in env:
                    os.environ.pop(k, None)
            os.environ.update(saved)

        p = cdir / "cohorts_mag7.parquet"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()

    @staticmethod
    def _null_row(iso: str) -> pd.DataFrame:
        """The exact row shape an ungated off-nightly zero-coverage run wrote."""
        return pd.DataFrame(
            {
                "gross_premium_mn": [None], "net_premium_mn": [None],
                "pc_ratio": [None], "zerodte_share": [None], "net_doi": [None],
                "n_members": [1], "n_members_covered": [0],
            },
            index=[pd.Timestamp(iso)],
        )

    def test_heals_null_row_at_a_covered_session(self):
        """A null row at a date the summary store DOES cover is re-aggregated.

        This is the 07-13/14/16/17/20 case — the reading was recoverable, so the
        repair is a heal, never a purge.
        """
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), ["2026-07-20", "2026-07-28"],
                           self._null_row("2026-07-20"))
        row = df.loc[pd.Timestamp("2026-07-20")]
        assert not pd.isna(row["gross_premium_mn"]), (
            f"null row at a covered session was left unhealed:\n{df}"
        )
        assert row["gross_premium_mn"] == 100.0, row["gross_premium_mn"]
        assert row["n_members_covered"] == 1, row["n_members_covered"]

    def test_fills_a_session_with_no_ledger_row_at_all(self):
        """A covered session the nightly never ran at gets a row appended.

        The single-asof upsert has no path back to it (the 07-01/02/06/09/10 and
        07-22/07-23 shape).
        """
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), ["2026-07-16", "2026-07-17", "2026-07-28"], None)
        got = [str(d.date()) for d in df.index]
        assert got == ["2026-07-16", "2026-07-17", "2026-07-28"], got
        assert not df["gross_premium_mn"].isna().any(), f"\n{df}"

    def test_writes_only_dates_the_summary_store_covers(self):
        """Candidates come from summary coverage, never from the calendar.

        The gap between two covered sessions must stay EMPTY: 07-11/07-18/07-19 are
        weekends and 07-21/07-22/07-23 have no coverage, so there is nothing to
        recover and a row asserting otherwise is the exact defect this repair
        exists to stop. Pins against widening the candidate set to a date range —
        that mutation fills the gap with all-null rows and fails here.
        """
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), ["2026-07-16", "2026-07-28"], None)
        assert [str(d.date()) for d in df.index] == ["2026-07-16", "2026-07-28"], (
            f"backfill invented rows for uncovered dates:\n{df}"
        )
        assert not df["gross_premium_mn"].isna().any(), f"\n{df}"

    def test_leaves_an_unrecoverable_null_row_as_found(self):
        """A null row at a date with no coverage is neither healed nor fabricated.

        Nothing can recover it (07-11/07-18/07-19/07-21), and after the sparkline
        selection fix it costs the strip nothing, so the honest outcome is to leave
        it exactly as found rather than invent a reading for it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), ["2026-07-28"], self._null_row("2026-07-18"))
        assert pd.isna(df.loc[pd.Timestamp("2026-07-18"), "gross_premium_mn"]), f"\n{df}"
        assert df.loc[pd.Timestamp("2026-07-18"), "n_members_covered"] == 0

    def test_zero_coverage_guard_is_live_on_an_intraday_index(self, tmp_path):
        """The n_members_covered<1 skip is reachable, not decoration.

        Candidate dates are NORMALIZED off the summary index while _aggregate_day
        matches the index exactly, so a summary frame carrying a time component
        yields a candidate date that aggregates to zero coverage. The guard is what
        keeps that seam from writing an all-null row — the very shape #4007 gated.
        """
        from engine.flow_cohorts import _heal_sessions

        tmp_data = tmp_path / "data"
        d = tmp_data / "options_flow"
        d.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([{
            "premium_mn": 100.0, "net_premium_mn": 10.0, "pc_ratio": 0.6,
            "volume": 1000.0, "zerodte_share": 0.4, "net_doi": None,
        }], index=[pd.Timestamp("2026-07-20 13:30")])
        df.to_parquet(d / "summary_AAPL.parquet")

        import unittest.mock as mock
        import lib.config as cfg_mod

        with mock.patch.object(cfg_mod, "data_dir", lambda: tmp_data):
            healed, skipped = _heal_sessions(
                tmp_data, "mag7", ["AAPL"], self.ASOF, {}
            )

        assert healed == [], healed
        assert skipped == 1, skipped
        assert not (d / "cohorts_mag7.parquet").exists(), (
            "a zero-coverage candidate must not create a ledger file"
        )

    def test_backfill_is_gated_to_the_nightly_lane(self):
        """COLLECT_LANE unset → the null row is left exactly as found.

        The backfill UPSERTS a forward ledger, so it lives behind the same
        HOUSE-U5 gate as the asof accrual: express/intraday lanes must leave
        data/ untouched.
        """
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), ["2026-07-20", "2026-07-28"],
                           self._null_row("2026-07-20"), env=None)
        assert pd.isna(df.loc[pd.Timestamp("2026-07-20"), "gross_premium_mn"]), f"\n{df}"
        # ...and the asof row must not have been accrued either.
        assert pd.Timestamp("2026-07-28") not in df.index, f"\n{df}"

    def test_lookback_is_bounded(self):
        """A covered session older than BACKFILL_LOOKBACK_DAYS is left alone.

        The pass must never walk deep history — it exists to repair the recent
        window the display reads, not to rebuild the ledger.
        """
        stale = self.ASOF - timedelta(days=BACKFILL_LOOKBACK_DAYS + 5)
        with tempfile.TemporaryDirectory() as tmp:
            df = self._run(Path(tmp), [str(stale), "2026-07-28"], None)
        assert pd.Timestamp(stale) not in df.index, (
            f"session {stale} is outside the {BACKFILL_LOOKBACK_DAYS}d window "
            f"and must not be backfilled:\n{df}"
        )
        assert [str(d.date()) for d in df.index] == ["2026-07-28"]

    def test_healed_ledger_feeds_a_full_sparkline(self):
        """End to end: the heal is what turns 4 real points back into 10.

        Pins the two halves together — selection alone cannot invent sessions the
        ledger never recorded, and the heal alone would still be eaten by .tail().
        """
        import unittest.mock as mock
        import lib.config as cfg_mod

        sessions = [f"2026-07-{d:02d}" for d in
                    (6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 20, 28)]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_data = Path(tmp) / "data"
            tmp_site = Path(tmp) / "site" / "flowdata"
            _make_membership(tmp_data, "mag7", ["AAPL"])
            _make_summary(tmp_data, "AAPL", [
                {"date": d, "premium_mn": 100.0 + i, "net_premium_mn": 10.0 + i,
                 "pc_ratio": 0.6, "volume": 1000.0, "zerodte_share": 0.4, "net_doi": None}
                for i, d in enumerate(sessions)
            ])
            # Ledger as the defect left it: null rows over five covered sessions.
            cdir = tmp_data / "options_flow"
            cdir.mkdir(parents=True, exist_ok=True)
            pd.concat([self._null_row(d) for d in
                       ("2026-07-13", "2026-07-14", "2026-07-16", "2026-07-17",
                        "2026-07-20")]).to_parquet(cdir / "cohorts_mag7.parquet")

            def patched_data_dir():
                return tmp_data

            with mock.patch.object(cfg_mod, "data_dir", patched_data_dir):
                rows = build_cohorts(tmp_data, asof=self.ASOF, site_flowdata_dir=tmp_site)

        mag7 = next(r for r in rows if r["key"] == "mag7")
        assert len(mag7["spark_gross"]) == SPARKLINE_SESSIONS, mag7["spark_gross"]
        assert None not in mag7["spark_gross"], mag7["spark_gross"]


# ── Test 14: a zero-coverage day must not ship a stance ───────────────────────
#
# Regression pin for the 2026-07-29 stamping defect.  build_flow_desk passes the
# market-tide asof into build_cohorts (scripts/build_flow_desk.py:803), so a run
# whose tide has advanced past the per-ticker summary coverage aggregates to
# n_members_covered=0 with every headline None.  _pc_tone(None) returned
# "balanced" and _net_soft_tone(None) returned "neutral~" — publishing those
# verbatim turned "we have no observations" into an affirmative claim about
# positioning.  19 committed cohorts.json vintages (2026-07-11 → 07-21) carried
# that stance on all-null days; they predate the Theme groups panel rendering
# (first shipped 07-22, when coverage was already full), so the contradiction
# never reached a live page — but the panel renders daily now, so the next
# uncovered session would have printed "balanced / 均衡" beside "no data today /
# 今日无数据" in one tile.  Nulls are printed, not spun.

class TestZeroCoverageEmitsNoStance:
    """A cohort day with no covered members carries no tone chip, in JSON or HTML."""

    ASOF_COVERED = date(2026, 7, 6)
    ASOF_BARE = date(2026, 7, 7)  # one day past the only summary row

    def _build(self, tmp_path: Path, asof: date, site: Path | None = None) -> list[dict]:
        """Build against a tmp data root.

        lib.config.data_dir MUST be patched (the idiom TestNightlyGate uses):
        build_cohorts takes data_dir for its summary reads, but lib.store resolves
        the cohort parquets through config, and tests/conftest.py arms
        COLLECT_LANE=nightly for every test — so an unpatched call upserts into the
        repo's committed stores.  Caught by the data guard while writing this test.
        """
        import unittest.mock as mock
        import lib.config as cfg_mod

        tmp_data = tmp_path / "data"
        _make_membership(tmp_data, "mag7", ["X1"])
        _make_summary(tmp_data, "X1", [{
            "date": self.ASOF_COVERED.isoformat(), "premium_mn": 100.0,
            "net_premium_mn": 50.0, "pc_ratio": 0.9, "volume": 1000,
            "zerodte_share": 0.4, "net_doi": 10.0,
        }])
        with mock.patch.object(cfg_mod, "data_dir", lambda: tmp_data):
            return build_cohorts(tmp_data, asof=asof, site_flowdata_dir=site)

    def _mag7(self, rows: list[dict]) -> dict:
        return next(r for r in rows if r["key"] == "mag7")

    def test_no_coverage_emits_null_tones(self, tmp_path):
        row = self._mag7(self._build(tmp_path, self.ASOF_BARE))
        assert row["n_members_covered"] == 0
        assert row["pc_ratio"] is None
        # The defect: these were "balanced" / "neutral~" — a read with nothing read.
        assert row["pc_tone"] is None, f"stance invented from a null: {row['pc_tone']!r}"
        assert row["net_tone"] is None, f"stance invented from a null: {row['net_tone']!r}"

    def test_covered_day_still_emits_tones(self, tmp_path):
        """Control — pins against suppressing the tone on a real day."""
        row = self._mag7(self._build(tmp_path, self.ASOF_COVERED))
        assert row["n_members_covered"] == 1
        assert row["pc_tone"] == "balanced"  # pc_ratio 0.9 is genuinely balanced
        assert row["net_tone"] == "pos~"

    def test_tone_fields_remain_present_in_json(self, tmp_path):
        """Schema contract holds: the keys stay, the values go null."""
        tmp_site = tmp_path / "site" / "flowdata"
        self._build(tmp_path, self.ASOF_BARE, site=tmp_site)
        payload = json.loads((tmp_site / "cohorts.json").read_text())
        assert payload["asof"] == self.ASOF_BARE.isoformat()
        for c in payload["cohorts"]:
            assert "pc_tone" in c and "net_tone" in c
            assert c["pc_tone"] is None and c["net_tone"] is None


class TestZeroCoverageRendersNoStanceWord:
    """A cohort with no observations must not be given a tilt word.

    WHERE THIS PANEL LIVES NOW (OIP W1.6-B). It used to render
    flow_desk.html.j2's Theme-groups panel through Jinja. flow_desk.html.j2 is a
    redirect stub and the panel moved into the workspace's Flow mode, as
    `flThemePanel()` in templates/options.html.j2 — so the law is re-pointed
    there rather than retired with the template. Retiring it would have taken
    the "no data, therefore no stance" rule dark: nothing in
    tests/test_build_options_command.py covers this panel.

    The panel is JS now, so it is DRIVEN (node) rather than rendered — which
    also makes the check stronger than the Jinja one it replaces: it exercises
    the real coverage predicate, not a template branch.

    The wording and class names travelled with it:
        coh-tile                -> oew-fl-tile
        "No theme-group data yet"
                                -> "No theme-group data for this close."
    """

    _NULL_EN = "No theme-group data for this close."
    _NULL_ZH = "本次收盘没有主题组合数据。"

    @staticmethod
    def _panel(cohorts: list[dict]) -> str:
        """Run the REAL flThemePanel() over a cohort list and return its markup."""
        root = Path(__file__).resolve().parent.parent
        src = (root / "templates" / "options.html.j2").read_text(encoding="utf-8")

        def block(opener: str, closer: str = "\n}") -> str:
            start = src.index(opener)
            return src[start: src.index(closer, start) + len(closer)]

        harness = "\n".join([
            block("function esc(s){"),
            re.search(r"^function bi\(en, zh\).*$", src, re.M).group(0),
            re.search(r"^function num\(v\).*$", src, re.M).group(0),
            block("function money(mn){"),
            re.search(r"^function smoney\(mn\).*$", src, re.M).group(0),
            re.search(r"^function flSoft\(mn\).*$", src, re.M).group(0),
            block("function flThemePanel(desk, cohorts){"),
            "process.stdout.write(flThemePanel(null, { cohorts: "
            + json.dumps(cohorts) + " }));",
        ])
        res = subprocess.run(["node", "-e", harness], capture_output=True,
                             text=True, timeout=30)
        assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
        assert "Theme groups" in res.stdout, "did not render the Theme groups panel"
        # Body only. The panel HEAD carries a `?` help tip that legitimately
        # explains what the net buy/sell mark means — sweeping that as if it
        # were a stance chip would fail the panel for its own documentation.
        # (The original Jinja version sliced the page for the same reason.)
        marker = '<div class="oew-pbody">'
        assert marker in res.stdout, "panel body marker missing — the slice would be vacuous"
        return res.stdout.split(marker, 1)[1]

    @staticmethod
    def _row(**over) -> dict:
        base = {
            "key": "mag7", "name_en": "Mag 7", "name_zh": "七巨头",
            "gross_premium_mn": None, "net_premium_mn": None, "pc_ratio": None,
            "zerodte_share": None, "net_doi": None, "n_members": 7,
            "n_members_covered": 0, "pc_tone": None, "net_tone": None,
            "coverage_label": "0 of 7 members covered", "raw_fallback": True,
            "spark_gross": [], "spark_net": [],
        }
        base.update(over)
        return base

    def test_no_stance_word_when_nothing_covered(self):
        panel = self._panel([self._row()])
        assert "balanced" not in panel, "printed a tilt for a cohort with no observations"
        assert "均衡" not in panel, "printed a tilt (ZH) for a cohort with no observations"
        assert "net buy" not in panel and "净买" not in panel
        assert "flat ~" not in panel and "持平 ~" not in panel

    def test_whole_panel_null_states_it_plainly(self):
        """Plain-word disclosure in both languages, not four tiles of dashes."""
        panel = self._panel([self._row()])
        assert self._NULL_EN in panel
        assert self._NULL_ZH in panel
        assert 'class="oew-fl-tile"' not in panel, "dead tiles shipped instead of the null line"

    def test_covered_cohort_still_renders_its_chip(self):
        """Control — a real day keeps its tilt chip and its tile."""
        panel = self._panel([self._row(
            gross_premium_mn=4893.9, net_premium_mn=304.1, pc_ratio=0.674,
            zerodte_share=0.514, n_members_covered=7, pc_tone="call-tilted",
            net_tone="pos~", coverage_label="7 of 7 members covered",
        )])
        assert 'class="oew-fl-tile"' in panel
        assert "偏看涨" in panel and "calls" in panel
        assert self._NULL_EN not in panel
        # The tile's headline figure. flow_desk's tile showed GROSS premium
        # ($4.9B); the workspace's shows NET, softened — the "~" is the
        # approximate-direction mark the panel foot explains, and it must stay
        # attached to a signed number rather than being dropped as decoration.
        assert "~+$304M" in panel, f"net-premium figure not rendered as expected: {panel}"

    def test_partial_coverage_keeps_the_strip(self):
        """One covered group among four nulls still shows the strip, not the null line."""
        rows = [
            self._row(key="mag7"),
            self._row(key="ai_software", name_en="Software", name_zh="软件",
                      gross_premium_mn=1878.7, net_premium_mn=116.0, pc_ratio=0.462,
                      n_members=17, n_members_covered=17, pc_tone="call-tilted",
                      net_tone="pos~"),
        ]
        panel = self._panel(rows)
        assert self._NULL_EN not in panel
        assert 'class="oew-fl-tile"' in panel
        # the uncovered group says so in words…
        assert "no data today" in panel or "今日无数据" in panel

        # …AND carries no tilt. This half was in the docstring but never asserted
        # — on either this panel or the flow_desk one it moved from — so a change
        # that gave every cohort a chip regardless of coverage passed. The
        # whole-panel null case cannot catch it: that branch returns before any
        # tile is built, so the chip code only ever runs on a MIXED payload.
        tiles = panel.split('<div class="oew-fl-tile">')[1:]
        assert len(tiles) == 2, f"expected both cohorts to render a tile, got {len(tiles)}"
        uncovered = next(t for t in tiles if "Mag 7" in t)
        covered = next(t for t in tiles if "Software" in t)
        assert 'class="tone' not in uncovered, (
            f"uncovered cohort was given a stance chip:\n{uncovered}"
        )
        for word in ("balanced", "均衡", "net buy", "净买", "flat ~", "持平 ~"):
            assert word not in uncovered, f"uncovered cohort printed a tilt word: {word!r}"
        assert 'class="tone' in covered, (
            "the covered cohort lost its chip — this control must stay non-vacuous"
        )
