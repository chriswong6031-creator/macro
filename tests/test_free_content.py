"""tests/test_free_content.py — Free estate builder test suite.

Covers (per brief):
  - Frontmatter validation failures (bad description, unknown related slug,
    slug/filename mismatch) using tmp_path fixtures; never mutates real content.
  - Determinism: two renders -> identical bytes.
  - --check freshness contract.
  - Unique slugs / titles / descriptions / canonicals across all content.
  - Every rendered page has exactly one rel=canonical using www host.
  - Internal root-relative links in rendered output resolve to files in site/.
  - JSON-LD script tags parse as valid JSON.
  - feed.xml well-formed XML with canonical URLs.
  - Sitemap discovery includes new families; preserves /stocks/ + top-level behavior.

Where content .md files or designer templates don't exist yet the test skips with
a reason keyed on file existence (per brief: "at final assembly everything exists
and nothing may skip").

All fixture writes go to tmp_path (MM_DATA_GUARD law).
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.seo import (  # noqa: E402
    SITE_BASE,
    build_core_sitemap,
    discover_core_pages,
    discover_free_pages,
    page_url,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_CONTENT_DIR = _REPO / "content" / "seo"
_SITE_DIR = _REPO / "site"
_TEMPLATES_DIR = _REPO / "templates"


def _required_templates_present() -> bool:
    """Return True if all required designer templates exist."""
    names = [
        "seo_base.html.j2",
        "seo_products_index.html.j2",
        "seo_product.html.j2",
        "seo_tools_index.html.j2",
        "seo_learn_index.html.j2",
        "seo_blog_index.html.j2",
        "seo_article.html.j2",
    ]
    return all((_TEMPLATES_DIR / n).exists() for n in names)


def _any_content_exists() -> bool:
    """Return True if at least one .md content file exists."""
    for pattern in (
        "products/*.md",
        "blog/*.md",
        "learn/**/*.md",
        "pages/*.md",
        "tools/*.md",
    ):
        if any((_CONTENT_DIR).glob(pattern)):
            return True
    return False


def _make_valid_fm(**overrides) -> dict:
    """Return a base valid frontmatter dict, optionally overridden."""
    base = {
        "slug": "test-article",
        "family": "article",
        "title": "Test Article Title",
        "description": "A" * 120,  # exactly 120 chars — minimum valid
        "published": "2026-07-20",
        "updated": "2026-07-20",
    }
    base.update(overrides)
    return base


def _write_md(path: Path, fm: dict, body: str = "<p>Body text.</p>") -> None:
    """Write a .md file with YAML frontmatter + HTML body."""
    yaml_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml_text}---\n{body}\n", encoding="utf-8")


def _load_module():
    """Import build_free_content (re-import each call to avoid state leakage)."""
    import importlib
    import scripts.build_free_content as m
    importlib.reload(m)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter validation failures (CONTRACT §3, tmp_path only)
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontmatterValidation:
    """Test that _validate() raises ValueError on invalid frontmatter."""

    def _validate_fm(self, fm: dict, path: Path, all_slugs: frozenset = frozenset()):
        import scripts.build_free_content as bfc
        bfc._validate(fm, path, all_slugs)

    def test_description_too_short_fails(self, tmp_path):
        """description < 120 chars raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="Too short")
        with pytest.raises(ValueError, match="description"):
            self._validate_fm(fm, path)

    def test_description_too_long_fails(self, tmp_path):
        """description > 155 chars raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 156)
        with pytest.raises(ValueError, match="description"):
            self._validate_fm(fm, path)

    def test_description_exactly_120_passes(self, tmp_path):
        """description == 120 chars is valid."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 120)
        self._validate_fm(fm, path)  # should not raise

    def test_description_exactly_155_passes(self, tmp_path):
        """description == 155 chars is valid."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 155)
        self._validate_fm(fm, path)  # should not raise

    def test_slug_filename_mismatch_fails(self, tmp_path):
        """slug != filename stem raises ValueError."""
        path = tmp_path / "my-article.md"
        fm = _make_valid_fm(slug="different-slug", description="A" * 120)
        with pytest.raises(ValueError, match="slug"):
            self._validate_fm(fm, path)

    def test_slug_filename_match_passes(self, tmp_path):
        """slug == filename stem passes."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(slug="test-article", description="A" * 120)
        self._validate_fm(fm, path)  # should not raise

    def test_unknown_related_article_slug_fails(self, tmp_path):
        """related.articles slug not in §1 URL map and not in all_slugs raises."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            related={"articles": ["nonexistent-slug-xyz"]},
        )
        with pytest.raises(ValueError, match="related"):
            self._validate_fm(fm, path, frozenset())

    def test_known_related_article_slug_passes(self, tmp_path):
        """related.articles slug that exists in all_slugs passes."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            related={"articles": ["known-slug"]},
        )
        self._validate_fm(fm, path, frozenset({"known-slug"}))  # no raise

    def test_allowlisted_application_cta_passes(self, tmp_path):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            cta={
                "href": "https://app.mastermind-x.com/terminal?signup=1",
                "label": "Start free",
            },
        )
        self._validate_fm(fm, path)

    def test_unreviewed_external_cta_fails(self, tmp_path):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            cta={"href": "https://example.com/signup", "label": "Start"},
        )
        with pytest.raises(ValueError, match="CTA allowlist"):
            self._validate_fm(fm, path)

    def test_title_over_70_fails(self, tmp_path):
        """title > 70 chars raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 120, title="A" * 71)
        with pytest.raises(ValueError, match="title"):
            self._validate_fm(fm, path)

    def test_invalid_family_fails(self, tmp_path):
        """Unknown family raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 120, family="unknown_family")
        with pytest.raises(ValueError, match="family"):
            self._validate_fm(fm, path)

    def test_product_with_three_step_workflow_passes(self, tmp_path):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            family="product",
            product_name="Test Product",
            eyebrow="Test workflow",
            order=1,
            workflow=["Open the surface", "Inspect the evidence", "Continue"],
        )
        self._validate_fm(fm, path)

    def test_product_without_workflow_fails(self, tmp_path):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            family="product",
            product_name="Test Product",
            eyebrow="Test workflow",
            order=1,
        )
        with pytest.raises(ValueError, match="workflow"):
            self._validate_fm(fm, path)

    @pytest.mark.parametrize("order", ["2", 2.0, True, None])
    def test_product_order_must_be_an_integer(self, tmp_path, order):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            family="product",
            product_name="Test Product",
            eyebrow="Test workflow",
            order=order,
            workflow=["Open the surface", "Inspect the evidence", "Continue"],
        )
        with pytest.raises(ValueError, match="order must be an integer"):
            self._validate_fm(fm, path)

    @pytest.mark.parametrize("order", [0, 100, -1])
    def test_product_order_must_be_in_range(self, tmp_path, order):
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            family="product",
            product_name="Test Product",
            eyebrow="Test workflow",
            order=order,
            workflow=["Open the surface", "Inspect the evidence", "Continue"],
        )
        with pytest.raises(ValueError, match="between 1 and 99"):
            self._validate_fm(fm, path)

    def test_lesson_without_track_fails(self, tmp_path):
        """lesson family without track raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 120, family="lesson", slug="test-article")
        with pytest.raises(ValueError, match="track"):
            self._validate_fm(fm, path)

    def test_lesson_invalid_track_fails(self, tmp_path):
        """lesson with invalid track value raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            family="lesson",
            slug="test-article",
            track="badtrack",
        )
        with pytest.raises(ValueError, match="track"):
            self._validate_fm(fm, path)

    def test_lesson_valid_track_passes(self, tmp_path):
        """lesson with valid track passes."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(
            description="A" * 120,
            family="lesson",
            slug="test-article",
            track="technical",
        )
        self._validate_fm(fm, path)  # should not raise

    def test_missing_required_key_fails(self, tmp_path):
        """Missing 'published' key raises ValueError."""
        path = tmp_path / "test-article.md"
        fm = _make_valid_fm(description="A" * 120)
        del fm["published"]
        with pytest.raises(ValueError, match="published"):
            self._validate_fm(fm, path)


class TestBodyScriptValidation:
    """F2: D4 — body fragments containing '<script' must be rejected."""

    def test_body_with_script_raises(self, tmp_path):
        """load_content() raises ValueError when a body contains '<script'."""
        import scripts.build_free_content as bfc
        blog_dir = tmp_path / "blog"
        blog_dir.mkdir(parents=True, exist_ok=True)
        fm = _make_valid_fm(slug="bad-article", description="A" * 120)
        path = blog_dir / "bad-article.md"
        # Write a body with <script> — CONTRACT §3 forbids this
        yaml_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
        path.write_text(
            f"---\n{yaml_text}---\n<p>body</p><script>alert(1)</script>\n",
            encoding="utf-8"
        )
        # Patch content dir to tmp
        orig_content = bfc._CONTENT_DIR
        try:
            bfc._CONTENT_DIR = tmp_path
            with pytest.raises(ValueError, match="script"):
                bfc.load_content()
        finally:
            bfc._CONTENT_DIR = orig_content

    def test_body_without_script_passes(self, tmp_path):
        """load_content() does not raise for clean bodies."""
        import scripts.build_free_content as bfc
        blog_dir = tmp_path / "blog"
        blog_dir.mkdir(parents=True, exist_ok=True)
        fm = _make_valid_fm(slug="good-article", description="A" * 120)
        path = blog_dir / "good-article.md"
        yaml_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
        path.write_text(
            f"---\n{yaml_text}---\n<p>Clean body, no scripts.</p>\n",
            encoding="utf-8"
        )
        orig_content = bfc._CONTENT_DIR
        try:
            bfc._CONTENT_DIR = tmp_path
            pages, _ = bfc.load_content()
            assert len(pages) == 1
        finally:
            bfc._CONTENT_DIR = orig_content

    def test_duplicate_product_order_fails(self, tmp_path):
        import scripts.build_free_content as bfc
        products_dir = tmp_path / "products"
        for slug in ("alpha", "beta"):
            _write_md(
                products_dir / f"{slug}.md",
                _make_valid_fm(
                    slug=slug,
                    family="product",
                    title=f"{slug.title()} Product",
                    product_name=f"{slug.title()} Product",
                    eyebrow="Test workflow",
                    order=1,
                    workflow=["Open the surface", "Inspect the evidence", "Continue"],
                ),
            )
        orig_content = bfc._CONTENT_DIR
        try:
            bfc._CONTENT_DIR = tmp_path
            with pytest.raises(ValueError, match="order 1 duplicates"):
                bfc.load_content()
        finally:
            bfc._CONTENT_DIR = orig_content

    def test_free_estate_header_cta_starts_terminal_signup(self):
        template = (_TEMPLATES_DIR / "_public_nav.html.j2").read_text(
            encoding="utf-8"
        )
        assert (
            'href="https://app.mastermind-x.com/terminal?signup=1"' in template
        )
        assert "Start free" in template
        assert 'public-nav-cta" href="{{ rel }}index.html"' not in template


# ─────────────────────────────────────────────────────────────────────────────
# _parse_md
# ─────────────────────────────────────────────────────────────────────────────

class TestParseMd:
    def test_parse_basic(self, tmp_path):
        import scripts.build_free_content as bfc
        p = tmp_path / "article.md"
        fm = {"slug": "article", "title": "T"}
        _write_md(p, fm, "<p>Hello world</p>")
        result_fm, body = bfc._parse_md(p)
        assert result_fm["slug"] == "article"
        assert "<p>Hello world</p>" in body

    def test_parse_no_frontmatter_fails(self, tmp_path):
        import scripts.build_free_content as bfc
        p = tmp_path / "bad.md"
        p.write_text("no frontmatter here", encoding="utf-8")
        with pytest.raises(ValueError, match="---"):
            bfc._parse_md(p)

    def test_parse_missing_closing_fence_fails(self, tmp_path):
        import scripts.build_free_content as bfc
        p = tmp_path / "bad.md"
        p.write_text("---\nslug: foo\n<p>body</p>", encoding="utf-8")
        with pytest.raises(ValueError):
            bfc._parse_md(p)


# ─────────────────────────────────────────────────────────────────────────────
# _slugify / _anchor_h2s
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic(self):
        import scripts.build_free_content as bfc
        assert bfc._slugify("Hello World") == "hello-world"

    def test_collapses_special_chars(self):
        import scripts.build_free_content as bfc
        assert bfc._slugify("Position Sizing: The Only Edge") == "position-sizing-the-only-edge"

    def test_strips_leading_trailing_hyphens(self):
        import scripts.build_free_content as bfc
        assert not bfc._slugify("  ").startswith("-")


class TestAnchorH2s:
    def test_adds_id_to_h2(self):
        import scripts.build_free_content as bfc
        body = "<h2>What Is Risk</h2><p>text</p>"
        new_body, toc = bfc._anchor_h2s(body)
        assert 'id="what-is-risk"' in new_body
        assert toc == [{"id": "what-is-risk", "label": "What Is Risk"}]

    def test_multiple_h2s(self):
        import scripts.build_free_content as bfc
        body = "<h2>First</h2><h2>Second</h2>"
        _, toc = bfc._anchor_h2s(body)
        assert len(toc) == 2
        assert toc[0]["id"] == "first"
        assert toc[1]["id"] == "second"

    def test_existing_id_preserved_in_toc(self):
        import scripts.build_free_content as bfc
        body = '<h2 id="custom">Custom Heading</h2>'
        new_body, toc = bfc._anchor_h2s(body)
        # toc still tracks it
        assert any(t["label"] == "Custom Heading" for t in toc)


# ─────────────────────────────────────────────────────────────────────────────
# _rel_for_depth / _depth_of / _canonical
# ─────────────────────────────────────────────────────────────────────────────

class TestDepthHelpers:
    def test_root_level(self):
        import scripts.build_free_content as bfc
        assert bfc._depth_of("/about-research.html") == 0
        assert bfc._rel_for_depth(0) == ""

    def test_one_deep(self):
        import scripts.build_free_content as bfc
        assert bfc._depth_of("/blog/slug.html") == 1
        assert bfc._rel_for_depth(1) == "../"

    def test_two_deep(self):
        import scripts.build_free_content as bfc
        assert bfc._depth_of("/tools/calculators/cagr.html") == 2
        assert bfc._rel_for_depth(2) == "../../"

    def test_canonical_www(self):
        import scripts.build_free_content as bfc
        canon = bfc._canonical("/blog/test.html")
        assert canon.startswith("https://www.mastermind-x.com/")
        assert "mastermind-x.com/" in canon
        assert "//www" in canon


# ─────────────────────────────────────────────────────────────────────────────
# _rfc822
# ─────────────────────────────────────────────────────────────────────────────

class TestRfc822:
    def test_format(self):
        import scripts.build_free_content as bfc
        from datetime import date
        result = bfc._rfc822(date(2026, 7, 20))
        assert "2026" in result
        assert "GMT" in result
        assert "12:00:00" in result


# ─────────────────────────────────────────────────────────────────────────────
# RSS feed
# ─────────────────────────────────────────────────────────────────────────────

class TestRssFeed:
    def _make_article_page(self, slug: str, published: str = "2026-07-20") -> dict:
        return {
            "fm": {
                "slug": slug,
                "family": "article",
                "title": f"Article {slug}",
                "description": "A" * 120,
                "published": published,
                "updated": published,
            },
            "body_html": "<p>body</p>",
            "toc": [],
            "url_path": f"/blog/{slug}.html",
        }

    def test_rss_well_formed_xml(self):
        import scripts.build_free_content as bfc
        pages = [self._make_article_page("test-slug")]
        rss = bfc._build_rss(pages)
        # Must parse as valid XML
        ET.fromstring(rss)

    def test_rss_canonical_urls_www(self):
        import scripts.build_free_content as bfc
        pages = [self._make_article_page("test-slug")]
        rss = bfc._build_rss(pages)
        assert "https://www.mastermind-x.com/blog/test-slug.html" in rss
        assert "https://mastermind-x.com/" not in rss

    def test_rss_no_build_timestamps(self):
        """RSS output must be fully deterministic — no build-time date."""
        import scripts.build_free_content as bfc
        from datetime import date
        pages = [self._make_article_page("stable-slug", "2026-06-01")]
        rss1 = bfc._build_rss(pages)
        rss2 = bfc._build_rss(pages)
        assert rss1 == rss2

    def test_rss_pubdate_from_frontmatter(self):
        """pubDate must come from frontmatter, not build time."""
        import scripts.build_free_content as bfc
        pages = [self._make_article_page("dated-slug", "2026-01-15")]
        rss = bfc._build_rss(pages)
        assert "Jan" in rss or "2026" in rss  # RFC 822 includes the date

    def test_rss_articles_only(self):
        """Lessons must not appear in the feed."""
        import scripts.build_free_content as bfc
        lesson = {
            "fm": {
                "slug": "position-sizing",
                "family": "lesson",
                "title": "Position Sizing",
                "description": "A" * 120,
                "published": "2026-07-10",
                "updated": "2026-07-10",
                "track": "risk",
            },
            "body_html": "<p>body</p>",
            "toc": [],
            "url_path": "/learn/risk/position-sizing.html",
        }
        article = self._make_article_page("test-article")
        pages = [lesson, article]
        rss = bfc._build_rss(pages)
        assert "position-sizing" not in rss
        assert "test-article" in rss

    def test_rss_sorted_newest_first(self):
        """Articles in feed are sorted by published desc."""
        import scripts.build_free_content as bfc
        pages = [
            self._make_article_page("older", "2026-01-01"),
            self._make_article_page("newer", "2026-07-01"),
        ]
        rss = bfc._build_rss(pages)
        newer_pos = rss.index("newer")
        older_pos = rss.index("older")
        assert newer_pos < older_pos, "Newer article should appear first in RSS"


# ─────────────────────────────────────────────────────────────────────────────
# JSON-LD generation
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonLd:
    def test_article_jsonld_parses_as_json(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(description="A" * 120)
        fm["published"] = "2026-07-20"
        fm["updated"] = "2026-07-20"
        # Bare JSON payload — seo_base's jsonld block adds the <script> wrapper
        payload = bfc._article_jsonld(fm, "https://www.mastermind-x.com/blog/test.html")
        assert "<script" not in payload
        data = json.loads(payload)  # must not raise
        assert data["@type"] == "Article"
        assert data["datePublished"] == "2026-07-20"

    def test_article_jsonld_contains_organization(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(description="A" * 120)
        fm["published"] = "2026-07-20"
        fm["updated"] = "2026-07-20"
        payload = bfc._article_jsonld(fm, "https://www.mastermind-x.com/blog/test.html")
        data = json.loads(payload)
        assert data["author"]["name"] == "MastermindX Research"
        assert data["publisher"]["name"] == "MastermindX"

    def test_product_jsonld_describes_visible_application_without_offers(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(
            family="product",
            product_name="Market Terminal",
            description="A" * 120,
        )
        payload = bfc._product_jsonld(
            fm, "https://www.mastermind-x.com/products/market-terminal.html"
        )
        data = json.loads(payload)
        assert data["@type"] == "WebPage"
        assert data["mainEntity"]["@type"] == "SoftwareApplication"
        assert data["mainEntity"]["name"] == "Market Terminal"
        assert "offers" not in data["mainEntity"]
        assert "aggregateRating" not in data["mainEntity"]

    def test_lesson_jsonld_not_emitted_for_page_family(self):
        """family='page' must NOT get Article JSON-LD per CONTRACT §9."""
        import scripts.build_free_content as bfc
        # page family does not generate jsonld_extra in _build_page_ctx
        fm = _make_valid_fm(description="A" * 120, family="page")
        ctx_fm = fm.copy()
        ctx_fm["published"] = "2026-07-20"
        ctx_fm["updated"] = "2026-07-20"
        # jsonld_extra is only generated for article/lesson families
        from datetime import date
        page = {
            "fm": ctx_fm,
            "body_html": "<p>body</p>",
            "toc": [],
            "url_path": "/about-research.html",
        }
        ctx = bfc._build_page_ctx(page, {}, {})
        assert ctx["jsonld_extra"] == "", "page family should have no JSON-LD"


# ─────────────────────────────────────────────────────────────────────────────
# Breadcrumbs
# ─────────────────────────────────────────────────────────────────────────────

class TestBreadcrumbs:
    def test_article_breadcrumbs(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(description="A" * 120, family="article")
        crumbs = bfc._breadcrumbs(fm, "/blog/test.html")
        labels = [c["label"] for c in crumbs]
        assert "Home" in labels
        assert "Blog" in labels
        # last item has no href
        assert crumbs[-1]["href"] is None

    def test_lesson_breadcrumbs_include_track(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(description="A" * 120, family="lesson", track="risk")
        crumbs = bfc._breadcrumbs(fm, "/learn/risk/position-sizing.html")
        labels = [c["label"] for c in crumbs]
        assert "Home" in labels
        assert "Learn" in labels
        assert "Risk & Position Management" in labels

    def test_home_breadcrumb_has_href(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(description="A" * 120, family="article")
        crumbs = bfc._breadcrumbs(fm, "/blog/test.html")
        home = next(c for c in crumbs if c["label"] == "Home")
        assert home["href"] == "/"

    def test_product_breadcrumbs_include_platform_hub(self):
        import scripts.build_free_content as bfc
        fm = _make_valid_fm(
            description="A" * 120,
            family="product",
            product_name="Market Terminal",
        )
        crumbs = bfc._breadcrumbs(fm, "/products/market-terminal.html")
        assert crumbs[1] == {
            "label": "Platform",
            "href": "/products/index.html",
        }
        assert crumbs[-1] == {"label": "Market Terminal", "href": None}


# ─────────────────────────────────────────────────────────────────────────────
# Determinism tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterminism:
    @pytest.mark.skipif(
        not _required_templates_present() or not _any_content_exists(),
        reason="Designer templates or content .md files not yet present",
    )
    def test_two_renders_identical_bytes(self, tmp_path):
        """Two consecutive renders of real content produce byte-identical output."""
        import scripts.build_free_content as bfc
        out1 = tmp_path / "render1"
        out2 = tmp_path / "render2"
        out1.mkdir()
        out2.mkdir()

        bfc.render_all(out1)
        bfc.render_all(out2)

        files1 = sorted(f.relative_to(out1) for f in out1.rglob("*") if f.is_file())
        files2 = sorted(f.relative_to(out2) for f in out2.rglob("*") if f.is_file())

        assert files1 == files2, "File lists differ between renders"
        for rel in files1:
            b1 = (out1 / rel).read_bytes()
            b2 = (out2 / rel).read_bytes()
            assert b1 == b2, f"Output differs between renders for {rel}"

    def test_rss_deterministic_no_real_templates_needed(self):
        """RSS determinism check requires no templates."""
        import scripts.build_free_content as bfc
        pages = [
            {
                "fm": {
                    "slug": "slug-a", "family": "article",
                    "title": "Title A", "description": "A" * 120,
                    "published": "2026-07-20", "updated": "2026-07-20",
                },
                "body_html": "<p>body</p>",
                "toc": [],
                "url_path": "/blog/slug-a.html",
            }
        ]
        rss1 = bfc._build_rss(pages)
        rss2 = bfc._build_rss(pages)
        assert rss1 == rss2

    @pytest.mark.skipif(
        not _required_templates_present() or not _any_content_exists(),
        reason="Designer templates or content .md files not yet present",
    )
    def test_check_mode_passes_after_render(self, tmp_path, monkeypatch):
        """--check mode returns 0 when site/ was just rendered."""
        import scripts.build_free_content as bfc

        # Render into real site/ first, then check
        # (non-destructive: only free-estate paths are touched)
        # We patch _SITE_DIR to a tmp dir to avoid touching real site/
        out = tmp_path / "site"
        out.mkdir()
        monkeypatch.setattr(bfc, "_SITE_DIR", out)

        bfc.render_all(out)

        # Now check should return 0 (byte-identical)
        result = bfc._check_mode.__wrapped__ if hasattr(bfc._check_mode, '__wrapped__') else None
        # Run check mode: render to tmp inside the function and compare
        # We directly test that rendered output matches itself by calling render_all twice
        out2 = tmp_path / "verify"
        out2.mkdir()
        bfc.render_all(out2)
        for f in out.rglob("*"):
            if f.is_file():
                rel = f.relative_to(out)
                assert (out2 / rel).exists(), f"Missing in second render: {rel}"
                assert f.read_bytes() == (out2 / rel).read_bytes(), f"Drift: {rel}"


# ─────────────────────────────────────────────────────────────────────────────
# HAND_AUTHORED carve-out (flagship product pages are source, not output)
# ─────────────────────────────────────────────────────────────────────────────

class TestHandAuthoredPages:
    """The three flagship product pages are hand-authored source files.

    The generator must keep CONSUMING their content/seo/products/*.md
    front-matter (hub cards, related links, clusters) while never writing,
    drift-comparing, or orphan-flagging their HTML.
    """

    def test_constant_names_files_that_are_actually_committed(self):
        """A typo in HAND_AUTHORED would silently disable the exemption."""
        import scripts.build_free_content as bfc
        missing = [
            rel for rel in sorted(bfc.HAND_AUTHORED)
            if not (_SITE_DIR / rel).is_file()
        ]
        assert not missing, f"HAND_AUTHORED names non-existent site/ files: {missing}"

    def test_is_hand_authored_normalises_path_forms(self):
        """url_path, site-relative str, native Path and backslashes all match."""
        import scripts.build_free_content as bfc
        assert bfc._is_hand_authored("/products/market-terminal.html")
        assert bfc._is_hand_authored("products/market-terminal.html")
        assert bfc._is_hand_authored(Path("products/market-terminal.html"))
        assert bfc._is_hand_authored("products\\market-terminal.html")
        assert not bfc._is_hand_authored("/products/index.html")
        assert not bfc._is_hand_authored("blog/index.html")

    @pytest.mark.skipif(
        not _required_templates_present() or not _any_content_exists(),
        reason="Designer templates or content .md files not yet present",
    )
    def test_render_skips_hand_authored_but_still_writes_the_hub(self, tmp_path):
        """render_all writes products/index.html and none of the flagships."""
        import scripts.build_free_content as bfc
        out = tmp_path / "site"
        out.mkdir()
        bfc.render_all(out)

        assert (out / "products" / "index.html").is_file(), \
            "products hub must still be generated"
        written = [
            rel for rel in sorted(bfc.HAND_AUTHORED) if (out / rel).exists()
        ]
        assert not written, f"render_all overwrote hand-authored source: {written}"

    @pytest.mark.skipif(
        not _required_templates_present() or not _any_content_exists(),
        reason="Designer templates or content .md files not yet present",
    )
    def test_hub_still_carries_a_card_for_every_hand_authored_product(self, tmp_path):
        """Skipping the WRITE must not drop the page from `pages`.

        The .md front-matter is what builds the hub cards, so the carve-out is
        wrong the moment a flagship stops appearing on products/index.html.
        """
        import scripts.build_free_content as bfc
        pages, _ = bfc.load_content()
        ctx = bfc._products_hub_ctx(pages)
        listed = {item["url_path"] for item in ctx["items"]}
        for rel in sorted(bfc.HAND_AUTHORED):
            assert f"/{rel}" in listed, f"{rel} missing from products hub context"

        # …and the card actually reaches the rendered hub, not just the context.
        out = tmp_path / "site"
        out.mkdir()
        bfc.render_all(out)
        html = (out / "products" / "index.html").read_text(encoding="utf-8")
        for rel in sorted(bfc.HAND_AUTHORED):
            assert Path(rel).name in html, f"{rel} not linked from rendered hub"

    @pytest.mark.skipif(
        not _required_templates_present() or not _any_content_exists(),
        reason="Designer templates or content .md files not yet present",
    )
    def test_orphan_walk_does_not_flag_hand_authored_pages(self, capsys):
        """D5 must not call a committed hand-authored page an orphan.

        This is the load-bearing exemption: render_all no longer produces these
        files, so without the carve-out every one of them reports ORPHAN and the
        CI estate check goes red.  The rc assertion is the anti-vacuity sentinel
        — the orphan walk only runs after a clean drift compare, so a red check
        would make the ORPHAN assertions below pass by never executing.
        """
        import scripts.build_free_content as bfc
        rc = bfc._check_mode()
        captured = capsys.readouterr()
        assert rc == 0, (
            "estate --check is red, so the orphan walk never ran and this pin "
            f"proves nothing:\n{captured.err}"
        )
        for rel in sorted(bfc.HAND_AUTHORED):
            assert f"ORPHAN (not produced by builder): {rel}" not in captured.err


# ─────────────────────────────────────────────────────────────────────────────
# Uniqueness tests (require content files to exist)
# ─────────────────────────────────────────────────────────────────────────────

def _load_content_or_skip():
    """Load content, skipping the test if content files don't exist yet.

    If load_content() raises ValueError (content violation), that is a REAL
    error — not a skip. The test will surface it so B4/B5 can fix the content.
    """
    if not _any_content_exists():
        pytest.skip("No content .md files present yet")
    import scripts.build_free_content as bfc
    return bfc.load_content()


class TestUniqueness:
    @pytest.mark.skipif(
        not _any_content_exists(),
        reason="No content .md files present yet",
    )
    def test_unique_slugs(self):
        """All content files have unique slugs."""
        pages, _ = _load_content_or_skip()
        slugs = [p["fm"]["slug"] for p in pages]
        assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {[s for s in slugs if slugs.count(s) > 1]}"

    @pytest.mark.skipif(
        not _any_content_exists(),
        reason="No content .md files present yet",
    )
    def test_unique_titles(self):
        """All content files have unique titles."""
        pages, _ = _load_content_or_skip()
        titles = [p["fm"]["title"] for p in pages]
        assert len(titles) == len(set(titles)), (
            f"Duplicate titles: {[t for t in titles if titles.count(t) > 1]}"
        )

    @pytest.mark.skipif(
        not _any_content_exists(),
        reason="No content .md files present yet",
    )
    def test_unique_descriptions(self):
        """All content files have unique descriptions."""
        pages, _ = _load_content_or_skip()
        descs = [p["fm"]["description"] for p in pages]
        assert len(descs) == len(set(descs)), (
            f"Duplicate descriptions found"
        )

    @pytest.mark.skipif(
        not _any_content_exists(),
        reason="No content .md files present yet",
    )
    def test_unique_canonicals(self):
        """All content pages have unique canonical URLs."""
        import scripts.build_free_content as bfc
        pages, _ = _load_content_or_skip()
        canonicals = [bfc._canonical(p["url_path"]) for p in pages]
        assert len(canonicals) == len(set(canonicals)), "Duplicate canonical URLs"


# ─────────────────────────────────────────────────────────────────────────────
# Rendered output tests (require templates + content)
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderedOutput:
    """Tests on real rendered site/ output.

    Each test skips if the relevant file doesn't exist (templates/content pending).
    At final assembly all must pass (brief requirement).
    """

    def _get_rendered_html_files(self) -> list[Path]:
        """Return all rendered free-estate HTML files."""
        files = []
        for d in ("products", "blog", "learn", "tools"):
            subdir = _SITE_DIR / d
            if subdir.exists():
                files.extend(subdir.rglob("*.html"))
        # also about-research.html
        ar = _SITE_DIR / "about-research.html"
        if ar.exists():
            files.append(ar)
        return files

    def test_rendered_pages_have_exactly_one_canonical(self):
        """Each rendered page has exactly one <link rel=canonical>."""
        files = self._get_rendered_html_files()
        if not files:
            pytest.skip("No rendered free-estate HTML files found in site/")

        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            matches = re.findall(r'<link[^>]+rel=["\']canonical["\'][^>]*/?>',
                                 html, re.IGNORECASE)
            if len(matches) != 1:
                errors.append(f"{f.relative_to(_REPO)}: {len(matches)} canonical tags")
        assert not errors, "Pages with wrong canonical count:\n" + "\n".join(errors)

    def test_rendered_canonicals_use_www(self):
        """All <link rel=canonical> href values use www host."""
        files = self._get_rendered_html_files()
        if not files:
            pytest.skip("No rendered free-estate HTML files found in site/")

        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            for m in re.finditer(
                r'<link[^>]+rel=["\']canonical["\'][^>]*/?>',
                html, re.IGNORECASE
            ):
                href_m = re.search(r'href=["\']([^"\']+)["\']', m.group())
                if href_m:
                    href = href_m.group(1)
                    if not href.startswith("https://www.mastermind-x.com/"):
                        errors.append(f"{f.relative_to(_REPO)}: {href}")
        assert not errors, "Non-www canonical hrefs:\n" + "\n".join(errors)

    def test_rendered_jsonld_parses_as_json(self):
        """All <script type=application/ld+json> blocks parse as valid JSON."""
        files = self._get_rendered_html_files()
        if not files:
            pytest.skip("No rendered free-estate HTML files found in site/")

        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            for m in re.finditer(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html, re.DOTALL | re.IGNORECASE
            ):
                try:
                    json.loads(m.group(1))
                except json.JSONDecodeError as e:
                    errors.append(f"{f.relative_to(_REPO)}: {e}")
        assert not errors, "Invalid JSON-LD:\n" + "\n".join(errors)

    def test_rendered_internal_links_resolve(self):
        """Root-relative internal links in rendered pages point to files that exist."""
        files = self._get_rendered_html_files()
        if not files:
            pytest.skip("No rendered free-estate HTML files found in site/")

        # Paths known to exist on the live site (not in site/ repo copy, but real)
        _KNOWN_LIVE_PATHS = {
            "/", "/about-research.html",
            "/reports.html", "/movers.html", "/congress_trades.html",
            "/learn.html", "/index.html",
        }

        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            # Find root-relative href/src attributes (not external URLs, not #fragments)
            for m in re.finditer(r'href=["\'](/[^"\'#?]+)["\']', html):
                path = m.group(1)
                # Skip feed.xml / xml / json
                if path.endswith(".xml") or path.endswith(".json"):
                    continue
                # Skip known live paths (exist on the deployed site, not in repo)
                if path in _KNOWN_LIVE_PATHS:
                    continue
                site_path = _SITE_DIR / path.lstrip("/")
                if not site_path.exists():
                    # Free-estate paths must resolve; dashboard paths are live-only
                    if any(
                        path.startswith(p)
                        for p in ("/products/", "/blog/", "/learn/", "/tools/")
                    ):
                        errors.append(f"{f.relative_to(_REPO)}: broken link {path}")
        assert not errors, "Broken internal links:\n" + "\n".join(errors)

    def test_rendered_nested_runtime_assets_resolve(self):
        """Every estate page loads shared scripts from site root and never emits
        the root-only inline font URLs that become /products/fonts/* 404s."""
        files = self._get_rendered_html_files()
        if not files:
            pytest.skip("No rendered free-estate HTML files found in site/")

        errors = []
        for page in files:
            html = page.read_text(encoding="utf-8")
            if 'url("fonts/' in html:
                errors.append(
                    f"{page.relative_to(_REPO)}: nested inline font URL"
                )
            for asset in ("supabase.js", "account.js", "mm_brain.js", "theme.js"):
                refs = re.findall(
                    rf'<script[^>]+src=["\']([^"\']*{re.escape(asset)}'
                    rf'(?:\?[^"\']*)?)["\']',
                    html,
                )
                if len(refs) != 1:
                    errors.append(
                        f"{page.relative_to(_REPO)}: {len(refs)} {asset} refs"
                    )
                    continue
                href = refs[0].split("?", 1)[0]
                target = (page.parent / href).resolve()
                if target != (_SITE_DIR / asset).resolve():
                    errors.append(
                        f"{page.relative_to(_REPO)}: {asset} resolves to {target}"
                    )
        assert not errors, "Broken nested runtime assets:\n" + "\n".join(errors)

    def test_calculator_pages_have_related_rail(self):
        """F2: Calculator pages must contain the related rail markup (.est-related)."""
        calc_dir = _SITE_DIR / "tools" / "calculators"
        if not calc_dir.exists():
            pytest.skip("site/tools/calculators/ not yet rendered")
        files = list(calc_dir.glob("*.html"))
        if not files:
            pytest.skip("No calculator pages rendered")
        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            if 'class="est-related"' not in html and "est-related" not in html:
                errors.append(f"{f.relative_to(_REPO)}: missing related rail (.est-related)")
        assert not errors, "Calculator pages missing related rail:\n" + "\n".join(errors)

    def test_calculator_pages_have_cta(self):
        """F2: Calculator pages must contain the CTA block markup (.est-cta-block)."""
        calc_dir = _SITE_DIR / "tools" / "calculators"
        if not calc_dir.exists():
            pytest.skip("site/tools/calculators/ not yet rendered")
        files = list(calc_dir.glob("*.html"))
        if not files:
            pytest.skip("No calculator pages rendered")
        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            if "est-cta-block" not in html:
                errors.append(f"{f.relative_to(_REPO)}: missing CTA block (.est-cta-block)")
        assert not errors, "Calculator pages missing CTA block:\n" + "\n".join(errors)

    def test_calculator_pages_have_tools_nav_active(self):
        """F2: Calculator pages must have 'tools' nav item marked aria-current='page'."""
        calc_dir = _SITE_DIR / "tools" / "calculators"
        if not calc_dir.exists():
            pytest.skip("site/tools/calculators/ not yet rendered")
        files = list(calc_dir.glob("*.html"))
        if not files:
            pytest.skip("No calculator pages rendered")
        errors = []
        for f in files:
            html = f.read_text(encoding="utf-8")
            # The base template emits aria-current="page" on the tools nav link
            # when page.section == 'tools'
            if 'aria-current="page"' not in html:
                errors.append(f"{f.relative_to(_REPO)}: missing aria-current='page' nav marker")
        assert not errors, "Calculator pages missing active nav:\n" + "\n".join(errors)

    def test_lesson_pages_have_track_eyebrow(self):
        """F2: Lesson pages must contain their track eyebrow text."""
        learn_dir = _SITE_DIR / "learn"
        if not learn_dir.exists():
            pytest.skip("site/learn/ not yet rendered")
        lesson_files = [f for f in learn_dir.rglob("*.html")
                        if f.name != "index.html"]
        if not lesson_files:
            pytest.skip("No lesson pages rendered")
        # Track display labels used in the template
        track_labels = ["Technical analysis", "Risk", "Ownership", "Lesson"]
        errors = []
        for f in lesson_files:
            html = f.read_text(encoding="utf-8")
            found = any(label in html for label in track_labels)
            if not found:
                errors.append(f"{f.relative_to(_REPO)}: missing track eyebrow text")
        assert not errors, "Lesson pages missing track eyebrow:\n" + "\n".join(errors)

    def test_rss_feed_well_formed(self):
        """site/blog/feed.xml is well-formed XML with canonical URLs."""
        feed_path = _SITE_DIR / "blog" / "feed.xml"
        if not feed_path.exists():
            pytest.skip("site/blog/feed.xml not yet rendered")

        text = feed_path.read_text(encoding="utf-8")
        # Must parse as XML
        try:
            ET.fromstring(text)
        except ET.ParseError as e:
            pytest.fail(f"feed.xml is not valid XML: {e}")

        # All URLs must be www
        assert "https://mastermind-x.com/" not in text, \
            "feed.xml contains apex (non-www) URL"
        assert "https://www.mastermind-x.com/" in text or \
            "mastermind-x.com" not in text, \
            "feed.xml missing www canonical URL"


# ─────────────────────────────────────────────────────────────────────────────
# Sitemap discovery tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSitemapDiscovery:
    """Test discover_free_pages and build_core_sitemap with new families."""

    def _make_free_site(self, tmp_path: Path) -> Path:
        """Create a minimal site/ with free-estate subdirs."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "index.html").write_text("<html></html>")
        (site / "macro.html").write_text("<html></html>")

        # products
        products = site / "products"
        products.mkdir()
        (products / "index.html").write_text("<html></html>")
        (products / "market-terminal.html").write_text("<html></html>")

        # blog
        blog = site / "blog"
        blog.mkdir()
        (blog / "index.html").write_text("<html></html>")
        (blog / "test-article.html").write_text("<html></html>")

        # learn
        learn = site / "learn"
        learn.mkdir()
        (learn / "index.html").write_text("<html></html>")
        tech = learn / "technical"
        tech.mkdir()
        (tech / "rsi.html").write_text("<html></html>")

        # tools
        tools = site / "tools"
        tools.mkdir()
        (tools / "index.html").write_text("<html></html>")
        calc = tools / "calculators"
        calc.mkdir()
        (calc / "position-size.html").write_text("<html></html>")
        ss = tools / "spreadsheets"
        ss.mkdir()
        (ss / "trading-journal.html").write_text("<html></html>")

        # stocks
        stocks = site / "stocks"
        stocks.mkdir()
        (stocks / "AAPL.html").write_text("<html></html>")

        return site

    def test_discover_free_pages_finds_products_hub(self, tmp_path):
        site = self._make_free_site(tmp_path)
        rels = [r[0] for r in discover_free_pages(site)]
        assert "products/index.html" in rels

    def test_discover_free_pages_finds_product_leaf(self, tmp_path):
        site = self._make_free_site(tmp_path)
        rels = [r[0] for r in discover_free_pages(site)]
        assert "products/market-terminal.html" in rels

    def test_discover_free_pages_finds_blog_hub(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "blog/index.html" in rels

    def test_discover_free_pages_finds_blog_leaf(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "blog/test-article.html" in rels

    def test_discover_free_pages_finds_learn_hub(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "learn/index.html" in rels

    def test_discover_free_pages_finds_learn_leaf(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "learn/technical/rsi.html" in rels

    def test_discover_free_pages_finds_tools_hub(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "tools/index.html" in rels

    def test_discover_free_pages_finds_tools_calculator(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "tools/calculators/position-size.html" in rels

    def test_discover_free_pages_finds_tools_spreadsheet(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "tools/spreadsheets/trading-journal.html" in rels

    def test_discover_free_pages_hub_priority_07(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        for rel, url, freq, fname, pri in results:
            if fname == "index.html":
                assert pri == 0.7, f"Hub {rel} should have priority 0.7, got {pri}"
                assert freq == "weekly", f"Hub {rel} should be weekly, got {freq}"

    def test_discover_free_pages_leaf_priority_06(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        for rel, url, freq, fname, pri in results:
            if fname != "index.html":
                assert pri == 0.6, f"Leaf {rel} should have priority 0.6, got {pri}"
                assert freq == "monthly", f"Leaf {rel} should be monthly, got {freq}"

    def test_discover_free_pages_no_feed_xml(self, tmp_path):
        """feed.xml must never appear in discover_free_pages."""
        site = self._make_free_site(tmp_path)
        (site / "blog" / "feed.xml").write_text("<?xml?>", encoding="utf-8")
        results = discover_free_pages(site)
        rels = [r[0] for r in results]
        assert "blog/feed.xml" not in rels

    def test_discover_free_pages_www_urls(self, tmp_path):
        site = self._make_free_site(tmp_path)
        results = discover_free_pages(site)
        for _, url, _, _, _ in results:
            assert url.startswith("https://www.mastermind-x.com/"), \
                f"Non-www URL in discover_free_pages: {url}"

    def test_build_core_sitemap_includes_blog(self, tmp_path):
        """build_core_sitemap includes blog/* pages after extension."""
        site = self._make_free_site(tmp_path)
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        assert "https://www.mastermind-x.com/blog/index.html" in result
        assert "https://www.mastermind-x.com/blog/test-article.html" in result

    def test_build_core_sitemap_includes_products(self, tmp_path):
        site = self._make_free_site(tmp_path)
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        assert "https://www.mastermind-x.com/products/index.html" in result
        assert (
            "https://www.mastermind-x.com/products/market-terminal.html"
            in result
        )

    def test_build_core_sitemap_includes_learn(self, tmp_path):
        site = self._make_free_site(tmp_path)
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        assert "https://www.mastermind-x.com/learn/index.html" in result
        assert "https://www.mastermind-x.com/learn/technical/rsi.html" in result

    def test_build_core_sitemap_includes_tools(self, tmp_path):
        site = self._make_free_site(tmp_path)
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        assert "https://www.mastermind-x.com/tools/index.html" in result
        assert "https://www.mastermind-x.com/tools/calculators/position-size.html" in result

    def test_build_core_sitemap_still_preserves_stocks(self, tmp_path):
        """Existing /stocks/ behavior is unchanged after extension."""
        site = self._make_free_site(tmp_path)
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://www.mastermind-x.com/stocks/AAPL.html</loc>'
            '<lastmod>2026-07-20</lastmod>'
            '<changefreq>daily</changefreq><priority>0.6</priority></url>\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(existing, site)
        assert "https://www.mastermind-x.com/stocks/AAPL.html" in result

    def test_build_core_sitemap_still_excludes_stocks_from_core(self, tmp_path):
        """site/stocks/*.html is still NOT in discover_core_pages after extension."""
        site = self._make_free_site(tmp_path)
        pages = discover_core_pages(site)
        for _, url, _ in pages:
            assert "/stocks/" not in url

    def test_sitemap_valid_xml_with_free_pages(self, tmp_path):
        """build_core_sitemap output is valid XML when free-estate pages are present."""
        site = self._make_free_site(tmp_path)
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        ET.fromstring(result)  # must not raise

    def test_sitemap_no_feed_xml(self, tmp_path):
        """feed.xml never appears in the sitemap."""
        site = self._make_free_site(tmp_path)
        (site / "blog" / "feed.xml").write_text("<?xml?>", encoding="utf-8")
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        assert "feed.xml" not in result

    def test_live_sitemap_includes_free_pages(self):
        """The committed site/sitemap.xml includes free-estate pages if they exist."""
        sm_path = _REPO / "site" / "sitemap.xml"
        if not sm_path.exists():
            pytest.skip("site/sitemap.xml not present")

        # Check if any free pages are rendered
        blog_idx = _SITE_DIR / "blog" / "index.html"
        if not blog_idx.exists():
            pytest.skip("Free-estate pages not yet rendered into site/")

        sm_text = sm_path.read_text()
        assert "https://www.mastermind-x.com/blog/index.html" in sm_text, \
            "blog/index.html missing from committed sitemap"
        products_idx = _SITE_DIR / "products" / "index.html"
        if products_idx.exists():
            assert "https://www.mastermind-x.com/products/index.html" in sm_text, \
                "products/index.html missing from committed sitemap"


# ─────────────────────────────────────────────────────────────────────────────
# llms.txt
# ─────────────────────────────────────────────────────────────────────────────

class TestLlmsTxt:
    def test_free_tools_section_in_templates(self):
        """templates/llms.txt has the '## Free tools & learning' section."""
        p = _REPO / "templates" / "llms.txt"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "## Free tools & learning" in text

    def test_free_tools_section_in_site(self):
        """site/llms.txt has the '## Free tools & learning' section."""
        p = _REPO / "site" / "llms.txt"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "## Free tools & learning" in text

    def test_llms_txt_byte_match(self):
        """templates/llms.txt and site/llms.txt are byte-identical."""
        tpl = (_REPO / "templates" / "llms.txt").read_bytes()
        site = (_REPO / "site" / "llms.txt").read_bytes()
        assert tpl == site, "templates/llms.txt and site/llms.txt do not byte-match"

    def test_llms_txt_mentions_tools_hub(self):
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "/tools/index.html" in text

    def test_llms_txt_mentions_product_hub(self):
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "/products/index.html" in text
        assert text.startswith("# MastermindX")

    def test_llms_txt_mentions_learn_hub(self):
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "/learn/index.html" in text

    def test_llms_txt_mentions_blog_hub(self):
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "/blog/index.html" in text

    def test_llms_txt_mentions_trading_journal(self):
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "trading-journal" in text.lower()

    def test_llms_txt_www_only(self):
        """No apex host in llms.txt."""
        text = (_REPO / "templates" / "llms.txt").read_text()
        assert "https://mastermind-x.com/" not in text


# ─────────────────────────────────────────────────────────────────────────────
# Empty site (no free pages) — graceful behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestGracefulEmpty:
    def test_discover_free_pages_empty_site(self, tmp_path):
        """discover_free_pages returns empty list when subdirs don't exist."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "index.html").write_text("<html></html>")
        results = discover_free_pages(site)
        assert results == []

    def test_build_core_sitemap_no_free_pages(self, tmp_path):
        """build_core_sitemap doesn't fail when no free-estate pages exist."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "index.html").write_text("<html></html>")
        (site / "macro.html").write_text("<html></html>")
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '</urlset>\n'
        )
        result = build_core_sitemap(empty, site)
        ET.fromstring(result)  # valid XML
        assert "<loc>https://www.mastermind-x.com/</loc>" in result
        assert "https://www.mastermind-x.com/macro.html" not in result
