"""tests/test_act_now_board_icons.py — the US Act-Now board's monoline mark contract.

Doctrine §5.8 (2026-08-03): "Emoji are not UI icons — they read as clip-art on white and
render inconsistently headless; use the monoline set in templates/_icons.html.j2." The
board's lane heads, row marks, bottoming-watch marks, legend and hover-card marks were
swept off emoji onto that set; these fences keep them there.

The watch surface moved between #4729 (an inline `.bw-*` shelf in this board) and #4716
(templates/_us_bottoming_watch.html.j2, a full-width strip that reuses the board's own
.acth-icon / .ai-bdg chrome). The fences below judge the strip as the board renders it —
via `bottoming=`, the host contract build_sector_central passes — so its two marks are
counted in the same .ai-bdg / .acth-icon totals as the lanes above it.

Every fence judges the RENDERED board, not the source. A source grep can only prove a
string is absent from one file — it cannot catch an icon that renders as escaped text
(`&lt;svg`), a rule that never reaches the element it names, or a twin that drifted. The
one source-level fence left (the CSS twin) is a byte comparison, which is what it is for.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEMPLATES = ROOT / "templates"
ACT_BOARD = TEMPLATES / "_us_act_now_board.html.j2"
DASHBOARD = TEMPLATES / "dashboard.html.j2"
ICONS = TEMPLATES / "_icons.html.j2"

# The emoji this board shipped before the sweep. 🏛/🧩 were the sector/theme row + shelf
# marks, 🟢🔵🏃🟠⚪ the five lane heads, ⚠ the policy-shock chip.
SWEPT = ("\U0001f3db", "\U0001f9e9", "\U0001f7e2", "\U0001f535",
         "\U0001f3c3", "\U0001f7e0", "⚪", "⚠")

# ✓ and ★ are text glyphs, not emoji: they carry the gate and model-book marks in the
# legend and on theme rows, and they are NOT part of the sweep.
KEPT_GLYPHS = ("✓", "★")


def _render(bottoming=None, **board) -> str:
    """Render the shipped include with a synthetic payload, autoescape ON.

    autoescape=True is not incidental — it is the condition the legend's Markup capture
    has to survive, and both hosts (build_site, build_sector_central) render this way.

    `bottoming` is a TOP-LEVEL var, not an action_board key: the watch strip is its own
    partial (_us_bottoming_watch.html.j2) and self-hides when the host passes nothing,
    which is exactly how us_stocks renders this same board.
    """
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals.update(t=lambda en, zh="": en, tr=lambda en: en, td=lambda en: en)
    vm = {"buy_now": [], "buy_soon": [], "on_the_run": [], "take_profits": [],
          "hold": [], "avoid": [], "more": {}, "notable": []}
    vm.update(board)
    return env.get_template(ACT_BOARD.name).render(action_board=vm, bottoming=bottoming)


def _sector_row(**over):
    row = {"kind": "sector", "ticker": "XLF", "name": "Financials", "label": "RALLY ON",
           "href": "sectors/XLF.html", "stat_en": "uptrend", "stat_zh": "上升趋势"}
    row.update(over)
    return row


def _theme_row(**over):
    row = {"kind": "theme", "slug": "ai_software", "name": "AI Software",
           "name_zh": "AI 软件", "href": "basket/ai_software.html", "score": 68,
           "reco": "accumulate", "label": "ACCUMULATE", "validated": False}
    row.update(over)
    return row


def _strip_payload():
    """The bottoming payload in the shape build_sector_central passes to the page.

    One BASKET and one SECTOR row, so both strip marks (diamond + sector) are drawn.
    """
    from engine.us_act_now import assemble_bottoming_watch
    out = assemble_bottoming_watch(
        [{"id": "b-uranium_miners", "kind": "basket", "name": "Uranium", "phase": "Trough",
          "pos": 0.8, "osc_slope": 0.4, "signal": None, "above200d": False,
          "timing_state": "COUNTERTREND BOUNCE"},
         {"id": "xlu", "kind": "sector", "name": "Utilities", "phase": "Trough",
          "pos": 6.7, "osc_slope": 5.0, "signal": "BUY", "above200d": True,
          "timing_state": "COUNTERTREND BOUNCE"}],
        reduce_ids=["uranium_miners"])
    return {"bottoming_watch": out["bottoming_watch"],
            "dual_read_ids": out["dual_read_ids"],
            "recovering_ids": out["recovering_ids"],
            "bottoming_authority": out["authority"],
            "recovering_rendered": False}


def _full_board() -> str:
    """Every mark-bearing surface at once: five lanes, both row kinds, the watch strip."""
    return _render(buy_now=[_theme_row()], buy_soon=[_sector_row()],
                   on_the_run=[_theme_row(slug="mag7", name="Magnificent Seven")],
                   take_profits=[_sector_row(ticker="XLE", name="Energy")],
                   hold=[_sector_row(ticker="XLU", name="Utilities")],
                   bottoming=_strip_payload())


def _board_region(html: str) -> str:
    """The panel only — the include's <style> block legitimately mentions class names."""
    i = html.index('id="action-board"')
    return html[i:]


# ── the sweep itself ─────────────────────────────────────────────────────────
def test_no_swept_emoji_survives_anywhere_in_the_rendered_board():
    html = _full_board()
    for e in SWEPT:
        assert e not in html, (
            f"emoji {e!r} is back on the act board — doctrine §5.8: emoji are not UI icons, "
            f"extend templates/_icons.html.j2 instead"
        )


def test_the_shock_chip_alert_is_an_icon_not_an_emoji():
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals.update(t=lambda en, zh="": en, tr=lambda en: en, td=lambda en: en)
    vm = {"buy_now": [], "buy_soon": [], "on_the_run": [], "take_profits": [],
          "hold": [], "avoid": [], "more": {}, "notable": []}
    html = env.get_template(ACT_BOARD.name).render(
        action_board=vm, shock_state={"active": True, "expires": "2026-08-11"})
    assert "Market shock active" in html, "the shock chip did not render — this fence scanned nothing"
    assert "⚠" not in html
    assert 'class="ab-shock-ic"' in html and "ic-svg" in html


def test_the_gate_check_and_model_star_stay_text_glyphs():
    """They are typography, not emoji — the sweep must not have taken them with it."""
    html = _render(buy_now=[_theme_row(validated=True, book_wt=0.12)])
    for g in KEPT_GLYPHS:
        assert g in html, f"{g!r} disappeared — it is a text glyph, not part of the sweep"


# ── every mark surface actually draws an svg ─────────────────────────────────
# 6 lane heads = the five action lanes + the bottoming-watch strip's own header;
# 7 row marks = five board rows + the strip's two. The strip reuses these wrappers
# rather than carrying its own, so a strip that lost its marks shows up as a
# short count here — the same fence that guards the lanes guards it.
@pytest.mark.parametrize("wrapper,count", [("acth-icon", 6), ("ai-bdg", 7)])
def test_every_mark_wrapper_contains_a_rendered_svg(wrapper, count):
    region = _board_region(_full_board())
    found = re.findall(rf'<span class="{wrapper}"[^>]*>\s*<svg class="ic-svg"', region)
    assert len(found) == count, (
        f"expected {count} .{wrapper} marks each wrapping an <svg class=\"ic-svg\">, "
        f"found {len(found)} — a mark rendered as text or the wrapper was renamed"
    )


def test_the_old_emoji_class_name_is_gone_from_both_css_copies():
    """.acth-emoji was renamed .acth-icon; a stale copy would style nothing, silently."""
    for f in (ACT_BOARD, DASHBOARD):
        assert "acth-emoji" not in f.read_text(encoding="utf-8"), f"{f.name} still says acth-emoji"


def test_the_hover_card_marks_are_icons_for_both_row_kinds():
    """dc_card's 'mark' is passed through {{ }} — a bare string would print, an icon draws."""
    region = _board_region(_full_board())
    marks = re.findall(r'<span class="row-pop-mark row-pop-mark--(\w+)"[^>]*>(.{0,40})', region)
    assert marks, "no hover-card marks rendered — this fence scanned nothing"
    kinds = {k for k, _ in marks}
    assert kinds == {"sector", "theme"}, f"expected both card kinds, got {kinds}"
    for kind, body in marks:
        assert '<svg class="ic-svg"' in body, (
            f"the {kind} hover card's mark rendered as {body!r}, not an icon"
        )


# ── the two ways an icon silently fails ──────────────────────────────────────
def test_the_legend_icons_are_markup_not_escaped_text():
    """The legend is built with {% set %}…{% endset %} so it survives autoescape.

    Hand `help()` a plain string containing the macro output and Jinja escapes it: the
    reader gets a literal `<svg …>` printed into the tooltip. That failure renders, so
    only an escape-aware fence catches it.
    """
    region = _board_region(_full_board())
    tip = region[region.index('class="help"'):]
    tip = tip[:tip.index("</span></span>") + 14]
    assert "&lt;svg" not in tip, (
        "the legend printed escaped markup — help() was handed a plain string instead of "
        "a {% set %} Markup capture"
    )
    en = tip[tip.index('class="l-en"'):tip.index('class="l-zh"')]
    zh = tip[tip.index('class="l-zh"'):]
    for lang, part in (("EN", en), ("ZH", zh)):
        assert part.count('<svg class="ic-svg"') == 2, (
            f"the {lang} legend must show the same two marks the rows show "
            f"(sector + theme), found {part.count('<svg class=\'ic-svg\'')}"
        )
    for label in ("板块基金", "主题"):
        assert f"</svg> {label}" in zh, f"the ZH legend lost {label!r} — EN/ZH parity is law"
    for label in ("sector fund", "theme"):
        assert f"</svg> {label}" in en, f"the EN legend lost {label!r}"


def test_the_board_never_emits_a_bare_ic_svg_rule():
    """sector_central.html.j2 scopes its own `.ic-svg` under #si-confluence.

    A global `.ic-svg { … }` shipped from this panel would fight its host's copy on one
    of the two pages that render it. Explicit selectors only.
    """
    css = re.sub(r"/\*.*?\*/", "", ACT_BOARD.read_text(encoding="utf-8"), flags=re.S)
    for rule in css.split("}"):
        if "{" not in rule:
            continue
        selectors = [s.strip() for s in rule.split("{")[0].split(",")]
        assert ".ic-svg" not in selectors, (
            "bare `.ic-svg` rule in the board CSS — scope it to the mark wrapper "
            "(.ai-bdg .ic-svg, .acth-icon .ic-svg, …) so it cannot fight a host page"
        )


def test_the_hover_card_mark_rule_is_not_scoped_to_the_board_id():
    """theme.js clones the card onto document.body, OUTSIDE #action-board.

    `#action-board .row-pop-mark .ic-svg` styles the hidden .rp-src source and misses the
    card the reader actually sees — an unsized icon in the visible popover.
    """
    css = re.sub(r"/\*.*?\*/", "", ACT_BOARD.read_text(encoding="utf-8"), flags=re.S)
    hits = re.findall(r"[^,{}]*\.row-pop-mark[^,{}]*", css)
    assert hits, "no .row-pop-mark icon rule at all — the hover-card mark is unsized"
    assert not any("#action-board" in h for h in hits), (
        "the .row-pop-mark icon rule is id-scoped; theme.js appends the card to "
        "document.body, so that rule can never reach the visible card"
    )


# ── the two copies of the board CSS, and the icon set itself ─────────────────
def test_the_icon_css_block_is_byte_identical_in_both_copies():
    """dashboard.html.j2 carries a verbatim twin of this board's CSS (its own header says
    so). A rule added to one copy and not the other ships a board that looks different
    depending on which page you opened."""
    start = "/* ── Monoline marks (doctrine §5.8"
    end = ".acth-icon { display: flex;"

    def block(p):
        s = p.read_text(encoding="utf-8")
        i = s.index(start)
        j = s.index(end, i)
        return s[i:s.index("}", j) + 1]

    assert block(ACT_BOARD) == block(DASHBOARD), (
        "the board's icon CSS drifted between _us_act_now_board.html.j2 and its verbatim "
        "twin in dashboard.html.j2"
    )


def test_the_sector_glyph_exists_and_is_not_mirrored_into_subsectors_js():
    """The subsectors.js ICON_PATHS mirror exists for glyphs THAT FILE draws client-side.

    `sector` is server-drawn only; copying it there would create a second definition with
    no reader, free to rot out of step with this one.
    """
    icons = ICONS.read_text(encoding="utf-8")
    m = re.search(r"'sector':\s*'([^']+)'", icons)
    assert m, "the 'sector' glyph is gone from templates/_icons.html.j2"
    path = m.group(1)
    assert path.count("<line") == 4 and path.count("<path") == 1, (
        "the sector glyph changed shape: it is a pediment + 3 columns + a base line, "
        "sized so the columns stay separated at the 13px it renders at in a row mark"
    )
    js = (TEMPLATES / "subsectors.js").read_text(encoding="utf-8")
    mirror = re.search(r"ICON_PATHS\s*=\s*\{(.*?)\n\s*\};", js, re.S)
    assert mirror, "subsectors.js no longer defines ICON_PATHS — re-point this fence"
    assert "sector" not in mirror.group(1) and path not in js, (
        "'sector' was mirrored into subsectors.js — that mirror is only for glyphs "
        "subsectors.js draws itself, and a second definition with no reader rots"
    )
