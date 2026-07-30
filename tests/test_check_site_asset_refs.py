"""Dead-reference guard — a shipped page must not link a file that isn't there.

The bug this was written for: templates/ticker.html.j2 emitted
`../baskets/<id>.html` while those pages ship under the SINGULAR
`site/basket/`, so every themes-and-baskets link on all 605 US ticker pages
404'd (909 links). Nothing else in CI noticed — the HTML was well-formed and
the render succeeded. Same silent shape as the pruned stylesheets in #3988 and
#4042.

The checker proves file EXISTENCE, not markup validity, so the discrimination
that matters is real-path vs. not-a-path: `data-src="macro"` and a
`<script>`-built `${SB}${sym}` must not read as links.

Run: .venv/bin/python -m pytest tests/test_check_site_asset_refs.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import check_site_asset_refs as mod  # noqa: E402
from scripts.check_site_asset_refs import (  # noqa: E402
    _KNOWN_GAPS,
    find_dangling,
    main,
)


def _site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "assets" / "css").mkdir(parents=True)
    (site / "basket").mkdir()
    (site / "stocks").mkdir()
    (site / "assets" / "css" / "abc123.css").write_text("a{}", encoding="utf-8")
    (site / "basket" / "ai_infra.html").write_text("<html></html>", encoding="utf-8")
    return site


def _page(site: Path, name: str, body: str) -> None:
    (site / name).write_text(f"<html><head></head><body>{body}</body></html>", encoding="utf-8")


def test_missing_hash_stylesheet_is_reported(tmp_path):
    site = _site(tmp_path)
    _page(site, "p.html", '<link rel="stylesheet" href="assets/css/deadbe.css?v=deadbe">')
    assert find_dangling(site) == {"assets/css/deadbe.css": ["p.html"]}


def test_present_stylesheet_with_version_stamp_is_clean(tmp_path):
    site = _site(tmp_path)
    _page(site, "p.html", '<link rel="stylesheet" href="assets/css/abc123.css?v=abc123">')
    assert find_dangling(site) == {}


def test_plural_directory_typo_is_caught(tmp_path):
    """The 605-page ticker bug: ../baskets/ vs the shipped ../basket/."""
    site = _site(tmp_path)
    (site / "stocks" / "AAPL.html").write_text(
        '<a href="../baskets/ai_infra.html">Themes</a>', encoding="utf-8")
    assert find_dangling(site) == {"baskets/ai_infra.html": ["stocks/AAPL.html"]}


def test_correct_singular_directory_is_clean(tmp_path):
    site = _site(tmp_path)
    (site / "stocks" / "AAPL.html").write_text(
        '<a href="../basket/ai_infra.html">Themes</a>', encoding="utf-8")
    assert find_dangling(site) == {}


def test_data_attributes_are_not_references(tmp_path):
    """`data-src=`/`data-href=` are payload, not links — a plain \\b matches the
    hyphen and would fail every alerts.html card (data-src="macro")."""
    site = _site(tmp_path)
    _page(site, "alerts.html",
          '<div data-src="macro" data-href="themes" data-cluster="regime"></div>')
    assert find_dangling(site) == {}


def test_script_template_literals_are_not_references(tmp_path):
    site = _site(tmp_path)
    _page(site, "p.html",
          '<script>el.innerHTML = `<a href="${SB}${sym}">x</a>'
          '<a href="../${esc(rm.dir)}/${esc(o.bid)}.html">y</a>`;</script>')
    assert find_dangling(site) == {}


def test_split_attribute_markup_is_not_reported_as_a_link(tmp_path):
    """An i18n macro can split `<a href="` across two language spans, leaving
    href="</span>". That is a markup defect, not a missing file — this checker
    must not claim a file named `</span>` is absent."""
    site = _site(tmp_path)
    _page(site, "cagr.html", '<a href="</span><span class="l-zh">x</a>')
    assert find_dangling(site) == {}


def test_external_and_scheme_refs_are_skipped(tmp_path):
    site = _site(tmp_path)
    _page(site, "p.html",
          '<a href="https://example.com/x.html">a</a>'
          '<a href="//cdn.example.com/y.css">b</a>'
          '<a href="mailto:x@y.z">c</a><a href="#top">d</a>'
          '<img src="data:image/gif;base64,R0lGOD">')
    assert find_dangling(site) == {}


def test_runtime_api_routes_are_not_files(tmp_path):
    """Caddy reverse-proxies /api/* to the app; it never hits the file tree."""
    site = _site(tmp_path)
    _page(site, "status.html", '<a href="/api/status">status</a><a href="/ws/tape">t</a>')
    assert find_dangling(site) == {}


def test_root_absolute_ref_resolves_from_site_root(tmp_path):
    site = _site(tmp_path)
    (site / "stocks" / "ABCB.html").write_text(
        '<a class="pcard" href="/stocks/NOPE.html">peer</a>', encoding="utf-8")
    assert find_dangling(site) == {"stocks/NOPE.html": ["stocks/ABCB.html"]}


def test_known_gaps_are_suppressed_but_new_breakage_is_not(tmp_path, monkeypatch):
    """The suppression mechanism, exercised against a SYNTHETIC pin.

    `_KNOWN_GAPS` is empty now that all six original pins got their emitter fix, so
    this must not read the live set for its fixture — an empty real list would make
    the assertion vacuous (or raise on `[0]`) exactly when the escape hatch is
    still load-bearing for whoever needs it next.
    """
    monkeypatch.setattr(mod, "_KNOWN_GAPS", frozenset({"legacy/pinned.html"}))
    site = _site(tmp_path)
    (site / "stocks" / "A.html").write_text(
        '<a href="/legacy/pinned.html">pinned</a><a href="/stocks/BRANDNEW.html">new</a>',
        encoding="utf-8")
    assert find_dangling(site) == {"stocks/BRANDNEW.html": ["stocks/A.html"]}


def test_pin_list_is_empty_so_the_set_stays_closed():
    """Every gap this guard shipped with has an emitter fix; nothing is pinned.

    Pinning is legitimate, so this is not a ban — it is the ratchet the docstring
    asks for. Re-pinning means editing this test, which puts the justification in
    front of a reviewer instead of letting a fresh 404 ride in silently.
    """
    assert _KNOWN_GAPS == frozenset(), sorted(_KNOWN_GAPS)


def test_every_pinned_gap_is_site_relative_and_unstamped():
    """A pin only suppresses if it matches the resolved site-relative path."""
    for gap in _KNOWN_GAPS:
        assert not gap.startswith("/"), gap
        assert "?" not in gap and "#" not in gap, gap


def test_main_returns_1_on_breakage_and_0_when_clean(tmp_path):
    site = _site(tmp_path)
    _page(site, "p.html", '<link rel="stylesheet" href="assets/css/deadbe.css">')
    assert main([str(site)]) == 1
    _page(site, "p.html", '<link rel="stylesheet" href="assets/css/abc123.css">')
    assert main([str(site)]) == 0


def test_selftest_passes():
    assert main(["--selftest"]) == 0


# ── severity split ────────────────────────────────────────────────────────────
# Template-decided targets (directories, asset hashes, page paths) are
# deterministic and fail. `stocks/<T>.html` is decided nightly by data, so a
# symbol outside that day's rendered universe warns instead of wedging the
# render — but it is still reported, never silently dropped.


def test_unrendered_ticker_link_warns_but_does_not_fail(tmp_path):
    site = _site(tmp_path)
    (site / "stocks" / "A.html").write_text(
        '<a class="pcard" href="/stocks/DELISTED.html">peer</a>', encoding="utf-8")
    assert find_dangling(site) == {"stocks/DELISTED.html": ["stocks/A.html"]}
    assert main([str(site)]) == 0  # reported, not fatal


def test_template_decided_target_still_fails_hard(tmp_path):
    site = _site(tmp_path)
    (site / "stocks" / "A.html").write_text(
        '<a href="../baskets/ai_infra.html">plural typo</a>', encoding="utf-8")
    assert main([str(site)]) == 1


def test_ticker_typo_outside_stocks_is_not_softened(tmp_path):
    """A wrong DIRECTORY is a template defect even when the leaf is a ticker."""
    site = _site(tmp_path)
    (site / "stocks" / "A.html").write_text(
        '<a href="/stock/AAPL.html">singular dir</a>', encoding="utf-8")
    assert main([str(site)]) == 1


def test_soft_and_hard_together_fail_on_the_hard_one(tmp_path):
    site = _site(tmp_path)
    (site / "stocks" / "A.html").write_text(
        '<a href="/stocks/DELISTED.html">soft</a>'
        '<link rel="stylesheet" href="assets/css/deadbe.css">', encoding="utf-8")
    assert main([str(site)]) == 1
