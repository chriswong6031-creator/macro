"""tests/test_us_board_continuity_guard.py — CSP-W5b board-continuity guard.

_board_continuity_warning compares the previous us_standouts.json (loaded
before overwrite) against the fresh build. Two builds stamping the SAME as_of
that produce materially different buy lanes read different data vintages —
2026-08-03→05 the lane swung 55↔76 names (VALE present in 7/7 stale-vintage
builds, 0/15 fresh-vintage) across 22 builds all claiming as_of=2026-07-31,
with zero disclosure. The guard is warn-only display-tier: it returns a
line-start ::warning string (printed BARE with flush=True at the call site —
repo annotation law) and never gates or edits the artifact.
"""
from __future__ import annotations

import pytest

from scripts.build_stock_library import (
    _BOARD_CONTINUITY_JACCARD_MIN,
    _BOARD_CONTINUITY_MIN_NAMES,
    _board_continuity_warning,
)


def _doc(as_of: str | None, tickers: list[str], price_through: str | None = None,
         panel_majority: str | None = None) -> dict:
    doc: dict = {"as_of": as_of,
                 "buy": [{"ticker": t, "name": t} for t in tickers]}
    if price_through or panel_majority:
        doc["staleness"] = {
            "price_through": price_through,
            "inputs": {"panel": {"majority_through": panel_majority}},
        }
    return doc


_ASOF = "2026-07-31"
# 12 shared names + per-side uniques → jaccard tunable below/above 0.90
_SHARED = [f"KEEP{i}" for i in range(12)]


class TestFires:
    def test_material_flip_at_same_as_of_warns(self):
        """The measured 2026-08-04 shape: same as_of, ~0.73 jaccard → warning."""
        prev = _doc(_ASOF, _SHARED + ["VALE", "OLD1", "OLD2", "OLD3"],
                    price_through="2026-07-31", panel_majority="2026-07-31")
        cur = _doc(_ASOF, _SHARED + ["NEW1", "NEW2"],
                   price_through="2026-08-03", panel_majority="2026-07-31")
        msg = _board_continuity_warning(prev, cur)
        assert msg is not None
        # Repo annotation law: the string IS the line — it must start with ::
        assert msg.startswith("::warning title=us-board-continuity::")
        assert "16->14" in msg
        assert "as_of=2026-07-31" in msg
        # flipped names are listed for forensics
        assert "VALE" in msg and "NEW1" in msg
        # both builds' disclosed reach is embedded so the cause is readable
        assert "price_through=2026-07-31" in msg
        assert "price_through=2026-08-03" in msg

    def test_disjoint_lanes_warn(self):
        prev = _doc(_ASOF, [f"A{i}" for i in range(10)])
        cur = _doc(_ASOF, [f"B{i}" for i in range(10)])
        msg = _board_continuity_warning(prev, cur)
        assert msg is not None
        assert "jaccard=0.00" in msg

    def test_missing_staleness_block_still_warns(self):
        """Pre-CSP-W5b artifacts (no staleness.inputs) must not crash the guard."""
        prev = _doc(_ASOF, _SHARED + ["OLD1", "OLD2", "OLD3", "OLD4"])
        cur = _doc(_ASOF, _SHARED[:8])
        msg = _board_continuity_warning(prev, cur)
        assert msg is not None
        assert "price_through=None" in msg

    def test_flip_list_truncates_with_count(self):
        prev = _doc(_ASOF, _SHARED + [f"OLD{i}" for i in range(9)])
        cur = _doc(_ASOF, _SHARED + [f"NEW{i}" for i in range(9)])
        msg = _board_continuity_warning(prev, cur)
        assert msg is not None
        # 9 added + 9 dropped, 8 shown → "+10 more"
        assert "+10 more" in msg


class TestHolds:
    def test_high_jaccard_is_quiet(self):
        """Normal same-day re-render drift (>= 0.90) stays silent."""
        prev = _doc(_ASOF, _SHARED + ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8"])
        cur = _doc(_ASOF, _SHARED + ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "Y1"])
        # jaccard = 19/21 ≈ 0.905
        assert _board_continuity_warning(prev, cur) is None

    def test_exact_threshold_is_quiet(self):
        """Boundary: jaccard == threshold does not warn (rule is strictly below)."""
        prev = _doc(_ASOF, [f"K{i}" for i in range(18)] + ["P1"])
        cur = _doc(_ASOF, [f"K{i}" for i in range(18)] + ["C1"])
        # jaccard = 18/20 = 0.90 exactly
        assert _board_continuity_warning(prev, cur) is None

    def test_different_as_of_is_quiet(self):
        """A new session legitimately reshapes the lane — no warning."""
        prev = _doc("2026-07-30", _SHARED + ["OLD1", "OLD2", "OLD3", "OLD4"])
        cur = _doc(_ASOF, _SHARED[:6])
        assert _board_continuity_warning(prev, cur) is None

    def test_missing_prev_is_quiet(self):
        assert _board_continuity_warning(None, _doc(_ASOF, _SHARED)) is None
        assert _board_continuity_warning({}, _doc(_ASOF, _SHARED)) is None

    def test_missing_as_of_is_quiet(self):
        assert _board_continuity_warning(_doc(None, _SHARED), _doc(_ASOF, _SHARED)) is None
        assert _board_continuity_warning(_doc(_ASOF, _SHARED), _doc(None, _SHARED)) is None

    def test_tiny_lanes_are_quiet(self):
        """Below the size floor, set overlap is too coarse to judge."""
        prev = _doc(_ASOF, ["A", "B"])
        cur = _doc(_ASOF, ["C", "D"])
        assert max(len(prev["buy"]), len(cur["buy"])) < _BOARD_CONTINUITY_MIN_NAMES
        assert _board_continuity_warning(prev, cur) is None

    def test_empty_lanes_are_quiet(self):
        assert _board_continuity_warning(_doc(_ASOF, []), _doc(_ASOF, [])) is None

    def test_garbage_rows_never_raise(self):
        """Malformed rows are skipped by the set builder, never fatal."""
        prev = {"as_of": _ASOF, "buy": ["not-a-dict", {"noticker": 1}, None]}
        cur = {"as_of": _ASOF, "buy": 42}  # not even a list
        assert _board_continuity_warning(prev, cur) is None


class TestThresholdCalibration:
    def test_threshold_separates_measured_populations(self):
        """Measured 2026-08-03→05: same-vintage adjacent builds >= 0.95, cross-
        vintage flips <= 0.87. The constant must sit strictly between, else the
        guard either flags every re-render or misses every real flip."""
        assert 0.87 < _BOARD_CONTINUITY_JACCARD_MIN <= 0.95
