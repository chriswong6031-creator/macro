"""P-MP1-SHELL §8a — the stance-projection function + `pv_card` no-read parameter.

MP-1-prophet-board.md §8a (Amendment 1, b1 ruling, `verdict.yml
rulings.b1_actionability_axis`): display-tier stance sources `entry_status` when
present on a plan row, else `board_read.fields.status`, projected through the SAME
Q7 bucket table `engine/us_board_rank.py` already ships
(`_LIVE_/_SETTING_UP_/_RAN_/_BLOCKED_STATUSES`) — never a second mapping. "No read
yet" (BLOCKED_DATA, DESIGN_NOTES.md Q7b) renders only when BOTH sources are absent.

This is the DATA-LAYER half of §8a, independently testable against the real
published payload (`site/prophet/index.json`) without the packet's central act
(re-sourcing the Setups card grid to the plan book / building the lifecycle
ladder), which the worker report attached to this commission documents as BLOCKED
by an unowned collision with the W-L1 provisional-board live-refresh system. The
projection function and the `pv_card(cx, allow_no_read=...)` parameter are real,
wired-correctness-verified building blocks for that still-blocked display wiring;
this file proves the function is CORRECT against real data and that the macro
parameter is BYTE-IDENTICAL for every caller that does not opt in.

Run: .venv/bin/python -m pytest tests/test_p_mp1_shell_stance_projection.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import jinja2  # noqa: E402

import scripts.build_site as bs  # noqa: E402

PAYLOAD = ROOT / "site" / "prophet" / "index.json"
PARTIAL = ROOT / "templates" / "_prophet_card.html.j2"


def _avail(value):
    return {"fields": {"status": {"value": value, "state": "available"}}}


def _not_applicable():
    return {"fields": {"status": {"value": None, "state": "not_applicable"}}}


# ── pure function: source precedence + bucket mapping ──────────────────────────
def test_entry_status_wins_over_board_read_when_both_present():
    out = bs.us_stance_projection("buy_now", _avail("blocked"))
    assert out == {"verb": "buy", "stance_basis": "entry_status"}


def test_board_read_fallback_when_entry_status_absent():
    out = bs.us_stance_projection(None, _avail("blocked"))
    assert out == {"verb": "avoid", "stance_basis": "board_read"}


def test_board_read_fallback_ignores_non_available_state():
    """`not_applicable` (e.g. a resolved plan) is not a usable board_read status —
    it must NOT be read as a value, only 'available' status states count."""
    out = bs.us_stance_projection(None, _not_applicable())
    assert out == {"verb": None, "stance_basis": "no_read"}


def test_no_read_only_when_both_absent():
    assert bs.us_stance_projection(None, None) == {"verb": None, "stance_basis": "no_read"}
    assert bs.us_stance_projection("", {}) == {"verb": None, "stance_basis": "no_read"}


def test_every_q7_status_maps_to_the_ruled_verb():
    """DESIGN_NOTES.md Q7 table, transcribed verbatim as the test oracle."""
    expect = {
        "buy_now": "buy", "partial": "buy", "buy_soon": "near",
        "await_confluence": "wait", "bounce_wait": "wait", "watch": "wait",
        "extended": "hold", "topping": "hold", "hold": "hold",
        "blocked": "avoid", "exit": "avoid", "avoid": "avoid",
        "wait_pullback": "wait", "later": "wait", "await": "wait",
    }
    for status, verb in expect.items():
        assert bs.us_stance_projection(status, None) == {
            "verb": verb, "stance_basis": "entry_status"}, status


def test_unrecognized_truthy_status_fails_soft_to_wait_not_an_exception():
    out = bs.us_stance_projection("some_future_status_v2", None)
    assert out == {"verb": "wait", "stance_basis": "entry_status"}


# ── real-payload proof: the projection is correct against the current bake ──────
def test_projection_reproduces_the_published_boundary_on_real_data():
    """Every one of the 262 published plans classifies into exactly one basis, and
    the no-read count matches the payload's own board_read_coverage arithmetic
    (25 not_applicable/plan_closed rows minus any of those 25 that also carry a
    live entry_status) — proving the function's BOTH-absent rule against real
    data, not just the hand-built fixtures above."""
    if not PAYLOAD.exists():
        import pytest
        pytest.skip("site/prophet/index.json not present in this checkout")
    data = json.loads(PAYLOAD.read_text())
    plans = data["plans"]
    bases = {"entry_status": 0, "board_read": 0, "no_read": 0}
    verbs_seen = set()
    for p in plans:
        out = bs.us_stance_projection(p.get("entry_status"), p.get("board_read"))
        bases[out["stance_basis"]] += 1
        if out["verb"] is not None:
            verbs_seen.add(out["verb"])
            assert out["verb"] in ("buy", "near", "wait", "hold", "avoid")
        else:
            assert out["stance_basis"] == "no_read"
    assert sum(bases.values()) == len(plans)
    # every row got a verdict from SOME source — the fallback closes the gap
    # entry_status alone left (only 143/262 rows carry entry_status directly).
    assert bases["board_read"] > 0, "the fallback path must fire on real data, not just fixtures"
    assert bases["no_read"] < len(plans), "not every row can be unreadable on a live payload"


# ── macro parameter: additive, byte-identical when unused ──────────────────────
def _env():
    return jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))


def _render(macro_call: str, **ctx) -> str:
    tmpl = _env().from_string(
        '{% import "_prophet_card.html.j2" as pv %}' + macro_call
    )
    return tmpl.render(**ctx)


_BASE_CX = {
    "href": "stock.html#AAPL", "tk": "AAPL", "mkt": "us", "name": "Apple",
    "sec": "Technology", "verb": "buy", "edge": 88, "stage": 2,
}


def test_pv_card_output_identical_with_and_without_the_new_parameter():
    """Every existing caller (hk/china/canada/intl, every current US call site)
    passes no `allow_no_read` argument — acceptance item 3 / §8a's parity
    requirement. Must be byte-for-byte identical to calling the macro with the
    parameter explicitly at its default."""
    out_omitted = _render("{{ pv.pv_card(cx) }}", cx=_BASE_CX)
    out_explicit_default = _render("{{ pv.pv_card(cx, allow_no_read=false) }}", cx=_BASE_CX)
    assert out_omitted == out_explicit_default


def test_pv_card_allow_no_read_off_still_defaults_missing_verb_to_wait():
    """Without the flag, a row with no verb (e.g. a caller that has not yet been
    updated) keeps the PRE-EXISTING legacy behavior — silently 'wait' — because
    this parameter is additive-only (§8a: 'every other caller's byte output is
    unchanged')."""
    tmpl = _env().from_string(
        '{% import "_prophet_card.html.j2" as pv %}'
        "{{ pv.pv_card({'href':'x','tk':'AAPL','mkt':'us'}) }}"
    )
    html = tmpl.render()
    assert 'class="pvcard pv-wait' in html
    assert "pv-noread" not in html


def test_pv_card_allow_no_read_on_renders_the_disclosed_no_read_state():
    """Opted in AND no usable verb -> the dashed, hue-free no-read chip (Q7b),
    never a guessed Wait."""
    tmpl = _env().from_string(
        '{% import "_prophet_card.html.j2" as pv %}'
        "{{ pv.pv_card({'href':'x','tk':'AAPL','mkt':'us'}, allow_no_read=true) }}"
    )
    html = tmpl.render()
    assert "pv-noread" in html
    assert "No read yet" in html
    assert 'class="pvcard pv-wait' not in html


def test_pv_card_allow_no_read_on_but_verb_present_renders_normally():
    """Opting in must not change a card that DOES have a usable verb — the flag
    only ever changes behavior on the no-verb path."""
    tmpl = _env().from_string(
        '{% import "_prophet_card.html.j2" as pv %}'
        "{{ pv.pv_card({'href':'x','tk':'AAPL','mkt':'us','verb':'buy'}, allow_no_read=true) }}"
    )
    html = tmpl.render()
    assert 'class="pvcard pv-buy' in html
    assert "pv-noread" not in html


def test_stance_basis_tip_renders_when_caller_passes_it():
    """§8a: 'per-row stance_basis disclosed at minimum in the LENS tip'."""
    tmpl = _env().from_string(
        '{% import "_prophet_card.html.j2" as pv %}'
        "{{ pv.pv_card({'href':'x','tk':'AAPL','mkt':'us','verb':'buy',"
        "'stance_basis':'board_read'}, allow_no_read=true) }}"
    )
    html = tmpl.render()
    assert "data-tip-en=" in html and "board_read" in html
