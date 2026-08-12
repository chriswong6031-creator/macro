"""Every customer-facing chat allowance must agree with the config that enforces it.

MNZ-R13 (`research/MASTERMIND_COMMERCIAL_ARCHITECTURE.md` §7). `config/brain.yml` is what
`engine.neuralweb.brain_gateway._get_allowance` reads to decide whether a request is
allowed. SEVEN customer surfaces sell those allowances. Six are in this repository and are
covered here; the seventh is in another repo and is not:

  1. `templates/plans.html.j2`  — DERIVED (lib/chat_allowance.py → both plans builders)
  2. `templates/index.html`     — hand-authored plain-copy landing: literals
  3. `templates/onboard.js`     — the signup/upgrade sheet: literals
  4. `templates/theme.js`       — `SD_PLAN_FEATURES`, the signed-in billing summary: literals
  5. `templates/chat.html`      — the signed-out chat gate's tier list: literals
  6. (the Terminal's `components/onboarding/plans.ts` is prices-only — no chat numbers)
  7. **NOT COVERED — the Terminal's `terminal/lib/i18n.tsx`**, in the charting-app repo.
     It carries `obInsider2: ["20 Pro AI dives a month", …]` while `config/brain.yml` says
     Essential deep is 10/month. A cross-repo guard is the open item; see the commercial
     implementation plan.

Each surface was found later than the last, which is the argument of this file: surfaces 2–4
were pinned first, 5 was found by adversarial review (and was WRONG — it advertised the value
of `brain_gateway`'s hardcoded fallback rather than the live config), and 7 was found by the
review after that (also wrong). Surfaces 2–5 cannot derive at build time — they ship as bytes,
and index.html/theme.js/chat.html are byte-paired with their `site/` copies. **A literal a
test pins to its enforcer is safe; an unbound one is not.**

WHAT THIS TEST IS NOT ABOUT
---------------------------
It is not fixing a false claim. On 2026-08-12 every literal on all five surfaces was
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
    # NOT `set(vm) == set(DISPLAY_TIERS)` — the module builds `out` by iterating
    # DISPLAY_TIERS, so that assertion re-derives its receipt from the thing it checks and
    # can never fail. Pin the ladder against the catalog that actually sells the tiers.
    tier_rank = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())["tier_rank"]
    assert list(DISPLAY_TIERS) == list(tier_rank), (
        "lib/chat_allowance.DISPLAY_TIERS drifted from config/plans.yml tier_rank — a newly "
        "sold tier would silently get no allowance derivation and no guard"
    )
    assert set(vm) == set(tier_rank)
    for tier in DISPLAY_TIERS:
        # config lane `pro` is surfaced as `deep` — "pro" already means a TIER on every
        # commercial surface, so the lane keeps its own word (see lib/chat_allowance.py).
        assert vm[tier]["fast"]["limit"] == int(quotas[tier]["fast"]["limit"])
        assert vm[tier]["deep"]["limit"] == int(quotas[tier]["pro"]["limit"])
        assert vm[tier]["fast"]["period"] == str(quotas[tier]["fast"]["period"])
        assert vm[tier]["deep"]["period"] == str(quotas[tier]["pro"]["period"])


def test_sentinels_follow_the_gateway_contract():
    """`limit < 0` is uncapped and `limit == 0` is absent — never "0 a month"."""
    vm = chat_allowance_view_model()
    for tier in DISPLAY_TIERS:
        for lane in ("fast", "deep"):
            spec = vm[tier][lane]
            assert spec["uncapped"] is (spec["limit"] < 0)
            assert spec["none"] is (spec["limit"] == 0)
            # Mutually exclusive by construction; a surface that confused them would
            # render "Unlimited" where it means "not included".
            assert not (spec["uncapped"] and spec["none"])


def test_both_plans_builders_agree_on_the_whole_view_model():
    """Two entry points render the SAME template, so both must hand it the same contract.

    Asserts the WHOLE key set, not just `chat_quotas`: both builders now splat `**vm` into
    the template, so a key present in one and absent from the other is an UndefinedError at
    render time in exactly one of the two lanes — the failure mode that motivated the splat.
    """
    a, b = plans_view_model(), _plans_view_model()
    assert set(a) == set(b), "the two plans view models disagree about their key set"
    assert a["chat_quotas"] == b["chat_quotas"] == chat_allowance_view_model()


@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda q: q.pop("pro"), id="missing-tier"),
        pytest.param(lambda q: q["pro"].pop("fast"), id="missing-lane"),
        pytest.param(lambda q: q["pro"]["fast"].pop("limit"), id="missing-limit"),
        pytest.param(lambda q: q["pro"]["fast"].update(limit=None), id="null-limit"),
        pytest.param(lambda q: q["pro"]["fast"].update(limit="lots"), id="string-limit"),
    ],
)
def test_malformed_config_raises_valueerror(tmp_path, mangle):
    """A silent fallback would re-introduce the drift this module exists to close.

    Every malformed shape must exit the SAME way. `limit:` with no value is the easy one to
    get wrong: a bare `int(None)` raises TypeError, which slips past a caller catching
    ValueError and past this module's documented contract.
    """
    raw = yaml.safe_load((ROOT / "config" / "brain.yml").read_text())
    mangle(raw["quotas"])
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "brain.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        chat_allowance_view_model(root=tmp_path)


def test_missing_config_file_raises():
    with pytest.raises((ValueError, OSError)):
        chat_allowance_view_model(root=ROOT / "tests")


# --------------------------------------------------------------------------- #
# The plans page: derived, and PROVABLY derived
# --------------------------------------------------------------------------- #
def _render_plans(chat_quotas: dict | None = None) -> str:
    """Render through the SAME splat the builders use, so this exercises the real path."""
    vm = plans_view_model()
    if chat_quotas is not None:
        vm = {**vm, "chat_quotas": chat_quotas}
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    return env.get_template("plans.html.j2").render(generated_utc="test", **vm)


def _mutate(**lanes) -> dict:
    """`_mutate(free_fast={'limit': 20})` -> a view model with that lane changed."""
    cq = copy.deepcopy(chat_allowance_view_model())
    for key, patch in lanes.items():
        tier, lane = key.split("_", 1)
        cq[tier][lane].update(patch)
        cq[tier][lane]["uncapped"] = cq[tier][lane]["limit"] < 0
        cq[tier][lane]["none"] = cq[tier][lane]["limit"] == 0
    return cq


def test_plans_page_renders_every_configured_lane():
    """All SIX lane values, not the four an earlier cut checked — a plain reprice of
    `essential.deep` or a re-hardcode of `free.deep` would otherwise pass unnoticed."""
    html = _render_plans()
    vm = chat_allowance_view_model()
    # All TWELVE rendered cells: three tier cards × two lanes, plus six matrix cells. Needles
    # are anchored on a tag boundary, because `f"{limit} a month"` for limit 0 or 50 is a
    # substring of the Pro card's "150 a month" and would pass while the Essential card
    # rendered no number at all.
    free_en, _ = _long(vm["free"]["fast"])
    ess_en, _ = _long(vm["essential"]["fast"])
    deep_en, _ = _long(vm["pro"]["deep"])
    assert f">{vm['free']['fast']['limit']} quick questions {free_en}<" in html
    assert f">{vm['essential']['fast']['limit']} {ess_en}<" in html
    assert f">{vm['pro']['deep']['limit']} {deep_en}<" in html
    for tier in DISPLAY_TIERS:
        for lane in ("fast", "deep"):
            spec = vm[tier][lane]
            if spec["none"] or spec["uncapped"]:
                continue
            assert f">{spec['limit']}<small>" in html, f"{tier}.{lane} matrix cell missing"
    assert vm["free"]["deep"]["none"], "free deep lane is expected to be absent"
    if vm["pro"]["fast"]["uncapped"]:
        assert "Unlimited" in html and "unlimited" in html


@pytest.mark.parametrize(
    "lanes,present,absent",
    [
        # A capped Pro fast lane must retire the uncapped claim in BOTH languages — the EN
        # and ZH cells are separate spans, and a one-sided fix is the failure a bilingual
        # surface actually has.
        ({"pro_fast": {"limit": 2000}}, ["2000"], ["Unlimited", "无限量"]),
        ({"free_fast": {"limit": 20}}, ["20 quick questions a week"], []),
        # The PERIOD must be derived too. An earlier cut interpolated only `.limit` into
        # hardcoded "a week"/"每周", so this flip made the card contradict the matrix.
        ({"free_fast": {"period": "month"}}, ["5 quick questions a month", "每月 5 个快速提问"],
         ["quick questions a week", "每周 5 个快速提问"]),
        # `day` is reachable in production: _get_allowance returns {period: "day"} for the
        # FREE fast lane whenever guest access is enabled.
        ({"free_fast": {"limit": 3, "period": "day"}}, ["3 quick questions a day", "每天 3 个快速提问"], []),
        # Pulling the deep lane from Essential must render ✗, never "0 a month".
        # Both needles are ANCHORED on the tag boundary: a bare "0 a month" is a
        # substring of "300 a month" and would fire on the untouched Essential fast
        # lane — a needle that matches the thing it is not testing proves nothing.
        ({"essential_deep": {"limit": 0}}, [], [">0<small>", ">0 a month<"]),
    ],
)
def test_plans_page_moves_when_the_config_moves(lanes, present, absent):
    """The discriminating test: a derivation that renders the same page whatever the config
    says is theatre. This is what catches a future edit that re-hardcodes a number."""
    html = _render_plans(_mutate(**lanes))
    for token in present:
        assert token in html, f"expected {token!r} after {lanes}"
    for token in absent:
        assert token not in html, f"{token!r} survived {lanes}"


def test_pulling_a_lane_adds_exactly_one_cross_cell():
    """The `none` sentinel must change the <td> CLASS, not just its text — a macro that
    returned only inner text could not express that, and the ✗ cell would read as a value."""
    before = _render_plans().count('<td class="no">✗</td>')
    after = _render_plans(_mutate(essential_deep={"limit": 0})).count('<td class="no">✗</td>')
    assert after == before + 1


# --------------------------------------------------------------------------- #
# The hand-authored surfaces: literals, pinned
# --------------------------------------------------------------------------- #
#: Period phrasing per surface. Derived, never hardcoded into a needle — an earlier cut
#: wrote "a week" / "每周" straight into these assertions, which reproduced on the pinned
#: surfaces the exact "limit interpolated, period hardcoded" defect the plans template was
#: fixed for: flipping `quotas.free.fast.period` left every surface test green while four
#: pages went on saying "a week".
_PER_LONG = {"week": ("a week", "每周"), "month": ("a month", "每月"), "day": ("a day", "每天")}
_PER_CELL = {"week": ("wk", "周"), "month": ("mo", "月"), "day": ("day", "天")}


def _long(spec: dict) -> tuple[str, str]:
    return _PER_LONG[spec["period"]]


def _fast_cell(spec: dict) -> tuple[str, str]:
    """The compact `5 / wk` form used by the landing + onboarding compare tables."""
    if spec["uncapped"]:
        return "Unlimited", "无限量"
    en, zh = _PER_CELL[spec["period"]]
    return f"{spec['limit']} / {en}", f"{spec['limit']} 次/{zh}"


def test_landing_page_chat_literals_match_the_config():
    """templates/index.html is hand-authored and byte-paired with site/index.html.

    Pins BOTH lanes and BOTH registers — an earlier cut covered only the Pro card and the
    three fast matrix cells, so bumping `essential.deep` from 10 to 25 left three stale
    literals on the landing with the suite green.
    """
    text = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()
    ess, pro = vm["essential"], vm["pro"]
    ess_en, ess_zh = _long(ess["fast"])
    pro_en, pro_zh = _long(pro["deep"])

    # tier card bullets — Essential and Pro
    assert f"{ess['fast']['limit']} Flash AI + {ess['deep']['limit']} Pro AI {ess_en}" in text
    assert f"{ess_zh} {ess['fast']['limit']} 次 Flash AI + {ess['deep']['limit']} 次 Pro AI" in text
    fast_en = "Unlimited" if pro["fast"]["uncapped"] else str(pro["fast"]["limit"])
    fast_zh = "无限量" if pro["fast"]["uncapped"] else f"{pro['fast']['limit']} 次"
    assert f"{fast_en} Flash AI + {pro['deep']['limit']} Pro AI {pro_en}" in text
    assert f"{fast_zh} Flash AI + {pro_zh} {pro['deep']['limit']} 次 Pro AI" in text

    # the "Pro AI" explainer line carries both deep numbers
    assert (f"{ess['deep']['limit']}/mo on Essential · {pro['deep']['limit']}/mo on Pro") in text
    assert (f"Essential {ess_zh} {ess['deep']['limit']} 份 · Pro {pro_zh} {pro['deep']['limit']} 份") in text

    # comparison matrix — fast row (all three tiers) and deep row (paid tiers)
    for tier in DISPLAY_TIERS:
        en, zh = _fast_cell(vm[tier]["fast"])
        assert f'data-zh="{zh}">{en}<' in text, f"landing fast cell for {tier} drifted"
    for tier in ("essential", "pro"):
        en, zh = _fast_cell(vm[tier]["deep"])
        assert f'data-zh="{zh}">{en}<' in text, f"landing deep cell for {tier} drifted"


def test_onboarding_sheet_chat_literals_match_the_config():
    """templates/onboard.js ships as bytes and is served `immutable`, so it cannot derive."""
    text = (ROOT / "templates" / "onboard.js").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()
    ess, pro = vm["essential"], vm["pro"]
    ess_en, ess_zh = _long(ess["fast"])
    pro_en, pro_zh = _long(pro["deep"])

    assert f"{ess['fast']['limit']} Flash AI answers + {ess['deep']['limit']} Pro AI dives {ess_en}" in text
    assert f"{ess_zh} {ess['fast']['limit']} 次 Flash AI + {ess['deep']['limit']} 次 Pro AI 深度分析" in text
    assert f"<b>{ess['fast']['limit']} Flash AI answers</b>, {ess['deep']['limit']} Pro AI dives {ess_en}" in text

    fast_en = "unlimited" if pro["fast"]["uncapped"] else f"{pro['fast']['limit']}"
    fast_zh = "无限量" if pro["fast"]["uncapped"] else f"{pro['fast']['limit']} 次"
    assert f"<b>{pro['deep']['limit']} Pro AI dives {pro_en} + {fast_en} Flash AI</b>" in text
    assert f"<b>{pro_zh} {pro['deep']['limit']} 次 Pro AI 深度分析 + {fast_zh} Flash AI</b>" in text

    flash_cells = ", ".join(
        f'["{en}", "{zh}"]' for en, zh in (_fast_cell(vm[t]["fast"]) for t in DISPLAY_TIERS)
    )
    assert f"v: [{flash_cells}]" in text, "onboarding Flash AI compare row drifted"
    deep = re.search(r'\{ l: \["Pro AI", "Pro AI"\],\s*v: \[(.+?)\] \},', text)
    assert deep, "onboarding Pro AI compare row not found — was it renamed?"
    row = deep.group(1)
    # Free has no deep lane at all, so the cell is the falsy `0` marker, not "0 / mo".
    assert row.startswith("0,") is vm["free"]["deep"]["none"]
    for tier in ("essential", "pro"):
        en, _ = _fast_cell(vm[tier]["deep"])
        assert f'["{en}"' in row, f"onboarding deep cell for {tier} drifted"


def test_billing_summary_chat_literals_match_the_config():
    """`SD_PLAN_FEATURES` in templates/theme.js — the signed-in billing "what's included"
    summary. Found by adversarial review after four surfaces were already pinned; it is the
    one a PAYING customer reads, so it is the worst one to let drift."""
    text = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()
    free_en, _ = _long(vm["free"]["fast"])
    ess_en, _ = _long(vm["essential"]["fast"])
    ess_deep_en, _ = _long(vm["essential"]["deep"])
    pro_deep_en, _ = _long(vm["pro"]["deep"])
    _, free_zh = _long(vm["free"]["fast"])

    assert f"'{vm['free']['fast']['limit']} Mastermind questions {free_en}'" in text
    assert f"'{free_zh} {vm['free']['fast']['limit']} 次 Mastermind 提问'" in text
    assert f"'{vm['essential']['fast']['limit']} Mastermind questions {ess_en}'" in text
    assert f"'{vm['essential']['deep']['limit']} deep research questions {ess_deep_en}'" in text
    assert f"'{vm['pro']['deep']['limit']} deep research questions {pro_deep_en}'" in text
    if vm["pro"]["fast"]["uncapped"]:
        assert "'Unlimited Mastermind questions'" in text
        assert "'无限量 Mastermind 提问'" in text
    else:
        assert f"'{vm['pro']['fast']['limit']} Mastermind questions" in text


def test_chat_gate_tier_list_matches_the_config():
    """`templates/chat.html`'s signed-out tier list — the SIXTH surface, and the one that was
    actually WRONG when review found it: it advertised "1000 fast" for Pro, which is the value
    of `brain_gateway`'s hardcoded FALLBACK, not of the live config that overrides it."""
    text = (ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
    vm = chat_allowance_view_model()
    for tier, label in (("free", None), ("essential", "Essential"), ("pro", "Pro")):
        fast, deep = vm[tier]["fast"], vm[tier]["deep"]
        if label:
            assert f'<span class="l-en">{label}</span>' in text, (
                f"chat gate no longer names the {tier} tier '{label}'"
            )
        if deep["none"]:
            continue
        fast_en = "Unlimited" if fast["uncapped"] else str(fast["limit"])
        fast_zh = "无限量" if fast["uncapped"] else f"{fast['limit']} 条"
        _, zh_per = _long(fast)
        assert f"{fast_en} fast + {deep['limit']} pro / {fast['period']}" in text, (
            f"chat gate {tier} row drifted from config/brain.yml"
        )
        assert f"{zh_per}{fast_zh}快速 + {deep['limit']} 条专业" in text or \
               f"{zh_per} {fast_zh}快速 + {deep['limit']} 条专业" in text
