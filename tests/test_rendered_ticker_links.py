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


# ── movers board (scripts/build_movers_page) ─────────────────────────────────

def _movers_data() -> dict:
    return {
        "sp500_tiles": [
            {"t": "LIVE", "name": "Live Corp", "sector": "Technology",
             "industry": "Software", "perf": {"1D": 6.0}},
            {"t": "DEAD", "name": "Dead Corp", "sector": "Technology",
             "industry": "Software", "perf": {"1D": 5.0}},
            {"t": "DOWN", "name": "Down Inc", "sector": "Financials",
             "industry": "Banks", "perf": {"1D": -7.0}},
        ],
        "theme_tiles": [],
        "asof": "2026-07-30",
    }


def test_movers_rows_carry_has_page():
    from scripts.build_movers_page import build_context

    ctx = build_context(_movers_data(), linkable=frozenset({"LIVE", "DOWN"}))
    flags = {r["ticker"]: r["has_page"]
             for r in ctx["gainers"] + ctx["losers"]}
    assert flags.get("LIVE") is True
    assert flags.get("DEAD") is False, "a mover with no dossier must not be linked"
    assert flags.get("DOWN") is True


def test_movers_linkable_none_links_everything():
    from scripts.build_movers_page import build_context

    ctx = build_context(_movers_data())
    assert all(r["has_page"] for r in ctx["gainers"] + ctx["losers"])


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


def test_movers_row_and_chip_templates_emit_no_anchor():
    tpl = _TEMPLATES / "movers.html.j2"
    row = _slice(tpl, '{% if m.has_page %}<a class="mv"', "{% if m.has_page %}</a>")
    out = _render(row, m={"ticker": "DEAD", "name": "Dead Corp", "sector": "Tech",
                          "pct": -9.06, "has_page": False},
                  loop=type("L", (), {"index": 1})(), _gmax=10, _lmax=10)
    assert "<a " not in out and "href=" not in out
    assert 'class="mv mv-off"' in out and "DEAD" in out

    chip = _slice(tpl, '{% if mm.has_page %}<a class="mchip"', "{% if mm.has_page %}</a>")
    out = _render(chip, mm={"ticker": "DEAD", "pct": -13.62, "has_page": False})
    assert "<a " not in out and "href=" not in out
    assert 'class="mchip mchip-off"' in out and "DEAD" in out


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
