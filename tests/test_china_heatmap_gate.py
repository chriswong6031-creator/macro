"""china_heatmap.html — the W2 anonymous tier-preview conversion.

This page is the odd one out among the converted desks. Special Situations was
already split and W1a moved only its access class; etfs.html was fully
server-rendered and its PR had to take the graded rows off the URL. The heatmap
shipped **zero content**: a 76-line shell that built every tile, stat and mover
in the browser from ``marketdata/<market>_heatmap.json``. Flipping the boundary
alone would therefore have replaced a 302 with a *thin-content 200* — a worse
outcome, because Google keeps it and rates it thin.

So the conversion is a CONTENT build, and this module guards both halves:

* the **SSR summary layer** (market pulse, breadth stat cards, sector ladder,
  both mover boards) is present, non-empty and market-correct for all THREE
  markets — the twins are the likeliest silent casualty of a China-only fix;
* the **gate** is one note, one CTA row and one micro-wall inside the hover
  card, with no ``.tier-wall``, because a wall over content that is free would
  be a lie;
* the hover card has **two distinct empty states** — "no nightly read yet" is
  true on an entitled build with a missing file and a lie on a walled one, and
  neither is inferred from the fetch result alone;
* the boundary opened the page and the tile map and **nothing else**.

Runs in the `unrun-page-guards` CI job (full venv: the engine imports pandas).
The Caddy↔policy byte-equality half is pinned by tests/test_site_access_boundary.py
and the wall mirror by tests/test_regwall.py, both in `tier-gate`.

Spec: research/seo_supercharge/W2_HEATMAP_ETFS_PREVIEW_SPEC.md Part A + §R.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHELL = SITE / "china_heatmap.html"
TILES = SITE / "marketdata" / "china_heatmap.json"
TEMPLATE_SRC = (ROOT / "templates" / "market_heatmap.html.j2").read_text(encoding="utf-8")
HEATMAP_JS = (ROOT / "templates" / "heatmap.js").read_text(encoding="utf-8")
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
CADDY = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")

MARKETS = ("china", "hk", "canada")
PAGE_WEIGHT_BUDGET = 80 * 1024   # spec §A3: the point is to stop anyone "solving"
                                 # the empty-shell problem by SSR-ing 1,500 tiles.


# ── helpers ─────────────────────────────────────────────────────────────────
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n
    from lib.seo import SITE_BASE
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    return env


def _render(market: str, *, summary, gated: bool, n_tiles: int = 1234) -> str:
    from engine.market_heatmap import PAGE_META, sibling_markets
    return _env().get_template("market_heatmap.html.j2").render(
        mk=PAGE_META[market], summary=summary, gated=gated,
        n_tiles=n_tiles, siblings=sibling_markets(market))


def _payload(market: str) -> dict:
    return json.loads((SITE / "marketdata" / f"{market}_heatmap.json").read_text(encoding="utf-8"))


def _summary(market: str):
    from engine.market_heatmap import page_summary
    return page_summary(_payload(market))


def _caddy_matcher_paths(matcher: str) -> set[str]:
    m = re.search(rf"@{matcher}\s*\{{(.*?)^\s*\}}", CADDY, flags=re.S | re.M)
    assert m, f"Caddy matcher @{matcher} missing"
    import shlex
    return {tok
            for line in re.findall(r"^\s*(?:not\s+)?path\s+([^\n]+)", m.group(1), flags=re.M)
            for tok in shlex.split(line)}


def _regwall_public_paths() -> set[str]:
    """Read the wall's static mirror without importing FastAPI in this CI lane."""

    source_path = ROOT / "app" / "regwall.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "PUBLIC_PATHS" for target in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, set)
            assert all(isinstance(path, str) for path in value)
            return value
    raise AssertionError("app/regwall.py must declare a literal PUBLIC_PATHS set")


ALL_MATCHERS = ("reg_html", "reg_asset", "gate_html",
                "reg_html_err", "reg_asset_err", "gate_html_err")


# ── the SSR content layer (spec §A2.3, masterplan gate §0.1) ────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_ssr_summary_is_present_non_empty_and_market_correct(market):
    """Gate §A9.9 — the twin parity check.

    A China-only fix that leaves hk/canada rendering the old empty shell is the
    likeliest silent casualty here: they share one template and one builder, and
    nothing about the page LOOKS broken when the summary is missing — it just
    quietly goes back to being a blank 51 KB document.
    """
    summary = _summary(market)
    assert summary, f"{market}: page_summary() returned nothing from the shipped tile map"
    html = _render(market, summary=summary, gated=False)

    assert 'id="hm-ssr"' in html
    for block in ("hx-pulse-read", "hx-stats", "hx-boards", "hx-sec", "hx-row"):
        assert block in html, f"{market}: SSR is missing the {block} block"

    # Non-empty is the load-bearing half: an SSR layer that renders four empty
    # containers passes a presence check and ships the same thin page.
    assert summary["gainers"] and summary["losers"], f"{market}: no movers"
    assert len(summary["sectors"]) >= 5, f"{market}: sector ladder too short"
    assert summary["breadth"]["adv"] not in ("", "—"), f"{market}: no breadth count"

    # Market-correct: this market's own sector labels and its own movers, not a
    # neighbour's. Every mover code must belong to this market's tile set.
    codes = {re.sub(r"\.(SS|SZ|SH|HK|TO|V|TSX|NE|CN)$", "", t["t"], flags=re.I)
             for t in _payload(market)["tiles"]}
    for row in summary["gainers"] + summary["losers"]:
        assert row["code"] in codes, f"{market}: mover {row['code']} is not on this map"
    top_names = {s["en"] for s in summary["sectors"]}
    assert top_names <= {s["en"] for s in _payload(market)["sectors"]}


@pytest.mark.parametrize("market", MARKETS)
def test_ssr_numbers_are_in_the_rendered_bytes(market):
    """The numbers a crawler reads must be the numbers the tile map carries.

    Not a restatement of the test above: this asserts the values SURVIVE Jinja
    into the document. A summary computed correctly and then dropped by a
    template typo is exactly the failure a presence check cannot see.
    """
    summary = _summary(market)
    html = _render(market, summary=summary, gated=False)
    assert f"<b>{summary['pct_up']}%</b>" in html
    assert summary["median"] in html
    assert summary["breadth"]["adv"] in html
    assert summary["gainers"][0]["code"] in html
    assert summary["sectors"][0]["en"] in html


def test_summary_is_none_when_there_is_no_map_and_the_shell_still_renders():
    """A dead feed must degrade to the shell we have always shipped, never to a
    page of empty boxes captioned with real-looking labels."""
    from engine.market_heatmap import page_summary
    assert page_summary(None) is None
    assert page_summary({"tiles": []}) is None
    assert page_summary({"tiles": [{"t": "X", "perf": {}, "sector": "S"}],
                         "timeframes": [], "default_tf": "1D"}) is None
    html = _render("china", summary=None, gated=True)
    assert 'id="hm-ssr"' not in html
    assert 'id="heatmap-full"' in html          # the map mount still ships


def test_summary_mirrors_the_js_arithmetic():
    """The SSR copy and the live copy must be the SAME numbers, or hydration
    visibly rewrites the page a crawler was shown.

    Pins the four behaviours heatmap.js's computeSummary/applyBoard actually
    have, against a hand-computed fixture: the ±0.05% advancing dead-band (NOT
    strict zero), cap-weighted sector aggregation when sizes are real caps,
    movers ranked by the active timeframe, and the whole-board breadth overlay
    taking over the counts when the payload carries a same-session row.
    """
    from engine.market_heatmap import page_summary
    tiles = [
        {"t": "A.SS", "name": "Alpha", "sector": "Tech", "size": 100.0, "perf": {"1D": 4.0}},
        {"t": "B.SS", "name": "Bravo", "sector": "Tech", "size": 300.0, "perf": {"1D": 8.0}},
        {"t": "C.SS", "name": "Charlie", "sector": "Fin", "size": 100.0, "perf": {"1D": 0.02}},
        {"t": "D.SS", "name": "Delta", "sector": "Fin", "size": 100.0, "perf": {"1D": -3.0}},
    ]
    base = {"market": "china", "default_tf": "1D", "size_basis": "marketcap",
            "timeframes": [{"key": "1D", "available": True}],
            "sectors": [{"key": "Tech", "en": "Tech", "zh": "科技"},
                        {"key": "Fin", "en": "Fin", "zh": "金融"}],
            "tiles": tiles, "n_tiles": 4, "asof": "2026-08-03"}

    s = page_summary(base)
    # +0.02% is inside the dead band -> flat, not advancing. 2 of 4 up = 50%.
    assert s["pct_up"] == 50
    # Cap-weighted: Tech = (100*4 + 300*8)/400 = 7.0; Fin = (0.02 - 3)/2 = -1.49
    assert s["top"]["en"] == "Tech" and s["top"]["pc"] == "+7.00%"
    assert s["bot"]["en"] == "Fin" and s["bot"]["pc"] == "−1.49%"
    # Median of [-3, 0.02, 4, 8] = (0.02 + 4)/2 = 2.01
    assert s["median"] == "+2.01%"
    assert [r["code"] for r in s["gainers"]] == ["B", "A", "C", "D"]
    assert [r["code"] for r in s["losers"]] == ["D", "C", "A", "B"]

    # Whole-board overlay: the tiles are a SAMPLE, so a same-session board row
    # owns the counts, the % up and the median — one sentence, one universe.
    boarded = dict(base, board_breadth={
        "n": 5000, "adv": 4000, "dec": 900, "flat": 100, "pct_up": 80.0,
        "med_pct": 1.25, "scope_en": "Whole board", "scope_zh": "全市场"})
    b = page_summary(boarded)
    assert b["pct_up"] == 80 and b["median"] == "+1.25%"
    assert b["breadth"]["adv"] == "4,000"
    assert "Whole board · 5,000 traded" == b["breadth"]["scope"]["en"]
    # Per-name detail stays tile-derived: the board feed carries no names.
    assert [r["code"] for r in b["gainers"]] == [r["code"] for r in s["gainers"]]


def test_minus_sign_is_the_typographic_minus_not_a_hyphen():
    """heatmap.js prints U+2212. A hyphen here would make the SSR and the live
    copy differ by one glyph on every negative number on the page."""
    from engine.market_heatmap import _fmt_pc
    assert _fmt_pc(-1.25) == "−1.25%" and "−" in _fmt_pc(-1.25)
    assert _fmt_pc(2.0) == "+2.00%"
    assert _fmt_pc(None) == "—"


# ── the gate (spec §A4) ─────────────────────────────────────────────────────
def test_gated_build_ships_one_note_one_cta_and_no_tier_wall():
    html = _render("china", summary=_summary("china"), gated=True)
    assert html.count('id="hm-gate-note"') == 1
    assert html.count('id="hm-cta"') == 1
    # No .tier-wall, no skeletons, no inert controls: everything this page shows
    # is free, and every control only re-slices data the visitor already holds.
    # A wall over free content would be a lie and five walls would be nagging.
    for anti in ("tier-wall", "tw-ghost", "gate-pill", 'class="gh"', 'class="gh ',
                 'class="gated', "pointer-events:none"):
        assert anti not in html, f"{anti} has no business on this page"
    assert 'href="plans.html"' in html
    assert "See plans" in html and "查看方案" in html
    assert "7-day Pro trial · cancel anytime" in html and "Pro 7 天试用 · 随时取消" in html


def test_ungated_build_ships_no_gate_furniture():
    """The inverse scan. A one-directional check ("the gated build has a note")
    passes just as happily when the note is unconditional — and hk/canada, which
    are NOT public in this PR, would then carry an upgrade wall on a page nobody
    can reach without an account."""
    html = _render("hk", summary=_summary("hk"), gated=False)
    for gone in ("hm-gate-note", "hm-cta", "data-hm-gated", "See plans", "查看方案"):
        assert gone not in html, f"ungated build leaked {gone}"


def test_cta_counts_are_templated_never_hardcoded():
    """Membership changes nightly; a stale honest-total is a dishonest total."""
    html = _render("china", summary=_summary("china"), gated=True, n_tiles=4242)
    assert "4,242" in html, "the CTA count is not templated (or lost its grouping)"
    for hardcoded in (r"\b1,?51\d\b", r"\b1,?52\d\b"):
        assert re.search(hardcoded, TEMPLATE_SRC) is None, "hardcoded tile count in the template"


def test_cta_names_the_sibling_markets_from_config():
    from engine.market_heatmap import sibling_markets
    assert sibling_markets("china")["en"] == "Hong Kong and Canada"
    assert sibling_markets("hk")["en"] == "China and Canada"
    assert "港股" in sibling_markets("china")["zh"]
    html = _render("china", summary=_summary("china"), gated=True)
    assert "Hong Kong and Canada" in html


# ── the hover card's TWO empty states (spec §A4.2, gate §A9.10) ─────────────
def test_hover_card_has_two_distinct_empty_states():
    """`rec === null` has two causes and they are not the same sentence.

    On a walled build "No nightly read for this name yet" is a lie: the read
    exists and is paid. Shipping one sentence for both causes IS the defect, so
    this pins that both strings exist, that they differ, and that the locked one
    is reached by its own branch.
    """
    assert "hm-c-locked" in HEATMAP_JS
    assert "is member content" in HEATMAP_JS
    assert "为会员内容" in HEATMAP_JS
    assert "No nightly read for this name yet" in HEATMAP_JS
    assert "该标的暂无每晚分析" in HEATMAP_JS

    body = re.search(r"function enrichCard\(el, data, t, rec, locked\) \{(.*?)\n  \}",
                     HEATMAP_JS, re.S)
    assert body, "enrichCard no longer takes the gate state — the branch is gone"
    src = body.group(1)
    lock_at = src.index("hm-c-locked")
    stub_at = src.index("No nightly read for this name yet")
    assert src.index("if (locked)") < lock_at < stub_at, (
        "the locked slot must be its own branch, ahead of the absent-file stub")
    assert re.search(r"if \(!rec\) \{", src), "the absent-file stub lost its branch"


def test_gate_state_is_never_inferred_from_the_fetch_result():
    """A network error must not read as a paywall, and a 200 from the public R2
    mirror must not read as an entitlement.

    The build stamps data-hm-gated on the mount and the wall answers who may
    read the graded file; `locked` is the AND of the two. If either input
    disappears the card starts lying in one direction or the other.
    """
    assert 'data-hm-gated' in TEMPLATE_SRC and "data-hm-gated" in HEATMAP_JS
    assert re.search(r"function mapIsGated\(\)", HEATMAP_JS)
    assert "/api/regwall/check" in HEATMAP_JS
    assert re.search(r"enrichCard\(el, data, t, res\[0\], gated && !res\[1\]\)", HEATMAP_JS), (
        "the locked state must be (build is gated) AND (the wall said no)")
    # Resolve BOTH before painting: enriching on whichever settles first would
    # flash the graded block at a viewer the wall has not cleared.
    assert "Promise.all([" in HEATMAP_JS
    # An unreachable wall keeps the lock — fail closed, never fail open.
    assert re.search(r"\.catch\(function \(\) \{ return false; \}\)", HEATMAP_JS)


def test_locked_slot_carries_no_directional_colour():
    """theme.css swaps --up/--down under html[data-lang="zh"] (红涨绿跌). A gate
    element tinted by market direction would invert its meaning with the
    language — the same class of defect as painting "fresh" red in ZH."""
    css = re.search(r"\.hm-c-locked\{.*?\.hm-c-locked a\{[^']*", HEATMAP_JS, re.S)
    assert css, ".hm-c-locked has no styling"
    assert "--up" not in css.group(0) and "--down" not in css.group(0)
    gate_css = re.search(r"\.gate-note \{.*?\.tw-note \{[^}]*\}", TEMPLATE_SRC, re.S)
    assert gate_css, "the gate CSS block moved — re-point this guard"
    assert "--up" not in gate_css.group(0) and "--down" not in gate_css.group(0)
    # Brand blue -> violet, never signal amber (terminal paywall lesson).
    assert "linear-gradient(135deg,var(--link),#8b5cf6)" in TEMPLATE_SRC.replace(" ", "")


def test_gate_css_uses_tokens_this_page_actually_defines():
    """special_situations.html.j2 defines --card/--grid/--ink/--faint/--blue in
    its own <style>. This page has no local token block at all — it inherits
    theme.css, where those roles are --panel/--line/--text/--muted/--link. A
    verbatim paste resolves every colour to nothing and renders a transparent
    note that still "works", which is the failure a review misses."""
    block = re.search(r"/\* ── gate elements.*?</style>", TEMPLATE_SRC, re.S)
    assert block, "the gate CSS block moved — re-point this guard"
    for dead in ("var(--card)", "var(--grid)", "var(--ink)", "var(--faint)", "var(--blue)"):
        assert dead not in block.group(0), f"{dead} is undefined on this page"


# ── directional colour (spec §A7) ───────────────────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_ssr_directional_fills_paint_from_the_theme_tokens(market):
    """Colour is the primary encoding on this page, so ZH's 红涨绿跌 flip is the
    highest-stakes thing here. A hard-coded green or red in the SSR survives the
    flip and paints a rising sector in the falling colour."""
    html = _render(market, summary=_summary(market), gated=False)
    body = html.split("<style>")[0] + html.split("</style>")[-1]
    for banned in ("#45b873", "#e06464", "#1f9a55", "#cf4040", ":green", ":red"):
        assert banned not in body, f"{market}: hard-coded directional colour {banned}"
    assert "var(--up)" in html and "var(--down)" in html


# ── SEO head (spec §A8, masterplan gate §0.1) ───────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_seo_head_is_one_title_self_canonical_and_in_budget(market):
    from engine.market_heatmap import PAGE_META
    mk = PAGE_META[market]
    assert len(mk["seo_title"]) <= 70, f"{market}: <title> over 70 chars"
    assert mk["seo_title"].endswith("MastermindX"), f"{market}: title is not brand-suffixed"
    assert 50 <= len(mk["seo_desc"]) <= 170, f"{market}: description outside 50-170"

    html = _render(market, summary=_summary(market), gated=False)
    assert html.count("<title>") == 1
    assert f"<title>{mk['seo_title']}</title>" in html
    # The page used to carry three different strings. og:/twitter: read seo_title
    # from _seo_head.html.j2, so one source means they can no longer disagree.
    assert html.count(f'content="{mk["seo_title"]}"') >= 2
    assert (f'<link rel="canonical" href="https://www.mastermind-x.com/'
            f'{market}_heatmap.html">') in html


def test_shipped_shell_head_matches_the_template_contract():
    html = SHELL.read_text(encoding="utf-8")
    from engine.market_heatmap import PAGE_META
    assert f"<title>{PAGE_META['china']['seo_title']}</title>" in html
    assert 'rel="canonical" href="https://www.mastermind-x.com/china_heatmap.html"' in html
    assert "noindex" not in html


# ── shipped bytes (gate §0.6b — access and content deploy together) ─────────
def test_shipped_shell_carries_the_summary_and_the_gate():
    """Gate 6b. The boundary mirrors self-deploy in ~3 min via the VPS config
    cron; a page bake rides the render lane and can be superseded for hours. So
    the walled shell is committed in the SAME PR as the flip, and this is the
    guard that it actually was — the etfs incident (#4426 flipped ahead of the
    bake, the full board was anonymously public ~1h, closed by #4446) is exactly
    what a green boundary test with a stale shell looks like.
    """
    html = SHELL.read_text(encoding="utf-8")
    assert 'id="hm-ssr"' in html, "the committed shell has no SSR summary layer"
    assert 'data-hm-gated="1"' in html
    assert html.count('id="hm-gate-note"') == 1
    assert html.count('id="hm-cta"') == 1
    assert "tier-wall" not in html
    # Real numbers, not empty containers.
    assert re.search(r'<div class="hx-bleg"><span class="hx-up">▲ [\d,]+</span>', html)
    assert re.search(r'<div class="hx-pulse-read">\s*<span class="l-en"><b>\d+%</b>', html)
    assert html.count('class="hx-sec"') >= 5
    assert html.count('class="hx-row"') == 10       # 5 gainers + 5 losers


def test_shipped_shell_holds_no_graded_read():
    """The one walled surface is our per-name conviction read. It arrives from a
    fetched per-ticker file and must never be baked into the page."""
    html = SHELL.read_text(encoding="utf-8")
    # The CLASSES, not the word: "our conviction read" is the page's own defined
    # product term and it survives in the methodology tip, where explaining what
    # members get is the whole point. What must never appear is a rendered band,
    # score or verdict.
    for graded in ("hm-c-band", "hm-c-score", "hm-c-verdict",
                   "conviction.band", "verdict_zh", "band_zh"):
        assert graded not in html, f"the shell baked a graded artefact: {graded}"


@pytest.mark.parametrize("market", MARKETS)
def test_page_weight_stays_inside_budget(market):
    """Spec §A3. Generous on purpose: the gate exists to stop anyone 'fixing'
    the empty-shell problem by server-rendering all ~1,500 tiles."""
    size = (SITE / f"{market}_heatmap.html").stat().st_size
    assert size < PAGE_WEIGHT_BUDGET, (
        f"{market}_heatmap.html is {size/1024:.1f} KB, budget {PAGE_WEIGHT_BUDGET/1024:.0f} KB")


# ── the two market facts moved onto the tile (spec T-A2, MITIGATE) ──────────
def test_tile_map_carries_the_free_market_facts():
    """`px` and `pct_vs_200dma` are FACTS, not grades, but they used to reach
    the card only inside the per-ticker file that also carries our graded read —
    so an anonymous card lost two honest numbers to protect a third thing."""
    payload = json.loads(TILES.read_text(encoding="utf-8"))
    tiles = payload["tiles"]
    with_px = [t for t in tiles if "px" in t]
    with_p200 = [t for t in tiles if "p200" in t]
    assert len(with_px) / len(tiles) > 0.95, "most tiles carry no last price"
    assert len(with_p200) / len(tiles) > 0.8, "most tiles carry no 200-day distance"
    assert all(t["px"] > 0 for t in with_px)
    # The card renders both from the tile, with the per-ticker file only as the
    # fallback for maps whose tiles do not carry them (the US map).
    assert re.search(r"var p2 = t\.p200 != null \? t\.p200 : tech\.pct_vs_200dma", HEATMAP_JS)
    assert re.search(r"var px = t\.px != null", HEATMAP_JS)
    assert "hm-c-meta" not in TEMPLATE_SRC          # built by the card, not the page


def test_200dma_is_omitted_rather_than_faked_on_a_short_series():
    """A '200-day average' printed off 40 prints is a different statistic
    wearing the same label."""
    pd = pytest.importorskip("pandas")
    from engine.market_heatmap import _market_facts
    short = pd.DataFrame({"X": [10.0] * 40},
                         index=pd.date_range("2026-01-01", periods=40, freq="D"))
    long = pd.DataFrame({"X": [10.0] * 199 + [11.0]},
                        index=pd.date_range("2025-01-01", periods=200, freq="D"))
    assert "p200" not in _market_facts(short, None)["X"]
    assert _market_facts(short, None)["X"]["px"] == 10.0
    assert "p200" in _market_facts(long, None)["X"]


# ── the boundary (masterplan gate §0.3) ────────────────────────────────────
def test_the_page_and_its_tile_map_are_public_in_every_mirror():
    public = set(POLICY["public"]["exact"])
    assert "/china_heatmap.html" in public
    assert "/marketdata/china_heatmap.json" in public
    for matcher in ALL_MATCHERS:
        assert "/china_heatmap.html" in _caddy_matcher_paths(matcher), matcher
    for matcher in ("reg_asset", "reg_asset_err"):
        assert "/marketdata/china_heatmap.json" in _caddy_matcher_paths(matcher), matcher
    assert "/china_heatmap.html" in _regwall_public_paths(), (
        "the wall's own mirror is the one a Caddy-vs-policy diff never reads")


def test_only_china_flipped():
    """hk and canada run the same template and the same builder and adopt this
    by adding one line each. Until they do, they must stay gated — a prefix
    where an exact path belonged would open all three silently."""
    public = set(POLICY["public"]["exact"])
    regwall_public = _regwall_public_paths()
    for market in ("hk", "canada"):
        assert f"/{market}_heatmap.html" not in public
        assert f"/{market}_heatmap.html" not in regwall_public
        assert f"/marketdata/{market}_heatmap.json" not in public
        assert f"/{market}_heatmap.html" not in _caddy_matcher_paths("gate_html")
    assert not any(p.startswith("/marketdata") for p in POLICY["public"]["prefixes"])


def test_opening_the_map_opened_no_graded_store():
    """The inverse of the promotion test. The graded read lives in the
    per-ticker stores; a promotion that widened a prefix instead of naming a
    path would open all ~1,500 of them."""
    public = set(POLICY["public"]["exact"])
    prefixes = tuple(POLICY["public"]["prefixes"])
    for store in ("/chinastockdata/", "/hkstockdata/", "/canadastockdata/", "/stockdata/"):
        assert store not in prefixes
        assert not any(p.startswith(store) for p in public), f"{store} leaked a file"
    assert "/marketdata/sp500_heatmap.json" not in public, (
        "the US map is served from the VPS live plane through @vps_external — "
        "adding it here would shadow that route")


def test_the_page_enters_the_sitemap_and_the_siblings_do_not():
    """Gate §0.4 / T-A4: the page enters the sitemap ONLY with the summary layer
    present, and lib/seo.py gates discovery on the public boundary — so this
    also proves the flip is what put it there, not a hand-edited list."""
    from lib import seo
    assert seo.is_public_path("/china_heatmap.html")
    assert not seo.is_public_path("/hk_heatmap.html")
    assert not seo.is_public_path("/canada_heatmap.html")
    assert not seo._should_exclude("china_heatmap")
    urls = [url for _stem, url, _fn in seo.discover_core_pages(SITE)]
    assert any(u.endswith("/china_heatmap.html") for u in urls), (
        "the sitemap builder did not pick the page up")
    assert not any(u.endswith("/hk_heatmap.html") for u in urls)
    assert not any(u.endswith("/canada_heatmap.html") for u in urls)
    # …and the shipped sitemap actually carries it, so the guard is about the
    # committed artefact rather than only about the discovery function.
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://www.mastermind-x.com/china_heatmap.html</loc>" in sitemap
    assert "hk_heatmap.html" not in sitemap and "canada_heatmap.html" not in sitemap


# ── copy law ────────────────────────────────────────────────────────────────
def test_new_copy_is_glance_tier_and_bilingual():
    html = _render("china", summary=_summary("china"), gated=True)
    banned = ("Display-only", "display context only", "validated", "falsifier",
              "证伪", "refuted", "sig_tier", "turn_state", "conviction.band", "n=")
    # Only the copy this PR owns: the gate note, the CTA and the SSR summary.
    owned = "\n".join(re.findall(r'<div class="(?:gate-note|cta-row|hx-pulse-read)"[^>]*>(.*?)</div>',
                                 html, re.S))
    assert owned.strip(), "the copy under test did not render"
    # Scan the READING copy, not the markup: `stroke-linejoin="round"` contains
    # "n=" and would flag a gate note that says nothing of the kind.
    words = re.sub(r"<[^>]+>", " ", owned)
    for word in banned:
        assert word not in words, f"banned tier-1 vocabulary in new copy: {word}"
    # Bilingual, both halves present, on every element this PR added.
    for frag in ('id="hm-gate-note"', 'id="hm-cta"', 'class="hx-pulse-read"'):
        i = html.index(frag)
        window = html[i:i + 1400]
        assert 'class="l-en"' in window and 'class="l-zh"' in window, frag
