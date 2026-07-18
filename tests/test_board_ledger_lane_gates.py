"""Tests for PR-R10 lane gates in engine/board_ledger.py.

Coverage:
  1. HK append_board is gated on CN_LANE=asia (asia_advance_enabled).
  2. CA append_board is gated on COLLECT_LANE=nightly (nightly_advance_enabled).
  3. Off-lane write returns 0 (refused).
  4. On-lane write succeeds (allowed).
  5. Read paths (grade, scorecard) are unaffected by lane gate.
"""
from __future__ import annotations

import os

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_calls(market: str = "HK") -> list[dict]:
    """Minimal board calls for append_board."""
    if market == "HK":
        return [{"ticker": "0700.HK", "group": "entry_open",
                 "edge_z": 1.5, "close_asof": 380.0}]
    return [{"ticker": "SHOP.TO", "group": "entry_open",
             "edge_z": 0.8, "close_asof": 90.0}]


# ---------------------------------------------------------------------------
# 1. HK gate: refused off-lane
# ---------------------------------------------------------------------------
class TestHKLaneGateRefused:
    def test_hk_off_lane_no_write(self, tmp_path, monkeypatch):
        """append_board(HK) must return 0 when CN_LANE != asia."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})

        # Ensure CN_LANE is NOT set to asia
        env = os.environ.copy()
        env.pop("CN_LANE", None)
        monkeypatch.setenv("CN_LANE", "render")

        n = bl.append_board(_minimal_calls("HK"), "HK", asof="2026-07-18")
        assert n == 0, "Expected 0 rows written when CN_LANE != asia"

        # Verify no parquet was written
        p = tmp_path / "hk_board.parquet"
        assert not p.exists(), "Parquet must not be created off-lane"

    def test_hk_lane_unset_no_write(self, tmp_path, monkeypatch):
        """append_board(HK) returns 0 when CN_LANE is unset."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.delenv("CN_LANE", raising=False)

        n = bl.append_board(_minimal_calls("HK"), "HK", asof="2026-07-18")
        assert n == 0, "Expected 0 rows when CN_LANE is unset"


# ---------------------------------------------------------------------------
# 2. HK gate: allowed on-lane
# ---------------------------------------------------------------------------
class TestHKLaneGateAllowed:
    def test_hk_on_lane_writes(self, tmp_path, monkeypatch):
        """append_board(HK) must write rows when CN_LANE=asia."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.setenv("CN_LANE", "asia")

        n = bl.append_board(_minimal_calls("HK"), "HK", asof="2026-07-18")
        assert n > 0, f"Expected rows written on CN_LANE=asia, got {n}"

        p = tmp_path / "hk_board.parquet"
        assert p.exists(), "Parquet must be created on-lane"


# ---------------------------------------------------------------------------
# 3. CA gate: refused off-lane
# ---------------------------------------------------------------------------
class TestCALaneGateRefused:
    def test_ca_off_lane_no_write(self, tmp_path, monkeypatch):
        """append_board(CA) returns 0 when COLLECT_LANE != nightly."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.setenv("COLLECT_LANE", "render")
        monkeypatch.delenv("US_LANE", raising=False)

        n = bl.append_board(_minimal_calls("CA"), "CA", asof="2026-07-18")
        assert n == 0, "Expected 0 rows written when COLLECT_LANE != nightly"

    def test_ca_lane_unset_no_write(self, tmp_path, monkeypatch):
        """append_board(CA) returns 0 when COLLECT_LANE is unset."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)

        n = bl.append_board(_minimal_calls("CA"), "CA", asof="2026-07-18")
        assert n == 0, "Expected 0 rows when COLLECT_LANE is unset"


# ---------------------------------------------------------------------------
# 4. CA gate: allowed on-lane
# ---------------------------------------------------------------------------
class TestCALaneGateAllowed:
    def test_ca_on_lane_writes(self, tmp_path, monkeypatch):
        """append_board(CA) must write rows when COLLECT_LANE=nightly."""
        import engine.board_ledger as bl

        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.delenv("CN_LANE", raising=False)  # CA gate uses COLLECT_LANE

        n = bl.append_board(_minimal_calls("CA"), "CA", asof="2026-07-18")
        assert n > 0, f"Expected rows written on COLLECT_LANE=nightly, got {n}"


# ---------------------------------------------------------------------------
# 5. Read paths are unaffected by lane gate (grade/scorecard still work)
# ---------------------------------------------------------------------------
class TestReadPathsUnaffected:
    def test_scorecard_works_off_lane(self, tmp_path, monkeypatch):
        """scorecard(HK) must not be blocked by CN_LANE env."""
        import engine.board_ledger as bl

        # Write a minimal parquet via on-lane (setup)
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        monkeypatch.setenv("CN_LANE", "asia")
        bl.append_board(_minimal_calls("HK"), "HK", asof="2026-07-01")

        # Now check scorecard works off-lane
        monkeypatch.setenv("CN_LANE", "render")
        # scorecard reads the parquet file (no lane check) — should not error
        try:
            sc = bl.scorecard("HK")
            assert isinstance(sc, dict), "scorecard must return dict"
        except Exception as exc:
            pytest.fail(f"scorecard raised off-lane: {exc}")


class TestGradeWriteBackLaneGate:
    """grade() computes in memory everywhere but persists stamps producer-lane-only.

    Regression: scorecard() -> grade() rewrote the committed CA store from the
    read-only prophet_governor (MM_DATA_GUARD catch on CI, 2026-07-18).
    """

    def _seed_store(self, bl, tmp_path, monkeypatch, market, lane_env):
        monkeypatch.setattr(
            bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet"
        )
        monkeypatch.setattr(bl, "_regime_stamp_for_date", lambda asof: {})
        for k, v in lane_env.items():
            monkeypatch.setenv(k, v)
        calls = [{"ticker": "0001.HK" if market == "HK" else "RY.TO",
                  "group": "entry_open", "board_pos": 1}]
        n = bl.append_board(calls, market, asof="2026-07-10")
        assert n == 1
        return tmp_path / f"{market.lower()}_board.parquet"

    def test_ca_off_lane_grade_does_not_rewrite_store(self, tmp_path, monkeypatch):
        import engine.board_ledger as bl

        p = self._seed_store(bl, tmp_path, monkeypatch,
                             "CA", {"COLLECT_LANE": "nightly"})
        before = p.read_bytes()
        monkeypatch.setenv("COLLECT_LANE", "render")
        bl.grade("CA")
        assert p.read_bytes() == before, (
            "off-lane grade() must not rewrite the CA store (PR-R10)"
        )

    def test_hk_on_lane_grade_may_rewrite_store(self, tmp_path, monkeypatch):
        import engine.board_ledger as bl

        p = self._seed_store(bl, tmp_path, monkeypatch,
                             "HK", {"CN_LANE": "asia"})
        # on-lane: write-back path is permitted (no assertion on content —
        # whether stamps change depends on fixture data; must not raise)
        out = bl.grade("HK")
        assert isinstance(out, dict)
        assert p.exists()
