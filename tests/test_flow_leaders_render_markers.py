"""Doctrine-marker regression test for the Flow Leaders page render.

Pins the #3224 user-first revamp at the RENDERED-OUTPUT level: the dot-ladder
signature and plain-word EN/ZH leg copy must come out of the template, and the
pre-#3224 machine slugs (`TSBrd`, `NotTrap`, `PriceOK`, `FlowZ`) must not.

Why output-level: the live page shipped the banned-vocab slug wall for 3 days
(2026-07-22..25) while the template was already compliant — the baked artifact,
not the template, is what users see. This test renders the real template with a
synthetic payload so a regression in either the template or its payload contract
fails loudly, with no dependency on repo data stores.
"""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BANNED_SLUGS = ("TSBrd", "NotTrap", "PriceOK", "FlowZ")


def _row_a(ticker: str = "NVDA") -> dict:
    return {
        "ticker": ticker,
        "sector": "Technology",
        "fire_a": True,
        "recurrence_count": 5,
        "days_since_inflection": None,
        "de_escalation": None,
        "signing_source": "tape",
        "zerodte_dominated": False,
        # A-board ladder legs: one lit, one dark, one null — exercises all three
        # segment states of the ladder macro.
        "A1_flow_recur": True,
        "A2_flow_z_hot": True,
        "A3_oi_confirmed": True,
        "A4_ts_breadth": False,
        "A5_price_leader": True,
        "A6_near_high": True,
        "A7_vol_confirm": None,
        "A8_not_trap": True,
    }


def _row_b(ticker: str = "AMD") -> dict:
    return {
        "ticker": ticker,
        "sector": "Technology",
        "fire_b": True,
        "recurrence_count": 2,
        "days_since_inflection": 2,
        "de_escalation": None,
        "signing_source": "tape",
        "zerodte_dominated": False,
        "B1_washout_recent": True,
        "B2_oversold_osc": True,
        "B3_turn_organ": True,
        "B5_flow_inflect": True,
        "B6_oi_confirmed": False,
        "B7_vol_confirm": None,
        "B8_not_trap": True,
    }


def _render(payload: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    return env.get_template("flow_leaders.html.j2").render(flow_leaders=payload)


def _payload() -> dict:
    return {
        "as_of": "2026-07-25",
        "stale": False,
        "coverage": {
            "n_universe": 2,
            "n_flow_sessions": 134,
            "flow_z_live": True,
            "tape_names": 2,
            "n_etfs": 1,
        },
        "board_a": [_row_a()],
        "board_a_total": 1,
        "board_b": [_row_b()],
        "board_b_total": 1,
        "etf_strip": [{"ticker": "SPY", "net_premium_mn": 12.5, "zerodte_share": 0.4}],
        "cold_start_detail": {
            "n_sessions": 134,
            "required_for_recurrence": 20,
            "message": None,
        },
    }


def test_render_carries_dot_ladder_signature():
    html = _render(_payload())
    assert 'class="ladder"' in html, "#3224 dot-ladder signature missing from render"
    assert 'class="seg seg-on"' in html, "lit ladder segment missing"
    assert 'class="seg seg-off"' in html, "dark ladder segment missing"
    assert 'class="seg seg-nul"' in html, "null ladder segment missing"


def test_render_carries_plain_word_leg_copy():
    html = _render(_payload())
    # Tier-2 receipt copy, EN + ZH (user-first doctrine: no machine slugs on glance).
    assert "Money keeps showing up" in html
    assert "资金反复出现" in html
    assert "Not a failed breakout" in html
    assert "Money flipped positive" in html


def test_render_has_no_banned_machine_slugs():
    html = _render(_payload())
    for slug in BANNED_SLUGS:
        assert slug not in html, f"banned pre-#3224 machine slug {slug!r} in render"


def test_render_survives_empty_boards():
    # Absent-safe: an empty payload must still render (honest-null page), not crash.
    html = _render({})
    assert "<html" in html
    for slug in BANNED_SLUGS:
        assert slug not in html


# ---------------------------------------------------------------------------
# OEU bug-wave F3-18 — the page stamp renders the underlying SESSION, not the
# build's wall-clock timestamp (which can be a weekend/holiday date while
# every board row describes the last real NYSE session).
# ---------------------------------------------------------------------------

def test_render_prefers_session_date_over_as_of_for_the_stamp():
    payload = _payload()
    payload["as_of"] = "2026-07-26T14:36:28+00:00"   # a Sunday build timestamp
    payload["session_date"] = "2026-07-24"            # the Friday session the boards describe
    html = _render(payload)
    assert '<span class="num">2026-07-24</span>' in html
    assert "2026-07-26" not in html


def test_render_falls_back_to_as_of_when_session_date_absent():
    """Backward-compat: an older payload shape (no session_date key at all)
    must still render something, not a blank stamp."""
    payload = _payload()
    payload["as_of"] = "2026-07-25T09:00:00+00:00"
    assert "session_date" not in payload
    html = _render(payload)
    assert '<span class="num">2026-07-25</span>' in html
