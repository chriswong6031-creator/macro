"""Tests for the P2.2 tape-flow stamp columns (engine/tape_flow_stamp.py).

Covers:
  * opt_net_signed_prem_5d_z:
    - min-history gate: null when fewer than 20 strictly-prior observations
    - computes correctly when history meets the gate
    - PIT: rows after the fire date are never included
  * opt_flow_breadth_group:
    - null when group coverage in the store is < 40% of expected peers
    - correct share when coverage >= 40%
  * opt_dte_quality:
    - null when the name-day row is absent
    - correct combined 8-90d vol share
  * opt_crowding_flag:
    - null when fewer than 20 strictly-prior observations
    - True when today's short-dated share >= 90th-percentile of prior history
    - False when below 90th-percentile
    - PIT: future rows are excluded from the percentile calculation
  * Schema-union: existing 8 opt_* columns preserved byte-identically after stamp pass
  * Writer gracefully handles absent tape_flow store (all-null stamp)
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.tape_flow_stamp import (  # noqa: E402
    TAPE_FLOW_STAMP_COLS,
    _MIN_HISTORY,
    _GROUP_COVERAGE_FLOOR,
    stamp_tape_flow,
    _net_signed_prem_5d_z,
    _dte_quality,
    _crowding_flag,
    _pit_rows,
)
from engine.options_stamp import STAMP_COLS  # noqa: E402
from scripts.stamp_options_state import (  # noqa: E402
    ALL_STAMP_COLS,
    stamp_ledger,
)


# ─── synthetic tape_flow frame builder ───────────────────────────────────────

def _tf_frame(
    dates: list,
    *,
    nsp: float | list = 1000.0,
    dte_0d: float = 0.05,
    dte_1_7d: float = 0.10,
    dte_8_30d: float = 0.35,
    dte_31_90d: float = 0.40,
) -> pd.DataFrame:
    """Build a synthetic tape_flow per-name DataFrame."""
    n = len(dates)
    nsp_vals = [nsp] * n if isinstance(nsp, (int, float)) else list(nsp)
    return pd.DataFrame({
        "date": [str(d)[:10] for d in dates],
        "net_signed_premium": nsp_vals,
        "dte_0d_vol_share": [dte_0d] * n,
        "dte_1_7d_vol_share": [dte_1_7d] * n,
        "dte_8_30d_vol_share": [dte_8_30d] * n,
        "dte_31_90d_vol_share": [dte_31_90d] * n,
    })


def _make_dates(n: int, end: str = "2026-07-04") -> list[_dt.date]:
    """Return a list of n consecutive dates ending on `end`."""
    end_d = _dt.date.fromisoformat(end)
    return [end_d - _dt.timedelta(days=n - 1 - i) for i in range(n)]


# ─── opt_net_signed_prem_5d_z ─────────────────────────────────────────────────

class TestNetSignedPrem5dZ:
    def test_null_when_insufficient_prior_history(self):
        """Fewer than _MIN_HISTORY strictly-prior rows → null (no fake z)."""
        dates = _make_dates(_MIN_HISTORY - 1)  # 19 dates, all before the fire
        fire = dates[-1]
        df = _tf_frame(dates, nsp=1000.0)
        pit = _pit_rows(df, fire)
        # fire date IS in the data; prior count = 18 (< 20)
        result = _net_signed_prem_5d_z(pit, fire)
        assert result is None

    def test_not_null_when_history_met(self):
        """Exactly _MIN_HISTORY strictly-prior rows + today → z computes."""
        dates = _make_dates(_MIN_HISTORY + 1)  # 21 dates: 20 prior + today
        fire = dates[-1]
        # vary nsp so std > 0
        nsp_vals = list(range(1000, 1000 + len(dates)))
        df = _tf_frame(dates, nsp=nsp_vals)
        pit = _pit_rows(df, fire)
        result = _net_signed_prem_5d_z(pit, fire)
        assert result is not None
        assert isinstance(result, float)

    def test_null_when_no_today_row(self):
        """Fire date has no row in the store → null (can't compute z for missing day)."""
        dates = _make_dates(_MIN_HISTORY + 5)
        fire = dates[-1]
        # build a frame that stops BEFORE fire
        df = _tf_frame(dates[:-1])
        pit = _pit_rows(df, fire)
        result = _net_signed_prem_5d_z(pit, fire)
        assert result is None

    def test_pit_excludes_future_rows(self):
        """Rows AFTER the fire date must never affect the z-score (PIT discipline)."""
        dates = _make_dates(_MIN_HISTORY + 10, end="2026-07-10")
        fire_idx = _MIN_HISTORY + 5  # a middle date
        fire = dates[fire_idx]

        # future rows have extreme nsp — if PIT leaks, z will be very large
        nsp_vals = [1000.0] * len(dates)
        for i in range(fire_idx + 1, len(dates)):
            nsp_vals[i] = 1_000_000.0

        df = _tf_frame(dates, nsp=nsp_vals)
        # _pit_rows filters to <= fire
        pit = _pit_rows(df, fire)
        result = _net_signed_prem_5d_z(pit, fire)
        # result must be computable (sufficient history) and must NOT be extreme
        assert result is not None
        assert abs(result) < 100.0  # an extreme z would be >> 100 if future leaked

    def test_zero_std_returns_zero(self):
        """Flat nsp series → rolling std = 0 → z returned as 0.0 (not NaN/None)."""
        dates = _make_dates(_MIN_HISTORY + 5)
        fire = dates[-1]
        df = _tf_frame(dates, nsp=5000.0)  # all identical
        pit = _pit_rows(df, fire)
        result = _net_signed_prem_5d_z(pit, fire)
        # flat series: std=0 → 0.0
        assert result == pytest.approx(0.0)


# ─── opt_dte_quality ──────────────────────────────────────────────────────────

class TestDteQuality:
    def test_absent_fire_date_is_null(self):
        dates = _make_dates(10)
        fire = dates[-1]
        df = _tf_frame(dates[:-1])  # no row for fire date
        pit = _pit_rows(df, fire)
        assert _dte_quality(pit, fire) is None

    def test_correct_combined_share(self):
        dates = _make_dates(5)
        fire = dates[-1]
        df = _tf_frame(dates, dte_8_30d=0.35, dte_31_90d=0.40)
        pit = _pit_rows(df, fire)
        result = _dte_quality(pit, fire)
        assert result == pytest.approx(0.75, abs=1e-6)

    def test_empty_store_is_null(self):
        fire = _dt.date(2026, 7, 4)
        result = _dte_quality(pd.DataFrame(), fire)
        assert result is None


# ─── opt_crowding_flag ────────────────────────────────────────────────────────

class TestCrowdingFlag:
    def _build_crowding_frame(self, n_prior: int, today_sdotm: float, prior_sdotm: float = 0.10):
        """Build a frame with `n_prior` prior rows + one today row."""
        dates = _make_dates(n_prior + 1)
        fire = dates[-1]
        dte_0d = prior_sdotm / 2.0
        dte_1_7d = prior_sdotm / 2.0
        nsp = [1000.0] * len(dates)
        df = _tf_frame(dates, nsp=nsp, dte_0d=dte_0d, dte_1_7d=dte_1_7d)
        # override today row
        today_idx = df.index[-1]
        df.at[today_idx, "dte_0d_vol_share"] = today_sdotm / 2.0
        df.at[today_idx, "dte_1_7d_vol_share"] = today_sdotm / 2.0
        return df, fire

    def test_null_when_insufficient_prior_history(self):
        df, fire = self._build_crowding_frame(n_prior=_MIN_HISTORY - 1, today_sdotm=0.9)
        pit = _pit_rows(df, fire)
        assert _crowding_flag(pit, fire) is None

    def test_true_when_above_p90(self):
        """Today's short-dated share clearly above the 90th percentile → True."""
        n_prior = _MIN_HISTORY + 10
        df, fire = self._build_crowding_frame(
            n_prior=n_prior,
            today_sdotm=0.90,   # very high
            prior_sdotm=0.10,   # history is low
        )
        pit = _pit_rows(df, fire)
        result = _crowding_flag(pit, fire)
        assert result is True

    def test_false_when_below_p90(self):
        """Today's short-dated share clearly below the 90th percentile → False."""
        n_prior = _MIN_HISTORY + 10
        df, fire = self._build_crowding_frame(
            n_prior=n_prior,
            today_sdotm=0.05,   # very low
            prior_sdotm=0.50,   # history is high
        )
        pit = _pit_rows(df, fire)
        result = _crowding_flag(pit, fire)
        assert result is False

    def test_pit_excludes_future(self):
        """Future rows with extreme crowding must not inflate the p90 baseline (PIT)."""
        n = _MIN_HISTORY + 20
        dates = _make_dates(n + 5, end="2026-07-10")
        fire_idx = n - 1
        fire = dates[fire_idx]

        dte_0d = [0.05] * len(dates)
        dte_1_7d = [0.05] * len(dates)
        # future rows have extreme share (if PIT leaks, p90 inflates and today < p90)
        for i in range(fire_idx + 1, len(dates)):
            dte_0d[i] = 0.99
            dte_1_7d[i] = 0.00

        nsp = [1000.0] * len(dates)
        df = pd.DataFrame({
            "date": [str(d)[:10] for d in dates],
            "net_signed_premium": nsp,
            "dte_0d_vol_share": dte_0d,
            "dte_1_7d_vol_share": dte_1_7d,
            "dte_8_30d_vol_share": [0.35] * len(dates),
            "dte_31_90d_vol_share": [0.40] * len(dates),
        })
        # fire date: high today_sdotm so it should be in top decile IF future is excluded
        df.at[fire_idx, "dte_0d_vol_share"] = 0.50
        df.at[fire_idx, "dte_1_7d_vol_share"] = 0.40

        pit = _pit_rows(df, fire)
        result = _crowding_flag(pit, fire)
        # future rows are excluded; prior history all had 0.10 total → today 0.90 >> p90 → True
        assert result is True

    def test_null_when_no_today_row(self):
        n_prior = _MIN_HISTORY + 5
        dates = _make_dates(n_prior + 1)
        fire = dates[-1]
        df = _tf_frame(dates[:-1])
        pit = _pit_rows(df, fire)
        assert _crowding_flag(pit, fire) is None


# ─── opt_flow_breadth_group ───────────────────────────────────────────────────

class TestFlowBreadthGroup:
    def _make_reader(self, members: dict[str, pd.DataFrame | None]):
        """Injectable reader that returns synthetic frames keyed by ticker."""
        def _read(root: str) -> pd.DataFrame | None:
            return members.get(root.upper())
        return _read

    def test_null_when_no_group_members(self):
        result = stamp_tape_flow("2026-07-04", "AAPL", sector="Tech", group_members=[],
                                 read_tape_flow=lambda r: None)
        assert result["opt_flow_breadth_group"] is None

    def test_null_when_coverage_below_floor(self):
        """Only 1 of 4 expected members present → 25% < 40% → null."""
        fire_date = "2026-07-04"
        dates = [_dt.date(2026, 7, 4)]
        frames = {
            "AAPL": _tf_frame(dates, nsp=1000.0),
        }
        result = stamp_tape_flow(
            fire_date, "AAPL",
            sector="Tech",
            group_members=["AAPL", "MSFT", "GOOGL", "AMZN"],  # 4 members, only 1 in store
            read_tape_flow=self._make_reader(frames),
        )
        assert result["opt_flow_breadth_group"] is None

    def test_correct_breadth_above_floor(self):
        """3 of 3 members present (100% coverage); 2 positive → breadth = 2/3."""
        fire_date = "2026-07-04"
        dates = [_dt.date(2026, 7, 4)]
        frames = {
            "AAPL": _tf_frame(dates, nsp=1000.0),   # positive
            "MSFT": _tf_frame(dates, nsp=-500.0),    # negative
            "GOOGL": _tf_frame(dates, nsp=200.0),    # positive
        }
        result = stamp_tape_flow(
            fire_date, "AAPL",
            sector="Tech",
            group_members=["AAPL", "MSFT", "GOOGL"],
            read_tape_flow=self._make_reader(frames),
        )
        assert result["opt_flow_breadth_group"] == pytest.approx(2 / 3, abs=1e-6)

    def test_breadth_pit_no_future_data(self):
        """Group breadth uses only tape_flow data for the fire date (PIT for group-level)."""
        fire_date = "2026-07-04"
        fire_d = _dt.date.fromisoformat(fire_date)

        # AAPL: fire date row positive; future date also positive (should not matter)
        aapl_dates = [fire_d, _dt.date(2026, 7, 5)]
        aapl_nsp = [1000.0, -9999.0]

        frames = {
            "AAPL": _tf_frame(aapl_dates, nsp=aapl_nsp),
            "MSFT": _tf_frame([fire_d], nsp=-100.0),
        }
        result = stamp_tape_flow(
            fire_date, "AAPL",
            sector="Tech",
            group_members=["AAPL", "MSFT"],
            read_tape_flow=self._make_reader(frames),
        )
        # fire date: AAPL positive, MSFT negative → 1/2 = 0.5
        assert result["opt_flow_breadth_group"] == pytest.approx(0.5, abs=1e-6)


# ─── stamp_tape_flow: absent store → all-null ─────────────────────────────────

def test_absent_store_returns_null_stamp():
    """When the tape_flow store has no data for a name, stamp is all-None."""
    result = stamp_tape_flow(
        "2026-07-04", "NOCOV",
        read_tape_flow=lambda r: None,
    )
    assert set(result.keys()) == set(TAPE_FLOW_STAMP_COLS)
    assert all(v is None for v in result.values())


def test_stamp_always_has_all_columns():
    """Every call returns a dict with exactly the four P2.2 keys (no extras, no missing)."""
    result = stamp_tape_flow(
        "2026-07-04", "ANY",
        sector="Industrials",
        group_members=["ANY"],
        read_tape_flow=lambda r: None,
    )
    assert set(result.keys()) == set(TAPE_FLOW_STAMP_COLS)


# ─── schema-union: existing 8 W1.3 opt_* columns preserved byte-identically ───

def test_schema_union_preserves_existing_stamp_cols():
    """The stamp_ledger pass adds 4 new columns but NEVER modifies existing W1.3 columns.

    Fixture: a ledger with the 8 existing W1.3 opt_* columns pre-filled with sentinel
    values. After stamp_ledger runs, those values must be byte-identical.
    """
    sentinel = {
        "opt_gamma_regime": "long",
        "opt_dist_to_flip_pct": 7.77,
        "opt_wall_up": 222.0,
        "opt_wall_down": 198.0,
        "opt_iv30": 0.333,
        "opt_iv_rank_252": None,   # always null (A9)
        "opt_doi_slope_5d": 0.0042,
        "opt_voi_flag": True,
    }
    row = {
        "as_of": "2026-07-04",
        "ticker": "TSST",
        "sector": "Industrials",
        "lane": "buy",
        "horizon": 21,
        **sentinel,
        # tape-flow cols absent → schema-union adds them
    }
    df = pd.DataFrame([row])
    out, n_newly = stamp_ledger(df)

    # 4 new columns added
    for col in TAPE_FLOW_STAMP_COLS:
        assert col in out.columns

    # ALL 8 existing W1.3 values preserved exactly
    for col, expected in sentinel.items():
        actual = out.at[0, col]
        if expected is None:
            assert actual is None or (isinstance(actual, float) and np.isnan(actual))
        elif isinstance(expected, bool):
            assert bool(actual) == expected
        elif isinstance(expected, float):
            assert actual == pytest.approx(expected)
        else:
            assert actual == expected

    # row was already stamped (non-null W1.3 values) → not re-stamped
    assert n_newly == 0


def test_schema_union_empty_ledger_no_crash():
    """stamp_ledger on an empty DataFrame returns (empty, 0) without error."""
    df = pd.DataFrame()
    out, n = stamp_ledger(df)
    assert n == 0
    assert out.empty


# ─── writer graceful null stamp for absent tape_flow store ────────────────────

def test_writer_graceful_absent_tape_flow_store(tmp_path, monkeypatch):
    """Full writer pass with absent tape_flow store: new cols present, all null for new rows."""
    # Patch out the chain/summary readers from options_stamp (no options coverage either)
    import engine.options_stamp as _os
    monkeypatch.setattr(_os, "_default_chain_dates", lambda: [])
    monkeypatch.setattr(_os, "_default_read_summary", lambda t: None)
    monkeypatch.setattr(_os, "_default_read_chain", lambda d: None)

    # Patch tape_flow reader to return None for all roots
    import engine.tape_flow_stamp as _tfs
    monkeypatch.setattr(_tfs, "_default_read_tape_flow", lambda r: None)

    df = pd.DataFrame({
        "as_of": ["2026-07-04", "2026-07-04"],
        "ticker": ["AAPL", "MSFT"],
        "sector": ["Tech", "Tech"],
        "lane": ["buy", "buy"],
        "horizon": [21, 21],
    })

    out, n_newly = stamp_ledger(df)

    # All P2.2 columns present
    for col in TAPE_FLOW_STAMP_COLS:
        assert col in out.columns

    # All W1.3 columns present
    for col in STAMP_COLS:
        assert col in out.columns

    # All stamp cols null (no coverage from either store)
    for col in ALL_STAMP_COLS:
        assert out[col].isna().all(), f"{col} should be null for absent stores"

    # No rows counted as stamped (all-null → not applied)
    assert n_newly == 0
