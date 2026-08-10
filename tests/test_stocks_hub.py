"""Contract tests for the /stocks/ market hub (engine/stocks_hub.py).

Each test pins a defect that shipped, or nearly shipped, on this surface:

* the sector filter that silently showed you half a sector,
* two different "% green" numbers printed side by side,
* a surface colour a theme override could miss,
* the crawl-hub links the redesign had to keep,
* volume boards filling with phantom zeros or with illiquid noise.
"""
from __future__ import annotations

import json
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


# ═══════════════════════════════════════════════════════════════════════════
# Pressure Watch band
# ═══════════════════════════════════════════════════════════════════════════
# The band displays a record of shocks that mostly did NOT recover, sitting
# directly under six opportunity-shaped mover boards. Every test here pins a way
# that framing could quietly invert: an ordering that ranks, a chip that invents
# evidence, a comparison that names peers a row never had, or copy that only
# tells the truth in one of the two languages the page ships.

_PP_FIXTURE = ROOT / "tests" / "fixtures" / "price_pressure_latest.json"


def _pp() -> dict:
    return json.loads(_PP_FIXTURE.read_text(encoding="utf-8"))


def _pp_band(board_asof: str = "2026-07-02"):
    return hub.pressure_band(_pp(), board_asof=board_asof)


def _pp_strings(node, out=None):
    """Every user-facing string the band emits, at any depth."""
    out = [] if out is None else out
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in {"cls", "end_cls", "key", "side", "mode", "t"}:
                _pp_strings(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _pp_strings(v, out)
    return out


def test_pressure_band_warms_up_rather_than_failing():
    """No artifact is the state this surface SHIPS in — it must be renderable.

    The band lands ahead of the engine that writes its artifact, so the absent
    path is the first thing real users see. It has to carry a title, a plain
    line and a stance, and it must never raise on junk.
    """
    for payload in (None, {}, [], "not a dict", 0):
        band = hub.pressure_band(payload)
        assert band["mode"] == "warmup"
        assert band["title_en"] and band["title_zh"]
        assert band["warm_en"] and band["warm_zh"]
        assert band["stance_en"] and band["stance_zh"], "a panel without a stance"
        assert band["base"] is None and band["open"] == [] and band["resolved"] == []


def test_pressure_band_falls_back_to_warmup_when_the_artifact_trails_the_page():
    """A month-old event list beside today's boards is a lie of juxtaposition."""
    assert _pp_band("2026-07-08")["mode"] == "live"    # 4 weekdays on
    assert _pp_band("2026-07-10")["mode"] == "warmup"  # 6 weekdays on
    # No page session to compare against: show what we have rather than nothing.
    assert hub.pressure_band(_pp())["mode"] == "live"


def test_open_events_are_ordered_by_recency_never_by_size():
    """Ordering by |move| or by how unusual it was IS ranking.

    The fixture is built so the two orders disagree: VKTX carries the largest
    move and the largest deviation and is the OLDEST event, so a magnitude sort
    would put it first. Recency puts it last, and the same-day pair breaks to
    ticker A-Z.
    """
    band = _pp_band()
    assert [e["t"] for e in band["open"]] == ["CDE", "ARQT", "IONQ", "VKTX"]

    raw = _pp()["open_events"]
    by_move = [r["ticker"] for r in sorted(raw, key=lambda r: -abs(r["resid"]))]
    by_z = [r["ticker"] for r in sorted(raw, key=lambda r: -abs(r["resid_z"]))]
    assert [e["t"] for e in band["open"]] != by_move
    assert [e["t"] for e in band["open"]] != by_z


def test_recency_order_is_stable_under_the_display_cap():
    """Capping must trim the OLDEST rows, never reshuffle the newest ones."""
    payload = _pp()
    payload["open_events"] = payload["open_events"] * 3  # 12 rows, dates repeat
    band = hub.pressure_band(payload, board_asof="2026-07-02")
    assert len(band["open"]) == hub.PW_MAX_OPEN
    assert band["open"][0]["t"] == "CDE"
    assert band["open"][0]["when_en"] == "Jul 1"
    # The cap is disclosed rather than silent.
    assert "6" in band["count_en"] and "12" in band["count_en"]
    assert "6" in band["count_zh"] and "12" in band["count_zh"]
    assert band["count_en"] != _pp_band()["count_en"]


def test_the_word_peers_never_appears_on_a_market_basis_row():
    """The peer helper falls back to a whole-universe mean for unlabelled names.

    Roughly two thirds of the panel is unlabelled, so "peers implied" on those
    rows would name a comparison group the row never had.
    """
    rows = {e["t"]: e for e in _pp_band()["open"]}
    assert rows["IONQ"]["cmp_en"] == "the market moved +1.4%"
    assert "peer" not in rows["IONQ"]["cmp_en"].lower()
    assert "同业" not in rows["IONQ"]["cmp_zh"]
    assert rows["ARQT"]["cmp_en"].startswith("peers moved")
    assert "同业" in rows["ARQT"]["cmp_zh"]


def test_a_basket_that_moved_with_the_name_leads_the_comparison():
    """CDE's GICS sector is chemicals and steel; its basket is silver miners.

    On a silver-complex selloff "peers implied" is economically false on exactly
    the day the row matters, so where a basket moved the same way it leads and
    the sector clause steps back to the hover.
    """
    cde = next(e for e in _pp_band()["open"] if e["t"] == "CDE")
    assert cde["cmp_en"] == "its Silver miners basket fell 3.4% too"
    assert "白银矿业" in cde["cmp_zh"]
    assert "silver-miners" not in cde["cmp_en"], "raw slug reached the glance tier"
    assert "its sector" in cde["tip_en"], "the basis is demoted, not lost"

    # The producer also carries a curated English display label. It is more
    # informative than prettifying the stable machine key and must win when
    # available.
    payload = _pp()
    payload["open_events"][0]["basket_en"] = "Silver miners (Equal-Weight)"
    labelled = hub.pressure_band(payload, board_asof="2026-07-02")["open"][0]
    assert labelled["cmp_en"].startswith("its Silver miners (Equal-Weight) basket")

    # A basket that moved the OTHER way is not evidence about this move.
    payload = _pp()
    payload["open_events"][0]["basket_ret"] = 0.02
    other = hub.pressure_band(payload, board_asof="2026-07-02")["open"][0]
    assert "basket" not in other["cmp_en"]
    assert other["cmp_en"].startswith("peers moved")


def test_an_uncovered_name_is_never_told_it_has_no_filing():
    """"We did not look" and "we looked and found nothing" are different facts.

    CDE is not in the filings panel. Printing "no filing on record" for it would
    manufacture evidence out of a coverage gap.
    """
    rows = {e["t"]: e for e in _pp_band()["open"]}
    assert rows["CDE"]["fam_en"] == "filings not tracked"
    assert "no filing" not in rows["CDE"]["fam_en"].lower()
    assert "not a claim" in rows["CDE"]["fam_tip_en"]
    assert "并不代表" in rows["CDE"]["fam_tip_zh"]
    # And the covered name that genuinely has none still says so.
    assert rows["ARQT"]["fam_en"] == "no filing on record"
    assert "found none" in rows["ARQT"]["fam_tip_en"]


def test_state_words_are_plain_and_side_aware():
    """The same fraction means "recovered" falling and "unwound" rising."""
    rows = {e["t"]: e for e in _pp_band()["open"]}
    assert rows["ARQT"]["state_en"] == "still falling"
    assert rows["IONQ"]["state_en"] == "still climbing"
    assert rows["VKTX"]["state_en"] == "44% unwound"
    assert rows["VKTX"]["state_zh"] == "已回落 44%"
    assert rows["CDE"]["state_en"] == "holding"
    assert all("_" not in e["state_en"] for e in rows.values())


def test_closed_episodes_report_both_sides_and_keep_the_dead_ones():
    """Losers never leave the table — a delisting is an outcome, not a gap."""
    band = _pp_band()
    ends = {r["t"]: (r["end_en"], r["end_cls"]) for r in band["resolved"]}
    assert ends["SGMO"] == ("kept the lower price", "low")
    assert ends["BEAM"] == ("back to where it started", "low")
    assert ends["ATRA"] == ("stopped trading", "gone")
    assert {r["side"] for r in band["resolved"]} == {"up", "down"}
    assert all("21D" not in r["end_en"] for r in band["resolved"])


def test_the_outcome_bar_is_a_complete_distribution_worst_first():
    """Delisted names lead the bar; every non-zero outcome stays visible."""
    seg = _pp_band()["base"]["segments"]
    assert [s["key"] for s in seg] == [
        "delisted", "accepted_lower", "partial", "recovered"]
    assert abs(sum(s["w"] for s in seg) - 100.0) < 1.0
    assert all(s["w"] >= 0.6 for s in seg), "a real outcome rendered as nothing"
    assert [s["pc"] for s in seg] == ["3%", "57%", "19%", "21%"]

    # An outcome with no share renders NOTHING rather than a decorative stub.
    payload = _pp()
    payload["base_rates"]["down"]["h21_share_delisted"] = 0.0
    thinner = hub.pressure_band(payload, board_asof="2026-07-02")["base"]["segments"]
    assert "delisted" not in [s["key"] for s in thinner]


def test_the_headline_translates_its_number_and_prints_the_null():
    """Law 3 — a share arrives as information, not as a statistic."""
    base = _pp_band()["base"]
    assert base["headline_en"] == (
        "After a drop like this, about 6 in 10 were still down a month later.")
    assert base["headline_zh"] == "出现这样的下跌之后，约六成在一个月后仍未收复。"
    assert "0.57" not in base["headline_en"] and "57%" not in base["headline_en"]
    assert "no measurable difference" in base["null_en"]
    assert "没有可测出的差别" in base["null_zh"]


def test_a_broad_selloff_day_leads_with_the_banner_and_demotes_the_rows():
    """Structural honesty, not a note: the market-wide read comes first."""
    payload = _pp()
    payload["day"]["banner"] = True
    band = hub.pressure_band(payload, board_asof="2026-07-02")
    assert band["banner"]["en"] == (
        "Most of today's pressure is market-wide, not single-name.")
    assert band["banner"]["zh"].startswith("今天的压力")
    assert "38" in band["banner"]["tip_en"]
    assert band["demoted"] is True
    assert _pp_band()["demoted"] is False, "no banner, no demotion"

    # An engine-supplied day sentence wins over the house default.
    payload["day"]["banner"] = {"en": "Rates repriced the whole tape.",
                                "zh": "利率重新定价了整条行情。"}
    supplied = hub.pressure_band(payload, board_asof="2026-07-02")
    assert supplied["banner"]["en"] == "Rates repriced the whole tape."


def test_a_residual_is_never_relabelled_as_a_price_move():
    """`resid` is the unexplained part of a move, not the move.

    With `ret` the line reads as a price change; without it the line has to say
    what it is actually quoting rather than quietly printing the residual under
    a price verb.
    """
    assert _pp_band()["open"][0]["move_en"] == "fell 11.9% on 6.1× volume"

    payload = _pp()
    for row in payload["open_events"]:
        row.pop("ret")
    bare = hub.pressure_band(payload, board_asof="2026-07-02")["open"][0]
    assert bare["move_en"] == "fell 9.8% more than the rest of the market on 6.1× volume"
    assert "11.9" not in bare["move_en"]


def test_every_english_string_ships_a_chinese_twin():
    """Bilingual parity, structurally: no `_en` key without its `_zh`."""
    def walk(node, path="P"):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.endswith("_en"):
                    zh = k[:-3] + "_zh"
                    assert zh in node, f"{path}.{k} has no {zh}"
                    assert node[zh] is not None or node[k] is None, \
                        f"{path}.{zh} is empty while {k} is not"
                if k == "en":
                    assert "zh" in node, f"{path} has en without zh"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    payload = _pp()
    payload["day"]["banner"] = True
    payload["gaps"] = ["Two sessions are missing from the store."]
    walk(hub.pressure_band(payload, board_asof="2026-07-02"))
    walk(hub.pressure_band(None))


def test_chinese_copy_is_not_english_left_untranslated():
    """A ZH string byte-identical to its EN twin is an untranslated row."""
    band = _pp_band()
    for row in band["open"] + band["resolved"]:
        for key in ("move", "cmp", "fam", "state", "end"):
            en, zh = row.get(f"{key}_en"), row.get(f"{key}_zh")
            if en and zh and any(c.isalpha() for c in en):
                assert zh != en, f"{row['t']} {key} was never translated"
                assert any("一" <= c <= "鿿" for c in zh), \
                    f"{row['t']} {key}_zh carries no Chinese"


BANNED_TIER1 = (
    # Adversarial ruling #2208 — interpretive spin on tape rows.
    "bounce", "dead-cat", "dead cat", "giveback", "manipulated",
    # House-law words and internal epistemics vocabulary.
    "validated", "falsifier", "refuted", "证伪", "prereg", "gauntlet",
    "display-tier", "lobe", "organ", "kernel",
    # Untranslated statistics and machine identifiers.
    "z-score", "n=", "resid", "_21d", "peer_basis",
)


def test_no_banned_vocabulary_in_anything_the_band_emits():
    """Every string, both languages, both modes — including the hover tier.

    Kept as one blanket assertion rather than a Tier-1-only check: the receipts
    are allowed to be technical, but they are not allowed to be jargon, and the
    hover tier is where jargon actually accumulates.
    """
    payload = _pp()
    payload["day"]["banner"] = True
    for band in (hub.pressure_band(payload, board_asof="2026-07-02"),
                 hub.pressure_band(None)):
        for s in _pp_strings(band):
            low = s.lower()
            for word in BANNED_TIER1:
                assert word not in low, f"banned {word!r} in {s!r}"
            assert "_" not in s, f"machine slug in {s!r}"


def test_the_help_card_carries_the_receipts_the_glance_tier_cannot():
    """Tier 2 is where the record's size, span, scope and source live."""
    help_ = _pp_band()["help"]
    keys = {r["k_en"] for r in help_["rows"]}
    assert {"What counts", "The record", "Coverage", "By filing type", "Scope"} <= keys
    body = " ".join(r["v_en"] for r in help_["rows"])
    assert "17,511" in body and "2021-09-01" in body
    assert "five years, not twenty" in body, "the span is rolling and must say so"
    assert "Five days in" in body, "the second horizon is published too"
    assert "tracked window only" in body, "the scope sentence is mandatory"
    assert "no difference showed up" in body, "the measured null must be printed"
    assert "Liquidity-shock reversal study, phase 0" in help_["receipt_en"]
    assert "来源：" in help_["receipt_zh"]
    # No family x horizon grid: the contrast it invites is the one measured null.
    assert "table" not in json.dumps(help_)


def test_gaps_are_printed_rather_than_hidden():
    payload = _pp()
    payload["gaps"] = [{"en": "Two sessions are missing.", "zh": "缺少两个交易日。"},
                       "A plain string gap."]
    band = hub.pressure_band(payload, board_asof="2026-07-02")
    assert [g["en"] for g in band["gaps"]] == ["Two sessions are missing.",
                                               "A plain string gap."]
    assert band["gaps"][0]["zh"] == "缺少两个交易日。"


def test_the_band_survives_a_half_built_artifact():
    """Fail-soft in the strong sense: partial data degrades, never raises."""
    assert hub.pressure_band({"asof": "2026-07-02"})["mode"] == "warmup"
    only_open = hub.pressure_band({"asof": "2026-07-02",
                                   "open_events": [{"ticker": "AAA", "side": "down",
                                                    "date": "2026-07-01"}]})
    assert only_open["mode"] == "live" and only_open["base"] is None
    assert only_open["open"][0]["move_en"] == "moved sharply"
    assert only_open["open"][0]["cmp_en"] == ""
    # Rows with no ticker cannot be rendered and must not become blank links.
    junk = hub.pressure_band({"asof": "2026-07-02",
                              "open_events": [{"side": "down"}, None]})
    assert junk["mode"] == "warmup"
