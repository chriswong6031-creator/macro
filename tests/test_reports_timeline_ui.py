"""Regression guards for the reports archive typography and timeline rail."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "reports.html.j2"
PUBLISHED = ROOT / "site" / "reports.html"
PRICE_TEMPLATE = ROOT / "templates" / "report_price_of_duration.html.j2"
PRICE_PUBLISHED = ROOT / "site" / "report_price_of_duration.html"
REGISTRY = ROOT / "scripts" / "build_reports.py"

PRICE_FIGURE_IDS = (
    "fig-timeline",
    "fig-collision",
    "fig-quadrant",
    "fig-reactions",
    "fig-stablecoin",
    "fig-ai-frontier",
    "fig-memory",
    "fig-triangle",
    "fig-regimes",
    "fig-cockpit",
)

PRICE_ANCHORS = (
    "opening",
    "accountability",
    "duration",
    "policy",
    "stablecoins",
    "ai",
    "global",
    "assets",
    "regimes",
    "triggers",
    "road",
    "portfolio",
    "falsifiers",
    "conclusion",
    "sources",
)


def test_reports_page_uses_san_francisco_with_inter_fallback() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "-apple-system,BlinkMacSystemFont" in source
    assert '"SF Pro Text","SF Pro Display",Inter' in source
    assert "--rc-display:" in source
    assert "--rc-serif:" not in source
    assert "Georgia" not in source


def test_timeline_date_and_marker_occupy_separate_grid_columns() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", " ", source)

    assert '<time class="rc-date" datetime="{{ r.date }}">' in source
    assert ".rc-date{ grid-column:1; grid-row:1;" in compact
    assert (
        ".rc-rail .dot{ grid-column:2; grid-row:1; position:relative;"
        in compact
    )
    assert ".rc-rail .dot{ position:absolute;" not in compact


def test_published_reports_stylesheet_hash_matches_its_contents() -> None:
    html = PUBLISHED.read_text(encoding="utf-8")
    match = re.search(
        r'href="assets/css/([0-9a-f]{8})\.css\?v=\1"',
        html,
    )

    assert match, "reports.html must reference a content-hashed stylesheet"
    css = ROOT / "site" / "assets" / "css" / f"{match.group(1)}.css"
    assert css.exists()
    assert hashlib.sha256(css.read_bytes()).hexdigest().startswith(match.group(1))

    published_css = re.sub(r"\s+", " ", css.read_text(encoding="utf-8"))
    assert '"SF Pro Text","SF Pro Display",Inter' in published_css
    assert ".rc-date{ grid-column:1; grid-row:1;" in published_css
    assert (
        ".rc-rail .dot{ grid-column:2; grid-row:1; position:relative;"
        in published_css
    )
    assert html.count('<time class="rc-date" datetime="') == 7


def _price_source() -> str:
    return PRICE_TEMPLATE.read_text(encoding="utf-8")


def test_price_of_duration_is_registered_as_newest_bilingual_archive_entry() -> None:
    source = REGISTRY.read_text(encoding="utf-8")

    assert '"slug": "report_price_of_duration"' in source
    assert '"template": "report_price_of_duration.html.j2"' in source
    assert '"date": "2026-08-24"' in source
    assert '"title_en": "The Price of Duration"' in source
    assert '"title_zh": "久期的价格"' in source


def test_price_of_duration_has_ten_accessible_original_inline_svg_figures() -> None:
    source = _price_source()

    assert source.count('<figure class="pod-figure"') == 10
    for figure_id in PRICE_FIGURE_IDS:
        assert f'id="{figure_id}"' in source
    assert source.count('<svg ') == 10
    assert source.count('<title id="f') == 10
    assert source.count('<desc id="f') == 10
    assert "screenshot" not in source.lower()


def test_price_of_duration_toc_targets_every_article_anchor() -> None:
    source = _price_source()

    for anchor in PRICE_ANCHORS:
        assert f'href="#{anchor}"' in source
        assert f'id="{anchor}"' in source


def test_price_of_duration_bilingual_and_epistemic_contracts_survive() -> None:
    source = _price_source()

    assert source.count('class="l-en"') > 60
    assert source.count('class="l-zh"') > 60
    for label in ("[F]", "[C]", "[I]", "[S]"):
        assert label in source
    for probability in ("45%", "20%", "25%", "10%"):
        assert probability in source
    assert "Mastermind desk estimates — not statistical confidence intervals" in source


def test_price_of_duration_editorial_boundary_statements_are_explicit() -> None:
    source = _price_source()

    required = (
        "Treasury buybacks are not central-bank monetization.",
        "It does not require an explicit yield cap.",
        "The system has not broken.",
        "It is not a claim that foreign investors have abandoned Treasuries.",
        "Stablecoin bill demand is not equivalent to 30-year Treasury demand.",
        "Bitcoin remains economically separate from that collateral. It is not backed by Treasury bills.",
        "Those clocks are connected. They are not synchronized.",
        "Which Chinese balance sheet is connected to which capital cycle?",
    )
    for statement in required:
        assert statement in source


def test_price_of_duration_reduced_motion_forces_final_state() -> None:
    compact = re.sub(r"\s+", " ", _price_source())

    assert "@media(prefers-reduced-motion:reduce)" in compact
    assert "opacity:1 !important" in compact
    assert "transform:none !important" in compact
    assert "transition:none !important" in compact
    assert "stroke-dashoffset:0 !important" in compact
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in compact


def test_price_of_duration_snapshot_and_primary_sources_are_timestamped() -> None:
    source = _price_source()

    for value in ("5.23%", "4.69%", "2.35%", "2.34%", "98.974", "15.93", "2.75%", "10.35%", "$77,787.99"):
        assert value in source
    assert "August 24, 2026" in source
    assert "https://fred.stlouisfed.org/series/DGS30" in source
    assert "https://home.treasury.gov/news/press-releases/sb0607" in source
    assert "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm" in source
    assert "https://www.boj.or.jp/" in source


def test_price_of_duration_canonical_builder_emits_the_report() -> None:
    html = PRICE_PUBLISHED.read_text(encoding="utf-8")

    assert "The Price of Duration" in html
    assert "久期的价格" in html
    assert html.count('<figure class="pod-figure"') == 10
    assert 'id="fig-cockpit"' in html
    assert "report_price_of_duration.html" in PUBLISHED.read_text(encoding="utf-8")


def test_price_of_duration_generated_ids_and_internal_anchors_resolve() -> None:
    html = PRICE_PUBLISHED.read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    internal_hrefs = re.findall(r'href="#([^"]+)"', html)

    assert len(ids) == len(set(ids)), "duplicate DOM ids break TOC and SVG accessibility"
    assert internal_hrefs
    assert set(internal_hrefs).issubset(set(ids))
