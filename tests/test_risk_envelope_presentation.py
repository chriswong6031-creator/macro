"""Presentation contract for the compact Grey Deer Market Reads rail (Sol 2026-08-30).

Pins structure and live-overlay hooks. Does not weaken
tests/test_risk_envelope.py or tests/test_live_risk_envelope.py.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import jinja2
import pytest

from scripts.build_risk_envelope import build_sources
from engine.risk_envelope import compose_envelope

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DASHBOARD = TEMPLATES / "dashboard.html.j2"
BAND = TEMPLATES / "_risk_envelope_band.html.j2"
SITE_MACRO = ROOT / "site" / "macro.html"
GD1_FIXTURE = ROOT / "tests" / "fixtures" / "risk_envelope" / "gd1_dual_read_2026-08-18.json"


def _env() -> jinja2.Environment:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)))
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n  # noqa: PLC0415

    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _render_surfaces(envelope: dict) -> str:
    tmpl = (
        '{% import "_risk_envelope_band.html.j2" as gde %}'
        "{{ gde.gde_context(risk_envelope) }}"
    )
    return _env().from_string(tmpl).render(risk_envelope=envelope)


def _gd1_envelope() -> dict:
    raw = json.loads(GD1_FIXTURE.read_text(encoding="utf-8"))
    sources = build_sources(raw["market_state"], raw["leadership_crack"], raw["session"])
    return compose_envelope(
        sources=sources,
        market="US",
        source_session=raw["session"],
        observed_at="2026-08-19T00:00:00Z",
        produced_at="2026-08-19T00:00:00Z",
        as_of=raw["session"],
        revision="settled",
    )


def _count_id(html: str, elem_id: str) -> int:
    return len(re.findall(rf'\bid="{re.escape(elem_id)}"', html))


def _slice_id(html: str, elem_id: str) -> str:
    start = html.find(f'id="{elem_id}"')
    assert start != -1, f"missing #{elem_id}"
    open_lt = html.rfind("<", 0, start)
    tag = html[open_lt + 1 : html.find(" ", open_lt)]
    closer = f"</{tag}>"
    depth = 0
    i = open_lt
    while i < len(html):
        if html.startswith(f"<{tag}", i) and (html[i + 1 + len(tag) : i + 2 + len(tag)] in " >\n"):
            depth += 1
        elif html.startswith(closer, i):
            depth -= 1
            if depth == 0:
                return html[open_lt : i + len(closer)]
        i += 1
    raise AssertionError(f"unclosed #{elem_id}")


class _IdCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.append(v)


@pytest.fixture(scope="module")
def sample_html() -> str:
    return _render_surfaces(_gd1_envelope())


@pytest.fixture(scope="module")
def gd1_html() -> str:
    return _render_surfaces(_gd1_envelope())


@pytest.fixture(scope="module")
def dash_src() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_live_hooks_are_exactly_one_each(sample_html):
    for hook in (
        "risk-envelope-band",
        "gde-live-chip",
        "gde-pending-chip",
        "gde-live-receipt",
    ):
        assert _count_id(sample_html, hook) == 1, hook


def test_rail_keeps_bundle_identity(sample_html):
    rail = _slice_id(sample_html, "risk-envelope-band")
    env = _gd1_envelope()
    assert f'data-bundle-id="{env["bundle_id"]}"' in rail
    assert f'data-settled-session="{env["source_session"]}"' in rail


def test_l1_rail_is_not_the_old_standalone_panel(sample_html):
    rail = _slice_id(sample_html, "risk-envelope-band")
    assert "panel span12" not in rail
    assert "gde-band" not in rail
    assert 'class="gde-rail"' in rail or "gde-rail " in rail


def test_l1_has_no_lead_paragraph_or_inline_evidence(sample_html):
    rail = _slice_id(sample_html, "risk-envelope-band")
    assert not re.search(r"<p[\s>]", rail, flags=re.I)
    assert not re.search(r"<details[\s>]", rail, flags=re.I)
    assert "gde-lead" not in rail
    assert "Evidence —" not in rail
    assert "Each read keeps its own clock" not in rail


def test_l1_does_not_quote_the_hero_score(sample_html):
    rail = _slice_id(sample_html, "risk-envelope-band")
    assert "gde-quote" not in rail
    assert "/100" not in rail
    env = _gd1_envelope()
    score = env.get("measured_state", {}).get("score")
    if score is not None:
        assert f">{score}<" not in rail
        assert f" {score} " not in rail


def test_policy_is_outside_the_market_read_group():
    envelope = _gd1_envelope()
    envelope["policy_summary"]["policy_count"] = 1
    rail = _slice_id(_render_surfaces(envelope), "risk-envelope-band")
    reads = _slice_id(rail, "gde-rail-reads") if 'id="gde-rail-reads"' in rail else None
    if reads is None:
        m = re.search(r'<span class="gde-rail-reads[^"]*"[^>]*>', rail)
        assert m, "market-read grouping missing"
        start = m.start()
        reads = rail[start:]
        # cut at the structural separator / meta group
        cut = reads.find('class="gde-rail-rule"')
        if cut == -1:
            cut = reads.find('class="gde-rail-meta"')
        assert cut != -1
        reads = reads[:cut]
    assert "gde-seg-policy" not in reads
    assert "gde-seg-policy" in rail
    assert "active" in rail.lower() or "项生效" in rail


def test_hazard_null_is_unclear_with_source_caveat():
    env = _gd1_envelope()
    env["hazard_summary"].update(stage=None, unreadable_sources=["leadership_crack"])
    rail = _slice_id(_render_surfaces(env), "risk-envelope-band")
    assert "Unclear" in rail
    assert "No breakage" not in rail
    assert "Nothing breaking" not in rail
    unread = env.get("hazard_summary", {}).get("unreadable_sources") or []
    if unread:
        assert "source unavailable" in rail or "sources unavailable" in rail


def test_gd1_contradiction_keeps_separate_reads(gd1_html):
    rail = _slice_id(gd1_html, "risk-envelope-band")
    assert "Risk-on" in rail or "Risk-On" in rail
    assert "Fragile" in rail
    assert "is-split" in rail
    assert "/100" not in rail
    detail = _slice_id(gd1_html, "gde-detail")
    assert "Where they disagree" in detail or "分歧所在" in detail


def test_detail_and_receipt_live_in_l2_l3(sample_html):
    detail = _slice_id(sample_html, "gde-detail")
    assert "Market reads" in detail or "市场判读" in detail
    assert _count_id(detail, "gde-live-receipt") == 1
    assert "<details" in detail.lower()
    assert "Evidence" in detail
    rail = _slice_id(sample_html, "risk-envelope-band")
    assert 'id="gde-live-receipt"' not in rail


def test_rail_opens_public_native_disclosure(sample_html):
    context = _slice_id(sample_html, "gde-context-disclosure")
    rail = _slice_id(context, "risk-envelope-band")
    assert rail.startswith("<summary")
    assert "onclick=" not in rail and 'aria-haspopup="dialog"' not in rail
    assert 'id="gde-detail"' in context
    assert 'aria-controls="gde-detail"' in rail
    assert "Why" in rail and "说明" in rail


def test_dashboard_places_rail_inside_the_regime_hero(dash_src):
    hero_close = dash_src.index("</div>{# /#regime-radar panel #}")
    assert "gde.gde_context(" in dash_src[:hero_close]
    assert "gde.gde_context(" not in dash_src[hero_close:]
    old_include = dash_src.find('{% include "_risk_envelope_band.html.j2" %}')
    assert old_include == -1


def test_member_risk_dialog_is_not_the_public_context_destination(dash_src):
    at = dash_src.index('id="dlg-risk"')
    window = dash_src[at : at + 8000]
    assert "gde.gde_detail(" not in window
    assert 'id="gde-context-disclosure"' not in dash_src
    assert "Risk Detail" in window
    assert "Scare Ladder &amp; Sentiment" not in window


def test_css_hidden_overrides_live_chip_display():
    css = (TEMPLATES / "_risk_envelope_band.css.j2").read_text(encoding="utf-8")
    assert ".gde-stamp-live[hidden]" in css
    assert ".gde-pending[hidden]" in css
    assert ".gde-receipt-live[hidden]" in css
    assert "display: none !important" in css


def test_band_html_declares_no_literal_custom_properties():
    src = BAND.read_text(encoding="utf-8")
    assert 'style="--' not in src
    assert "gde-ms-RISK_ON" in src or "gde-ms-{{" in src
    assert "gde-hz-{{" in src


def test_generated_macro_smoke_allows_explicit_no_envelope():
    if not SITE_MACRO.is_file():
        pytest.skip("sparse checkout omits site/ (needs_full_checkout); fixture contracts still run")
    html = SITE_MACRO.read_text(encoding="utf-8")
    count = _count_id(html, "risk-envelope-band")
    assert count in (0, 1)
    for hook in ("gde-live-chip", "gde-pending-chip", "gde-live-receipt", "gde-context-disclosure", "gde-detail"):
        assert _count_id(html, hook) == count, hook
    if count:
        hero = _slice_id(html, "regime-radar")
        assert 'id="gde-context-disclosure"' in hero
        assert 'id="gde-detail"' not in _slice_id(html, "dlg-risk")
        assert _slice_id(html, "risk-envelope-band").startswith("<summary")


@pytest.mark.parametrize("verdict,en,zh", [
    ("RISK_OFF", "Risk-off", "风险规避"),
    ("MIXED", "Mixed", "分歧"),
    ("RISK_ON", "Risk-on", "风险偏好"),
])
def test_missing_optional_trend_labels_use_the_actual_verdict(verdict, en, zh):
    envelope = _gd1_envelope()
    envelope["measured_state"]["verdict"] = verdict
    for source in envelope["provenance"]["sources"]:
        if source["role"] == "measured_state":
            source["state"] = verdict
            source["detail"].pop("state_label_en", None)
            source["detail"].pop("state_label_zh", None)
    html = _render_surfaces(envelope)
    for surface in ("risk-envelope-band", "gde-detail"):
        fragment = _slice_id(html, surface)
        assert f'class="l-en">{en}</span>' in fragment
        assert f'class="l-zh">{zh}</span>' in fragment
    if verdict == "RISK_OFF":
        assert "while the broad trend remains positive" not in html
        assert "但整体趋势仍保持积极" not in html
    elif verdict == "RISK_ON":
        assert "while the broad trend remains positive" in html
        assert "但整体趋势仍保持积极" in html


@pytest.mark.parametrize("count", [None, False, True, -1, "0", 1.5])
def test_unknown_or_invalid_policy_count_is_not_zero(count):
    envelope = _gd1_envelope()
    envelope["policy_summary"]["policy_count"] = count
    html = _render_surfaces(envelope)
    detail = _slice_id(html, "gde-detail")
    assert "No Grey Deer policy active" not in detail
    assert "Policy status unavailable" in detail
    assert "政策状态不可用" in detail
    assert "gde-seg-policy" not in _slice_id(html, "risk-envelope-band")


def test_missing_policy_count_is_explicitly_unavailable():
    envelope = _gd1_envelope()
    envelope["policy_summary"].pop("policy_count", None)
    detail = _slice_id(_render_surfaces(envelope), "gde-detail")
    assert "Policy status unavailable" in detail
    assert "No Grey Deer policy active" not in detail


def test_zero_active_policy_does_not_take_homepage_space():
    envelope = _gd1_envelope()
    envelope["policy_summary"]["policy_count"] = 0
    html = _render_surfaces(envelope)
    assert "gde-seg-policy" not in _slice_id(html, "risk-envelope-band")
    assert "No Grey Deer policy active" in _slice_id(html, "gde-detail")


@pytest.mark.parametrize("count", [1, 3])
def test_active_policy_count_remains_visible_but_orthogonal(count):
    envelope = _gd1_envelope()
    envelope["policy_summary"]["policy_count"] = count
    html = _render_surfaces(envelope)
    rail = _slice_id(html, "risk-envelope-band")
    assert "gde-seg-policy" in rail
    assert "gde-seg-policy" not in _slice_id(rail, "gde-rail-reads")
    assert f'>{count} <span class="l-en">active</span>' in rail


def test_required_source_loss_is_unclear_without_daily_shape_skip():
    envelope = _gd1_envelope()
    envelope["hazard_summary"].update(
        stage=None, unreadable_sources=["leadership_crack"],
        unmapped_required_sources=[],
    )
    rail = _slice_id(_render_surfaces(envelope), "risk-envelope-band")
    assert "Unclear" in rail
    assert "1 source unavailable" in rail
    assert "No breakage" not in rail


def test_live_overlay_does_not_hide_the_settled_read_clock():
    css = (TEMPLATES / "_risk_envelope_band.css.j2").read_text(encoding="utf-8")
    # The live painter updates its status, not the underlying settled trend.
    assert not re.search(
        r"\.gde-rail:has\([^}]+\.gde-stamp-settled\s*\{\s*display:\s*none",
        css,
    )


def test_homepage_names_the_customer_job_not_the_internal_composer():
    rail = _slice_id(_render_surfaces(_gd1_envelope()), "risk-envelope-band")
    assert "Risk context" in rail
    assert "风险提示" in rail
    assert "Market Reads" not in rail


@pytest.mark.parametrize("envelope", [None, {}, {"schema": "unrecognized"}])
def test_absent_envelope_renders_no_public_disclosure(envelope):
    assert not _render_surfaces(envelope).strip()
    # The dashboard must not supply an unguarded, empty wrapper of its own.
    assert 'id="gde-context-disclosure"' not in DASHBOARD.read_text()


@pytest.mark.parametrize("stage", [None, "FRAGILE", "TRANSMITTING", "BREAKDOWN"])
def test_missing_hazard_source_is_visible_at_glance_and_detail(stage):
    envelope = _gd1_envelope()
    envelope["hazard_summary"].update(stage=stage, unreadable_sources=["missing_required"], unmapped_required_sources=[])
    envelope["data_state"] = "DEGRADED"
    html = _render_surfaces(envelope)
    for surface in ("risk-envelope-band", "gde-detail"):
        assert "1 source unavailable" in _slice_id(html, surface)


@pytest.mark.parametrize("state,en,zh", [("STALE", "Sources older", "来源较旧"), ("DEGRADED", "Limited coverage", "覆盖受限"), ("UNKNOWN", "Coverage unknown", "覆盖不明")])
def test_aggregate_source_caveat_is_visible_without_a_missing_count(state, en, zh):
    envelope = _gd1_envelope()
    envelope["data_state"] = state
    rail = _slice_id(_render_surfaces(envelope), "risk-envelope-band")
    assert en in rail and zh in rail


@pytest.mark.parametrize("coverage,en,zh", [("STALE", "Trend source older", "趋势来源较旧"), ("MISSING", "Trend source missing", "趋势来源缺失")])
def test_trend_source_health_is_visible_at_glance_and_detail(coverage, en, zh):
    envelope = _gd1_envelope()
    for source in envelope["provenance"]["sources"]:
        if source["role"] == "measured_state":
            source["coverage"] = coverage
    html = _render_surfaces(envelope)
    for surface in ("risk-envelope-band", "gde-detail"):
        fragment = _slice_id(html, surface)
        assert en in fragment and zh in fragment


def test_active_policy_explains_its_separate_meaning():
    envelope = _gd1_envelope()
    envelope["policy_summary"]["policy_count"] = 3
    detail = _slice_id(_render_surfaces(envelope), "gde-detail")
    assert "Policy is separate from the market readings" in detail
    assert "政策独立于市场判读" in detail
