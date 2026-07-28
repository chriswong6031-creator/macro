"""CN standout board — the 110-cap overflow must land in a visible `watch` lane.

2026-07-28 finding: build_china_library.main() cut the buy lane with a flat
``eligible_rows[:110]`` slice. The live artifact that day carried eligible=156 and
buy=110 — 46 names that PASSED the same confluence gate appeared NOWHERE on the
page or in the artifact. The RIPENING and RAN arrays cannot absorb them: both
exclude gate-eligible names by construction (a W1-B invariant asserts ripening
rows are never gate-eligible), so the overflow was silently dropped, not demoted.

Fix = an additive ``watch`` lane, mirroring the US board's watch routing
(scripts/build_stock_library.py, W6-US fix 6). The cap is page width, not a
quality bar, and `buy` deliberately keeps its width: it feeds the board-ORDER
forward ledger (china_standout_track.append_board) and the bot:china_book
consumer, so widening it would be a promotion-adjacent change.

Run: .venv/bin/python -m pytest tests/test_china_board_watch_lane.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_china_library as bcl  # noqa: E402


def _rows(n: int) -> list[dict]:
    """Minimal rank-ordered row dicts — only the identity the lane split preserves."""
    return [{"ticker": f"{600000 + i}.SS", "rank": i} for i in range(n)]


def test_overflow_lands_in_watch_and_nothing_is_dropped():
    """156 eligible (the 2026-07-28 live count) → 110 buy + 46 watch, loss-free."""
    rows = _rows(156)
    buy, watch = bcl._split_board_lanes(rows)

    assert len(buy) == 110
    assert len(watch) == 46
    # loss-free AND order-preserving: concatenating the lanes reconstructs the input
    # exactly, by identity — no row copied, re-sorted, or dropped.
    assert buy + watch == rows
    assert all(a is b for a, b in zip(buy + watch, rows))
    # disjoint: every eligible row is in exactly one lane
    buy_ids, watch_ids = {id(r) for r in buy}, {id(r) for r in watch}
    assert not (buy_ids & watch_ids)
    assert len(buy_ids | watch_ids) == len(rows)


def test_under_cap_leaves_watch_empty():
    rows = _rows(80)
    buy, watch = bcl._split_board_lanes(rows)
    assert buy == rows
    assert watch == []


def test_exactly_at_cap_leaves_watch_empty():
    rows = _rows(bcl.BOARD_BUY_CAP)
    buy, watch = bcl._split_board_lanes(rows)
    assert len(buy) == bcl.BOARD_BUY_CAP
    assert watch == []


def test_empty_input():
    assert bcl._split_board_lanes([]) == ([], [])


def test_board_cap_is_pinned_at_110():
    """Widening the board is a DELIBERATE act, never an incidental edit.

    `buy` width feeds china_standout_track.append_board (the board-ORDER forward
    ledger, whose history is only comparable at a constant width) and the
    bot:china_book consumer. Changing this constant must update this test AND
    re-check both consumers — the watch lane exists precisely so display pressure
    never has to move it.
    """
    assert bcl.BOARD_BUY_CAP == 110


def test_watch_is_declared_optional_in_the_artifact_contract():
    """Contract side: watch is emitted by every build from schema 1.2.0 on, but is
    declared OPTIONAL — the committed pre-rebuild china_standouts.json has no watch
    key, and a required field would read as removed-drift on the main heartbeat
    until the next nightly turns the artifact over."""
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST

    entry = next(e for e in ARTIFACT_MANIFEST
                 if e["artifact"] == "site/factordata/china_standouts.json")
    assert entry["schema_version"] == "1.2.0"
    assert "watch" in (entry.get("optional_fields") or [])
    # optional by design until artifact turnover — NOT a required top-level key
    assert "watch" not in entry["schema_fields"]
