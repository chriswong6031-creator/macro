"""tests/test_fs2_flow_atlas.py — FS-2 flow-signal atlas builder unit tests.

CI target: flow-signal-cohorts job in ci.yml (extend paths + pytest file list).
All tests are hermetic: synthetic cohort fixtures in tmp_path.
No network, no thetadata_eod store, no real cohort parquets.

Test cases (per FS-2 acceptance gate):
  1. Wilson CI correctness vs a hand-computed case.
  2. Cohort-separation assertion (mixed-source frame raises ValueError).
  3. N-floor labeling (cell n < 30 → ERA-SPARSE flag, stat suppressed).
  4. Accrual-label path (absent/thin cohort → table emitted with accruing
     status, not fabricated numbers).
  5. Table H: 0DTE index vol>OI flag is correctly annotated as structural artifact.
  6. Table I: era-stratified output has correct hit-rate computation.
  7. Table J: premium decile table emits N_FLOOR suppression for thin deciles.
  8. Table K: crowdedness tercile breakpoints are computed from data, not hardcoded.
  9. Table A: qual_class splits correctly when vol_gt_oi is present.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Allow running standalone without the package installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ops_flow_atlas import (
    N_FLOOR,
    _assert_single_source,
    _rate_cell,
    _sparse_cell,
    table_a,
    table_h,
    table_i,
    table_j,
    table_k,
    wilson_ci,
)


# ── fixtures ───────────────────────────────────────────────────────────────────

_EVT_COUNTER = [0]  # mutable singleton for globally unique event_ids across calls


def _make_eod_events(n: int, root: str = "TEST", source: str = "eod_proxy",
                     era: str = "2023+", zerodte: bool = False,
                     vol_gt_oi: bool = True, dte_bucket: str = "8_30d",
                     premium: float = 250_000.0, session_date: str = "2024-01-02") -> pd.DataFrame:
    """Create a minimal synthetic eod_proxy event DataFrame with globally unique event_ids."""
    start = _EVT_COUNTER[0]
    _EVT_COUNTER[0] += n
    ids = [f"EVT_{root}_{start + i:08d}" for i in range(n)]
    return pd.DataFrame({
        "event_id": ids,
        "era": [era] * n,
        "dte_bucket": [dte_bucket] * n,
        "mny_bucket": ["unknown"] * n,
        "vol_gt_oi": [vol_gt_oi] * n,
        "premium": [premium] * n,
        "session_date": [session_date] * n,
        "source": [source] * n,
        "root": [root] * n,
        "zerodte": [zerodte] * n,
    })


def _make_eod_grades(events: pd.DataFrame, hit_frac: float = 0.6,
                     ret_val: float = 0.01, excess_val: float = 0.005,
                     n_null: int = 0) -> pd.DataFrame:
    """Create synthetic grade rows aligned to events."""
    n = len(events)
    n_ok = n - n_null
    fwd_ret_5 = [ret_val if i < int(n_ok * hit_frac) else -ret_val for i in range(n_ok)] + [None] * n_null
    fwd_ret_21 = fwd_ret_5[:]
    spy_excess_5 = [excess_val] * n_ok + [None] * n_null
    spy_excess_21 = spy_excess_5[:]
    fwd_ret_63 = fwd_ret_5[:]
    spy_excess_63 = spy_excess_5[:]
    return pd.DataFrame({
        "event_id": events["event_id"].tolist(),
        "fwd_ret_5": fwd_ret_5,
        "spy_excess_5": spy_excess_5,
        "fwd_ret_21": fwd_ret_21,
        "spy_excess_21": spy_excess_21,
        "fwd_ret_63": fwd_ret_63,
        "spy_excess_63": spy_excess_63,
        "terminal_state_clean8_21": ["CLEAN_LIFTOFF"] * n_ok + [None] * n_null,
    })


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write DataFrame to parquet (round-trip safe)."""
    pq.write_table(pa.Table.from_pandas(df), path)


# ── 1. Wilson CI correctness ───────────────────────────────────────────────────

class TestWilsonCI:
    def test_known_value(self):
        """Hand-computed Wilson CI for k=60, n=100 at z=1.96."""
        k, n = 60, 100
        p = k / n
        z = 1.96
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        margin = z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
        expected_lo = max(0.0, centre - margin)
        expected_hi = min(1.0, centre + margin)
        lo, hi = wilson_ci(k, n)
        assert abs(lo - expected_lo) < 1e-10
        assert abs(hi - expected_hi) < 1e-10

    def test_n_zero_returns_nan(self):
        lo, hi = wilson_ci(0, 0)
        assert np.isnan(lo)
        assert np.isnan(hi)

    def test_perfect_rate(self):
        lo, hi = wilson_ci(100, 100)
        assert lo >= 0.9
        assert hi >= 0.9999  # clamped to 1.0 or very close due to float

    def test_zero_rate(self):
        lo, hi = wilson_ci(0, 100)
        assert lo == 0.0
        assert hi < 0.05  # tight CI near 0


# ── 2. Cohort-separation assertion ────────────────────────────────────────────

class TestCohortSeparation:
    def test_mixed_source_raises(self):
        df = pd.DataFrame({
            "event_id": ["A", "B"],
            "source": ["eod_proxy", "tape_recon"],
        })
        with pytest.raises(ValueError, match="Cohort separation violation"):
            _assert_single_source(df, "eod_proxy")

    def test_correct_source_passes(self):
        df = pd.DataFrame({
            "event_id": ["A", "B"],
            "source": ["eod_proxy", "eod_proxy"],
        })
        _assert_single_source(df, "eod_proxy")  # must not raise

    def test_missing_source_column_passes(self):
        df = pd.DataFrame({"event_id": ["A", "B"]})
        _assert_single_source(df, "eod_proxy")  # no source col → no check

    def test_wrong_source_single_value_raises(self):
        df = pd.DataFrame({
            "event_id": ["A"],
            "source": ["tape_recon"],
        })
        with pytest.raises(ValueError):
            _assert_single_source(df, "eod_proxy")


# ── 3. N-floor labeling ────────────────────────────────────────────────────────

class TestNFloor:
    def test_sparse_cell_below_floor(self):
        cell = _sparse_cell(5)
        assert cell["flag"] == "ERA-SPARSE"
        assert cell["stat"] is None
        assert cell["n"] == 5

    def test_rate_cell_suppressed_below_floor(self):
        cell = _rate_cell(5, N_FLOOR - 1)
        assert cell.get("flag") == "ERA-SPARSE"
        assert cell.get("stat") is None

    def test_rate_cell_emitted_at_floor(self):
        cell = _rate_cell(15, N_FLOOR)  # exactly at floor
        assert cell.get("flag") is None
        assert "rate" in cell
        assert cell["n"] == N_FLOOR
        assert "ci_lo" in cell
        assert "ci_hi" in cell

    def test_rate_cell_extra_fields_passed(self):
        cell = _rate_cell(20, 50, extra={"median_ret": 0.01})
        assert cell.get("median_ret") == 0.01


# ── 4. Accrual-label path ─────────────────────────────────────────────────────

class TestAccrualLabel:
    def test_table_a_with_empty_events(self, tmp_path):
        """Table A with empty cohort produces a result with no cells, no fabricated stats."""
        df = pd.DataFrame(columns=[
            "event_id", "era", "dte_bucket", "mny_bucket", "vol_gt_oi",
            "premium", "session_date", "source", "root", "zerodte",
        ])
        ev_path = tmp_path / "events.parquet"
        _write_parquet(df, ev_path)
        result = table_a(ev_path, "eod_proxy")
        assert result["table_id"] == "A"
        assert isinstance(result["cells"], list)
        # n_sessions should be 0 when no data
        assert result["n_sessions"] == 0

    def test_table_i_thin_cohort_sparse_cells(self):
        """Table I with n < N_FLOOR per era produces ERA-SPARSE cells, not fabricated rates."""
        n_per_era = N_FLOOR - 1  # below floor
        events = pd.concat([
            _make_eod_events(n_per_era, era="2012-15"),
            _make_eod_events(n_per_era, era="2020-22"),
        ], ignore_index=True)
        grades = _make_eod_grades(events)

        result = table_i(events, grades)
        for cell in result["cells"]:
            # fwd_ret_5 cell should be ERA-SPARSE because n < N_FLOOR
            r5 = cell.get("fwd_ret_5", {})
            assert r5.get("flag") == "ERA-SPARSE", (
                f"Expected ERA-SPARSE for era={cell['era']}, got {r5}"
            )


# ── 5. Table H: 0DTE index annotation ────────────────────────────────────────

class TestTableH:
    def _make_h_events(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Create events with 0DTE index + non-0DTE single-name groups."""
        n = 50
        idx_events = _make_eod_events(n, root="SPXW", zerodte=True, dte_bucket="0d", vol_gt_oi=True)
        sn_events = _make_eod_events(n, root="AAPL", zerodte=False, dte_bucket="8_30d", vol_gt_oi=True)
        events = pd.concat([idx_events, sn_events], ignore_index=True)
        grades = _make_eod_grades(events)
        return events, grades

    def test_0dte_index_has_trivial_voi_annotation(self):
        events, grades = self._make_h_events()
        result = table_h(events, grades)
        cells_by_group = {c["group"]: c for c in result["cells"]}
        idx_cell = cells_by_group.get("0DTE_index")
        assert idx_cell is not None, "0DTE_index cell should be present"
        # vol>OI rate should be 1.0 (all events are vol_gt_oi=True)
        voi = idx_cell.get("vol_gt_oi_rate", {})
        assert voi.get("rate") == 1.0
        # Note about structural artifact must be present
        assert idx_cell.get("note_0dte_voi") is not None

    def test_single_name_no_trivial_annotation(self):
        events, grades = self._make_h_events()
        result = table_h(events, grades)
        cells_by_group = {c["group"]: c for c in result["cells"]}
        sn_cell = cells_by_group.get("short_DTE_single_name")
        assert sn_cell is not None
        assert sn_cell.get("note_0dte_voi") is None


# ── 6. Table I: era-stratified hit-rate computation ──────────────────────────

class TestTableI:
    def test_hit_rate_matches_manual(self):
        """60/100 positive returns → hit_rate = 0.6."""
        n = 100
        events = _make_eod_events(n, era="2023+")
        grades = _make_eod_grades(events, hit_frac=0.6, ret_val=0.01)
        result = table_i(events, grades)
        cell = next(c for c in result["cells"] if c["era"] == "2023+")
        r5 = cell["fwd_ret_5"]
        assert r5.get("flag") is None
        # rate should be exactly 0.60 (60/100)
        assert abs(r5["rate"] - 0.6) < 1e-6

    def test_multiple_eras_independent_cells(self):
        n = 60
        events = pd.concat([
            _make_eod_events(n, era="2012-15"),
            _make_eod_events(n, era="2016-19"),
            _make_eod_events(n, era="2020-22"),
            _make_eod_events(n, era="2023+"),
        ], ignore_index=True)
        grades = _make_eod_grades(events, hit_frac=0.7)
        result = table_i(events, grades)
        assert len(result["cells"]) == 4
        eras = {c["era"] for c in result["cells"]}
        assert "2023+" in eras
        assert "2012-15" in eras

    def test_cohort_separation_enforced(self):
        events = _make_eod_events(50, source="tape_recon")
        grades = _make_eod_grades(events)
        with pytest.raises(ValueError, match="Cohort separation"):
            table_i(events, grades)


# ── 7. Table J: premium decile suppression ────────────────────────────────────

class TestTableJ:
    def test_enough_data_produces_deciles(self):
        """With 300 ok-graded events, all deciles should be above N_FLOOR."""
        n = 300
        # Vary premium to get real deciles
        events = _make_eod_events(n)
        events["premium"] = np.linspace(100_000, 1_000_000, n)
        grades = _make_eod_grades(events, hit_frac=0.6)
        result = table_j(events, grades)
        assert result.get("table_id") == "J"
        # Most cells should not be sparse (n = 30 per decile)
        non_sparse = [
            c for c in result["cells"]
            if c.get("fwd_ret_21", {}).get("flag") != "ERA-SPARSE"
        ]
        assert len(non_sparse) >= 8, f"Expected >= 8 non-sparse deciles, got {len(non_sparse)}"

    def test_thin_data_produces_sparse_cells(self):
        """With n < N_FLOOR * 10, some deciles should be ERA-SPARSE."""
        n = 20  # far below N_FLOOR * 10
        events = _make_eod_events(n)
        events["premium"] = np.linspace(100_000, 1_000_000, n)
        grades = _make_eod_grades(events, hit_frac=0.5)
        result = table_j(events, grades)
        # Should either be CANNOT_COMPUTE or have some ERA-SPARSE cells
        if result.get("status") == "CANNOT_COMPUTE":
            return  # acceptable
        any_sparse = any(
            c.get("fwd_ret_21", {}).get("flag") == "ERA-SPARSE"
            for c in result.get("cells", [])
        )
        assert any_sparse


# ── 8. Table K: crowdedness breakpoints from data ────────────────────────────

class TestTableK:
    def test_tercile_breakpoints_from_data(self):
        """Breakpoints must be computed from actual data, not hardcoded."""
        n = 200
        events = _make_eod_events(n)
        # Give varied session_dates so daily counts vary per root
        events["session_date"] = pd.date_range("2024-01-01", periods=n).astype(str)
        events["root"] = ["AAA" if i % 3 == 0 else "BBB" for i in range(n)]
        grades = _make_eod_grades(events, hit_frac=0.6)
        result = table_k(events, grades)
        bps = result.get("tercile_breakpoints", {})
        assert "p33" in bps and "p67" in bps
        assert bps["p33"] <= bps["p67"]

    def test_output_has_three_terciles_maximum(self):
        n = 150
        events = _make_eod_events(n)
        events["session_date"] = pd.date_range("2024-01-01", periods=n).astype(str)
        grades = _make_eod_grades(events, hit_frac=0.6)
        result = table_k(events, grades)
        # Should have at most 3 terciles
        assert len(result.get("cells", [])) <= 3


# ── 9. Table A: qual_class splitting ─────────────────────────────────────────

class TestTableA:
    def test_vol_gt_oi_class_present(self, tmp_path):
        n = 60
        df = _make_eod_events(n, vol_gt_oi=True)
        ev_path = tmp_path / "events.parquet"
        _write_parquet(df, ev_path)
        result = table_a(ev_path, "eod_proxy")
        qual_classes = {c["qual_class"] for c in result["cells"]}
        assert "vol_gt_oi" in qual_classes

    def test_premium_burst_class_present(self, tmp_path):
        n = 60
        df = _make_eod_events(n, vol_gt_oi=False)
        ev_path = tmp_path / "events.parquet"
        _write_parquet(df, ev_path)
        result = table_a(ev_path, "eod_proxy")
        qual_classes = {c["qual_class"] for c in result["cells"]}
        assert "premium_burst_only" in qual_classes

    def test_total_event_count_correct(self, tmp_path):
        n = 80
        df = _make_eod_events(n, vol_gt_oi=True)
        # Mix eras
        df.loc[df.index[:40], "era"] = "2020-22"
        df.loc[df.index[40:], "era"] = "2023+"
        ev_path = tmp_path / "events.parquet"
        _write_parquet(df, ev_path)
        result = table_a(ev_path, "eod_proxy")
        total = sum(c["n_events"] for c in result["cells"])
        assert total == n
