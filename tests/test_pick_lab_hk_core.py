"""Tests for HK Pick Lab core: HK_PROFILE, registry_hk, and hk.py candidate books.

Covers per spec §3 and HKPL rules:
  - HK_PROFILE field values (HKPL-R3/R4/R6/R7)
  - registry_hk: 20 books, config_hash stability, uniqueness, kill_adjacency
  - run_book_hk: every book fires on positive synthetic HK snapshot
  - run_book_hk: negative cases (condition not met → no picks)
  - hklab_knife_avoid and hklab_chase_avoid: is_avoid=True (inverse books)
  - hklab_random_ctrl: determinism (same asof → same picks, different → different)
  - Suspension guard: last_print_sessions_ago > 2 excluded
  - Organ staleness: organ_fresh_* False → disabled_stale=True, zero picks (HKPL-R7)
  - Liquidity floor: adv63_hkd < HK$20M excluded
  - max_picks cap: no book returns more than 8 picks (HKPL-R6)
  - All US and CN tests still green (not re-run here but imports verified)

Run:
    python3 -m pytest tests/test_pick_lab_hk_core.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.profile import US_PROFILE, CN_PROFILE, HK_PROFILE, MarketProfile
from engine.pick_lab.registry_hk import (
    HK_REGISTRY,
    HK_BY_ID,
    HK_FLAGSHIP2_MIRROR_ID,
    _config_hash,
)
from engine.pick_lab.hk import run_book_hk, _apply_hk_universe, _organ_fresh


# ================================================================ helpers =====

def _make_asof() -> str:
    return "2024-07-09"


def _hk_base_snap(
    tickers=("H001", "H002", "H003", "H004", "H005",
             "H006", "H007", "H008", "H009", "H010",
             "H011", "H012", "H013", "H014", "H015"),
) -> pd.DataFrame:
    """Synthetic HK snapshot with all commonly used columns.

    All tickers pass the universe screens (last_print_sessions_ago ≤ 2,
    adv63_hkd ≥ HK$20M) and have sensible default values.
    Defaults do NOT trigger most book conditions — tests override relevant
    columns to create positive cases.
    """
    asof = _make_asof()
    num = len(tickers)
    rows = []
    for i, t in enumerate(tickers):
        rows.append({
            "ticker": t,
            "asof": asof,
            "name": f"Corp {t}",
            "name_zh": f"公司 {t}",
            "sector": "Financials",
            "close": 20.0 + i,
            "adv63_hkd": 50e6 + i * 1e6,        # above HK$20M floor
            "last_print_sessions_ago": 1,         # recently traded
            "off_high": -0.15 - i * 0.01,        # 15-16% below high
            "rsi14": 45.0,
            "dist_200dma": 0.02 + i * 0.005,     # slightly above 200dma
            "above_200": True,
            "washout_2w": False,
            "extended": False,
            "edge_z": 0.5 + i * 0.1,
            "beta": 0.9 + i * 0.05,
            "beta_role": "neutral",
            "label": "neutral",
            "tier": "T1",
            # 1D signals
            "d1_macd_xup_bars": None,             # not recently crossed
            "d1_stoch_xup_bars": None,
            "d1_from_os": False,
            "d3_macd_xup_bars": None,
            "sessions_since_23d_cross": None,
            "ret_since_23d_cross": None,
            # organ columns (null by default → most organ books disabled without fresh flag)
            "washout_state": None,
            "confluence_count": 0,
            "confluence_signals": None,
            "knife_risk": False,
            "adr_gap_pct": None,
            "cbbc_leverage_state": None,
            "buyback_flag": False,
            "dilution_flag": False,
            "catalyst_days_to": None,
            "attention_shock_z": None,
            "narrative_tone": None,
            "sfc_short_pressure_q": None,
            "sb_accum_z": None,
            "ah_discount_pctile": None,
            # organ freshness (default False → stale, organ books disabled)
            "organ_fresh_washout": False,
            "organ_fresh_adr": False,
            "organ_fresh_cbbc": False,
            "organ_fresh_narrative": False,
            "organ_fresh_catalyst": False,
            "organ_fresh_sb": False,
            # top-level scalars (repeated per row)
            "risk_state": "neutral",
            "peg_state": "normal",
            "liquidity_regime": "NEUTRAL",
            "vhsi_pctile": 0.5,
            "hsi_close": 19000.0,
        })
    df = pd.DataFrame(rows).set_index("ticker")
    df.attrs["asof"] = asof
    return df


def _hk_snap_with(overrides: dict[str, dict]) -> pd.DataFrame:
    """Base HK snap with per-ticker or per-column overrides.

    Use ticker='_ALL_' to set a column value on all rows.
    """
    df = _hk_base_snap()
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
    """Convenience: run_book_hk for a given engine_id."""
    book = HK_BY_ID[engine_id]
    return run_book_hk(book, snap)


def _snap_with_fresh_organs(organs: list[str]) -> pd.DataFrame:
    """Base snap with specified organ freshness columns set to True."""
    df = _hk_base_snap()
    for organ in organs:
        col = f"organ_fresh_{organ}"
        if col not in df.columns:
            df[col] = False
        df[col] = True
    return df


# ================================================================ profile =====

class TestHKProfile:
    """Tests for HK_PROFILE field correctness (HKPL-R3/R4/R6)."""

    def test_hk_profile_market_id(self):
        assert HK_PROFILE.market_id == "HK"

    def test_hk_profile_paths(self):
        assert HK_PROFILE.fires_path == Path("data/hk_pick_lab/fires.jsonl")
        assert HK_PROFILE.grades_path == Path("data/hk_pick_lab/grades.jsonl")
        assert HK_PROFILE.snapshot_dir == Path("data/hk_pick_lab/snapshots")

    def test_hk_profile_benchmark(self):
        assert HK_PROFILE.benchmark_ticker == "^HSI"
        assert callable(HK_PROFILE.benchmark_loader)

    def test_hk_profile_fill_basis_close(self):
        """HKPL-R4: exec = next HK session close (no price limits)."""
        assert HK_PROFILE.fill_basis == "close"

    def test_hk_profile_no_sealed_up(self):
        """No price limits in HK — no sealed_up concept."""
        assert HK_PROFILE.sealed_up_col is None

    def test_hk_profile_no_st_screen(self):
        """No ST concept in HK."""
        assert HK_PROFILE.st_exclude_col is None

    def test_hk_profile_primary_horizon_21(self):
        """HKPL-R3: primary ruler = 21-session HSI-excess."""
        assert HK_PROFILE.primary_horizon == 21

    def test_hk_profile_mfe_mae_25(self):
        """HKPL-R3: MFE/MAE descriptive window = 25 sessions."""
        assert HK_PROFILE.mfe_mae_sessions == 25

    def test_hk_profile_refire_lockout_21(self):
        """HKPL-R6: refire lockout 21 sessions."""
        assert HK_PROFILE.refire_lockout_sessions == 21

    def test_hk_profile_max_picks_8(self):
        """HKPL-R6: max 8 picks/day."""
        assert HK_PROFILE.max_picks_default == 8

    def test_hk_profile_liq_turnover_20m(self):
        """HKPL-R3 defaults: 63d ADV ≥ HK$20M."""
        assert HK_PROFILE.liq_turnover_min == 20e6

    def test_hk_profile_random_ctrl_id(self):
        assert HK_PROFILE.random_ctrl_id == "hklab_random_ctrl"

    def test_hk_profile_avoid_engine_id(self):
        assert HK_PROFILE.avoid_engine_id == "hklab_chase_avoid"

    def test_hk_profile_extra_fire_stamp_cols(self):
        """Extra stamps include HK-specific fire cols (spec §5)."""
        stamps = HK_PROFILE.extra_fire_stamp_cols
        assert "risk_state" in stamps
        assert "peg_state" in stamps
        assert "washout_state" in stamps
        assert "adr_gap_pct" in stamps
        assert "beta_role" in stamps
        assert "halted" in stamps
        assert "halt_voided" in stamps
        assert "vhsi_pctile" in stamps

    def test_hk_profile_data_gap_col(self):
        """HK uses data_gap_col for disabled_stale honesty."""
        assert HK_PROFILE.data_gap_col is True

    def test_hk_profile_default_ruler(self):
        assert HK_PROFILE.default_ruler == "21d_hsi_excess"

    def test_hk_profile_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            HK_PROFILE.market_id = "CHANGED"  # type: ignore[misc]

    def test_us_profile_unchanged(self):
        """HK_PROFILE addition must not alter US_PROFILE."""
        assert US_PROFILE.market_id == "US"
        assert US_PROFILE.max_picks_default == 12
        assert US_PROFILE.benchmark_ticker == "SPY"

    def test_cn_profile_unchanged(self):
        """HK_PROFILE addition must not alter CN_PROFILE."""
        assert CN_PROFILE.market_id == "CN"
        assert CN_PROFILE.fill_basis == "hl2_raw"
        assert CN_PROFILE.benchmark_ticker == "510300.SS"


# ================================================================ registry ====

class TestHKRegistry:
    """Tests for HK_REGISTRY integrity."""

    def test_count_20_books(self):
        assert len(HK_REGISTRY) == 20

    def test_all_engine_ids_unique(self):
        ids = [b["engine_id"] for b in HK_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_all_config_hashes_unique(self):
        hashes = [b["config_hash"] for b in HK_REGISTRY]
        assert len(hashes) == len(set(hashes))

    def test_config_hash_stable(self):
        """Config hashes must be stable across runs (HKPL-R2)."""
        for book in HK_REGISTRY:
            assert book["config_hash"] == _config_hash(book["config"])

    def test_flagship2_mirror_not_in_registry(self):
        """HK_FLAGSHIP2_MIRROR_ID is NOT counted in the 20 (spec §4)."""
        assert HK_FLAGSHIP2_MIRROR_ID not in HK_BY_ID
        assert HK_FLAGSHIP2_MIRROR_ID == "hklab_flagship2_mirror"

    def test_all_books_have_required_fields(self):
        required = {
            "engine_id", "name_en", "name_zh", "family", "ruler",
            "horizon_role", "max_picks", "refire_lockout_sessions",
            "config", "config_hash",
        }
        for book in HK_REGISTRY:
            missing = required - set(book)
            assert not missing, f"{book['engine_id']} missing: {missing}"

    def test_all_hk_engine_ids_prefixed(self):
        for book in HK_REGISTRY:
            assert book["engine_id"].startswith("hklab_"), (
                f"Expected hklab_ prefix: {book['engine_id']}"
            )

    def test_all_entry_books_horizon_role(self):
        """All HK books are entry books (HKPL-R9: no LH in v1)."""
        for book in HK_REGISTRY:
            assert book["horizon_role"] == "entry", (
                f"{book['engine_id']} horizon_role={book['horizon_role']}"
            )

    def test_by_id_dict_coverage(self):
        assert set(HK_BY_ID.keys()) == {b["engine_id"] for b in HK_REGISTRY}

    def test_max_picks_8(self):
        """HKPL-R6: max 8 picks/day."""
        for book in HK_REGISTRY:
            assert book["max_picks"] == 8, (
                f"{book['engine_id']} max_picks={book['max_picks']}, expected 8"
            )

    def test_refire_lockout_21(self):
        """HKPL-R6: refire lockout 21 sessions."""
        for book in HK_REGISTRY:
            assert book["refire_lockout_sessions"] == 21

    def test_kill_adjacency_on_required_books(self):
        """Spec §8 requires kill_adjacency on books 7, 15, 18 at minimum."""
        required = {
            "hklab_washout_sb",         # book 7 — southbound kill adjacency
            "hklab_beta_amplifier",     # book 15 — momentum kill adjacency
            "hklab_flagship_nogate",    # book 18 — momentum kill adjacency
        }
        for eid in required:
            book = HK_BY_ID[eid]
            assert book.get("kill_adjacency"), (
                f"{eid} should have kill_adjacency per spec §8"
            )

    def test_inverse_books_have_inverse_flag(self):
        """hklab_knife_avoid and hklab_chase_avoid must have inverse=True in config."""
        for eid in ("hklab_knife_avoid", "hklab_chase_avoid"):
            book = HK_BY_ID[eid]
            assert book["config"].get("inverse") is True, (
                f"{eid} should have config.inverse=True"
            )

    def test_no_coiled_book(self):
        """HKPL §8: NO COILED books for HK (do-not-port)."""
        for book in HK_REGISTRY:
            cfg = book["config"]
            for key in cfg:
                assert "coiled" not in key.lower(), (
                    f"{book['engine_id']} config key '{key}' references COILED (killed for HK)"
                )

    def test_no_connect_inclusion_book(self):
        """HKPL §8: NO Connect-inclusion event books."""
        for book in HK_REGISTRY:
            for key in book["config"]:
                assert "connect_incl" not in key.lower() and "h_incl" not in key.lower(), (
                    f"{book['engine_id']} references Connect-inclusion (NO-GO)"
                )

    def test_no_sb_delta_ranking(self):
        """HKPL §8: southbound Δ-ranking NO-GO (SB_ACCUM confluence signal is legal)."""
        for book in HK_REGISTRY:
            cfg = book["config"]
            for key in cfg:
                # sb delta rank keys are banned; confluence_signal_required=SB_ACCUM is legal
                assert key not in ("sb_delta_rank", "sb_delta_ranking", "southbound_rank"), (
                    f"{book['engine_id']} uses southbound delta ranking (NO-GO)"
                )

    def test_no_momentum_rank_in_configs(self):
        """HK KILL: no residual/selection momentum ranks."""
        momentum_keywords = ["momentum_rank", "mom_rank", "cross_section_mom", "selection_mom"]
        for book in HK_REGISTRY:
            for key in book["config"]:
                for kw in momentum_keywords:
                    assert kw not in key.lower(), (
                        f"{book['engine_id']} config key '{key}' looks like a momentum rank (HK KILL)"
                    )

    def test_hk_random_ctrl_in_registry(self):
        assert "hklab_random_ctrl" in HK_BY_ID


# ================================================================ universe ====

class TestHKUniverse:
    """Tests for _apply_hk_universe screener."""

    def test_suspended_name_excluded(self):
        """last_print_sessions_ago > 2 → excluded."""
        snap = _hk_base_snap()
        snap.at["H001", "last_print_sessions_ago"] = 3  # suspended
        df = _apply_hk_universe(snap)
        assert "H001" not in df.index

    def test_recently_traded_passes(self):
        """last_print_sessions_ago ≤ 2 → included."""
        snap = _hk_base_snap()
        snap.at["H001", "last_print_sessions_ago"] = 2
        df = _apply_hk_universe(snap)
        assert "H001" in df.index

    def test_null_last_print_passes_with_liq_unknown(self):
        """Null last_print_sessions_ago → passes (unknown session count)."""
        snap = _hk_base_snap()
        snap.at["H001", "last_print_sessions_ago"] = None
        df = _apply_hk_universe(snap)
        assert "H001" in df.index

    def test_low_adv_excluded(self):
        """adv63_hkd < HK$20M → excluded."""
        snap = _hk_base_snap()
        snap.at["H002", "adv63_hkd"] = 10e6  # below floor
        df = _apply_hk_universe(snap)
        assert "H002" not in df.index

    def test_null_adv_passes_with_liq_unknown(self):
        """Null adv63_hkd → passes with liq_unknown flag."""
        snap = _hk_base_snap()
        snap.at["H003", "adv63_hkd"] = np.nan
        df = _apply_hk_universe(snap)
        assert "H003" in df.index
        assert bool(df.at["H003", "liq_unknown"]) is True

    def test_all_pass_by_default(self):
        snap = _hk_base_snap()
        df = _apply_hk_universe(snap)
        assert len(df) == len(snap)


# ================================================================ organ fresh ==

class TestOrganFresh:
    """Tests for _organ_fresh staleness helper (HKPL-R7)."""

    def test_stale_when_column_missing(self):
        df = _hk_base_snap()
        # drop the column to simulate missing
        if "organ_fresh_washout" in df.columns:
            df = df.drop(columns=["organ_fresh_washout"])
        assert _organ_fresh(df, "washout") is False

    def test_stale_when_all_false(self):
        df = _hk_base_snap()
        df["organ_fresh_washout"] = False
        assert _organ_fresh(df, "washout") is False

    def test_fresh_when_any_true(self):
        df = _hk_base_snap()
        df["organ_fresh_washout"] = True
        assert _organ_fresh(df, "washout") is True

    def test_stale_when_all_null(self):
        df = _hk_base_snap()
        df["organ_fresh_washout"] = None
        assert _organ_fresh(df, "washout") is False


# ================================================================ Family A ====

class TestFamilyA:
    """Family A: 1D velocity books."""

    def _setup_1d_snap(self) -> pd.DataFrame:
        """Snap where H001 has all 1D velocity conditions met."""
        return _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi14": 45.0,
                "edge_z": 2.5,
            },
        })

    def test_1d_pure_fires_on_1d_cross(self):
        snap = self._setup_1d_snap()
        result = _run("hklab_1d_pure", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"

    def test_1d_pure_no_picks_without_from_os(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 5.0,
                "d1_from_os": False,   # fails
                "rsi14": 45.0,
            },
        })
        result = _run("hklab_1d_pure", snap)
        assert result["n_picks"] == 0

    def test_1d_pure_rsi14_cap(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 5.0,
                "d1_from_os": True,
                "rsi14": 75.0,  # above 70
            },
        })
        result = _run("hklab_1d_pure", snap)
        assert result["n_picks"] == 0

    def test_1d_pure_stoch_cap(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 10.0,   # above 8
                "d1_from_os": True,
                "rsi14": 45.0,
            },
        })
        result = _run("hklab_1d_pure", snap)
        assert result["n_picks"] == 0

    def test_1d_pure_authority_display_only(self):
        snap = self._setup_1d_snap()
        result = _run("hklab_1d_pure", snap)
        for p in result["picks"]:
            assert p["authority"] == "display_only"

    def test_1d_ignition_stale_organ_disabled(self):
        """Organ stale → disabled_stale=True, zero picks (HKPL-R7)."""
        snap = _hk_snap_with({
            "H001": {"d1_macd_xup_bars": 1.0, "washout_state": "ignition_watch"},
        })
        # organ_fresh_washout = False by default
        result = _run("hklab_1d_ignition", snap)
        assert result["disabled_stale"] is True
        assert result["n_picks"] == 0

    def test_1d_ignition_fires_when_organ_fresh(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "washout_state": "ignition_watch",
                "organ_fresh_washout": True,
                "confluence_count": 3,
            },
            "_ALL_": {"organ_fresh_washout": True},
        })
        result = _run("hklab_1d_ignition", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_1d_ignition_requires_1d_cross(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": None,  # no cross
                "washout_state": "ignition_watch",
                "organ_fresh_washout": True,
            },
            "_ALL_": {"organ_fresh_washout": True},
        })
        result = _run("hklab_1d_ignition", snap)
        assert result["n_picks"] == 0

    def test_1d_adr_stale_organ_disabled(self):
        snap = _hk_snap_with({
            "H001": {"d1_macd_xup_bars": 1.0, "adr_gap_pct": 1.5},
        })
        result = _run("hklab_1d_adr", snap)
        assert result["disabled_stale"] is True

    def test_1d_adr_fires_when_organ_fresh(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "adr_gap_pct": 1.5,
                "organ_fresh_adr": True,
            },
            "_ALL_": {"organ_fresh_adr": True},
        })
        result = _run("hklab_1d_adr", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_1d_adr_requires_gap_threshold(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "adr_gap_pct": 0.3,   # below 0.5 threshold
                "organ_fresh_adr": True,
            },
            "_ALL_": {"organ_fresh_adr": True},
        })
        result = _run("hklab_1d_adr", snap)
        assert result["n_picks"] == 0

    def test_1d_blastoff_requires_no_d3_cross(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": 1.0,   # already crossed → fails
                "above_200": True,
            },
        })
        result = _run("hklab_1d_blastoff", snap)
        assert result["n_picks"] == 0

    def test_1d_blastoff_fires_when_d3_null(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": None,  # not yet crossed
                "above_200": True,
            },
        })
        result = _run("hklab_1d_blastoff", snap)
        assert result["n_picks"] >= 1

    def test_1d_blastoff_requires_above_200(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "d3_macd_xup_bars": None,
                "above_200": False,   # below 200dma → fails
            },
        })
        result = _run("hklab_1d_blastoff", snap)
        assert result["n_picks"] == 0

    def test_1d_regime_requires_risk_on(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "risk_state": "neutral",   # not Risk-on
                "peg_state": "normal",
            },
        })
        result = _run("hklab_1d_regime", snap)
        assert result["n_picks"] == 0

    def test_1d_regime_fires_on_risk_on(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "risk_state": "Risk-on",
                "peg_state": "normal",
                "edge_z": 1.5,
            },
            "_ALL_": {"risk_state": "Risk-on"},
        })
        result = _run("hklab_1d_regime", snap)
        assert result["n_picks"] >= 1

    def test_1d_regime_excludes_peg_weak_side(self):
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 2.0,
                "risk_state": "Risk-on",
                "peg_state": "weak_side_pressure",   # excluded
            },
            "_ALL_": {"risk_state": "Risk-on", "peg_state": "weak_side_pressure"},
        })
        result = _run("hklab_1d_regime", snap)
        assert result["n_picks"] == 0


# ================================================================ Family B ====

class TestFamilyB:
    """Family B: washout/ignition organ-integrated books."""

    def _snap_with_washout_fresh(self, **extra) -> pd.DataFrame:
        """Base snap with organ_fresh_washout=True everywhere."""
        snap = _hk_snap_with({"_ALL_": {"organ_fresh_washout": True}})
        for k, v in extra.items():
            snap[k] = v
        return snap

    def test_washout_ignite_stale_organ_disabled(self):
        snap = _hk_snap_with({
            "H001": {"washout_state": "ignition_watch"},
        })
        result = _run("hklab_washout_ignite", snap)
        assert result["disabled_stale"] is True
        assert result["n_picks"] == 0

    def test_washout_ignite_fires_on_ignition_watch(self):
        snap = self._snap_with_washout_fresh()
        snap.at["H001", "washout_state"] = "ignition_watch"
        snap.at["H001", "confluence_count"] = 4
        result = _run("hklab_washout_ignite", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_washout_ignite_no_picks_on_chase_risk(self):
        """chase_risk state is not in the allowed list."""
        snap = self._snap_with_washout_fresh()
        snap["washout_state"] = "chase_risk"
        result = _run("hklab_washout_ignite", snap)
        assert result["n_picks"] == 0

    def test_washout_sb_requires_both_organs_fresh(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},  # sb stale
            "H001": {"washout_state": "ignition_watch", "sb_accum_z": 2.0,
                     "confluence_signals": '["SB_ACCUM"]'},
        })
        result = _run("hklab_washout_sb", snap)
        assert result["disabled_stale"] is True

    def test_washout_sb_fires_with_both_fresh_and_signal(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True, "organ_fresh_sb": True},
            "H001": {
                "washout_state": "ignition_watch",
                "sb_accum_z": 2.0,
                "confluence_signals": '["SB_ACCUM", "BUYBACK"]',
            },
        })
        result = _run("hklab_washout_sb", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"

    def test_washout_sb_no_picks_without_sb_signal(self):
        """washout state present but SB_ACCUM not in confluence_signals."""
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True, "organ_fresh_sb": True},
            "H001": {
                "washout_state": "ignition_watch",
                "confluence_signals": '["BUYBACK"]',  # no SB_ACCUM
            },
        })
        result = _run("hklab_washout_sb", snap)
        assert result["n_picks"] == 0

    def test_washout_buyback_fires_with_buyback_signal(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
            "H001": {
                "washout_state": "washout_watch",
                "confluence_signals": '["BUYBACK"]',
                "confluence_count": 2,
            },
        })
        result = _run("hklab_washout_buyback", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_pullback_entry_fires_on_pullback_state(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
            "H001": {"washout_state": "pullback_entry_watch", "rsi14": 35.0},
        })
        result = _run("hklab_pullback_entry", snap)
        assert result["n_picks"] >= 1

    def test_knife_avoid_is_avoid(self):
        snap = _hk_snap_with({
            "H001": {"knife_risk": True, "off_high": -0.35},
            "H002": {"knife_risk": True, "off_high": -0.25},
        })
        result = _run("hklab_knife_avoid", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["is_avoid"] is True
            assert "AVOID" in " ".join(p["why"]) or "avoid" in " ".join(p["why"]).lower()

    def test_knife_avoid_no_picks_when_no_knife(self):
        snap = _hk_base_snap()
        snap["knife_risk"] = False
        result = _run("hklab_knife_avoid", snap)
        assert result["n_picks"] == 0


# ================================================================ Family C ====

class TestFamilyC:
    """Family C: HK-unique structure books."""

    def test_cbbc_fuel_stale_organ_disabled(self):
        snap = _hk_snap_with({
            "H001": {"cbbc_leverage_state": "bear_skew"},
        })
        result = _run("hklab_cbbc_fuel", snap)
        assert result["disabled_stale"] is True

    def test_cbbc_fuel_fires_with_bear_skew(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_cbbc": True},
            "H001": {"cbbc_leverage_state": "bear_skew", "dist_200dma": 0.05},
            "H002": {"cbbc_leverage_state": "bear_skew_froth", "dist_200dma": 0.08},
        })
        result = _run("hklab_cbbc_fuel", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_cbbc_fuel_no_picks_without_bear_skew(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_cbbc": True},
            "H001": {"cbbc_leverage_state": "neutral"},
        })
        result = _run("hklab_cbbc_fuel", snap)
        assert result["n_picks"] == 0

    def test_ah_value_fires_on_discount_pctile(self):
        snap = _hk_snap_with({
            "H001": {"ah_discount_pctile": 90.0},
            "H002": {"ah_discount_pctile": 80.0},
            "H003": {"ah_discount_pctile": 70.0},
        })
        result = _run("hklab_ah_value", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"  # highest discount

    def test_ah_value_no_picks_when_all_null(self):
        snap = _hk_base_snap()
        snap["ah_discount_pctile"] = None
        result = _run("hklab_ah_value", snap)
        assert result["n_picks"] == 0

    def test_short_squeeze_stale_organ_disabled(self):
        snap = _hk_snap_with({
            "H001": {"sfc_short_pressure_q": 4, "rsi14": 40.0},
        })
        result = _run("hklab_short_squeeze", snap)
        assert result["disabled_stale"] is True

    def test_short_squeeze_fires_with_short_pressure_and_rsi_reclaim(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_sb": True},
            "H001": {"sfc_short_pressure_q": 4, "rsi14": 42.0},
        })
        result = _run("hklab_short_squeeze", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_short_squeeze_requires_rsi_in_band(self):
        """RSI below 30 or above 50 fails the reclaim condition."""
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_sb": True},
            "H001": {"sfc_short_pressure_q": 4, "rsi14": 60.0},  # above band
        })
        result = _run("hklab_short_squeeze", snap)
        assert result["n_picks"] == 0

    def test_catalyst_narrative_stale_organs_disabled(self):
        snap = _hk_snap_with({
            "H001": {
                "catalyst_days_to": 3,
                "attention_shock_z": 2.0,
                "narrative_tone": 60,
                "rsi14": 55.0,
                "organ_fresh_catalyst": True,  # only catalyst fresh, narrative stale
            },
        })
        result = _run("hklab_catalyst_narrative", snap)
        assert result["disabled_stale"] is True

    def test_catalyst_narrative_fires_when_both_organs_fresh(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_catalyst": True, "organ_fresh_narrative": True},
            "H001": {
                "catalyst_days_to": 3,
                "attention_shock_z": 2.0,
                "narrative_tone": 60,
                "rsi14": 55.0,
            },
        })
        result = _run("hklab_catalyst_narrative", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1

    def test_catalyst_narrative_requires_rsi_cap(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_catalyst": True, "organ_fresh_narrative": True},
            "H001": {
                "catalyst_days_to": 3,
                "attention_shock_z": 2.0,
                "narrative_tone": 60,
                "rsi14": 75.0,   # above 70 cap
            },
        })
        result = _run("hklab_catalyst_narrative", snap)
        assert result["n_picks"] == 0


# ================================================================ Family D ====

class TestFamilyD:
    """Family D: beta/regime books."""

    def test_beta_amplifier_requires_risk_on(self):
        snap = _hk_snap_with({
            "H001": {"risk_state": "neutral", "beta_role": "amplifier", "above_200": True},
        })
        result = _run("hklab_beta_amplifier", snap)
        assert result["n_picks"] == 0

    def test_beta_amplifier_fires_on_risk_on_amplifier(self):
        snap = _hk_snap_with({
            "_ALL_": {"risk_state": "Risk-on"},
            "H001": {"risk_state": "Risk-on", "beta_role": "amplifier", "above_200": True, "beta": 1.5},
            "H002": {"risk_state": "Risk-on", "beta_role": "amplifier", "above_200": True, "beta": 1.2},
        })
        result = _run("hklab_beta_amplifier", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"  # highest beta first

    def test_beta_amplifier_requires_above_200(self):
        snap = _hk_snap_with({
            "_ALL_": {"risk_state": "Risk-on"},
            "H001": {"risk_state": "Risk-on", "beta_role": "amplifier", "above_200": False},
        })
        result = _run("hklab_beta_amplifier", snap)
        assert result["n_picks"] == 0

    def test_beta_cushion_requires_risk_off(self):
        snap = _hk_snap_with({
            "_ALL_": {"risk_state": "neutral"},
            "H001": {"risk_state": "neutral", "beta_role": "cushion"},
        })
        result = _run("hklab_beta_cushion", snap)
        assert result["n_picks"] == 0

    def test_beta_cushion_fires_on_risk_off_cushion(self):
        snap = _hk_snap_with({
            "_ALL_": {"risk_state": "Risk-off"},
            "H001": {"risk_state": "Risk-off", "beta_role": "cushion", "beta": 0.3},
            "H002": {"risk_state": "Risk-off", "beta_role": "cushion", "beta": 0.5},
        })
        result = _run("hklab_beta_cushion", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"  # lowest beta first

    def test_hibor_easy_requires_easy_regime(self):
        snap = _hk_snap_with({
            "_ALL_": {"liquidity_regime": "NEUTRAL"},
            "H001": {"liquidity_regime": "NEUTRAL", "washout_2w": True},
        })
        result = _run("hklab_hibor_easy", snap)
        assert result["n_picks"] == 0

    def test_hibor_easy_fires_on_easy_and_washout(self):
        snap = _hk_snap_with({
            "_ALL_": {"liquidity_regime": "EASY"},
            "H001": {"liquidity_regime": "EASY", "washout_2w": True, "off_high": -0.25},
            "H002": {"liquidity_regime": "EASY", "washout_2w": True, "off_high": -0.15},
        })
        result = _run("hklab_hibor_easy", snap)
        assert result["n_picks"] >= 1
        assert result["picks"][0]["ticker"] == "H001"  # deeper washout first

    def test_hibor_easy_requires_washout_2w(self):
        snap = _hk_snap_with({
            "_ALL_": {"liquidity_regime": "EASY"},
            "H001": {"liquidity_regime": "EASY", "washout_2w": False},  # no washout
        })
        result = _run("hklab_hibor_easy", snap)
        assert result["n_picks"] == 0


# ================================================================ Family E ====

class TestFamilyE:
    """Family E: ablations + controls."""

    def test_flagship_nogate_returns_picks(self):
        snap = _hk_base_snap()
        result = _run("hklab_flagship_nogate", snap)
        assert result["n_picks"] > 0

    def test_flagship_nogate_max_8(self):
        snap = _hk_base_snap()
        result = _run("hklab_flagship_nogate", snap)
        assert result["n_picks"] <= 8

    def test_flagship_nogate_ranked_by_edge_z(self):
        snap = _hk_snap_with({
            "H001": {"edge_z": 5.0},
            "H002": {"edge_z": 3.0},
            "H003": {"edge_z": 1.0},
        })
        result = _run("hklab_flagship_nogate", snap)
        # H001 should be first
        assert result["picks"][0]["ticker"] == "H001"

    def test_chase_avoid_stale_organ_disabled(self):
        snap = _hk_snap_with({
            "H001": {"washout_state": "chase_risk"},
        })
        result = _run("hklab_chase_avoid", snap)
        assert result["disabled_stale"] is True

    def test_chase_avoid_fires_with_organ_fresh(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
            "H001": {"washout_state": "chase_risk", "rsi14": 75.0},
            "H002": {"washout_state": "chase_risk", "rsi14": 78.0},
        })
        result = _run("hklab_chase_avoid", snap)
        assert result["disabled_stale"] is False
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["is_avoid"] is True

    def test_chase_avoid_is_avoid(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
            "H001": {"washout_state": "chase_risk"},
        })
        result = _run("hklab_chase_avoid", snap)
        if result["n_picks"] > 0:
            for p in result["picks"]:
                assert p["is_avoid"] is True
                assert "AVOID" in " ".join(p["why"]) or "avoid" in " ".join(p["why"]).lower()

    def test_chase_avoid_no_picks_when_no_chase_state(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
        })
        # No tickers have chase_risk washout_state
        result = _run("hklab_chase_avoid", snap)
        assert result["n_picks"] == 0


# ================================================================ Random ctrl =

class TestRandomCtrl:
    """hklab_random_ctrl: determinism."""

    def test_same_asof_same_picks(self):
        snap = _hk_base_snap()
        book = HK_BY_ID["hklab_random_ctrl"]
        r1 = run_book_hk(book, snap)
        r2 = run_book_hk(book, snap)
        assert [p["ticker"] for p in r1["picks"]] == [p["ticker"] for p in r2["picks"]]

    def test_different_asof_different_picks(self):
        snap1 = _hk_base_snap()
        snap2 = _hk_base_snap()
        snap2.attrs["asof"] = "2024-08-01"
        book = HK_BY_ID["hklab_random_ctrl"]
        r1 = run_book_hk(book, snap1)
        r2 = run_book_hk(book, snap2)
        assert [p["ticker"] for p in r1["picks"]] != [p["ticker"] for p in r2["picks"]], (
            "Different asof dates should produce different random picks"
        )

    def test_random_ctrl_max_8(self):
        snap = _hk_base_snap()
        result = _run("hklab_random_ctrl", snap)
        assert result["n_picks"] <= 8

    def test_random_ctrl_no_disabled_stale(self):
        snap = _hk_base_snap()
        result = _run("hklab_random_ctrl", snap)
        assert result["disabled_stale"] is False


# ================================================================ Staleness ===

class TestOrganStalenessFailClosed:
    """HKPL-R7: organ stale → disabled_stale=True, zero picks for organ-dependent books."""

    # All organ books that require washout freshness
    WASHOUT_BOOKS = [
        "hklab_1d_ignition",
        "hklab_washout_ignite",
        "hklab_washout_sb",
        "hklab_washout_buyback",
        "hklab_pullback_entry",
        "hklab_chase_avoid",
    ]

    def _snap_with_conditions(self) -> pd.DataFrame:
        """Snap with data that would trigger all organ books IF organs were fresh."""
        snap = _hk_snap_with({
            "_ALL_": {
                "d1_macd_xup_bars": 1.0,
                "washout_state": "ignition_watch",
                "confluence_count": 5,
                "confluence_signals": '["SB_ACCUM", "BUYBACK"]',
                "adr_gap_pct": 1.5,
                "cbbc_leverage_state": "bear_skew",
                "sfc_short_pressure_q": 4,
                "rsi14": 42.0,
                "catalyst_days_to": 2,
                "attention_shock_z": 2.5,
                "narrative_tone": 65,
            },
        })
        return snap

    def test_washout_books_disabled_when_organ_stale(self):
        snap = self._snap_with_conditions()
        # All organ fresh cols default to False
        for eid in self.WASHOUT_BOOKS:
            result = _run(eid, snap)
            assert result["disabled_stale"] is True, (
                f"{eid} should be disabled_stale when washout organ is stale"
            )
            assert result["n_picks"] == 0

    def test_cbbc_book_disabled_when_organ_stale(self):
        snap = self._snap_with_conditions()
        result = _run("hklab_cbbc_fuel", snap)
        assert result["disabled_stale"] is True

    def test_short_squeeze_disabled_when_organ_stale(self):
        snap = self._snap_with_conditions()
        result = _run("hklab_short_squeeze", snap)
        assert result["disabled_stale"] is True

    def test_catalyst_narrative_disabled_when_organs_stale(self):
        snap = self._snap_with_conditions()
        result = _run("hklab_catalyst_narrative", snap)
        assert result["disabled_stale"] is True


# ================================================================ Suspension ==

class TestSuspensionGuard:
    """Spec §3: names with no print in last 2 sessions excluded."""

    def test_suspended_name_excluded_from_all_books(self):
        """A name halted >2 sessions must not appear in any book's picks."""
        snap = _hk_snap_with({
            # H001 is suspended; set all conditions to trigger every book
            "H001": {
                "last_print_sessions_ago": 5,   # >2 → suspended
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 3.0,
                "d1_from_os": True,
                "rsi14": 40.0,
                "edge_z": 10.0,
                "above_200": True,
                "knife_risk": True,
                "washout_state": "ignition_watch",
                "risk_state": "Risk-on",
                "beta_role": "amplifier",
                "beta": 2.0,
                "liquidity_regime": "EASY",
                "washout_2w": True,
                "ah_discount_pctile": 99.0,
                "organ_fresh_washout": True,
            },
        })
        # Ensure all organs fresh so books are not disabled
        for col in ["organ_fresh_washout", "organ_fresh_adr", "organ_fresh_cbbc",
                    "organ_fresh_narrative", "organ_fresh_catalyst", "organ_fresh_sb"]:
            snap[col] = True
        snap["risk_state"] = "Risk-on"
        snap["liquidity_regime"] = "EASY"

        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            tickers = {p["ticker"] for p in result["picks"]}
            assert "H001" not in tickers, (
                f"{book['engine_id']} should exclude suspended name H001"
            )


# ================================================================ Edge cases ==

class TestEdgeCases:
    """Edge cases: empty snapshot, all below ADV floor, etc."""

    def test_empty_snap_all_books_return_no_picks(self):
        snap = pd.DataFrame(columns=["close", "adv63_hkd"]).set_index(
            pd.Index([], name="ticker")
        )
        snap.attrs["asof"] = "2024-07-09"
        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            assert result["n_picks"] == 0
            assert result["engine_id"] == book["engine_id"]

    def test_all_below_adv_floor_no_picks(self):
        snap = _hk_base_snap()
        snap["adv63_hkd"] = 5e6   # below HK$20M
        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            assert result["n_picks"] == 0

    def test_all_books_return_required_keys(self):
        snap = _hk_base_snap()
        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            assert "engine_id" in result
            assert "picks" in result
            assert "disabled_stale" in result
            assert "n_picks" in result
            assert result["engine_id"] == book["engine_id"]
            assert isinstance(result["picks"], list)
            assert isinstance(result["disabled_stale"], bool)
            assert result["n_picks"] == len(result["picks"])

    def test_all_books_authority_display_only(self):
        """All pick rows must carry authority='display_only' (HKPL-R1)."""
        snap = _hk_snap_with({
            "_ALL_": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 3.0,
                "d1_from_os": True,
                "rsi14": 40.0,
                "washout_state": "ignition_watch",
                "knife_risk": True,
                "risk_state": "Risk-on",
                "beta_role": "amplifier",
                "above_200": True,
                "beta": 1.5,
                "liquidity_regime": "EASY",
                "washout_2w": True,
                "ah_discount_pctile": 90.0,
                "organ_fresh_washout": True,
                "organ_fresh_adr": True,
                "organ_fresh_cbbc": True,
                "organ_fresh_narrative": True,
                "organ_fresh_catalyst": True,
                "organ_fresh_sb": True,
                "cbbc_leverage_state": "bear_skew",
                "adr_gap_pct": 1.5,
                "sfc_short_pressure_q": 4,
                "catalyst_days_to": 2,
                "attention_shock_z": 2.5,
                "narrative_tone": 65,
                "confluence_signals": '["SB_ACCUM", "BUYBACK"]',
                "confluence_count": 5,
                "sb_accum_z": 2.0,
            },
        })

        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            for p in result["picks"]:
                assert p["authority"] == "display_only", (
                    f"{book['engine_id']}: pick missing authority='display_only'"
                )

    def test_max_picks_8_respected(self):
        """No book returns more than 8 picks (HKPL-R6)."""
        # Large universe (25 tickers)
        tickers = [f"Y{i:03d}" for i in range(25)]
        snap = _hk_base_snap(tickers=tickers)
        snap["d1_macd_xup_bars"] = 1.0
        snap["d1_stoch_xup_bars"] = 3.0
        snap["d1_from_os"] = True
        snap["rsi14"] = 40.0
        snap["above_200"] = True
        snap["washout_state"] = "ignition_watch"
        snap["knife_risk"] = True
        snap["risk_state"] = "Risk-on"
        snap["beta_role"] = "amplifier"
        snap["beta"] = 1.5
        snap["liquidity_regime"] = "EASY"
        snap["washout_2w"] = True
        snap["ah_discount_pctile"] = 90.0
        snap["organ_fresh_washout"] = True
        snap["organ_fresh_adr"] = True
        snap["organ_fresh_cbbc"] = True
        snap["organ_fresh_narrative"] = True
        snap["organ_fresh_catalyst"] = True
        snap["organ_fresh_sb"] = True
        snap["cbbc_leverage_state"] = "bear_skew"
        snap["adr_gap_pct"] = 1.5
        snap["sfc_short_pressure_q"] = 4
        snap["catalyst_days_to"] = 2
        snap["attention_shock_z"] = 2.5
        snap["narrative_tone"] = 65
        snap["confluence_signals"] = '["SB_ACCUM", "BUYBACK"]'
        snap["confluence_count"] = 5
        snap["sb_accum_z"] = 2.0

        for book in HK_REGISTRY:
            result = run_book_hk(book, snap)
            assert result["n_picks"] <= book["max_picks"], (
                f"{book['engine_id']} returned {result['n_picks']} > max {book['max_picks']}"
            )

    def test_disabled_stale_false_for_non_organ_books(self):
        """Non-organ books never return disabled_stale=True."""
        non_organ_books = {
            "hklab_1d_pure", "hklab_1d_blastoff", "hklab_1d_regime",
            "hklab_knife_avoid", "hklab_ah_value", "hklab_beta_amplifier",
            "hklab_beta_cushion", "hklab_hibor_easy", "hklab_flagship_nogate",
            "hklab_random_ctrl",
        }
        snap = _hk_base_snap()
        for book in HK_REGISTRY:
            if book["engine_id"] not in non_organ_books:
                continue
            result = run_book_hk(book, snap)
            assert result["disabled_stale"] is False, (
                f"{book['engine_id']} should not be disabled_stale (non-organ book)"
            )


# ================================================================ Inverse books =

class TestInverseBooks:
    """Spec §3: hklab_knife_avoid and hklab_chase_avoid are INVERSE (avoid) books."""

    def test_knife_avoid_config_inverse_flag(self):
        book = HK_BY_ID["hklab_knife_avoid"]
        assert book["config"].get("inverse") is True

    def test_chase_avoid_config_inverse_flag(self):
        book = HK_BY_ID["hklab_chase_avoid"]
        assert book["config"].get("inverse") is True

    def test_knife_avoid_picks_flagged_is_avoid(self):
        snap = _hk_snap_with({"H001": {"knife_risk": True}})
        result = _run("hklab_knife_avoid", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["is_avoid"] is True

    def test_chase_avoid_picks_flagged_is_avoid(self):
        snap = _hk_snap_with({
            "_ALL_": {"organ_fresh_washout": True},
            "H001": {"washout_state": "chase_risk", "rsi14": 78.0},
        })
        result = _run("hklab_chase_avoid", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["is_avoid"] is True

    def test_non_avoid_books_not_flagged(self):
        """Non-inverse books must not set is_avoid=True."""
        snap = _hk_snap_with({
            "H001": {
                "d1_macd_xup_bars": 1.0,
                "d1_stoch_xup_bars": 3.0,
                "d1_from_os": True,
                "rsi14": 40.0,
                "edge_z": 2.0,
            },
        })
        result = _run("hklab_1d_pure", snap)
        assert result["n_picks"] >= 1
        for p in result["picks"]:
            assert p["is_avoid"] is False
