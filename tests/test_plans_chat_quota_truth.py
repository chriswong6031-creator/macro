"""Every customer-facing chat allowance must agree with the config that enforces it.

MNZ-R13 (`research/MASTERMIND_COMMERCIAL_ARCHITECTURE.md` §7). `config/brain.yml` is what
`engine.neuralweb.brain_gateway._get_allowance` reads to decide whether a request is
allowed. Four surfaces sell those allowances:

  1. `templates/plans.html.j2`   — DERIVED (lib/chat_allowance.py → both plans builders)
  2. `templates/index.html`      — hand-authored plain-copy landing: literals
  3. `templates/onboard.js`      — the signup/upgrade sheet: literals
  4. (Terminal `components/onboarding/plans.ts` carries no chat numbers today.)

Surfaces 2 and 3 cannot derive at build time — they ship as bytes, and `index.html` is
additionally byte-paired with `site/index.html`. So they keep literals and this test is
what binds them. **A literal a test pins to its enforcer is safe; an unbound one is
not.** Reprice a lane and every surface reds here at once, which is the whole point.

WHAT THIS TEST IS NOT ABOUT
---------------------------
It is not fixing a false claim. On 2026-08-12 every literal on all four surfaces was
CORRECT, including "Unlimited" / 无限量 for the Pro fast lane — that is the honest
rendering of `quotas.pro.fast.limit: -1`, the uncapped sentinel documented in
`_get_allowance` ("A negative configured limit means uncapped requests for that lane")
and set by operator ruling 2026-07-28. The defect was that nothing bound them.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from lib.chat_allowance import DISPLAY_TIERS, chat_allowance_view_model
from scripts.build_public_pages import plans_view_model
from scripts.build_site import _plans_view_model

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# The derivation itself
# --------------------------------------------------------------------------- #
def test_view_model_matches_the_enforcing_config():
    """The view model is the config, re-keyed — not a second opinion about it."""
    quotas = yaml.safe_load((ROOT / "config" / "brain.yml").read_text())["quotas"]
    vm = chat_allowance_view_model()
    assert set(vm) == set(DISPLAY_TIERS)
    for tier in DISPLAY_TIERS:
        # config lane `pro` is surfaced as `deep` — "pro" already means a TIER on every
        # commercial surface, so the lane keeps its own word (see lib/chat_allowance.py).
        assert vm[tier]["fast"]["limit"] == int(quotas[tier]["fast"]["limit"])
        assert vm[tier]["deep"]["limit"] == int(quotas[tier]["pro"]["limit"])
        assert vm[tier]["fast"]["period"] == str(quotas[tier]["fast"]["period"])


def test_sentinels_follow_the_gateway_contract():
    """`limit < 0` is uncapped and `limit == 0` is absent — never "0 a month"."""
    vm = chat_allowance_view_model()
    for tier in DISPLAY_TIERS:
        for lane in ("fast", "deep"):
            spec = vm[tier][lane]
            assert spec["uncapped"] is (spec["limit"] < 0)
            assert spec["none"] is (spec["limit"] == 0)
            # The two flags are mutually exclusive by construction; a surface that
            # confused them would render "Unlimited" where it means "not included".
            assert not (spec["uncapped"] and spec["none"])


def test_both_plans_builders_receive_the_same_chat_contract():
    """Two entry points render the SAME template, so both must hand it the same block.

    Mirrors tests/test_terminal_indicator_pricing.py, which pins the indicator block
    across the same pair for the same reason.
    """
    expected = chat_allowance_view_model()
    assert plans_view_model()["chat_quotas"] == expected
    assert _plans_view_model()["chat_quotas"] == expected


def test_malformed_config_raises_rather_than_falling_back():
    """A silent fallback would re-introduce the drift this module exists to close."""
    from lib import chat_allowance

    bad = ROOT / "tests"          # a directory with no config/brain.yml under it
    with pytest.raises((ValueError, OSError)):
        chat_allowance.chat_allowance_view_model(root=bad)


# --------------------------------------------------------------------------- #
# The plans page: derived, and PROVABLY derived
# --------------------------------------------------------------------------- #
def _render_plans(chat_quotas: dict) -> str:
    vm = plans_view_model()
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    return env.get_template("plans.html.j2").render(
        generated_utc="test",
        currency=vm["currency"],
        essential=vm["essential"],
        pro=vm["pro"],
        founding=vm["founding"],
        terminal_indicators=vm["terminal_indicators"],
        chat_quotas=chat_quotas,
    )


def test_plans_page_renders_the_configured_allowances():
    html = _render_plans(chat_allowance_view_model())
    vm = chat_allowance_view_model()
    free, ess, pro = vm["free"], vm["essential"], vm["pro"]
    assert f"{free['fast']['limit']} quick questions a week" in html
    assert f"{ess['fast']['limit']} a month" in html
    assert f"{pro['deep']['limit']} a month" in html
    if pro["fast"]["uncapped"]:
        assert "Unlimited" in html and "unlimited" in html
    else:
        assert f"{pro['fast']['limit']}" in html


def test_plans_page_moves_when_the_config_moves():
    """The discriminating test: a derivation that renders the same page whatever the
    config says is theatre. Mutate the lane, and the promise must follow — this is what
    catches a future edit that quietly re-hardcodes a number into the template."""
    base = _render_plans(chat_allowance_view_model())
    mutant = copy.deepcopy(chat_allowance_view_model())
    mutant["pro"]["fast"] = {"limit": 2000, "period": "month", "uncapped": False, "none": False}
    mutant["free"]["fast"] = {"limit": 20, "period": "week", "uncapped": False, "none": False}
    after = _render_plans(mutant)

    assert after != base
    assert "20 quick questions a week" in after
    assert "2000" in after
    # The uncapped claim must be GONE once the lane is capped. Checked on the zh copy
    # too, because the EN and ZH cells are separate spans and a one-sided fix is the
    # failure mode a bilingual surface actually has.
    assert "Unlimited" not in after
    assert "无限量" not in after


# --------------------------------------------------------------------------- #
# The hand-authored surfaces: literals, pinned
# --------------------------------------------------------------------------- #
def _fast_cell(spec: dict) -> tuple[str, str]:
    """The compact `5 / wk` form used by the landing + onboarding compare tables."""
    if spec["uncapped"]:
        return "Unlimited", "无限量"
    unit_en, unit_zh = ("wk", "周") if spec["period"] == "week" else ("mo", "月")
    return f"{spec['limit']} / {unit_en}", f"{spec['limit']} 次/{unit_zh}"


def test_landing_page_chat_literals_match_the_config():
    """templates/index.html is hand-authored and byte-paired with site/index.html, so it
    cannot derive. These two lines are the whole chat claim on the landing."""
    text = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()

    # Pro tier card bullet (index.html ~:783)
    fast_en = "Unlimited" if vm["pro"]["fast"]["uncapped"] else str(vm["pro"]["fast"]["limit"])
    fast_zh = "无限量" if vm["pro"]["fast"]["uncapped"] else f"{vm['pro']['fast']['limit']} 次"
    assert f"{fast_en} Flash AI + {vm['pro']['deep']['limit']} Pro AI a month" in text, (
        "landing Pro card no longer matches config/brain.yml quotas.pro"
    )
    assert f"{fast_zh} Flash AI + 每月 {vm['pro']['deep']['limit']} 次 Pro AI" in text

    # Comparison matrix Flash AI row (index.html ~:832)
    for tier in DISPLAY_TIERS:
        en, zh = _fast_cell(vm[tier]["fast"])
        assert f'data-zh="{zh}">{en}<' in text, (
            f"landing Flash AI matrix cell for {tier} no longer matches config/brain.yml"
        )


def test_onboarding_sheet_chat_literals_match_the_config():
    """templates/onboard.js ships as bytes (and is served `immutable`), so it cannot
    derive either. Five literal sites carry chat numbers; all five are pinned here."""
    text = (ROOT / "templates" / "onboard.js").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()
    ess, pro = vm["essential"], vm["pro"]

    # Essential value copy — the "what you're missing" and "what you get" pair (~:261, :264)
    assert f"{ess['fast']['limit']} Flash AI answers + {ess['deep']['limit']} Pro AI dives a month" in text
    assert f"每月 {ess['fast']['limit']} 次 Flash AI + {ess['deep']['limit']} 次 Pro AI 深度分析" in text
    assert f"<b>{ess['fast']['limit']} Flash AI answers</b>, {ess['deep']['limit']} Pro AI dives a month" in text

    # Pro value copy (~:267)
    fast_en = "unlimited" if pro["fast"]["uncapped"] else f"{pro['fast']['limit']}"
    fast_zh = "无限量" if pro["fast"]["uncapped"] else f"{pro['fast']['limit']} 次"
    assert f"<b>{pro['deep']['limit']} Pro AI dives a month + {fast_en} Flash AI</b>" in text
    assert f"<b>每月 {pro['deep']['limit']} 次 Pro AI 深度分析 + {fast_zh} Flash AI</b>" in text

    # Compare table rows (~:407 Flash, :408 Pro AI)
    flash_cells = ", ".join(
        f'["{en}", "{zh}"]' for en, zh in (_fast_cell(vm[t]["fast"]) for t in DISPLAY_TIERS)
    )
    assert f"v: [{flash_cells}]" in text, (
        "onboarding Flash AI compare row no longer matches config/brain.yml"
    )
    deep = re.search(r'\{ l: \["Pro AI", "Pro AI"\],\s*v: \[(.+?)\] \},', text)
    assert deep, "onboarding Pro AI compare row not found — was it renamed?"
    row = deep.group(1)
    # Free has no deep lane at all, so the cell is the falsy `0` marker, not "0 / mo".
    assert row.startswith("0,") is vm["free"]["deep"]["none"]
    assert f'["{ess["deep"]["limit"]} / mo"' in row
    assert f'["{pro["deep"]["limit"]} / mo"' in row
