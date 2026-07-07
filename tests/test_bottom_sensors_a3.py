"""tests/test_bottom_sensors_a3.py — Amendment-3 structural descriptors on the
bottom-sensor envelope (decline_geometry family E display, underwater_state
family F shadow) + the shadow forward-ledger.

Load-bearing test: the TAIL-BIND EQUIVALENCE (§_decline_herf / _underwater_bars).
The display helpers compute on the last (window+1) / window closes to stay within
the render budget, then take .iloc[-1].  Because the underlying rolling apply is
POSITIONAL, that latest value must equal the FULL-series latest value exactly —
otherwise the "bind, don't recompute a variant" law (RUL-31 / §F.3) is violated.
We prove past-truncation invariance directly (the existing
tests/test_entry_primitives_a3.py already proves FUTURE-truncation invariance of
the primitives themselves).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.entry_primitives import (  # noqa: E402
    decline_concentration_series,
    time_underwater_series,
)
from engine.neuralweb.bottom_sensors import (  # noqa: E402
    _DECLINE_WINDOW,
    _UNDERWATER_WINDOW,
    _assign_terciles,
    _decline_herf,
    _underwater_bars,
)
from engine.neuralweb import bottom_sensors_shadow as BSS  # noqa: E402


# ---------------------------------------------------------------------------
# shared fixture
# ---------------------------------------------------------------------------

def _biz_close(n: int, seed: int = 42) -> pd.Series:
    """Seeded random-walk close on a business-day index of length n."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    rets = rng.standard_normal(n) * 0.02
    prices = 100.0 * np.exp(np.cumsum(rets))
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# (1) TAIL-BIND EQUIVALENCE — the load-bearing proof
# ---------------------------------------------------------------------------

class TestDeclineHerfTailBind:
    """_decline_herf(close) must equal decline_concentration_series(close).iloc[-1]
    for every as-of date — i.e. the tail(window+1) truncation is exact."""

    def test_matches_full_series_latest(self):
        close = _biz_close(1500, seed=2)
        full = decline_concentration_series(
            close, window=_DECLINE_WINDOW, min_down_days=8
        )
        rng = np.random.default_rng(7)
        # sample as-of positions in the warm region (need >= window+1 history)
        for t_idx in rng.integers(_DECLINE_WINDOW + 5, len(close), size=30):
            d = close.index[int(t_idx)]
            as_of_close = close.loc[:d]                 # only history <= d (no leak)
            helper_val = _decline_herf(as_of_close)
            full_val = full.loc[d]
            if pd.isna(full_val):
                assert helper_val is None, f"t={d}: full NaN but helper={helper_val}"
                continue
            assert helper_val is not None, f"t={d}: helper None but full={full_val}"
            assert abs(helper_val - round(float(full_val), 6)) <= 1e-6, (
                f"tail-bind mismatch t={d}: helper={helper_val} full={full_val}"
            )

    def test_short_series_returns_none(self):
        assert _decline_herf(_biz_close(_DECLINE_WINDOW, seed=1)) is None
        assert _decline_herf(None) is None

    def test_value_in_unit_interval(self):
        v = _decline_herf(_biz_close(400, seed=3))
        assert v is None or (0.0 < v <= 1.0 + 1e-9)


class TestUnderwaterBarsTailBind:
    """_underwater_bars(close) must equal time_underwater_series(close).iloc[-1]."""

    def test_matches_full_series_latest(self):
        close = _biz_close(1500, seed=4)
        full = time_underwater_series(close, window=_UNDERWATER_WINDOW)
        rng = np.random.default_rng(11)
        for t_idx in rng.integers(_UNDERWATER_WINDOW + 2, len(close), size=30):
            d = close.index[int(t_idx)]
            helper_val = _underwater_bars(close.loc[:d])
            full_val = full.loc[d]
            if pd.isna(full_val):
                assert helper_val is None, f"t={d}: full NaN but helper={helper_val}"
                continue
            assert helper_val == int(full_val), (
                f"tail-bind mismatch t={d}: helper={helper_val} full={full_val}"
            )

    def test_short_series_returns_none(self):
        assert _underwater_bars(_biz_close(_UNDERWATER_WINDOW - 1, seed=1)) is None
        assert _underwater_bars(None) is None

    def test_nonnegative_int(self):
        v = _underwater_bars(_biz_close(400, seed=5))
        assert v is None or (isinstance(v, int) and v >= 0)


# ---------------------------------------------------------------------------
# (2) cross-sectional tercile assignment
# ---------------------------------------------------------------------------

class TestAssignTerciles:
    def test_boundary_semantics(self):
        # 99 names with values 1..99; q33≈33.34, q67≈66.66 (pct 33.33/66.67).
        vals = pd.Series({f"S{i}": float(i) for i in range(1, 100)})
        out = _assign_terciles(vals, ("grind", "mixed", "flush"))
        q33 = float(np.percentile(vals.values, 33.33))
        q67 = float(np.percentile(vals.values, 66.67))
        for sym, v in vals.items():
            if v <= q33:
                assert out[sym] == "grind"
            elif v <= q67:
                assert out[sym] == "mixed"
            else:
                assert out[sym] == "flush"
        # roughly equal thirds
        counts = out.value_counts()
        assert counts["grind"] > 20 and counts["mixed"] > 20 and counts["flush"] > 20

    def test_high_value_is_flush(self):
        vals = pd.Series({f"S{i}": float(i) for i in range(1, 100)})
        out = _assign_terciles(vals, ("grind", "mixed", "flush"))
        assert out["S99"] == "flush"   # top of the cross-section = flush
        assert out["S1"] == "grind"    # bottom = grind

    def test_nan_values_are_none(self):
        vals = pd.Series({"A": 1.0, "B": np.nan, "C": 50.0})
        # only 2 computable < min_names default(30) → all None
        out = _assign_terciles(vals, ("lo", "mid", "hi"))
        assert out["B"] is None
        assert out.isna().all() or (out == None).all()  # noqa: E711

    def test_thin_cross_section_degrades_to_none(self):
        vals = pd.Series({f"S{i}": float(i) for i in range(10)})  # 10 < 30
        out = _assign_terciles(vals, ("lo", "mid", "hi"))
        assert all(v is None for v in out)

    def test_nan_preserved_with_enough_computable(self):
        vals = pd.Series({f"S{i}": float(i) for i in range(40)})
        vals["S5"] = np.nan
        out = _assign_terciles(vals, ("lo", "mid", "hi"))
        assert out["S5"] is None                # NaN value → None even when cross-section is fat
        assert out.notna().sum() == 39


# ---------------------------------------------------------------------------
# (3) shadow forward-ledger: snapshot / mature / grade
# ---------------------------------------------------------------------------

class TestShadowSnapshot:
    def test_append_and_dedup(self, tmp_path):
        p = str(tmp_path / "book.jsonl")
        recs = [
            {"symbol": "AAA", "decline_geometry": "flush", "decline_herf": 0.7,
             "underwater_state": "long", "underwater_bars": 200},
            {"symbol": "BBB", "decline_geometry": "grind", "decline_herf": 0.1,
             "underwater_state": "short", "underwater_bars": 3},
        ]
        n1 = BSS.snapshot("2026-07-06", recs, path=p)
        assert n1 == 2
        # re-run same date → idempotent (dedup by (date, symbol))
        n2 = BSS.snapshot("2026-07-06", recs, path=p)
        assert n2 == 0
        # a new date appends fresh rows
        n3 = BSS.snapshot("2026-07-07", recs, path=p)
        assert n3 == 2
        book = BSS.load_book(p)
        assert len(book) == 4
        assert set(book["symbol"]) == {"AAA", "BBB"}
        assert set(book.columns) >= {"date", "symbol", "decline_geometry",
                                     "decline_herf", "underwater_state", "underwater_bars"}

    def test_missing_symbol_skipped(self, tmp_path):
        p = str(tmp_path / "book.jsonl")
        n = BSS.snapshot("2026-07-06", [{"decline_geometry": "flush"}], path=p)
        assert n == 0

    def test_nonfinite_coerced_to_none(self, tmp_path):
        p = str(tmp_path / "book.jsonl")
        BSS.snapshot("2026-07-06", [{"symbol": "X", "decline_herf": float("nan"),
                                     "decline_geometry": None}], path=p)
        book = BSS.load_book(p)
        assert book.iloc[0]["decline_herf"] is None


class TestShadowMatureGrade:
    def _panel(self, n=120):
        idx = pd.bdate_range("2026-01-02", periods=n)
        # flush name RISES after snapshot; grind name FALLS — so grade shows a gap.
        flush = pd.Series(100.0 * np.exp(np.cumsum(np.full(n, 0.004))), index=idx)
        grind = pd.Series(100.0 * np.exp(np.cumsum(np.full(n, -0.004))), index=idx)
        return pd.DataFrame({"UP": flush, "DN": grind})

    def test_leak_guard_and_gap(self, tmp_path):
        p = str(tmp_path / "book.jsonl")
        closes = self._panel(120)
        snap_date = closes.index[10]
        BSS.snapshot(snap_date, [
            {"symbol": "UP", "decline_geometry": "flush", "underwater_state": "short"},
            {"symbol": "DN", "decline_geometry": "grind", "underwater_state": "long"},
        ], path=p, horizons=(21, 63))

        # asof only 5 bars after snapshot → NEITHER horizon has elapsed → empty
        early = BSS.mature(closes.index[15], closes, path=p, horizons=(21, 63))
        assert early.empty

        # asof at end → 21d horizon elapsed
        matured = BSS.mature(closes.index[-1], closes, path=p, horizons=(21, 63))
        assert not matured.empty
        assert set(matured["horizon"].unique()) <= {21, 63}

        g = BSS.grade(matured)
        assert g["n_matured"] == len(matured)
        h21 = g["by_horizon"]["h21"]
        gap = h21["decline_geometry"]["flush_minus_grind"]
        # flush (UP, rising) should out-return grind (DN, falling) → positive gap
        assert gap is not None and gap > 0

    def test_empty_book_grades_empty(self, tmp_path):
        p = str(tmp_path / "nope.jsonl")
        matured = BSS.mature("2026-07-06", self._panel(), path=p)
        assert matured.empty
        assert BSS.grade(matured)["n_matured"] == 0
