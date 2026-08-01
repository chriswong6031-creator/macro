"""Render smoke tests for the 2026 Markets-News revamp (news.html.j2).

The page is a hero-led, importance-ranked, aged single feed (build_site builds the
unified `news_feed`; the template renders it). These tests pin the SHIPPED design's
invariants and the critical house-law guards:
  • renders with a full vm and with an all-empty vm (null-safety)
  • schema-violating side-artifacts degrade, never raise
  • no translated text inside a title= attribute (CI i18n guard)
  • internal scorer strings never surface; reason slugs are de-underscored
  • the AI chip appears ONLY when a real ai_importance is present (Undefined guard)
  • the build_site render-call shape (no duplicate macro_news kwarg) holds
  • bilingual l-en/l-zh spans are emitted

Mirrors scripts/build_site.py's Jinja env (autoescape=False, same loader).
"""
from __future__ import annotations

from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _feed_item(title="Fed holds rates steady", lane="fed", theme="monetary",
               rank=60.0, tickers=None, event=None, ai_importance=None,
               sentiment=None, seendate="2026-07-22T10:00:00Z") -> dict:
    return {
        "title": title, "title_zh": "美联储维持利率不变",
        "url": "https://reuters.com/x", "domain": "reuters.com",
        "source_name": "Reuters", "source_tier": "tier1",
        "seendate": seendate, "theme": theme, "lane": lane,
        "rank_score": rank, "tickers": tickers or [], "event": event,
        "ai_importance": ai_importance, "ai_sentiment": sentiment,
        "novelty_z": 1.8, "echo": {"n_sources": 3},
    }


def _full_vm() -> dict:
    feed = [
        _feed_item("RTX beats Q2, raises FY guidance", "companies", "earnings", 74.0,
                   ["RTX"], {"event_type": "guidance_raise", "direction": "bullish"}),
        _feed_item("Fed officials signal patience on cuts", "fed", "monetary", 62.0),
        _feed_item("Tesla slumps as AI-spend concerns weigh", "companies", "stocks", 55.0,
                   ["TSLA"], {"event_type": "rating_change", "direction": "bearish"}),
        _feed_item("Payrolls cool at the margin", "macro", "labor", 48.0),
        _feed_item("Broad market drifts lower", "markets", "macro", 40.0),
    ]
    return dict(
        news_feed=feed,
        latest={"date": "2026-07-22", "conditions": {"risk_appetite": {
            "news_sentiment_state": "optimistic", "news_sentiment_z": 0.7}}},
        macro_news={
            "headlines": [f for f in feed if f["lane"] in ("fed", "macro", "markets")],
            "synthesis": {"top_tickers": ["RTX", "TSLA"], "top_channels": []},
            "fetched_at": "2026-07-22T06:00:00Z",
        },
        macro_news_disclaimer="News is display-only context and never feeds a signal.",
        macro_news_disclaimer_zh="新闻仅为展示性背景，绝不构成信号。",
        macro_catalysts=[{"date": "2026-07-30", "time_et": "2:00pm",
                          "label": "FOMC decision", "label_zh": "FOMC决议"}],
        event_strip=[{"dow": "Thu", "md": "Jul 24", "label": "Jobless claims",
                      "label_zh": "初请失业金"}],
        prediction_markets={"events": [{"label_en": "July FOMC", "label_zh": "7月FOMC",
                             "outcomes": [{"outcome": "Hold", "prob": 82}]}]},
        macro_releases={"cards": [{
            "display_name": "Nonfarm Payrolls", "release": "nonfarm_payrolls",
            "actual": 147000.0, "prior": 139000.0, "prior_label": "vs prior",
            "period": "Jun 2026", "surprise_size": "notable", "direction_tag": "bullish",
            "summary": "Payrolls above prior."}]},
        news_rejected={"feeds": {"macro": [
            {"title": "10 stocks to buy this week", "domain": "fool.com",
             "reason": "stock_pick_roundup"}]}},
        news_calibration={"classes": [
            {"event_type": "earnings_result", "n": 14, "verdict": "accruing"}]},
        financial_news={"providers": {"polygon": True}, "market": []},
    )


def _empty_vm() -> dict:
    return dict(
        news_feed=[], latest={"date": "2026-07-22", "conditions": None},
        macro_news=None, macro_news_disclaimer="", macro_news_disclaimer_zh="",
        macro_catalysts=[], event_strip=[], prediction_markets=None,
        macro_releases=None, news_rejected=None, news_calibration=None,
        financial_news=None,
    )


def _render_full() -> str:
    return _env().get_template("news.html.j2").render(**_full_vm())


def _render_empty() -> str:
    return _env().get_template("news.html.j2").render(**_empty_vm())


# --------------------------------------------------------------------------- #
# render / structure
# --------------------------------------------------------------------------- #
def test_full_vm_renders_without_exception():
    html = _render_full()
    assert len(html) > 1000
    assert "What matters now" in html


def test_empty_vm_renders_without_exception():
    html = _render_empty()
    assert len(html) > 500
    assert "What matters now" in html          # header always renders
    assert "quiet" in html.lower()             # empty-feed state


def test_hero_lead_story_renders():
    html = _render_full()
    assert "nx-lead" in html and "nx-impact" in html
    assert "RTX beats Q2" in html              # top-ranked story leads the hero
    assert "Top story" in html or "头条" in html


def test_impact_ring_content_is_compact_and_centered():
    """The score stays self-contained and gives mobile headlines full width.

    Without this guard they inherit the page's 1.6 line-height, spreading the
    two rows into the ring edge. On mobile the ring belongs in the eyebrow row,
    rather than reserving scarce horizontal space beside the lead headline.
    """
    html = _render_full()
    assert "flex-direction:column; align-items:center; justify-content:center" in html
    assert "overflow:hidden;" in html
    assert ".nx-impact b{ position:relative; font-size:17px; font-weight:800; line-height:1;" in html
    assert "font-size:8px; line-height:1; letter-spacing:.06em; text-align:center;" in html
    assert 'grid-template-areas:"eyebrow impact" "body body"' in html
    assert ".nx-lead-row{ display:contents; }" in html
    assert ".nx-lead-title{ overflow-wrap:anywhere; }" in html


def test_feed_renders_ranked_story_cards():
    html = _render_full()
    assert html.count("nx-story") >= 5         # one card per feed item
    assert "nx-rankdot" in html                # per-card impact number


def test_lane_and_search_data_attributes_present():
    """The lane filter + search read data-lane / data-search — the previously-dead
    data-search attribute is now wired."""
    html = _render_full()
    assert 'data-lane="fed"' in html and 'data-lane="companies"' in html
    assert "data-search=" in html
    assert 'id="nxSeg"' in html and 'id="nxSearch"' in html


def test_release_board_renders():
    html = _render_full()
    assert "Nonfarm Payrolls" in html
    assert "147" in html


def test_calendar_renders_catalysts_and_strip():
    html = _render_full()
    assert "FOMC decision" in html or "FOMC决议" in html
    assert "Jobless claims" in html or "初请失业金" in html


def test_diagnostics_collapsed_and_relocated():
    """Reject log + calibration live in ONE collapsed drawer, not as prominent boards."""
    html = _render_full()
    assert '<details class="nx-diag">' in html        # a collapsed <details> drawer
    assert "Newsroom diagnostics" in html or "新闻室诊断" in html


# --------------------------------------------------------------------------- #
# house-law guards
# --------------------------------------------------------------------------- #
def test_no_translated_title_attrs():
    """No translated (CJK) text inside a title= attribute (check_title_i18n guard)."""
    import re
    html = _render_full()
    for t_val in re.findall(r'title=["\']([^"\']+)["\']', html):
        assert not any('一' <= c <= '鿿' for c in t_val), \
            f"Translated text in title= attribute: {t_val!r}"


def test_no_span_leak_in_placeholder():
    """The search placeholder must be a plain string, not a t() span pair."""
    import re
    html = _render_full()
    ph = re.search(r'placeholder="([^"]*)"', html)
    assert ph and "<span" not in ph.group(1), "t() must never populate an attribute"


def test_importance_reasons_and_internal_slugs_never_render():
    html = _render_full()
    assert "importance_reasons" not in html
    assert "intelligence_score" not in html    # internal scorer keys never surface as text
    # reject reason is de-underscored, never the raw slug
    assert "stock_pick_roundup" not in html


def test_ai_chip_only_when_ai_importance_present():
    """Regression guard for the Jinja Undefined bug: a missing ai_importance key
    (Undefined) must NOT render the AI chip. Chip appears only for a real value."""
    html = _render_full()
    assert "nx-chip ai" not in html            # fixture items have ai_importance=None
    # now add a real AI score → chip appears
    vm = _full_vm()
    vm["news_feed"][0]["ai_importance"] = 92.0
    html2 = _env().get_template("news.html.j2").render(**vm)
    assert "nx-chip ai" in html2


def test_bilingual_spans_present():
    html = _render_full()
    assert 'class="l-en"' in html and 'class="l-zh"' in html
    assert "当下要闻" in html                    # zh title span emitted


def test_disclaimer_renders():
    html = _render_full()
    assert "display-only" in html.lower()


# --------------------------------------------------------------------------- #
# degrade-safety — schema-violating side-artifacts must not raise
# --------------------------------------------------------------------------- #
_BAD_ARTIFACT_CASES = [
    ("calibration_is_list", {"news_calibration": [1, 2, 3]}),
    ("calibration_classes_str", {"news_calibration": {"classes": "x"}}),
    ("releases_cards_str", {"macro_releases": {"cards": "x"}}),
    ("releases_is_list", {"macro_releases": [1, 2]}),
    ("cards_of_strings", {"macro_releases": {"cards": ["a", "b"]}}),
    ("rejected_is_list", {"news_rejected": [1, 2]}),
    ("rejected_feeds_str", {"news_rejected": {"feeds": "x"}}),
    ("rejected_items_str", {"news_rejected": {"feeds": {"macro": "xy"}}}),
    ("news_feed_str", {"news_feed": "not-a-list"}),
    ("news_feed_items_bad", {"news_feed": [1, "x", None]}),
]


@pytest.mark.parametrize("case_id,overrides", _BAD_ARTIFACT_CASES,
                         ids=[c[0] for c in _BAD_ARTIFACT_CASES])
def test_schema_violating_artifact_degrades_not_raises(case_id, overrides):
    vm = _empty_vm()
    vm.update(overrides)
    html = _env().get_template("news.html.j2").render(**vm)
    assert len(html) > 500
    assert "What matters now" in html          # page structure intact


def test_string_cards_release_board_shows_no_release_section():
    """cards-as-string degrades the release board out (empty), never raises."""
    vm = _empty_vm()
    vm["macro_releases"] = {"cards": "x"}
    html = _env().get_template("news.html.j2").render(**vm)
    assert "Nonfarm Payrolls" not in html      # nothing bogus rendered
    assert len(html) > 500


# --------------------------------------------------------------------------- #
# build_site render-call shape — no duplicate macro_news kwarg (with news_feed)
# --------------------------------------------------------------------------- #
# build_site.py's vm carries 'macro_news'; macro_releases/news_rejected/
# news_calibration/financial_news/news_feed are separate locals passed explicitly.
_EXPLICIT_KWARGS = ("macro_releases", "news_rejected", "news_calibration",
                    "financial_news", "news_feed")


def test_build_site_render_call_shape_no_duplicate_kwarg():
    vm = {k: v for k, v in _full_vm().items() if k not in _EXPLICIT_KWARGS}
    assert "macro_news" in vm
    render_vm = {k: v for k, v in vm.items() if k != "macro_news"}   # the W3 fix
    html = _env().get_template("news.html.j2").render(
        **render_vm,
        macro_news=dict(vm["macro_news"]),
        macro_releases=None, news_rejected=None, news_calibration=None,
        financial_news=None, news_feed=_full_vm()["news_feed"],
    )
    assert len(html) > 1000
    assert "nx-story" in html


def test_naive_duplicate_macro_news_kwarg_raises_typeerror():
    """Pins the failure mode if build_site regresses to **vm without dropping macro_news."""
    vm = {k: v for k, v in _full_vm().items() if k not in _EXPLICIT_KWARGS}
    tmpl = _env().get_template("news.html.j2")
    with pytest.raises(TypeError, match="multiple values for keyword argument 'macro_news'"):
        tmpl.render(**vm, macro_news=dict(vm["macro_news"]),
                    macro_releases=None, news_rejected=None, news_calibration=None,
                    financial_news=None, news_feed=[])
