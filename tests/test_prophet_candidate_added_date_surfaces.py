"""Caller census + freshness-header guards for the Prophet candidate Added-date rollout.

Static source inspection (the same `_pv_card_calls` extraction pattern
tests/test_prophet_card_live_change.py already uses) rather than a full page
render — these six templates are enormous and every other pv_card test in this
repo works the same way. What is pinned:

  1. Every pv_card call site that renders a CANDIDATE BOARD card (as opposed to
     the plan-book cards in _us_prophet_plan_cards.html.j2, which are excluded
     by name and have their own byte-pin test) passes `added_date` and passes
     `'date': none` — never an as-of expression as `date`.
  2. No pv_card caller exists outside this named census (a new caller added
     later without updating this file fails loudly rather than silently
     shipping an unreviewed as-of date).
  3. HK (confirmed missing before this change) now carries a board-level
     "Data through" freshness disclosure; CA and Intl keep/gain theirs.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

#: Candidate-board pv_card callers this program touches. _us_prophet_plan_cards.html.j2
#: is the one legitimate exception (per-plan honest dates) and is asserted separately.
CANDIDATE_CALLERS = {
    "_us_board_cards.html.j2": 1,
    "china.html.j2": 2,
    "hk.html.j2": 1,
    "canada.html.j2": 1,
    "intl.html.j2": 1,
}
EXCLUDED_NON_CANDIDATE_CALLER = "_us_prophet_plan_cards.html.j2"

_AS_OF_TOKENS = ("signal.asof", "setups.as_of", "setups.get('as_of')", ".asof)", "get('asof')")


def _pv_card_calls(template_name: str) -> list[str]:
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    return re.findall(r"\{\{\s*pv\.pv_card\(\{(.*?)\}\)\s*\}\}", source, flags=re.DOTALL)


def _all_pv_card_caller_files() -> set[str]:
    out = set()
    for path in TEMPLATES.glob("*.j2"):
        text = path.read_text(encoding="utf-8")
        if "pv.pv_card(" in text or re.search(r"(?<!\.)\bpv_card\(", text):
            out.add(path.name)
    # _prophet_card.html.j2 itself defines the macro (and calls itself in no
    # meaningful sense for this census) — its own macro *definition* line
    # contains "pv_card(cx" which the grep above also matches; exclude it.
    out.discard("_prophet_card.html.j2")
    return out


def test_no_pv_card_caller_exists_outside_the_named_census():
    expected = set(CANDIDATE_CALLERS) | {EXCLUDED_NON_CANDIDATE_CALLER}
    assert _all_pv_card_caller_files() == expected


def test_every_candidate_caller_has_the_expected_call_count():
    for name, expected_n in CANDIDATE_CALLERS.items():
        calls = _pv_card_calls(name)
        assert len(calls) == expected_n, f"{name}: expected {expected_n} pv_card call(s), found {len(calls)}"


def test_every_candidate_call_passes_added_date_and_a_bare_none_date():
    for name in CANDIDATE_CALLERS:
        for call in _pv_card_calls(name):
            assert "added_date" in call, f"{name}: pv_card call missing added_date:\n{call}"
            assert re.search(r"'date':\s*none\s*,", call), (
                f"{name}: pv_card call's 'date' is not a bare none:\n{call}")


def test_no_candidate_call_passes_an_as_of_expression_as_date():
    for name in CANDIDATE_CALLERS:
        for call in _pv_card_calls(name):
            date_val = re.search(r"'date':\s*([^\n,]*),", call)
            assert date_val, f"{name}: no 'date' key found in call:\n{call}"
            expr = date_val.group(1)
            for token in _AS_OF_TOKENS:
                assert token not in expr, f"{name}: 'date' still carries an as-of expression ({token}):\n{expr}"


def test_plan_cards_caller_is_the_sole_exception_and_keeps_its_own_date():
    calls = _pv_card_calls(EXCLUDED_NON_CANDIDATE_CALLER)
    assert len(calls) == 1
    assert "'date': p.get('plan_asof') or p.get('recorded_at')" in calls[0]
    assert "added_date" not in calls[0]


# ───────────────────────── board-level freshness headers ─────────────────────

def test_hk_standouts_board_carries_a_data_through_freshness_header():
    src = (TEMPLATES / "hk.html.j2").read_text(encoding="utf-8")
    idx = src.find('id="standouts"')
    assert idx != -1, "hk.html.j2 #standouts panel not found"
    window = src[idx: idx + 4000]
    assert "setups.as_of" in window or "setups.get('as_of')" in window
    assert "Data through" in window
    assert "数据截至" in window


def test_canada_standouts_board_carries_a_data_through_freshness_header():
    src = (TEMPLATES / "canada.html.j2").read_text(encoding="utf-8")
    idx = src.find('id="standouts"')
    assert idx != -1, "canada.html.j2 #standouts panel not found"
    window = src[idx: idx + 4000]
    assert "setups.as_of" in window or "setups.get('as_of')" in window
    assert "Data through" in window
    assert "数据截至" in window


def test_intl_prophet_board_carries_a_data_through_freshness_header():
    src = (TEMPLATES / "intl.html.j2").read_text(encoding="utf-8")
    idx = src.find("Prophet Stock Signals")
    assert idx != -1, "intl.html.j2 Prophet Stock Signals header not found"
    window = src[idx: idx + 1500]
    assert "setups.as_of" in window or "setups.get('as_of')" in window
    assert "Data through" in window
    assert "数据截至" in window


def test_us_and_cn_freshness_headers_unaffected_by_this_change():
    # US and CN already had their board-level stamp before this program — pin
    # that this change did not touch or duplicate it.
    dash = (TEMPLATES / "dashboard.html.j2").read_text(encoding="utf-8")
    assert dash.count('id="stocks-header"') == 1
    china = (TEMPLATES / "china.html.j2").read_text(encoding="utf-8")
    assert china.count('id="stocks-header"') == 1


# ─────────────────────────── build-script wiring census ──────────────────────

#: S5 (2026-09-01 repair round): build_intl.py's OWN direct call was removed —
#: it was a provable no-op (build_intl_library.main() is the artifact's single
#: owner: it reads the prior committed intl_setups.json, stamps `setups`, THEN
#: writes that file and returns the already-stamped `setups`; build_intl.py's
#: second call always re-read the file build_intl_library.main() had just
#: written with this exact content). Only build_intl_library.py needs the
#: direct wiring now.
BUILD_SCRIPTS = {
    "build_site.py": "stamp_us_board_since",
    "build_china.py": "stamp_cn_board_since",
    "build_hk.py": "stamp_hkca_board_since",
    "build_canada.py": "stamp_hkca_board_since",
    "build_intl_library.py": "stamp_intl_board_since",
}


def test_every_build_script_wires_its_market_stamp_fail_open():
    scripts_dir = ROOT / "scripts"
    for name, fn in BUILD_SCRIPTS.items():
        src = (scripts_dir / name).read_text(encoding="utf-8")
        assert fn in src, f"{name}: no reference to {fn}"
        assert "fail_open" in src.split(fn)[1][:80] or f"{fn}_fail_open" in src, (
            f"{name}: {fn} call does not appear to be the fail-open wrapper")


def test_build_intl_no_longer_carries_the_dead_no_op_restamp():
    # S5: dead code removed. build_intl.py relies entirely on the `setups` it
    # gets back from build_intl_library.main(), which is already stamped.
    src = (ROOT / "scripts" / "build_intl.py").read_text(encoding="utf-8")
    assert "stamp_intl_board_since" not in src
    assert "build_intl_library.main(alpha=alpha)" in src
