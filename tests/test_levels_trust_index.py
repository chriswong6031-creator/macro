"""tests/test_levels_trust_index.py — WP-C2 per-ticker Trust Index (pure aggregation)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_trust_index import compute_trust_index, SCHEMA  # noqa: E402


def _rec(root, wall, band, anchor, date="2026-07-16"):
    return {"root": root, "session_date": date,
            "wall_contained": wall, "band_contained": band, "anchor_drew": anchor}


def _boards(root, n, wall=True, band=True, anchor=True):
    return [_rec(root, wall, band, anchor, f"2026-07-{d:02d}") for d in range(1, n + 1)]


def _wilson(k, n):
    if not n:
        return None
    p = k / n
    return (max(0.0, p - 0.15), min(1.0, p + 0.15))


class TestTrustIndex:
    def test_schema_and_ranking_order(self):
        recs = _boards("GOOD", 10, True, True, True) + _boards("BAD", 10, False, False, False)
        ti = compute_trust_index(recs, ci_fn=_wilson)
        assert ti["schema"] == SCHEMA
        assert [e["root"] for e in ti["ranked"]] == ["GOOD", "BAD"]  # higher composite first
        assert ti["ranked"][0]["rank"] == 1 and ti["ranked"][1]["rank"] == 2
        assert ti["ranked"][0]["composite"] == 1.0
        assert ti["ranked"][1]["composite"] == 0.0

    def test_held_out_below_min_sessions(self):
        recs = _boards("BIG", 9) + _boards("SMALL", 3)
        ti = compute_trust_index(recs, min_sessions=8)
        assert [e["root"] for e in ti["ranked"]] == ["BIG"]
        assert [e["root"] for e in ti["banking"]] == ["SMALL"]
        assert ti["n_ranked"] == 1 and ti["n_banking"] == 1

    def test_composite_is_mean_of_components(self):
        # 10 boards: walls 100%, band 100%, anchor 0% -> composite = (1+1+0)/3
        recs = _boards("MIX", 10, wall=True, band=True, anchor=False)
        ti = compute_trust_index(recs, ci_fn=_wilson)
        e = ti["ranked"][0]
        assert e["walls_contained"]["rate"] == 1.0
        assert e["anchor_drew"]["rate"] == 0.0
        assert abs(e["composite"] - (2.0 / 3.0)) < 1e-3
        assert e["anchor_drew"]["misses"] == 10

    def test_misses_shown_and_ci_present(self):
        recs = ([_rec("T", True, True, True)] * 6) + ([_rec("T", False, False, False)] * 4)
        # give distinct dates so they're 10 boards
        recs = [_rec("T", i < 6, i < 6, i < 6, f"2026-07-{i+1:02d}") for i in range(10)]
        ti = compute_trust_index(recs, ci_fn=_wilson)
        e = ti["ranked"][0]
        assert e["walls_contained"]["misses"] == 4 and e["walls_contained"]["n"] == 10
        assert e["composite_ci"] is not None and len(e["composite_ci"]) == 2

    def test_none_components_skipped(self):
        # a ticker with only band data (walls/anchor None) still ranks on band alone
        recs = [_rec("NB", None, True, None, f"2026-07-{i+1:02d}") for i in range(9)]
        ti = compute_trust_index(recs)
        e = ti["ranked"][0]
        assert e["walls_contained"]["rate"] is None
        assert e["band_contained"]["rate"] == 1.0
        assert e["composite"] == 1.0  # mean of the one available component

    def test_least_reliable_reported(self):
        recs = _boards("HI", 9, True, True, True) + _boards("LO", 9, False, False, False)
        ti = compute_trust_index(recs)
        assert ti["least_reliable"]["root"] == "LO"

    def test_empty_input(self):
        ti = compute_trust_index([])
        assert ti["n_ranked"] == 0 and ti["ranked"] == [] and ti["least_reliable"] is None
