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
    """DNR:HOLD-IGNITION-SURFACES — no forced ranking when nothing is heating."""
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


def test_no_fixed_track_is_sized_to_a_sub_12px_label():
    """The 2026-08-04 break: 10px labels inside flat px tracks.

    `.tt-k` and `.tt-fs` are 10px, and 10px is below the browser's
    minimum-font-size setting — a user preference (commonly 12–16px) that raises
    the RENDERED size while the track stays where the CSS put it. So the width of
    that text is not a function of this stylesheet, and a track sized to fit it at
    the authored size has no guarantee at all. Sized to clear "setting up" at 10px
    the columns were 58px with 4.1px of slack: at a 12px clamp "watching" overran
    its column and the shelf's "loading up" chip overran the 74px label column and
    printed across the theme names beside it, which is what the operator
    screenshotted. Same class as the score-ring caption in #4357.

    These assertions are STRUCTURAL on purpose. A clearance check measured in a
    default render passes on the broken build — it cannot reach the state that
    breaks it — so what gets pinned is the two properties that make the layout
    hold at any rendered label width:
      · the label column can GROW (minmax → max-content), so a clamped chip widens
        its track instead of painting over the column beside it, and
      · a clamped column label WRAPS inside its own track (overflow-wrap).
    """
    css = _panel_css()

    # 1. the three widths are declared once, so the grids cannot drift apart
    assert "--tt-col:" in css and "--tt-quiet:" in css and "--tt-gk:" in css, (
        "the header row, the theme rows and the member groups must read their "
        "column widths from one declaration — three inline copies drift")
    ladder = css.split(".tt-row{")[1].split("}")[0]
    assert "repeat(5,var(--tt-col))" in ladder and "var(--tt-quiet)" in ladder, (
        "the ladder must size from the shared properties, not inline px")
    assert "repeat(5,58px)" not in css, "the pre-#4357-ruling magic number is back"

    # 2. the label column grows rather than overflowing — the chip overlap fix
    gk = css.split(".tt-g{")[1].split("}")[0]
    assert "minmax(var(--tt-gk),max-content)" in gk, (
        "a flat label track is what let the 'loading up' chip print across the "
        "theme names; it must be free to widen when the chip is clamped larger")
    assert not re.search(r"grid-template-columns:\d+px", gk), (
        "a fixed px label column cannot report that its chip no longer fits")

    # 3. containment is a guarantee, not a margin — no label paints out of its cell
    k = css.split(".tt-k{")[1].split("}")[0]
    assert "overflow-wrap:break-word" in k, (
        "past any track width a column label must wrap inside its OWN column; "
        "without this it silently paints over its neighbour")
    assert "overflow:hidden" not in k and "text-overflow:ellipsis" not in k, (
        "clipping the label to 'watchin…' is the worse fix (#4357 ruling)")


def test_the_glance_row_is_one_line_and_the_stance_is_the_exception():
    """Doctrine Law 4: a per-row constant belongs in one place, once.

    `_stance_for` is a lookup on the five counts printed on the row beside it, so
    the stance sentence carries no information the ladder has not already given —
    and on a normal night four of five rows print the identical sentence. Three
    lines per theme is what made the panel 692px. The row that has live names is
    the one row whose stance asks for something today, so it keeps it on the
    glance tier; the rest carry it inside the disclosure.
    """
    src = (TMPL / "_theme_tape.html.j2").read_text()
    summary = src.split('<summary class="tt-s">')[1].split("</summary>")[0]
    detail = src.split('<div class="tt-det">')[1].split("{%- endfor %}")[0]

    assert 'class="tt-say"' in summary, "the actionable row keeps its stance"
    say_at = summary.index('class="tt-say"')
    gate = summary.rfind("_c.get('live')", 0, say_at)
    assert gate != -1, (
        "the glance-tier stance must be gated on the live count — ungated it is "
        "the repeated constant Law 4 forbids")

    assert 'class="tt-heat"' not in summary, (
        "rank/heat is Tier-3 reference, not a second glance line per theme")
    assert 'class="tt-heat"' in detail and "say_en" in detail, (
        "what leaves the glance tier has to land somewhere — rank, heat and the "
        "stance for every non-live row belong in the expanded row")


def _gist(tape):
    """The closed tier's one line, sliced out of the rendered panel."""
    return _render(tape).split('class="tt-gist"')[1].split("</span>\n      </summary>")[0]


def _with_off_list(tape):
    """Give a tape the two groups that fold into the gist's off-list figure.

    The base fixture has neither, which is a legitimate night — and it is exactly
    why the off-list clause has to be tested against a tape that HAS them: an
    assertion written against the bare fixture passes on a template that never
    emits the clause at all.
    """
    tape = dict(tape)
    tape["washout_turns"] = [{
        "name": "Space Tech", "name_zh": "太空科技", "rank": 28,
        "turn_1w": 2.03, "turn_1m": -14.17, "n_members": 12, "n_on_board": 1,
        "counts": {"live": 0, "setting_up": 1, "ran": 0, "leading": 0,
                   "watching": 0, "quiet": 11},
        "members": {}, "quiet_sample": [],
    }]
    tape["foresight_shelf"] = [
        {"label_en": "loading up", "label_zh": "蓄势",
         "names_en": ["Medical Devices", "Nuclear & SMR Power"],
         "names_zh": ["医疗器械", "核能与小型模块堆"], "more": 1},
        {"label_en": "re-rating", "label_zh": "重估",
         "names_en": ["AI Semiconductors"], "names_zh": ["AI 半导体"], "more": 0},
    ]
    return tape


def test_the_whole_panel_is_one_closed_disclosure():
    """Operator, 2026-08-06: "way smaller in height."

    680px desktop / 1004px phone against the real artifacts, after two separate
    compaction passes. The closed height is now the budget, so the structure that
    delivers it is pinned: ONE <details> with no `open` attribute wrapping
    everything except the eyebrow and the gist. A future section added outside
    `.tt-body` is the re-inflation this guard exists to catch.
    """
    src = (TMPL / "_theme_tape.html.j2").read_text()
    assert '<details class="tt-all">' in src, "the panel is one disclosure"
    assert '<details class="tt-all" open' not in src and \
           '<details open class="tt-all"' not in src, "it ships CLOSED"

    head, body = src.split('<div class="tt-body">', 1)
    summary = head.split('<summary class="tt-all-s">')[1]
    # everything heavy lives behind the fold
    for heavy in ('class="tt-cols"', 'class="tt-i"', 'class="tt-turn"',
                  'class="tt-shelf"', 'class="tt-foot"'):
        assert heavy not in summary, f"{heavy} must sit inside .tt-body, not the summary"
        assert heavy in body, f"{heavy} went missing from the disclosure body"
    # the summary is the eyebrow + the gist, and nothing else
    assert 'class="tt-eyebrow"' in summary and 'class="tt-gist"' in summary
    assert 'class="tt-sub"' not in src, (
        "the standing subtitle described the panel instead of reading it; the gist "
        "replaced it")


def test_the_gist_carries_every_folded_section_in_words():
    """The charter's rule is NARRATION, not enumeration — and folding must not
    reintroduce the detection-without-narration defect the panel exists to close.

    A reader who never opens the panel must still be told: what is hottest, whether
    anything is live on this board, and that there is more off the heat list (the
    turn group + the shelf, which were the always-visible sections before the
    fold). Plus the stance, because closed is the default state and Law 1 is
    answered on the tier the reader is actually on.
    """
    gist = _gist(_with_off_list(_build()))

    assert "Software" in gist and "软件" in gist, "the hottest theme is named"
    assert "live name" in gist and "可操作" in gist, "the board's live count"
    assert "off the heat list" in gist and "不在热度榜上" in gist, (
        "the turn group and the shelf both fold — the gist is where a reader is "
        "told they exist")
    for stance in ("where to look, not what to buy", "而非买入对象"):
        assert stance in gist, f"Law 1 stance missing from the closed tier: {stance}"

    # …and stays silent about it on a night with neither (honest null, not "0 more")
    bare = _gist(_build())
    assert "off the heat list" not in bare and "不在热度榜上" not in bare


def test_the_gist_counts_agree_with_the_ladder_it_folds():
    """One source, two renderings. The closed line and the open ladder are the same
    figures, so a fixture where they can disagree is the bug this pins."""
    tape = _with_off_list(_build())
    gist = _gist(tape)

    live = sum((r.get("counts") or {}).get("live") or 0 for r in tape["rows"])
    off = sum(len(g["names_en"]) + (g.get("more") or 0)
              for g in (tape.get("foresight_shelf") or []))
    off += len(tape.get("washout_turns") or [])
    assert live and off, "fixture must exercise both clauses, not skip them"

    assert f'is-live">{live}<' in gist, f"live total {live} not printed"
    assert f'"tt-gf">{off}<' in gist, f"off-list total {off} not printed"

    # the shelf's `more` overflow counts — it is names the shelf did not print,
    # and dropping it would under-report the very thing the gist is standing in for
    assert off == 2 + 1 + 1 + 1, "3 loading-up + 1 re-rating + 1 turn row"


def test_a_zero_live_night_still_says_so_on_the_closed_tier():
    """Law 5 — printed absence is this panel's whole argument, and the closed line
    is the only tier most readers see. A gist that simply omitted the live clause
    would read as 'nothing to report' on exactly the night it matters."""
    tape = _build()
    for r in tape["rows"]:
        r["counts"]["live"] = 0
    gist = _render(tape).split('class="tt-gist"')[1].split("</span>\n      </summary>")[0]
    assert "nothing live on the board today" in gist
    assert "本榜今日无可操作" in gist
    assert "is-live" not in gist, "no colour on a night with nothing live"


def test_no_user_facing_copy_bakes_in_a_page_direction():
    """Law 4 (one footnote) + direction-proof copy.

    This panel has moved twice — above the board, below the board, and now last on
    the page — and BOTH times the move left copy behind that still pointed the old
    way. #4553 caught the footnote ("the picks below") and fixed it to "above";
    that word went stale again on 2026-08-06 when the panel moved to the bottom,
    and three more strings were still saying "below" that #4553 never touched: the
    `?` tip ("the board below is unchanged by it") and the two per-row hovers
    ("this changes no ranking below"), en and zh.
    So the guard is no longer "says above, not below" — it is that NO user-facing
    string on this panel names a direction at all. A relative word is a claim about
    where the panel sits, and this panel does not sit still. Say "on this page".
    """
    src = (TMPL / "_theme_tape.html.j2").read_text()
    # strip {# … #} comments: they discuss placement history on purpose
    body = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
    for word in ("picks below", "picks above", "board below", "board above",
                 "ranking below", "ranking above",
                 "下方选股", "上方选股", "下方看板", "上方看板",
                 "不改变下方", "不改变上方"):
        assert word not in body, (
            f"{word!r} bakes a page position into user-facing copy — the panel has "
            f"already moved twice and this is the third time it went stale")
    foot = src.split('<p class="tt-foot">')[1].split("</p>")[0]
    assert "picks on this page" in foot and "本页选股" in foot
    assert "more than one line" not in foot, (
        "duplicated from the ? tip — a second copy on the always-visible tier is "
        "the stacked footnote Law 4 forbids")
    # Law 1 — the panel's own stance survives even when the `measuring` clause dark
    for lang, stance in (("l-en", "where to look, not at what to buy"),
                         ("l-zh", "而非买入对象")):
        span = foot.split(f'class="{lang}"')[1].split("</span>")[0]
        # what a reader gets when `measuring` is False: drop the whole conditional
        unconditional = re.sub(r"\{%\s*if\b.*?\{%\s*endif\s*%\}", "", span, flags=re.S)
        assert stance in unconditional, (
            f"[{lang}] the stance must sit outside the measuring conditional — on a "
            "night with no live row this is the panel's only answer to 'so what "
            "do I do'")


def test_mobile_break_matches_the_board_and_hides_the_header_row():
    """#4344 — primary decisions never x-scroll on a phone."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    assert "@media (max-width:680px)" in src
    block = src.split("@media (max-width:680px)")[1]
    assert ".tt-cols{display:none}" in block.replace(" ", "")
    assert ".tt-c.is-zero-cell{display:none}" in block.replace(" ", "")


def test_the_page_includes_the_partial_last_of_all():
    """Operator order 2026-08-06: "move it down to bottom of the page."

    Third complaint about this panel's footprint. It shipped ABOVE the board;
    #4553 moved it below the board and cut it 692px → 498px; #4605 merged one
    minute later, added the washout-turn group and a second shelf group, and it
    measured 680px desktop / 1004px phone against the real artifacts — bigger than
    the state that drew the first complaint. Trimming it in place failed twice, so
    it leaves the reading order: after every board panel, and folded shut.

    Pinned against `id="holdings"` — the last panel us_stocks renders (the data
    health strip after it is `mode != 'stocks'`) — not merely against the board,
    which is what the previous version of this guard checked and which the panel
    satisfied while still sitting six panels above the bottom.
    """
    dash = (TMPL / "dashboard.html.j2").read_text()
    assert '{% include "_theme_tape.html.j2" %}' in dash
    inc = dash.index("_theme_tape.html.j2")
    for anchor in ('id="us-standouts"', 'id="equity-scoreboard"', 'id="sectors"',
                   'id="accumulation"', 'id="holdings"'):
        assert inc > dash.index(anchor), f"the tape must render after {anchor}"


def test_full_page_renders_the_panel_on_stocks_and_never_on_macro():
    """Integration: the real dashboard template, both modes, one shared view-model.

    A partial can parse perfectly and still never reach the page — this is the
    assertion that the include actually fires, in the right mode, and renders
    after every other panel. Source order is what the template guard above pins;
    this one pins the RENDERED order, which is what a reader scrolls.
    """
    from tests.test_dashboard_template_render import _base_vm, _env
    vm = dict(_base_vm(), theme_tape=_build())

    stocks = _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")
    assert 'id="theme-tape"' in stocks
    at = stocks.index('id="theme-tape"')
    for anchor in ('id="us-standouts"', 'id="holdings"'):
        assert at > stocks.index(anchor), f"rendered tape must follow {anchor}"
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


# ════════════════════════════════════════════════════════════════════════════
# THE FORESIGHT DESK JOIN (W5a)
#
# The tape reads price; the desk reads filings and company language, so it sees a
# theme tighten before the tape has anything to say about it. Joining them is
# worth exactly one word per row and one shelf, and the tests that matter are the
# ones that keep that word HONEST: a stage enum leaking to the glance tier, a
# mapping typo that makes the feature look alive while it joins nothing, a theme
# printed twice, and — the one with a shelf life — a disclosure written as a
# constant, which would go on claiming "not confirmed" years after it stopped
# being true.
# ════════════════════════════════════════════════════════════════════════════
import json as _json  # noqa: E402

from engine.theme_tape import (  # noqa: E402
    FORESIGHT_LABELS,
    STAGE_LABEL,
    THEME_MAP,
    THEME_NAME_ZH,
    THEME_UNMAPPED,
)

DESK_ARTIFACT = ROOT / "site" / "basketdata" / "foresight_cascade.json"
ROT_ARTIFACT = ROOT / "site" / "marketdata" / "subsector_rotation.json"


def _shipped(path):
    """A git-tracked artifact, read as a hard requirement.

    Never skip on absence: a coverage gate that skips when its input is missing
    is a dark gate, and both files are tracked in the repo precisely so the gate
    can always run.
    """
    assert path.exists(), f"{path} is git-tracked and must be present"
    return _json.loads(path.read_text())


def _desk(*themes, asof="2026-08-04"):
    return {"asof": asof, "themes": list(themes)}


def _theme(key, stage, name=None, **over):
    doc = {"theme": key, "name": name or key.replace("_", " ").title(),
           "stage": stage, "bottleneck_text_only": False,
           "bottleneck_fingerprint_only": False}
    doc.update(over)
    return doc


def _hot_rotation(*names):
    """A rotation artifact where each named theme is hot and has two members."""
    return _rotation(
        themes=[{"theme": n, "theme_zh": n, "emerging_score": 3.0 - i,
                 "quadrant": "leading", "rs": {"1W": 1.0, "1M": 2.0}}
                for i, n in enumerate(names)],
        subsectors=[{"theme": n, "name": "S", "members": [{"t": "APPF"}, {"t": "MSFT"}]}
                    for n in names],
    )


# ── the mapping table (pure — these can never go dark) ──────────────────────
def test_every_desk_theme_is_mapped_or_explicitly_unmapped():
    """No desk theme may fall through the join silently.

    A theme in neither table gets no chip AND no reason on record, which is how
    a taxonomy drifts apart unnoticed. Adding a theme to the desk must force a
    decision here.
    """
    keys = {t["theme"] for t in _shipped(DESK_ARTIFACT)["themes"]}
    missing = sorted(keys - set(THEME_MAP) - set(THEME_UNMAPPED))
    assert missing == [], (
        f"desk themes with no mapping decision: {missing} — add each to "
        "THEME_MAP, or to THEME_UNMAPPED with the reason it cannot be paired")


def test_mapped_and_unmapped_are_disjoint_and_every_exclusion_is_reasoned():
    both = sorted(set(THEME_MAP) & set(THEME_UNMAPPED))
    assert both == [], f"claimed as both mapped and unmapped: {both}"
    for key, why in THEME_UNMAPPED.items():
        assert isinstance(why, str) and len(why) > 20, (
            f"{key} is excluded without a usable reason")


def test_every_mapping_target_is_a_real_rotation_theme():
    """The typo guard, and the reason this test exists at all.

    A mistyped target does not raise — it simply never matches a row, so the
    chip never appears and the feature looks alive while joining nothing. Only
    checking targets against the published vocabulary can see it.
    """
    published = {t.get("theme") for t in _shipped(ROT_ARTIFACT).get("themes") or []}
    unknown = sorted({v for v in THEME_MAP.values() if v not in published})
    assert unknown == [], (
        f"mapping targets that no rotation theme publishes: {unknown} — these "
        "would never join, and nothing else would notice")


def test_every_desk_theme_has_a_chinese_name():
    for key in set(THEME_MAP) | set(THEME_UNMAPPED):
        assert THEME_NAME_ZH.get(key), f"{key} would print English in zh"


def test_a_narrow_slice_of_a_broad_row_stays_unmapped():
    """The composition test (ruling 2026-08-04).

    Desk themes may share a target only when they JOINTLY COMPOSE it. The three
    healthcare themes are narrow slices of a much broader row — pharma, managed
    care and hospitals are most of "Healthcare & Biotech" — so a row-level word
    would overstate the slice. They keep their shelf presence under their own
    names, which is where they already sit on live data.
    """
    for key in ("glp1_obesity", "medical_devices", "diagnostics_lifesci"):
        assert key not in THEME_MAP, (
            f"{key} is a slice of Healthcare & Biotech, not a constituent that "
            "composes it — a row-level chip would overstate it")
        assert "Healthcare & Biotech" in THEME_UNMAPPED[key]
    # the trio that DOES compose its row keeps the many-to-one mapping
    assert {k for k, v in THEME_MAP.items() if v == "Semiconductors"} == {
        "ai_semiconductors", "memory_storage", "semicap_equipment"}
    assert "Healthcare & Biotech" not in set(THEME_MAP.values())


def test_the_whole_stage_enum_has_a_decision():
    """Every value the desk can emit maps to a word, or explicitly to nothing."""
    from engine.foresight_cascade import _STAGE_RANK

    missing = sorted(set(_STAGE_RANK) - set(STAGE_LABEL))
    assert missing == [], f"stage values with no display decision: {missing}"


def test_only_two_words_ever_reach_a_reader():
    words = {v for v in STAGE_LABEL.values() if v is not None}
    assert words == set(FORESIGHT_LABELS) == {"loading", "re_rating"}
    for en, zh in FORESIGHT_LABELS.values():
        assert en and zh and en != zh


def test_stages_that_are_neither_thesis_nor_re_rating_get_no_word():
    for stage in ("GLUT-RISK", "WATCH", "UNKNOWN"):
        assert STAGE_LABEL[stage] is None
    # an enum value invented tomorrow falls through to silence, not to a crash
    assert STAGE_LABEL.get("SOMETHING-NEW") is None


# ── the join ────────────────────────────────────────────────────────────────
def test_a_covered_hot_row_carries_the_word_and_names_its_source():
    tape = build_theme_tape(
        _hot_rotation("Semiconductors"), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "PRECIPICE",
                               name="AI Semiconductors")))
    chip = tape["rows"][0]["foresight"]
    assert chip["label_en"] == "loading up" and chip["label_zh"] == "蓄势"
    # a target can be composed of several desk themes, so the hover names the
    # ones the word actually came from
    assert chip["sources_en"] == "AI Semiconductors"
    assert chip["tip_en"] and chip["tip_zh"]


def test_a_row_the_desk_has_no_read_on_carries_nothing():
    tape = build_theme_tape(_rotation(), _standouts(), today=TODAY,
                            foresight=_desk(_theme("solar", "PRECIPICE")))
    assert tape["rows"][0]["name"] == "Software"
    assert tape["rows"][0]["foresight"] is None


def test_disagreeing_desk_themes_on_one_row_print_no_word():
    """Absence beats a four-character chip hiding a coin flip."""
    tape = build_theme_tape(
        _hot_rotation("Semiconductors"), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "RE-RATING"),
                        _theme("memory_storage", "PRECIPICE")))
    assert tape["rows"][0]["foresight"] is None


def test_a_watch_sibling_cannot_veto_a_live_read():
    """WATCH earns no word, so it does not get a vote either."""
    tape = build_theme_tape(
        _hot_rotation("Semiconductors"), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "RE-RATING"),
                        _theme("memory_storage", "WATCH"),
                        _theme("semicap_equipment", "WATCH")))
    assert tape["rows"][0]["foresight"]["label_en"] == "re-rating"


# ── the shelf ───────────────────────────────────────────────────────────────
def _shelf(tape, label):
    return next((g for g in tape["foresight_shelf"] if g["label"] == label), None)


def test_staged_themes_off_the_heat_list_reach_the_shelf():
    tape = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("nuclear_power", "PRECIPICE (text)",
                               name="Nuclear & SMR Power", bottleneck_text_only=True),
                        _theme("ai_semiconductors", "RE-RATING",
                               name="AI Semiconductors")))
    assert _shelf(tape, "loading")["names_en"] == ["Nuclear & SMR Power"]
    assert _shelf(tape, "loading")["names_zh"] == ["核电与小型堆"]
    assert _shelf(tape, "re_rating")["names_en"] == ["AI Semiconductors"]


def test_a_theme_shown_as_a_row_is_never_also_on_the_shelf():
    """It is on the heat list by definition; the shelf would say the opposite."""
    tape = build_theme_tape(
        _hot_rotation("Semiconductors"), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "PRECIPICE",
                               name="AI Semiconductors")))
    assert tape["rows"][0]["foresight"] is not None
    assert tape["foresight_shelf"] == []


def test_an_unmapped_desk_theme_still_reaches_the_reader_by_name():
    """A mapping gap costs the chip, never the disclosure."""
    key = sorted(THEME_UNMAPPED)[0]
    tape = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme(key, "PRECIPICE", name="Unpairable Theme")))
    assert _shelf(tape, "loading")["names_en"] == ["Unpairable Theme"]


def test_stages_without_a_word_reach_neither_a_row_nor_the_shelf():
    tape = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("solar", "WATCH"),
                        _theme("cybersecurity", "GLUT-RISK")))
    assert tape["foresight_shelf"] == []
    assert tape["foresight_unconfirmed"] is False


# ── the numeric-confirmation disclosure (a CONDITION, never a constant) ─────
def test_a_text_only_stage_is_not_numerically_confirmed():
    tape = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("nuclear_power", "PRECIPICE (text)",
                               bottleneck_text_only=True)))
    assert tape["foresight_unconfirmed"] is True


def test_a_re_rating_stage_with_a_text_only_band_is_not_confirmed():
    """The leg a stage-string check alone would miss, and today's real state.

    RE-RATING carries no "(text)" qualifier, so on the stage string it reads as
    confirmed while its bottleneck band is language-only — which is exactly the
    shape site/basketdata/foresight_cascade.json ships for ai_semiconductors.
    """
    tape = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "RE-RATING",
                               bottleneck_text_only=True)))
    assert tape["foresight_unconfirmed"] is True


def test_the_disclosure_retires_itself_when_a_stage_becomes_confirmed():
    """The assertion that must not rot.

    Pinning "the panel says not-confirmed" would be a time bomb: it passes today
    and becomes a lie the night a numeric leg lights up. So the test pins the
    CONDITIONAL — a fully confirmed desk drops the clause and keeps the stance —
    which stays true in both eras.
    """
    confirmed = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("nuclear_power", "PRECIPICE",
                               name="Nuclear & SMR Power")))
    assert confirmed["foresight_unconfirmed"] is False
    assert _shelf(confirmed, "loading")["names_en"] == ["Nuclear & SMR Power"]

    html = _render(confirmed)
    assert "not confirmed by price or trading yet" not in html
    assert "价格与成交尚未确认" not in html
    # the stance survives either way — a shelf with no instruction is not a shelf
    assert "Watch — don’t chase." in html and "观望，勿追高。" in html


def test_one_unconfirmed_theme_is_enough_to_state_the_disclosure():
    mixed = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("nuclear_power", "PRECIPICE"),
                        _theme("solar", "PRECIPICE (text)",
                               bottleneck_text_only=True)))
    assert mixed["foresight_unconfirmed"] is True
    assert "not confirmed by price or trading yet" in _render(mixed)


def test_the_shipped_desk_read_is_disclosed_by_the_rule_not_by_a_pin():
    """Today every staged theme is an early read; assert the RULE reproduces it.

    This deliberately does not pin "zero confirmed" as a number — that would
    redden the day the desk's first numeric leg fires, which is a success and not
    a regression. It asserts that whatever the artifact says, the panel's flag
    agrees with the per-theme predicate.
    """
    from engine.theme_tape import _numerically_confirmed

    themes = [t for t in _shipped(DESK_ARTIFACT)["themes"]
              if STAGE_LABEL.get(t.get("stage")) is not None]
    assert themes, "the shipped desk carries no staged theme to check"
    tape = build_theme_tape(_rotation(), _standouts(), today=TODAY,
                            foresight=_shipped(DESK_ARTIFACT))
    assert tape["foresight_unconfirmed"] is any(
        not _numerically_confirmed(t) for t in themes)


# ── fail-open ───────────────────────────────────────────────────────────────
def test_no_desk_read_leaves_the_panel_exactly_as_it_was():
    """The layer is additive or it is nothing.

    The <style> block is unconditional (it is one static string), so the check
    that matters is on the MARKUP: with no desk read, not one shelf or chip
    element is emitted, and the page is byte-identical to the pre-join panel.
    """
    base = _render(build_theme_tape(_rotation(), _standouts(), today=TODAY))
    markup = re.sub(r"<style\b.*?</style>", "", base, flags=re.S | re.I)
    assert 'class="tt-shelf"' not in markup and 'class="tt-fs"' not in markup
    assert base == _render(build_theme_tape(_rotation(), _standouts(),
                                            today=TODAY, foresight=None))


@pytest.mark.parametrize("desk", [
    None, {}, {"themes": None}, {"themes": "nope"}, {"themes": [None, 7]},
    {"themes": [{"theme": "solar"}]},                        # no stage
    {"themes": [{"stage": "PRECIPICE"}]},                    # no key
    {"themes": [{"theme": "solar", "stage": "PRECIPICE"}]},  # no display name
])
def test_a_broken_desk_read_is_never_fatal(desk):
    tape = build_theme_tape(_rotation(), _standouts(), today=TODAY, foresight=desk)
    assert tape is not None and tape["foresight_shelf"] == []


def test_a_stale_desk_read_prints_nothing():
    """Filing language from three weeks ago is not evidence about tonight."""
    tape = build_theme_tape(
        _hot_rotation("Semiconductors"), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "PRECIPICE"),
                        asof="2026-06-01"))
    assert tape["rows"][0]["foresight"] is None
    assert tape["foresight_shelf"] == []


def test_the_desk_cannot_change_which_themes_appear_or_in_what_order():
    """Heat rank stays the only ordering. Display-tier means exactly this."""
    plain = build_theme_tape(_rotation(), _standouts(), today=TODAY)
    joined = build_theme_tape(
        _rotation(), _standouts(), today=TODAY,
        foresight=_desk(_theme("ai_semiconductors", "PRECIPICE"),
                        _theme("nuclear_power", "PRECIPICE (text)")))
    assert [r["name"] for r in plain["rows"]] == [r["name"] for r in joined["rows"]]
    for a, b in zip(plain["rows"], joined["rows"]):
        assert a["rank"] == b["rank"] and a["counts"] == b["counts"]
        assert a["stance"] == b["stance"] and a["quiet_sample"] == b["quiet_sample"]


# ── the surface ─────────────────────────────────────────────────────────────
def _joined():
    return build_theme_tape(
        _hot_rotation("Semiconductors", "Commodities Metals"), _standouts(),
        today=TODAY,
        foresight=_desk(
            _theme("ai_semiconductors", "RE-RATING", name="AI Semiconductors",
                   bottleneck_text_only=True),
            _theme("rare_earth_critical_min", "PRECIPICE (text)",
                   name="Rare Earth & Critical Minerals", bottleneck_text_only=True),
            _theme("nuclear_power", "PRECIPICE (text)", name="Nuclear & SMR Power",
                   bottleneck_text_only=True)))


def test_the_word_and_the_shelf_render_in_both_languages():
    html = _render(_joined())
    assert 'class="tt-fs"' in html and 'class="tt-shelf"' in html
    for token in ("loading up", "蓄势", "re-rating", "重估",
                  "Off the heat list", "不在热度榜上",
                  "Nuclear &amp; SMR Power", "核电与小型堆"):
        assert token in html, token


def test_the_english_word_does_not_read_as_a_progress_state():
    """"loading" beside a list of names reads as a list still arriving.

    The particle is the whole fix and it is one word long, so it is easy to lose
    to a well-meaning tidy-up. 蓄势 carries no such collision and is untouched.
    """
    assert FORESIGHT_LABELS["loading"] == ("loading up", "蓄势")


def test_no_stage_enum_value_ever_reaches_the_reader():
    """Doctrine Law 2 — the desk's state names are internal vocabulary.

    Scans the rendered text AND the hovers: the enum is what the two words above
    exist to replace, so a leak here is the feature failing its only content job.
    """
    html = _render(_joined())
    text = _visible_text(html) + " " + _tip_text(html)
    for slug in ("PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK", "WATCH",
                 "UNKNOWN", "foresight_cascade", "bottleneck", "fingerprint",
                 "text_only", "entry_ready", "THESIS"):
        assert slug not in text, f"stage vocabulary reached the reader: {slug}"


def test_the_word_is_uncoloured_and_takes_the_column_header_type():
    """No hue on the least-confirmed thing on the panel, and no new type.

    The chip is a label, so it speaks in the voice the panel already labels with
    (`.tt-k`). Any --ink-*/--up/--down here would paint the desk's read louder
    than the board states beside it.
    """
    css = _panel_css()
    chip = css.split(".tt-fs{")[1].split("}")[0]
    assert "font-size:10px" in chip and "font-weight:700" in chip
    assert "letter-spacing:.05em" in chip and "color:var(--muted)" in chip
    for coloured in ("--ink-up", "--ink-down", "var(--up)", "var(--down)"):
        assert coloured not in chip, f"the desk's word must carry no state ink: {coloured}"
    assert "text-transform:uppercase" not in chip, (
        "in caps 're-rating' is the desk's enum value verbatim on a glance tier")


def test_the_shelf_list_is_not_a_member_roster():
    """tier_preview.js collapses `#theme-tape .tt-names` to "N 只股票" (N stocks).

    The shelf holds THEMES, so being caught by that gate would print a false
    sentence in Chinese — and would hide the panel's disclosure from exactly the
    visitors with the least other context. It shares the flex declaration and
    nothing else.
    """
    src = (TMPL / "_theme_tape.html.j2").read_text()
    shelf = src.split('class="tt-shelf"')[1].split("{%- endif %}")[0]
    assert "tt-names" not in shelf, "the shelf roster is caught by the tier gate"
    assert "tt-load" in shelf
    css = _panel_css()
    assert ".tt-names,body.page-stocks.tt-load{display:flex" in css, (
        "the two lists must share ONE declaration — a second copy of the "
        "atomic-wrap fix will drift from the first")


def test_the_shelf_survives_the_phone_break():
    """#4488's flex fix is inherited, not re-implemented — and .tt-g flattens."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    block = src.split("@media (max-width:680px)")[1].replace(" ", "")
    assert ".tt-g{grid-template-columns:minmax(0,1fr)" in block
    assert ".tt-gk{text-align:left}" in block


def test_the_page_carries_the_desk_read_on_every_render_path():
    """build_site renders us_stocks TWICE — the second pass must not strip it.

    The one-build-lag fix rebuilds the tape from a fresher board; a rebuild that
    forgot the desk would show the shelf in a dry run and drop it from the page
    that actually ships.
    """
    src = (ROOT / "scripts" / "build_site.py").read_text()
    # Both call sites wrap across lines and nest calls two deep
    # (`json.loads(p.read_text())`), so walk the parens rather than pattern-match
    # a line: a regex that quietly matches nothing would make this gate vacuous.
    calls = []
    for m in re.finditer(r"\b(?:build_theme_tape|_btt)\(", src):
        depth, i = 0, m.end() - 1
        while i < len(src):
            depth += (src[i] == "(") - (src[i] == ")")
            i += 1
            if depth == 0:
                break
        calls.append(" ".join(src[m.start():i].split()))
    assert len(calls) >= 2, f"expected the first-pass AND the re-render call, got {calls}"
    missing = [c for c in calls if "foresight" not in c]
    assert missing == [], (
        f"a build_theme_tape call renders without the desk read: {missing}")


# ── the washout-turn group (W-D) ────────────────────────────────────────────
# The floor that picks the heat rows is a MOMENTUM floor, so the one shape it can
# never show is the one that matters most on a turn: down hard on the month, up on
# the week. Space Tech sat 28th of 41 and "lagging" on 2026-08-02 while its
# Satellites sleeve ran +2.03% against the market on the week after −14.17% on the
# month. These tests pin the group that fixes that, and — just as hard — pin that
# it changed nothing above it.

def _washed(theme_rs=None, sub_rs=None, name="Space Tech", zh="太空科技",
            sub="Satellites", sub_zh="卫星", **over):
    """A rotation with one hot theme and one washed-out floor-FAILER.

    `theme_rs` puts the turn shape on the theme itself; `sub_rs` puts it on the
    named subsector only — the two grains the group reads.
    """
    doc = _rotation()
    doc["themes"] = [
        doc["themes"][0],
        {"theme": name, "theme_zh": zh, "emerging_score": -0.485,
         "quadrant": "lagging", "rs": theme_rs or {"1W": -0.92, "1M": -15.05}},
    ]
    doc["subsectors"] = [
        doc["subsectors"][0],
        {"theme": name, "name": sub, "name_zh": sub_zh,
         "rs": sub_rs or {"1W": -3.16, "1M": -2.54},
         "members": [{"t": "RKLB"}, {"t": "ASTS"}, {"t": "APPF"}]},
    ]
    doc.update(over)
    return doc


TURN_SHAPE = {"1W": 4.5, "1M": -14.17}


def test_a_floor_failer_with_the_turn_shape_gets_a_row():
    """The whole point: a theme the momentum floor rejects becomes visible."""
    tape = build_theme_tape(_washed(theme_rs=TURN_SHAPE), _standouts(), today=TODAY)
    turns = tape["washout_turns"]
    assert [t["name"] for t in turns] == ["Space Tech"]
    assert turns[0]["name_zh"] == "太空科技"
    assert (turns[0]["turn_1w"], turns[0]["turn_1m"]) == (4.5, -14.17)
    # It carries its place on the ladder it just failed — the row's own admission.
    assert turns[0]["rank"] == 2 and tape["rank_of"] == 2
    # The theme's own figures earned it, so no sleeve is named.
    assert turns[0]["lead_en"] is None and turns[0]["lead_zh"] is None


def test_a_sleeve_can_earn_the_row_and_is_named_when_it_does():
    """Space Tech's real 2026-08-02 shape: the THEME's 1W is negative.

    A theme rolls up as the mean of its subsectors, so two sleeves still falling
    average the turning one away — measured over the 25 archived rotation days the
    theme-grain test alone never once selects Space Tech. Reading the sleeves is
    what makes the group able to see the case it was built for, and NAMING the
    sleeve is what stops the row overstating one fifth of a theme as the whole.
    """
    tape = build_theme_tape(
        _washed(theme_rs={"1W": -0.92, "1M": -15.05}, sub_rs={"1W": 2.03, "1M": -14.17}),
        _standouts(), today=TODAY)
    row = tape["washout_turns"][0]
    assert row["name"] == "Space Tech"
    assert row["lead_en"] == "Satellites" and row["lead_zh"] == "卫星"
    assert (row["turn_1w"], row["turn_1m"]) == (2.03, -14.17)


def test_both_legs_of_the_shape_are_required():
    """Down-and-still-down is not a turn; up-and-never-washed-out is not a washout."""
    for rs in ({"1W": -0.92, "1M": -15.05},      # washed out, not turning
               {"1W": 4.5, "1M": 3.0},           # turning, never washed out
               {"1W": 4.5, "1M": None},          # a missing leg is not a pass
               {"1W": None, "1M": -14.17}):
        tape = build_theme_tape(_washed(theme_rs=rs), _standouts(), today=TODAY)
        assert tape["washout_turns"] == [], rs


def test_the_thresholds_are_exclusive_at_the_boundary():
    """A guard that fires AT its own threshold is a different guard.

    Pinned because these two numbers are the group's entire selectivity: at the
    briefed thresholds exactly one theme-grain hit occurred in the 25 archived
    rotation days, so a silent slide from `>` to `>=` would not show up as an
    empty group — it would show up as a slightly fuller one nobody questions.
    """
    from engine.theme_tape import TURN_1M_MAX, TURN_1W_MIN

    exact = build_theme_tape(
        _washed(theme_rs={"1W": TURN_1W_MIN, "1M": TURN_1M_MAX}), _standouts(), today=TODAY)
    assert exact["washout_turns"] == []
    inside = build_theme_tape(
        _washed(theme_rs={"1W": TURN_1W_MIN + 0.01, "1M": TURN_1M_MAX - 0.01}),
        _standouts(), today=TODAY)
    assert [t["name"] for t in inside["washout_turns"]] == ["Space Tech"]


def test_the_group_is_capped_and_sorted_by_the_strongest_turn():
    from engine.theme_tape import TURN_N

    doc = _rotation()
    doc["themes"] = [doc["themes"][0]] + [
        {"theme": f"T{i}", "theme_zh": f"T{i}", "emerging_score": -1.0 - i,
         "quadrant": "lagging", "rs": {"1W": 2.5 + i, "1M": -14.0}}
        for i in range(5)
    ]
    doc["subsectors"] = [doc["subsectors"][0]] + [
        {"theme": f"T{i}", "name": "S", "members": [{"t": "APPF"}]} for i in range(5)
    ]
    turns = build_theme_tape(doc, _standouts(), today=TODAY)["washout_turns"]
    assert len(turns) == TURN_N == 3
    assert [t["name"] for t in turns] == ["T4", "T3", "T2"]      # 1W desc
    assert [t["turn_1w"] for t in turns] == [6.5, 5.5, 4.5]


def test_a_theme_on_the_heat_list_is_never_repeated_in_the_group():
    """A hot theme with the shape is ALREADY visible; printing it twice says
    the opposite of what the group means."""
    doc = _rotation()
    doc["themes"][0]["rs"] = {"1W": 9.0, "1M": -20.0}
    tape = build_theme_tape(doc, _standouts(), today=TODAY)
    assert [r["name"] for r in tape["rows"]] == ["Software"]
    assert [t["name"] for t in tape["washout_turns"]] == []


def test_no_qualifying_theme_means_no_group_at_all():
    """Honest-null: [] on the payload and NOTHING in the markup — no header,
    no empty box. A group that printed a best-available row on a night with no
    turn would be the forced ranking the Ignition Radar suspension forbids."""
    tape = _build()
    assert tape["washout_turns"] == []
    html = _render(tape)
    assert 'class="tt-turn"' not in html
    for token in ("Turning from washout", "洗盘转折"):
        assert token not in html, token


def test_a_dead_tape_still_prints_nothing_even_with_a_turn():
    """The panel's own floor outranks the group. No heat row → no panel, and a
    washout-turn cannot resurrect one on a tape that has nothing to say."""
    doc = _washed(theme_rs=TURN_SHAPE)
    doc["themes"][0]["emerging_score"] = -9.0       # kill the one hot theme
    doc["themes"][0]["quadrant"] = "lagging"
    assert build_theme_tape(doc, _standouts(), today=TODAY) is None


def test_the_group_cannot_touch_the_heat_rows():
    """The TOP_N selection is byte-identical with and without a qualifying turn.

    This is the fence that makes the group display-tier: it is computed AFTER the
    rows are final and reads nothing but the set of names already shown.
    """
    plain = build_theme_tape(_washed(), _standouts(), today=TODAY)
    turned = build_theme_tape(_washed(theme_rs=TURN_SHAPE), _standouts(), today=TODAY)
    assert plain["washout_turns"] == [] and turned["washout_turns"] != []
    assert plain["rows"] == turned["rows"]
    assert plain["rank_of"] == turned["rank_of"]


def test_the_row_narrates_members_through_the_same_machinery():
    """Same partition, same buckets, same total — one implementation, so the two
    groups cannot drift into describing the board differently."""
    tape = build_theme_tape(_washed(theme_rs=TURN_SHAPE), _standouts(), today=TODAY)
    row = tape["washout_turns"][0]
    assert set(row["counts"]) == set(BUCKETS)
    assert sum(row["counts"].values()) == row["n_members"] == 3
    assert row["n_on_board"] == row["n_members"] - row["counts"]["quiet"]
    # APPF is live on the fixture board; RKLB/ASTS are on no lane at all.
    assert [m["t"] for m in row["members"]["live"]] == ["APPF"]
    assert row["quiet_sample"] == ["RKLB", "ASTS"]


# ── the group's surface ─────────────────────────────────────────────────────
def _turned_html():
    return _render(build_theme_tape(
        _washed(theme_rs={"1W": -0.92, "1M": -15.05}, sub_rs={"1W": 2.03, "1M": -14.17}),
        _standouts(), today=TODAY))


def test_the_group_renders_its_label_and_figures_in_both_languages():
    html = _turned_html()
    assert 'class="tt-turn"' in html
    for token in ("Turning from washout — early, unconfirmed", "洗盘转折——早期，未确认",
                  "Satellites", "卫星", "+2.0%", "past week", "近一周"):
        assert token in html, token
    # The true minus, never the hyphen-minus, on a figure.
    assert "−14.2%" in html and "-14.2%" not in html


def test_the_group_carries_the_null_and_the_stance_once():
    """Law 5 + Law 1, and Law 4's "a constant belongs in one place": every row
    here is early for the same reason, so the reason is stated once."""
    text = _visible_text(_turned_html())
    assert text.count("Watch — don’t chase.") == 1
    assert text.count("观望，勿追高。") == 1
    for token in ("no measured edge", "没有经检验的优势证据"):
        assert token in text, token


def test_no_row_in_the_group_carries_a_buy_verb():
    """P2 — watch-lanes, never buy claims. The heat rows' stance table tops out
    at "act per row"; no row here has earned a verb, and the construction behind
    the group is a measured null."""
    # Bound the slice to the group itself: the panel FOOTNOTE below it legitimately
    # says "not at what to buy" / "而非买入对象", and a greedy split would read that
    # negation as a buy word and make this gate fail for the wrong reason.
    html = _turned_html()
    group = html.split('<div class="tt-turn">')[1].split('<hr class="tt-rule">')[0]
    for verb in ("act per row", "按行操作", "Buy", "买入", "get ready", "做好准备"):
        assert verb not in group, f"the washout-turn group must not say {verb!r}"
    assert "tt-stance" not in group


def test_the_group_leaks_no_machine_vocabulary():
    html = _turned_html()
    text = _visible_text(html) + " " + _tip_text(html)
    hits = [b for b in BANNED_ON_ANY_TIER if b in text]
    assert hits == [], f"banned vocabulary reached the reader: {hits}"
    for slug in ("washout_turns", "emerging_score", "lagging", "quadrant",
                 "turn_1w", "rs_1m", "osc_slope", "Trough"):
        assert slug not in text, f"machine vocabulary reached the reader: {slug}"


def test_the_group_reuses_the_row_idiom_rather_than_inventing_a_second_one():
    """A turn row must be the SAME object as a heat row — same seven-column grid
    under the same header, same member groups — or the two halves of one panel
    drift apart. Only the label, the figures line and the reason are new."""
    src = (TMPL / "_theme_tape.html.j2").read_text()
    group = src.split('<div class="tt-turn">')[1].split("{#- THE SHELF")[0]
    for shared in ("tt-i", "tt-s", "tt-row", "tt-det", "tt-g", "tt-gk",
                   "tt-quiet", "tt-c", "tt-v"):
        assert shared in group, f"the turn row must reuse .{shared}"
    # .tt-names / .tt-sym moved into the tt_slot/tt_mem/tt_quiet macros when the
    # member lists gained a server-side tier gate (docs/TIER_PREVIEW_PATTERN.md),
    # so "the SAME object" is now provable more directly than by class name: the
    # turn row must reach its member lists through the very macros the heat row
    # uses, and there must be no second inline copy of that markup anywhere.
    heat = src.split("{#- THE WASHOUT-TURN GROUP")[0]
    for macro in ("tt_slot(", "tt_mem(", "tt_quiet("):
        assert macro in group, f"the turn row must reuse {macro})"
        assert macro in heat, f"the heat row must reuse {macro})"
    assert src.count('<span class="tt-names"') == 2, (
        "tt-names must be emitted ONLY by tt_slot (its two gated/ungated arms) — "
        "a third inline copy is the drift this test exists to catch")
    assert src.count('class="tt-sym"') == 2, (
        "tt-sym must be emitted ONLY by tt_mem and tt_quiet")


def test_the_group_takes_no_state_ink():
    """It is the least-confirmed thing on the panel; it must not be the loudest.
    The same argument that keeps the foresight word grey."""
    css = _panel_css()
    for cls in ("tt-turn{", "tt-turn-hd{", "tt-turn-line{", "tt-turn-why{"):
        block = css.split(cls)[1].split("}")[0]
        for coloured in ("--ink-up", "--ink-down", "var(--up)", "var(--down)"):
            assert coloured not in block, f".{cls[:-1]} must carry no state ink"
