"""Acquisition-truth guards for the anonymous landing page.

The landing page is an ACQUISITION surface: every number and freshness label on
it is a claim a stranger has no way to audit. Operation
market-os-acquisition-truth-bridge-20260903: three claim surfaces drifted from
(or were never bound to) the committed canonical artifacts they describe —

  * the one-line ``<script type="application/json" id="ph-data">`` island said
    "board of 2026-07-06, 11 cards" while site/prophet/showcase.json (the
    nightly emit it claims to be) said 2026-08-14, 12 cards;
  * the coverage claim said "2,700+" against 1,955 published dossiers
    (site/stocks/index.html, the estate we actually ship);
  * scripted demo tiles wore TODAY / live labels and Math.random() motion —
    fake liveness on hand-frozen numbers.

These tests bind each surface to its artifact. templates/index.html and
site/index.html are a byte-identical plain-copy pair (ui.template_site_sync),
so every assertion runs against BOTH copies. scripts/bake_landing_preview.py is
the deterministic adapter that keeps the derived regions true (--check reds CI,
--fix rewrites both copies); these tests are the law it answers to.

showcase.json's ``as_of`` is SNAPSHOT IDENTITY, never site freshness — the
teaser is a deliberately DELAYED artifact (scripts/freshness_sentinel.py). The
guard here is therefore equality-with-the-artifact plus an explicit staleness
note once the snapshot outlives its 14-day policy + 7-day grace, not a
freshness SLA.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = (ROOT / "templates" / "index.html", ROOT / "site" / "index.html")
SHOWCASE_PATH = ROOT / "site" / "prophet" / "showcase.json"
STOCKS_INDEX_PATH = ROOT / "site" / "stocks" / "index.html"

ISLAND_RE = re.compile(
    r'<script type="application/json" id="ph-data">(.*?)</script>', re.S)
# The stocks-index strapline is the canonical published-dossier denominator
# ("Every one of the <b>N</b> US names we publish a dossier for…").
STOCKS_TOTAL_RE = re.compile(r"Every one of the <b>([\d,]+)</b>")
# The pricing-table coverage row: feature label + its tipbox claim.
DOSSIER_TIP_RE = re.compile(
    r'<span class="ft" data-zh="个股档案">Stock dossiers</span>'
    r'<span class="tipbox" data-zh="([^"]*)">([^<]*)</span>')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _island(text: str) -> dict:
    m = ISLAND_RE.search(text)
    assert m, "landing page must carry the #ph-data island"
    return json.loads(m.group(1))


def _island_raw(text: str) -> str:
    m = ISLAND_RE.search(text)
    assert m, "landing page must carry the #ph-data island"
    return m.group(1)


def _showcase() -> dict:
    assert SHOWCASE_PATH.is_file(), "canonical artifact site/prophet/showcase.json missing"
    return json.loads(_read(SHOWCASE_PATH))


def _published_dossier_total() -> int:
    text = _read(STOCKS_INDEX_PATH)
    m = STOCKS_TOTAL_RE.search(text)
    assert m, "site/stocks/index.html must carry its 'Every one of the <b>N</b>' total"
    return int(m.group(1).replace(",", ""))


def _pyramid_kicker(text: str, card_class: str) -> str:
    """The <p class="kicker …"> line of one hero pyramid card (pp1/pp2/…)."""
    start = text.index(f'<div class="pcard {card_class}"')
    kick = text.index('<p class="kicker', start)
    end = text.index("</p>", kick)
    return text[kick:end + len("</p>")]


def _prophet_section(text: str) -> str:
    start = text.index('<section class="psec" id="f-prophet">')
    end = text.index("</section>", start)
    return text[start:end]


# ── 1. the baked island IS the canonical artifact ───────────────────────────

@pytest.mark.parametrize("path", HTML_PATHS)
def test_baked_showcase_island_matches_canonical_artifact(path: Path):
    """#ph-data must be showcase.json — same as_of, same count, same tickers.

    RED at introduction: the island carried the board of 2026-07-06 with 11
    cards while showcase.json carried 2026-08-14 with 12.
    """
    island = _island(_read(path))
    showcase = _showcase()
    assert island["as_of"] == showcase["as_of"], (
        f"{path.name}: island as_of {island['as_of']!r} != "
        f"showcase.json as_of {showcase['as_of']!r} — the baked teaser has "
        "drifted from the artifact it claims to be "
        "(run: python -m scripts.bake_landing_preview --fix)")
    assert island["count"] == showcase["count"]
    island_tks = {c["tk"] for c in island["cards"]}
    showcase_tks = {c["tk"] for c in showcase["cards"]}
    assert island_tks == showcase_tks, (
        f"{path.name}: island cards {sorted(island_tks)} != "
        f"showcase cards {sorted(showcase_tks)}")


@pytest.mark.parametrize("path", HTML_PATHS)
def test_island_is_the_canonical_serialization(path: Path):
    """ONE canonical serialization: json.dumps of the artifact object itself,
    compact separators, unescaped UTF-8 (the surrounding island idiom). Byte
    equality is what makes the bake idempotent and the drift check exact."""
    expected = json.dumps(_showcase(), ensure_ascii=False, separators=(",", ":"))
    assert _island_raw(_read(path)) == expected, (
        f"{path.name}: #ph-data is not the canonical serialization of "
        "site/prophet/showcase.json (run: python -m scripts.bake_landing_preview --fix)")


# ── 2. the coverage count is derived and denominated ────────────────────────

@pytest.mark.parametrize("path", HTML_PATHS)
def test_coverage_count_is_derived_and_denominated(path: Path):
    """The dossier-coverage claim must equal the stocks-index total and must
    name its denominator (published dossiers), EN and zh alike.

    RED at introduction: the tipbox said "2,700+ names" against 1,955
    published dossiers.
    """
    text = _read(path)
    total = _published_dossier_total()
    m = DOSSIER_TIP_RE.search(text)
    assert m, f"{path.name}: dossier-coverage tipbox row missing or reshaped"
    zh_copy, en_copy = m.group(1), m.group(2)
    count_txt = f"{total:,}"
    assert count_txt in en_copy, (
        f"{path.name}: coverage claim must carry the derived total {count_txt} "
        f"(site/stocks/index.html), got: {en_copy!r}")
    assert "published dossier" in en_copy, (
        f"{path.name}: coverage claim must name its denominator "
        f"(published dossiers), got: {en_copy!r}")
    assert count_txt in zh_copy, (
        f"{path.name}: zh twin must carry the same derived total, got: {zh_copy!r}")
    assert "已发布" in zh_copy and "档案" in zh_copy, (
        f"{path.name}: zh twin must name the denominator, got: {zh_copy!r}")
    assert "2,700" not in en_copy and "2,700" not in zh_copy


# ── 3. no unbacked TODAY / LIVE labels on scripted demo tiles ───────────────

@pytest.mark.parametrize("path", HTML_PATHS)
def test_no_unbacked_live_today_labels(path: Path):
    """Hand-frozen demo tiles must wear the page's DEMO idiom, not TODAY/live.

    The hero pyramid's heatmap and Prophet sample cards are scripted set
    dressing (fixed numbers, no data source). The page already has an honest
    idiom for exactly this — TODAY'S READ · US <span class="asof">demo</span>
    and the SCRIPTED DEMO chip — so these two must carry it too.
    """
    text = _read(path)

    heat = _pyramid_kicker(text, "pp1")
    assert "TODAY" not in heat, f"{path.name}: heatmap kicker still claims TODAY: {heat!r}"
    assert "live" not in heat.lower(), (
        f"{path.name}: heatmap kicker still claims live: {heat!r}")
    assert "实时" not in heat and "今日" not in heat, (
        f"{path.name}: heatmap kicker zh twin still claims live/today: {heat!r}")
    assert 'class="asof"' in heat and "demo" in heat and "演示" in heat, (
        f"{path.name}: heatmap kicker must carry the DEMO idiom: {heat!r}")

    prophet = _pyramid_kicker(text, "pp2")
    assert "TODAY" not in prophet and "今日" not in prophet, (
        f"{path.name}: Prophet sample kicker still claims TODAY: {prophet!r}")
    assert "PROPHET · DEMO" in prophet and "Prophet · 演示" in prophet, (
        f"{path.name}: Prophet sample kicker must carry the DEMO idiom: {prophet!r}")
    assert ">free<" in prophet and 'data-zh="免费"' in prophet, (
        f"{path.name}: the FREE chip must survive the relabel: {prophet!r}")

    # The fake live-motion for those tiles goes with the label: no jitter loop.
    assert "heatRound" not in text and "bumpTile" not in text, (
        f"{path.name}: the heatmap Math.random jitter block must be gone — "
        "static baseline tiles + DEMO label are the honest shape")


# ── 4. the delayed snapshot's age is guarded ────────────────────────────────

@pytest.mark.parametrize("path", HTML_PATHS)
def test_delayed_snapshot_age_is_guarded(path: Path):
    """Beyond 14-day policy + 7-day grace the section must SAY it is stale.

    The render path computes the snapshot age from the island's as_of and
    reveals an explicit note pointing at the live board; without JavaScript a
    <noscript> note carries the honest fallback. A fetch failure must never
    blank the baked BOARD OF label.
    """
    text = _read(path)
    section = _prophet_section(text)

    # the note element: present, hidden by default, bilingual, links the board
    stale = re.search(r'<p[^>]*id="ph-stale"[^>]*>.*?</p>', section, re.S)
    assert stale, f"{path.name}: #ph-stale staleness note element missing"
    note = stale.group(0)
    assert "hidden" in note, f"{path.name}: staleness note must default hidden: {note!r}"
    assert "older than our 2-week delay" in note, note
    assert "us_stocks.html" in note, note
    assert 'data-zh="' in note and "两周" in note, (
        f"{path.name}: staleness note needs its zh twin: {note!r}")

    # the guard code: age from as_of, 21-day threshold (14 policy + 7 grace)
    assert "STALE_AFTER_DAYS=21" in text, (
        f"{path.name}: staleness guard constant missing from the render path")
    assert "getElementById('ph-stale')" in text
    assert "864e5" in text, f"{path.name}: guard must compute age in days from as_of"

    # fetch-failure honesty: the live override only swaps on a good payload
    # (baked as_of label survives any fetch failure), and the BOARD OF label
    # only renders with a parseable date — never a dangling 'BOARD OF '.
    assert "d.as_of!==data.as_of" in text
    assert "d.length>=10" in text

    # no-JS honesty: a <noscript> note inside the section
    ns = re.search(r"<noscript>.*?</noscript>", section, re.S)
    assert ns, f"{path.name}: the Prophet section needs a <noscript> honest note"
    assert "us_stocks.html" in ns.group(0)
    assert 'data-zh="' in ns.group(0), (
        f"{path.name}: <noscript> note needs its zh twin: {ns.group(0)!r}")


# ── 5. EN ⇄ zh semantic parity on every changed label ───────────────────────

@pytest.mark.parametrize("path", HTML_PATHS)
def test_en_zh_semantic_parity_on_changed_labels(path: Path):
    """Each label this change introduces must say the same thing in both
    languages — spot-asserted as exact pairs (the LANG applier swaps innerHTML
    against data-zh, so both halves live on the same element)."""
    text = _read(path)
    total = f"{_published_dossier_total():,}"

    # heatmap kicker: demo ⇄ 演示 on the same asof-span idiom
    heat = _pyramid_kicker(text, "pp1")
    assert '<span class="asof">demo</span>' in heat, heat
    assert "科技股" in heat and "<span class='asof'>演示</span>" in heat, heat

    # Prophet sample kicker: PROPHET · DEMO ⇄ Prophet · 演示, FREE ⇄ 免费
    prophet = _pyramid_kicker(text, "pp2")
    assert '<span data-zh="Prophet · 演示">PROPHET · DEMO</span>' in prophet, prophet
    assert '<span class="asof" data-zh="免费">free</span>' in prophet, prophet

    # coverage tipbox: same derived count in both halves
    m = DOSSIER_TIP_RE.search(text)
    assert m, f"{path.name}: dossier-coverage tipbox row missing"
    assert total in m.group(1) and total in m.group(2)

    # staleness note: same state (older than the delay window → live board)
    section = _prophet_section(text)
    stale = re.search(r'<p[^>]*id="ph-stale"[^>]*>.*?</p>', section, re.S)
    assert stale, f"{path.name}: #ph-stale staleness note element missing"
    note = stale.group(0)
    assert "older than our 2-week delay" in note and "两周" in note, note
    assert note.count("us_stocks.html") >= 2, (
        f"{path.name}: both language halves must link the live board: {note!r}")

    # noscript note: JS-off statement in both halves
    ns = re.search(r"<noscript>.*?</noscript>", section, re.S)
    assert ns, f"{path.name}: <noscript> note missing"
    assert "JavaScript is off" in ns.group(0) and "JavaScript 已关闭" in ns.group(0), (
        ns.group(0))
