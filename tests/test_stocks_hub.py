"""Contract tests for the /stocks/ market hub (engine/stocks_hub.py).

Each test pins a defect that shipped, or nearly shipped, on this surface:

* the sector filter that silently showed you half a sector,
* two different "% green" numbers printed side by side,
* a surface colour a theme override could miss,
* the crawl-hub links the redesign had to keep,
* volume boards filling with phantom zeros or with illiquid noise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import stocks_hub as hub  # noqa: E402
from engine.market_heatmap import _ADV_BAND  # noqa: E402


# ── the sector-vocabulary collapse ──────────────────────────────────────────
CANON = {"Tech", "Health Care", "Financials", "Consumer Disc.", "Comm. Services",
         "Industrials", "Staples", "Energy", "Materials", "Real Estate", "Utilities"}


def _builder():
    from scripts import build_ticker_pages as B
    return B


def test_both_sector_vocabularies_collapse_to_one_display_name():
    """GICS and Yahoo names for one sector must land on the same chip.

    membership.parquet is stitched from more than one vendor and carries both
    "Information Technology" and "Technology". Mapping only the GICS half let the
    other fall through unchanged, so the page printed two Tech chips and each one
    hid the names filed under the other vendor's spelling.
    """
    B = _builder()
    pairs = [
        ("Information Technology", "Technology"),
        ("Health Care", "Healthcare"),
        ("Financials", "Financial"),
        ("Consumer Discretionary", "Consumer Cyclical"),
        ("Consumer Staples", "Consumer Defensive"),
        ("Materials", "Basic Materials"),
    ]
    for gics, vendor in pairs:
        assert B._sector_display(gics) == B._sector_display(vendor), (
            f"{gics!r} and {vendor!r} are the same sector but render as "
            f"{B._sector_display(gics)!r} vs {B._sector_display(vendor)!r} — "
            "the filter would split the sector in two"
        )
        assert B._sector_display(gics) in CANON


def test_every_sector_string_in_membership_maps_to_a_canonical_name():
    """No vendor spelling may fall through to a bare passthrough chip."""
    pd = pytest.importorskip("pandas")
    fp = ROOT / "data" / "universe" / "membership.parquet"
    if not fp.exists():
        pytest.skip("membership.parquet not in this checkout")
    B = _builder()
    raw = [s for s in pd.read_parquet(fp)["sector"].dropna().unique()]
    assert raw, "membership.parquet carries no sector column values"
    unmapped = sorted({s for s in raw if B._sector_display(s) not in CANON})
    assert not unmapped, (
        f"sector strings with no canonical mapping: {unmapped} — each becomes its "
        "own filter chip covering only part of its sector"
    )


def test_every_canonical_sector_has_a_translation():
    B = _builder()
    missing = sorted(s for s in CANON if B._sector_zh(s) == s)
    assert not missing, f"untranslated sector chips in 中文 mode: {missing}"


# ── breadth / spine agreement ───────────────────────────────────────────────
def test_breadth_uses_the_shared_dead_band():
    """A move inside +/-_ADV_BAND is flat, exactly as on the heatmap pages."""
    tiny = _ADV_BAND / 2.0
    br = hub.breadth([tiny, -tiny, 5.0, -5.0])
    assert br["adv"] == 1 and br["dec"] == 1 and br["flat"] == 2


def test_spine_crossing_matches_the_breadth_number_it_is_labelled_with():
    """The curve's zero crossing and the stat strip must be one number.

    An earlier cut computed the crossing with `v >= 0` while the stat strip used
    the dead band, so the page printed "45% finished green" beside "44%
    advancing" — one fact, two answers.

    The universe below deliberately parks 300 of 900 names INSIDE the dead band,
    the way a real tape does. A smooth ramp cannot catch this: it leaves only a
    handful of names between `>= 0` and `> band`, so the wrong rule lands within
    rounding of the right one and the guard passes on broken code.
    """
    flat_band = _ADV_BAND * 0.8
    rets = ([-4.0 + 0.01 * i for i in range(300)]            # 300 clear decliners
            + [flat_band * (i % 3 - 1) for i in range(300)]  # 300 inside the band
            + [0.2 + 0.01 * i for i in range(300)])          # 300 clear advancers
    br = hub.breadth(rets)
    assert br["flat"] >= 200, "fixture no longer exercises the dead band"

    sp = hub.day_shape(rets, pct_up=br["pct_up"])
    frac_right = 1.0 - (sp["cross_x"] / hub.SPINE_W)
    assert abs(frac_right * 100.0 - br["pct_up"]) < 1.0, (
        f"crossing sits at {frac_right*100:.1f}% of the width but the label "
        f"claims {br['pct_up']}% — the picture contradicts its own caption"
    )


def test_stance_is_descriptive_never_directional():
    """This panel reports the tape; it must not tell anyone what to do."""
    verbs = {"buy", "sell", "add", "trim", "short", "long", "enter", "exit",
             "accumulate", "chase", "买入", "卖出", "加仓", "减仓"}
    for pct in range(0, 101, 5):
        for med in (-1.5, -0.1, 0.0, 0.1, 1.5):
            s = hub.stance(pct, med)
            words = set(re.findall(r"[a-z]+", s["en"].lower()))
            assert not (words & verbs), f"directional advice in stance: {s}"
            assert not any(v in s["zh"] for v in verbs)


# ── boards ──────────────────────────────────────────────────────────────────
def _row(t, **kw):
    base = {"ticker": t, "name": f"{t} Inc.", "chg": 1.0, "dvol": 1e9,
            "rvol": 1.0, "pos52": 50.0}
    base.update(kw)
    return base


def test_names_without_volume_stay_out_of_the_volume_boards():
    """Close-only bars carry no volume; a phantom 0 would rank them, not skip them."""
    rows = [_row("AAA", dvol=None, rvol=None), _row("BBB", dvol=5e9, rvol=3.0)]
    b = hub.boards(rows)
    assert [r["t"] for r in b["active"]] == ["BBB"]
    assert [r["t"] for r in b["unusual"]] == ["BBB"]


def test_unusual_volume_board_ignores_illiquid_names():
    """A thin name doubling its own tiny volume is noise, not news."""
    rows = [_row("THIN", dvol=3.0e6, rvol=9.9), _row("REAL", dvol=8.0e8, rvol=2.2)]
    b = hub.boards(rows)
    assert [r["t"] for r in b["unusual"]] == ["REAL"], (
        "the illiquid name outranked a real one — without the liquidity floor "
        "this board fills with the least-traded names every session"
    )


def test_52_week_boards_only_take_names_actually_near_the_edge():
    rows = [_row("HI", pos52=97.0), _row("MID", pos52=50.0), _row("LO", pos52=2.0)]
    b = hub.boards(rows)
    assert [r["t"] for r in b["near_high"]] == ["HI"]
    assert [r["t"] for r in b["near_low"]] == ["LO"]


def test_board_rows_are_toned_by_direction_not_by_metric():
    """A most-traded name that FELL must still read as a decline."""
    rows = [_row("DOWN", chg=-4.0, dvol=9e9)]
    b = hub.boards(rows)
    assert b["active"][0]["tone"] == "dn"


# ── consolidated theme ribbons ──────────────────────────────────────────────
def _theme_payload() -> dict:
    members = [
        {"t": ticker, "perf": {"1D": pct}, "asof": "2026-08-07"}
        for ticker, pct in (("AAA", 8.0), ("BBB", 6.0), ("NO_PAGE", 5.0),
                            ("CCC", 4.0), ("ALSO_MISSING", 2.0))
    ]
    return {
        "themes_asof": "2026-08-07",
        "theme_tiles": [{
            "sector": "Artificial Intelligence",
            "members": members,
            "asof": "2026-08-07",
        }],
    }


def test_theme_ribbons_keep_only_members_with_a_rendered_dossier():
    ribbons = hub.theme_ribbons(
        _theme_payload(), linkable=frozenset({"AAA", "BBB", "CCC"})
    )
    assert len(ribbons) == 1
    assert ribbons[0]["name"] == "Artificial Intelligence"
    assert ribbons[0]["avg_pc"] == "+6.00%"
    assert ribbons[0]["asof"] == "2026-08-07"
    assert [m["t"] for m in ribbons[0]["members"]] == ["AAA", "BBB", "CCC"]
    assert "NO_PAGE" not in str(ribbons), "a missing dossier would become a dead chip"


def test_theme_ribbon_disappears_when_only_one_linkable_member_survives():
    assert hub.theme_ribbons(
        _theme_payload(), linkable=frozenset({"AAA"})
    ) == []


def test_hub_builder_loads_theme_groups_independently_of_the_board_payload(
        tmp_path, monkeypatch):
    """The unique mover-page read must enter the actual index render context."""
    from engine.marketing import movers_source

    monkeypatch.setattr(movers_source, "load_movers", lambda _root: _theme_payload())
    rows = [
        _row("AAA", sector="Technology", chg=2.0),
        _row("BBB", sector="Technology", chg=1.0),
        _row("CCC", sector="Technology", chg=-1.0),
    ]
    built = _builder()._build_hub_context(tmp_path / "site", rows)["hub"]
    assert built["themes_asof"] == "2026-08-07"
    assert [m["t"] for m in built["themes"][0]["members"]] == ["AAA", "BBB", "CCC"]


# ── theme-token law ─────────────────────────────────────────────────────────
def test_treemap_fill_is_always_a_token_never_a_literal_colour():
    """The defect this page was rebuilt for: a literal colour a theme can miss.

    Every tile fill must be a var(--hm*) reference so the ramp tracks --up/--down,
    including the red-up/green-down swap under html[data-lang="zh"].
    """
    for r in (-40.0, -3.1, -2.0, -0.9, -0.05, 0.0, 0.05, 0.9, 2.0, 3.1, 40.0):
        fill = hub.tone_var(r)
        assert re.fullmatch(r"var\(--hm(?:0|[ud][1-4])\)", fill), fill


def test_stylesheet_declares_no_literal_surface_colour():
    """No hard-coded background may re-enter the hub stylesheet.

    The bug: `.card` carried a dark rgba() rescued by a [data-theme="light"]
    override on the base rule only, so `.card:hover` — which had no light twin —
    repainted every hovered card charcoal in light mode.
    """
    tpl = (ROOT / "templates" / "ticker_index.html.j2").read_text()
    css = tpl.split("<style>", 1)[1].split("</style>", 1)[0]
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)          # drop comments
    offenders = []
    for m in re.finditer(r"(background(?:-color)?)\s*:\s*([^;{}]+)", css):
        val = m.group(2).strip()
        if re.search(r"rgba?\(|#[0-9a-fA-F]{3,8}\b|\bhsla?\(", val):
            offenders.append(val)
    assert not offenders, (
        f"literal surface colours in the hub stylesheet: {offenders} — a theme "
        "override can miss one, which is exactly how the charcoal hover shipped"
    )


def test_hub_uses_one_ui_face_with_tabular_figures_not_monospace():
    """Data alignment must not turn the market hub into a terminal texture."""
    tpl = (ROOT / "templates" / "ticker_index.html.j2").read_text()
    css = tpl.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "var(--font-mono)" not in css
    assert "var(--font-ui)" in css
    assert "font-variant-numeric: tabular-nums" in css


# ── client payload + crawl links ────────────────────────────────────────────
def test_search_index_column_order_matches_the_client_constants():
    """The client reads this array positionally; a silent reorder mislabels rows."""
    rows = [{"ticker": "AAA", "name": "Alpha", "sector": "Tech", "price_f": 12.5,
             "chg": -1.25, "stance_key": "uptrend", "cap_bn": 310.4, "rvol": 2.5,
             "pos52": 88.8}]
    got = hub.search_index(rows)[0]
    assert got == ["AAA", "Alpha", "Tech", 12.5, -1.25, "uptrend", 310, 2.5, 88.8]

    tpl = (ROOT / "templates" / "ticker_index.html.j2").read_text()
    m = re.search(r"var\s+T\s*=\s*0\s*,(.*?);", tpl, re.S)
    assert m, "the positional column constants vanished from the template"
    assert re.search(r"NM\s*=\s*1", m.group(1))
    assert re.search(r"SC\s*=\s*2", m.group(1))
    assert re.search(r"PX\s*=\s*3", m.group(1))
    assert re.search(r"CH\s*=\s*4", m.group(1))
    assert re.search(r"STK\s*=\s*5", m.group(1))
    assert re.search(r"CAP\s*=\s*6", m.group(1))
    assert re.search(r"RV\s*=\s*7", m.group(1))


def test_directory_keeps_a_link_for_every_covered_name():
    """This is what let the page stop rendering 1,544 cards.

    The A-Z index is the crawl hub's whole reason to exist; dropping a ticker
    here silently orphans that dossier from internal linking.
    """
    tickers = [f"T{i:04d}" for i in range(1544)] + ["3M", "AAPL"]
    rows = [{"ticker": t} for t in tickers]
    got = {t for g in hub.directory(rows) for t in g["tickers"]}
    assert got == set(tickers)


def test_directory_files_non_alpha_tickers_rather_than_dropping_them():
    got = hub.directory([{"ticker": "3M"}, {"ticker": "AAPL"}])
    assert {g["letter"] for g in got} == {"#", "A"}


# ── treemap geometry ────────────────────────────────────────────────────────
def _payload(n=40):
    return {
        "default_tf": "1D",
        "timeframes": [{"key": "1D", "available": True}],
        "sectors": [{"key": "Tech", "en": "Technology", "zh": "科技"}],
        "tiles": [{"t": f"T{i}", "name": f"Name {i}", "sector": "Tech",
                   "size": 1.0 + i, "perf": {"1D": (i % 9) - 4.0}} for i in range(n)],
    }


def test_treemap_tiles_stay_inside_the_viewbox():
    tm = hub.treemap(_payload())
    assert tm and tm["n"] > 0
    for sec in tm["sectors"]:
        for t in sec["tiles"]:
            assert t["x"] >= -0.6 and t["y"] >= -0.6
            assert t["x"] + t["w"] <= tm["w"] + 0.6
            assert t["y"] + t["h"] <= tm["h"] + 0.6


def test_treemap_only_links_tickers_that_ship_a_page():
    """A tile linking to a dossier we never rendered is a 404 in the map."""
    tm = hub.treemap(_payload(12), linkable=frozenset({"T0", "T1"}))
    hrefs = {t["t"]: t["href"] for s in tm["sectors"] for t in s["tiles"]}
    assert hrefs.get("T0") == "T0.html"
    assert all(v is None for k, v in hrefs.items() if k not in {"T0", "T1"})


def test_treemap_is_none_when_the_payload_is_missing_or_empty():
    """The map is auth-gated upstream; its absence must not take the page down."""
    assert hub.treemap(None) is None
    assert hub.treemap({"tiles": []}) is None
    assert hub.treemap({**_payload(), "timeframes": [{"key": "1D", "available": False}]}) is None


def test_breadth_and_shape_survive_an_empty_universe():
    assert hub.breadth([]) is None
    assert hub.day_shape([]) is None
    assert hub.boards([])["gainers"] == []
