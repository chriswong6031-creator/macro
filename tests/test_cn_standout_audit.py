"""SA-W2 CN foundations test suite.

Tests cover:
  - CN_LANE fail-closed write refusal (both new stores)
  - keep-first on regime_daily.parquet + cn_attribution.parquet
  - species_id mapping from row flags
  - two-axis attribution precedence + tiling + independence
  - us_proxy stratum never pooled (scoreboard unit test)
  - premature_stop_noise own-maturity exclusion
  - never-raise corrupt-artifact
  - data_gap absent-store honesty (no fabricated zeros)
  - regime_store.get_regime_for_date absent-store returns None (not zero)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module imports (lazy to allow tests to run without full engine available)
# ---------------------------------------------------------------------------

from engine.china_regime_store import (
    append as regime_append,
    get_regime_for_date,
    store_birth_date,
)
from engine.china_standout_audit import (
    _axis1_outcome,
    _axis2_process,
    _build_scoreboard,
    _effective_n,
    _wilson_ci,
    run_attribution,
    _TAXONOMY_CONSTANTS,
    _TAXONOMY_VERSION,
)
from engine.china_standout_track import _derive_species_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_regime_history(root: Path, date_str: str = "2026-07-12") -> None:
    """Create a minimal regime_history.parquet for test use."""
    p = root / "data" / "china_regime"
    p.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "growth_score": [0.3],
            "growth_confidence": [0.7],
            "growth_agreement": [0.6],
            "growth_n_components": [3],
            "inflation_score": [-0.1],
            "inflation_confidence": [0.6],
            "inflation_agreement": [0.5],
            "inflation_n_components": [3],
            "quad": ["Q1"],
            "pending_quad": [None],
            "pending_days": [0],
            "raw_quad": ["Q1"],
            "quad_name": ["Goldilocks"],
            "liquidity": ["expanding"],
            "cycle": ["mid"],
            "regime_confidence": [0.65],
        },
        index=pd.DatetimeIndex([pd.Timestamp(date_str)]),
    )
    df.to_parquet(p / "regime_history.parquet")


def _make_board(root: Path, dates: list[str] | None = None) -> pd.DataFrame:
    """Create a minimal board.parquet for test use."""
    if dates is None:
        dates = ["2026-07-01"]
    rows = []
    for d in dates:
        rows.append({
            "date": d,
            "ticker": "000001.SS",
            "board_rank": 1,
            "tier": "T1",
            "setup": None,
            "extended": False,
            "washout": False,
            "level": 100.0,
            "coiled": False,
            "coiled_star": False,
            "coiled_cohort": None,
            "coiled_fire": False,
            "coiled_fire_ticks": None,
            "ticks": None,
            "provisional": False,
            "ext_score": 0.2,
            "washout_2w": False,
            "hold_state": None,
            "entry_status": None,
            "sector_turn": None,
            "stage": None,
            "narr_theme": None,
            "narr_level": None,
            "narr_rel20": None,
            "narr_breadth": None,
            "ab_tier": None,
            "species_id": "cn_tier",
            "archetype": None,
            "own_market_regime": None,
            "own_market_regime_note": "null: test row",
            "fill_basis": "t1_hl2",
            "fwd_mfe_5": None,
            "fwd_mfe_10": None,
            "fwd_mfe_21": None,
            "fwd_mfe_63": None,
            "terminal_state_clean15_126": None,
            "terminal_state_clean8_21": None,
            "post_cushion_breach": None,
            # For attribution test
            "fwd_21d_excess": 0.05,
        })
    df = pd.DataFrame(rows)
    p = root / "data" / "china_standout_track"
    p.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p / "board.parquet", index=False)
    return df


# ---------------------------------------------------------------------------
# 1. CN_LANE fail-closed: regime store
# ---------------------------------------------------------------------------

class TestRegimeStoreLaneFail:
    def test_refuses_write_when_lane_not_asia(self, tmp_path, monkeypatch):
        """append() must refuse when CN_LANE != 'asia'."""
        _make_regime_history(tmp_path)
        monkeypatch.setenv("CN_LANE", "render")
        result = regime_append(asof="2026-07-12", root=tmp_path)
        assert result is False, "Should refuse write on non-asia lane"
        p = tmp_path / "data" / "china_regime" / "regime_daily.parquet"
        assert not p.exists(), "No parquet should be written on non-asia lane"

    def test_refuses_write_when_lane_empty(self, tmp_path, monkeypatch):
        """append() must refuse when CN_LANE is empty (default non-production)."""
        _make_regime_history(tmp_path)
        monkeypatch.delenv("CN_LANE", raising=False)
        result = regime_append(asof="2026-07-12", root=tmp_path)
        assert result is False

    def test_allows_write_when_lane_asia(self, tmp_path, monkeypatch):
        """append() must write when CN_LANE == 'asia'."""
        _make_regime_history(tmp_path)
        monkeypatch.setenv("CN_LANE", "asia")
        result = regime_append(asof="2026-07-12", root=tmp_path)
        assert result is True
        p = tmp_path / "data" / "china_regime" / "regime_daily.parquet"
        assert p.exists()


# ---------------------------------------------------------------------------
# 2. keep-first on regime_daily.parquet
# ---------------------------------------------------------------------------

class TestRegimeStoreKeepFirst:
    def test_keep_first_same_date(self, tmp_path, monkeypatch):
        """A second append for the same date must NOT overwrite the first row."""
        _make_regime_history(tmp_path)
        monkeypatch.setenv("CN_LANE", "asia")
        regime_append(asof="2026-07-12", root=tmp_path)
        p = tmp_path / "data" / "china_regime" / "regime_daily.parquet"
        df1 = pd.read_parquet(p)
        first_written_at = df1["written_at"].iloc[0]

        # Modify regime_history to simulate a re-run changing values
        import time as _time
        _time.sleep(0.01)  # ensure different timestamp
        regime_append(asof="2026-07-12", root=tmp_path)
        df2 = pd.read_parquet(p)
        assert len(df2) == 1, "Should remain 1 row (keep-first)"
        assert df2["written_at"].iloc[0] == first_written_at, "written_at must not change on re-run"

    def test_different_dates_both_appended(self, tmp_path, monkeypatch):
        """Two different dates both get rows."""
        _make_regime_history(tmp_path, "2026-07-12")
        monkeypatch.setenv("CN_LANE", "asia")
        regime_append(asof="2026-07-12", root=tmp_path)
        # Add second date
        _make_regime_history(tmp_path, "2026-07-11")
        regime_append(asof="2026-07-11", root=tmp_path)
        p = tmp_path / "data" / "china_regime" / "regime_daily.parquet"
        df = pd.read_parquet(p)
        assert len(df) == 2


# ---------------------------------------------------------------------------
# 3. species_id mapping from row flags
# ---------------------------------------------------------------------------

class TestSpeciesIdMapping:
    def test_washout_2w_true_gives_cn_washout(self):
        row = {"washout_2w": True, "coiled": False}
        assert _derive_species_id(row) == "cn_washout"

    def test_coiled_true_gives_cn_coiled(self):
        row = {"washout_2w": False, "coiled": True}
        assert _derive_species_id(row) == "cn_coiled"

    def test_default_gives_cn_tier(self):
        row = {"washout_2w": False, "coiled": False}
        assert _derive_species_id(row) == "cn_tier"

    def test_washout_takes_precedence_over_coiled(self):
        """washout_2w wins when both are True."""
        row = {"washout_2w": True, "coiled": True}
        assert _derive_species_id(row) == "cn_washout"

    def test_none_values_give_cn_tier(self):
        row = {"washout_2w": None, "coiled": None}
        assert _derive_species_id(row) == "cn_tier"

    def test_dict_coiled_form(self):
        """coiled as a dict (the raw row form from build_china_library)."""
        row = {"washout_2w": False, "coiled": {"coiled": True}}
        assert _derive_species_id(row) == "cn_coiled"


# ---------------------------------------------------------------------------
# 4. Two-axis attribution: precedence, tiling, independence
# ---------------------------------------------------------------------------

class TestAxis1Outcome:
    """Test axis-1 outcome-cause precedence and tiling."""

    def test_idio_break_takes_precedence(self):
        """idio_break > sector_rotated_out when idio vs sector is very negative."""
        c = _TAXONOMY_CONSTANTS
        # pick_excess < bench, sector_excess also negative → would also hit sector_rotated_out
        # but idio_break should win (sector_excess near zero = idio_break)
        pick_excess = c["IDIO_BREAK_PP"] - 0.01  # clearly below -4pp
        sector_excess = -0.01   # sector nearly flat
        bench_return = -0.02
        # idio vs sector = pick_excess - sector_excess = very negative
        assert _axis1_outcome(pick_excess, sector_excess, bench_return) == "idio_break"

    def test_sector_rotated_out(self):
        c = _TAXONOMY_CONSTANTS
        sector_excess = c["SECTOR_OUT_PP"] - 0.01  # -3.5pp sector
        pick_excess = sector_excess + 0.01   # pick tracks sector closely (idio ≈ 0.01)
        bench_return = 0.0
        assert _axis1_outcome(pick_excess, sector_excess, bench_return) == "sector_rotated_out"

    def test_macro_headwind(self):
        c = _TAXONOMY_CONSTANTS
        bench_return = c["MACRO_FALL_PCT"] - 0.01   # -4% market (below -3% threshold)
        sector_excess = -0.01                         # sector near flat vs bench
        # idio_vs_sector = pick_excess - sector_excess = bench_return + idio_target
        # For macro_headwind: abs(idio_vs_sector) <= IDIO_BAND_PP=0.02
        # We need bench_return + idio_target to be within ±0.02:
        # abs(-0.04 + idio_target) <= 0.02  →  idio_target in [0.02, 0.06]
        # Use idio_target = 0.03 → idio_vs_sector = -0.01 (within band)
        idio_target = 0.03
        pick_excess = bench_return + sector_excess + idio_target
        # verify construction: idio_vs_sector = -0.01, abs < 0.02
        assert abs((pick_excess - sector_excess)) <= c["IDIO_BAND_PP"]
        assert _axis1_outcome(pick_excess, sector_excess, bench_return) == "macro_headwind"

    def test_idio_alpha(self):
        c = _TAXONOMY_CONSTANTS
        sector_excess = 0.01
        pick_excess = sector_excess + c["IDIO_ALPHA_PP"] + 0.01  # clearly above +4pp idio
        bench_return = 0.02
        assert _axis1_outcome(pick_excess, sector_excess, bench_return) == "idio_alpha"

    def test_beta_tailwind(self):
        c = _TAXONOMY_CONSTANTS
        sector_excess = c["BETA_STRONG_PCT"] + 0.01   # sector well positive
        pick_excess = sector_excess + 0.005   # pick tracks sector (idio 0.5% < 2pp band)
        bench_return = 0.03
        assert _axis1_outcome(pick_excess, sector_excess, bench_return) == "beta_tailwind"

    def test_mixed_when_no_threshold_tiles(self):
        # Small excess, small sector, small bench
        assert _axis1_outcome(0.01, 0.005, 0.005) == "mixed"

    def test_none_pick_excess_returns_mixed(self):
        assert _axis1_outcome(None, 0.0, 0.0) == "mixed"

    def test_axes_are_independent(self):
        """outcome_cause and process_fault must be assigned independently.
        A row can have idio_break AND signaled_too_late simultaneously.
        """
        c = _TAXONOMY_CONSTANTS
        # Axis-1: idio_break
        pick_excess = c["IDIO_BREAK_PP"] - 0.01
        sector_excess = -0.01
        outcome = _axis1_outcome(pick_excess, sector_excess, -0.01)
        assert outcome == "idio_break"
        # Axis-2: signaled_too_late (independent)
        process = _axis2_process(
            ext_score=c["EXT_SCORE_LATE_PCT"] + 0.01,
            board_rank=5,
            stage=None,
            terminal_state=None,
            fwd_mfe_21=None,
        )
        assert process == "signaled_too_late"
        # Both truths are recorded independently — not one masking the other
        assert outcome != process  # different axes


class TestAxis2Process:
    """Test axis-2 process-fault precedence."""

    def test_ran_late_stage_gives_signaled_too_late(self):
        result = _axis2_process(
            ext_score=0.1, board_rank=5, stage="RAN_LATE",
            terminal_state=None, fwd_mfe_21=None,
        )
        assert result == "signaled_too_late"

    def test_high_ext_score_gives_signaled_too_late(self):
        c = _TAXONOMY_CONSTANTS
        result = _axis2_process(
            ext_score=c["EXT_SCORE_LATE_PCT"] + 0.01,
            board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
        )
        assert result == "signaled_too_late"

    def test_high_rank_gives_signaled_too_late(self):
        c = _TAXONOMY_CONSTANTS
        result = _axis2_process(
            ext_score=0.1,
            board_rank=c["LATE_RANK_THRESH"] + 1,
            stage=None,
            terminal_state=None, fwd_mfe_21=None,
        )
        assert result == "signaled_too_late"

    def test_premature_stop_noise_requires_own_maturity(self):
        """premature_stop_noise is NOT assigned when premature_stop_mature=False."""
        c = _TAXONOMY_CONSTANTS
        result = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state="STOPPED",
            fwd_mfe_21=c["PREMATURE_STOP_MFE_PP"] + 0.01,
            premature_stop_mature=False,  # immature — must not assign
        )
        assert result == "clean", (
            "premature_stop_noise must not be assigned when premature_stop_mature=False (SA-R10)"
        )

    def test_premature_stop_noise_with_maturity(self):
        c = _TAXONOMY_CONSTANTS
        result = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state="STOPPED",
            fwd_mfe_21=c["PREMATURE_STOP_MFE_PP"] + 0.01,
            premature_stop_mature=True,
        )
        assert result == "premature_stop_noise"

    def test_clean_when_nothing_tiles(self):
        result = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
        )
        assert result == "clean"


# ---------------------------------------------------------------------------
# 5. us_proxy stratum never pooled in scoreboard
# ---------------------------------------------------------------------------

class TestUsProxyNeverPooled:
    def test_us_proxy_stratum_is_distinct_cell(self):
        """Scoreboard must never pool us_proxy rows with own-market cells."""
        attribution = pd.DataFrame([
            {"date": "2026-07-01", "ticker": "000001.SS", "horizon": 21,
             "taxonomy_version": "v2", "outcome_cause": "mixed", "process_fault": "clean",
             "regime_stratum": "us_proxy", "fwd_excess": 0.05,
             "species_id": None, "own_market_regime": None},
            {"date": "2026-07-10", "ticker": "000002.SS", "horizon": 21,
             "taxonomy_version": "v2", "outcome_cause": "idio_alpha", "process_fault": "clean",
             "regime_stratum": "Q1", "fwd_excess": 0.08,
             "species_id": "cn_tier", "own_market_regime": "Q1"},
        ])
        scoreboard = _build_scoreboard(attribution, pd.DataFrame())
        cells = scoreboard.get("cells", [])
        strata = {c["stratum"] for c in cells}
        assert "us_proxy" in strata
        assert "Q1" in strata
        # us_proxy and Q1 must be separate cells
        us_cells = [c for c in cells if c["stratum"] == "us_proxy"]
        q1_cells = [c for c in cells if c["stratum"] == "Q1"]
        assert us_cells, "us_proxy stratum must be a separate cell"
        assert q1_cells, "Q1 stratum must be a separate cell"
        assert us_cells[0]["raw_n"] == 1
        assert q1_cells[0]["raw_n"] == 1

    def test_scoreboard_marks_us_proxy_flag(self):
        """us_proxy cells must carry us_proxy=True."""
        attribution = pd.DataFrame([
            {"date": "2026-07-01", "ticker": "000001.SS", "horizon": 21,
             "taxonomy_version": "v2", "outcome_cause": "mixed", "process_fault": "clean",
             "regime_stratum": "us_proxy", "fwd_excess": 0.05,
             "species_id": None, "own_market_regime": None},
        ])
        scoreboard = _build_scoreboard(attribution, pd.DataFrame())
        us_cells = [c for c in scoreboard["cells"] if c["stratum"] == "us_proxy"]
        assert us_cells[0]["us_proxy"] is True


# ---------------------------------------------------------------------------
# 6. Never-raise: corrupt artifact
# ---------------------------------------------------------------------------

class TestNeverRaise:
    def test_regime_append_never_raises_on_corrupt_history(self, tmp_path, monkeypatch):
        """append() must not raise even if regime_history.parquet is corrupt."""
        p = tmp_path / "data" / "china_regime"
        p.mkdir(parents=True, exist_ok=True)
        (p / "regime_history.parquet").write_bytes(b"not a valid parquet file at all")
        monkeypatch.setenv("CN_LANE", "asia")
        result = regime_append(asof="2026-07-12", root=tmp_path)
        assert result is False  # fails gracefully — never raises

    def test_run_attribution_never_raises_on_corrupt_board(self, tmp_path, monkeypatch):
        """run_attribution() must not raise even if board.parquet is corrupt."""
        p = tmp_path / "data" / "china_standout_track"
        p.mkdir(parents=True, exist_ok=True)
        (p / "board.parquet").write_bytes(b"not valid parquet")
        monkeypatch.setenv("CN_LANE", "asia")
        result = run_attribution(root=tmp_path, lane="asia")
        assert isinstance(result, dict)
        assert result.get("written") is False

    def test_get_regime_for_date_never_raises_absent_store(self, tmp_path):
        """get_regime_for_date() returns None (not zero) when store is absent."""
        result = get_regime_for_date("2026-07-12", root=tmp_path)
        assert result is None, (
            "absent store must return None, not a fabricated zero (SA-R15 data_gap law)"
        )


# ---------------------------------------------------------------------------
# 7. Data-gap honesty: absent store → None not zero
# ---------------------------------------------------------------------------

class TestDataGapHonesty:
    def test_absent_regime_store_returns_none(self, tmp_path):
        """get_regime_for_date: absent store → None, never 0."""
        r = get_regime_for_date("2026-07-12", root=tmp_path)
        assert r is None

    def test_store_birth_date_returns_none_when_absent(self, tmp_path):
        assert store_birth_date(root=tmp_path) is None

    def test_run_attribution_absent_board_returns_data_gap(self, tmp_path, monkeypatch):
        """run_attribution on missing board → written=False, not written=True with zeros."""
        monkeypatch.setenv("CN_LANE", "asia")
        result = run_attribution(root=tmp_path, lane="asia")
        assert result.get("written") is False
        reason = result.get("reason", "")
        assert reason, "Should explain why it did not write"


# ---------------------------------------------------------------------------
# 8. attribution keep-first
# ---------------------------------------------------------------------------

class TestAttributionKeepFirst:
    def test_cn_attribution_keep_first(self, tmp_path, monkeypatch):
        """A second run for the same (date, ticker, horizon, taxonomy_version) must not duplicate."""
        _make_board(tmp_path, ["2026-07-01"])
        monkeypatch.setenv("CN_LANE", "asia")
        run_attribution(root=tmp_path, lane="asia")
        run_attribution(root=tmp_path, lane="asia")
        attr_p = tmp_path / "data" / "standout_audit" / "cn_attribution.parquet"
        if attr_p.exists():
            df = pd.read_parquet(attr_p)
            key_cols = ["date", "ticker", "horizon", "taxonomy_version"]
            dups = df.duplicated(subset=key_cols)
            assert not dups.any(), "cn_attribution.parquet must not have duplicate keys"


# ---------------------------------------------------------------------------
# 9. Attribution lane fail-closed
# ---------------------------------------------------------------------------

class TestAttributionLaneFail:
    def test_attribution_refuses_write_on_non_asia_lane(self, tmp_path, monkeypatch):
        """run_attribution refuses writes when lane != 'asia'."""
        _make_board(tmp_path, ["2026-07-01"])
        monkeypatch.setenv("CN_LANE", "render")
        result = run_attribution(root=tmp_path, lane="render")
        assert result.get("written") is False
        attr_p = tmp_path / "data" / "standout_audit" / "cn_attribution.parquet"
        assert not attr_p.exists()


# ---------------------------------------------------------------------------
# 10. Wilson CI and effective-N helpers
# ---------------------------------------------------------------------------

class TestStatHelpers:
    def test_wilson_ci_zero_n(self):
        lo, hi = _wilson_ci(0, 0)
        assert lo == 0.0 and hi == 0.0

    def test_wilson_ci_all_wins(self):
        lo, hi = _wilson_ci(10, 10)
        assert lo > 0.7, "Wilson LB for k=n=10 should be well above 0.7"
        assert hi <= 1.0

    def test_effective_n_non_overlapping(self):
        """Four dates 7 days apart should yield 1 non-overlapping 30-day window."""
        dates = ["2026-07-01", "2026-07-08", "2026-07-15", "2026-07-22"]
        eff_n = _effective_n(dates)
        assert eff_n == 1, f"Expected 1 window for 4 dates within 30 days, got {eff_n}"

    def test_effective_n_two_windows(self):
        """Dates 35 days apart should span 2 windows."""
        dates = ["2026-07-01", "2026-08-05"]  # 35 days apart
        eff_n = _effective_n(dates)
        assert eff_n == 2

    def test_effective_n_empty(self):
        assert _effective_n([]) == 0
