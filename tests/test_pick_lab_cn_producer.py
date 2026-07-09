"""Tests for China Pick Lab CN snapshot producer + Reversion Desk (spec §4/§5).

Covers:
  - cn_snapshot.build_cn_core_rows: null-honest assembly, all columns present,
    low-vol tercile cross-sectional assignment, reversing/no-data cases
  - cn_snapshot.CN_SNAPSHOT_COLUMNS: completeness (all listed columns present)
  - reversion_desk.compute_reversion_desk: rank order, bonus arithmetic, screens
  - reversion_desk.build_reversion_desk_artifact: schema/as_of/rows output
  - Executability screens: fillable==False excluded, is_st==True excluded
  - Spec §4 bonus arithmetic: washout_2w +0.5, coiled +0.25, star +0.15, ext -0.5x

Does NOT import build_china_library (heavy pipeline dependency).
Does NOT hit disk (temp dirs only for write_snapshot round-trip test).

Run:
    python3 -m pytest tests/test_pick_lab_cn_producer.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.cn_snapshot import CN_SNAPSHOT_COLUMNS, build_cn_core_rows
from engine.pick_lab.reversion_desk import (
    _compute_score,
    build_reversion_desk_artifact,
    compute_reversion_desk,
)


# ============================================================ helpers ========

TICKERS = ["A001", "A002", "A003", "A004", "A005",
           "A006", "A007", "A008", "A009", "A010"]
ASOF = "2024-06-03"


def _base_kwargs(tickers=TICKERS) -> dict:
    """Minimal build_cn_core_rows kwargs — all required arguments, null-honest defaults."""
    n = len(tickers)
    return dict(
        tickers=list(tickers),
        asof=ASOF,
        close_by={t: float(i + 10) for i, t in enumerate(tickers)},
        turnover_by={t: 50e6 for t in tickers},
        sector_by={t: ("Tech" if i % 2 == 0 else "Energy") for i, t in enumerate(tickers)},
        name_by={t: f"Name {t}" for t in tickers},
        name_zh_by={t: f"名字 {t}" for t in tickers},
        board_by={t: "main" for t in tickers},
        is_st_by={t: False for t in tickers},
    )


def _make_snap(
    n: int = 10,
    rev_deepest: list[bool] | None = None,
    washout_2w: list[bool] | None = None,
    coiled: list[bool] | None = None,
    star: list[bool] | None = None,
    ext_score: list[float] | None = None,
    is_st: list[bool] | None = None,
    fillable: list[bool | None] | None = None,
    rev_rank: list[int | None] | None = None,
    sector_n: list[int | None] | None = None,
) -> pd.DataFrame:
    """Build a synthetic CN snapshot DataFrame for reversion_desk tests."""
    tickers = [f"T{i:03d}" for i in range(n)]
    data: dict = {
        "rev_deepest_quintile": rev_deepest if rev_deepest is not None else [True] * n,
        "rev_3m_sector_rank": rev_rank if rev_rank is not None else list(range(1, n + 1)),
        "rev_sector_n": sector_n if sector_n is not None else [n] * n,
        "rev_z": [float(n - i) / n for i in range(n)],
        "rev_3m": [-float(i + 1) for i in range(n)],
        "washout_2w": washout_2w if washout_2w is not None else [False] * n,
        "coiled": coiled if coiled is not None else [False] * n,
        "star": star if star is not None else [False] * n,
        "extension_score": ext_score if ext_score is not None else [0.0] * n,
        "is_st": is_st if is_st is not None else [False] * n,
        "fillable": fillable if fillable is not None else [True] * n,
        "close": [float(10 + i) for i in range(n)],
        "sector": [("Tech" if i % 2 == 0 else "Energy") for i in range(n)],
        "name": [f"Name {i}" for i in range(n)],
        "name_zh": [f"名字 {i}" for i in range(n)],
        # Chip fields (for _chips() coverage)
        "d1_macd_xup_bars": [None] * n,
        "d1_from_os": [None] * n,
        "d2_macd_xup_bars": [None] * n,
        "cycle_phase": ["RECOVERY"] * n,
        "participation_regime": ["institutional_accumulation"] * n,
        "chase_veto": [False] * n,
        "t_plus_one_risk": [False] * n,
        "extension_extended": [False] * n,
    }
    df = pd.DataFrame(data, index=pd.Index(tickers, name="ticker"))
    df.attrs["asof"] = ASOF
    return df


# ============================================================ cn_snapshot =====

class TestCNSnapshotColumns:
    """CN_SNAPSHOT_COLUMNS completeness checks."""

    def test_all_listed_columns_non_empty(self):
        """CN_SNAPSHOT_COLUMNS must be a non-empty list of strings."""
        assert isinstance(CN_SNAPSHOT_COLUMNS, list)
        assert len(CN_SNAPSHOT_COLUMNS) > 0
        assert all(isinstance(c, str) for c in CN_SNAPSHOT_COLUMNS)

    def test_key_columns_present(self):
        """Key CN columns must be in CN_SNAPSHOT_COLUMNS."""
        required = [
            "ticker", "asof", "sector", "close",
            "rev_z", "rev_3m_sector_rank", "rev_deepest_quintile",
            "washout_2w", "coiled", "star",
            "d1_macd_xup_bars", "d1_from_os",
            "is_st", "fillable", "limit_state",
            "cycle_phase", "participation_regime",
        ]
        for col in required:
            assert col in CN_SNAPSHOT_COLUMNS, f"Missing key column: {col}"

    def test_no_duplicates(self):
        """No duplicate column names."""
        assert len(CN_SNAPSHOT_COLUMNS) == len(set(CN_SNAPSHOT_COLUMNS))


class TestBuildCNcoreRows:
    """Unit tests for build_cn_core_rows pure assembler."""

    def test_empty_tickers_returns_empty(self):
        kw = _base_kwargs([])
        rows = build_cn_core_rows(**kw)
        assert rows == []

    def test_all_cn_snapshot_columns_present(self):
        """Every row must carry all CN_SNAPSHOT_COLUMNS keys."""
        rows = build_cn_core_rows(**_base_kwargs())
        assert len(rows) == len(TICKERS)
        for row in rows:
            for col in CN_SNAPSHOT_COLUMNS:
                assert col in row, f"Missing column {col!r} in row for {row.get('ticker')}"

    def test_asof_stamped(self):
        rows = build_cn_core_rows(**_base_kwargs())
        for row in rows:
            assert row["asof"] == ASOF

    def test_ticker_identity(self):
        rows = build_cn_core_rows(**_base_kwargs())
        result_tickers = [r["ticker"] for r in rows]
        assert result_tickers == list(TICKERS)

    def test_null_close_is_none_not_nan(self):
        """Null values must be Python None, not NaN, in the output."""
        kw = _base_kwargs()
        kw["close_by"]["A001"] = None
        rows = build_cn_core_rows(**kw)
        row0 = next(r for r in rows if r["ticker"] == "A001")
        assert row0["close"] is None

    def test_reversal_columns_propagated(self):
        kw = _base_kwargs()
        kw["rev_z_by"] = {"A001": -2.5, "A002": 1.0}
        kw["rev_deepest_quintile_by"] = {"A001": True}
        kw["rev_sector_rank_by"] = {"A001": 3}
        rows = build_cn_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "A001")
        assert r1["rev_z"] == -2.5
        assert r1["rev_deepest_quintile"] is True
        assert r1["rev_3m_sector_rank"] == 3
        r2 = next(r for r in rows if r["ticker"] == "A002")
        assert r2["rev_z"] == 1.0
        assert r2["rev_deepest_quintile"] is None  # not provided

    def test_washout_coiled_propagated(self):
        kw = _base_kwargs()
        kw["washout_2w_by"] = {"A003": True}
        kw["coiled_by"] = {
            "A004": {"coiled": True, "star": False, "bonus": 0.25},
            "A005": {"coiled": False, "star": True, "bonus": 0.15},
        }
        rows = build_cn_core_rows(**kw)
        r3 = next(r for r in rows if r["ticker"] == "A003")
        assert r3["washout_2w"] is True
        r4 = next(r for r in rows if r["ticker"] == "A004")
        assert r4["coiled"] is True
        assert r4["star"] is False
        r5 = next(r for r in rows if r["ticker"] == "A005")
        assert r5["coiled"] is False
        assert r5["star"] is True

    def test_regime_scalars_broadcast(self):
        """Regime scalars (cycle_phase etc) are the same on every row."""
        kw = _base_kwargs()
        kw["cycle_phase"] = "RECOVERY"
        kw["participation_regime"] = "institutional_accumulation"
        kw["qvix_z"] = 1.5
        rows = build_cn_core_rows(**kw)
        for row in rows:
            assert row["cycle_phase"] == "RECOVERY"
            assert row["participation_regime"] == "institutional_accumulation"
            assert row["qvix_z"] == 1.5

    def test_is_st_propagated(self):
        kw = _base_kwargs()
        kw["is_st_by"] = {"A001": True, "A002": False}
        rows = build_cn_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "A001")
        r2 = next(r for r in rows if r["ticker"] == "A002")
        assert r1["is_st"] is True
        assert r2["is_st"] is False

    def test_lowvol_tercile_assignment(self):
        """Low-vol tercile is assigned cross-sectionally: roughly 1/3 each."""
        tickers = [f"T{i}" for i in range(9)]
        kw = _base_kwargs(tickers)
        # give each ticker a different vol so we can predict terciles
        vols = {f"T{i}": float(i + 1) * 0.1 for i in range(9)}
        kw["vol_by"] = vols
        rows = build_cn_core_rows(**kw)
        labels = [r["lowvol_tercile"] for r in rows]
        # T0..T2 → low (lowest vol); T3..T5 → mid; T6..T8 → high
        assert labels[0] == "low"
        assert labels[4] == "mid"
        assert labels[8] == "high"

    def test_extension_score_propagated(self):
        kw = _base_kwargs()
        kw["extension_by"] = {
            "A001": {"score": 0.7, "extended": True, "reason": "stretched"},
        }
        rows = build_cn_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "A001")
        assert r1["extension_score"] == pytest.approx(0.7)
        assert r1["extension_extended"] is True

    def test_osc_d1_propagated(self):
        kw = _base_kwargs()
        kw["osc_d12_by"] = {
            "A001": {
                "d1_macd": 0.3, "d1_sig": 0.1,
                "d1_macd_xup_bars": 2.0,
                "d1_k": 35.0, "d1_d": 28.0,
                "d1_kd_xup_bars": 3.0,
                "d1_from_os": True, "d1_ob": False,
                "d2_macd": None, "d2_sig": None,
                "d2_macd_xup_bars": None, "d2_k": None, "d2_d": None,
                "d2_kd_xup_bars": None, "d2_from_os": None, "d2_ob": None,
            }
        }
        rows = build_cn_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "A001")
        assert r1["d1_macd_xup_bars"] == pytest.approx(2.0)
        assert r1["d1_from_os"] is True
        assert r1["d1_ob"] is False

    def test_null_honest_missing_cols(self):
        """Fields not provided → None (never fabricated or NaN)."""
        kw = _base_kwargs(["X001"])
        rows = build_cn_core_rows(**kw)
        row = rows[0]
        # These are not provided in base kwargs — should be None
        assert row["rev_z"] is None
        assert row["cycle_phase"] is None
        assert row["washout_2w"] is None
        assert row["coiled"] is None
        assert row["d1_macd_xup_bars"] is None

    def test_extension_missing_gives_none(self):
        """When extension_by is not provided, extension_score/extended are None."""
        kw = _base_kwargs(["Z001"])
        rows = build_cn_core_rows(**kw)
        row = rows[0]
        assert row["extension_score"] is None
        assert row["extension_extended"] is None


# ============================================================ reversion_desk ==

class TestComputeReversionDesk:
    """Tests for compute_reversion_desk and bonus arithmetic (spec §4)."""

    def test_empty_snap_returns_empty(self):
        df = pd.DataFrame()
        result = compute_reversion_desk(df, as_of=ASOF)
        assert result == []

    def test_none_snap_returns_empty(self):
        result = compute_reversion_desk(None, as_of=ASOF)
        assert result == []

    def test_basic_rank_order(self):
        """Deeper reversal (lower sector_rank) should rank first."""
        # 5 names, sector_rank=1..5, no bonuses
        snap = _make_snap(5, rev_rank=[1, 2, 3, 4, 5], sector_n=[5] * 5)
        result = compute_reversion_desk(snap, as_of=ASOF)
        assert len(result) == 5
        # First row should have rank=1 in the output AND be the deepest (rev rank=1)
        assert result[0]["rank"] == 1
        assert result[0]["rev_depth"]["sector_rank"] == 1
        # Second row has sector_rank=2
        assert result[1]["rev_depth"]["sector_rank"] == 2

    def test_washout_bonus_lifts_rank(self):
        """washout_2w (+0.5) should lift a shallower name above a deeper one."""
        # T001 has sector_rank=1 (deepest, no bonus)
        # T002 has sector_rank=2 but washout_2w=True (+0.5)
        # With sector_n=5: T001 depth_score=1.0, T002 depth_score=0.75 + 0.5 = 1.25
        # So T002 should rank first
        snap = _make_snap(
            5,
            rev_rank=[1, 2, 3, 4, 5],
            sector_n=[5] * 5,
            washout_2w=[False, True, False, False, False],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        first = result[0]
        # T001's ticker (index 0) → T000 in the fixture
        # T002 (index 1) has washout bonus so score > T001
        assert first["rev_depth"]["sector_rank"] == 2  # T001 (washout=True) ranks first
        assert first["bonuses"].get("washout_2w") == pytest.approx(0.5)

    def test_coiled_bonus(self):
        """coiled (+0.25) lifts rank."""
        snap = _make_snap(
            3,
            rev_rank=[1, 2, 3],
            sector_n=[5, 5, 5],
            coiled=[False, True, False],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        # T001 (rank=2) with coiled=True should outscore T000 (rank=1, no bonus)
        # T000: depth=1.0; T001: depth=0.75 + 0.25 = 1.0 exactly → tie → sort stable
        # Check T001 bonus present
        coiled_row = next(r for r in result if r["rev_depth"]["sector_rank"] == 2)
        assert "coiled" in coiled_row["bonuses"]
        assert coiled_row["bonuses"]["coiled"] == pytest.approx(0.25)

    def test_star_bonus_not_stacked_with_coiled(self):
        """star (+0.15) only applies when coiled is False (elif)."""
        # T000: no bonus; T001: star=True, coiled=False → +0.15
        snap = _make_snap(
            2,
            rev_rank=[1, 2],
            sector_n=[5, 5],
            star=[False, True],
            coiled=[False, False],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        star_row = next(r for r in result if r["rev_depth"]["sector_rank"] == 2)
        assert "star" in star_row["bonuses"]
        assert star_row["bonuses"]["star"] == pytest.approx(0.15)

    def test_coiled_takes_precedence_over_star(self):
        """When coiled=True AND star=True, only coiled bonus (+0.25) applies."""
        snap = _make_snap(
            1,
            rev_rank=[1],
            sector_n=[5],
            coiled=[True],
            star=[True],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        row = result[0]
        assert row["bonuses"].get("coiled") == pytest.approx(0.25)
        assert "star" not in row["bonuses"]

    def test_extension_penalty(self):
        """extension_score of 1.0 → penalty of -0.5."""
        # T000: no bonus, no penalty; T001: ext_score=1.0, penalty=-0.5
        snap = _make_snap(
            2,
            rev_rank=[1, 2],
            sector_n=[5, 5],
            ext_score=[0.0, 1.0],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        ext_row = next(r for r in result if r["rev_depth"]["sector_rank"] == 2)
        assert "extension_penalty" in ext_row["bonuses"]
        assert ext_row["bonuses"]["extension_penalty"] == pytest.approx(-0.5)

    def test_extension_penalty_can_demote_deep_name(self):
        """A deeply-reversed name with high extension can be demoted below a shallower one."""
        # T000: sector_rank=1 (deepest), ext_score=1.0 → depth=1.0, ext=-0.5 → total=0.5
        # T001: sector_rank=2, ext_score=0.0 → depth=0.75 → total=0.75
        # T001 should rank first
        snap = _make_snap(
            2,
            rev_rank=[1, 2],
            sector_n=[5, 5],
            ext_score=[1.0, 0.0],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        assert result[0]["rev_depth"]["sector_rank"] == 2  # shallower but clean

    def test_washout_plus_coiled_stacks(self):
        """washout_2w (+0.5) and coiled (+0.25) stack on the same name."""
        snap = _make_snap(
            2,
            rev_rank=[1, 2],
            sector_n=[5, 5],
            washout_2w=[False, True],
            coiled=[False, True],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        stacked = next(r for r in result if r["rev_depth"]["sector_rank"] == 2)
        assert stacked["bonuses"].get("washout_2w") == pytest.approx(0.5)
        assert stacked["bonuses"].get("coiled") == pytest.approx(0.25)
        # depth(rank=2,n=5) = 1 - (2-1)/5 = 0.8; bonus = 0.5 + 0.25 = 0.75 → score = 1.55
        assert stacked["score"] == pytest.approx(1.55, abs=0.01)

    def test_st_excluded(self):
        """Names with is_st==True must not appear in the desk."""
        snap = _make_snap(
            3,
            is_st=[False, True, False],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        tickers_in_result = [r["ticker"] for r in result]
        assert "T001" not in tickers_in_result

    def test_fillable_false_excluded(self):
        """Names with fillable==False are excluded (executability screen, not signal)."""
        snap = _make_snap(
            3,
            fillable=[True, False, True],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        tickers_in_result = [r["ticker"] for r in result]
        assert "T001" not in tickers_in_result

    def test_max_rows_respected(self):
        """Output must not exceed max_rows."""
        snap = _make_snap(20)
        result = compute_reversion_desk(snap, as_of=ASOF, max_rows=12)
        assert len(result) <= 12

    def test_max_rows_custom(self):
        """Custom max_rows is honoured."""
        snap = _make_snap(10)
        result = compute_reversion_desk(snap, as_of=ASOF, max_rows=5)
        assert len(result) <= 5

    def test_non_deepest_excluded(self):
        """Names with rev_deepest_quintile==False are excluded from the desk."""
        snap = _make_snap(
            5,
            rev_deepest=[True, False, True, False, True],
        )
        result = compute_reversion_desk(snap, as_of=ASOF)
        # Only 3 names pass; all should be in the result
        assert len(result) == 3

    def test_all_filtered_returns_empty(self):
        """If all names fail screens, result is empty."""
        snap = _make_snap(3, is_st=[True, True, True])
        result = compute_reversion_desk(snap, as_of=ASOF)
        assert result == []

    def test_output_row_schema(self):
        """Every row must have the required output fields."""
        snap = _make_snap(3)
        result = compute_reversion_desk(snap, as_of=ASOF)
        required_keys = {
            "ticker", "name", "name_zh", "rank", "score",
            "rev_depth", "bonuses", "chips", "close", "sector", "authority",
        }
        for row in result:
            for key in required_keys:
                assert key in row, f"Missing key {key!r}"

    def test_authority_display_only(self):
        """Every row must carry authority='display_only' (CNPL-R1)."""
        snap = _make_snap(3)
        result = compute_reversion_desk(snap, as_of=ASOF)
        for row in result:
            assert row["authority"] == "display_only"

    def test_rank_sequence_starts_at_1(self):
        """Ranks must be 1-indexed sequential."""
        snap = _make_snap(5)
        result = compute_reversion_desk(snap, as_of=ASOF)
        for i, row in enumerate(result):
            assert row["rank"] == i + 1

    def test_chips_include_cycle_phase(self):
        """cycle_phase present in snap → appears as a chip."""
        snap = _make_snap(2)
        snap["cycle_phase"] = "RECOVERY"
        result = compute_reversion_desk(snap, as_of=ASOF)
        for row in result:
            assert row["chips"].get("cycle_phase") == "RECOVERY"

    def test_exception_safety(self):
        """compute_reversion_desk must not raise on malformed input."""
        # Passing a non-DataFrame shouldn't raise
        result = compute_reversion_desk("not a dataframe", as_of=ASOF)
        assert result == []


class TestBuildReversionDeskArtifact:
    """Tests for build_reversion_desk_artifact (JSON wrapper)."""

    def test_schema_key(self):
        snap = _make_snap(5)
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF)
        assert artifact["schema"] == "china_reversion_desk.v1"

    def test_as_of_key(self):
        snap = _make_snap(5)
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF)
        assert artifact["as_of"] == ASOF

    def test_n_rows_matches_rows(self):
        snap = _make_snap(5)
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF)
        assert artifact["n_rows"] == len(artifact["rows"])

    def test_authority_field(self):
        snap = _make_snap(5)
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF)
        assert artifact["authority"] == "display_only"

    def test_empty_snap_gives_empty_rows(self):
        artifact = build_reversion_desk_artifact(pd.DataFrame(), as_of=ASOF)
        assert artifact["rows"] == []
        assert artifact["n_rows"] == 0
        assert artifact["schema"] == "china_reversion_desk.v1"

    def test_max_rows_respected(self):
        snap = _make_snap(20)
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF, max_rows=8)
        assert len(artifact["rows"]) <= 8
        assert artifact["n_rows"] <= 8


class TestComputeScoreUnit:
    """Direct unit tests for _compute_score bonus arithmetic."""

    def _row(self, **kwargs) -> "pd.Series":
        defaults = dict(
            rev_3m_sector_rank=1,
            rev_sector_n=5,
            washout_2w=False,
            coiled=False,
            star=False,
            extension_score=0.0,
        )
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_no_bonuses(self):
        """rank=1, n=5 → depth=1.0; no bonuses → score=1.0."""
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5)
        assert _compute_score(row) == pytest.approx(1.0)

    def test_washout_adds_half(self):
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5, washout_2w=True)
        assert _compute_score(row) == pytest.approx(1.5)

    def test_coiled_adds_quarter(self):
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5, coiled=True)
        assert _compute_score(row) == pytest.approx(1.25)

    def test_star_adds_point_15(self):
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5, star=True)
        assert _compute_score(row) == pytest.approx(1.15)

    def test_extension_penalty_full(self):
        """extension_score=1.0 → -0.5 penalty."""
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5, extension_score=1.0)
        assert _compute_score(row) == pytest.approx(0.5)

    def test_washout_plus_coiled_stacks(self):
        row = self._row(rev_3m_sector_rank=1, rev_sector_n=5, washout_2w=True, coiled=True)
        assert _compute_score(row) == pytest.approx(1.75)

    def test_all_bonuses_plus_extension(self):
        """washout (+0.5) + coiled (+0.25) + ext_score=0.5 (-0.25 penalty) = +0.5 net."""
        row = self._row(
            rev_3m_sector_rank=1, rev_sector_n=5,
            washout_2w=True, coiled=True, extension_score=0.5,
        )
        # depth=1.0 (rank=1,n=5); bonus = 0.5 + 0.25 - 0.5*0.5 = 0.5; score = 1.5
        assert _compute_score(row) == pytest.approx(1.5)

    def test_coiled_wins_over_star_when_both_set(self):
        """When both coiled and star are True, only coiled (+0.25) applies."""
        row_both = self._row(rev_3m_sector_rank=1, rev_sector_n=5, coiled=True, star=True)
        row_coiled_only = self._row(rev_3m_sector_rank=1, rev_sector_n=5, coiled=True)
        assert _compute_score(row_both) == pytest.approx(_compute_score(row_coiled_only))

    def test_null_rank_gives_zero_depth(self):
        """When rev_3m_sector_rank is None, depth_component = 0."""
        row = self._row(rev_3m_sector_rank=None, rev_sector_n=5)
        assert _compute_score(row) == pytest.approx(0.0)


class TestReversionDeskNoValidatedWord:
    """Guard: 'validated' must not appear in user-facing strings (CI-enforced word)."""

    def test_no_validated_in_module(self):
        import engine.pick_lab.reversion_desk as _mod
        import inspect
        source = inspect.getsource(_mod)
        # 'validated' is only allowed in comments citing the spec
        # The word in user-facing output would be in authority/schema/chips fields
        # We check it doesn't appear in the JSON-serialized output rows
        snap = _make_snap(5)
        import json
        artifact = build_reversion_desk_artifact(snap, as_of=ASOF)
        output_str = json.dumps(artifact)
        assert "validated" not in output_str, (
            "User-facing output must not contain the word 'validated' (CI-enforced)"
        )
