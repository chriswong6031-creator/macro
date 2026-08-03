"""Rendered-HTML contract for the HK board priority display layer (hk_prophet_v1).

Program: research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md
Gates covered here: G1 (the seven witnesses are visible), G2 (leaders lane),
G3 (ran lane, marker-anchored, fail-closed on unknown age), G4 (stage buckets +
filter chips + featured + priority score), G9 (fail-soft on pre-v1 artifacts).

TWO SHAPES, ONE TEMPLATE.  The committed `site/factordata/hk_standouts.json`
carries NONE of the v1 fields (stage / prophet / featured / new / theme, the
`ran[]` and `leaders[]` arrays, the `ranking` block) — the first nightly after the
engine lane merges fills them.  So the assertions come in pairs: the new schema
must produce the priority surface, and the OLD schema must still produce the flat
three-lane board with none of it.  A regression that quietly drops the fail-soft
branch would ship a broken board on merge night, when the artifact on disk is
still the old one.

ASSERTION STYLE (harness law): every presence/absence assertion targets a full
markup string (`'<div class="nb-stage-hd sg-live"'`), never a bare class token.
pv_css() and this page's own <style> block emit the class SELECTORS as literal
text on every render, so `'nb-stage-hd' in html` is true even when nothing
renders — an absence test written that way is vacuous.

`production_fixture()` is also the fixture the screenshot pass uses, so the
picture and the test see the same shapes.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from zlib import crc32

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "site" / "factordata" / "hk_standouts.json"

_STAGE_ORDER = ["live", "setting_up", "ran", "blocked"]

# The hk_leadership cohort, as it reaches the template's theme slot (HKRV-R5:
# display-tier context — it boosts the leaders table's order and nothing else).
_COHORT = {"id": "hk_leadership", "name": "HK mega-cap leaders",
           "name_zh": "港股大市值龙头", "rank": 1, "bull_days": 3}


# --------------------------------------------------------------------------- #
# Render harness — the whole page, both modes of the contract
# --------------------------------------------------------------------------- #

def _render(setups: dict | None, mode: str = "stocks") -> str:
    """Render templates/hk.html.j2 with a minimal vm and return the HTML."""
    from engine import i18n

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("hk.html.j2").render(**_vm(setups, mode))


def _render_source(src: str, setups: dict | None, mode: str = "stocks") -> str:
    """Render an ARBITRARY hk.html.j2 source (e.g. the base branch's) with the same
    vm — the other half of the fail-soft proof."""
    from engine import i18n
    from jinja2 import ChoiceLoader, DictLoader

    env = Environment(
        loader=ChoiceLoader([DictLoader({"hk.html.j2": src}),
                             FileSystemLoader(str(ROOT / "templates"))]),
        autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("hk.html.j2").render(**_vm(setups, mode))


def _vm(setups: dict | None, mode: str) -> dict:
    return {
        "mode": mode,
        "latest": {"date": "2026-07-31", "quad_name": "Goldilocks", "quad": "Q1",
                   "liquidity_overlay": "neutral", "pending_quad": None},
        "actions": {"buy_now": [], "buy_soon": [], "on_the_run": [],
                    "take_profits": [], "hold": [], "avoid": []},
        "setups": setups,
        "gv": None, "market_state": None, "hk_scoreboard": None,
        "sectors_by_ticker": {}, "velocity_desk": None,
        "built": "2026-07-31T00:00:00Z",
        "hk_breadth": None, "hk_full_breadth": None, "benchmark": None,
        "hk_sectors": [], "hk_flow": None, "track_record": None, "hk_ab": None,
        "hk_dispersion": None, "hk_cycles": None, "hk_indicators": None,
        "state_display_json": "{}", "washout_desk": None, "freshness": None,
        "hk_history": None, "hk_news": None, "hk_policy": None, "hk_macro": None,
        "hk_property": None, "hk_alerts": None, "hk_market_drivers": None,
        "hk_conditions": None, "hk_signal_stack": None, "hk_event_calendar": None,
        "hk_context_chips": None, "velocity_desk_picks": None, "hk_lab_button": None,
        "index_health": None, "hk_1d_velocity_desk": None,
    }


def _tags(html: str) -> list[str]:
    """The element stream — open/close tag names in document order.  The fail-soft
    contract is about STRUCTURE, so the comparison ignores text and attributes: CSS
    added inside the existing <style> element must be free, a new element must not."""
    return ["".join(m) for m in re.findall(r"<\s*(/?)([a-zA-Z][a-zA-Z0-9-]*)", html)]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def committed_artifact() -> dict:
    return json.loads(ARTIFACT.read_text())


def _stage_of(row: dict) -> str:
    """The engine's own grouping rule (masterplan §3.1 / us_board_rank parity):
    entry_signal.status decides, and a blocking marker forces `blocked`."""
    last = (row.get("signal") or {}).get("last") or {}
    if last.get("quality") == "block":
        return "blocked"
    return {
        "buy_now": "live", "partial": "live", "buy_soon": "live",
        "await_confluence": "setting_up", "bounce_wait": "setting_up", "watch": "setting_up",
        "extended": "ran", "topping": "ran", "hold": "ran",
        "blocked": "blocked", "exit": "blocked", "avoid": "blocked",
    }.get((row.get("entry_signal") or {}).get("status") or "", "setting_up")


_ENTRY_VALUE = {"buy_now": 25, "partial": 21, "buy_soon": 14, "await_confluence": 11,
                "bounce_wait": 9, "watch": 6, "hold": 5, "extended": 4, "topping": 3,
                "blocked": 0, "exit": 0, "avoid": 0}


def _pseudo_score(ticker: str, status: str = "") -> float:
    """Stable 0–100 stand-in for the real priority score: the true entry leg plus a
    deterministic stand-in for the other 75 points.  crc32, not hash() — hash() is
    salted per process, so a hashed fixture would reorder between runs."""
    return round(_ENTRY_VALUE.get(status, 6) + (crc32(ticker.encode()) % 7000) / 100.0, 1)


def hk_priority_overlay(rows: list[dict], *, board_cap: int = 8, sector_cap: int = 3,
                        cohort: set[str] | None = None) -> list[dict]:
    """Stamp the frozen hk_prophet_v1 row contract onto buy rows and return them in
    the order the engine promises: stage bucket first (live → setting_up → ran →
    blocked), priority score desc inside the bucket, ticker as the tiebreak.

    Mutates copies, never the inputs.  Deterministic for a given input order.
    """
    cohort = cohort if cohort is not None else set()
    out = []
    for i, row in enumerate(rows):
        row = dict(row)
        ticker = row.get("ticker") or f"T{i}"
        status = (row.get("entry_signal") or {}).get("status") or ""
        row["stage"] = _stage_of(row)
        row["prophet"] = {"version": "hk_prophet_v1", "score": _pseudo_score(ticker, status),
                          "components": {"signal": 26.0, "entry": 21.0, "edge": 17.5,
                                         "runway": 0.0, "quality": 8.0}}
        row["days_since_signal"] = i % 9
        row["new"] = row["days_since_signal"] <= 2 and row["stage"] == "live"
        if ticker in cohort:
            row["theme"] = dict(_COHORT)
            row["theme_confirmed"] = (i % 3 == 0)
        out.append(row)

    out.sort(key=lambda r: (_STAGE_ORDER.index(r["stage"]), -r["prophet"]["score"], r["ticker"]))

    per_sector: dict[str, int] = {}
    featured = 0
    for row in out:
        sector = row.get("sector") or "—"
        ok = (row["stage"] == "live"
              and (row.get("entry_signal") or {}).get("status") in ("buy_now", "partial")
              and featured < board_cap and per_sector.get(sector, 0) < sector_cap
              and not row.get("extended"))
        row["featured"] = bool(ok)
        if ok:
            featured += 1
            per_sector[sector] = per_sector.get(sector, 0) + 1
    for rank, row in enumerate(out, 1):
        row["score_rank"] = rank
        row["display_rank"] = rank
    return out


# The seven witnesses (masterplan §1): every one of them bottomed 2026-06-26 and ran
# +8.7%…+44.0% by 07-31 while the board's eligibility fell 47 → 5.  9961.HK is named
# Trip.com Group here — engine/hk_adr_bridge.py:78 pairs the ticker with PDD and
# engine/market_heatmap.py:106 with 携程集团; the two disagree, and a display fixture
# must not commit a screenshot carrying a company name that may be wrong.
WITNESSES = [
    ("0700.HK", "Tencent Holdings", "腾讯控股", "Communication Services", 601.0, 21.4),
    ("9988.HK", "Alibaba Group", "阿里巴巴", "Consumer Discretionary", 118.9, 30.2),
    ("9618.HK", "JD.com", "京东集团", "Consumer Discretionary", 132.4, 15.8),
    ("1810.HK", "Xiaomi", "小米集团", "Technology", 55.2, 26.6),
    ("3690.HK", "Meituan", "美团", "Consumer Discretionary", 148.7, 44.0),
    ("1024.HK", "Kuaishou", "快手", "Communication Services", 62.1, 8.7),
    ("9961.HK", "Trip.com Group", "携程集团", "Consumer Discretionary", 494.0, 12.3),
]
WITNESS_TICKERS = [w[0] for w in WITNESSES]


def _a_real_spark() -> str:
    """Borrow a real pre-rendered sparkline off the committed artifact. The card
    recolors it to the verb hue in CSS, so any row's SVG is visually valid on any
    other — and a fixture whose cards have no chart produces a screenshot of a board
    that does not exist."""
    for row in committed_artifact().get("buy") or []:
        if row.get("spark_svg"):
            return row["spark_svg"]
    return ""


def _witness_buy_row(w, status: str, block_reason: str | None = None) -> dict:
    tk, name, name_zh, sector, price, _ = w
    return {
        "ticker": tk, "name": name, "name_zh": name_zh,
        "sector": sector, "sector_zh": sector,
        "price": price, "alpha": 1.2, "off_high": -6.4, "dir": "up",
        "label": "BOTTOMING", "label_zh": "筑底中", "group": "entry_open",
        "conviction": {"score": 71, "verdict": "Leader turning up",
                       "verdict_zh": "龙头转强", "cautions": [], "cautions_zh": [],
                       "vol_squeeze": None},
        "entry_signal": {"status": status, "headline": "Partial entry — half size now",
                         "headline_zh": "部分入场 — 当前可建半仓",
                         "buy_zone": {"low": round(price * 0.96, 2),
                                      "high": round(price * 1.01, 2)}},
        "signal": {"asof": "2026-07-31",
                   "last": ({"quality": "block", "reason": block_reason, "type": "buy"}
                            if block_reason else {"quality": "ok", "reason": None})},
        "lead": {"en": "Leader cohort participating.", "zh": "龙头组合正在参与。"},
        "ah_value": None, "southbound": None, "extended": False,
        "spark_svg": _a_real_spark(),
    }


def _witness_ran_row(w, *, sessions: int | None, pct: float | None,
                     anchor: str, confirmed: bool) -> dict:
    tk, name, name_zh, sector, price, run = w
    row = {"ticker": tk, "name": name, "name_zh": name_zh, "sector": sector,
           "sector_zh": sector, "price": price, "sessions_since": sessions,
           "cross_date": "2026-07-14", "pct_since": pct, "anchor": anchor,
           "label": "RALLY", "label_zh": "上涨中"}
    if confirmed:
        row["theme"] = dict(_COHORT)
        row["theme_confirmed"] = True
        row["theme_note"] = "Leader group just confirmed — watch for the next entry"
        row["theme_note_zh"] = "龙头组合刚确认 —— 关注下一个买点"
    return row


def _witness_leader_row(w, *, themed: bool, zone: bool, confirmed: bool = False) -> dict:
    tk, name, name_zh, sector, price, run = w
    row = {"ticker": tk, "name": name, "name_zh": name_zh, "sector": sector,
           "sector_zh": sector, "price": price, "alpha": round(run / 20.0, 2),
           "off_high": -round(run / 8.0, 1), "label": "UPTREND", "label_zh": "上升趋势",
           "extended": run > 40}
    if zone:
        row["entry_signal"] = {"buy_zone": {"low": round(price * 0.93, 2),
                                            "high": round(price * 0.97, 2)}}
    if themed:
        row["theme"] = dict(_COHORT)
        row["theme_confirmed"] = confirmed
    return row


def production_fixture() -> dict:
    """The committed artifact plus the hk_prophet_v1 overlay — the shape the first
    nightly after the engine lane merges will ship.  Used by the tests AND by the
    screenshot pass, so the picture and the assertions never drift apart."""
    art = committed_artifact()
    su = dict(art)

    # Each witness appears in exactly ONE lane. A name carded in `blocked` while it
    # also sits in "Recently fired" is two contradictory stances for one ticker, and
    # the committed watch list already contains 1024.HK — so the witnesses claim
    # their tickers first and the artifact's own rows yield.
    carded = [
        _witness_buy_row(WITNESSES[3], "buy_now"),                                       # Xiaomi
        _witness_buy_row(WITNESSES[6], "partial"),                                       # Trip.com
        _witness_buy_row(WITNESSES[2], "blocked", "failed reclaim-and-hold"),            # JD
        _witness_buy_row(WITNESSES[1], "blocked", "counter-trend, no 200-reclaim/hold"),  # Alibaba
    ]
    ran_rows = [
        _witness_ran_row(WITNESSES[4], sessions=11, pct=44.0, anchor="marker", confirmed=True),
        _witness_ran_row(WITNESSES[0], sessions=9, pct=21.4, anchor="approx", confirmed=False),
        _witness_ran_row(WITNESSES[5], sessions=6, pct=None, anchor="marker", confirmed=False),
    ]
    claimed = {r["ticker"] for r in carded} | {r["ticker"] for r in ran_rows}

    # The real buy rows, plus the watch rows promoted into the board (v1 shows the
    # blocked and setting-up names instead of hiding them).
    rows = [dict(r) for r in (art.get("buy") or []) if r.get("ticker") not in claimed]
    for w in art.get("watch") or []:
        if w.get("ticker") in claimed:
            continue
        r = dict(w)
        r["entry_signal"] = dict(r.get("entry_signal") or {})
        r["entry_signal"].setdefault("status", "await_confluence")
        rows.append(r)
    rows += carded

    su["buy"] = hk_priority_overlay(rows, cohort=set(WITNESS_TICKERS))
    su["ran"] = ran_rows
    su["leaders"] = [
        _witness_leader_row(WITNESSES[4], themed=True, zone=False, confirmed=True),
        _witness_leader_row(WITNESSES[1], themed=True, zone=True),
        _witness_leader_row(WITNESSES[3], themed=True, zone=False),
        _witness_leader_row(WITNESSES[0], themed=True, zone=True),
        _witness_leader_row(WITNESSES[2], themed=False, zone=False),
        _witness_leader_row(WITNESSES[6], themed=False, zone=True),
        _witness_leader_row(WITNESSES[5], themed=True, zone=False),
    ]
    su["lane_counts"] = {
        "featured": sum(1 for r in su["buy"] if r.get("featured")),
        "live": sum(1 for r in su["buy"] if r["stage"] == "live"),
        "setting_up": sum(1 for r in su["buy"] if r["stage"] == "setting_up"),
        "ran": sum(1 for r in su["buy"] if r["stage"] == "ran"),
        "blocked": sum(1 for r in su["buy"] if r["stage"] == "blocked"),
        "ran_lane": len(su["ran"]),
    }
    su["board_definition"] = "hk_prophet_v1"
    su["ranking"] = {
        "version": "hk_prophet_v1",
        "weights": {"signal": 0.30, "entry": 0.25, "edge": 0.25,
                    "runway": 0.10, "quality": 0.10},
        "component_coverage": {"runway": {"nonzero": 0, "n": len(su["buy"])},
                               "signal": {"nonzero": len(su["buy"]), "n": len(su["buy"])}},
    }
    return su


@pytest.fixture(scope="module")
def prio_html() -> str:
    return _render(production_fixture())


@pytest.fixture(scope="module")
def legacy_html() -> str:
    return _render(committed_artifact())


# --------------------------------------------------------------------------- #
# G4 — stage buckets, in order, above every card they own
# --------------------------------------------------------------------------- #

def test_stage_headings_render_in_priority_order(prio_html):
    positions = []
    for sk in _STAGE_ORDER:
        marker = '<div class="nb-stage-hd sg-%s" data-stage="%s"' % (sk, sk)
        idx = prio_html.find(marker)
        assert idx != -1, "stage heading missing for bucket %r" % sk
        positions.append(idx)
    assert positions == sorted(positions), (
        "stage headings must render live → setting_up → ran → blocked, got %r" % positions)


def test_stage_heading_carries_label_count_and_stance(prio_html):
    su = production_fixture()
    n_live = sum(1 for r in su["buy"] if r["stage"] == "live")
    block = prio_html[prio_html.find('<div class="nb-stage-hd sg-live"'):]
    block = block[:block.find("</div>") + 6]
    assert '<span class="sh-l"><span class="l-en">Live now</span>' in block
    assert '<span class="l-zh">现在可操作</span>' in block
    assert '<span class="sh-n">%d</span>' % n_live in block
    assert '<span class="l-en">entry window is open</span>' in block


def test_no_blocked_card_above_a_live_card(prio_html):
    """The G4 no-blocked-above-live rule, read off the rendered card order rather
    than off the fixture: a card carries its bucket as data-stage."""
    order = re.findall(r'<a class="pvcard[^"]*" href="hk_lookup\.html#[^"]+" '
                       r'data-ticker="[^"]+" data-stage="([a-z_]+)"', prio_html)
    assert order, "no staged cards rendered"
    assert order.index("live") < order.index("blocked")
    assert order == sorted(order, key=_STAGE_ORDER.index), (
        "cards must never leave their bucket: %r" % order)


def test_every_priority_card_carries_a_stage_attribute(prio_html):
    n_cards = prio_html.count('<a class="pvcard')
    n_staged = len(re.findall(r'<a class="pvcard[^"]*"[^>]*data-stage="', prio_html))
    assert n_cards == n_staged == len(production_fixture()["buy"])


# --------------------------------------------------------------------------- #
# G4 — the featured glow, and ONLY on featured rows
# --------------------------------------------------------------------------- #

def test_featured_glow_lands_only_on_featured_rows(prio_html):
    su = production_fixture()
    feat = {r["ticker"] for r in su["buy"] if r.get("featured")}
    assert feat, "fixture must contain at least one featured row"
    glowing = set(re.findall(r'<a class="pvcard pv-\w+ pv-featured" href="[^"]*" '
                             r'data-ticker="([^"]+)"', prio_html))
    assert glowing == feat, "glow cohort %r != featured cohort %r" % (glowing, feat)


def test_featured_rows_carry_the_star_chip_so_colour_is_never_the_only_carrier(prio_html):
    su = production_fixture()
    n_feat = sum(1 for r in su["buy"] if r.get("featured"))
    assert prio_html.count('<span class="pv-mk-i pv-mk-feat"') == n_feat
    assert '<span class="l-en">★ Featured</span><span class="l-zh">★ 精选</span>' in prio_html


def test_featured_rows_are_all_buy_verb_so_the_aura_never_sits_on_a_lighter_card(prio_html):
    verbs = set(re.findall(r'<a class="pvcard pv-(\w+) pv-featured"', prio_html))
    assert verbs <= {"buy"}, "featured aura found on non-buy card(s): %r" % verbs


# --------------------------------------------------------------------------- #
# G4 — filter chips
# --------------------------------------------------------------------------- #

def test_filter_bar_renders_one_chip_per_non_empty_bucket_with_true_counts(prio_html):
    su = production_fixture()
    counts = {sk: sum(1 for r in su["buy"] if r["stage"] == sk) for sk in _STAGE_ORDER}
    counts["ran"] += len(su["ran"])
    assert '<div class="pbf-bar" id="hk-stage-filter" role="group"' in prio_html
    bar = prio_html[prio_html.find('<div class="pbf-bar"'):]
    bar = bar[:bar.find("</div>")]
    assert '<button type="button" data-stagepick="all" aria-pressed="true">' in bar
    assert '<span class="pbf-n">%d</span>' % (len(su["buy"]) + len(su["ran"])) in bar
    for sk, n in counts.items():
        chip = '<button type="button" data-stagepick="%s" aria-pressed="false"' % sk
        if n:
            assert chip in bar, "missing filter chip for %r" % sk
            seg = bar[bar.find(chip):]
            assert '<span class="pbf-n">%d</span>' % n in seg[:seg.find("</button>")]
        else:
            assert chip not in bar, "empty bucket %r must render no chip" % sk


def test_filter_chip_counts_match_what_filtering_would_show(prio_html):
    """A chip whose number disagrees with the filtered result is a defect. The CSS
    filters on data-stage, so count the rendered data-stage carriers per bucket —
    cards plus the ran section, minus the headings (which also carry the attr)."""
    su = production_fixture()
    for sk in _STAGE_ORDER:
        chip = '<button type="button" data-stagepick="%s" aria-pressed="false"' % sk
        if chip not in prio_html:
            continue
        seg = prio_html[prio_html.find(chip):]
        claimed = int(re.search(r'<span class="pbf-n">(\d+)</span>',
                                seg[:seg.find("</button>")]).group(1))
        cards = len(re.findall(r'<a class="pvcard[^"]*"[^>]*data-stage="%s"' % sk, prio_html))
        extra = len(su["ran"]) if sk == "ran" else 0
        assert claimed == cards + extra, (
            "chip %r claims %d, board shows %d" % (sk, claimed, cards + extra))


def test_filter_bar_has_exactly_one_polite_live_region_and_its_script(prio_html):
    assert prio_html.count('<span class="pbf-live" id="hk-stage-status" aria-live="polite">') == 1
    assert "var bar = document.getElementById('hk-stage-filter');" in prio_html
    assert "box.setAttribute('data-stagef', btn.getAttribute('data-stagepick'));" in prio_html


# --------------------------------------------------------------------------- #
# G3 — the ran section
# --------------------------------------------------------------------------- #

def test_ran_section_renders_with_stage_attr_so_the_filter_reaches_it(prio_html):
    assert '<div class="pbr" data-stage="ran">' in prio_html
    assert '<span class="pbr-t"><span class="l-en">Recently fired</span>' in prio_html
    assert '<span class="pbr-n">3</span>' in prio_html


def test_ran_rows_count_sessions_never_ticks(prio_html):
    seg = _ran_block(prio_html)
    assert "fired 11 sessions ago" in seg
    assert "11个交易日前触发" in seg
    assert re.search(r"fired \d+d ago", seg) is None, "ran rows must not print day units"


def test_ran_approx_anchor_marks_the_figure_and_explains_itself(prio_html):
    seg = _ran_block(prio_html)
    assert "fired ≈9 sessions ago" in seg, "approx anchor must carry the ≈ glyph"
    assert "≈ means the exact date this signal fired was not recorded" in seg
    # the marker-anchored row must NOT be marked approximate
    row = _ran_row(seg, "3690.HK")
    assert "≈" not in row


def test_ran_row_with_no_measurable_move_prints_an_em_dash_not_a_zero(prio_html):
    row = _ran_row(_ran_block(prio_html), "1024.HK")
    assert '<span class="pbr-na"' in row, "null pct_since must render the em-dash slot"
    assert ">—</span>" in row
    assert "az-up" not in row and "az-dn" not in row
    assert "+0.0%" not in row


def test_ran_rows_with_a_confirmed_cohort_sort_first_and_carry_the_amber_line(prio_html):
    seg = _ran_block(prio_html)
    order = re.findall(r'<span class="pbr-tk">([^<]+)</span>', seg)
    assert order[0] == "3690.HK", "theme_confirmed rows must lead the ran list: %r" % order
    row = _ran_row(seg, "3690.HK")
    assert '<a class="pbr-r pbr-warm"' in row
    assert '<span class="pbr-wl">' in row
    assert "Leader group just confirmed" in row
    # exactly one warm row in this fixture — the emphasis must stay scarce
    assert seg.count('<a class="pbr-r pbr-warm"') == 1


def test_ran_section_carries_no_buy_family_language(prio_html):
    seg = _ran_block(prio_html)
    for word in ("Buy now", "buy now", "Buy zone", "Add here"):
        assert word not in seg, "ran lane must not use buy-family language (%r)" % word
    assert "the entry window has passed" in seg


def _ran_block(html: str) -> str:
    start = html.find('<div class="pbr" data-stage="ran">')
    assert start != -1, "ran section not rendered"
    end = html.find('<p class="pb-fn">', start)
    assert end != -1, "pb-fn end sentinel not found after the ran section"
    return html[start:end]


def _ran_row(block: str, ticker: str) -> str:
    idx = block.find('<span class="pbr-tk">%s</span>' % ticker)
    assert idx != -1, "ran row %r not found" % ticker
    start = block.rfind("<a class=", 0, idx)
    return block[start:block.find("</a>", idx) + 4]


# --------------------------------------------------------------------------- #
# G2 — the leaders strip
# --------------------------------------------------------------------------- #

def _leaders_block(html: str) -> str:
    start = html.find('<div class="topsetups leaders-strip">')
    assert start != -1, "leaders strip not rendered"
    end = html.find("</table></div>", start)
    assert end != -1, "leaders table end sentinel not found"
    return html[start:end]


def test_leaders_strip_states_its_rank_key_and_its_stance(prio_html):
    seg = _leaders_block(prio_html)
    assert "🏃 <span class=\"l-en\">Market leaders</span>" in seg
    assert "Strongest runners by 3-month momentum" in seg
    assert "watch, don’t chase" in seg
    assert "观察，勿追高" in seg


def test_leaders_alpha_column_says_it_is_only_a_tiebreak(prio_html):
    seg = _leaders_block(prio_html)
    assert "<span class=\"l-en\">α (tiebreak)</span>" in seg
    assert "It does NOT order this table" in seg


def test_leaders_rows_keep_the_engines_order(prio_html):
    seg = _leaders_block(prio_html)
    rendered = re.findall(r'<span class="ts-tk">([^<]+)</span>', seg)
    assert rendered == [r["ticker"] for r in production_fixture()["leaders"][:15]]


def test_every_leaders_column_carries_a_c_class_so_none_escapes_the_mobile_budget(prio_html):
    """The c-* classes ARE the mobile contract (≤680px hides the tertiary set); a th
    or td without one silently escapes that budget."""
    seg = _leaders_block(prio_html)
    head = seg[seg.find("<thead>"):seg.find("</thead>")]
    ths = re.findall(r"<th\b[^>]*>", head)
    assert len(ths) == 7, "expected 7 leader columns, got %d" % len(ths)
    for th in ths:
        assert re.search(r'class="[^"]*\bc-[a-z]+\b', th), "th without a c-* class: %s" % th
    body = seg[seg.find("<tbody>"):]
    first = body[:body.find("</tr>")]
    tds = re.findall(r"<td\b[^>]*>", first)
    assert len(tds) == len(ths), "row/column count mismatch: %d td vs %d th" % (len(tds), len(ths))
    for td in tds:
        assert re.search(r'class="[^"]*\bc-[a-z]+\b', td), "td without a c-* class: %s" % td


def test_leaders_cohort_column_appears_only_when_rows_carry_it(prio_html):
    assert '<th class="c-theme"' in _leaders_block(prio_html)
    su = production_fixture()
    su["leaders"] = [{k: v for k, v in r.items() if k != "theme"} for r in su["leaders"]]
    seg = _leaders_block(_render(su))
    assert '<th class="c-theme"' not in seg
    head = seg[seg.find("<thead>"):seg.find("</thead>")]
    assert len(re.findall(r"<th\b", head)) == 6


def test_leaders_entry_column_never_promises_an_entry(prio_html):
    seg = _leaders_block(prio_html)
    assert seg.count('<span class="ent-warn"><span class="l-en">wait for pullback</span>') >= 1
    assert '<span class="ent-good"><span class="l-en">pullback zone</span>' in seg
    assert "Buy now" not in seg


def test_cohort_chip_tells_the_truth_about_where_it_counts(prio_html):
    """HKRV-R5 fence: the hk_leadership read boosts the leaders table's order and
    earns nothing at all on the graded buy lane. Both statements must be on the
    surface, on the element each one is about."""
    seg = _leaders_block(prio_html)
    assert "Membership adds a small boost to where a name sits in THIS table" in seg
    assert "on the board above it earns nothing at all" in seg
    assert "membership earns the card no points and changes nothing in the ranking" in prio_html


# --------------------------------------------------------------------------- #
# G1 — the seven witnesses are visible
# --------------------------------------------------------------------------- #

def test_all_seven_witnesses_appear_somewhere_on_the_board(prio_html):
    missing = [tk for tk in WITNESS_TICKERS if tk not in prio_html]
    assert not missing, "witnesses absent from the rebuilt board: %r" % missing


def test_at_least_five_witnesses_carry_a_stance_bearing_row(prio_html):
    """G1's fixture gate. A stance-bearing row is a staged card (its verb chip is
    the stance), a ran row (stance: the window has passed) or a leaders row
    (stance: watch — don't chase)."""
    carded = set(re.findall(r'data-ticker="([^"]+)"[^>]*data-stage="', prio_html))
    ran = set(re.findall(r'<span class="pbr-tk">([^<]+)</span>', prio_html))
    leaders = set(re.findall(r'<span class="ts-tk">([^<]+)</span>', prio_html))
    seen = {tk for tk in WITNESS_TICKERS if tk in (carded | ran | leaders)}
    assert len(seen) >= 5, "only %d of 7 witnesses carry a stance: %r" % (len(seen), seen)


def test_a_card_never_contradicts_the_bucket_it_sits_in(prio_html):
    """The bucket outranks the verb. HK's 200-day veto stamps a blocking marker while
    the entry gauge may still read `partial`, which would print a solid green BUY
    chip under a heading that says "stand aside". No buy-family verb is reachable in
    the ran or blocked buckets."""
    su = production_fixture()
    shut = {r["ticker"] for r in su["buy"] if r["stage"] in ("ran", "blocked")}
    assert shut, "fixture must contain ran/blocked rows"
    for tk in shut:
        m = re.search(r'<a class="pvcard pv-(\w+)[^"]*" href="[^"]*" data-ticker="%s"'
                      % re.escape(tk), prio_html)
        assert m, "card %r not rendered" % tk
        assert m.group(1) not in ("buy", "near"), (
            "%s sits in a shut bucket but carries a %r verb" % (tk, m.group(1)))


def test_a_buy_status_row_in_a_shut_bucket_is_demoted_not_hidden(prio_html):
    """The demotion must not cost the row its place: it stays carded, in its bucket,
    with the reason on the ⚠ mark."""
    su = production_fixture()
    blocked_buy = [r for r in su["buy"] if r["stage"] == "blocked"
                   and (r.get("entry_signal") or {}).get("status") in ("buy_now", "partial")]
    for r in blocked_buy:
        assert 'data-ticker="%s" data-stage="blocked"' % r["ticker"] in prio_html


def test_the_glow_can_never_land_outside_the_live_bucket(prio_html):
    su = production_fixture()
    su["buy"] = [dict(r, featured=True) for r in su["buy"]]   # engine gate gone rogue
    html = _render(su)
    lit = set(re.findall(r'<a class="pvcard \w+ pv-featured"[^>]*data-stage="(\w+)"', html))
    lit |= set(re.findall(r'<a class="pvcard pv-\w+ pv-featured" href="[^"]*" '
                          r'data-ticker="[^"]*" data-stage="(\w+)"', html))
    assert lit <= {"live"}, "featured aura escaped the live bucket: %r" % lit


def test_blocked_witnesses_name_the_check_that_is_holding_them_out(prio_html):
    """G6 display-tier relief: a blocked name is visible AND its reason is nameable
    in plain words, on Tier 2 where mechanics belong."""
    assert "Price has not reclaimed its 200-day line and held there" in prio_html
    assert "价格尚未重新站上200日均线并守住" in prio_html
    assert "still under its 200-day line" in prio_html
    assert "failed reclaim-and-hold</span>" not in prio_html, (
        "the engine's raw reason string must not reach the glance tier verbatim")


# --------------------------------------------------------------------------- #
# G4 — the Priority slot and the formula footnote
# --------------------------------------------------------------------------- #

def test_priority_replaces_edge_in_the_card_slot_when_the_row_scores(prio_html):
    assert '<span class="pv-edl"><span class="l-en">Priority</span>' \
           '<span class="l-zh">优先级</span></span>' in prio_html
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' not in prio_html
    top = production_fixture()["buy"][0]
    assert '<span class="pv-edn">%d</span>' % round(top["prophet"]["score"]) in prio_html


def test_footnote_states_the_weights_read_from_the_artifact(prio_html):
    assert '<p class="pb-fn">' in prio_html
    assert "Priority = signal 30% + entry 25% + edge 25% + runway 10% + setup quality 10%." in prio_html
    assert "优先级＝信号30%＋入场25%＋优势25%＋上行空间10%＋形态质量10%。" in prio_html
    assert "it is not a win probability" in prio_html
    assert "The hk_prophet_v1 forward record is accruing separately." in prio_html


def test_footnote_follows_the_artifact_when_the_engine_changes_a_weight(prio_html):
    """The weights are READ, never hard-coded — a template that prints last quarter's
    constants beside this quarter's score is printing a wrong number."""
    su = production_fixture()
    su["ranking"]["weights"] = {"signal": 0.40, "entry": 0.20, "edge": 0.20,
                                "runway": 0.10, "quality": 0.10}
    html = _render(su)
    assert "Priority = signal 40% + entry 20% + edge 20% + runway 10% + setup quality 10%." in html
    assert "signal 30% + entry 25%" not in html


def test_dark_leg_is_disclosed_in_plain_words_wherever_the_weight_appears(prio_html):
    n = len(production_fixture()["buy"])
    assert "runway currently contributes 0 for all %d names" % n in prio_html
    assert "上行空间目前对全部 %d 只股票都记 0 分" % n in prio_html
    assert prio_html.count("currently contributes 0 for all") >= 2, (
        "the disclosure must ride with the weights on both the footnote and the card tip")


def test_no_dark_leg_note_when_the_artifact_reports_no_coverage(prio_html):
    """Silent, not fail-closed: HK has never measured leg coverage, and asserting an
    unmeasured null would be the same overclaim pointing the other way."""
    su = production_fixture()
    su["ranking"].pop("component_coverage")
    html = _render(su)
    assert "currently contributes 0" not in html
    assert "都记 0 分" not in html


def test_new_chip_honours_the_engine_flag_over_the_fallback(prio_html):
    assert '<span class="l-en">New</span><span class="l-zh">新</span>' in prio_html
    su = production_fixture()
    for r in su["buy"]:
        r["new"] = False
        r["days_since_signal"] = 0          # would trip the ≤2-session fallback
    html = _render(su)
    assert '<span class="pv-mk-i pv-mk-new"' not in html, (
        "an engine-supplied new=False must not be overridden by the fallback")


# --------------------------------------------------------------------------- #
# G9 — fail-soft: the committed artifact still renders the flat board
# --------------------------------------------------------------------------- #

_NEW_MARKUP = [
    '<div class="nb-stage-hd',
    '<div class="pbf-bar"',
    '<span class="pbf-live"',
    '<div class="pbr" data-stage="ran">',
    '<p class="pb-fn">',
    '<div class="topsetups leaders-strip">',
    '<div class="pv-mk">',
    "getElementById('hk-stage-filter')",
]


def test_committed_artifact_carries_none_of_the_v1_contract():
    """If this ever fails the fixture has drifted and the fail-soft tests below have
    quietly stopped testing fail-soft."""
    art = committed_artifact()
    assert art.get("ran") is None and art.get("leaders") is None
    assert art.get("ranking") is None
    assert not any(r.get("stage") for r in art.get("buy") or [])


def test_legacy_artifact_renders_the_flat_board_with_no_priority_markup(legacy_html):
    for frag in _NEW_MARKUP:
        assert frag not in legacy_html, "priority markup leaked onto the legacy board: %r" % frag
    # `data-stage=` also appears in the filter CSS (which ships on every render), so
    # the absence test is anchored to a real TAG, never to the bare attribute name.
    stray = re.search(r'<[a-zA-Z][a-zA-Z0-9-]*[^>]*\sdata-stage="', legacy_html)
    assert stray is None, "legacy element carries data-stage: %r" % (stray and stray.group(0))
    assert legacy_html.count('<a class="pvcard') == len(committed_artifact()["buy"])


def test_legacy_board_keeps_its_own_copy_and_the_edge_slot(legacy_html):
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' in legacy_html
    assert "Priority</span>" not in legacy_html
    assert "Only names with a fresh entry signal make this board." in legacy_html
    assert "Bottoming names, ranked by flow, value and strength" in legacy_html
    assert "Ranked by readiness" not in legacy_html


def test_legacy_board_keeps_the_artifacts_own_card_order(legacy_html):
    order = re.findall(r'<a class="pvcard[^"]*" href="hk_lookup\.html#([^"]+)"', legacy_html)
    assert order == [r["ticker"] for r in committed_artifact()["buy"]]


def test_health_banner_survives_the_rebuild(legacy_html, prio_html):
    """The ledger-write failure is load-bearing until the engine lane heals it — it
    must be on the surface on BOTH paths."""
    for html in (legacy_html, prio_html):
        assert '<p class="note st-health"' in html
        assert "Some inputs didn't update this render" in html
        assert "部分数据本次未更新" in html


def test_legacy_render_is_tag_stream_identical_to_the_base_branch():
    """The strongest form of the fail-soft proof: render the COMMITTED artifact
    through this template and through the base branch's, and compare the element
    streams.  Skipped (never failed) when the base ref is unreachable — a shallow or
    sparse CI checkout has no business reddening main — because every observable half
    of the same contract is pinned unconditionally by the tests above."""
    base = None
    for ref in ("origin/main", "main"):
        try:
            base = subprocess.run(["git", "show", "%s:templates/hk.html.j2" % ref],
                                  cwd=ROOT, capture_output=True, text=True,
                                  check=True, timeout=30).stdout
            break
        except Exception:
            continue
    if not base:
        pytest.skip("base ref templates/hk.html.j2 unavailable in this checkout")
    art = committed_artifact()
    mine, theirs = _tags(_render(art)), _tags(_render_source(base, art))
    assert mine == theirs, "legacy render changed shape vs the base branch (%d vs %d tags)" % (
        len(mine), len(theirs))


# --------------------------------------------------------------------------- #
# House invariants
# --------------------------------------------------------------------------- #

def test_no_cjk_in_title_attributes(prio_html):
    for value in re.findall(r'\stitle="([^"]*)"', prio_html):
        assert not re.search(r"[一-鿿]", value), (
            "translated text in a title= attribute (CI-guarded): %r" % value)


def test_no_validated_claim_in_the_new_surface(prio_html):
    """`check_validated_claims.py` guards the word house-wide; this pins the blocks
    this PR authored so a later edit cannot smuggle it back in."""
    for block in (_ran_block(prio_html), _leaders_block(prio_html)):
        assert "validated" not in block.lower()


def test_both_languages_are_present_on_every_new_block(prio_html):
    for block in (_ran_block(prio_html), _leaders_block(prio_html)):
        assert 'class="l-en"' in block and 'class="l-zh"' in block


def test_no_raw_stage_slug_reaches_the_glance_tier(prio_html):
    """`setting_up` may live in data-stage / data-stagepick attributes; it must never
    be the words a reader sees."""
    for text in re.findall(r'<span class="(?:sh-l|sh-s)">(.*?)</span></?', prio_html):
        assert "setting_up" not in text and "hk_prophet_v1" not in text
    assert ">setting_up<" not in prio_html


def test_macro_mode_page_is_untouched_by_the_rebuild():
    html = _render(production_fixture(), mode="macro")
    assert '<div class="pbf-bar"' not in html
    assert '<div class="topsetups leaders-strip">' not in html
