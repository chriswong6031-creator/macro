"""Tests for the pick-lab snapshot producer integration.

Covers:
  - build_core_rows: assembles rows from synthetic profile/gate/tech/osc dicts
  - build_core_rows: null-honest tolerance (missing keys → None, no crash)
  - build_core_rows: priority order (profile > board_rec > technicals > oscillators)
  - build_core_rows: SNAPSHOT_COLUMNS completeness (all columns present, even if None)
  - write_snapshot / latest_snapshot: round-trip + keep-first dedup
  - producer assembly helpers: dd_pct computation from close array mirrors F1D logic

Does NOT import or run build_stock_library (heavy pipeline dependency).
Does NOT call engine.signal_quality, engine.stock_score, or any network/disk paths.

Run:
    python -m pytest tests/test_pick_lab_snapshot_producer.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.snapshot import (
    SNAPSHOT_COLUMNS,
    build_core_rows,
    write_snapshot,
    latest_snapshot,
)
from engine.pick_lab.signals_1d import compute_grids


# ============================================================ helpers ========

def _make_dates(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _rising_close(n: int = 350) -> pd.Series:
    """Monotonically rising series with sufficient history for all oscillators."""
    dates = _make_dates(n)
    return pd.Series(np.linspace(10.0, 200.0, n), index=dates)


def _declining_close(n: int = 350) -> pd.Series:
    """Declining then recovering series (washout shape)."""
    dates = _make_dates(n)
    prices = np.concatenate([
        np.linspace(100.0, 10.0, 200),   # sharp decline
        np.linspace(10.0, 20.0, 150),    # partial recovery
    ])
    return pd.Series(prices, index=dates)


# ============================================================ build_core_rows =

class TestBuildCoreRows:
    """Unit tests for the PURE build_core_rows assembler."""

    def test_empty_profiles(self):
        """No profiles → no rows, no crash."""
        rows = build_core_rows(profile_dicts=[], asof="2026-07-09")
        assert rows == []

    def test_single_profile_all_cols_present(self):
        """A single profile dict produces a row with every SNAPSHOT_COLUMN key."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAPL", "composite_z": 1.5, "close": 180.0}],
            asof="2026-07-09",
        )
        assert len(rows) == 1
        row = rows[0]
        for col in SNAPSHOT_COLUMNS:
            assert col in row, f"Missing column: {col}"

    def test_asof_stamped(self):
        """asof is always stamped on the row."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAPL"}],
            asof="2026-07-09",
        )
        assert rows[0]["asof"] == "2026-07-09"

    def test_ticker_required(self):
        """A profile without 'ticker' is skipped."""
        rows = build_core_rows(
            profile_dicts=[{"composite_z": 1.0}],  # no ticker
            asof="2026-07-09",
        )
        assert rows == []

    def test_missing_keys_are_none(self):
        """Fields not supplied in any source dict are None (null-honest)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAPL", "composite_z": 2.0}],
            asof="2026-07-09",
        )
        row = rows[0]
        # Columns not explicitly supplied must be None
        assert row["d1_macd"] is None
        assert row["d3_k"] is None
        assert row["tier"] is None
        assert row["archetype"] is None
        assert row["sector_phase"] is None   # enrichment null

    def test_board_rec_gate_fields(self):
        """board_rec_dicts supplies gate fields (tier, t_ticks, gate_state)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "MSFT", "composite_z": 3.0}],
            board_rec_dicts={"MSFT": {"tier": "T2", "t_ticks": 1, "gate_state": "eligible"}},
            asof="2026-07-09",
        )
        row = rows[0]
        assert row["tier"] == "T2"
        assert row["t_ticks"] == 1
        assert row["gate_state"] == "eligible"

    def test_oscillator_fields_merged(self):
        """oscillator_dicts supplies d1/d2/d3 fields."""
        osc = {
            "TSLA": {
                "d1_macd": 0.5, "d1_sig": 0.3, "d1_macd_xup_bars": 2.0,
                "d1_k": 60.0, "d1_d": 55.0, "d1_kd_xup_bars": 1.0,
                "d1_from_os": True, "d1_ob": False,
                "d3_macd": 0.2, "d3_sig": 0.1, "d3_k": 70.0, "d3_d": 65.0,
                "weekly_bull": True,
            }
        }
        rows = build_core_rows(
            profile_dicts=[{"ticker": "TSLA"}],
            oscillator_dicts=osc,
            asof="2026-07-09",
        )
        row = rows[0]
        assert row["d1_macd"] == 0.5
        assert row["d3_macd"] == 0.2
        assert row["weekly_bull"] is True

    def test_priority_order_profile_wins(self):
        """profile_dicts wins over board_rec_dicts for shared keys (keep-first)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "X", "tier": "T1_PROFILE"}],
            board_rec_dicts={"X": {"tier": "T2_BOARD"}},
            asof="2026-07-09",
        )
        # profile goes first in merge order, so its tier wins
        assert rows[0]["tier"] == "T1_PROFILE"

    def test_multiple_tickers(self):
        """Multiple tickers produce one row each, correctly keyed."""
        rows = build_core_rows(
            profile_dicts=[
                {"ticker": "AAPL", "composite_z": 1.0},
                {"ticker": "MSFT", "composite_z": 2.0},
                {"ticker": "GOOG", "composite_z": 3.0},
            ],
            asof="2026-07-09",
        )
        assert len(rows) == 3
        tickers = {r["ticker"] for r in rows}
        assert tickers == {"AAPL", "MSFT", "GOOG"}

    def test_all_sources_empty_dicts(self):
        """Empty source dicts for board/tech/osc: only profile fields in row."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "Z", "composite_z": 0.5}],
            board_rec_dicts={},
            technicals_dicts={},
            oscillator_dicts={},
            asof="2026-07-09",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["composite_z"] == 0.5
        assert row["tier"] is None

    def test_technicals_dict_supplies_dd_pct(self):
        """technicals_dicts supplies dd_pct (and other tech fields)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "MU"}],
            technicals_dicts={"MU": {"dd_pct": 0.31}},
            asof="2026-07-09",
        )
        assert rows[0]["dd_pct"] == 0.31

    def test_calm_stress_on_row(self):
        """calm and stress passed in profile_dicts are stamped on the row."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "SPY", "calm": 1.0, "stress": 0.0}],
            asof="2026-07-09",
        )
        assert rows[0]["calm"] == 1.0
        assert rows[0]["stress"] == 0.0

    def test_enrichment_cols_null(self):
        """sector_phase/stage/bucket (PL-R7b enrichment) are None in core rows."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "HD"}],
            asof="2026-07-09",
        )
        row = rows[0]
        for col in ("sector_phase", "sector_stage", "sector_rs_mom20", "sector_bucket"):
            assert row[col] is None, f"{col} should be None before enrichment"

    def test_authority_not_set_in_core_rows(self):
        """build_core_rows is a pure schema builder; authority is stamped by the runner."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "A"}],
            asof="2026-07-09",
        )
        # authority is NOT part of SNAPSHOT_COLUMNS — it's added by write_snapshot convention
        # Core rows must not accidentally inject it
        assert "authority" not in rows[0] or rows[0].get("authority") is None


# ============================================================ write/read =====

class TestWriteSnapshot:
    """Round-trip and dedup tests for write_snapshot / latest_snapshot."""

    def test_write_and_read_round_trip(self, tmp_path):
        """Write rows then read them back via latest_snapshot."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAPL", "composite_z": 1.5, "close": 180.0}],
            asof="2026-07-09",
        )
        df = pd.DataFrame(rows)
        n = write_snapshot(df, "2026-07-09", base_dir=str(tmp_path))
        assert n == 1

        snap, asof = latest_snapshot(base_dir=str(tmp_path))
        assert snap is not None
        assert asof == "2026-07-09"
        assert "AAPL" in snap.index
        assert snap.at["AAPL", "composite_z"] == 1.5

    def test_idempotent_write(self, tmp_path):
        """Writing the same (asof, ticker) twice is a no-op (keep-first dedup)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "MSFT", "composite_z": 2.0}],
            asof="2026-07-09",
        )
        df = pd.DataFrame(rows)
        n1 = write_snapshot(df, "2026-07-09", base_dir=str(tmp_path))
        n2 = write_snapshot(df, "2026-07-09", base_dir=str(tmp_path))
        assert n1 == 1
        assert n2 == 0  # already present — no new rows written

    def test_multiple_dates_partitioned(self, tmp_path):
        """Different dates write to monthly partitions; latest_snapshot returns max asof."""
        for asof, ticker, z in [
            ("2026-06-30", "AAPL", 1.0),
            ("2026-07-01", "MSFT", 2.0),
            ("2026-07-09", "GOOG", 3.0),
        ]:
            rows = build_core_rows(
                profile_dicts=[{"ticker": ticker, "composite_z": z}],
                asof=asof,
            )
            write_snapshot(pd.DataFrame(rows), asof, base_dir=str(tmp_path))

        snap, asof = latest_snapshot(base_dir=str(tmp_path))
        assert asof == "2026-07-09"
        assert "GOOG" in snap.index

    def test_no_snapshot_returns_none(self, tmp_path):
        """latest_snapshot on an empty dir returns (None, None)."""
        snap, asof = latest_snapshot(base_dir=str(tmp_path))
        assert snap is None
        assert asof is None


# ============================================================ producer helpers =

class TestProducerHelpers:
    """Test the dd_pct computation logic as used in the producer block.

    The producer computes dd_pct inline from _ext_closes using the same
    constants as the F1D shadow ledger block (WASH_B=91, WASH_A=217).
    This test validates that logic in isolation.
    """

    WASH_B = 91
    WASH_A = 217

    def _dd_pct_from_close(self, close_arr: np.ndarray) -> float | None:
        """Replicate the dd_pct computation used in the producer block."""
        n = len(close_arr)
        if n < self.WASH_A + self.WASH_B:
            return None
        window = close_arr[n - self.WASH_B:]
        local_min = int(np.argmin(window))
        capit_pos = (n - self.WASH_B) + local_min
        if capit_pos < 126:
            return None
        prior_max = float(np.nanmax(close_arr[capit_pos - 126: capit_pos]))
        if prior_max <= 0:
            return None
        return float(-(close_arr[capit_pos] / prior_max - 1.0))

    def test_deep_washout_detected(self):
        """A 40% drawdown series returns dd_pct ≈ 0.40."""
        n = 400
        close = np.concatenate([
            np.linspace(100.0, 100.0, 200),  # flat base
            np.linspace(100.0, 60.0, 91),    # 40% decline in the washout window
            np.linspace(60.0, 70.0, 109),    # partial recovery
        ])
        dd = self._dd_pct_from_close(close)
        assert dd is not None
        assert 0.30 <= dd <= 0.50, f"Expected ~0.40, got {dd}"

    def test_insufficient_history_returns_none(self):
        """Too few bars → None (null-honest)."""
        close = np.linspace(10.0, 100.0, 200)  # below WASH_A + WASH_B = 308
        dd = self._dd_pct_from_close(close)
        assert dd is None

    def test_flat_series_returns_small_or_none(self):
        """Flat price → no real drawdown → dd_pct near 0 or None (capit_pos check)."""
        close = np.full(350, 50.0)
        dd = self._dd_pct_from_close(close)
        # Flat series: argmin=0, capit_pos could be < 126; dd is None or ~0
        assert dd is None or dd < 0.05


# ============================================================ null-honest tolerance =

class TestNullHonestTolerance:
    """The assembly must tolerate any combination of missing source dicts."""

    @pytest.mark.parametrize("missing_source", [
        "board_rec_dicts",
        "technicals_dicts",
        "oscillator_dicts",
    ])
    def test_missing_source_dict_no_crash(self, missing_source):
        """Omitting any source dict does not crash; affected cols are None."""
        kwargs: dict = dict(
            profile_dicts=[{"ticker": "A", "composite_z": 1.0}],
            board_rec_dicts={"A": {"tier": "T1"}},
            technicals_dicts={"A": {"dd_pct": 0.25}},
            oscillator_dicts={"A": {"d1_macd": 0.3}},
            asof="2026-07-09",
        )
        del kwargs[missing_source]
        rows = build_core_rows(**kwargs)
        assert len(rows) == 1

    def test_extra_keys_in_profile_passthrough(self):
        """Extra keys in profile_dicts beyond SNAPSHOT_COLUMNS are passed through
        (build_core_rows is a merge helper, not a strict schema filter).
        The snapshot DataFrame write will just carry them as extra columns.
        """
        rows = build_core_rows(
            profile_dicts=[{"ticker": "B", "EXTRA_UNKNOWN_KEY": "foo", "composite_z": 1.0}],
            asof="2026-07-09",
        )
        row = rows[0]
        # All SNAPSHOT_COLUMNS must be present
        for col in SNAPSHOT_COLUMNS:
            assert col in row, f"Missing snapshot column: {col}"
        # composite_z value is correct
        assert row["composite_z"] == 1.0

    def test_board_rec_for_unknown_ticker_ignored(self):
        """board_rec_dicts entries for tickers not in profile_dicts are silently ignored."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "KNOWN"}],
            board_rec_dicts={"UNKNOWN": {"tier": "T1"}},
            asof="2026-07-09",
        )
        assert len(rows) == 1
        assert rows[0]["ticker"] == "KNOWN"

    def test_none_values_in_source_are_null_honest(self):
        """Explicit None values in source dicts are preserved as None in output."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "C", "composite_z": None}],
            asof="2026-07-09",
        )
        assert rows[0]["composite_z"] is None

    def test_all_sources_missing_data_for_ticker(self):
        """Ticker in profile only, no matching entries in other dicts → all other cols None."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "SOLO"}],
            board_rec_dicts={"OTHER": {"tier": "T2"}},
            technicals_dicts={"OTHER": {"dd_pct": 0.1}},
            oscillator_dicts={"OTHER": {"d1_macd": 0.5}},
            asof="2026-07-09",
        )
        row = rows[0]
        assert row["ticker"] == "SOLO"
        assert row["tier"] is None
        assert row["dd_pct"] is None
        assert row["d1_macd"] is None


# ============================================================ dd_pct merge path =

class TestDdPctMergePath:
    """Producer-path regression: dd_pct=None in profile must NOT block the real value
    from technicals_dicts.  Finding: build_core_rows kept the None from the higher-
    priority profile source and ignored the computed value in technicals_dicts because
    the old code used `if k not in row` (presence-only guard).  Fixed to
    `if k not in row or row[k] is None`.
    """

    def test_dd_pct_none_in_profile_overridden_by_technicals(self):
        """profile_dicts seeds dd_pct=None; technicals_dicts has the computed value.
        The computed value must win (None is overridable by a real value).
        """
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAA", "dd_pct": None}],
            technicals_dicts={"AAA": {"dd_pct": 0.35}},
            asof="2026-07-09",
        )
        assert len(rows) == 1
        assert rows[0]["dd_pct"] == 0.35, (
            f"dd_pct should be 0.35 from technicals_dicts, got {rows[0]['dd_pct']}"
        )

    def test_dd_pct_real_value_in_profile_blocks_technicals(self):
        """If profile has a real (non-None) dd_pct, that value wins (keep-first for
        non-None values is still honoured)."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "BBB", "dd_pct": 0.10}],
            technicals_dicts={"BBB": {"dd_pct": 0.90}},
            asof="2026-07-09",
        )
        assert rows[0]["dd_pct"] == 0.10, (
            "Profile's real dd_pct should win over technicals; got "
            f"{rows[0]['dd_pct']}"
        )

    def test_false_and_zero_in_profile_not_overridden(self):
        """False and 0 are real values and must not be overridden by later sources."""
        rows = build_core_rows(
            profile_dicts=[{"ticker": "CCC", "above_200": False, "rsi14": 0.0}],
            technicals_dicts={"CCC": {"above_200": True, "rsi14": 55.0}},
            asof="2026-07-09",
        )
        assert rows[0]["above_200"] is False, "False from profile must not be overridden"
        assert rows[0]["rsi14"] == 0.0, "0.0 from profile must not be overridden"

    def test_producer_pipeline_dd_pct_reaches_row(self):
        """End-to-end producer path: mimics build_stock_library seeding dd_pct=None in
        the profile (as it does in production) then computing it into _plab_tech_dicts.
        Verifies the fix is load-bearing for the washout books (PL-R3 family C).
        """
        # profile carries dd_pct=None (as the real producer does at line 3956)
        profile_dicts = [
            {"ticker": "WASH", "composite_z": 1.2, "washout_active": True, "dd_pct": None},
        ]
        # technicals_dicts carries the computed value (from the dd_pct loop, lines 3986-4008)
        technicals_dicts = {"WASH": {"dd_pct": 0.42}}

        rows = build_core_rows(
            profile_dicts=profile_dicts,
            technicals_dicts=technicals_dicts,
            asof="2026-07-09",
        )
        assert rows[0]["dd_pct"] == 0.42, (
            "dd_pct computed in _plab_tech_dicts must reach the snapshot row; "
            f"got {rows[0]['dd_pct']} — washout books 9/11 would be silent producers"
        )

    def test_write_snapshot_upsert_persists_enrichment(self, tmp_path):
        """Upsert mode replaces existing (asof, ticker) rows so enrichment columns
        are actually persisted.  Verifies the PL-R7 fix in build_pick_lab.py.
        """
        asof = "2026-07-09"
        # Core write (as build_stock_library does): sector_stage=None
        core_df = pd.DataFrame([{
            "ticker": "ENRICH",
            "asof": asof,
            "sector_stage": None,
            "calm": None,
            "composite_z": 1.5,
        }])
        n1 = write_snapshot(core_df, asof, base_dir=str(tmp_path))
        assert n1 == 1

        # Enriched re-write (as build_pick_lab does): sector_stage='Expansion', calm=0.7
        enriched_df = pd.DataFrame([{
            "ticker": "ENRICH",
            "asof": asof,
            "sector_stage": "Expansion",
            "calm": 0.7,
            "composite_z": 1.5,
        }])
        n2 = write_snapshot(enriched_df, asof, base_dir=str(tmp_path), mode="upsert")
        assert n2 == 1, f"Upsert should report 1 row written, got {n2}"

        # Read back and confirm enrichment survived
        snap, snap_asof = latest_snapshot(base_dir=str(tmp_path))
        assert snap is not None
        assert "ENRICH" in snap.index
        assert snap.at["ENRICH", "sector_stage"] == "Expansion", (
            f"sector_stage should be 'Expansion' after upsert, "
            f"got {snap.at['ENRICH', 'sector_stage']}"
        )
        assert abs(snap.at["ENRICH", "calm"] - 0.7) < 1e-6


# ============================================================ signals_1d compat =

class TestSignals1dCompat:
    """Smoke tests ensuring signals_1d output is compatible with the producer's osc_dicts."""

    def test_compute_grids_output_has_expected_columns(self):
        """compute_grids returns a DataFrame with all d1_ and d2_ osc columns."""
        panel = pd.DataFrame(
            {"AAPL": _rising_close(), "TSLA": _declining_close()},
        )
        result = compute_grids(panel)
        expected_grids = ["d1", "d2"]
        expected_suffixes = ["macd", "sig", "macd_xup_bars", "k", "d", "kd_xup_bars", "from_os", "ob"]
        for g in expected_grids:
            for s in expected_suffixes:
                col = f"{g}_{s}"
                assert col in result.columns, f"Missing column {col} in compute_grids output"

    def test_compute_grids_output_compatible_with_osc_dicts(self):
        """The osc row dict built from compute_grids is accepted by build_core_rows."""
        panel = pd.DataFrame({"X": _rising_close()})
        d12 = compute_grids(panel)

        osc_dicts = {}
        if "X" in d12.index:
            row = d12.loc["X"].to_dict()
            # Null-filter: build_core_rows accepts None values; NaN needs to be None
            osc_dicts["X"] = {
                k: (None if (v is not None and not isinstance(v, (bool, str)) and pd.isna(v)) else v)
                for k, v in row.items()
            }

        rows = build_core_rows(
            profile_dicts=[{"ticker": "X", "composite_z": 1.0}],
            oscillator_dicts=osc_dicts,
            asof="2026-07-09",
        )
        assert len(rows) == 1
        # Should not crash; d1_macd value is either float or None
        d1_macd = rows[0]["d1_macd"]
        assert d1_macd is None or isinstance(d1_macd, (int, float))
