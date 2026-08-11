"""Executable guards for the TOP ANATOMY W1 surface design freeze.

Authored (PR #5267) while the template was still INERT — no builder, no nav row,
no pipeline slot — so the guards below render it through a standalone Jinja
environment of the test's own making. That standalone render is still the freeze
and is kept verbatim: the design must survive on its own terms, independent of
whatever wires it.

The surface is no longer inert. `scripts/build_winner_health_page.py` renders it
from `data/top_maturation/latest.json`, `templates/_navlinks.html.j2` carries its
row, and `config/dag.yml` / `.github/workflows/daily.yml` schedule it (their
parity is `tests/test_dag_conformance.py`'s job, not this file's). A freeze that
only ever ran in a harness the production path does not use would be a freeze on
nobody's page, so the same two invariants are re-asserted through the real
builder below, and the wiring itself is pinned so the surface cannot silently go
dark again.
"""
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, Undefined


ROOT = Path(__file__).resolve().parent.parent


def _template():
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=Undefined,
    )
    # Shared chrome calls these globals. The production builder wires the real
    # `engine.i18n` implementations; this standalone design harness needs only
    # parity, and deliberately keeps no dependency on the builder so the freeze
    # still fails loudly if the TEMPLATE regresses while the wiring is healthy.
    env.globals.update(td=lambda x, *a, **k: x, tr=lambda x, *a, **k: x)
    return env.get_template("winner_health.html.j2")


def _row(**overrides):
    row = {
        "ticker": "TEST", "name": "Test Corp", "r126": 0.62,
        "spark": [10.0, 11.0, 10.5], "episode_high": 12.0,
        "legs": [], "analog": None,
    }
    row.update(overrides)
    return row


# ══════════════════════════════════════════════════════════════════════════════
# W2b — the three-tier board (design spec §9 delta)
#
# Each guard below maps to a numbered line of W2B_SURFACE_DESIGN_SPEC.md §9 and
# is a DESIGN gate, not a smoke test. The five fixtures above are unchanged and
# must keep passing verbatim: contract note 1 says a top-level `states` with no
# `tiers` renders as the primary tier alone, so a half-migrated builder degrades
# to today's page rather than to a blank one.
# ══════════════════════════════════════════════════════════════════════════════
#: §9.1 — pin the schema FAMILY, not one version. Asserting only `v1` would
#: silently un-guard the page the next time the contract bumps.
def _assert_no_schema_string(html):
    import re
    leaked = re.findall(r"winner_health\.v\d+", html)
    assert not leaked, f"schema mechanics reached Tier 1: {set(leaked)}"


def _tier(key, states=None, readable=True, **kw):
    t = {"key": key, "readable": readable,
         "figure": {"primary": "r126", "r63": "r63", "atrz": "atr_x"}[key],
         "library": {"track": "W", "window_start": "2022-07", "window_end": "2026-07",
                     "horizon_td": 63, "drawdown_pct": 20},
         "states": {k: [] for k in ("extended_healthy", "extended_watch", "thinning",
                                    "breaking", "no_read")}}
    for k, v in (states or {}).items():
        t["states"][k] = v
    t["extended_n"] = sum(len(v) for v in t["states"].values())
    t.update(kw)
    return t


def _three_tier(**kw):
    ctx = {"null_state": False, "universe_n": 20764,
           "tiers": [_tier("primary", {"extended_healthy": [_row()]}),
                     _tier("r63", {"extended_healthy": [_row(ticker="AAA", r63=0.41)]}),
                     _tier("atrz", {"extended_healthy": [_row(ticker="BBB", atr_x=7.2)]})]}
    ctx.update(kw)
    return ctx


TIER_NAMES = ("Big six-month gains", "Fast three-month runs", "Far above trend")


def test_w2b_three_tiers_render_and_never_print_a_cross_tier_total():
    """§9.2 — three boards, three counts, and NO number that adds them up.

    G-2 is the whole reason the shelf exists: a name can clear more than one bar,
    so a total across tiers would be a figure with no referent.
    """
    ctx = _three_tier()
    ctx["tiers"][0]["states"]["extended_healthy"] = [_row(ticker=f"P{i}") for i in range(7)]
    ctx["tiers"][1]["states"]["extended_healthy"] = [_row(ticker=f"Q{i}", r63=0.4) for i in range(11)]
    ctx["tiers"][2]["states"]["extended_healthy"] = [_row(ticker=f"R{i}", atr_x=7.0) for i in range(13)]
    for t in ctx["tiers"]:
        t["extended_n"] = sum(len(v) for v in t["states"].values())
    html = _template().render(wh=ctx)
    for name in TIER_NAMES:
        assert name in html, f"tier {name!r} did not render"
    assert html.count('class="sh-row"') == 3, "the shelf must carry exactly three rows"
    # 7 + 11 + 13 = 31, and no pairwise sum may appear either.
    for forbidden in (31, 18, 20, 24):
        assert f">{forbidden}<" not in html, f"a cross-tier total ({forbidden}) reached the page"


def test_w2b_unreadable_tier_renders_the_null_band_and_no_rows():
    """§9.3 — a tier whose own library did not load shows nothing, and says so.

    The failure this prevents: `classify([])` returns `extended_healthy`, so a
    tier with no thresholds would print a confident board of "Still running ·
    Nothing to do" for names nobody measured.
    """
    ctx = _three_tier()
    ctx["tiers"][1] = _tier("r63", readable=False)
    html = _template().render(wh=ctx)
    assert "This group was not read tonight" in html
    assert "Nothing to read here tonight" in html
    # the OTHER tiers are unaffected — an unread tier is not a dead page
    assert "Big six-month gains" in html and "Far above trend" in html
    body = html.split('id="t-three-month"')[1].split("</section>")[0]
    assert 'class="row"' not in body, "an unread tier rendered rows"


def test_w2b_empty_tier_renders_the_none_band():
    """§9.4 — zero names is a reading ("none clears this bar"), not a gap."""
    ctx = _three_tier()
    ctx["tiers"][2] = _tier("atrz")
    html = _template().render(wh=ctx)
    assert "No name is in this group tonight" in html
    assert "Nothing to watch" in html


def test_w2b_unreadable_rows_carry_no_wear_marks():
    """§9.5 — three empty outlined slots mean "measured and clear" on this page.

    On a name nobody could measure that would be a lie, so nothing is drawn.
    """
    ctx = _three_tier()
    ctx["tiers"][1]["states"]["no_read"] = [
        _row(ticker="NRD", r63=None, state="no_read",
             checks={"evaluated": 3, "total": 10}, legs=[])]
    ctx["tiers"][1]["extended_n"] = 2
    html = _template().render(wh=ctx)
    assert "Not enough to compare" in html
    assert "no similar runs to compare" in html
    grp = html.split('id="three-month-noread"')[1].split("</section>")[0]
    assert 'class="wear"' not in grp, "an unreadable row drew wear marks"
    assert "Only 3 of the 10 checks" in html, "the {k} of {m} receipt is missing"


def test_w2b_oversized_calm_group_rolls_up_and_aging_group_never_does():
    """§9.6/§9.7 — the picture is what gets dropped under load, never the reading.

    Absence from `Still running` is itself the complete reading, so that group
    rolls up. Absence from an aging group is NOT a reading — a holder must be
    able to find their name — so those rows always render and lose only the
    sparkline.
    """
    big = [_row(ticker=f"T{i:03d}") for i in range(56)]
    small = [_row(ticker=f"S{i:03d}") for i in range(55)]

    ctx = _three_tier(tiers=[_tier("primary", {"extended_healthy": big})])
    html = _template().render(wh=ctx)
    assert "Not listed one by one" in html
    assert html.count('class="row"') == 0, "a rolled-up group still rendered rows"

    ctx = _three_tier(tiers=[_tier("primary", {"extended_healthy": small})])
    html = _template().render(wh=ctx)
    assert html.count('class="row"') == 55
    assert "Not listed one by one" not in html

    # 56 AGING rows: every row renders, and the spark cell is the only casualty.
    ctx = _three_tier(tiers=[_tier("primary", {"extended_watch": big})])
    html = _template().render(wh=ctx)
    assert html.count('class="row"') == 56, "an aging group dropped rows"
    assert html.count('<svg class="sp"') == 0, "compact rows kept their sparklines"
    assert "Not listed one by one" not in html

    ctx = _three_tier(tiers=[_tier("primary", {"extended_watch": small})])
    html = _template().render(wh=ctx)
    assert html.count('<svg class="sp"') == 55


def test_w2b_trend_figure_is_neutral_and_honest_dashes_when_absent():
    """§9.8 — the trend distance is a DISTANCE, not a direction.

    It is >= the bar for a name still in the band, so directional ink would print
    a permanent green (permanent red under 红涨绿跌) that means nothing.
    """
    ctx = _three_tier(tiers=[_tier("atrz", {"extended_healthy": [_row(ticker="ABC", atr_x=7.2)]})])
    html = _template().render(wh=ctx)
    assert '<span class="fig neutral">7.2×</span>' in html
    assert "above trend" in html.lower()
    assert '<span class="fig dn">' not in html

    ctx = _three_tier(tiers=[_tier("atrz", {"breaking": [_row(ticker="ABC", atr_x=None)]})])
    html = _template().render(wh=ctx)
    assert '<span class="fig neutral">—</span>' in html, "the honest dash did not reach the new figure"


def test_w2b_tape_lag_chip_renders_only_when_the_tape_is_actually_behind():
    """§9.9 — a stale tape is disclosed; a fresh one draws no furniture."""
    html = _template().render(wh=_three_tier(tape_lag_sessions=26))
    assert "sessions behind" in html and ">26<" in html
    for quiet in (None, 4):
        html = _template().render(wh=_three_tier(tape_lag_sessions=quiet))
        assert "sessions behind" not in html, f"the chip rendered at lag={quiet}"


def test_w2b_mixed_cohort_banner_renders_once_in_every_atrz_state():
    """§9.10 — the mandate requires it on EVERY state of that tier, and nowhere else."""
    cases = {
        "board": _tier("atrz", {"extended_watch": [_row(ticker="A", atr_x=7.0)]}),
        "clear": _tier("atrz", {"extended_healthy": [_row(ticker="A", atr_x=7.0)]}),
        "none": _tier("atrz"),
        "unread": _tier("atrz", readable=False),
    }
    for label, tier in cases.items():
        html = _template().render(wh=_three_tier(tiers=[tier]))
        assert html.count('class="mixnote"') == 1, f"banner count wrong in atrz/{label}"
        assert "A mixed group." in html, f"banner copy missing in atrz/{label}"
    # and never on the other two tiers
    for key in ("primary", "r63"):
        html = _template().render(wh=_three_tier(tiers=[_tier(key, {"extended_watch": [_row()]})]))
        assert 'class="mixnote"' not in html, f"the mixed-group banner leaked onto {key}"


def test_w2b_leg_tips_name_their_own_library_or_declare_a_fixed_rule():
    """§9.11 — the mandate's no-reuse receipt, made executable.

    A library-cut leg's hover names THIS tier; a fixed rule says it is the same
    everywhere. Without the split a reader would assume all three fixed rules had
    been re-fitted per group.
    """
    legs = [{"key": "rs_decel", "words_en": "leadership fading", "words_zh": "领涨地位减弱",
             "tip_en": "Its edge is shrinking.", "tip_zh": "优势正在收窄。", "cut": "library"},
            {"key": "below_50d", "words_en": "lost its 50-day line", "words_zh": "跌破 50 日均线",
             "tip_en": "Closed below for 3 sessions.", "tip_zh": "已连续 3 个交易日收于其下。",
             "cut": "fixed"}]
    ctx = _three_tier(tiers=[_tier("atrz", {"extended_watch": [
        _row(ticker="ABC", atr_x=7.0, legs=legs)]})])
    html = _template().render(wh=ctx)
    assert "Cut from past runs in Far above trend only" in html
    assert "never from another group&#39;s history" in html or \
           "never from another group's history" in html
    assert "This is a fixed rule, the same in every group." in html


def test_w2b_zh_rows_never_print_the_literal_string_none():
    """§9.12 / §10 — Jinja's `default` substitutes only for UNDEFINED, not None.

    The artifact ships "name_zh": null on most rows, so without the boolean flag
    every ZH row printed the literal word "None" under its ticker. Verified live
    on MRNA, VSTS, ATEN, PBF and VIRT before the fix.
    """
    ctx = _three_tier(tiers=[_tier("primary", {"extended_healthy": [
        _row(ticker="MRNA", name="Moderna", name_zh=None),
        _row(ticker="NONAME", name=None, name_zh=None)]})])
    html = _template().render(wh=ctx)
    assert ">None<" not in html, "a null Chinese name printed the literal string 'None'"
    assert "MRNA" in html and "Moderna" in html
    assert ">NONAME<" in html, "a row with no name at all must fall back to its ticker"


@pytest.mark.parametrize("wh", [
    None,
    {"null_state": True},
    {"null_state": False, "states": {}},
    {"null_state": False, "universe_n": 100, "states": {
        "extended_healthy": [_row()], "extended_watch": [],
        "thinning": [], "breaking": []}},
    {"null_state": False, "states": {"extended_watch": [
        _row(spark=[10.0, 11.0], analog={"n": 4, "track": "W"})]}},
])
def test_design_freeze_renders_board_and_honest_null_fixtures(wh):
    html = _template().render(wh=wh) if wh is not None else _template().render()
    assert "Winner Health" in html
    _assert_no_schema_string(html)


def test_optional_row_number_renders_an_honest_dash_not_fake_zero():
    wh = {"null_state": False, "states": {"extended_healthy": [{"ticker": "NULL"}]}}
    html = _template().render(wh=wh)
    assert "NULL" in html
    assert '<span class="fig">—</span>' in html
    assert '<span class="fig">+0%</span>' not in html


# ══════════════════════════════════════════════════════════════════════════════
# the freeze, re-asserted on the WIRED path
#
# The harness above builds its own environment. The production one is built by
# `scripts/build_winner_health_page.py` — different globals (real `engine.i18n`),
# different loader root, and a fail-open artifact loader in front of it. Both
# invariants have to survive THAT path too, or the freeze is guarding a render
# no reader ever gets.
# ══════════════════════════════════════════════════════════════════════════════
def _render_via_builder(tmp_path, wh):
    import json
    import sys

    sys.path.insert(0, str(ROOT))
    from scripts import build_winner_health_page as bwh  # noqa: PLC0415

    if wh is None:
        # No artifact at all — the builder's own honest-null path, which is the
        # production equivalent of rendering with `wh` undefined.
        return bwh.render(ROOT, fixture=tmp_path / "absent.json")
    p = tmp_path / "wh.json"
    p.write_text(json.dumps(wh, ensure_ascii=False), encoding="utf-8")
    return bwh.render(ROOT, fixture=p)


@pytest.mark.parametrize("wh", [
    None,
    {"null_state": True},
    {"null_state": False, "states": {}},
    {"null_state": False, "universe_n": 100, "states": {
        "extended_healthy": [_row()], "extended_watch": [],
        "thinning": [], "breaking": []}},
    {"null_state": False, "states": {"extended_watch": [
        _row(spark=[10.0, 11.0], analog={"n": 4, "track": "W"})]}},
])
def test_design_freeze_holds_through_the_production_builder(tmp_path, wh):
    html = _render_via_builder(tmp_path, wh)
    assert "Winner Health" in html
    _assert_no_schema_string(html)


def test_honest_dash_survives_the_production_builder(tmp_path):
    wh = {"null_state": False, "states": {"extended_healthy": [{"ticker": "NULL"}]}}
    html = _render_via_builder(tmp_path, wh)
    assert "NULL" in html
    assert '<span class="fig">—</span>' in html
    assert '<span class="fig">+0%</span>' not in html


def test_the_surface_is_wired_and_not_inert():
    """The template is referenced by a builder and reachable from the shared nav.

    Pins the transition out of the inert state this file was written against: an
    unreferenced template renders green here forever while shipping to nobody.
    """
    builder = ROOT / "scripts" / "build_winner_health_page.py"
    assert builder.exists(), "no page builder — the surface is inert again"
    assert "winner_health.html.j2" in builder.read_text(encoding="utf-8")

    # Product pages carry ONE global header family; the row lives in its shared
    # inventory, never in a page-local header (CLAUDE.md navigation law).
    navlinks = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert "winner_health.html" in navlinks, "surface is unreachable from the product nav"


#: §14.1 — the figure cell is 92px and its caption is uppercased at 10px with 0.8px
#: letter-spacing, so a caption that renders wider than the column wraps to two lines
#: and takes the row's baseline with it.
#:
#: THE SPEC'S "<=13 CHARACTERS" IS A PROXY, AND IT IS THE WRONG ONE — measured in the
#: browser on the built page: `IN SIX MONTHS` is 13 chars and renders 90px (fits);
#: `THREE MONTHS` is 12 chars and renders 92px (WRAPS, because every glyph is a wide
#: capital). Character count and rendered width disagree in exactly the range these
#: captions live in, so a char-count assertion here would pass while the page wraps —
#: a guard giving false confidence about the defect it was written for.
#:
#: A Jinja unit test has no layout engine, so this FREEZES the exact strings instead.
#: Each was measured in-browser at 1360px; changing one fails this test and forces the
#: re-measurement rather than letting a plausible-looking caption ship unverified.
MEASURED_CAPTIONS = {
    "primary": ("in six months", 90),   # 13 chars, 90px — fits, 2px of headroom
    "r63": ("three months", 92),        # 12 chars, 92px — WRAPS; see the §4.5 amendment
    "atrz": ("above trend", 76),        # 11 chars — fits
}


def test_w2b_figure_captions_are_frozen_at_their_measured_strings():
    """§14.1 / §4.5 — captions are pinned to strings whose rendered width was measured.

    Asserted on the RENDERED caption of every tier rather than on a copy table, so the
    guard cannot be satisfied by a spec edit that never reached the template.
    """
    import re
    for key, figure_kw in (("primary", {"r126": 0.62}), ("r63", {"r63": 0.41}),
                           ("atrz", {"atr_x": 7.2})):
        ctx = _three_tier(tiers=[_tier(key, {"extended_healthy": [
            _row(ticker="ABC", **figure_kw)]})])
        html = _template().render(wh=ctx)
        caps = re.findall(r'<span class="cap"><span class="l-en">([^<]*)</span>', html)
        assert caps, f"{key}: no figure caption rendered"
        want, px = MEASURED_CAPTIONS[key]
        assert caps[0].strip() == want, (
            f"{key}: caption changed to {caps[0].strip()!r} — the pinned string was "
            f"{want!r} at {px}px in a 92px column. Re-measure the new string in a "
            f"browser before changing this pin; character count does not predict it.")
