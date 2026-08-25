"""Regression guards for the reports archive typography and timeline rail."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "reports.html.j2"
PUBLISHED = ROOT / "site" / "reports.html"
PRICE_TEMPLATE = ROOT / "templates" / "report_price_of_duration.html.j2"
PRICE_PUBLISHED = ROOT / "site" / "report_price_of_duration.html"
REGISTRY = ROOT / "scripts" / "build_reports.py"

PRICE_FIGURE_IDS = (
    "fig-quadrant",
    "fig-timeline",
    "fig-collision",
    "fig-reactions",
    "fig-stablecoin",
    "fig-ai-frontier",
    "fig-memory",
    "fig-triangle",
    "fig-regimes",
    "fig-cockpit",
)

PRICE_ANCHORS = (
    "market-changed",
    "model-repair",
    "duration-mechanism",
    "policy-trap-v2",
    "stablecoin-machine-v2",
    "ai-capital-efficiency",
    "global-market-map",
    "hard-assets",
    "four-futures",
    "change-our-mind",
    "road-2027",
    "next-act",
    "sources-v2",
)

PRICE_V2_SENTENCE_MARKERS = (
    "There are moments when markets stop behaving according to the story investors have been using to explain them.",
    "The United States is trying to finance two enormous projects at the same time.",
    "The critical word is <strong>short-dated</strong>.",
    "This is the transition from <strong>AI exposure</strong> to <strong>AI capital efficiency</strong>.",
    "Hong Kong and mainland China are different markets",
    "Bitcoin&rsquo;s liquidity clock outran the calendar",
    "These are <strong>Mastermind desk estimates</strong>, not statistically calibrated probabilities.",
    "The forward map should not be a fake smooth price path.",
    "The first AI trade rewarded conviction.",
)


class _VisibleReportParser(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, lang: str) -> None:
        super().__init__()
        self.lang = lang
        self.pod_depth = 0
        self.hidden_depth = 0
        self.stack: list[tuple[str, bool, bool]] = []
        self.text: list[str] = []
        self.figures: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class", "") or ""
        class_names = classes.split()
        opens_pod = tag == "article" and "pod" in class_names
        hidden = (self.lang == "en" and "l-zh" in class_names) or (
            self.lang == "zh" and "l-en" in class_names
        )
        if tag not in self._VOID:
            self.stack.append((tag, opens_pod, hidden))
        if opens_pod:
            self.pod_depth += 1
        if hidden:
            self.hidden_depth += 1
        if tag == "figure" and "pod-figure" in class_names and not self.hidden_depth:
            figure_id = dict(attrs).get("id")
            if figure_id:
                self.figures.append(figure_id)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        open_tag, opens_pod, hidden = self.stack.pop()
        assert open_tag == tag, f"malformed generated HTML near </{tag}> (opened <{open_tag}>)"
        if hidden:
            self.hidden_depth -= 1
        if opens_pod:
            self.pod_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.pod_depth and not self.hidden_depth:
            self.text.append(data)


def _visible_report_text(source: str, lang: str) -> str:
    parser = _VisibleReportParser(lang)
    parser.feed(source)
    return " ".join(parser.text)


def _visible_report_figures(source: str, lang: str) -> list[str]:
    parser = _VisibleReportParser(lang)
    parser.feed(source)
    return parser.figures


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


def _price_figure_source(figure_id: str) -> str:
    source = _price_source()
    start = source.index(f'id="{figure_id}"')
    end = source.index("</figure>", start)
    return source[start:end]


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
    assert source.count('<title id=') == 20
    assert source.count('<desc id=') == 20
    assert source.count('data-a11y-en=') == 10
    assert source.count('data-a11y-zh=') == 10
    assert source.count('aria-labelledby="timeline-title-en timeline-desc-en"') == 1
    assert "svg.setAttribute('aria-labelledby',labels)" in source
    assert "attributeFilter:['data-lang']" in source
    assert "screenshot" not in source.lower()


def test_price_of_duration_figures_are_direct_article_content_not_runtime_legacy_cargo() -> None:
    source = _price_source()
    published = PRICE_PUBLISHED.read_text(encoding="utf-8")
    shell = published.index('<div class="pod-v2-shell">')

    assert "pod-legacy" not in source
    assert "data-figure-slot" not in source
    assert "legacy.querySelectorAll" not in source
    for figure_id in PRICE_FIGURE_IDS:
        assert published.index(f'id="{figure_id}"') > shell


def test_price_of_duration_svg_language_markup_is_legal_and_independently_spaced() -> None:
    source = _price_source()
    svg_blocks = re.findall(r"<svg\b.*?</svg>", source, flags=re.DOTALL)

    assert len(svg_blocks) == 10
    for svg in svg_blocks:
        assert "<span" not in svg, "HTML span elements are invalid inside inline SVG"
        assert "{{ t(" not in svg, "the HTML bilingual macro must not be emitted inside SVG text"
        ET.fromstring(svg)
        assert svg.count('<title id=') == 2
        assert svg.count('<desc id=') == 2
        assert 'class="l-en"' in svg
        assert 'class="l-zh"' in svg
    assert not re.search(
        r'<tspan[^>]+dy="[1-9][^"]*"[^>]+class="l-en".*?'
        r'<tspan[^>]+dy="0"[^>]+class="l-zh"',
        source,
        flags=re.DOTALL,
    ), "Chinese line spacing must not depend on a hidden English tspan"


def test_price_of_duration_collision_circle_uses_bilingual_three_line_label_blocks() -> None:
    figure = _price_figure_source("fig-collision")
    svg = ET.fromstring(re.search(r"<svg\b.*?</svg>", figure, flags=re.DOTALL).group(0))
    label_blocks = [
        element
        for element in svg.iter()
        if element.tag.endswith("text")
        and "pod-collision-meta" in element.attrib.get("class", "").split()
    ]

    assert len(label_blocks) == 2
    assert {"l-en", "l-zh"} == {
        classes
        for element in label_blocks
        for classes in element.attrib.get("class", "").split()
        if classes in {"l-en", "l-zh"}
    }
    for block in label_blocks:
        rows = [child for child in block if child.tag.endswith("tspan")]
        assert len(rows) == 3
        assert [row.attrib.get("x") for row in rows] == ["410", "410", "410"]
        assert [row.attrib.get("y") for row in rows] == ["242", "257", "272"]
        assert all((row.text or "").strip() for row in rows)

    rows_by_language = {
        "l-en": [child.text for child in label_blocks[0] if child.tag.endswith("tspan")],
        "l-zh": [child.text for child in label_blocks[1] if child.tag.endswith("tspan")],
    }
    assert rows_by_language["l-en"] == [
        "pensions · insurers",
        "banks · FX reserves",
        "households",
    ]
    assert rows_by_language["l-zh"] == ["养老金 · 保险", "银行 · 外汇储备", "家庭"]
    assert '<tspan class="l-zh">全球久期</tspan>' in figure
    assert figure.count('<tspan class="l-zh">需求</tspan>') == 1


def test_price_of_duration_all_ten_figures_have_distinct_explanatory_motion() -> None:
    expected_scenes = {
        "fig-quadrant": ("sovereign-signal", "pod-motion-point"),
        "fig-timeline": ("collapsed-timeline", "pod-motion-collapse"),
        "fig-collision": ("capital-collision", "pod-motion-accumulator"),
        "fig-reactions": ("reaction-functions", "pod-motion-convergence"),
        "fig-stablecoin": ("stablecoin-machine", "pod-motion-machine"),
        "fig-ai-frontier": ("ai-frontier", "pod-motion-frontier"),
        "fig-memory": ("memory-clocks", "pod-motion-clock"),
        "fig-triangle": ("duration-triangle", "pod-motion-synapse"),
        "fig-regimes": ("regime-tree", "pod-motion-probability"),
        "fig-cockpit": ("six-gauge-cockpit", "pod-motion-gauge"),
    }

    for figure_id, (scene, motion_class) in expected_scenes.items():
        figure = _price_figure_source(figure_id)
        assert f'data-motion-scene="{scene}"' in figure
        assert motion_class in figure


def test_price_of_duration_motion_runtime_pauses_offscreen_and_in_hidden_tabs() -> None:
    source = _price_source()

    assert "is-motion-active" in source
    assert "var active=!reduced&&!motionPaused&&!document.hidden" in source
    assert "entry.target.setAttribute('data-motion-in-view',entry.isIntersecting?'true':'false')" in source
    assert "document.addEventListener('visibilitychange',syncMotionActivity)" in source
    assert "io.unobserve" not in source
    assert ".pod-figure[data-motion-scene]" in source


def test_price_of_duration_motion_has_user_pause_and_static_legacy_fallback() -> None:
    source = _price_source()

    assert 'id="pod-motion-toggle"' in source
    assert 'aria-pressed="false"' in source
    assert "motionPaused" in source
    assert "motionToggle.addEventListener('click'" in source
    assert "!motionPaused" in source
    no_observer = source.split("if(!('IntersectionObserver' in window)){", 1)[1].split(
        "var io=new IntersectionObserver", 1
    )[0]
    assert "data-motion-in-view','true'" not in no_observer
    assert "is-motion-active" not in no_observer
    assert "f.classList.add('is-visible')" in no_observer


def test_price_of_duration_flow_directions_preserve_causal_meaning() -> None:
    stablecoin = _price_figure_source("fig-stablecoin")
    cockpit = _price_figure_source("fig-cockpit")

    assert "M311 121 C311 139 334 145 350 153" in stablecoin
    assert "M755 121 C755 178 649 177 591 177" not in stablecoin
    assert 'd="M485 336 H557" marker-end="url(#f5r)"' in stablecoin
    for path in (
        "M254 173 L327 239",
        "M410 143 V197",
        "M566 173 L493 239",
        "M566 437 L493 371",
        "M410 467 V413",
        "M254 437 L327 371",
    ):
        assert path in cockpit


def test_price_of_duration_publishes_complete_editorial_v2_not_the_wave_one_shell() -> None:
    source = _price_source()

    for marker in PRICE_V2_SENTENCE_MARKERS:
        assert marker in source
    assert source.count("<h2 id=") >= 13
    assert source.count("<h3") >= 24
    assert source.count('<table class="pod-table') >= 7


def test_price_of_duration_has_no_reader_visible_build_or_review_scaffolding() -> None:
    source = _price_source()
    banned = (
        "Editorial V2 — Wave 1 composition shell",
        "Publication gate",
        "return to Sol",
        "numeric series held for publication refresh",
        "pending the publication-day series refresh",
        "Model repair",
        "OLD MAP · SEQUENTIAL",
        "The earlier map treated these stages as a line",
        "Opening diagnosis · anomaly before narrative",
        "Forecast accountability · mechanisms over dates",
        "Conclusion · which AI, which balance sheet, which regime",
        "Implementation component:",
        "The strongest part of the existing Claude/Fable report architecture",
        "the entire purpose of this rewrite",
        "KEY CHANGE FROM OUR OLD MAP",
    )

    for phrase in banned:
        assert phrase not in source


def test_price_of_duration_uses_reading_scale_type_and_explicit_light_art_direction() -> None:
    compact = re.sub(r"\s+", " ", _price_source())

    assert "--pod-body-size:18px" in compact
    assert "font-size:var(--pod-body-size)" in compact
    assert "@media (max-width:600px)" in compact
    assert "--pod-body-size:17px" in compact
    assert 'html[data-theme="light"] .pod {' in compact
    assert 'html[data-theme="light"] .pod .pod-figure' in compact
    assert 'html[data-theme="light"] .pod .pod-table' in compact
    assert 'html[data-lang="zh"] .pod .pod-figure' in compact


def test_price_of_duration_toc_targets_every_article_anchor() -> None:
    source = _price_source()

    for anchor in PRICE_ANCHORS:
        assert f'href="#{anchor}"' in source
        assert f'id="{anchor}"' in source


def test_price_of_duration_bilingual_and_epistemic_contracts_survive() -> None:
    source = _price_source()
    published = PRICE_PUBLISHED.read_text(encoding="utf-8")

    assert source.count('class="l-en"') > 60
    assert source.count('class="l-zh"') > 60
    assert len(re.findall(r"\b[A-Za-z]+(?:[-'][A-Za-z]+)*\b", _visible_report_text(published, "en"))) > 9_000
    assert len(re.findall(r"[\u3400-\u9fff]", _visible_report_text(published, "zh"))) > 15_000
    assert _visible_report_figures(published, "en") == list(PRICE_FIGURE_IDS)
    assert _visible_report_figures(published, "zh") == list(PRICE_FIGURE_IDS)
    assert " / Mastermind 研究台估计" not in published
    for label in ("[F]", "[C]", "[I]", "[S]"):
        assert label in source
    for probability in ("45%", "20%", "25%", "10%"):
        assert probability in source
    assert "Mastermind desk estimates — not statistical confidence intervals" in source


def test_price_of_duration_article_sections_have_structural_bilingual_parity() -> None:
    source = _price_source()

    for anchor in PRICE_ANCHORS[:-1]:
        start = source.index(f'<h2 id="{anchor}"')
        next_h2 = source.find('<h2 ', start + 4)
        section = source[start:] if next_h2 == -1 else source[start:next_h2]
        assert '<div class="l-en pod-lang-section">' in section
        assert '<div class="l-zh pod-lang-section">' in section

    # These markers guard the arguments that the previous condensed Chinese layer
    # omitted or compressed most aggressively.
    for marker in (
        "每多投入一美元 AI 资本，究竟能创造多少持久现金流",
        "AI 期权性被过早提升成了 AI 证据",
        "事件闸门时间线",
        "秋季是压力窗口，不是保证投降的日期",
        "储备货币持有人会要求什么价格",
        "哪一张中国资产负债表",
    ):
        assert marker in source


def test_price_of_duration_mobile_dense_content_scrolls_locally_not_at_page_level() -> None:
    compact = re.sub(r"\s+", " ", _price_source())

    assert ".pod .pod-table-wrap { overflow-x:auto;" in compact
    assert ".pod .pod-figure { overflow-x:auto;" in compact
    assert ".pod .pod-figure svg { min-width:820px;" in compact
    assert ".pod .pod-figure-head, .pod .pod-figure figcaption { min-width:0;" in compact


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
    assert '.pod .pod-figure [class*="pod-motion-"]' in compact
    assert "opacity:1 !important" in compact
    assert "transform:none !important" in compact
    assert "transition:none !important" in compact
    assert "animation:none !important" in compact
    assert "stroke-dashoffset:0 !important" in compact
    assert ".pod .pod-motion-flow { display:none !important; }" in compact
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in compact


def test_price_of_duration_language_labels_do_not_override_language_visibility() -> None:
    source = _price_source()

    assert source.count('<div class="stat"') == 5
    assert source.count('class="sk"') == 5
    assert source.count('class="sl"') == 5
    assert source.count('class="pod-proof-chip"') >= 4
    assert ".pod .stat span" not in source
    assert ".pod .pod-gauge span" not in source
    assert ".pod .pod-proof-key span" not in source
    assert ".pod .pod-proof-chip" in source


def test_price_of_duration_figures_are_visible_without_animation_javascript() -> None:
    compact = re.sub(r"\s+", " ", _price_source())

    assert ".pod .pod-reveal { opacity:1; transform:none;" in compact
    assert ".pod .pod-draw { stroke-dasharray:760; stroke-dashoffset:0;" in compact
    assert ".pod .pod-figure.pod-motion-pending .pod-reveal { opacity:0;" in compact
    assert "f.classList.add('pod-motion-pending')" in compact
    assert "f.classList.remove('pod-motion-pending')" in compact
    assert "f.classList.add('is-visible')" in compact
    assert "},4000)" in compact


def test_price_of_duration_snapshot_and_primary_sources_are_timestamped() -> None:
    source = _price_source()

    for value in ("5.27%", "4.74%", "2.40%", "2.32%", "98.974", "15.93", "2.70%", "10.37%", "$78,710"):
        assert value in source
    assert "August 24, 2026" in source
    assert "https://fred.stlouisfed.org/series/DGS30" in source
    assert "https://home.treasury.gov/news/press-releases/sb0607" in source
    assert "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm" in source
    assert "https://www.boj.or.jp/" in source
    assert "No comparable aggregate" in source
    assert "AI debt supply is materially larger" not in source
    assert "no comparable aggregate AI-debt total is presented" in source
    assert "Yahoo Finance public tape · DX-Y.NYB / ^VIX" in source
    assert "Yahoo Finance futures tape · GC=F / SI=F" in source
    assert "Yahoo Finance public spot tape · BTC-USD" in source
    assert "https://www.ice.com/forex/usdx" in source
    assert "https://www.cboe.com/tradable-products/vix" in source
    assert "https://www.cmegroup.com/markets/metals/precious.html" in source
    assert "https://www.cmegroup.com/markets/metals/base.html" in source


def test_price_of_duration_reader_figure_numbers_follow_article_order() -> None:
    html = PRICE_PUBLISHED.read_text(encoding="utf-8")
    positions = [html.index(f'id="{figure_id}"') for figure_id in PRICE_FIGURE_IDS]

    assert positions == sorted(positions)
    for number, figure_id in enumerate(PRICE_FIGURE_IDS, start=1):
        start = html.index(f'id="{figure_id}"')
        end = html.index('</figure>', start)
        assert f"Figure {number} ·" in html[start:end]


def test_price_of_duration_overrides_inaccurate_generic_method_disclaimer() -> None:
    source = _price_source()
    published = PRICE_PUBLISHED.read_text(encoding="utf-8")

    assert ".pod + .disc { display:none; }" in source
    assert "point-in-time research built from the primary and named market-data sources" in source
    assert "pod-disc" in published


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
