"""Every Prophet *candidate* pv_card caller feeds the membership slot, not asof.

US/CN keep `'date': none` (the #6532/#6544 honesty pin). HK/CA/Intl stop feeding
`signal.asof` / board `as_of` as `date`. US plan cards keep their honest plan date
and do not grow an Added chip.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

CANDIDATE_CALLERS = (
    "_us_board_cards.html.j2",
    "china.html.j2",
    "hk.html.j2",
    "canada.html.j2",
    "intl.html.j2",
)
PLAN_CALLER = "_us_prophet_plan_cards.html.j2"

_ASOF_DATE = re.compile(
    r"'date':\s*\("
    r"(?:n|s|b)\.get\('signal'\)"
    r"|'date':\s*\(setups\.get\('as_of'\)"
    r"|'date':\s*setups\.get\('as_of'\)"
    r"|'date':\s*\(n\.get\('signal'\)"
    r"|'date':\s*\(s\.get\('signal'\)"
)


def _pv_card_calls(template_name: str) -> list[str]:
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    return re.findall(r"\{\{\s*pv\.pv_card\(\{(.*?)\}\)\s*\}\}", source, flags=re.DOTALL)


def test_every_candidate_caller_passes_added_date_from_board_since():
    expected_counts = {
        "_us_board_cards.html.j2": 1,
        "china.html.j2": 2,
        "hk.html.j2": 1,
        "canada.html.j2": 1,
        "intl.html.j2": 1,
    }
    for name, n in expected_counts.items():
        calls = _pv_card_calls(name)
        assert len(calls) == n, (name, len(calls))
        for call in calls:
            assert "added_date" in call, name
            assert "board_since" in call, name


def test_us_and_cn_candidate_callers_keep_date_none_and_add_membership_slot():
    us = _pv_card_calls("_us_board_cards.html.j2")
    assert len(us) == 1
    assert "'date': none" in us[0]
    assert "added_date" in us[0]

    cn = _pv_card_calls("china.html.j2")
    assert len(cn) == 2
    assert all("'date': none" in c for c in cn)
    src = (TEMPLATES / "china.html.j2").read_text(encoding="utf-8")
    assert src.count("'date': none,") == 2
    assert all("added_date" in c for c in cn)


def test_hk_ca_intl_no_longer_feed_asof_as_the_visible_date():
    for name in ("hk.html.j2", "canada.html.j2", "intl.html.j2"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        calls = _pv_card_calls(name)
        assert calls, name
        for call in calls:
            assert _ASOF_DATE.search(call) is None, name
            assert "signal" not in call or "asof" not in call or "'date': none" in call
            assert "'date': none" in call
            assert "added_date" in call


def test_plan_cards_keep_honest_plan_date_and_do_not_take_added_date():
    calls = _pv_card_calls(PLAN_CALLER)
    assert len(calls) == 1
    call = calls[0]
    assert "p.get('plan_asof') or p.get('recorded_at')" in call
    assert "added_date" not in call


def test_gated_us_shell_and_payload_share_the_one_candidate_partial():
    dash = (TEMPLATES / "dashboard.html.j2").read_text(encoding="utf-8")
    assert '{% include "_us_board_cards.html.j2" %}' in dash
    build = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert 'get_template("_us_board_cards.html.j2")' in build


def test_no_other_pv_card_callers_outside_the_census():
    found: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.j2")):
        text = path.read_text(encoding="utf-8")
        if "pv.pv_card(" not in text:
            continue
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel == "_prophet_card.html.j2":
            continue
        found.append(rel)
    assert set(found) == set(CANDIDATE_CALLERS) | {PLAN_CALLER}


def test_builders_stamp_board_since_before_render():
    pins = {
        "scripts/build_site.py": "us",
        "scripts/build_china.py": "cn",
        "scripts/build_hk.py": "hk",
        "scripts/build_canada.py": "ca",
        "scripts/build_intl.py": "intl",
        "scripts/build_intl_library.py": "intl",
    }
    for rel, market in pins.items():
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "stamp_setups_fail_open" in src, rel
        assert re.search(
            rf'stamp_setups_fail_open\(\s*["\']{market}["\']',
            src,
        ), rel


def test_us_freshness_pin_still_forbids_pv_dt_on_candidate_cards():
    """#6532: candidate cards must not grow `.pv-dt` even after Added lands."""
    src = (TEMPLATES / "_us_board_cards.html.j2").read_text(encoding="utf-8")
    assert "'date': none" in src
    assert "n.signal.asof" not in src.replace(" ", "")
