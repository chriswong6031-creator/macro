"""Tests for the per-report SEO landing pages (RV programmatic SEO).

Guards the pieces that make the Google play work: stable/unique slugs, a paywalled
JSON-LD contract (isAccessibleForFree:false + hasPart), the teaser-not-full-summary
exposure, the public first-pages excerpt (present when supplied, absent when not,
and always OUTSIDE the gated part), the ?doc= funnel CTA, and a sitemap merge that
never eats other sections.
"""
from __future__ import annotations

import re

import pytest
from jinja2 import Environment, FileSystemLoader

from scripts import build_research_pages as rp

_ITEM = {
    "id": "marketdesk-abc123-71f35b",
    "title": "JPM US Market Intel | Morning Briefing",
    "institution": "J.P. Morgan",
    "side": "sell",
    "desk": "Equity Research",
    "published_at": "2026-07-24T10:08:48Z",
    "summary_points": ["**Teaserbullet** with the thesis.", "Secretbullettwo copy.", "Secretbulletthree copy."],
    "tags": ["Rates", "Equities"],
    "tickers": ["JPM", "SPX"],
    "pages": 12,
}


def _norm_render(item: dict, excerpt_paras: list[str] | None = None) -> str:
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=True, trim_blocks=True, lstrip_blocks=True)
    n = rp._norm(item)
    canonical = f"{rp.CANONICAL_BASE}/research/x.html"
    md = f"{n['inst']} research. {n['teaser']}"
    return env.get_template("research_report.html.j2").render(
        n=n, canonical=canonical, meta_desc=md,
        jsonld_str=rp._jsonld(n, canonical, md), related=[],
        excerpt_paras=excerpt_paras or [], site_base=rp.CANONICAL_BASE)


# --- slugs -----------------------------------------------------------------
def test_slug_is_kebab_with_id_suffix():
    s = rp._slug(_ITEM["title"], _ITEM["id"], set())
    assert re.fullmatch(r"[a-z0-9-]+", s)
    assert s.endswith("71f35b")               # stable id suffix
    assert "jpm-us-market-intel" in s


def test_paren_repair_does_not_move_the_published_slug():
    """A closed ticker parenthetical must keep the page's already-indexed URL.

    The four production truncations ("Alcon Inc. (ALCC" …) ship as live
    /research/ pages; repairing the title may not orphan them.
    """
    for raw in ("Alcon Inc. (ALCC", "SAP (SAPG", "Repsol (REP", "Carrefour (CARR"):
        item = dict(_ITEM, title=raw)
        assert rp._slug(raw, _ITEM["id"], set()) == rp.slug_map([item])[_ITEM["id"]]


def test_slug_map_unique_and_deterministic():
    items = [dict(_ITEM, id=f"x{i}-aaa{i:03d}", title="Same Title") for i in range(5)]
    a = rp.slug_map(items)
    b = rp.slug_map(items)
    assert a == b                              # deterministic
    assert len(set(a.values())) == 5           # unique despite identical titles


# --- paywalled JSON-LD + teaser exposure -----------------------------------
def test_page_is_marked_paywalled_and_leaks_only_the_teaser():
    html = _norm_render(_ITEM)
    assert '"isAccessibleForFree": false' in html
    assert '"hasPart"' in html and '.rr-gate' in html      # gated part declared
    assert '"@type": "Article"' in html
    # the FIRST bullet (teaser) is public; later bullets are NOT in the page
    assert "Teaserbullet with the thesis" in html
    assert "Secretbullettwo" not in html
    assert "Secretbulletthree" not in html
    # markdown emphasis is stripped from the public snippet
    assert "**Teaserbullet" not in html


# --- title repair at the render boundary ------------------------------------
def _head(html: str) -> str:
    return html.split("</head>", 1)[0]


def test_truncated_title_never_ships_unbalanced_into_the_head():
    """#3505 regression: "Alcon Inc. (ALCC" reached <title>/og:title verbatim.

    The upstream desk truncates its Reuters ticker parenthetical at the "."; these
    pages are public and the title is the most SEO-weighted element on them, so the
    builder repairs rather than trusts the catalog.
    """
    html = _norm_render(dict(_ITEM, title="Alcon Inc. (ALCC"))
    head = _head(html)
    assert "Alcon Inc. (ALCC)" in head
    assert "<title>Alcon Inc. (ALCC) — J.P. Morgan" in head
    assert 'og:title" content="Alcon Inc. (ALCC) — J.P. Morgan"' in head
    assert 'twitter:title" content="Alcon Inc. (ALCC) — J.P. Morgan"' in head
    assert "<h1>Alcon Inc. (ALCC)</h1>" in html
    # no dangling "(" anywhere the crawler reads the name
    assert head.count("(") == head.count(")")


def test_dedupe_marker_never_reaches_the_page_or_the_url():
    item = dict(_ITEM, title="Carrefour (CARR(1)")
    assert rp._norm(item)["title"] == "Carrefour (CARR)"
    assert "-1-" not in rp.slug_map([item])[_ITEM["id"]]
    assert "Carrefour (CARR)" in _head(_norm_render(item))


def test_every_committed_report_title_is_balanced():
    """Production guard over the REAL catalog: no live page ships a stray paren."""
    from scripts.build_research_vault import _public_catalog, load_catalog
    items = _public_catalog(load_catalog())["items"]
    if not items:
        pytest.skip("committed catalog is empty")
    bad = [n["title"] for n in map(rp._norm, items)
           if n["title"].count("(") != n["title"].count(")")]
    assert not bad, f"unbalanced parens in rendered titles: {bad}"


# --- public first-pages excerpt --------------------------------------------
# NOTE: the CSS class names (.rr-x, .rr-x-fade …) are in the <style> block on
# EVERY page, so a bare 'rr-x' substring proves nothing — assert on the markup.
_EXCERPT = ["Alphaquotable first paragraph of the pdf body text here.",
            "Bravosecond paragraph continues the argument."]


def test_excerpt_paragraphs_are_public_when_provided():
    html = _norm_render(_ITEM, excerpt_paras=_EXCERPT)
    # The exact-quote play: the report's own words are on the page, verbatim.
    assert "Alphaquotable" in html
    assert "Bravosecond" in html
    assert '<section class="rr-x"' in html
    # The excerpt is PUBLIC: it renders before (outside) the gated part, so the
    # JSON-LD hasPart/.rr-gate paywall declaration stays truthful.
    assert html.index('<section class="rr-x"') < html.index('<div class="rr-gate">')
    assert '"isAccessibleForFree": false' in html
    # noarchive keeps the cache from serving the excerpt around us.
    assert "noarchive" in html


def test_no_excerpt_renders_like_before():
    html = _norm_render(_ITEM, excerpt_paras=[])
    assert '<section class="rr-x"' not in html
    assert "Alphaquotable" not in html
    # the pre-excerpt page contract is untouched
    assert '"isAccessibleForFree": false' in html
    assert '<div class="rr-gate">' in html


def test_page_has_canonical_and_funnel_cta():
    html = _norm_render(_ITEM)
    assert '<link rel="canonical"' in html
    assert f'?doc={_ITEM["id"]}' in html                   # deep-link back to the viewer
    assert "J.P. Morgan" in html and "SELL" in html


# --- sitemap merge ---------------------------------------------------------
def test_sitemap_merge_preserves_other_sections():
    existing = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://www.mastermind-x.com/macro.html</loc></url>\n'
        '  <url><loc>https://www.mastermind-x.com/stocks/AAPL.html</loc></url>\n'
        '  <url><loc>https://www.mastermind-x.com/research/OLD.html</loc></url>\n'
        '</urlset>\n')
    out = rp.build_sitemap(existing, [{"loc": "https://www.mastermind-x.com/research/new.html"}])
    assert "/macro.html" in out                # untouched
    assert "/stocks/AAPL.html" in out          # ticker pages preserved
    assert "/research/OLD.html" not in out     # stale /research/ replaced
    assert "/research/new.html" in out         # fresh /research/ added
    assert out.count("</urlset>") == 1         # well-formed


# --- end-to-end build: a non-empty catalog MUST produce pages ---------------
def _redirect_out(monkeypatch, tmp_path):
    """Point the builder's outputs at tmp_path (never write the live site/ tree)."""
    monkeypatch.setattr(rp, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(rp, "SITEMAP", tmp_path / "sitemap.xml")


def test_build_writes_pages_hub_and_sitemap_for_nonempty_catalog(monkeypatch, tmp_path):
    _redirect_out(monkeypatch, tmp_path)
    other = dict(_ITEM, id="ubs-xyz789-99aa11", title="Second Report", institution="UBS")
    n = rp.build({"items": [_ITEM, other]})
    assert n == 2
    names = {p.name for p in (tmp_path / "research").glob("*.html")}
    assert "index.html" in names               # crawl hub emitted
    assert len(names) == 3                     # 2 report pages + hub
    xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert xml.count("<url>") == 3             # hub + 2 reports merged into sitemap


def test_build_prunes_the_page_a_retitle_orphans(monkeypatch, tmp_path):
    """A repaired title can move a slug; the old file must not survive as a
    self-canonical near-duplicate that nothing links to."""
    _redirect_out(monkeypatch, tmp_path)
    rp.build({"items": [dict(_ITEM, title="Carrefour (CARR(1)")]})
    stale = tmp_path / "research" / "carrefour-carr-1-71f35b.html"
    stale.write_text("<html>orphan</html>", encoding="utf-8")

    rp.build({"items": [dict(_ITEM, title="Carrefour (CARR(1)")]})
    assert not stale.exists()
    assert (tmp_path / "research" / "carrefour-carr-71f35b.html").exists()
    assert (tmp_path / "research" / "index.html").exists()      # hub is never pruned


def test_build_refuses_to_mass_prune_on_a_partial_catalog(monkeypatch, tmp_path, capsys):
    """A degraded catalog must not be able to de-index the section."""
    _redirect_out(monkeypatch, tmp_path)
    full = [dict(_ITEM, id=f"md-{i}-aaa{i:03d}", title=f"Report {i}") for i in range(12)]
    rp.build({"items": full})
    before = {p.name for p in (tmp_path / "research").glob("*.html")}
    capsys.readouterr()                                        # drop the first build's output

    rp.build({"items": full[:2]})                              # catalog collapses
    after = {p.name for p in (tmp_path / "research").glob("*.html")}
    assert after == before                                     # nothing deleted

    # The refusal is a GitHub annotation, so it is a BARE print on stdout — routed
    # through logging it would emit "WARNING ::warning …" and GitHub would ignore it
    # (see tests/test_gh_annotation_line_start.py). Assert the column-0 form.
    out = capsys.readouterr().out
    warn = [ln for ln in out.splitlines() if "refusing to prune" in ln]
    assert warn, f"no refusal line on stdout, got: {out!r}"
    assert warn[0].startswith("::warning title=research_pages::"), (
        f"annotation must start at column 0 or GitHub drops it, got: {warn[0]!r}")


def test_build_on_committed_catalog_never_yields_zero_pages(monkeypatch, tmp_path):
    """#3392 regression: the production catalog must always yield landing pages.

    Guards the failure class that shipped dark: a non-empty committed catalog
    with zero site/research/*.html produced. Runs the REAL committed
    data/research_vault/catalog.json through the vault build's own projection,
    so any data-shape drift that breaks the builder fails HERE — not silently
    inside the nightly's fail-soft wrapper.
    """
    from scripts.build_research_vault import _public_catalog, load_catalog
    catalog = _public_catalog(load_catalog())
    if not catalog["items"]:
        pytest.skip("committed catalog is empty — empty state is the honest render")
    _redirect_out(monkeypatch, tmp_path)
    written = rp.build(catalog)
    assert written > 0                         # the alarm: non-empty catalog, zero pages
    renderable = [it for it in catalog["items"] if it.get("id")]
    assert written == len(renderable)          # one landing page per id-bearing report
    assert (tmp_path / "research" / "index.html").exists()


# --- titles: the real committed catalog, not a synthetic fixture --------------
# #3562 and #3570 each fixed a title defect that reached public <title>/<h1>/
# JSON-LD, and each shipped only SYNTHETIC coverage. The recurrence guard has to
# run over the REAL catalog: an ingest-time fix cannot reach a document that
# already has a receipt, so a bad row can sit in data/research_vault/catalog.json
# indefinitely without any synthetic test noticing.

def test_committed_catalog_never_titles_a_report_after_its_source_filename():
    """#3570 regression, over the REAL committed catalog.

    Three reports shipped a de-slugified PDF filename as the public title of their
    SEO landing page ("2026 07 24 Pmi Fall Seven Times Get Up Eight en"). Those
    pages exist so someone Googling the exact report title lands on us, and a
    filename matches nothing anyone types.

    The literal check — title == deslug(source filename) — is neither available
    nor meaningful here: ``catalog._ITEM_FIELDS`` deliberately drops
    ``source_filename``, and the page slug is DERIVED FROM the title, so
    slug-vs-title equality holds for every healthy row too. The property that
    separates good from bad is the filename *shape*, which is what
    ``title.looks_filename_derived`` reports — and since it is defined as
    ``clean(t) != t``, the detector can never drift from the repair.
    """
    from engine.research_vault import title as title_mod
    from scripts.build_research_vault import _public_catalog, load_catalog

    items = _public_catalog(load_catalog())["items"]
    if not items:
        pytest.skip("committed catalog is empty — nothing to guard")

    bad = [(it.get("id"), it.get("title")) for it in items
           if title_mod.looks_filename_derived(it.get("title") or "")]
    assert bad == [], (
        "catalog rows titled after their source PDF filename — this string becomes "
        f"the public <title>/<h1>/JSON-LD headline of a /research/ page: {bad[:5]}"
    )


def test_committed_catalog_titles_reach_every_seo_surface_clean():
    """<title>, <h1>, og:title and JSON-LD "headline" are separately derived.

    A fix that lands in one and misses another still ships the bad string to the
    crawler that matters, so assert on the RENDERED page rather than the catalog.
    Covers both defect classes at their real heal point: filename shape (#3570,
    repaired in the catalog) and the dangling truncated paren (#3562, repaired at
    render by ``clean_title`` — so the catalog legitimately still holds
    "Alcon Inc. (ALCC" and only the rendered output must be balanced).

    The shape predicates run on the FULL title only. ``_jsonld`` caps headline at
    110 chars (Google's limit), and a mid-word cut can strip a closing paren or
    leave a trailing comma — an artefact of truncation, not a title defect. The
    honest assertion for that surface is that it is the leading slice of the same
    repaired title, which is what proves the repair reached it.
    """
    import html as _html

    from engine.research_vault import title as title_mod
    from scripts.build_research_vault import _public_catalog, load_catalog

    items = _public_catalog(load_catalog())["items"]
    if not items:
        pytest.skip("committed catalog is empty — nothing to render")

    offenders: list[tuple] = []
    for item in items:
        page = _norm_render(item)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        head = re.search(r"<title>(.*?)</title>", page, re.S)
        jsonld = re.search(r'"headline":\s*"([^"]*)"', page)
        assert h1 and head and jsonld, f"{item.get('id')}: an SEO surface is missing"

        title_txt = _html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip()
        if title_mod.looks_filename_derived(title_txt):
            offenders.append((item.get("id"), "filename-shaped", title_txt))
        if title_txt.count("(") > title_txt.count(")"):
            offenders.append((item.get("id"), "dangling-paren", title_txt))

        # the same repaired string must feed <title> and the JSON-LD headline
        if title_txt not in _html.unescape(head.group(1)):
            offenders.append((item.get("id"), "<title> disagrees with <h1>", title_txt))
        if not title_txt.startswith(_html.unescape(jsonld.group(1))):
            offenders.append((item.get("id"), "headline is not the title", title_txt))
    assert offenders == [], f"bad title reached a public SEO surface: {offenders[:5]}"


# --- stale-page prune (a retitled report MOVES; the old URL must not survive) --
def test_prune_stale_drops_orphans_but_keeps_the_hub():
    keep = {"a-111111.html", "index.html"}
    names = ["a-111111.html", "index.html", "old-title-111111.html"]
    assert rp.prune_stale(keep, names) == ["old-title-111111.html"]


def test_prune_stale_refuses_a_mass_delete():
    """A catalog that came back short must never wipe the estate — the guard
    refuses wholesale, and build() then logs it instead of deleting."""
    keep = {"a-111111.html", "index.html"}
    names = ["a-111111.html", "index.html"] + [f"gone-{i}.html" for i in range(20)]
    assert rp.prune_stale(keep, names) == []


def test_prune_stale_ignores_non_html():
    keep = {"index.html"}
    assert rp.prune_stale(keep, ["index.html", "notes.txt"]) == []


def test_build_removes_the_page_of_a_retitled_report(monkeypatch, tmp_path):
    _redirect_out(monkeypatch, tmp_path)
    rp.build({"items": [_ITEM]})
    before = {p.name for p in (tmp_path / "research").glob("*.html")}
    old = next(n for n in before if n != "index.html")

    rp.build({"items": [dict(_ITEM, title="PMI: Fall Seven Times, Get Up Eight")]})
    after = {p.name for p in (tmp_path / "research").glob("*.html")}
    assert old not in after                     # the stale URL is gone, not duplicated
    assert "pmi-fall-seven-times-get-up-eight-71f35b.html" in after
    assert "index.html" in after
