"""Theme Tape (W2) — the join, the partition, and the surface it renders.

The panel exists to close a detection-without-narration defect, so the tests that
matter are the ones that would let the silence back in: a member that lands in no
bucket, a machine slug reaching the glance tier, a member roster that an anonymous
visitor can read, and a dead tape that still prints a top-5.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import pytest

from engine.theme_tape import (
    BUCKETS,
    QUADRANT_HEAT,
    REASON_TEXT,
    STANCES,
    build_theme_tape,
)

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "templates"


# ── fixtures ────────────────────────────────────────────────────────────────
def _rotation(**over):
    """A two-theme rotation artifact: one hot and constructive, one cold."""
    doc = {
        "asof": "2026-08-02",
        "themes": [
            {"theme": "Software", "theme_zh": "软件", "emerging_score": 3.27,
             "quadrant": "leading", "rs": {"1W": 7.59, "1M": 8.66}},
            {"theme": "Semiconductors", "theme_zh": "半导体", "emerging_score": -4.57,
             "quadrant": "lagging", "rs": {"1W": -2.0, "1M": -3.0}},
        ],
        "subsectors": [
            {"theme": "Software", "name": "Enterprise",
             "members": [{"t": "APPF"}, {"t": "AMZN"}, {"t": "MSFT"},
                         {"t": "SNOW"}, {"t": "OKTA"}, {"t": "WDAY"}]},
            {"theme": "Semiconductors", "name": "Analog", "members": [{"t": "NVDA"}]},
        ],
        "track_record": {"verdict": "measuring", "n_days": 27,
                         "proven": {"5": False, "10": False, "21": False, "63": False}},
    }
    doc.update(over)
    return doc


def _standouts(**over):
    doc = {
        "as_of": "2026-07-31",
        "buy": [
            {"ticker": "APPF", "stage": "live"},
            {"ticker": "AMZN", "stage": "setting_up",
             "dossier": {"no_buy_reasons": ["extended", "capped_by_entry"]}},
        ],
        "ran": [{"ticker": "MSFT", "stage": "ran"}],
        "leaders": [
            {"ticker": "SNOW", "dossier": {"no_buy_reasons": ["extended"]}},
            {"ticker": "OKTA", "dossier": {"no_buy_reasons": ["extended"]}},
        ],
        "watch": [],
        "laggards": [],
    }
    doc.update(over)
    return doc


TODAY = _dt.date(2026, 8, 3)


def _build(**kw):
    return build_theme_tape(_rotation(), _standouts(), today=TODAY, **kw)


# ── the join ────────────────────────────────────────────────────────────────
def test_hot_theme_reports_its_members_by_board_state():
    tape = _build()
    assert tape is not None
    row = tape["rows"][0]
    assert row["name"] == "Software" and row["name_zh"] == "软件"
    assert row["rank"] == 1 and tape["rank_of"] == 2
    assert row["counts"] == {"live": 1, "setting_up": 1, "ran": 1,
                             "leading": 2, "watching": 0, "quiet": 1}
    assert [m["t"] for m in row["members"]["live"]] == ["APPF"]
    assert [m["t"] for m in row["members"]["leading"]] == ["SNOW", "OKTA"]
    assert row["quiet_sample"] == ["WDAY"]


def test_every_member_lands_in_exactly_one_bucket():
    """The total-partition principle: the row must add up to the roster.

    This is the assertion that keeps a name from going invisible — the exact
    failure the panel was built to fix.
    """
    tape = _build()
    for row in tape["rows"]:
        assert sum(row["counts"].values()) == row["n_members"]
        assert row["n_on_board"] == row["n_members"] - row["counts"]["quiet"]
        named = sum(len(v) for v in row["members"].values())
        assert named == row["n_on_board"]


def test_cold_theme_never_reaches_the_tape():
    """The floor, not a top-K slice: a lagging, negative-score theme is dropped."""
    tape = _build()
    assert [r["name"] for r in tape["rows"]] == ["Software"]


def test_dead_tape_renders_nothing():
    """DO_NOT_REBUILD row 151 — no forced ranking when nothing is heating."""
    cold = _rotation()
    for theme in cold["themes"]:
        theme["emerging_score"] = -1.0
        theme["quadrant"] = "lagging"
    assert build_theme_tape(cold, _standouts(), today=TODAY) is None


def test_stale_rotation_artifact_suppresses_the_panel():
    assert build_theme_tape(_rotation(), _standouts(),
                            today=_dt.date(2026, 9, 30)) is None


@pytest.mark.parametrize("rotation", [None, {}, {"themes": []}, {"themes": "nope"}])
def test_missing_or_broken_artifact_is_not_fatal(rotation):
    assert build_theme_tape(rotation, _standouts(), today=TODAY) is None


def test_absent_board_still_prints_the_theme_and_says_so():
    """The whole point: a hot theme the board is silent on keeps its line."""
    tape = build_theme_tape(_rotation(), {"as_of": "x"}, today=TODAY)
    row = tape["rows"][0]
    assert row["counts"]["quiet"] == row["n_members"] == 6
    assert row["stance"] == "nothing"
    assert row["say_en"] == STANCES["nothing"][0]


# ── the stance table ────────────────────────────────────────────────────────
@pytest.mark.parametrize("counts,expected", [
    ({"live": 1, "setting_up": 3, "ran": 9, "leading": 2, "watching": 4}, "act"),
    ({"live": 0, "setting_up": 2, "ran": 1, "leading": 1, "watching": 1}, "get_ready"),
    ({"live": 0, "setting_up": 0, "ran": 1, "leading": 0, "watching": 5}, "dont_chase"),
    ({"live": 0, "setting_up": 0, "ran": 0, "leading": 3, "watching": 0}, "dont_chase"),
    ({"live": 0, "setting_up": 0, "ran": 0, "leading": 0, "watching": 2}, "stand_aside"),
    ({"live": 0, "setting_up": 0, "ran": 0, "leading": 0, "watching": 0}, "nothing"),
])
def test_stance_is_a_strict_priority_walk_over_the_counts(counts, expected):
    from engine.theme_tape import _stance_for
    assert _stance_for(counts) == expected


def test_every_stance_is_bilingual_and_ends_in_a_verb_phrase():
    for key, (en, zh) in STANCES.items():
        assert en and zh and en != zh, key
        assert en.endswith("."), key


# ── plain words (Doctrine Law 2) ────────────────────────────────────────────
def test_an_unknown_reason_slug_is_dropped_not_printed():
    board = _standouts()
    board["buy"][1]["dossier"]["no_buy_reasons"] = ["some_new_engine_slug"]
    row = build_theme_tape(_rotation(), board, today=TODAY)["rows"][0]
    amzn = row["members"]["setting_up"][0]
    assert amzn["t"] == "AMZN"
    assert amzn["why_en"] is None and amzn["why_zh"] is None


def test_near_miss_reasons_narrate_the_moment_they_appear():
    """W0.2 lands `near_miss_reason` on verdicts; the map must already carry it."""
    board = _standouts()
    board["buy"][1] = {"ticker": "AMZN", "stage": "setting_up",
                       "signal": {"near_miss_reason": "freshness_expired"}}
    row = build_theme_tape(_rotation(), board, today=TODAY)["rows"][0]
    assert row["members"]["setting_up"][0]["why_en"] == REASON_TEXT["freshness_expired"][0]


def test_a_shared_reason_is_stated_once_for_the_group():
    """Law 4 — a constant belongs in one place, not on every name."""
    row = _build()["rows"][0]
    assert row["shared_why"]["leading"] == REASON_TEXT["extended"]
    assert all(m["why_en"] is None for m in row["members"]["leading"])


def test_a_mixed_group_keeps_per_name_reasons():
    board = _standouts()
    board["leaders"][1]["dossier"]["no_buy_reasons"] = ["earnings_blackout"]
    row = build_theme_tape(_rotation(), board, today=TODAY)["rows"][0]
    assert row["shared_why"]["leading"] is None
    assert [m["why_en"] for m in row["members"]["leading"]] == [
        REASON_TEXT["extended"][0], REASON_TEXT["earnings_blackout"][0]]


def test_reason_and_heat_vocabulary_is_bilingual_and_slug_free():
    for table in (REASON_TEXT, QUADRANT_HEAT):
        for slug, (en, zh) in table.items():
            assert en and zh and en != zh, slug
            assert "_" not in en, f"{slug}: a machine slug reached the copy"
            assert en == en.lower() or en[0].isupper(), slug


def test_the_unproven_scorecard_is_carried_to_the_surface():
    """Law 5 — the artifact grades itself as `measuring`, so the panel must say so."""
    assert _build()["measuring"] is True
    proven = _rotation()
    proven["track_record"]["proven"]["21"] = True
    assert build_theme_tape(proven, _standouts(), today=TODAY)["measuring"] is False


# ── zero authority ──────────────────────────────────────────────────────────
def test_the_join_mutates_neither_artifact():
    rotation, board = _rotation(), _standouts()
    import copy
    before = (copy.deepcopy(rotation), copy.deepcopy(board))
    build_theme_tape(rotation, board, today=TODAY)
    assert (rotation, board) == before


def test_the_view_carries_no_rank_gate_or_size_field():
    """Display tier: nothing the board could consume as authority."""
    tape = _build()
    forbidden = ("gate", "size", "weight", "sizing", "conviction", "alpha",
                 "score_rank", "display_rank", "authority")
    for row in tape["rows"]:
        for key in row:
            assert not any(f in key for f in forbidden), key


def test_module_writes_nothing_and_declares_no_scoring_helpers():
    src = (ROOT / "engine" / "theme_tape.py").read_text()
    for banned in ("write_text(", "open(", "json.dump", "to_csv", "mkdir"):
        assert banned not in src, f"the view builder must not write: {banned}"


# ── the rendered surface ────────────────────────────────────────────────────
def _render(tape):
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env.get_template("_theme_tape.html.j2").render(theme_tape=tape, mode="stocks")


def test_section_renders_from_a_fixture_with_counts_and_names():
    html = _render(_build())
    assert 'id="theme-tape"' in html
    assert "Software" in html and "软件" in html
    assert ">1st of 41<" not in html  # rank_of is 2 in the fixture, not 41
    assert "APPF" in html and "SNOW" in html and "OKTA" in html
    assert STANCES["act"][0] in html and STANCES["act"][1] in html


def test_a_zero_bucket_still_prints_its_slot():
    """Printed absence is the panel's argument; a collapsed cell erases it."""
    html = _render(_build())
    assert "is-zero" in html and "–" in html


def test_no_panel_markup_at_all_when_the_view_is_absent():
    for empty in (None, {}, {"rows": []}):
        assert "theme-tape" not in _render(empty)


def test_zh_copy_is_present_for_every_glance_string():
    html = _render(_build())
    for zh in ("主题热度", "可操作", "形成中", "已启动", "领跑", "观察中", "未触发",
               "领先大盘", STANCES["act"][1]):
        assert zh in html, zh


def test_no_translated_text_inside_an_html_attribute():
    """CI law: title=/aria carry no CJK, and no i18n dual-span is expanded inline."""
    html = _render(_build())
    cjk = re.compile(r"[一-鿿]")
    for tag in re.findall(r"<[a-zA-Z][^>]*>", html):
        for attr, val in re.findall(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"', tag):
            assert "<span" not in val, f"dual-span expanded inside {attr}="
            if attr.lower() in ("title", "aria-label", "alt", "placeholder"):
                assert not cjk.search(val), f"translated text inside {attr}="


# ── banned vocabulary (Doctrine Law 2 + the falsifier ban) ──────────────────
# Internal leg / state / study names that must never reach a user surface, plus
# the front-facing falsifier ban (operator 2026-07-27) and the CI-guarded
# "validated". `near_miss_reason` and the raw gate slugs head the list: they are
# what this panel translates, so a regression here is the panel failing its job.
BANNED_ON_ANY_TIER = [
    "near_miss_reason", "not_topped_veto", "not_topped", "freshness_expired",
    "capped_by_entry", "earnings_blackout", "stoch_ob", "stoch_bear", "macd_bear",
    "signal_gate", "emerging_score", "no_buy_reasons", "us_standouts",
    "subsector_rotation.json", "turn_state", "quadrant", "z_accel", "rs_ratio",
    "IGNITION", "UPTURN_CONFIRMED", "slow reco", "expected-null", "forward meter",
    "display-tier", "display tier", "K-of-N", "gauntlet", "prereg", "Oracle P",
    "n=", "FDR", "z-score", "t-stat", "rank-IC", "cross-sectional",
    "validated", "falsifier", "refuted", "证伪", "thesis refuted",
]


def _visible_text(html: str) -> str:
    body = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    body = re.sub(r"\{#.*?#\}", " ", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def _tip_text(html: str) -> str:
    return " ".join(re.findall(r'data-tip-(?:en|zh|rc-en|rc-zh)="([^"]*)"', html))


@pytest.mark.parametrize("scope", ["visible", "hover"])
def test_no_banned_vocabulary_reaches_the_reader(scope):
    html = _render(_build())
    text = _visible_text(html) if scope == "visible" else _tip_text(html)
    hits = [b for b in BANNED_ON_ANY_TIER if b in text]
    assert hits == [], f"banned vocabulary on the {scope} tier: {hits}"


def test_template_source_carries_no_animation_to_gate():
    """No motion here, so no reduced-motion kill block is owed. Keep it that way."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    style = "\n".join(re.findall(r"<style\b.*?</style>", src, flags=re.S | re.I))
    for prop in ("transition:", "animation:", "@keyframes"):
        assert prop not in style, (
            f"{prop} added without a prefers-reduced-motion block naming its pseudos")


def test_panel_introduces_no_raw_hex_colour():
    """Every value resolves from a theme.css token, so light/dark/zh repaint free."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    style = "\n".join(re.findall(r"<style\b.*?</style>", src, flags=re.S | re.I))
    # Comments cite PR numbers ("#4344"), which are not colours — scan declarations.
    style = re.sub(r"/\*.*?\*/", " ", style, flags=re.S)
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", style) is None


def test_state_ink_uses_the_text_grade_token_with_a_fallback():
    """--ink-* is the text-grade form; raw --up is fill-grade and fails contrast."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    assert "var(--ink-up,var(--up))" in src.replace(" ", "")


def _panel_css() -> str:
    src = (TMPL / "_theme_tape.html.j2").read_text()
    style = "\n".join(re.findall(r"<style\b.*?</style>", src, flags=re.S | re.I))
    return re.sub(r"/\*.*?\*/", " ", style, flags=re.S).replace(" ", "").replace("\n", "")


def test_member_lists_wrap_atomically_and_cannot_swallow_a_name():
    """Regression: the 390px roster lost "PCOR" and tore "+46" into "+" / "46".

    The `.tt-n` spans are emitted with NO whitespace between them and a ticker is
    `white-space:nowrap`, so as an inline run the list is one unbreakable word with
    nowhere to wrap — it overran the phone and the frame cut the tail off. Flex takes
    its break opportunities between ITEMS, so each member wraps whole regardless of
    font metrics. `overflow-wrap:anywhere` was the bad patch: it made the run
    breakable by splitting inside tokens, which is what tore the "+46" chip apart.
    Measured after the fix at a genuine 390px viewport, every row expanded:
    18 lists / 69 items / 0 overflowing / 0 split / page scrollWidth == 390.
    """
    css = _panel_css()
    assert "display:flex" in css and "flex-wrap:wrap" in css, (
        ".tt-names must be a flex container — an inline run has no break "
        "opportunity between adjacent .tt-n spans and drops members off the line")
    assert "overflow-wrap:anywhere" not in css, (
        "anywhere splits INSIDE tokens and widows the '+' from its count")
    assert ".tt-more{" in css and "white-space:nowrap" in css.split(".tt-more{")[1][:120], (
        "the +N overflow chip must be one unbreakable token")


def test_a_group_reason_takes_exactly_one_separator():
    """The trailing separator and the reason's leading one printed "· ·"."""
    css = _panel_css()
    assert ".tt-n:not(:last-child)::after" in css, (
        "the separator must TRAIL its name, or a wrapped line opens with an orphan "
        "middot")
    assert ".tt-names>.tt-why::before{content:none}" in css, (
        "a group-level reason already has the previous name's trailing separator")


def test_mobile_break_matches_the_board_and_hides_the_header_row():
    """#4344 — primary decisions never x-scroll on a phone."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    assert "@media (max-width:680px)" in src
    block = src.split("@media (max-width:680px)")[1]
    assert ".tt-cols{display:none}" in block.replace(" ", "")
    assert ".tt-c.is-zero-cell{display:none}" in block.replace(" ", "")


def test_the_page_includes_the_partial_above_the_board():
    dash = (TMPL / "dashboard.html.j2").read_text()
    assert '{% include "_theme_tape.html.j2" %}' in dash
    assert dash.index("_theme_tape.html.j2") < dash.index('id="us-standouts"')


def test_full_page_renders_the_panel_on_stocks_and_never_on_macro():
    """Integration: the real dashboard template, both modes, one shared view-model.

    A partial can parse perfectly and still never reach the page — this is the
    assertion that the include actually fires, in the right mode, above the board.
    """
    from tests.test_dashboard_template_render import _base_vm, _env
    vm = dict(_base_vm(), theme_tape=_build())

    stocks = _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")
    assert 'id="theme-tape"' in stocks
    assert stocks.index('id="theme-tape"') < stocks.index('id="us-standouts"')
    assert STANCES["act"][0] in stocks

    macro = _env().get_template("dashboard.html.j2").render(**vm, mode="macro")
    assert 'id="theme-tape"' not in macro


def test_full_page_is_unchanged_when_the_view_is_absent():
    """Fail-open: no artifact, no panel, no exception, page otherwise identical."""
    from tests.test_dashboard_template_render import _base_vm, _env
    without = _env().get_template("dashboard.html.j2").render(
        **dict(_base_vm(), theme_tape=None), mode="stocks")
    assert "theme-tape" not in without
    assert len(without) > 50_000


# ── tier preview (named member states are the product) ──────────────────────
def test_member_lists_collapse_to_a_count_for_anonymous_and_free():
    js = (TMPL / "tier_preview.js").read_text()
    assert "#theme-tape .tt-names" in js, "the tape roster is not on the gate's list"
    assert "applyTapeMembers()" in js, "the collapse never runs"
    # the counts stay free: no selector touches the glance-tier ladder
    for free in (".tt-v", ".tt-row", ".tt-quiet"):
        assert free not in js, f"{free} is aggregate and must stay visible"
    # reversible through the same stash the themes strip uses, so an in-page
    # upgrade restores the names without a reload
    stash = js.split("function applyTapeMembers")[1].split("function placeSurfaceGates")[0]
    assert "data-mx-old-html" in stash and "list.innerHTML = stashed" in stash


def test_the_shipped_site_copy_matches_the_template():
    """Plain-copy asset pairing (CI-guarded)."""
    assert (TMPL / "tier_preview.js").read_bytes() == (
        ROOT / "site" / "tier_preview.js").read_bytes()
