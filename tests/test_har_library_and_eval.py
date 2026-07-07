"""tests/test_har_library_and_eval.py — Unit tests for HAR library + eval.

Tests cover:
  1. Span segmentation boundary conditions (no open spans leak into library)
  2. Walk-forward retrieval cutoff enforcement
  3. Era-cap enforcement
  4. Shuffle null determinism (same seed = same result)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_analog_library import segment_spans, _normalize_trajectory, N_GRID
from engine.cycle_pattern.har import (
    query as har_query,
    _apply_era_cap,
    crps_normal_approximation,
    km_remaining_quantiles,
    ERA_CAP_K,
    ERA_WINDOW_M,
    _FP_COLS,
    _TRAJ_COLS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_state_df(entity_configs: list[dict]) -> pd.DataFrame:
    """Build a minimal state_monthly DataFrame for testing.

    Each config dict: {entity_id, dates, directions, pos_vals, age_m_vals}
    directions: list of 'up'/'down' per row.
    """
    rows = []
    for cfg in entity_configs:
        entity_id = cfg["entity_id"]
        family_prefix = entity_id.split(":")[0]
        for i, (d, dirn, pos, age) in enumerate(zip(
            cfg["dates"], cfg["directions"], cfg["pos_vals"], cfg["age_m_vals"]
        )):
            rows.append({
                "entity_id": entity_id,
                "native_id": entity_id.split(":")[1].upper(),
                "date": pd.Timestamp(d),
                "direction": dirn,
                "pos": float(pos),
                "age_m": float(age),
                "amp_proxy": 0.5,
                "quad": "Q2",
                "liquidity": "expanding",
                "vol_pctile": 0.5,
                "hazard_epoch": "price_c4414dcb",
            })
    return pd.DataFrame(rows)


def _make_library_row(
    span_id: str,
    family: str,
    direction: str,
    start_date: str,
    end_date: str,
    realized_dur_m: float,
    n_rows: int = 5,
) -> dict:
    row = {
        "span_id": span_id,
        "entity_id": f"{family}:TEST",
        "family": family,
        "direction": direction,
        "start_date": pd.Timestamp(start_date),
        "end_date": pd.Timestamp(end_date),
        "realized_dur_m": realized_dur_m,
        "n_rows": n_rows,
        "amp_proxy": 0.5,
        "revision_optimistic": True,
    }
    for i in range(N_GRID):
        row[f"norm_pos_{i}"] = 50.0  # neutral trajectory
    for col in _FP_COLS:
        row[col] = 0.25  # uniform fingerprint
    return row


# ── Test 1: Span segmentation — no open spans ────────────────────────────────

class TestSpanSegmentation:
    """Verify that the last span per entity (open) is excluded from the library."""

    def test_open_span_excluded(self):
        """Last span per entity must NOT appear in the library output."""
        # Entity with 3 direction changes → 4 spans: spans 1-3 completed, span 4 open
        state = _make_state_df([
            {
                "entity_id": "us_sector:XLK",
                "dates": [
                    "2015-01-31", "2015-02-28", "2015-03-31",  # span 1 (up)
                    "2015-04-30", "2015-05-31",                  # span 2 (down)
                    "2015-06-30", "2015-07-31", "2015-08-31",   # span 3 (up)
                    "2015-09-30", "2015-10-31",                  # span 4 (down) — OPEN
                ],
                "directions": ["up", "up", "up", "down", "down", "up", "up", "up", "down", "down"],
                "pos_vals": [30, 50, 70, 60, 40, 20, 40, 60, 80, 50],
                "age_m_vals": [1, 2, 3, 1, 2, 1, 2, 3, 1, 2],
            }
        ])
        records = segment_spans(state)
        lib = pd.DataFrame(records) if records else pd.DataFrame()

        # Should have exactly 3 completed spans
        assert len(lib) == 3, f"Expected 3, got {len(lib)}"

        # Open span (last direction run = down, ending at 2015-10-31) must not appear
        if len(lib) > 0:
            end_dates = pd.to_datetime(lib["end_date"])
            # Last span ends at 2015-10-31 → must not be in library
            assert not (end_dates == pd.Timestamp("2015-10-31")).any(), \
                "Open span leaked into library"

    def test_single_entity_single_span_is_open(self):
        """An entity with only one direction has NO completed spans."""
        state = _make_state_df([
            {
                "entity_id": "us_sector:XLB",
                "dates": ["2015-01-31", "2015-02-28", "2015-03-31"],
                "directions": ["up", "up", "up"],
                "pos_vals": [30, 50, 70],
                "age_m_vals": [1, 2, 3],
            }
        ])
        records = segment_spans(state)
        assert len(records) == 0, "Single span entity should yield 0 completed spans"

    def test_two_direction_changes_yield_two_completed_spans(self):
        """Three spans → 2 completed, 1 open."""
        state = _make_state_df([
            {
                "entity_id": "us_sector:XLE",
                "dates": ["2015-01-31", "2015-02-28",  # span 1 up
                          "2015-03-31", "2015-04-30",  # span 2 down
                          "2015-05-31", "2015-06-30",  # span 3 up (OPEN)
                         ],
                "directions": ["up", "up", "down", "down", "up", "up"],
                "pos_vals": [30, 60, 70, 40, 20, 50],
                "age_m_vals": [1, 2, 1, 2, 1, 2],
            }
        ])
        records = segment_spans(state)
        assert len(records) == 2
        directions = [r["direction"] for r in records]
        assert directions == ["up", "down"]

    def test_span_realized_dur_from_age_m_last(self):
        """realized_dur_m must equal age_m of the last row in the span."""
        state = _make_state_df([
            {
                "entity_id": "us_sector:XLF",
                "dates": ["2015-01-31", "2015-02-28", "2015-03-31",  # span 1 up, age: 1,2,3
                          "2015-04-30",                               # span 2 down, age: 1 (OPEN)
                         ],
                "directions": ["up", "up", "up", "down"],
                "pos_vals": [30, 50, 70, 40],
                "age_m_vals": [1.0, 2.1, 3.2, 1.0],  # span 1 last = 3.2
            }
        ])
        records = segment_spans(state)
        assert len(records) == 1
        assert abs(records[0]["realized_dur_m"] - 3.2) < 0.01


# ── Test 2: Walk-forward cutoff ───────────────────────────────────────────────

class TestWalkForwardCutoff:
    """har_query must not retrieve analogs with end_date >= cutoff_date."""

    def _build_library(self) -> pd.DataFrame:
        rows = [
            _make_library_row("span_A", "us_sector", "up", "2018-01-31", "2018-06-30", 6.0),
            _make_library_row("span_B", "us_sector", "up", "2020-01-31", "2020-06-30", 6.0),
            _make_library_row("span_C", "us_sector", "up", "2022-01-31", "2022-06-30", 6.0),
        ]
        return pd.DataFrame(rows)

    def test_cutoff_excludes_future_analogs(self):
        """With cutoff_date=2021-01-01, span_C (end=2022) must be excluded."""
        lib = self._build_library()
        q_traj = np.full(N_GRID, 50.0)
        q_fp = np.full(len(_FP_COLS), 0.25)

        result = har_query(
            current_age_m=1.0,
            current_pos_grid=q_traj,
            current_family="us_sector",
            current_fp=q_fp,
            library=lib,
            k=6,
            cutoff_date=pd.Timestamp("2021-01-01"),
        )
        # Only span_A and span_B should be eligible
        assert "span_C" not in result["analog_ids"], "Future analog leaked"
        assert result["n_candidates"] == 2

    def test_no_analogs_after_cutoff(self):
        """If all analogs are after cutoff, result should be empty-like."""
        lib = self._build_library()
        q_traj = np.full(N_GRID, 50.0)
        q_fp = np.full(len(_FP_COLS), 0.25)

        result = har_query(
            current_age_m=1.0,
            current_pos_grid=q_traj,
            current_family="us_sector",
            current_fp=q_fp,
            library=lib,
            k=6,
            cutoff_date=pd.Timestamp("2017-01-01"),  # before all analogs
        )
        assert result["n_candidates"] == 0
        assert np.isnan(result["p50"])


# ── Test 3: Era-cap enforcement ───────────────────────────────────────────────

class TestEraCap:
    """_apply_era_cap must limit to era_cap analogs per rolling era window."""

    def test_era_cap_limits_dense_era(self):
        """5 analogs in the same 24-month window → only era_cap=2 selected."""
        rows = [
            _make_library_row(f"span_{i}", "us_sector", "up",
                              f"2020-0{i+1}-01", f"2020-0{i+1}-28", float(i + 5))
            for i in range(5)
        ]
        lib = pd.DataFrame(rows)
        distances = np.array([0.1, 0.2, 0.3, 0.4, 0.5])  # span_0 is closest

        sel, sel_dists = _apply_era_cap(lib, distances, k=5, era_cap=2, era_window_m=24)
        # Should select at most 2 from the dense cluster
        assert len(sel) <= 2, f"Era cap not enforced: got {len(sel)}"

    def test_era_cap_allows_spread_analogs(self):
        """Analogs 3 years apart should not conflict with era cap."""
        rows = [
            _make_library_row("span_2010", "us_sector", "up", "2010-01-01", "2010-06-30", 6.0),
            _make_library_row("span_2013", "us_sector", "up", "2013-01-01", "2013-06-30", 6.0),
            _make_library_row("span_2016", "us_sector", "up", "2016-01-01", "2016-06-30", 6.0),
        ]
        lib = pd.DataFrame(rows)
        distances = np.array([0.1, 0.2, 0.3])

        sel, _ = _apply_era_cap(lib, distances, k=3, era_cap=2, era_window_m=24)
        # All 3 are spread > 24mo apart, so era_cap=2 per window allows all
        assert len(sel) == 3


# ── Test 4: Shuffle determinism ───────────────────────────────────────────────

class TestShuffleDeterminism:
    """Running shuffle with the same seed must produce identical results."""

    def test_shuffle_determinism(self):
        """Two runs with the same RNG seed must produce identical CRPS matrices."""
        from scripts.run_har1_eval import _shuffle_crps

        # Build minimal query rows
        rows = [
            {
                "span_id": f"s{i}", "family": "us_sector", "direction": "up",
                "start_date": pd.Timestamp("2024-01-31"),
                "end_date": pd.Timestamp("2024-06-30"),
                "realized_dur_m": float(5 + i),
                "era": 2024,
            }
            for i in range(5)
        ]
        query_rows = pd.DataFrame(rows)

        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        analog_results = [{"analog_ids": []} for _ in range(5)]

        mat1 = _shuffle_crps(query_rows, analog_results, rng1, n_shuffle=10)
        mat2 = _shuffle_crps(query_rows, analog_results, rng2, n_shuffle=10)

        np.testing.assert_array_equal(mat1, mat2,
                                      err_msg="Shuffle not deterministic with same seed")

    def test_shuffle_different_seeds_differ(self):
        """Two runs with different seeds must generally differ."""
        from scripts.run_har1_eval import _shuffle_crps

        rows = [
            {
                "span_id": f"s{i}", "family": "us_sector", "direction": "up",
                "start_date": pd.Timestamp("2024-01-31"),
                "end_date": pd.Timestamp("2024-06-30"),
                "realized_dur_m": float(5 + i),
                "era": 2024,
            }
            for i in range(10)
        ]
        query_rows = pd.DataFrame(rows)
        analog_results = [{"analog_ids": []} for _ in range(10)]

        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(99)
        mat1 = _shuffle_crps(query_rows, analog_results, rng1, n_shuffle=20)
        mat2 = _shuffle_crps(query_rows, analog_results, rng2, n_shuffle=20)

        # Should differ at least somewhere
        assert not np.allclose(mat1, mat2, equal_nan=True), \
            "Different seeds should produce different shuffle results"


# ── Test 5: CRPS and trajectory helpers ──────────────────────────────────────

class TestHelpers:
    def test_crps_exact_forecast(self):
        """Perfect point forecast (all quantiles = realized) should give CRPS = 0."""
        c = crps_normal_approximation(5.0, 5.0, 5.0, 5.0, 5.0, 5.0)
        assert abs(c) < 1e-10, f"Expected 0, got {c}"

    def test_crps_nan_on_nan_quantile(self):
        """NaN in any quantile should propagate to NaN CRPS."""
        c = crps_normal_approximation(float("nan"), 5.0, 5.0, 5.0, 5.0, 5.0)
        assert np.isnan(c)

    def test_normalize_trajectory_length(self):
        """Output must always have exactly N_GRID points."""
        for n_rows in [1, 2, 5, N_GRID, N_GRID + 3]:
            pos_vals = np.linspace(20, 80, n_rows)
            out = _normalize_trajectory(pos_vals)
            assert len(out) == N_GRID, f"n_rows={n_rows}: expected {N_GRID}, got {len(out)}"

    def test_normalize_trajectory_single_row(self):
        """Single-row span: all grid points equal the single pos value."""
        out = _normalize_trajectory(np.array([42.0]))
        assert np.allclose(out, 42.0)

    def test_km_remaining_quantiles_monotone(self):
        """Remaining time quantiles should be non-decreasing."""
        # Build a simple KM table
        km_table = [{"age_m": i + 1, "survival": max(0.01, 1.0 - 0.05 * (i + 1))}
                    for i in range(20)]
        result = km_remaining_quantiles(5.0, km_table)
        vals = [result["p10"], result["p25"], result["p50"], result["p75"], result["p90"]]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1] + 1e-6, \
                f"Quantiles not non-decreasing: {vals}"


# ── Test 6: Family mapping ────────────────────────────────────────────────────

class TestFamilyMapping:
    """bloc: prefix must map to 'country' family in library."""

    def test_bloc_maps_to_country(self):
        state = _make_state_df([
            {
                "entity_id": "bloc:EEM",
                "dates": ["2015-01-31", "2015-02-28",  # span 1
                          "2015-03-31",                 # span 2 (open)
                         ],
                "directions": ["up", "up", "down"],
                "pos_vals": [30, 60, 40],
                "age_m_vals": [1, 2, 1],
            }
        ])
        records = segment_spans(state)
        assert len(records) == 1
        assert records[0]["family"] == "country", \
            f"bloc should map to country, got {records[0]['family']}"

    def test_cn_sector_maps_to_cn_sector(self):
        state = _make_state_df([
            {
                "entity_id": "cn_sector:801010",
                "dates": ["2015-01-31", "2015-02-28",  # span 1
                          "2015-03-31",                 # span 2 (open)
                         ],
                "directions": ["up", "up", "down"],
                "pos_vals": [30, 60, 40],
                "age_m_vals": [1, 2, 1],
            }
        ])
        records = segment_spans(state)
        assert len(records) == 1
        assert records[0]["family"] == "cn_sector"
