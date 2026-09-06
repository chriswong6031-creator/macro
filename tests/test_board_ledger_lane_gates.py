"""Tests for PR-R10 lane gates in engine/board_ledger.py.

Coverage:
  1. HK append_board is gated on CN_LANE=asia (asia_advance_enabled).
  2. CA append_board is gated on COLLECT_LANE=nightly (nightly_advance_enabled).
  3. Off-lane write returns 0 (refused).
  4. On-lane write succeeds (allowed).
  5. Read paths (grade, scorecard) are unaffected by lane gate.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


# ---------------------------------------------------------------------------
# 6. Canada builder health projection distinguishes an off-lane no-op
# ---------------------------------------------------------------------------
def _load_canada_board_ledger_caller():
    """Compile only the real caller function, avoiding unrelated render deps."""
    source_path = Path(__file__).resolve().parents[1] / "scripts" / "build_canada.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_canada_board_ledger"
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {
        "__builtins__": __builtins__,
        "__name__": "_canada_board_ledger_contract",
        "Path": Path,
    }
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["_canada_board_ledger"], namespace


def _canada_setups() -> dict:
    return {
        "buy": [
            {
                "ticker": "TEST.TO",
                "group": "setting_up",
                "alpha": 0.75,
                "price": 100.0,
                "signal": {},
                "conviction": {},
                "entry_signal": {},
            }
        ],
        "watch": [],
    }


def _run_canada_caller(
    monkeypatch,
    tmp_path: Path,
    *,
    advance_enabled: bool,
    append_result: int = 1,
    append_error: Exception | None = None,
):
    """Run the production caller against deterministic ledger/read projections."""
    import engine
    import engine.board_ledger as board_ledger

    seen = {"append": 0, "scorecard": 0, "grade": 0, "track": 0, "shadow": 0}

    def append_board(*_args, **_kwargs):
        seen["append"] += 1
        if append_error is not None:
            raise append_error
        return append_result

    def scorecard(_market: str) -> dict:
        seen["scorecard"] += 1
        return {"status": "accruing"}

    def grade(_market: str) -> dict:
        seen["grade"] += 1
        return {"available": False}

    track_ledger = ModuleType("engine.track_ledger")

    def track_document(*_args, **_kwargs) -> dict:
        seen["track"] += 1
        return {"meta": {"n_total": 0}, "rows": []}

    track_ledger.from_board_ledger_grade = track_document
    track_ledger.atomic_write = lambda *_args, **_kwargs: None

    board_shadow = ModuleType("engine.board_shadow")

    def write_shadow(*_args, **_kwargs) -> None:
        seen["shadow"] += 1

    board_shadow.write_shadow = write_shadow

    canada_library = ModuleType("scripts.build_canada_library")
    canada_library._ENTRY_STATE = {}
    canada_library.CA_BOARD_DEFINITION = "canada_branch_b_v1"

    monkeypatch.setattr(board_ledger, "append_board", append_board)
    monkeypatch.setattr(board_ledger, "scorecard", scorecard)
    monkeypatch.setattr(board_ledger, "grade", grade)
    monkeypatch.setitem(sys.modules, "engine.track_ledger", track_ledger)
    monkeypatch.setitem(sys.modules, "engine.board_shadow", board_shadow)
    monkeypatch.setitem(sys.modules, "scripts.build_canada_library", canada_library)
    monkeypatch.setattr(engine, "track_ledger", track_ledger, raising=False)
    monkeypatch.setattr(engine, "board_shadow", board_shadow, raising=False)

    caller, namespace = _load_canada_board_ledger_caller()
    namespace.update(
        {
            "_board_asof": lambda _latest: "2026-09-03",
            "_ledger_advance_enabled": lambda: advance_enabled,
            "config": SimpleNamespace(
                load=lambda: {"storage": {"site_dir": str(tmp_path)}}
            ),
            "log": SimpleNamespace(
                info=lambda *_args, **_kwargs: None,
                warning=lambda *_args, **_kwargs: None,
                error=lambda *_args, **_kwargs: None,
            ),
        }
    )
    setups = _canada_setups()
    health = caller(setups, {"date": "2026-09-03"})
    return health, setups, seen


def test_canada_off_nightly_caller_skips_append_without_false_error(
    monkeypatch, tmp_path
):
    """Expected write refusal is not a customer-visible ledger failure."""
    health, setups, seen = _run_canada_caller(
        monkeypatch,
        tmp_path,
        advance_enabled=False,
        append_result=0,
    )

    assert seen["append"] == 0, "off-nightly caller must not enter append_board"
    assert not [row for row in health if row.get("status") == "ERROR"], health
    assert setups["board_track"] == {"status": "accruing"}
    assert seen["scorecard"] == 1
    assert seen["grade"] == 1
    assert seen["track"] == 1
    assert seen["shadow"] == 1


def test_canada_armed_nightly_zero_append_remains_loud(monkeypatch, tmp_path):
    """A zero result after authorized admission is still a real failure."""
    health, _setups, seen = _run_canada_caller(
        monkeypatch,
        tmp_path,
        advance_enabled=True,
        append_result=0,
    )

    assert seen["append"] == 1
    errors = [row for row in health if row.get("status") == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["rows"] == 0
    assert "append wrote 0 rows" in errors[0]["en"]


def test_canada_armed_nightly_success_is_healthy(monkeypatch, tmp_path):
    """A successful authorized append produces no ledger health finding."""
    health, _setups, seen = _run_canada_caller(
        monkeypatch,
        tmp_path,
        advance_enabled=True,
        append_result=1,
    )

    assert seen["append"] == 1
    assert not [row for row in health if row.get("status") == "ERROR"], health


def test_canada_armed_nightly_exception_remains_loud(monkeypatch, tmp_path):
    """A real exception in the authorized append path remains visible."""
    health, _setups, seen = _run_canada_caller(
        monkeypatch,
        tmp_path,
        advance_enabled=True,
        append_error=RuntimeError("synthetic append failure"),
    )

    assert seen["append"] == 1
    errors = [row for row in health if row.get("status") == "ERROR"]
    assert len(errors) == 1
    assert "FAILED" in errors[0]["en"]
