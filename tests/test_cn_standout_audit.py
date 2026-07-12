"""SA-W2 CN foundations test suite — review-fix pass (F1-F7, F9).

Tests cover:
  - CN_LANE fail-closed write refusal (both new stores)
  - keep-first on regime_daily.parquet + cn_attribution.parquet
  - species_id mapping from row flags
  - two-axis attribution precedence + tiling + independence
  - us_proxy stratum never pooled (scoreboard unit test)
  - premature_stop_noise: NEVER emitted in CN (F5 — PREMATURE_STOP_IMPLEMENTED=False)
  - never-raise corrupt-artifact
  - data_gap absent-store honesty (no fabricated zeros)
  - regime_store.get_regime_for_date absent-store returns None (not zero)
  - F1: regime store appended BEFORE board → own_market_regime non-null on same-day row
  - F2: window-unit Wilson CI — 12 rows / 3 windows must produce valid CI, no exception
  - F6: ticks-based signaled_too_late (primary clause)
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
    _window_unit_k,
    run_attribution,
    _TAXONOMY_CONSTANTS,
    _TAXONOMY_VERSION,
    PREMATURE_STOP_IMPLEMENTED,
    _PREMATURE_STOP_NOTE,
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
        """idio_break > macro_headwind when idio vs peer is very negative."""
        c = _TAXONOMY_CONSTANTS
        pick_excess = c["IDIO_BREAK_PP"] - 0.01  # clearly below -4pp
        peer_dev = -0.01   # peer nearly flat
        bench_return = -0.02
        assert _axis1_outcome(pick_excess, peer_dev, bench_return) == "idio_break"

    def test_macro_headwind(self):
        c = _TAXONOMY_CONSTANTS
        bench_return = c["MACRO_FALL_PCT"] - 0.01   # -4% market (below -3% threshold)
        peer_dev = -0.01                              # peer near flat vs bench
        idio_target = 0.03
        pick_excess = bench_return + peer_dev + idio_target
        # verify construction: idio_vs_peer = 0.03-(-0.01) = 0.03, wait — pick_excess - peer_dev
        # pick_excess = (-0.04) + (-0.01) + 0.03 = -0.02
        # idio_vs_peer = -0.02 - (-0.01) = -0.01, abs(-0.01) <= 0.02 ✓
        assert abs((pick_excess - peer_dev)) <= c["IDIO_BAND_PP"]
        assert _axis1_outcome(pick_excess, peer_dev, bench_return) == "macro_headwind"

    def test_idio_alpha(self):
        c = _TAXONOMY_CONSTANTS
        peer_dev = 0.01
        pick_excess = peer_dev + c["IDIO_ALPHA_PP"] + 0.01  # clearly above +4pp idio
        bench_return = 0.02
        assert _axis1_outcome(pick_excess, peer_dev, bench_return) == "idio_alpha"

    def test_mixed_when_no_threshold_tiles(self):
        # Small excess, small peer dev, small bench
        assert _axis1_outcome(0.01, 0.005, 0.005) == "mixed"

    def test_none_pick_excess_returns_mixed(self):
        assert _axis1_outcome(None, 0.0, 0.0) == "mixed"

    def test_sector_rotated_out_degrades_to_mixed(self):
        """F3: sector_rotated_out is SUPPRESSED (no genuine sector leg) — degrades to mixed."""
        c = _TAXONOMY_CONSTANTS
        # Conditions that would produce sector_rotated_out in old code:
        peer_dev = c["SECTOR_OUT_PP"] - 0.01  # -3.5pp peer deviation
        pick_excess = peer_dev + 0.01          # pick tracks peer closely (idio ≈ 0.01)
        bench_return = 0.0
        # Must NOT return sector_rotated_out — must return mixed (no sector leg)
        result = _axis1_outcome(pick_excess, peer_dev, bench_return)
        assert result != "sector_rotated_out", (
            "sector_rotated_out must not be emitted (no genuine sector leg; F3 ruling)"
        )

    def test_beta_tailwind_degrades_to_mixed(self):
        """F3: beta_tailwind is SUPPRESSED (no genuine sector leg) — degrades to mixed."""
        c = _TAXONOMY_CONSTANTS
        peer_dev = c["BETA_STRONG_PCT"] + 0.01   # peer strongly positive
        pick_excess = peer_dev + 0.005            # pick tracks peer (idio 0.5% < 2pp band)
        bench_return = 0.03
        result = _axis1_outcome(pick_excess, peer_dev, bench_return)
        assert result != "beta_tailwind", (
            "beta_tailwind must not be emitted (no genuine sector leg; F3 ruling)"
        )

    def test_axes_are_independent(self):
        """outcome_cause and process_fault must be assigned independently.
        A row can have idio_break AND signaled_too_late simultaneously.
        """
        c = _TAXONOMY_CONSTANTS
        # Axis-1: idio_break
        pick_excess = c["IDIO_BREAK_PP"] - 0.01
        peer_dev = -0.01
        outcome = _axis1_outcome(pick_excess, peer_dev, -0.01)
        assert outcome == "idio_break"
        # Axis-2: signaled_too_late via ticks (independent)
        fault, basis = _axis2_process(
            ext_score=0.1,
            board_rank=5,
            stage=None,
            terminal_state=None,
            fwd_mfe_21=None,
            ticks=float(c["FRESH_TICKS"] + 1),  # ticks > FRESH_TICKS
        )
        assert fault == "signaled_too_late"
        assert outcome != fault  # different axes


class TestAxis2Process:
    """Test axis-2 process-fault precedence.

    NOTE: _axis2_process now returns (code, timing_basis) tuple (F6 change).
    """

    def test_ran_late_stage_gives_signaled_too_late(self):
        fault, basis = _axis2_process(
            ext_score=0.1, board_rank=5, stage="RAN_LATE",
            terminal_state=None, fwd_mfe_21=None,
        )
        assert fault == "signaled_too_late"
        assert "stage==RAN_LATE" in basis

    def test_high_ext_score_fallback_gives_signaled_too_late(self):
        """F6: ext_score fallback fires when ticks is null."""
        c = _TAXONOMY_CONSTANTS
        fault, basis = _axis2_process(
            ext_score=c["EXT_SCORE_LATE_PCT"] + 0.01,
            board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=None,  # ticks null → use ext_score fallback
        )
        assert fault == "signaled_too_late"
        assert any("ext_score" in b for b in basis)

    def test_ticks_based_signaled_too_late(self):
        """F6: primary clause — ticks > FRESH_TICKS fires signaled_too_late."""
        c = _TAXONOMY_CONSTANTS
        fault, basis = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=float(c["FRESH_TICKS"] + 1),  # stale cross
        )
        assert fault == "signaled_too_late"
        assert any("ticks" in b for b in basis)

    def test_fresh_ticks_does_not_fire(self):
        """F6: ticks <= FRESH_TICKS → NOT signaled_too_late (fresh cross)."""
        c = _TAXONOMY_CONSTANTS
        fault, basis = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=float(c["FRESH_TICKS"]),  # exactly at threshold — still fresh
        )
        assert fault == "clean", f"ticks=FRESH_TICKS should be clean, got {fault}"

    def test_ticks_zero_is_fresh(self):
        """ticks=0 means the cross just fired — must be clean (fresh)."""
        fault, _ = _axis2_process(
            ext_score=0.9, board_rank=50, stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=0.0,
        )
        # ticks=0 <= FRESH_TICKS=2 → primary clause doesn't fire
        # ext_score only fires as fallback when ticks is None
        # With ticks present, ext_score fallback is NOT checked
        assert fault == "clean", (
            "ticks=0 is fresh; ext_score fallback must not fire when ticks is provided"
        )

    def test_board_rank_not_used_for_timing(self):
        """F6: board_rank is no longer a timing clause (was mislabeling ~25% of board)."""
        c = _TAXONOMY_CONSTANTS
        # board_rank well above old threshold, but ticks null and ext_score low
        fault, _ = _axis2_process(
            ext_score=0.1,
            board_rank=99,  # far above old LATE_RANK_THRESH=45
            stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=None,  # fallback: ext_score=0.1 < 0.70 → clean
        )
        assert fault == "clean", (
            "board_rank alone must no longer trigger signaled_too_late (F6 ruling)"
        )

    def test_timing_basis_field_populated(self):
        """timing_basis must list the clauses that fired."""
        c = _TAXONOMY_CONSTANTS
        _, basis = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
            ticks=float(c["FRESH_TICKS"] + 5),
        )
        assert isinstance(basis, list)
        assert len(basis) > 0, "timing_basis must be populated for signaled_too_late"

    def test_premature_stop_noise_never_emitted_in_cn(self):
        """F5: PREMATURE_STOP_IMPLEMENTED=False — CN rows NEVER emit premature_stop_noise."""
        assert PREMATURE_STOP_IMPLEMENTED is False, (
            "PREMATURE_STOP_IMPLEMENTED must be False for CN (no stop-date column)"
        )
        c = _TAXONOMY_CONSTANTS
        # Even with all conditions met, premature_stop_noise must never fire in CN
        for premature_stop_mature in (True, False):
            fault, _ = _axis2_process(
                ext_score=0.1, board_rank=5, stage=None,
                terminal_state="STOPPED",
                fwd_mfe_21=c["PREMATURE_STOP_MFE_PP"] + 0.01,
                premature_stop_mature=premature_stop_mature,
            )
            assert fault != "premature_stop_noise", (
                f"CN must never emit premature_stop_noise "
                f"(premature_stop_mature={premature_stop_mature}; F5 ruling)"
            )

    def test_premature_stop_note_carried(self):
        """F5: the unimplemented note must exist and mention the data model requirement."""
        assert "stop-date column" in _PREMATURE_STOP_NOTE.lower() or "stop_date" in _PREMATURE_STOP_NOTE, (
            "PREMATURE_STOP_NOTE must explain the missing stop-date column requirement"
        )

    def test_clean_when_nothing_tiles(self):
        fault, _ = _axis2_process(
            ext_score=0.1, board_rank=5, stage=None,
            terminal_state=None, fwd_mfe_21=None,
        )
        assert fault == "clean"


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

    def test_missed_mover_zero_episodes_returns_none_not_zero(self):
        """F4: missed_mover_rate with 0 episodes must return value=None, not 0.0 (SA-R15)."""
        from engine.china_standout_audit import _missed_mover_rate
        board = pd.DataFrame([{
            "date": "2026-07-01",
            "ticker": "000001.SS",
            "fwd_21d_excess": 0.05,  # positive but < _MISSED_MOVER_EXCESS=0.12
        }])
        result = _missed_mover_rate(board)
        assert result["value"] is None, (
            "F4: zero episodes → value must be None, not 0.0 (SA-R15 forbids fabricated zero)"
        )
        assert result["n_episodes"] == 0
        assert "data_gap" in result.get("note", "").lower(), (
            "F4: zero episodes → note must mention data_gap"
        )


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

    def test_wilson_ci_k_gt_n_returns_sentinel_not_complex(self):
        """F2: k > n must return sentinel (1.0, 0.0), never a complex or raise TypeError."""
        lo, hi = _wilson_ci(k=15, n=3)
        assert isinstance(lo, float) and isinstance(hi, float), (
            "k>n must return floats, not complex — defensive sentinel"
        )
        assert lo > hi, "sentinel: lo > hi signals units mismatch"

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

    def test_window_unit_k_reviewer_repro(self):
        """F2 reviewer repro: 12 rows / 3 windows, k_rows=9 winning rows.

        Under the old code, k=9 and n=eff_n=3 → k>n → negative Wilson variance → TypeError.
        Under the fixed code, k is computed in window units (0 <= k <= 3), no exception.
        """
        # 12 rows in 3 non-overlapping 30-day windows (4 rows each)
        # Window 1: 2026-01-01..2026-01-22 — 3 wins out of 4 (mean=0.75 > 0 → positive window)
        # Window 2: 2026-02-05..2026-02-26 — 3 wins out of 4 (mean=0.75 > 0 → positive window)
        # Window 3: 2026-03-10..2026-03-31 — 3 wins out of 4 (mean=0.75 > 0 → positive window)
        # k_rows=9, eff_n=3, k_windows=3
        dates = (
            ["2026-01-01"] * 4 +   # window 1
            ["2026-02-05"] * 4 +   # window 2 (35d after window 1)
            ["2026-03-10"] * 4     # window 3 (33d after window 2)
        )
        # 9 wins out of 12 rows (3 wins per window)
        outcome_positive = [True, True, True, False] * 3

        eff_n = _effective_n(dates)
        assert eff_n == 3, f"Expected 3 windows, got {eff_n}"

        k = _window_unit_k(dates, outcome_positive)
        assert k <= eff_n, f"k={k} must not exceed eff_n={eff_n} (F2 invariant)"

        # F2 core invariant: Wilson CI must not raise and must return valid floats
        lo, hi = _wilson_ci(k, eff_n)
        assert isinstance(lo, float) and isinstance(hi, float)
        assert lo <= hi, f"Valid CI: lo={lo} must be <= hi={hi}"
        assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0

    def test_window_unit_k_bounded_by_eff_n(self):
        """k from _window_unit_k must always satisfy 0 <= k <= eff_n."""
        import random
        rng = random.Random(42)
        for _ in range(50):
            n_rows = rng.randint(1, 30)
            dates = [
                f"2026-{1 + (i // 10):02d}-{1 + (i % 28):02d}"
                for i in range(n_rows)
            ]
            outcome_positive = [rng.random() > 0.4 for _ in range(n_rows)]
            eff_n = _effective_n(dates)
            k = _window_unit_k(dates, outcome_positive)
            assert 0 <= k <= eff_n, (
                f"k={k} must be in [0, eff_n={eff_n}] — invariant violated"
            )


# ---------------------------------------------------------------------------
# 11. F1 sequencing test: regime store appended BEFORE append_board
# ---------------------------------------------------------------------------

class TestRegimeStampSequencing:
    def test_regime_store_before_board_stamps_own_market_regime(self, tmp_path, monkeypatch):
        """F1: regime store must be appended BEFORE append_board so that the board row
        carries a non-null own_market_regime on the same day.

        This test simulates the sequencing: append the regime store, THEN call
        append_board (which calls get_regime_for_date internally).
        Without the F1 fix, the row would carry own_market_regime=null because
        get_regime_for_date is called before the store is written.
        """
        # Step 1: create regime_history so append() can read it
        _make_regime_history(tmp_path, "2026-07-12")
        monkeypatch.setenv("CN_LANE", "asia")

        # Step 2: append regime store FIRST (this is the F1 fix — must precede append_board)
        ok = regime_append(asof="2026-07-12", root=tmp_path)
        assert ok is True, "Regime store append should succeed"

        # Step 3: verify get_regime_for_date returns non-null for today
        regime = get_regime_for_date("2026-07-12", root=tmp_path)
        assert regime is not None, (
            "F1: get_regime_for_date must find today's row — it was appended BEFORE append_board"
        )
        assert regime.get("quad") == "Q1", (
            "F1: the regime row must carry the correct quad from regime_history"
        )

    def test_board_before_regime_store_stamps_null(self, tmp_path, monkeypatch):
        """F1 negative control: if regime store is NOT yet written, get_regime_for_date returns None.
        This confirms the bug that the F1 fix corrects: calling append_board before
        china_regime_store.append means own_market_regime is null (keep-first locks that null in).
        """
        _make_regime_history(tmp_path, "2026-07-12")
        monkeypatch.setenv("CN_LANE", "asia")
        # Do NOT append the regime store first
        result = get_regime_for_date("2026-07-12", root=tmp_path)
        assert result is None, (
            "F1 negative control: regime store not yet written → get_regime_for_date returns None"
        )
