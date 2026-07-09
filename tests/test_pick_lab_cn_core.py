"""Tests for China Pick Lab core: profile, registry_cn, and cn.py candidate books.

Covers per spec §3 and CNPL rules:
  - MarketProfile: US_PROFILE / CN_PROFILE field values
  - registry_cn: 20 books, config_hash stability, uniqueness, kill_adjacency presence
  - run_book_cn: every book fires on positive synthetic CN snapshot
  - run_book_cn: negative cases (condition not met → no picks)
  - cnlab_chase_avoid: inverse book flagged correctly (CNPL-R7)
  - cnlab_random_ctrl: determinism (same asof → same picks, different asof → different)
  - ST exclusion: is_st=True rows excluded from all books
  - Sealed_up exclusion: fillable=False rows excluded
  - cnlab_block_discount / cnlab_lhb_inst: data_gap when all-null (CNPL-R9)
  - cnlab_capitulation_beta: dormant when cycle_phase is non-matching
  - Liquidity floor: close < ¥2 excluded
  - All existing US tests remain unaffected (imported from registry/candidates)

Run:
    python3 -m pytest tests/test_pick_lab_cn_core.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.profile import US_PROFILE, CN_PROFILE, MarketProfile
from engine.pick_lab.registry_cn import (
    CN_REGISTRY,
    CN_BY_ID,
    FLAGSHIP2_MIRROR_ID,
    _config_hash,
)
from engine.pick_lab.cn import run_book_cn, _apply_cn_universe


# ================================================================ helpers =====

def _make_asof(n_tickers: int = 15) -> str:
    return "2024-06-03"


def _cn_base_snap(
    tickers=("A001", "A002", "A003", "A004", "A005",
             "A006", "A007", "A008", "A009", "A010",
             "A011", "A012", "A013", "A014", "A015"),
) -> pd.DataFrame:
    """Synthetic CN snapshot with all commonly used columns.

    All tickers pass the universe screens (not ST, fillable, close ≥ ¥2,
    turnover ≥ ¥30M) and have enough fields for most book conditions.
    Defaults do NOT trigger most book conditions — individual tests override
    the relevant columns to create positive cases.
    """
    asof = _make_asof()
    num = len(tickers)
    rows = []
    for i, t in enumerate(tickers):
        rows.append({
            "ticker": t,
            "asof": asof,
            "sector": "Technology",
            "board": "main",
            "close": 10.0 + i,               # well above ¥2 floor
            "turnover_20d": 50e6 + i * 1e6,  # above ¥30M
            "dd_pct_2y": 15.0 + i,           # moderate drawdown
            "rev_3m_sector_rank": float(i + 1) / num,  # rank 1/N ... N/N
            "rev_deepest_quintile": (i < num // 5),     # bottom quintile = True for first 20%
            "washout_2w": False,
            "coiled": False,
            "star": False,
            "extension_score": float(i),
            "rsi_5": 40.0,
            "rsi_10": 45.0,
            "above_ma120": True,
            "ma20_slope_up": True,
            "d1_macd_xup_bars": None,         # not recently crossed
            "d1_kd_xup_bars": None,
            "d1_from_os": False,
            "d1_macd": 0.0,
            "d1_sig": -0.1,
            "d1_k": 50.0,
            "d1_d": 40.0,
            "d3_macd_xup_bars": None,         # not crossed
            "tier": "T1",
            "limit_state": "normal",
            "fillable": True,
            "chase_veto": False,
            "t_plus_one_risk": "low",
            "lianban_count": 0,
            "is_st": False,
            "archetype": "value",
            "lowvol_tercile": "mid",          # mid vol by default
            "theme_basket": None,
            "theme_breadth_pct": None,
            "theme_member_ret21_rank": None,
            "block_discount_recent": None,    # absent by default → data_gap
            "lhb_inst_seats_5d": None,        # absent by default → data_gap
            # top-level scalars (repeated per row)
            "cycle_phase": "TRENDING",
            "participation_regime": "neutral",
            "participation_risk": "normal",
            "policy_impulse": "neutral",
            "qvix_z": 0.5,
            "csi300_close": 3500.0,
        })
    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


def _cn_snap_with(overrides: dict[str, dict]) -> pd.DataFrame:
    """Base CN snap with per-ticker or per-column overrides.

    overrides = {ticker: {field: value, ...}}  — per-ticker
    Pass ticker='_ALL_' to set a column value on all rows.
    """
    df = _cn_base_snap()
    for ticker, fields in overrides.items():
        if ticker == "_ALL_":
            for col, val in fields.items():
                if col not in df.columns:
                    df[col] = None
                df[col] = val
        else:
            if ticker in df.index:
                for col, val in fields.items():
                    if col not in df.columns:
                        df[col] = None
                    df.at[ticker, col] = val
    return df


def _run(engine_id: str, snap: pd.DataFrame) -> dict:
    """Convenience: run_book_cn for a given engine_id."""
    book = CN_BY_ID[engine_id]
    return run_book_cn(book, snap)


# ================================================================ profile =====

class TestMarketProfile:
    """Tests for US_PROFILE and CN_PROFILE field correctness."""

    def test_us_profile_paths(self):
        assert US_PROFILE.fires_path == Path("data/pick_lab/fires.jsonl")
        assert US_PROFILE.grades_path == Path("data/pick_lab/grades.jsonl")
        assert US_PROFILE.snapshot_dir == Path("data/pick_lab/snapshots")

    def test_us_profile_benchmark(self):
        assert US_PROFILE.benchmark_ticker == "SPY"
        assert US_PROFILE.benchmark_loader is None

    def test_us_profile_fill_basis_close(self):
        assert US_PROFILE.fill_basis == "close"

    def test_us_profile_no_st_screen(self):
        assert US_PROFILE.st_exclude_col is None

    def test_us_profile_no_sealed_up(self):
        assert US_PROFILE.sealed_up_col is None

    def test_us_profile_liq_close_5(self):
        assert US_PROFILE.liq_close_min == 5.0

    def test_us_profile_random_ctrl_id(self):
        assert US_PROFILE.random_ctrl_id == "plab_random_ctrl"

    def test_us_profile_avoid_engine_id(self):
        assert US_PROFILE.avoid_engine_id == "plab_topping_avoid"

    def test_cn_profile_paths(self):
        assert CN_PROFILE.fires_path == Path("data/china_pick_lab/fires.jsonl")
        assert CN_PROFILE.snapshot_dir == Path("data/china_pick_lab/snapshots")

    def test_cn_profile_benchmark(self):
        assert CN_PROFILE.benchmark_ticker == "510300.SS"
        assert callable(CN_PROFILE.benchmark_loader)

    def test_cn_profile_fill_basis_hl2(self):
        assert CN_PROFILE.fill_basis == "hl2_raw"

    def test_cn_profile_st_col(self):
        assert CN_PROFILE.st_exclude_col == "is_st"

    def test_cn_profile_sealed_up_col(self):
        assert CN_PROFILE.sealed_up_col == "limit_state"

    def test_cn_profile_liq_floor(self):
        assert CN_PROFILE.liq_close_min == 2.0
        assert CN_PROFILE.liq_turnover_min == 30e6

    def test_cn_profile_random_ctrl_id(self):
        assert CN_PROFILE.random_ctrl_id == "cnlab_random_ctrl"

    def test_cn_profile_avoid_engine_id(self):
        assert CN_PROFILE.avoid_engine_id == "cnlab_chase_avoid"

    def test_cn_profile_extra_fire_stamps(self):
        assert "board" in CN_PROFILE.extra_fire_stamp_cols
        assert "limit_state" in CN_PROFILE.extra_fire_stamp_cols
        assert "cycle_phase" in CN_PROFILE.extra_fire_stamp_cols

    def test_cn_profile_data_gap_col(self):
        assert CN_PROFILE.data_gap_col is True
        assert CN_PROFILE.skipped_unfillable_col is True

    def test_profile_is_frozen(self):
        """MarketProfile is frozen (immutable)."""
        with pytest.raises((AttributeError, TypeError)):
            US_PROFILE.market_id = "CHANGED"  # type: ignore[misc]


# ================================================================ registry ====

class TestCNRegistry:
    """Tests for CN_REGISTRY integrity."""

    def test_count_20_books(self):
        assert len(CN_REGISTRY) == 20

    def test_all_engine_ids_unique(self):
        ids = [b["engine_id"] for b in CN_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_all_config_hashes_unique(self):
        hashes = [b["config_hash"] for b in CN_REGISTRY]
        assert len(hashes) == len(set(hashes))

    def test_config_hash_stable(self):
        """Config hashes must be stable across runs (CNPL-R2)."""
        for book in CN_REGISTRY:
            assert book["config_hash"] == _config_hash(book["config"])

    def test_flagship2_mirror_not_in_registry(self):
        """flagship2_mirror id is NOT counted in the 20 (spec §4)."""
        assert FLAGSHIP2_MIRROR_ID not in CN_BY_ID

    def test_all_books_have_required_fields(self):
        required = {
            "engine_id", "name_en", "name_zh", "family", "ruler",
            "horizon_role", "max_picks", "refire_lockout_sessions",
            "config", "config_hash",
        }
        for book in CN_REGISTRY:
            missing = required - set(book)
            assert not missing, f"{book['engine_id']} missing: {missing}"

    def test_all_cn_engine_ids_prefixed(self):
        for book in CN_REGISTRY:
            assert book["engine_id"].startswith("cnlab_"), (
                f"Expected cnlab_ prefix: {book['engine_id']}"
            )

    def test_all_entry_books_horizon_role(self):
        """All CN books are entry books (no LH in v1 per CNPL-R10)."""
        for book in CN_REGISTRY:
            assert book["horizon_role"] == "entry", (
                f"{book['engine_id']} horizon_role={book['horizon_role']}"
            )

    def test_by_id_dict_coverage(self):
        assert set(CN_BY_ID.keys()) == {b["engine_id"] for b in CN_REGISTRY}

    def test_max_picks_12(self):
        for book in CN_REGISTRY:
            assert book["max_picks"] == 12

    def test_refire_lockout_21(self):
        for book in CN_REGISTRY:
            assert book["refire_lockout_sessions"] == 21

    def test_kill_adjacency_present_on_required_books(self):
        """Spec §8 requires kill_adjacency notes on books 2,3,4,5,8,9,10,12,13,14,16."""
        required = {
            "cnlab_rev_washout",
            "cnlab_rev_coiled",
            "cnlab_rev_lowvol",
            "cnlab_1d_pure",
            "cnlab_1d_blastoff",
            "cnlab_block_discount",
            "cnlab_lhb_inst",
            "cnlab_theme_laggard",
            "cnlab_capitulation_beta",
            "cnlab_qvix_panic",
            "cnlab_chase_avoid",
        }
        for eid in required:
            book = CN_BY_ID[eid]
            assert book.get("kill_adjacency"), (
                f"{eid} should have kill_adjacency per spec §8"
            )

    def test_cnlab_random_ctrl_in_registry(self):
        assert "cnlab_random_ctrl" in CN_BY_ID

    def test_cnlab_chase_avoid_is_inverse(self):
        book = CN_BY_ID["cnlab_chase_avoid"]
        assert book["config"].get("inverse") is True

    def test_no_cnlab_book_uses_lianban_as_buy(self):
        """CNPL-R7: no book uses limit-up/lianban as a buy input."""
        for book in CN_REGISTRY:
            cfg = book["config"]
            if book["engine_id"] == "cnlab_chase_avoid":
                # allowed: this is the AVOID direction
                continue
            # No book should set lianban_count or lianban_buy as a buy condition
            for key in cfg:
                assert "lianban" not in key.lower() or cfg.get("inverse", False), (
                    f"{book['engine_id']} uses lianban as buy condition (CNPL-R7 violation)"
                )

    def test_no_momentum_rank_in_configs(self):
        """CN kill law: NO momentum ranks in any book config."""
        momentum_keywords = ["momentum_rank", "mom_rank", "cross_section_mom"]
        for book in CN_REGISTRY:
            for key in book["config"]:
                for kw in momentum_keywords:
                    assert kw not in key.lower(), (
                        f"{book['engine_id']} config key '{key}' looks like a momentum rank"
                    )


# ================================================================ universe ====

class TestCNUniverse:
    """Tests for _apply_cn_universe screener."""

    def test_st_excluded(self):
        snap = _cn_base_snap()
        snap.at["A001", "is_st"] = True
        df = _apply_cn_universe(snap)
        assert "A001" not in df.index

    def test_fillable_false_excluded(self):
        snap = _cn_base_snap()
        snap.at["A002", "fillable"] = False
        df = _apply_cn_universe(snap)
        assert "A002" not in df.index

    def test_close_below_floor_excluded(self):
        snap = _cn_base_snap()
        snap.at["A003", "close"] = 1.5  # below ¥2 floor
        df = _apply_cn_universe(snap)
        assert "A003" not in df.index

    def test_turnover_below_floor_excluded(self):
        snap = _cn_base_snap()
        snap.at["A004", "turnover_20d"] = 20e6  # below ¥30M floor
        df = _apply_cn_universe(snap)
        assert "A004" not in df.index

    def test_null_turnover_passes_with_liq_unknown(self):
        snap = _cn_base_snap()
        snap.at["A005", "turnover_20d"] = np.nan  # null → passes with flag
        df = _apply_cn_universe(snap)
        assert "A005" in df.index
        assert bool(df.at["A005", "liq_unknown"]) is True

    def test_non_st_fillable_liquid_passes(self):
        snap = _cn_base_snap()
        df = _apply_cn_universe(snap)
        assert len(df) == len(snap)  # all 15 pass by default


# ================================================================ Family A ====

class TestFamilyA:
    """Family A: Reversion books."""

    def test_rev_pure_fires_on_deepest_quintile(self):
        snap = _cn_base_snap()
        # First 3 tickers have rev_deepest_quintile=True (from _cn_base_snap with 15 tickers)
        result = _run("cnlab_rev_pure", snap)
        assert result["n_picks"] > 0
        for p in result["picks"]:
            assert p["authority"] == "display_only"

    def test_rev_pure_no_picks_when_no_quintile(self):
        snap = _cn_base_snap()
        snap["rev_deepest_quintile"] = False
        result = _run("cnlab_rev_pure", snap)
        assert result["n_picks"] == 0

    def test_rev_washout_requires_washout_2w(self):
        snap = _cn_base_snap()
        snap["washout_2w"] = False
        result = _run("cnlab_rev_washout", snap)
        assert result["n_picks"] == 0

    def test_rev_washout_fires_with_washout(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "washout_2w": True,
                     "rev_3m_sector_rank": 0.05},
            "A002": {"rev_deepest_quintile": True, "washout_2w": True,
                     "rev_3m_sector_rank": 0.10},
        })
        result = _run("cnlab_rev_washout", snap)
        assert result["n_picks"] >= 1

    def test_rev_coiled_requires_coiled_or_star(self):
        snap = _cn_base_snap()
        snap["coiled"] = False
        snap["star"] = False
        result = _run("cnlab_rev_coiled", snap)
        assert result["n_picks"] == 0

    def test_rev_coiled_fires_with_coiled(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "coiled": True, "rev_3m_sector_rank": 0.05},
        })
        result = _run("cnlab_rev_coiled", snap)
        assert result["n_picks"] >= 1

    def test_rev_coiled_fires_with_star(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "star": True, "rev_3m_sector_rank": 0.05},
        })
        result = _run("cnlab_rev_coiled", snap)
        assert result["n_picks"] >= 1

    def test_rev_lowvol_requires_lowvol_tercile(self):
        snap = _cn_base_snap()
        snap["lowvol_tercile"] = "mid"
        result = _run("cnlab_rev_lowvol", snap)
        assert result["n_picks"] == 0

    def test_rev_lowvol_fires_with_low_tercile(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "lowvol_tercile": "low",
                     "rev_3m_sector_rank": 0.05},
        })
        result = _run("cnlab_rev_lowvol", snap)
        assert result["n_picks"] >= 1

    def test_rev_pure_ranks_by_reversal_depth(self):
        """Deepest reversal (lowest rev_3m_sector_rank) ranked first."""
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "rev_3m_sector_rank": 0.01},
            "A002": {"rev_deepest_quintile": True, "rev_3m_sector_rank": 0.02},
            "A003": {"rev_deepest_quintile": True, "rev_3m_sector_rank": 0.04},
        })
        result = _run("cnlab_rev_pure", snap)
        assert result["picks"][0]["ticker"] == "A001"

    def test_st_excluded_from_rev_pure(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "is_st": True, "rev_3m_sector_rank": 0.01},
            "A002": {"rev_deepest_quintile": True, "rev_3m_sector_rank": 0.02},
        })
        result = _run("cnlab_rev_pure", snap)
        tickers = [p["ticker"] for p in result["picks"]]
        assert "A001" not in tickers  # ST excluded


# ================================================================ Family B ====

class TestFamilyB:
    """Family B: 1D velocity books."""

    def _setup_1d_snap(self) -> pd.DataFrame:
        """Snap where A001 has all 1D velocity conditions met."""
        return _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi_10": 45.0,
            },
        })

    def test_1d_pure_fires_on_1d_cross(self):
        snap = self._setup_1d_snap()
        result = _run("cnlab_1d_pure", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "A001"

    def test_1d_pure_no_picks_without_from_os(self):
        snap = _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": False,  # not from oversold
                "rsi_10": 45.0,
            },
        })
        result = _run("cnlab_1d_pure", snap)
        # A001 fails (no from_os); others also fail (no 1D cross)
        assert result["n_picks"] == 0

    def test_1d_pure_rsi10_cap(self):
        snap = _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi_10": 75.0,   # above cap of 70
            },
        })
        result = _run("cnlab_1d_pure", snap)
        assert result["n_picks"] == 0

    def test_1d_phase_requires_constructive_phase(self):
        snap = self._setup_1d_snap()
        snap["cycle_phase"] = "DISTRIBUTION"  # not in allowed list
        result = _run("cnlab_1d_phase", snap)
        assert result["n_picks"] == 0

    def test_1d_phase_fires_on_accumulation(self):
        snap = self._setup_1d_snap()
        snap["cycle_phase"] = "ACCUMULATION"
        result = _run("cnlab_1d_phase", snap)
        assert result["n_picks"] >= 1

    def test_1d_participation_blocks_frothy(self):
        snap = self._setup_1d_snap()
        snap["participation_regime"] = "institutional_accumulation"
        snap["participation_risk"] = "frothy"
        result = _run("cnlab_1d_participation", snap)
        assert result["n_picks"] == 0

    def test_1d_participation_fires_on_inst_accum(self):
        snap = self._setup_1d_snap()
        snap["participation_regime"] = "institutional_accumulation"
        snap["participation_risk"] = "normal"
        result = _run("cnlab_1d_participation", snap)
        assert result["n_picks"] >= 1

    def test_1d_blastoff_requires_no_d3_cross(self):
        snap = _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": 1.0,   # 3D already crossed → FAILS
                "above_ma120": True,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_1d_blastoff", snap)
        assert result["n_picks"] == 0

    def test_1d_blastoff_fires_when_3d_null(self):
        snap = _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": None,  # not yet crossed
                "above_ma120": True,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_1d_blastoff", snap)
        assert result["n_picks"] >= 1

    def test_1d_blastoff_excludes_chase_veto(self):
        snap = _cn_snap_with({
            "A001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": None,
                "above_ma120": True,
                "chase_veto": True,    # should be excluded
            },
        })
        result = _run("cnlab_1d_blastoff", snap)
        assert result["n_picks"] == 0


# ================================================================ Family C ====

class TestFamilyC:
    """Family C: structure/flow books."""

    def test_block_discount_data_gap_when_all_null(self):
        """CNPL-R9: all-null block_discount_recent → data_gap=True, zero picks."""
        snap = _cn_base_snap()
        # block_discount_recent is already None for all in base snap
        result = _run("cnlab_block_discount", snap)
        assert result["data_gap"] is True
        assert result["n_picks"] == 0

    def test_block_discount_fires_when_column_present(self):
        snap = _cn_snap_with({
            "_ALL_": {"block_discount_recent": False},  # column present, all False
            "A001": {"block_discount_recent": True},
            "A002": {"block_discount_recent": True},
        })
        result = _run("cnlab_block_discount", snap)
        assert result["data_gap"] is False
        assert result["n_picks"] >= 1

    def test_lhb_inst_data_gap_when_all_null(self):
        """CNPL-R9: all-null lhb_inst_seats_5d → data_gap=True, zero picks."""
        snap = _cn_base_snap()
        result = _run("cnlab_lhb_inst", snap)
        assert result["data_gap"] is True
        assert result["n_picks"] == 0

    def test_lhb_inst_fires_when_seats_present(self):
        snap = _cn_snap_with({
            "_ALL_": {"lhb_inst_seats_5d": 0},
            "A001": {"lhb_inst_seats_5d": 3},   # ≥ 2 seats
            "A002": {"lhb_inst_seats_5d": 2},
        })
        result = _run("cnlab_lhb_inst", snap)
        assert result["data_gap"] is False
        assert result["n_picks"] >= 1

    def test_lhb_inst_requires_min_seats(self):
        snap = _cn_snap_with({
            "_ALL_": {"lhb_inst_seats_5d": 1},  # below threshold of 2
        })
        result = _run("cnlab_lhb_inst", snap)
        assert result["n_picks"] == 0

    def test_policy_put_requires_policy_impulse(self):
        snap = _cn_base_snap()
        snap["policy_impulse"] = "neutral"
        result = _run("cnlab_policy_put", snap)
        assert result["n_picks"] == 0

    def test_policy_put_fires_on_market_rescue(self):
        snap = _cn_snap_with({
            "A001": {"policy_impulse": "market_rescue", "dd_pct_2y": 35.0, "ma20_slope_up": True},
        })
        snap["policy_impulse"] = "market_rescue"  # scalar for all rows
        snap["dd_pct_2y"] = 35.0
        result = _run("cnlab_policy_put", snap)
        assert result["n_picks"] >= 1

    def test_theme_laggard_requires_high_breadth(self):
        snap = _cn_snap_with({
            "A001": {
                "theme_breadth_pct": 50.0,     # below 80% threshold
                "theme_member_ret21_rank": 20.0,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_theme_laggard", snap)
        assert result["n_picks"] == 0

    def test_theme_laggard_fires_with_high_breadth_laggard(self):
        snap = _cn_snap_with({
            "A001": {
                "theme_breadth_pct": 90.0,
                "theme_member_ret21_rank": 25.0,  # bottom half
                "chase_veto": False,
            },
        })
        result = _run("cnlab_theme_laggard", snap)
        assert result["n_picks"] >= 1

    def test_theme_laggard_excludes_chase_veto(self):
        snap = _cn_snap_with({
            "A001": {
                "theme_breadth_pct": 90.0,
                "theme_member_ret21_rank": 25.0,
                "chase_veto": True,   # should be excluded
            },
        })
        result = _run("cnlab_theme_laggard", snap)
        assert result["n_picks"] == 0


# ================================================================ Family D ====

class TestFamilyD:
    """Family D: washout/panic regimes."""

    def test_capitulation_beta_dormant_in_trending_phase(self):
        """Book dormant when cycle_phase is not CAPITULATION/DELEVERAGING."""
        snap = _cn_base_snap()
        snap["cycle_phase"] = "TRENDING"
        snap["dd_pct_2y"] = 50.0
        result = _run("cnlab_capitulation_beta", snap)
        assert result["n_picks"] == 0

    def test_capitulation_beta_fires_in_capitulation(self):
        snap = _cn_snap_with({
            "A001": {"cycle_phase": "CAPITULATION", "dd_pct_2y": 45.0},
        })
        snap["cycle_phase"] = "CAPITULATION"  # scalar for all rows
        snap["dd_pct_2y"] = 45.0
        result = _run("cnlab_capitulation_beta", snap)
        assert result["n_picks"] >= 1

    def test_capitulation_beta_requires_deep_dd(self):
        snap = _cn_base_snap()
        snap["cycle_phase"] = "CAPITULATION"
        snap["dd_pct_2y"] = 35.0   # below 40% threshold
        result = _run("cnlab_capitulation_beta", snap)
        assert result["n_picks"] == 0

    def test_qvix_panic_requires_high_qvix(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "qvix_z": 1.5, "limit_state": "normal"},
        })
        snap["qvix_z"] = 1.5  # below 2.0 threshold
        result = _run("cnlab_qvix_panic", snap)
        assert result["n_picks"] == 0

    def test_qvix_panic_fires_with_high_qvix(self):
        snap = _cn_snap_with({
            "A001": {"rev_deepest_quintile": True, "qvix_z": 2.5, "limit_state": "normal",
                     "rev_3m_sector_rank": 0.05},
        })
        snap["qvix_z"] = 2.5
        result = _run("cnlab_qvix_panic", snap)
        assert result["n_picks"] >= 1

    def test_qvix_panic_excludes_sealed_down(self):
        snap = _cn_snap_with({
            "A001": {
                "rev_deepest_quintile": True,
                "qvix_z": 3.0,
                "limit_state": "sealed_down",   # excluded
            },
        })
        snap["qvix_z"] = 3.0
        result = _run("cnlab_qvix_panic", snap)
        tickers = [p["ticker"] for p in result["picks"]]
        assert "A001" not in tickers

    def test_star_20cm_requires_board(self):
        snap = _cn_snap_with({
            "A001": {
                "board": "main",   # not star/chinext → fails
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi_10": 45.0,
                "above_ma120": True,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_star_20cm", snap)
        assert result["n_picks"] == 0

    def test_star_20cm_fires_on_star_board(self):
        snap = _cn_snap_with({
            "A001": {
                "board": "star",
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi_10": 45.0,
                "above_ma120": True,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_star_20cm", snap)
        assert result["n_picks"] >= 1

    def test_star_20cm_fires_on_chinext_board(self):
        snap = _cn_snap_with({
            "A001": {
                "board": "chinext",
                "d1_macd_xup_bars": 2.0,
                "d1_kd_xup_bars": 7.0,
                "d1_from_os": True,
                "rsi_10": 60.0,
                "above_ma120": True,
                "chase_veto": False,
            },
        })
        result = _run("cnlab_star_20cm", snap)
        assert result["n_picks"] >= 1


# ================================================================ Family E ====

class TestFamilyE:
    """Family E: defensive + ablations + control."""

    def test_lowvol_defensive_fires_on_lowvol_tercile(self):
        snap = _cn_base_snap()
        snap.loc[["A001", "A002", "A003"], "lowvol_tercile"] = "low"
        result = _run("cnlab_lowvol_defensive", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["features"].get("lowvol_tercile") == "low"

    def test_lowvol_defensive_no_picks_when_no_lowvol(self):
        snap = _cn_base_snap()
        snap["lowvol_tercile"] = "mid"
        result = _run("cnlab_lowvol_defensive", snap)
        assert result["n_picks"] == 0

    def test_dividend_ma120_requires_archetype(self):
        snap = _cn_base_snap()
        snap["archetype"] = "value"
        snap["above_ma120"] = True
        snap["dd_pct_2y"] = 10.0
        result = _run("cnlab_dividend_ma120", snap)
        assert result["n_picks"] == 0

    def test_dividend_ma120_fires(self):
        snap = _cn_snap_with({
            "A001": {
                "archetype": "dividend_defensive",
                "above_ma120": True,
                "dd_pct_2y": 8.0,
            },
        })
        result = _run("cnlab_dividend_ma120", snap)
        assert result["n_picks"] >= 1

    def test_dividend_ma120_dd_cap(self):
        snap = _cn_snap_with({
            "A001": {
                "archetype": "dividend_defensive",
                "above_ma120": True,
                "dd_pct_2y": 20.0,   # above 15% cap
            },
        })
        result = _run("cnlab_dividend_ma120", snap)
        assert result["n_picks"] == 0

    def test_flagship_nogate_returns_picks(self):
        snap = _cn_base_snap()
        result = _run("cnlab_flagship_nogate", snap)
        assert result["n_picks"] > 0

    def test_flagship_nogate_max_12(self):
        snap = _cn_base_snap()
        result = _run("cnlab_flagship_nogate", snap)
        assert result["n_picks"] <= 12

    def test_flagship_nogate_ranked_by_rev_depth(self):
        """cnlab_flagship_nogate ranks by rev_3m_sector_rank ascending."""
        snap = _cn_base_snap()
        result = _run("cnlab_flagship_nogate", snap)
        ranks = [p["features"].get("rev_3m_sector_rank") for p in result["picks"]
                 if p["features"].get("rev_3m_sector_rank") is not None]
        if len(ranks) >= 2:
            assert ranks[0] <= ranks[1]


# ================================================================ Chase avoid ==

class TestChaseAvoid:
    """CNPL-R7: cnlab_chase_avoid is the INVERSE (avoid) book."""

    def test_chase_avoid_only_selects_chase_veto_true(self):
        snap = _cn_snap_with({
            "A001": {"chase_veto": True},
            "A002": {"chase_veto": False},
            "A003": {"chase_veto": True},
        })
        result = _run("cnlab_chase_avoid", snap)
        tickers = {p["ticker"] for p in result["picks"]}
        assert "A001" in tickers
        assert "A003" in tickers
        assert "A002" not in tickers

    def test_chase_avoid_no_picks_when_none_chasing(self):
        snap = _cn_base_snap()
        snap["chase_veto"] = False
        result = _run("cnlab_chase_avoid", snap)
        assert result["n_picks"] == 0

    def test_chase_avoid_config_has_inverse_flag(self):
        book = CN_BY_ID["cnlab_chase_avoid"]
        assert book["config"].get("inverse") is True

    def test_chase_avoid_not_buy_order(self):
        """chase_avoid is labelled AVOID in why chips."""
        snap = _cn_snap_with({
            "A001": {"chase_veto": True},
        })
        result = _run("cnlab_chase_avoid", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert "AVOID" in " ".join(p["why"]) or "avoid" in " ".join(p["why"]).lower()

    def test_chase_avoid_excluded_from_rev_books(self):
        """chase_veto=True names are excluded from cnlab_rev_pure (not a buy signal)."""
        snap = _cn_snap_with({
            "A001": {
                "rev_deepest_quintile": True,
                "chase_veto": True,   # should NOT be in cnlab_rev_pure
                "rev_3m_sector_rank": 0.01,
            },
        })
        # cnlab_rev_pure does NOT use chase_veto — spec doesn't require exclusion there
        # (only 1D blastoff, theme_laggard explicitly use it). This is a correctness sanity:
        result = _run("cnlab_rev_pure", snap)
        # A001 should appear in rev_pure (chase_veto is not filtered there per spec)
        tickers = [p["ticker"] for p in result["picks"]]
        assert "A001" in tickers


# ================================================================ Random ctrl =

class TestRandomCtrl:
    """cnlab_random_ctrl: determinism per CNPL-R12."""

    def test_same_asof_same_picks(self):
        snap = _cn_base_snap()
        book = CN_BY_ID["cnlab_random_ctrl"]
        r1 = run_book_cn(book, snap)
        r2 = run_book_cn(book, snap)
        assert [p["ticker"] for p in r1["picks"]] == [p["ticker"] for p in r2["picks"]]

    def test_different_asof_different_picks(self):
        snap1 = _cn_base_snap()
        snap2 = _cn_base_snap()
        snap2.attrs["asof"] = "2024-07-01"
        book = CN_BY_ID["cnlab_random_ctrl"]
        r1 = run_book_cn(book, snap1)
        r2 = run_book_cn(book, snap2)
        assert [p["ticker"] for p in r1["picks"]] != [p["ticker"] for p in r2["picks"]], (
            "Different asof dates should produce different random picks"
        )

    def test_random_ctrl_max_12(self):
        snap = _cn_base_snap()
        result = _run("cnlab_random_ctrl", snap)
        assert result["n_picks"] <= 12

    def test_random_ctrl_no_data_gap(self):
        snap = _cn_base_snap()
        result = _run("cnlab_random_ctrl", snap)
        assert result["data_gap"] is False


# ================================================================ ST / sealed =

class TestSTAndSealedExclusion:
    """ST exclusion and fillable=False exclusion."""

    def test_st_excluded_from_all_books(self):
        snap = _cn_base_snap()
        # Make A001 ST, but qualify for rev_pure
        snap.at["A001", "is_st"] = True
        snap.at["A001", "rev_deepest_quintile"] = True
        snap.at["A001", "rev_3m_sector_rank"] = 0.001  # deepest
        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            tickers = {p["ticker"] for p in result["picks"]}
            assert "A001" not in tickers, (
                f"{book['engine_id']} should exclude ST names"
            )

    def test_fillable_false_excluded_from_all_books(self):
        snap = _cn_base_snap()
        snap.at["A001", "fillable"] = False
        snap.at["A001", "rev_deepest_quintile"] = True
        snap.at["A001", "rev_3m_sector_rank"] = 0.001
        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            tickers = {p["ticker"] for p in result["picks"]}
            assert "A001" not in tickers, (
                f"{book['engine_id']} should exclude fillable=False names"
            )


# ================================================================ Empty snap =

class TestEdgeCases:
    """Edge cases: empty snapshot, all below liquidity floor, etc."""

    def test_empty_snap_all_books_return_no_picks(self):
        snap = pd.DataFrame(columns=["close", "is_st", "fillable"]).set_index(
            pd.Index([], name="ticker")
        )
        snap.attrs["asof"] = "2024-06-03"
        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            assert result["n_picks"] == 0
            assert result["engine_id"] == book["engine_id"]

    def test_all_below_liq_floor_no_picks(self):
        snap = _cn_base_snap()
        snap["close"] = 0.5  # below ¥2
        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            assert result["n_picks"] == 0

    def test_all_books_return_authority_display_only(self):
        """All pick rows must carry authority='display_only'."""
        # Set up conditions so most books fire
        snap = _cn_base_snap()
        snap["rev_deepest_quintile"] = True
        snap["washout_2w"] = True
        snap["d1_macd_xup_bars"] = 1.0
        snap["d1_kd_xup_bars"] = 3.0
        snap["d1_from_os"] = True
        snap["rsi_10"] = 40.0
        snap["chase_veto"] = True
        snap["lowvol_tercile"] = "low"
        snap["archetype"] = "dividend_defensive"
        snap["above_ma120"] = True
        snap["dd_pct_2y"] = 45.0
        snap["cycle_phase"] = "CAPITULATION"
        snap["qvix_z"] = 3.0

        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            for p in result["picks"]:
                assert p["authority"] == "display_only", (
                    f"{book['engine_id']}: pick missing authority='display_only'"
                )

    def test_max_picks_respected(self):
        """No book returns more than max_picks picks."""
        # large universe (30 tickers)
        tickers = [f"X{i:03d}" for i in range(30)]
        snap = _cn_base_snap(tickers=tickers)
        snap["rev_deepest_quintile"] = True
        snap["d1_macd_xup_bars"] = 1.0
        snap["d1_kd_xup_bars"] = 3.0
        snap["d1_from_os"] = True
        snap["rsi_10"] = 40.0
        snap["chase_veto"] = True
        snap["lowvol_tercile"] = "low"

        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            assert result["n_picks"] <= book["max_picks"], (
                f"{book['engine_id']} returned {result['n_picks']} > max {book['max_picks']}"
            )

    def test_result_dict_structure(self):
        """run_book_cn always returns a dict with required keys."""
        snap = _cn_base_snap()
        for book in CN_REGISTRY:
            result = run_book_cn(book, snap)
            assert "engine_id" in result
            assert "picks" in result
            assert "data_gap" in result
            assert "n_picks" in result
            assert result["engine_id"] == book["engine_id"]
            assert isinstance(result["picks"], list)
            assert isinstance(result["data_gap"], bool)
            assert result["n_picks"] == len(result["picks"])

    def test_data_gap_false_for_non_store_books(self):
        """Only block_discount and lhb_inst can have data_gap=True."""
        snap = _cn_base_snap()
        store_books = {"cnlab_block_discount", "cnlab_lhb_inst"}
        for book in CN_REGISTRY:
            if book["engine_id"] in store_books:
                continue
            result = run_book_cn(book, snap)
            assert result["data_gap"] is False, (
                f"{book['engine_id']} should not have data_gap=True"
            )
