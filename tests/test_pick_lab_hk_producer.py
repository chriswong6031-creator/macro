"""Tests for HK Pick Lab snapshot producer + 1D Velocity Desk (spec §4/§5).

Covers:
  - hk_snapshot.HK_SNAPSHOT_COLUMNS: completeness, no duplicates, key columns present
  - hk_snapshot.build_hk_core_rows: null-honest assembly, all columns present,
    asof/ticker stamped, regime scalars broadcast, oscillator propagation
  - hk_snapshot.build_hk_core_rows: organ columns always None at producer time
  - velocity_desk.compute_velocity_desk: membership (union of books 1–5), rank order,
    confluence_n counting, knife/chase warning chips (NOT exclusions), two-pass behavior
  - velocity_desk.build_velocity_desk_artifact: schema/as_of/rows/authority output
  - Velocity desk: max 8 rows (HKPL-R6), rank is 1-indexed sequential
  - No "validated" word in any user-facing output

Does NOT import build_hk_library (heavy pipeline dependency).
Does NOT hit disk.
Does NOT call store.read or any network/I/O.

Run:
    python3 -m pytest tests/test_pick_lab_hk_producer.py -x -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS, build_hk_core_rows
from engine.pick_lab.velocity_desk import (
    compute_velocity_desk,
    build_velocity_desk_artifact,
    _cond_1d_pure,
    _cond_1d_ignition,
    _cond_1d_adr,
    _cond_1d_blastoff,
    _cond_1d_regime,
    _is_1d_member,
    _confluence_n,
    _build_chips,
)


# ============================================================ shared helpers ==

TICKERS = ["HK001", "HK002", "HK003", "HK004", "HK005",
           "HK006", "HK007", "HK008"]
ASOF = "2024-07-09"


def _base_kwargs(tickers=None) -> dict:
    """Minimal build_hk_core_rows kwargs — all required arguments, null-honest defaults."""
    if tickers is None:
        tickers = list(TICKERS)
    return dict(
        tickers=list(tickers),
        asof=ASOF,
        close_by={t: float(i + 10) for i, t in enumerate(tickers)},
        adv63_hkd_by={t: 50e6 for t in tickers},
        name_by={t: f"Corp {t}" for t in tickers},
        name_zh_by={t: f"公司 {t}" for t in tickers},
        sector_by={t: "Financials" for t in tickers},
    )


def _make_hk_snap(
    n: int = 8,
    d1_macd_xup_bars: list | None = None,
    d1_stoch_xup_bars: list | None = None,
    d1_from_os: list | None = None,
    rsi14: list | None = None,
    above_200: list | None = None,
    edge_z: list | None = None,
    washout_state: list | None = None,
    adr_gap_pct: list | None = None,
    d3_macd_xup_bars: list | None = None,
    risk_state: list | None = None,
    knife_risk: list | None = None,
    extended: list | None = None,
    beta_role: list | None = None,
    cbbc_leverage_state: list | None = None,
) -> pd.DataFrame:
    """Build a synthetic HK snapshot DataFrame for velocity_desk tests."""
    tickers = [f"H{i:03d}" for i in range(n)]
    data: dict = {
        "d1_macd_xup_bars": d1_macd_xup_bars if d1_macd_xup_bars is not None else [None] * n,
        "d1_stoch_xup_bars": d1_stoch_xup_bars if d1_stoch_xup_bars is not None else [None] * n,
        "d1_from_os": d1_from_os if d1_from_os is not None else [False] * n,
        "rsi14": rsi14 if rsi14 is not None else [45.0] * n,
        "above_200": above_200 if above_200 is not None else [False] * n,
        "edge_z": edge_z if edge_z is not None else [0.5] * n,
        "washout_state": washout_state if washout_state is not None else [None] * n,
        "adr_gap_pct": adr_gap_pct if adr_gap_pct is not None else [None] * n,
        "d3_macd_xup_bars": d3_macd_xup_bars if d3_macd_xup_bars is not None else [None] * n,
        "risk_state": risk_state if risk_state is not None else [None] * n,
        "knife_risk": knife_risk if knife_risk is not None else [False] * n,
        "extended": extended if extended is not None else [False] * n,
        "beta_role": beta_role if beta_role is not None else ["neutral"] * n,
        "cbbc_leverage_state": cbbc_leverage_state if cbbc_leverage_state is not None else [None] * n,
        "close": [float(10 + i) for i in range(n)],
        "sector": ["Financials"] * n,
        "name": [f"Corp H{i:03d}" for i in range(n)],
        "name_zh": [f"公司 {i}" for i in range(n)],
    }
    df = pd.DataFrame(data, index=pd.Index(tickers, name="ticker"))
    df.attrs["asof"] = ASOF
    return df


# ============================================================ HK_SNAPSHOT_COLUMNS ==

class TestHKSnapshotColumns:
    """HK_SNAPSHOT_COLUMNS completeness checks."""

    def test_is_list_of_strings(self):
        assert isinstance(HK_SNAPSHOT_COLUMNS, list)
        assert len(HK_SNAPSHOT_COLUMNS) > 0
        assert all(isinstance(c, str) for c in HK_SNAPSHOT_COLUMNS)

    def test_no_duplicates(self):
        assert len(HK_SNAPSHOT_COLUMNS) == len(set(HK_SNAPSHOT_COLUMNS))

    def test_key_columns_present(self):
        """Key HK columns must be in HK_SNAPSHOT_COLUMNS."""
        required = [
            "ticker", "asof", "sector", "close",
            "adv63_hkd", "last_print_sessions_ago",
            "off_high", "rsi14", "dist_200dma", "above_200",
            "edge_z", "beta", "beta_role",
            "washout_2w", "extended",
            "d1_macd_xup_bars", "d1_stoch_xup_bars", "d1_from_os",
            "d2_macd_xup_bars", "d3_macd_xup_bars",
            "sessions_since_23d_cross", "ret_since_23d_cross",
            "risk_state", "peg_state", "liquidity_regime", "vhsi_pctile", "hsi_close",
            # Organ columns (null at producer time)
            "washout_state", "adr_gap_pct", "cbbc_leverage_state",
            "knife_risk", "sb_accum_z", "ah_discount_pctile",
            # Freshness columns
            "organ_fresh_washout", "organ_fresh_adr", "organ_fresh_sb",
        ]
        for col in required:
            assert col in HK_SNAPSHOT_COLUMNS, f"Missing key column: {col}"

    def test_organ_columns_present(self):
        """All organ columns from hk.py must be in HK_SNAPSHOT_COLUMNS."""
        organ_cols = [
            "washout_state", "confluence_count", "confluence_signals",
            "knife_risk", "adr_gap_pct", "cbbc_leverage_state",
            "buyback_flag", "dilution_flag", "catalyst_days_to",
            "attention_shock_z", "narrative_tone",
            "sfc_short_pressure_q", "sb_accum_z", "ah_discount_pctile",
        ]
        for col in organ_cols:
            assert col in HK_SNAPSHOT_COLUMNS, f"Missing organ column: {col}"

    def test_freshness_columns_present(self):
        """All organ freshness columns must be in HK_SNAPSHOT_COLUMNS (HKPL-R7)."""
        for tag in ("washout", "adr", "cbbc", "narrative", "catalyst", "sb"):
            col = f"organ_fresh_{tag}"
            assert col in HK_SNAPSHOT_COLUMNS, f"Missing freshness column: {col}"


# ============================================================ build_hk_core_rows ==

class TestBuildHKCoreRows:
    """Unit tests for build_hk_core_rows pure assembler."""

    def test_empty_tickers_returns_empty(self):
        kw = _base_kwargs([])
        rows = build_hk_core_rows(**kw)
        assert rows == []

    def test_all_hk_snapshot_columns_present(self):
        """Every row must carry all HK_SNAPSHOT_COLUMNS keys."""
        rows = build_hk_core_rows(**_base_kwargs())
        assert len(rows) == len(TICKERS)
        for row in rows:
            for col in HK_SNAPSHOT_COLUMNS:
                assert col in row, f"Missing column {col!r} in row for {row.get('ticker')}"

    def test_asof_stamped(self):
        rows = build_hk_core_rows(**_base_kwargs())
        for row in rows:
            assert row["asof"] == ASOF

    def test_ticker_identity(self):
        rows = build_hk_core_rows(**_base_kwargs())
        result_tickers = [r["ticker"] for r in rows]
        assert result_tickers == list(TICKERS)

    def test_null_close_is_none_not_nan(self):
        """Null values must be Python None, not NaN."""
        kw = _base_kwargs()
        kw["close_by"]["HK001"] = None
        rows = build_hk_core_rows(**kw)
        row0 = next(r for r in rows if r["ticker"] == "HK001")
        assert row0["close"] is None

    def test_organ_columns_always_none_at_producer(self):
        """Organ columns must be None at producer time (runner fills via upsert)."""
        rows = build_hk_core_rows(**_base_kwargs())
        organ_cols = [
            "washout_state", "confluence_count", "confluence_signals",
            "knife_risk", "adr_gap_pct", "cbbc_leverage_state",
            "buyback_flag", "dilution_flag", "catalyst_days_to",
            "attention_shock_z", "narrative_tone",
            "sfc_short_pressure_q", "sb_accum_z", "ah_discount_pctile",
        ]
        for row in rows:
            for col in organ_cols:
                assert row[col] is None, (
                    f"Organ column {col!r} must be None at producer time, "
                    f"got {row[col]!r} for {row['ticker']}"
                )

    def test_freshness_columns_always_none_at_producer(self):
        """Organ freshness columns must be None at producer time (HKPL-R7)."""
        rows = build_hk_core_rows(**_base_kwargs())
        for row in rows:
            for tag in ("washout", "adr", "cbbc", "narrative", "catalyst", "sb"):
                col = f"organ_fresh_{tag}"
                assert row[col] is None, (
                    f"Freshness column {col!r} must be None at producer time"
                )

    def test_regime_scalars_broadcast(self):
        """Regime scalars are broadcast identically to every row."""
        kw = _base_kwargs()
        kw["risk_state"] = "Risk-on"
        kw["vhsi_pctile"] = 35.0
        kw["hsi_close"] = 20000.5
        kw["liquidity_regime"] = "EASY"
        rows = build_hk_core_rows(**kw)
        for row in rows:
            assert row["risk_state"] == "Risk-on"
            assert row["vhsi_pctile"] == pytest.approx(35.0)
            assert row["hsi_close"] == pytest.approx(20000.5)
            assert row["liquidity_regime"] == "EASY"

    def test_oscillator_d1_propagated(self):
        kw = _base_kwargs(["HK001"])
        kw["osc_d123_by"] = {
            "HK001": {
                "d1_macd": 0.3, "d1_sig": 0.1,
                "d1_macd_xup_bars": 2.0,
                "d1_k": 35.0, "d1_d": 28.0,
                "d1_kd_xup_bars": 3.0,     # → stored as d1_stoch_xup_bars
                "d1_from_os": True, "d1_ob": False,
                "d2_macd": None, "d2_sig": None,
                "d2_macd_xup_bars": None, "d2_k": None, "d2_d": None,
                "d2_kd_xup_bars": None, "d2_from_os": None, "d2_ob": None,
                "d3_macd_xup_bars": None,
            }
        }
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["d1_macd_xup_bars"] == pytest.approx(2.0)
        assert row["d1_from_os"] is True
        assert row["d1_ob"] is False
        # d1_kd_xup_bars → d1_stoch_xup_bars (alias for hk.py)
        assert row["d1_stoch_xup_bars"] == pytest.approx(3.0)

    def test_d3_macd_xup_bars_propagated(self):
        kw = _base_kwargs(["HK001"])
        kw["osc_d123_by"] = {
            "HK001": {
                "d1_macd_xup_bars": 1.0,
                "d1_kd_xup_bars": 5.0,
                "d1_from_os": False, "d1_ob": False,
                "d1_macd": None, "d1_sig": None, "d1_k": None, "d1_d": None,
                "d2_macd": None, "d2_sig": None, "d2_macd_xup_bars": None,
                "d2_k": None, "d2_d": None, "d2_kd_xup_bars": None,
                "d2_from_os": None, "d2_ob": None,
                "d3_macd_xup_bars": 4.0,
            }
        }
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["d3_macd_xup_bars"] == pytest.approx(4.0)

    def test_washout_2w_extended_propagated(self):
        kw = _base_kwargs()
        kw["washout_2w_by"] = {"HK001": True, "HK002": False}
        kw["extended_by"] = {"HK001": False, "HK002": True}
        rows = build_hk_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "HK001")
        r2 = next(r for r in rows if r["ticker"] == "HK002")
        assert r1["washout_2w"] is True
        assert r1["extended"] is False
        assert r2["washout_2w"] is False
        assert r2["extended"] is True

    def test_stale_cross_diagnostic_propagated(self):
        kw = _base_kwargs(["HK001"])
        kw["sessions_since_23d_cross_by"] = {"HK001": 7}
        kw["ret_since_23d_cross_by"] = {"HK001": 0.015}
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["sessions_since_23d_cross"] == 7
        assert row["ret_since_23d_cross"] == pytest.approx(0.015)

    def test_null_honest_missing_cols(self):
        """Fields not provided → None (never fabricated or NaN)."""
        kw = _base_kwargs(["X001"])
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["edge_z"] is None
        assert row["beta"] is None
        assert row["washout_2w"] is None
        assert row["d1_macd_xup_bars"] is None
        assert row["risk_state"] is None
        assert row["vhsi_pctile"] is None

    def test_beta_columns_propagated(self):
        kw = _base_kwargs(["HK001"])
        kw["beta_by"] = {"HK001": 1.35}
        kw["beta_role_by"] = {"HK001": "amplifier"}
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["beta"] == pytest.approx(1.35)
        assert row["beta_role"] == "amplifier"

    def test_last_print_sessions_ago_propagated(self):
        kw = _base_kwargs(["HK001", "HK002"])
        kw["last_print_sessions_ago_by"] = {"HK001": 0, "HK002": 3}
        rows = build_hk_core_rows(**kw)
        r1 = next(r for r in rows if r["ticker"] == "HK001")
        r2 = next(r for r in rows if r["ticker"] == "HK002")
        assert r1["last_print_sessions_ago"] == 0
        assert r2["last_print_sessions_ago"] == 3

    def test_edge_basis_propagated(self):
        kw = _base_kwargs(["HK001"])
        kw["edge_basis_by"] = {"HK001": [{"leg": "sb", "z": 1.2}]}
        rows = build_hk_core_rows(**kw)
        row = rows[0]
        assert row["edge_basis"] == [{"leg": "sb", "z": 1.2}]


# ============================================================ Membership predicates ==

class TestMembershipPredicates:
    """Unit tests for the 1D-family predicate functions."""

    def _row(self, **kwargs) -> pd.Series:
        defaults = dict(
            d1_macd_xup_bars=None,
            d1_stoch_xup_bars=None,
            d1_from_os=False,
            rsi14=45.0,
            above_200=True,
            washout_state=None,
            adr_gap_pct=None,
            d3_macd_xup_bars=None,
            risk_state=None,
        )
        defaults.update(kwargs)
        return pd.Series(defaults)

    # --- 1d_pure ---
    def test_1d_pure_fires_all_conditions(self):
        row = self._row(d1_macd_xup_bars=2, d1_stoch_xup_bars=5, d1_from_os=True, rsi14=60)
        assert _cond_1d_pure(row) is True

    def test_1d_pure_fails_macd_too_old(self):
        row = self._row(d1_macd_xup_bars=3, d1_stoch_xup_bars=5, d1_from_os=True, rsi14=60)
        assert _cond_1d_pure(row) is False

    def test_1d_pure_fails_stoch_too_old(self):
        row = self._row(d1_macd_xup_bars=1, d1_stoch_xup_bars=9, d1_from_os=True, rsi14=60)
        assert _cond_1d_pure(row) is False

    def test_1d_pure_fails_not_from_os(self):
        row = self._row(d1_macd_xup_bars=2, d1_stoch_xup_bars=5, d1_from_os=False, rsi14=60)
        assert _cond_1d_pure(row) is False

    def test_1d_pure_fails_rsi_too_high(self):
        row = self._row(d1_macd_xup_bars=2, d1_stoch_xup_bars=5, d1_from_os=True, rsi14=70)
        assert _cond_1d_pure(row) is False

    def test_1d_pure_fails_null_macd(self):
        row = self._row(d1_macd_xup_bars=None, d1_stoch_xup_bars=5, d1_from_os=True, rsi14=60)
        assert _cond_1d_pure(row) is False

    # --- 1d_ignition ---
    def test_1d_ignition_fires(self):
        row = self._row(d1_macd_xup_bars=3, washout_state="ignition_watch")
        assert _cond_1d_ignition(row) is True

    def test_1d_ignition_fires_pullback(self):
        row = self._row(d1_macd_xup_bars=2, washout_state="pullback_entry_watch")
        assert _cond_1d_ignition(row) is True

    def test_1d_ignition_fails_wrong_state(self):
        row = self._row(d1_macd_xup_bars=2, washout_state="washout_watch")
        assert _cond_1d_ignition(row) is False

    def test_1d_ignition_fails_null_state(self):
        row = self._row(d1_macd_xup_bars=2, washout_state=None)
        assert _cond_1d_ignition(row) is False

    def test_1d_ignition_fails_macd_too_old(self):
        row = self._row(d1_macd_xup_bars=4, washout_state="ignition_watch")
        assert _cond_1d_ignition(row) is False

    # --- 1d_adr ---
    def test_1d_adr_fires(self):
        row = self._row(d1_macd_xup_bars=2, adr_gap_pct=0.7)
        assert _cond_1d_adr(row) is True

    def test_1d_adr_exact_threshold(self):
        row = self._row(d1_macd_xup_bars=2, adr_gap_pct=0.5)
        assert _cond_1d_adr(row) is True

    def test_1d_adr_fails_small_gap(self):
        row = self._row(d1_macd_xup_bars=2, adr_gap_pct=0.4)
        assert _cond_1d_adr(row) is False

    def test_1d_adr_fails_null_gap(self):
        row = self._row(d1_macd_xup_bars=2, adr_gap_pct=None)
        assert _cond_1d_adr(row) is False

    def test_1d_adr_fails_macd_too_old(self):
        row = self._row(d1_macd_xup_bars=3, adr_gap_pct=0.7)
        assert _cond_1d_adr(row) is False

    # --- 1d_blastoff ---
    def test_1d_blastoff_fires(self):
        """1D cross ≤3, 3D null (not yet crossed), above 200dma."""
        row = self._row(d1_macd_xup_bars=2, d3_macd_xup_bars=None, above_200=True)
        assert _cond_1d_blastoff(row) is True

    def test_1d_blastoff_fails_3d_crossed(self):
        """3D already crossed → not the fast cohort."""
        row = self._row(d1_macd_xup_bars=2, d3_macd_xup_bars=4.0, above_200=True)
        assert _cond_1d_blastoff(row) is False

    def test_1d_blastoff_fails_below_200(self):
        row = self._row(d1_macd_xup_bars=2, d3_macd_xup_bars=None, above_200=False)
        assert _cond_1d_blastoff(row) is False

    def test_1d_blastoff_fails_macd_too_old(self):
        row = self._row(d1_macd_xup_bars=4, d3_macd_xup_bars=None, above_200=True)
        assert _cond_1d_blastoff(row) is False

    # --- 1d_regime ---
    def test_1d_regime_fires(self):
        row = self._row(d1_macd_xup_bars=3, risk_state="Risk-on")
        assert _cond_1d_regime(row) is True

    def test_1d_regime_fails_wrong_state(self):
        row = self._row(d1_macd_xup_bars=2, risk_state="Risk-off")
        assert _cond_1d_regime(row) is False

    def test_1d_regime_fails_null_state(self):
        row = self._row(d1_macd_xup_bars=2, risk_state=None)
        assert _cond_1d_regime(row) is False

    # --- _is_1d_member ---
    def test_membership_union(self):
        """A row meeting any condition is a member."""
        # meets 1d_blastoff only
        row = self._row(d1_macd_xup_bars=2, d3_macd_xup_bars=None, above_200=True)
        assert _is_1d_member(row) is True

    def test_membership_none_fires(self):
        """A row meeting no condition is not a member."""
        row = self._row()  # all None / default False
        assert _is_1d_member(row) is False


# ============================================================ Confluence count ==

class TestConfluenceN:
    """Unit tests for _confluence_n secondary signal counting."""

    def _row(self, **kwargs) -> pd.Series:
        defaults = dict(
            d1_from_os=False,
            washout_state=None,
            adr_gap_pct=None,
            risk_state=None,
            above_200=False,
        )
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_zero_signals(self):
        row = self._row()
        assert _confluence_n(row) == 0

    def test_all_five_signals(self):
        row = self._row(
            d1_from_os=True,
            washout_state="ignition_watch",
            adr_gap_pct=0.8,
            risk_state="Risk-on",
            above_200=True,
        )
        assert _confluence_n(row) == 5

    def test_from_os_alone(self):
        row = self._row(d1_from_os=True)
        assert _confluence_n(row) == 1

    def test_washout_state_active(self):
        """All active washout states count as one signal."""
        for ws in ("washout_watch", "ignition_watch", "pullback_entry_watch"):
            row = self._row(washout_state=ws)
            assert _confluence_n(row) == 1, f"Expected 1 for washout_state={ws}"

    def test_washout_state_chase_risk_not_counted(self):
        """chase_risk is not an active washout state for confluence count."""
        row = self._row(washout_state="chase_risk")
        assert _confluence_n(row) == 0

    def test_adr_gap_exact_threshold(self):
        """adr_gap_pct exactly 0.5 counts."""
        row = self._row(adr_gap_pct=0.5)
        assert _confluence_n(row) == 1

    def test_adr_gap_below_threshold_not_counted(self):
        row = self._row(adr_gap_pct=0.49)
        assert _confluence_n(row) == 0

    def test_risk_on_counts(self):
        row = self._row(risk_state="Risk-on")
        assert _confluence_n(row) == 1

    def test_risk_off_not_counted(self):
        row = self._row(risk_state="Risk-off")
        assert _confluence_n(row) == 0

    def test_above_200_counts(self):
        row = self._row(above_200=True)
        assert _confluence_n(row) == 1


# ============================================================ Velocity desk ==

class TestComputeVelocityDesk:
    """Tests for compute_velocity_desk rank order and behavior."""

    def test_empty_snap_returns_empty(self):
        result = compute_velocity_desk(pd.DataFrame(), as_of=ASOF)
        assert result == []

    def test_none_snap_returns_empty(self):
        result = compute_velocity_desk(None, as_of=ASOF)  # type: ignore[arg-type]
        assert result == []

    def test_no_members_returns_empty(self):
        """Snapshot with no rows meeting 1D conditions → empty desk."""
        snap = _make_hk_snap(3)  # all d1_macd_xup_bars=None → no members
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert result == []

    def test_membership_filter_applied(self):
        """Only rows meeting a 1D condition appear in the desk."""
        snap = _make_hk_snap(3)
        # Set only the first ticker to meet 1d_blastoff
        snap.loc["H000", "d1_macd_xup_bars"] = 2
        snap.loc["H000", "above_200"] = True
        # d3_macd_xup_bars is already None by default
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) == 1
        assert result[0]["ticker"] == "H000"

    def test_rank_by_confluence_n_then_edge_z(self):
        """Rows ranked: higher confluence_n first; ties broken by edge_z DESC."""
        snap = _make_hk_snap(
            3,
            d1_macd_xup_bars=[1.0, 2.0, 3.0],
            d1_from_os=[True, True, True],   # all from_os = +1 confluence each
            above_200=[True, True, True],     # +1 each
            risk_state=["Risk-on", None, None],  # H000 gets +1 extra
            edge_z=[1.0, 2.0, 3.0],
        )
        # H000: confluence = from_os(1) + above_200(1) + risk_on(1) = 3, edge_z=1.0
        # H001: confluence = from_os(1) + above_200(1) = 2, edge_z=2.0
        # H002: confluence = from_os(1) + above_200(1) = 2, edge_z=3.0
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert result[0]["ticker"] == "H000"    # highest confluence
        # H002 beats H001 on tie in confluence (both=2) via edge_z
        assert result[1]["ticker"] == "H002"
        assert result[2]["ticker"] == "H001"

    def test_confluence_n_stamped_correctly(self):
        """confluence_n on each row matches the actual count of signals."""
        snap = _make_hk_snap(
            1,
            d1_macd_xup_bars=[1.0],
            d1_from_os=[True],
            above_200=[True],
            risk_state=["Risk-on"],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) == 1
        # from_os + above_200 + risk_on = 3
        assert result[0]["confluence_n"] == 3

    def test_max_rows_respected(self):
        """Output must not exceed max_rows (HKPL-R6)."""
        # Build 10 eligible rows
        n = 10
        snap = _make_hk_snap(
            n,
            d1_macd_xup_bars=[2.0] * n,
            d1_from_os=[True] * n,
            d1_stoch_xup_bars=[5.0] * n,
            rsi14=[50.0] * n,
        )
        result = compute_velocity_desk(snap, as_of=ASOF, max_rows=8)
        assert len(result) <= 8

    def test_default_max_rows_8(self):
        """Default max_rows = 8 (HKPL-R6)."""
        n = 12
        snap = _make_hk_snap(
            n,
            d1_macd_xup_bars=[2.0] * n,
            d1_from_os=[True] * n,
            d1_stoch_xup_bars=[5.0] * n,
            rsi14=[50.0] * n,
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) <= 8

    def test_rank_is_1_indexed_sequential(self):
        """Ranks must be 1-indexed consecutive integers."""
        n = 4
        snap = _make_hk_snap(
            n,
            d1_macd_xup_bars=[1.0] * n,
            d1_from_os=[True] * n,
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        for i, row in enumerate(result):
            assert row["rank"] == i + 1

    def test_output_row_schema(self):
        """Every row must have the required output fields."""
        snap = _make_hk_snap(
            2,
            d1_macd_xup_bars=[1.0, 2.0],
            d1_from_os=[True, False],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        required_keys = {
            "ticker", "name", "name_zh", "rank",
            "confluence_n", "chips", "close", "sector",
            "edge_z", "authority",
        }
        for row in result:
            for key in required_keys:
                assert key in row, f"Missing key {key!r}"

    def test_authority_display_only(self):
        """Every row must carry authority='display_only' (HKPL-R1)."""
        snap = _make_hk_snap(
            2,
            d1_macd_xup_bars=[1.0, 2.0],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        for row in result:
            assert row["authority"] == "display_only"

    def test_knife_chip_shown_not_excluded(self):
        """knife_risk=True names appear in the desk with a warning chip (NOT excluded).

        HK keeps knives visible per organ doctrine — knife_risk is a chip, never a gate.
        H000 meets 1d_blastoff (d1_macd_xup_bars≤3, d3=None, above_200=True).
        """
        snap = _make_hk_snap(
            2,
            d1_macd_xup_bars=[2.0, None],   # H000 meets 1d_blastoff; H001 is not a member
            d3_macd_xup_bars=[None, None],   # 3D not crossed → blastoff eligible
            above_200=[True, False],          # H000 above 200dma
            knife_risk=[True, False],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        # H000 must appear (not excluded) AND have knife_warning chip
        h000 = next((r for r in result if r["ticker"] == "H000"), None)
        assert h000 is not None, "knife_risk=True row should NOT be excluded from the desk"
        assert h000["chips"].get("knife_warning") is True

    def test_extended_chip_shown_not_excluded(self):
        """extended=True (chase warning) appears as chip, NOT an exclusion.

        H000 meets 1d_blastoff (d1_macd_xup_bars≤3, d3=None, above_200=True).
        """
        snap = _make_hk_snap(
            2,
            d1_macd_xup_bars=[2.0, None],   # H000 meets 1d_blastoff; H001 not a member
            d3_macd_xup_bars=[None, None],
            above_200=[True, False],
            extended=[True, False],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        h000 = next((r for r in result if r["ticker"] == "H000"), None)
        assert h000 is not None, "extended=True row should NOT be excluded from the desk"
        assert h000["chips"].get("extended_warning") is True

    def test_two_pass_null_organ_behavior(self):
        """First-pass (producer): organ columns null → honest null-fail in membership.

        hklab_1d_ignition requires washout_state — it is null at producer time.
        A row that ONLY meets 1d_ignition (which needs organ) should be excluded
        in the price-only first pass. A row that meets 1d_blastoff (price-only)
        should still appear.
        """
        snap = _make_hk_snap(
            2,
            d1_macd_xup_bars=[2.0, 2.0],
            # H000: meets blastoff (above_200=True, d3=None, no washout_state)
            # H001: needs ignition (washout_state=null → ignition condition fails)
            above_200=[True, False],
            d3_macd_xup_bars=[None, None],
            washout_state=[None, None],   # organ null = ignition fails for H001
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        tickers_in_result = [r["ticker"] for r in result]
        assert "H000" in tickers_in_result, "blastoff condition should fire without organs"
        # H001 meets neither blastoff (above_200=False) nor ignition (washout_state=None)
        # nor pure (no from_os/stoch), nor adr (no gap), nor regime (no risk_state)
        assert "H001" not in tickers_in_result

    def test_adr_chip_shown_when_present(self):
        """adr_gap_pct appears as a chip when present."""
        snap = _make_hk_snap(
            1,
            d1_macd_xup_bars=[1.0],
            adr_gap_pct=[0.75],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) == 1
        assert result[0]["chips"].get("adr_gap_pct") == pytest.approx(0.75)

    def test_condition_chips_present(self):
        """Chips include which 1D conditions fired."""
        snap = _make_hk_snap(
            1,
            d1_macd_xup_bars=[2.0],
            d1_stoch_xup_bars=[5.0],
            d1_from_os=[True],
            rsi14=[55.0],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) == 1
        chips = result[0]["chips"]
        assert chips.get("1d_pure") is True

    def test_exception_safety(self):
        """compute_velocity_desk must not raise on malformed input."""
        result = compute_velocity_desk("not a dataframe", as_of=ASOF)  # type: ignore[arg-type]
        assert result == []

    def test_washout_state_chip_shown(self):
        """washout_state from organ appears as chip when not null."""
        snap = _make_hk_snap(
            1,
            d1_macd_xup_bars=[2.0],
            washout_state=["ignition_watch"],
        )
        result = compute_velocity_desk(snap, as_of=ASOF)
        assert len(result) == 1
        assert result[0]["chips"].get("washout_state") == "ignition_watch"


# ============================================================ Artifact wrapper ==

class TestBuildVelocityDeskArtifact:
    """Tests for build_velocity_desk_artifact (JSON wrapper)."""

    def test_schema_key(self):
        snap = _make_hk_snap(
            2, d1_macd_xup_bars=[1.0, 2.0], d1_from_os=[True, False]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        assert artifact["schema"] == "hk_1d_velocity_desk.v1"

    def test_as_of_key(self):
        snap = _make_hk_snap(
            2, d1_macd_xup_bars=[1.0, 2.0], d1_from_os=[True, False]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        assert artifact["as_of"] == ASOF

    def test_n_rows_matches_rows(self):
        snap = _make_hk_snap(
            3, d1_macd_xup_bars=[1.0, 2.0, 3.0], d1_from_os=[True, True, True]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        assert artifact["n_rows"] == len(artifact["rows"])

    def test_authority_field(self):
        snap = _make_hk_snap(
            2, d1_macd_xup_bars=[1.0, 2.0], d1_from_os=[True, False]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        assert artifact["authority"] == "display_only"

    def test_empty_snap_gives_empty_rows(self):
        artifact = build_velocity_desk_artifact(pd.DataFrame(), as_of=ASOF)
        assert artifact["rows"] == []
        assert artifact["n_rows"] == 0
        assert artifact["schema"] == "hk_1d_velocity_desk.v1"

    def test_max_rows_respected(self):
        n = 12
        snap = _make_hk_snap(
            n, d1_macd_xup_bars=[1.0] * n, d1_from_os=[True] * n
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF, max_rows=8)
        assert len(artifact["rows"]) <= 8
        assert artifact["n_rows"] <= 8

    def test_json_serializable(self):
        """Artifact must be fully JSON-serializable."""
        snap = _make_hk_snap(
            3, d1_macd_xup_bars=[1.0, 2.0, 3.0], d1_from_os=[True, True, True]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        # Should not raise
        serialized = json.dumps(artifact)
        decoded = json.loads(serialized)
        assert decoded["schema"] == "hk_1d_velocity_desk.v1"


# ============================================================ No "validated" word ==

class TestNoValidatedWord:
    """Guard: 'validated' must not appear in user-facing output (CI-enforced)."""

    def test_no_validated_in_velocity_desk_output(self):
        snap = _make_hk_snap(
            3, d1_macd_xup_bars=[1.0, 2.0, 3.0], d1_from_os=[True, True, True]
        )
        artifact = build_velocity_desk_artifact(snap, as_of=ASOF)
        output_str = json.dumps(artifact)
        assert "validated" not in output_str, (
            "User-facing output must not contain the word 'validated' (CI-enforced)"
        )

    def test_no_validated_in_hk_snapshot_rows(self):
        rows = build_hk_core_rows(**_base_kwargs())
        output_str = json.dumps(rows, default=str)
        assert "validated" not in output_str, (
            "Snapshot rows must not contain the word 'validated' (CI-enforced)"
        )
