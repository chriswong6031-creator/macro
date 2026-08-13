"""The etfs.html tier gate — the split IS the boundary.

etfs.html is a 13F fund-conviction desk: which stocks tracked managers are
accumulating, ranked by cross-fund agreement, with an explicit "what to do"
stance column. Roughly 55% of its bytes are graded output, so unlike the two
Special Situations shells (which W1a merely re-classified) this page had to be
SPLIT before it could go anonymous-public. What ships free is context and honest
totals — the rotation backdrop, the whole fund coverage directory, the counts —
and ZERO stock rows: both boards are best-first, and previewing a best-first
board hands over its head, which is the part people pay for.

Two layers, deliberately:

* the SPLIT is proven hermetically (fake rows, real templates), so the contract
  holds even before a render lane has rebaked the desk;
* the SHIPPED BYTES are then checked against the same invariant — no row the
  paid payload carries may also sit in the free shell.

The second layer skips (loudly) until the desk has been rebaked in the gated
shape, because the baked page on main lags a template change by one render.

Kept import-light on purpose: this runs in ci.yml's `tier-gate` job, whose venv
is `pytest pyyaml jinja2 fastapi httpx`. Never import scripts.build_site here —
it pulls numpy/pandas/plotly and would turn the whole job into an error.

See docs/TIER_PREVIEW_PATTERN.md and
research/seo_supercharge/W2_HEATMAP_ETFS_PREVIEW_SPEC.md (Part B).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "site" / "etfs.html"
PAYLOAD = ROOT / "site" / "premiumdata" / "etfs.json"

# ── row identity ────────────────────────────────────────────────────────────
# A row's identity is its whole rendered body, NOT its ticker. Keying on the
# ticker would be wrong in BOTH directions here:
#   * one ticker legitimately appears on the consensus board AND on a per-fund
#     add row AND in the trims shelf — three different rows, same company, so a
#     ticker on both sides of the wall is not a leak;
#   * the coverage directory is FREE and lists 77 fund tickers (XLK, QQQ,
#     ARKK, SMH…), several of which are also names on the board — a naive
#     ticker scan would cry leak on the free tier's own anchor content.
BOARD_ROW = re.compile(r'<div class="cb-row">(.*?)<div class="cb-stance-cell">', re.S)
ADD_ROW = re.compile(r'<td class="fundcell">(.*?)</td>', re.S)
FRESH_CARD = re.compile(r'<div class="fc" style=(.*?)<div class="fc-foot">', re.S)


def _keys(pat: re.Pattern, html: str) -> list[str]:
    """Whitespace-normalised identity of every row `pat` finds in `html`."""
    return [" ".join(m.group(1).split()) for m in pat.finditer(html)]


def _env():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.globals.update(td=lambda en: en, tr=lambda en: en,
                       clean_name=lambda n: n or "")
    return env


# ── fixtures ────────────────────────────────────────────────────────────────

def _stance(tone: str = "watch") -> dict:
    return {"tone": tone, "en": "Watch — don't chase", "zh": "观望 — 勿追",
            "why": {"en": "why", "zh": "为什么"}}


def _fav(ticker: str, i: int = 0) -> dict:
    return {"ticker": ticker, "name": f"{ticker} Inc", "sector": "Technology",
            "n_accum": 3, "n_trim": 0, "n_new": 1, "n_exit": 0, "contested": False,
            "is_active_any": True, "net_conviction_pp": 2.0 - i * 0.1,
            "funds": [{"fund": "ARKK", "conviction_pp": 0.9}], "stance": _stance()}


def _add(ticker: str, etf: str = "ARKK") -> dict:
    return {"ticker": ticker, "name": f"{ticker} Inc", "etf": etf, "category": "Tech",
            "is_active": True, "is_new": True, "conviction_pp": 0.75,
            "weight_series": [1.0, 1.2, 1.4], "stance": _stance()}


def _trim(ticker: str, etf: str = "XLK") -> dict:
    return {"ticker": ticker, "name": f"{ticker} Inc", "etf": etf, "category": "Tech",
            "is_exit": True, "conviction_pp": -0.4,
            "weight_series": [1.4, 1.1, 0.8], "stance": _stance("trim")}


def _fresh(ticker: str) -> dict:
    return {"ticker": ticker, "name": f"{ticker} Inc", "n_funds": 2,
            "conviction_pp": 1.1, "funds": [{"fund": "ARKK", "is_active": True}],
            "stance": _stance()}


_ROTATION = {
    "risk": {"label": {"en": "RISK-ON", "zh": "风险偏好"}, "tilt": 0.3, "tone": "lift",
             "read": {"en": "credit and cyclicals leading", "zh": "信用与周期领先"},
             "legs": [{"label": {"en": "Credit vs Duration", "zh": "信用 vs 久期"},
                       "dir": 1, "chg20": 3.6}]},
    "sector": {"rows": [{"ticker": "XLV", "label": {"en": "Health Care", "zh": "医疗"},
                         "mom60": 8.4, "rank": 1}], "mom_max": 8.4},
    "style": [{"label": {"en": "Small vs Large", "zh": "小盘 vs 大盘"},
               "lead": {"en": "large leading", "zh": "大盘领先"},
               "tilt": -1, "chg20": -2.0}],
    "as_of": "2026-07-31",
    "disclaimer": {"en": "Rotation context — how style, risk and sector ETFs have "
                         "been trading. Descriptive, never a buy list.",
                   "zh": "轮动背景 —— 风格、风险与行业 ETF 的近期走势。描述性，非买入清单。"},
}
# The apostrophe is U+2019, byte-for-byte as engine/etf_board._T5_STANCE ships
# it — an ASCII ' would be autoescaped to &#39; and this fixture would then be
# testing markup the page never emits.
_T5 = {"tone": "u", "head": {"en": "Risk-on tape", "zh": "风险偏好行情"},
       "rest": {"en": "credit and cyclicals lead. Watch, don’t chase.",
                "zh": "信用与周期领先。观望，勿追。"}}
_COVERAGE = [
    {"fund": "ARKK", "fund_name": "ARK Innovation ETF", "is_active": True,
     "category": "Innovation", "n_snapshots": 412, "latest_asof": "2026-08-02",
     "stale_days": 1, "unofficial": False},
    {"fund": "IWM", "fund_name": "iShares Russell 2000 ETF", "is_active": False,
     "category": "Small-cap", "n_snapshots": 96, "latest_asof": "2026-07-28",
     "stale_days": 6, "unofficial": True},
]
_GRADED_TILE = {"k": {"en": "Strongest consensus", "zh": "最强共识"}, "v": "AAA",
                "m": {"en": "3 funds building", "zh": "3 只基金增持"},
                "tone": "lift", "stance": _stance()}
_FREE_TILE = {"k": {"en": "On the board", "zh": "上榜个股"}, "v": "3",
              "m": {"en": "names at least two funds are building at once",
                    "zh": "至少两只基金同时增持的个股"}, "tone": "link"}
_OTHER_TILES = [
    {"k": {"en": "Fresh conviction", "zh": "全新建仓"}, "v": "17",
     "m": {"en": "brand-new positions this cycle", "zh": "本轮全新建立的仓位"},
     "tone": "accent"},
    # `v` is the bilingual pair, exactly as board_context now emits it — a bare
    # "RISK-ON" string here once mirrored (and so protected) the zh leak.
    {"k": {"en": "Market backdrop", "zh": "市场环境"},
     "v": {"en": "RISK-ON", "zh": "风险偏好"},
     "m": _ROTATION["risk"]["read"], "tone": "lift"},
]

FAVORED = [_fav(t, i) for i, t in enumerate(("AAA", "BBB", "CCC"))]
ADDS = [_add(t) for t in ("DDD", "EEE")]
TRIMS = [_trim(t) for t in ("FFF",)]
FRESH = [_fresh("GGG")]


def _board(*, gated: bool) -> dict:
    return {
        "verdict": None if gated else {"en": "Managers are building into tech.",
                                       "zh": "经理人正在科技上积累信念。"},
        "stance": _T5,
        "coverage": {"funds": 2, "active": 1},
        "tiles": ([_FREE_TILE] + _OTHER_TILES) if gated
                 else ([_GRADED_TILE] + _OTHER_TILES),
        "fresh": [] if gated else FRESH,
        "rotation": _ROTATION,
        "scale": {"consensus_pp": 2.0},
    }


def _gate(**over) -> dict:
    g = {"tier": "essential", "payload": "/premiumdata/etfs.json",
         "total": len(FAVORED), "preview": 0, "locked": len(FAVORED),
         "n_buys": len(ADDS), "n_funds": 1, "n_fresh": 1, "has_fresh": True}
    g.update(over)
    return g


def _render(*, gated: bool, gate_over: dict | None = None,
            favored=None, adds=None, trims=None, board=None) -> str:
    """Render the shell the way the builder does.

    `favored`/`adds`/`trims`/`board` are overridable so a test can render the
    ADVERSARIAL case — a gate set AND the graded rows handed in anyway — which is
    what pins the TEMPLATE's own contract. Without that, "the gated shell has no
    rows" only ever restates that this helper passed empty lists, and the guard
    is vacuous the moment the builder stops nulling them.
    """
    env = _env()
    gate = _gate(**(gate_over or {})) if gated else None
    if favored is None:
        favored = [] if gated else FAVORED
    if adds is None:
        adds = [] if gated else ADDS
    if trims is None:
        trims = [] if gated else TRIMS
    return env.get_template("etfs.html.j2").render(
        favored=favored, accumulation=adds, trims=trims,
        coverage=_COVERAGE, pulse={},
        board=board if board is not None else _board(gated=gated), gate=gate,
        generated_utc="2026-08-03 12:00")


def _payload_blocks() -> dict[str, str]:
    """The four paid blocks, rendered from the SAME partials the shell includes."""
    env = _env()
    return {
        "board_html": env.get_template("_etf_board_rows.html.j2").render(
            rows=FAVORED, scale=2.0),
        "accumulation_html": env.get_template("_etf_accumulation_rows.html.j2").render(
            rows=ADDS),
        "fresh_html": env.get_template("_etf_fresh_cards.html.j2").render(rows=FRESH),
        "trims_html": env.get_template("_etf_trim_rows.html.j2").render(rows=TRIMS),
    }


# ── the split ───────────────────────────────────────────────────────────────

def test_gated_shell_carries_no_graded_row():
    """The whole point: the free document does not CONTAIN the paid rows.

    Not hidden, not blurred, not tier-checked in JS — absent. A client-side hide
    is one view-source away from being no gate at all.

    Rendered ADVERSARIALLY: the gate is set AND every graded list is handed in
    anyway. That is the invariant the template owns. Passing empty lists and then
    asserting the output is empty would restate the fixture, not the contract —
    it survived a mutation that gutted the gate arm entirely.

    (The hero TILES are deliberately not part of this: which tiles exist is a
    builder decision, because choosing the replacement needs len(favored). That
    half is pinned by test_builder_replaces_the_graded_hero_tile below and by the
    shipped-byte check.)
    """
    shell = _render(gated=True, favored=FAVORED, adds=ADDS, trims=TRIMS)
    paid = _payload_blocks()
    for name, pat, key in (("consensus board", BOARD_ROW, "board_html"),
                           ("per-fund adds", ADD_ROW, "accumulation_html"),
                           ("fresh conviction", FRESH_CARD, "fresh_html")):
        locked = set(_keys(pat, paid[key]))
        assert locked, f"{name}: fixture produced no rows — vacuous test"
        assert not locked & set(_keys(pat, shell)), f"{name} rows leaked into the free shell"
    # trims ship a distinctive negative-conviction cell
    assert '<span class="conv d">' not in shell
    for ticker in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"):
        assert ticker not in shell, f"{ticker} is withheld content but reached the shell"
    # and the gate furniture is what stands in their place
    assert 'class="cb-ghosts"' in shell and 'class="tier-wall"' in shell


def test_gated_shell_withholds_the_hero_verdict_and_the_graded_tile():
    """T-B1: the hero's graded tile is REPLACED by an honest total, not hidden.

    The verdict line summarises the walled board and the first tile is its head
    (a ticker plus a stance pill), so both are paid. The replacement is a count,
    which is deterministic and non-graded, and it means the page never opens on
    a grey skeleton.

    Adversarial again: the board handed in still CARRIES its verdict, so this
    pins the template's refusal rather than the builder's nulling.
    """
    shell = _render(gated=True, board=dict(_board(gated=True),
                                           verdict={"en": "Managers are building into tech.",
                                                    "zh": "经理人正在科技上积累信念。"}))
    assert "Managers are building into tech" not in shell
    assert "Strongest consensus" not in shell
    assert "On the board" in shell and "上榜个股" in shell
    assert 'class="tile t-link"' in shell
    # …and the free page still answers "so what do I do?" (Doctrine Law 1)
    assert "Risk-on tape" in shell and "风险偏好行情" in shell
    assert "Watch, don’t chase." in shell and "观望，勿追。" in shell


def test_gated_shell_keeps_the_whole_free_tier():
    """Context and totals are free — and they have to actually be there, or the
    page is a wall with a headline, which is the soft-404 shape we are undoing."""
    shell = _render(gated=True)
    # the fund coverage directory: every tracked fund, open by default (T-B3)
    assert "ARK Innovation ETF" in shell and "iShares Russell 2000 ETF" in shell
    assert "<details open>" in shell, "the coverage shelf must not ship collapsed"
    # the rotation backdrop, in full
    assert "Health Care" in shell and "Small vs Large" in shell
    assert "Credit vs Duration" in shell
    # honest totals + the disclosure footer ("&" arrives autoescaped)
    assert "curated &amp; active funds" in shell
    assert "How to read this" in shell
    # the wall itself, bilingual, with one ask and one explanation
    assert 'id="etf-tier-wall"' in shell and 'id="etf-board-note"' in shell
    assert shell.count('class="tier-wall"') == 1, "exactly ONE wall on this page"
    assert "are open to members" in shell and "笔买入向会员开放" in shell
    assert "See plans" in shell and "查看方案" in shell
    assert "7-day Pro trial · cancel anytime" in shell and "Pro 7 天试用 · 随时取消" in shell
    assert 'id="etf-tw-signin"' in shell


def test_builder_replaces_the_graded_hero_tile():
    """T-B1, pinned where it is actually decided.

    The template renders whatever tiles it is handed — it cannot know that a tile
    VALUE is a ticker. Choosing the replacement needs len(favored), so the
    substitution lives in scripts/build_site.build_etf_page, and this is the test
    that holds it. Needs the page stack, so it skips on the import-light
    tier-gate lane and runs in the full packs.
    """
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")
    import sys
    sys.path.insert(0, str(ROOT))
    from scripts.build_site import _etf_free_tile

    tile = _etf_free_tile(40)
    assert tile["v"] == "40", "the free tile is a COUNT, never a name"
    assert tile["k"]["en"] == "On the board" and tile["k"]["zh"] == "上榜个股"
    assert "stance" not in tile, "a stance pill on the free tile would be graded output"
    assert tile["tone"] == "link", (
        "a count is not a direction — an up/down tone would flip under 中文")
    # deterministic: same input, same tile, no ordering exposed
    assert _etf_free_tile(40) == tile


def test_ungated_shell_keeps_every_row_and_no_gate_furniture():
    shell = _render(gated=False)
    paid = _payload_blocks()
    assert len(_keys(BOARD_ROW, shell)) == len(FAVORED)
    assert set(_keys(BOARD_ROW, shell)) == set(_keys(BOARD_ROW, paid["board_html"]))
    assert 'class="tier-wall"' not in shell
    assert 'class="gate-pill"' not in shell
    assert 'class="cb-ghosts"' not in shell
    assert 'id="etf-board-note"' not in shell
    assert "Strongest consensus" in shell
    assert "Managers are building into tech" in shell
    # no stance line on the entitled build — the verdict is the hero read there
    assert 'class="stance-line"' not in shell
    # and no dead hydration script on a page with nothing to hydrate
    assert "attempt-hydrate" not in shell


def test_coverage_shelf_opens_on_BOTH_builds():
    """T-B3 ruled the <details> default state UNIFIES open.

    A collapsed block may never be crawled, and the free tier's substance is
    exactly this directory — but the two builds must not differ structurally
    beyond the wall, so the entitled page opens it too.
    """
    for gated in (True, False):
        assert "<details open>" in _render(gated=gated), f"gated={gated}"


def test_partials_are_the_one_source_for_both_sides():
    """The payload and the entitled shell must render from the SAME partial.

    Checked on the SOURCE, not on the output. Comparing rendered partial markup
    against a shell that {% include %}s that very partial is a tautology — both
    sides move together, so it survives any edit to the partial (proven: a
    mutation to the rank markup left the output-comparison version green). What
    actually prevents drift is that the shell owns NO second copy of the row
    markup, so this asserts exactly that.
    """
    shell_src = (ROOT / "templates" / "etfs.html.j2").read_text(encoding="utf-8")
    for partial, marker in (
        ("_etf_board_rows.html.j2", '<div class="cb-row">'),
        ("_etf_accumulation_rows.html.j2", '<td class="fundcell">'),
        ("_etf_fresh_cards.html.j2", '<div class="fc-top">'),
        # marker was '<span class="sh-ic">🔻</span>' until 2026-08-12: a decorative
        # emoji is the WORST possible anti-drift marker, because a doctrine §5.8
        # sweep removes it estate-wide and this guard silently reports "vacuous"
        # rather than the drift it exists to catch. Anchored on structure instead.
        ("_etf_trim_rows.html.j2", '<span class="mini exit"'),
    ):
        assert f'{{% include "{partial}" %}}' in shell_src, (
            f"the shell must render {partial}, not its own copy of those rows")
        assert marker not in shell_src, (
            f"{partial}'s row markup is duplicated inside etfs.html.j2 — one of "
            "the two copies will drift, and only one of them feeds the payload")
        assert marker in (ROOT / "templates" / partial).read_text(encoding="utf-8"), (
            f"{partial} no longer contains {marker!r} — this guard just went vacuous")
    # the shared macros likewise have exactly one home
    assert '{% from "_etf_macros.html.j2" import' in shell_src
    assert "{% macro stance(" not in shell_src


# ── the empty-state trap ────────────────────────────────────────────────────

def test_gated_build_never_prints_building_over_content_that_exists():
    """A gated shell showing "Building — …" over 40 real rows is a lie told to
    the visitor we are asking to pay. Both boards have such a branch."""
    shell = _render(gated=True)
    assert "Building —" not in shell
    assert "构建中" not in shell


def test_a_genuinely_empty_board_still_reaches_its_honest_empty_state():
    """The other half, and the one a naive `{% if gate %}` gets wrong: when the
    collector really has nothing, the gated page must say so rather than dangle
    skeletons and a wall over content that does not exist."""
    shell = _render(gated=True, gate_over={"total": 0, "locked": 0, "n_buys": 0,
                                           "n_fresh": 0, "has_fresh": False})
    assert shell.count("Building —") == 2, "both empty states must be reachable"
    assert 'class="tier-wall"' not in shell
    assert 'class="cb-ghosts"' not in shell
    assert 'class="gate-pill"' not in shell
    # …and no gate NOTE either: "0 names sit on the board, ranked by how many
    # funds are backing each one" over an empty desk is its own small lie, and
    # it is a separate template arm from the skeletons above.
    assert 'id="etf-board-note"' not in shell
    assert "names sit on the board" not in shell


def test_fresh_section_is_absent_when_there_is_nothing_to_restore():
    """Shipping a hidden section hydration can only ever un-hide onto nothing is
    an orphan heading waiting to happen."""
    assert 'id="etf-fresh-sec"' in _render(gated=True)
    assert 'id="etf-fresh-sec"' not in _render(gated=True,
                                               gate_over={"has_fresh": False})


# ── doctrine ────────────────────────────────────────────────────────────────

def test_no_banned_tier1_vocabulary_reaches_the_public_shell():
    """This page is anonymous-public now, so its copy lands in Google's index and
    in AI-overview extractions. "Display-only" / "展示性" is internal tier
    vocabulary (DESIGN_DOCTRINE Law 2); "validated" is separately CI-guarded;
    falsifier language is barred from front surfaces (operator 2026-07-27)."""
    shell = _render(gated=True)
    for banned in ("Display-only", "display-only", "DISPLAY context", "仅供展示",
                   "展示性背景", "validated", "falsifier", "证伪"):
        assert banned not in shell, f"banned vocabulary in the public shell: {banned}"


def test_rotation_disclaimer_is_rendered_from_code_not_from_the_stale_pulse_file():
    """basketdata/etf_pulse.json is rebuilt under render scope `baskets` while
    this page bakes under `macro`, so a macro-only render reprints whatever
    wording the last baskets run left on disk. Reading the constant instead is
    what keeps the retired "Display-only" string from resurfacing on a public
    page months after the emitter was fixed."""
    env = _env()
    shell = env.get_template("etfs.html.j2").render(
        favored=[], accumulation=[], trims=[], coverage=_COVERAGE,
        # a pulse dict still carrying the OLD banned wording…
        pulse={"disclaimer_en": "Display-only rotation context — trailing ratio momentum.",
               "disclaimer_zh": "仅供展示的轮动背景。"},
        board=_board(gated=True), gate=_gate(), generated_utc="2026-08-03 12:00")
    assert "Display-only" not in shell and "仅供展示" not in shell
    assert "Rotation context — how style, risk and sector ETFs" in shell


def test_backdrop_tile_speaks_chinese_on_both_builds():
    """The hero's "Market backdrop" tile printed RISK-ON untranslated on the zh
    view — board_context handed the template label_en alone while the Market
    Backdrop card below carried the {en, zh} pair. The tile value is now that
    same pair and the macro renders a mapping bilingually; a plain string (the
    regression) leaves the tv div with no l-zh span, and a macro that stops
    b()-ing a mapping renders its escaped repr — both go red here."""
    for gated in (True, False):
        shell = _render(gated=gated)
        assert ('<div class="tv"><span class="l-en">RISK-ON</span>'
                '<span class="l-zh">风险偏好</span></div>') in shell, f"gated={gated}"
        # …while scalar tile values (counts, tickers) still render bare
        assert ('<div class="tv">3</div>' in shell          # the free honest total
                or '<div class="tv">AAA</div>' in shell), f"gated={gated}"


def test_rotation_backdrop_is_dated_by_the_pulse_as_of_not_the_bake_stamp():
    """§B9.6: etf_pulse.json refreshes under render scope `baskets` while this
    page bakes under `macro`, so a macro-only render can rebake the page around
    a stale rotation module. The module therefore dates itself from its own
    data source — the pulse's as_of — and never inherits the hero's bake stamp:
    the fixture's as_of (2026-07-31) must appear, on a page whose generated_utc
    is a different day, and dropping as_of must drop the date line rather than
    fall back to the render clock."""
    shell = _render(gated=True)
    assert re.search(r'数据截至</span>\s*2026-07-31', shell), (
        "the rotation footer must print the pulse's own as_of")
    assert re.search(r'prices through</span><span class="l-zh">数据截至', shell)
    # no as_of → no date line (never the bake stamp in its place)
    bare = dict(_board(gated=True), rotation={k: v for k, v in _ROTATION.items()
                                              if k != "as_of"})
    shell = _render(gated=True, board=bare)
    assert "数据截至" not in shell and "prices through" not in shell


def test_freshness_dots_do_not_ride_the_direction_inks():
    """红涨绿跌 flips --lift/--drag under 中文. Freshness is a DATA-QUALITY status,
    not a market direction, so riding those tokens paints "fresh" red and "stale"
    green for every Chinese reader — the exact defect the W2 mockup's first ZH
    render shipped. Fixed semantic inks, identical in both languages."""
    css = (ROOT / "templates" / "etfs.html.j2").read_text(encoding="utf-8")
    for cls, ink in ((".fdot.fresh", "#1FA971"), (".fdot.aging", "#f0b429"),
                     (".fdot.stale", "#e06464")):
        assert f"{cls}{{background:{ink}}}" in css, f"{cls} must use a fixed ink"
    assert ".fdot.fresh{background:var(--lift)}" not in css
    assert ".fdot.stale{background:var(--drag)}" not in css


def test_gate_furniture_carries_no_directional_colour():
    """A wall is not a market read; tinting it by state would make it flip."""
    css = (ROOT / "templates" / "etfs.html.j2").read_text(encoding="utf-8")
    gate_block = css[css.index("═══ tier gate"):css.index("═══ motion ═══")]
    for token in ("var(--lift)", "var(--drag)", "var(--up)", "var(--down)"):
        assert token not in gate_block, f"{token} must not tint the tier gate"
    assert "#8b5cf6" in gate_block          # the lock violet, as in the reference
    assert "linear-gradient(135deg,var(--link),#8b5cf6)" in gate_block  # never amber


def test_wall_css_resolves_its_surface_tokens():
    """theme.css ships no --surface family. Pasting the special_situations wall
    without transliterating its tokens renders a transparent-but-working card —
    the failure mode a review misses because nothing errors."""
    css = (ROOT / "templates" / "etfs.html.j2").read_text(encoding="utf-8")
    assert ".tw-card{" in css
    for token in ("--surface:", "--surface-brd:", "--surface-shadow:"):
        assert css.count(token) >= 2, (
            f"{token} must be defined for BOTH themes before .tw-card uses it")


def test_seo_head_is_unified_and_search_intent_titled():
    """T-B4 (ruled). <title> and seo_title used to disagree, and both led with a
    house phrase nobody searches."""
    shell = _render(gated=True)
    title = "Which Stocks Fund Managers Are Buying — MastermindX"
    assert f"<title>{title}</title>" in shell
    assert len(title) <= 70
    assert "mastermind-x.com/etfs.html" in shell        # self-canonical
    assert "Real fund moves" in shell                    # the h1 voice is untouched


# ── shipped artifacts ───────────────────────────────────────────────────────

def _shipped_payload():
    if not PAYLOAD.exists():
        pytest.skip("etfs not yet rebaked in the gated shape "
                    "(render.yml emits site/premiumdata/etfs.json)")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated"):
        pytest.skip("etfs is running ungated (config.yml etf_holdings.gated=false)")
    return payload


def test_shipped_shell_leaks_no_paid_row():
    payload = _shipped_payload()
    shell = SHELL.read_text(encoding="utf-8")
    locked = _keys(BOARD_ROW, payload["board_html"])
    assert locked, "a gated payload with no board rows is a vacuous pass"
    assert len(locked) == payload["locked"], (
        "row identities must cover the whole paid board or this check is vacuous: "
        f"keyed {len(locked)} of {payload['locked']} locked rows")
    for name, pat, key in (("consensus board", BOARD_ROW, "board_html"),
                           ("per-fund adds", ADD_ROW, "accumulation_html"),
                           ("fresh conviction", FRESH_CARD, "fresh_html"),
                           ("trims", ADD_ROW, "trims_html")):
        paid = set(_keys(pat, payload[key]))
        leaked = sorted(paid & set(_keys(pat, shell)))
        assert leaked == [], (f"{name}: paid rows readable in the free shell: "
                              f"{[k[:120] for k in leaked[:3]]}")
    assert _keys(BOARD_ROW, shell) == [], "the free shell renders no board row at all"
    # the hero's graded half, checked on the real bytes — this is where the
    # builder-side tile substitution (T-B1) is actually proven in production
    assert "Strongest consensus" not in shell and "最强共识" not in shell
    assert payload["verdict_html"], "the walled verdict must be in the payload…"
    assert "eh-verdict" not in shell, "…and not in the shell"
    assert "On the board" in shell, "the honest-total replacement must be there"


def test_the_leak_check_can_actually_see_a_duplicated_row():
    """A control, so the assertion above can never pass because the keying stopped
    matching the markup. Plant one paid row in a copy of the shell: it must bite."""
    paid = _payload_blocks()["board_html"]
    row = BOARD_ROW.search(paid)
    assert row, "fixture markup changed — the row pattern no longer matches"
    planted = _render(gated=True) + '<div class="cb-row">' + row.group(1) + \
        '<div class="cb-stance-cell">'
    assert set(_keys(BOARD_ROW, planted)) & set(_keys(BOARD_ROW, paid))


def test_shipped_payload_declares_the_contract():
    payload = _shipped_payload()
    assert payload["schema"] == "tier_payload.v1"
    assert payload["page"] == "etfs"
    assert payload["required_tier"] == "essential"
    assert payload["locked"] > 0
    assert payload["preview"] == 0, (
        "both boards are best-first; the ratified pattern forbids previewing them")
    for key in ("board_html", "accumulation_html", "verdict_html", "tiles_html"):
        assert payload[key], f"payload is missing {key} — hydration would half-restore"


def test_free_shell_stays_inside_its_weight_budget():
    """The free shell exists to be crawled and to convert. 282 KB of graded rows
    left with the split; this stops anyone quietly putting them back."""
    if not SHELL.exists():
        pytest.skip("site/etfs.html not built in this checkout")
    _shipped_payload()   # only meaningful once the gated shape is baked
    size = SHELL.stat().st_size
    assert size < 130 * 1024, f"free shell is {size / 1024:.1f} KiB (budget 130 KiB)"


# ── the serving boundary ────────────────────────────────────────────────────

def test_etfs_is_public_in_exactly_one_access_class():
    """Left in two classes the page serves public while the policy file documents
    it as gated — the drift that makes a boundary review meaningless."""
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    classes = [name for name in ("public", "free_registered", "deny")
               if "/etfs.html" in (policy.get(name, {}).get("exact") or [])]
    assert classes == ["public"], f"/etfs.html is classified {classes}, expected ['public']"


def test_the_payload_prefix_is_still_enforced_early():
    """Opening the shell must not open the rows. /premiumdata/ requires the
    site_full entitlement regardless of PAYWALL_ENABLED."""
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    prefixes = policy["premium"]["enforced_early"]["prefixes"]
    assert "/premiumdata/" in prefixes
    public = policy["public"]
    assert "/premiumdata/etfs.json" not in (public.get("exact") or [])
    assert not any(p.startswith("/premiumdata")
                   for p in (public.get("prefixes") or []))


def test_all_three_boundary_mirrors_agree():
    """A promotion that lands in two of the three mirrors passes every other
    guard: the boundary suite diffs Caddy against site_access.yml and never
    imports app/regwall.py's own list."""
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    assert "/etfs.html" in policy["public"]["exact"]
    # every matcher list that names the W1a shells must also name this one
    lists = [ln for ln in caddy.splitlines() if "/special_situations.html" in ln]
    assert lists, "Caddyfile matcher lists not found — did the file change shape?"
    for line in lists:
        assert "/etfs.html" in line, f"Caddy matcher missing /etfs.html: {line.strip()[:90]}"
