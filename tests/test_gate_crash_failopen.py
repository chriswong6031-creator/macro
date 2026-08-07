"""Audit F2/F5/F7 guards (2026-08-06) — a crashed cascade must never admit.

F2: `confluence_tiers.cascade`'s exception blank used to assert not_topped=True +
ticks=None, which `signal_gate.gate` read as clean-and-fresh and awarded a forming
'pending' master T1 at weight 0.9 — a data failure INVERTED into a buyable verdict.
The fix is the `evaluated` flag; these tests are the mutation pins that keep it
load-bearing (each asserts both the fixed behaviour AND that the pre-fix shape
still admits, so deleting the flag check fails loudly here, not in production).

F5: the crash blank's young_history=None ("never got that far") was bool()'d into
False — stamping a never-tiered name into the MATURE graded cohort (era law).

F7: one NaN conviction base left blend_sorted's percentile pool unsorted — the NaN
row ranked FIRST and every row's bisect percentile was corrupted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine import confluence_tiers as ct  # noqa: E402
from engine import signal_gate as sg  # noqa: E402


def _series(n: int = 500) -> pd.Series:
    idx = pd.bdate_range("2020-01-01", periods=n)
    x = np.arange(n, dtype=float)
    return pd.Series(120.0 + 6.0 * np.sin(x / 11.0) + 2.0 * np.sin(x / 5.0), index=idx)


def _pending_result(series: pd.Series) -> dict:
    """A §7 pending-buy payload whose marker sits ON the series' last bar (fresh —
    a stale marker date trips the held-staleness gate before the pending branch)."""
    last = str(series.index[-1].date())
    return {
        "markers": [{"type": "buy", "quality": "pending", "date": last}],
        "state": "long", "above200": True, "weekly_bull": True,
        "early_now": False, "asof": last,
    }


class TestF2CrashIsNotABuy:
    def test_cascade_exception_blank_carries_evaluated_false(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(ct, "_tf_bars", _boom)
        out = ct.cascade(_series())
        assert out["evaluated"] is False
        assert out["tier"] is None and out["eligible"] is False
        # the blank still carries the historical shape the gate used to misread
        assert out["not_topped"] is True and out["ticks"] is None

    def test_gate_refuses_pending_t1_when_cascade_crashed(self, monkeypatch):
        px = _series()
        monkeypatch.setattr(sg, "analyze", lambda *a, **k: _pending_result(px))
        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(ct, "_tf_bars", _boom)
        v = sg.gate("TEST", px)
        assert v.get("tier_cascade") is None, "crashed cascade must never award T1"
        assert not sg.is_buyable(v), "a data failure is not an admission"

    def test_mutation_pin_pre_fix_shape_still_admits(self, monkeypatch):
        """The flag is LOAD-BEARING: the same blank with evaluated=True (the pre-fix
        reading) must still produce the buyable T1 — so removing the evaluated check
        flips THIS assertion, not just the one above."""
        px = _series()
        monkeypatch.setattr(sg, "analyze", lambda *a, **k: _pending_result(px))
        healthy_blank = dict(ct._BLANK, null_legs={})          # evaluated=True default
        monkeypatch.setattr(ct, "cascade", lambda *a, **k: dict(healthy_blank))
        v = sg.gate("TEST", px)
        assert v.get("tier_cascade") == "T1" and sg.is_buyable(v), (
            "fixture drift: the pre-fix path no longer admits — the crash test above "
            "would be vacuous; re-derive the pending fixture")


class TestF5YoungHistoryCohort:
    def test_crash_leaves_young_history_none_not_false(self, monkeypatch):
        px = _series()
        monkeypatch.setattr(sg, "analyze", lambda *a, **k: _pending_result(px))
        def _boom(*a, **k):
            raise RuntimeError("store exploded")
        monkeypatch.setattr(ct, "_tf_bars", _boom)
        v = sg.gate("TEST", px)
        assert v["young_history"] is None, (
            "a never-tiered name must not be stamped into the mature cohort")

    def test_real_booleans_still_pass_through(self, monkeypatch):
        px = _series()
        monkeypatch.setattr(sg, "analyze", lambda *a, **k: _pending_result(px))
        for flag in (True, False):
            monkeypatch.setattr(
                ct, "cascade",
                lambda *a, _f=flag, **k: dict(ct._BLANK, null_legs={}, young_history=_f))
            v = sg.gate("TEST", px)
            assert v["young_history"] is flag


class TestF7NaNPercentile:
    def test_nan_base_ranks_last_not_first(self):
        items = [("A", 1.0), ("B", float("nan")), ("C", 3.0), ("D", 2.0)]
        verdicts = {k: {"eligible": True, "weight": 1.0} for k, _ in items}
        out = sg.blend_sorted(
            items,
            base_of=lambda x: x[1],
            verdict_of=lambda x: verdicts[x[0]],
        )
        order = [k for k, _ in out]
        assert order[0] == "C", f"highest real base must rank first, got {order}"
        assert order == ["C", "D", "A", "B"], (
            "NaN base must rank AS 0.0 (last among positives), never first")
