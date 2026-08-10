"""Every surface that links a ticker dossier must link one that actually ships.

Which `site/stocks/<TICKER>.html` pages exist is decided nightly by DATA:
build_ticker_pages walks membership.parquet, then drops any ticker with no
stockdata blob, a `limited` profile, or fewer than three substantive sections.
2,842 tickers are membership-active; 1,666 get a page.

Three surfaces link tickers from WIDER sources and so could each name a symbol
that never got one — peer cards from factordata/factors.json, the movers board
from the heatmap, the crypto rails shelf from baskets/membership.json. They did:
47 targets carrying 211 dead links — 197 peer cards over 35 symbols (CACC and
NTST from 9 each), 12 movers rows/chips, 2 crypto tiles — every one a live 404
on a shipping page.

The fix is a filter, not a wider universe: each emitter asks lib.pages.
rendered_ticker_pages() whether a page ships and drops the ANCHOR — never the
row — when it does not. These tests pin each emitter's half of that contract
plus the site-wide result.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.pages import rendered_ticker_pages  # noqa: E402

_TEMPLATES = _REPO / "templates"
_SITE = _REPO / "site"


# ── lib.pages.rendered_ticker_pages ──────────────────────────────────────────

def _git_repo(tmp_path: Path, tickers: tuple[str, ...]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    stocks = tmp_path / "site" / "stocks"
    stocks.mkdir(parents=True)
    for t in tickers:
        (stocks / f"{t}.html").write_text("<html></html>", encoding="utf-8")
    (stocks / "index.html").write_text("<html></html>", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path / "site"


def test_rendered_ticker_pages_reads_disk(tmp_path):
    stocks = tmp_path / "site" / "stocks"
    stocks.mkdir(parents=True)
    for t in ("AAA", "BBB"):
        (stocks / f"{t}.html").write_text("x", encoding="utf-8")
    assert rendered_ticker_pages(tmp_path / "site") == frozenset({"AAA", "BBB"})


def test_rendered_ticker_pages_excludes_the_index(tmp_path):
    """stocks/index.html is the directory listing, not a ticker."""
    stocks = tmp_path / "site" / "stocks"
    stocks.mkdir(parents=True)
    (stocks / "index.html").write_text("x", encoding="utf-8")
    (stocks / "AAA.html").write_text("x", encoding="utf-8")
    assert rendered_ticker_pages(tmp_path / "site") == frozenset({"AAA"})


def test_rendered_ticker_pages_survives_a_partial_checkout(tmp_path):
    """A checkout missing site/stocks/ must NOT read as 'nothing ships'.

    Deciding the filter from visible pages alone is only sound when the tree
    holds everything that ships. A sparse cone or interrupted sync would
    otherwise silently un-link every peer/movers/crypto symbol site-wide — the
    #3988/#4042 shape pointed the other way. The committed baseline covers it.
    """
    site = _git_repo(tmp_path, ("AAA", "BBB"))
    assert rendered_ticker_pages(site) == frozenset({"AAA", "BBB"})

    import shutil
    shutil.rmtree(site / "stocks")
    assert rendered_ticker_pages(site) == frozenset({"AAA", "BBB"})


def test_rendered_ticker_pages_absent_tree_is_empty_not_an_error(tmp_path):
    """No pages and no git baseline: nothing ships, and nothing raises.

    An ABSENT baseline is not an unreadable one — it must degrade to the
    on-disk answer rather than blowing up a render.
    """
    assert rendered_ticker_pages(tmp_path / "nope") == frozenset()


# ── peer cards (scripts/build_ticker_pages) ──────────────────────────────────

def _factors(*tickers: str) -> dict:
    return {
        t: {"ticker": t, "name": f"{t} Corp", "sector": "Technology",
            "mktcap_bn": 10.0 + i}
        for i, t in enumerate(tickers)
    }


def test_peer_without_a_page_loses_its_href_not_its_card():
    from scripts.build_ticker_pages import _build_peers

    peers = _build_peers(
        "AAA", "Technology", _factors("AAA", "LIVE", "DEAD"), {}, None,
        self_cap_hint=10.0, linkable=frozenset({"AAA", "LIVE"}),
    )
    by_ticker = {p["ticker"]: p for p in peers}
    # The card survives — it is a real same-sector name with a real market cap.
    assert set(by_ticker) == {"LIVE", "DEAD"}
    assert by_ticker["LIVE"]["href"] == "/stocks/LIVE.html"
    assert by_ticker["DEAD"]["href"] is None
    assert by_ticker["DEAD"]["mktcap"]


def test_peer_linkable_none_links_everything():
    """The pre-filter behaviour, for callers with no site tree to consult."""
    from scripts.build_ticker_pages import _build_peers

    peers = _build_peers(
        "AAA", "Technology", _factors("AAA", "LIVE", "DEAD"), {}, None,
        self_cap_hint=10.0, linkable=None,
    )
    assert all(p["href"] for p in peers)


# ── basket pages (the same defect one level up) ──────────────────────────────
# A ticker page links basket/<slug>.html for every membership row it holds, but
# a basket page is only BUILT once 3+ of its members carry price history
# (engine/baskets.py:206). Membership is curated by hand, so a new sleeve is
# linkable-looking and unbuilt for at least a night. silver_miners was curated
# 2026-08-05 with 10 members and 404'd from stocks/HL.html and stocks/SSRM.html
# — which failed check_site_asset_refs on EVERY render from 03:24Z on
# 2026-08-06 and wedged the whole render lane: no page body was rebuilt for
# ~28h, so merged UI work sat in templates/ and never reached the VPS.

def _basket_repo(tmp_path: Path, ids: tuple[str, ...]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    bdir = tmp_path / "site" / "basket"
    bdir.mkdir(parents=True)
    for b in ids:
        (bdir / f"{b}.html").write_text("<html></html>", encoding="utf-8")
    (bdir / "index.html").write_text("<html></html>", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path / "site"


def test_rendered_basket_pages_reads_disk_and_drops_the_index(tmp_path):
    from lib.pages import rendered_basket_pages

    site = _basket_repo(tmp_path, ("gold_miners", "mag7"))
    got = rendered_basket_pages(site)
    assert got == frozenset({"gold_miners", "mag7"})
    assert "index" not in got


def test_rendered_basket_pages_survives_a_partial_checkout(tmp_path):
    """A scoped render must not un-link every basket it merely did not fetch."""
    from lib.pages import rendered_basket_pages

    site = _basket_repo(tmp_path, ("gold_miners", "mag7"))
    (site / "basket" / "mag7.html").unlink()          # committed but not on disk
    assert rendered_basket_pages(site) == frozenset({"gold_miners", "mag7"})


def test_rendered_basket_pages_absent_tree_is_empty_not_an_error(tmp_path):
    from lib.pages import rendered_basket_pages

    assert rendered_basket_pages(tmp_path / "nope") == frozenset()


def test_a_basket_without_a_page_keeps_its_row_and_loses_its_link():
    from scripts.build_ticker_pages import _build_themes

    blob = {"baskets_membership": [
        {"slug": "gold_miners", "name": "Gold Miners", "name_zh": "黄金矿业",
         "theme": "Gold producer sleeve."},
        {"slug": "silver_miners", "name": "Silver Miners", "name_zh": "白银矿业",
         "theme": "Silver producer sleeve."},
    ]}
    rows = _build_themes(blob, [], {}, frozenset({"gold_miners"}))["baskets"]
    by_id = {r["id"]: r for r in rows}

    assert set(by_id) == {"gold_miners", "silver_miners"}, "the ROW always survives"
    assert by_id["gold_miners"]["linked"] is True
    assert by_id["silver_miners"]["linked"] is False
    # the substance is still there to read, unlinked
    assert by_id["silver_miners"]["name_en"] == "Silver Miners"
    assert by_id["silver_miners"]["theme"] == "Silver producer sleeve."


def test_a_basket_row_from_member_context_is_gated_too():
    """The second row source. Gating only the membership branch would leave the
    dead link reachable through member_context, which is how a half-swept fix
    ships looking complete."""
    from scripts.build_ticker_pages import _build_themes

    rows = _build_themes(
        None,
        [{"basket_id": "silver_miners", "basket": "Silver Miners",
          "band_en": "mid", "band_zh": "中"}],
        {}, frozenset({"gold_miners"}),
    )["baskets"]
    assert [r["id"] for r in rows] == ["silver_miners"]
    assert rows[0]["linked"] is False


def test_basket_linkable_none_links_everything():
    """The pre-filter behaviour, for callers with no site tree to consult."""
    from scripts.build_ticker_pages import _build_themes

    blob = {"baskets_membership": [{"slug": "anything", "name": "Any"}]}
    rows = _build_themes(blob, [], {}, None)["baskets"]
    assert rows[0]["linked"] is True


def test_basket_row_template_emits_no_anchor_when_unlinked():
    frag = _slice(_TEMPLATES / "ticker.html.j2",
                  '<div class="throw">', "</div>")
    out = _render(frag, b={"id": "silver_miners", "name_en": "Silver Miners",
                           "name_zh": "白银矿业", "theme": "Silver producer sleeve.",
                           "rationale": "", "band_en": "", "linked": False})
    assert "<a " not in out and "href=" not in out
    assert "Silver Miners" in out and "Silver producer sleeve." in out

    linked = _render(frag, b={"id": "gold_miners", "name_en": "Gold Miners",
                              "name_zh": "黄金矿业", "theme": "Gold sleeve.",
                              "rationale": "", "band_en": "", "linked": True})
    assert 'href="../basket/gold_miners.html"' in linked


# ── consolidated stocks-hub theme board ─────────────────────────────────────

def _theme_movers_data() -> dict:
    return {
        "themes_asof": "2026-08-07",
        "theme_tiles": [{
            "sector": "Software",
            "asof": "2026-08-07",
            "members": [
                {"t": "LIVE", "perf": {"1D": 8.0}, "asof": "2026-08-07"},
                {"t": "ALSO_LIVE", "perf": {"1D": 6.0}, "asof": "2026-08-07"},
                {"t": "DEAD", "perf": {"1D": 5.0}, "asof": "2026-08-07"},
                {"t": "ALSO_DEAD", "perf": {"1D": 4.0}, "asof": "2026-08-07"},
            ],
        }],
    }


def test_consolidated_theme_board_excludes_every_missing_dossier():
    from engine.stocks_hub import theme_ribbons

    rows = theme_ribbons(
        _theme_movers_data(), linkable=frozenset({"LIVE", "ALSO_LIVE"})
    )
    assert [m["t"] for m in rows[0]["members"]] == ["LIVE", "ALSO_LIVE"]
    assert "DEAD" not in str(rows), "a theme member with no dossier must not be linked"


# ── templates emit no anchor when the page is absent ─────────────────────────

def _render(source: str, **ctx) -> str:
    from jinja2 import Environment

    env = Environment(autoescape=True)
    env.globals.update(
        t=lambda a, b=None: a, tr=lambda a, b=None: a, td=lambda a, b=None: a,
        pct=lambda v: f"{v:+.2f}%", tone=lambda x: f"tone-{x}", zip=zip,
    )
    return env.from_string(source).render(**ctx)


def _slice(path: Path, start: str, end: str) -> str:
    """Lines [start .. end] of a template, both located by substring."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    i = next((n for n, ln in enumerate(lines) if start in ln), None)
    j = next((n for n, ln in enumerate(lines) if end in ln and n >= (i or 0)), None)
    assert i is not None and j is not None, f"markers not found in {path.name}: {start!r} / {end!r}"
    return "".join(lines[i:j + 1])


def test_peer_card_template_emits_a_flat_card_not_a_link():
    frag = _slice(_TEMPLATES / "ticker.html.j2",
                  '{% if p.href %}<a class="pcard"', "{% if p.href %}</a>")
    out = _render(frag, p={"ticker": "DEAD", "name": "Dead Corp",
                           "href": None, "mktcap": "$5B"})
    assert "<a " not in out and "href=" not in out
    assert 'class="pcard pcard-off"' in out
    assert "DEAD" in out and "$5B" in out          # the information survives


def test_crypto_equity_tile_template_emits_no_anchor():
    frag = _slice(_TEMPLATES / "crypto.html.j2",
                  '<div class="equity-grid">', '<div class="equity-grid">')
    out = _render(frag, equities=[
        {"ticker": "DEAD", "price": "$1.00", "change": "-1.0%", "state": "Range",
         "state_zh": "震荡", "tone": "neutral", "href": None},
    ])
    assert "<a " not in out and "href=" not in out
    assert "equity-off" in out and "DEAD" in out


# ── the shipped tree ─────────────────────────────────────────────────────────

def test_no_shipped_page_links_a_ticker_page_that_does_not_exist():
    """The invariant the three filters above exist to hold.

    scripts/check_site_asset_refs.py enforces this in the render lanes across
    every reference class; this is the repo-side backstop for the ticker class
    specifically, so a regression fails in the pack that owns these builders.
    """
    import re

    if not _SITE.is_dir():
        pytest.skip("site/ not present in this checkout")
    n_pages = len(list((_SITE / "stocks").glob("*.html"))) if (_SITE / "stocks").is_dir() else 0
    if n_pages < 100:
        # Never assert vacuously: a checkout without the ticker pages proves
        # nothing, so say so with the count instead of passing green.
        pytest.skip(f"partial checkout — only {n_pages} ticker page(s) present")

    rx = re.compile(
        r"""(?<![\w-])(?:href|src)\s*=\s*["']([^"']*stocks/[A-Za-z0-9.\-]+\.html)["']"""
    )
    dead: dict[str, list[str]] = {}
    n_refs = 0
    for page in _SITE.rglob("*.html"):
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for ref in rx.findall(text):
            if ref.startswith(("http://", "https://", "//")):
                continue
            n_refs += 1
            target = (_SITE / ref.lstrip("/")) if ref.startswith("/") else (page.parent / ref)
            if not target.exists():
                dead.setdefault(target.name, []).append(page.name)

    assert n_refs > 1000, f"only {n_refs} ticker refs scanned — scan is not covering site/"
    assert not dead, (
        f"{len(dead)} ticker page(s) linked but never rendered, "
        f"across {sum(len(v) for v in dead.values())} link(s): "
        + ", ".join(f"{k} (from {v[0]}{', +%d more' % (len(v) - 1) if len(v) > 1 else ''})"
                    for k, v in sorted(dead.items())[:10])
    )


def test_no_shipped_page_links_a_basket_page_that_does_not_exist():
    """The basket-class half of the same invariant.

    This is the one that actually fired: `silver_miners` was curated into
    membership.json on 2026-08-05, linked from two shipping stock pages, and
    never built — engine/baskets.py skips a basket with fewer than 3 members in
    the returns cache, and a day-old sleeve has none. check_site_asset_refs
    caught it in the render lane, which is the right place to catch it and the
    worst place to be blocked by it: the render aborts before committing, so
    every page body on the site froze for ~28h while the failure looked like a
    basket problem rather than a site-wide publish outage.
    """
    import re

    if not _SITE.is_dir():
        pytest.skip("site/ not present in this checkout")
    n_pages = len(list((_SITE / "basket").glob("*.html"))) if (_SITE / "basket").is_dir() else 0
    if n_pages < 20:
        pytest.skip(f"partial checkout — only {n_pages} basket page(s) present")

    rx = re.compile(
        r"""(?<![\w-])(?:href|src)\s*=\s*["']([^"']*basket/[A-Za-z0-9._\-]+\.html)["']"""
    )
    dead: dict[str, list[str]] = {}
    n_refs = 0
    for page in _SITE.rglob("*.html"):
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for ref in rx.findall(text):
            if ref.startswith(("http://", "https://", "//")):
                continue
            n_refs += 1
            target = (_SITE / ref.lstrip("/")) if ref.startswith("/") else (page.parent / ref)
            if not target.exists():
                dead.setdefault(target.name, []).append(page.name)

    assert n_refs > 100, f"only {n_refs} basket refs scanned — scan is not covering site/"
    assert not dead, (
        f"{len(dead)} basket page(s) linked but never built, "
        f"across {sum(len(v) for v in dead.values())} link(s): "
        + ", ".join(f"{k} (from {v[0]}{', +%d more' % (len(v) - 1) if len(v) > 1 else ''})"
                    for k, v in sorted(dead.items())[:10])
    )
