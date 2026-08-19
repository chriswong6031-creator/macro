"""P-MP1-SHELL groundwork (MP-1-prophet-board.md §8, "count plumbing").

This packet's central act — re-sourcing the US Prophet "Setups" card grid to the
plan book (site/prophet/index.json.plans) and building the lifecycle ladder — is
BLOCKED (see the worker report attached to this commission): the DESIGN_NOTES §7
spawn gate G-D ("plan-book enrichment... for the full universe") is unmet on the
live payload (name/sector/spark board_read coverage is 43/250 = 17%, not the full
universe), and the `.mx-mark`/`.mx-cap` weight-grammar primitives Amendment 1
classifies as an "inherited DS-PR-0 primitive" (gate G-B) do not exist in
templates/theme.css or anywhere else in templates/.

Only the two independently-safe, non-blocked pieces of §8's "count plumbing" line
item shipped this session:
  1. action_board() now publishes a single `total` field — the sum of its six
     urgency lanes — so _us_act_now_board.html.j2's header can quote a published
     count instead of re-deriving one from row iteration (the estate's count law).
  2. main() loads site/prophet/index.json (when present) into vm["us_prophet_book"],
     fail-soft like every other board load in build_site.py, as the future entry
     point for the blocked work once G-D/G-B are resolved. No template consumes
     this key yet, so it is a data-only addition with zero rendered-byte effect.

This file pins #1 (a pure function, easy to test in isolation). #2 is a fail-soft
IO-load block inside main() with no standalone function boundary; its behavior is
implicitly covered by every existing build_site smoke/render test continuing to
pass with the new key threaded through (see test_dashboard_template_render.py,
test_action_board_lane_split.py, test_us_act_now.py — all green against this
change, evidence in the worker report).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.build_site as bs  # noqa: E402


def _sector_timing(fund: str, urgency: str, tag: str = "") -> dict:
    return {fund: {
        "label": "TEST",
        "entry": {"urgency": urgency, "tag": tag, "text": "", "days_hi": None},
        "age_short": None, "age_short_zh": None,
        "eq_badge": None, "eq_dir": "flat", "eq_tip": None, "state_style": None,
    }}


def test_action_board_total_sums_every_lane():
    """`total` must equal the sum of all six urgency lanes — never a re-derivation
    the template could disagree with (P-MP1-SHELL §8 count-plumbing law)."""
    st = {}
    st.update(_sector_timing("XLK", "now"))
    st.update(_sector_timing("XLC", "imminent"))
    st.update(_sector_timing("XLY", "hold"))
    st.update(_sector_timing("XLF", "exit"))
    st.update(_sector_timing("XLI", "caution", "DON'T CHASE"))
    st.update(_sector_timing("XLV", "caution", "UNCONFIRMED — HIGH RISK"))
    board = bs.action_board(st, [])
    lanes = ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid")
    assert board["total"] == sum(len(board[lane]) for lane in lanes)
    assert board["total"] == 6


def test_action_board_total_present_and_zero_on_empty_board():
    """An empty board still publishes `total` (0), never an absent key — the
    template's `action_board.get('total') is number` guard depends on this."""
    board = bs.action_board({}, [])
    assert board["total"] == 0
    for lane in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        assert board[lane] == []


def test_action_board_total_folds_in_basket_items():
    """basket_items rows (narrative baskets) count toward `total` exactly like
    sector rows — the header total must not undercount by reading only sectors."""
    bi = {"buy_now": [{"ticker": "AIQ", "kind": "theme"}], "more": {}}
    board = bs.action_board({}, [], basket_items=bi)
    assert board["total"] == 1
    assert board["buy_now"][0]["ticker"] == "AIQ"
