"""Regression tests for the US action-board hover-card redesign."""
from __future__ import annotations

from pathlib import Path

from tests.test_dashboard_template_render import _base_vm, _env


ROOT = Path(__file__).resolve().parents[1]


def _sector() -> dict:
    return {
        "kind": "sector",
        "name": "Health Care",
        "ticker": "XLV",
        "href": "basket/us_sector_health.html",
        "label": "BOTTOMING",
        "age_short": "3d ago",
        "age_short_zh": "3天前",
        "eq_badge": "▲ +56",
        "eq_dir": "up",
        "eq_tip": "LONG ENTRY EXPLANATION THAT MUST NEVER REACH THE HOVER CARD",
        "rs_60d": 13.5,
        "dc_day": 27,
        "buy_zone": 14,
        "n_holdings": 20,
        "rsi_3d": 67,
        "stoch_3d": 83,
        "rate_str": "-0.0% vs SPY · 50% up · n=2200",
        "rate_pos": False,
        "season_str": "+1.3% (64%)",
        "text": "LONG MODEL COMMENTARY THAT MUST NEVER REACH THE HOVER CARD",
        "text_zh": "冗长模型说明",
        "stat_en": "clean entry · 3d ago",
        "stat_zh": "干净入场 · 3天前",
    }


def _theme() -> dict:
    return {
        "kind": "theme",
        "name": "Payments & Fintech",
        "name_zh": "支付与金融科技",
        "slug": "payments_fintech",
        "href": "basket/payments_fintech.html",
        "reco": "accumulate",
        "label": "ACCUMULATE",
        "label_zh": "积累",
        "score": 62,
        "book_wt": None,
        "perf_20d_rel": 0.042,
        "breadth_pct50": 0.75,
        "rs_pctile": 0.44,
        "flip_distance": 4.2,
        "rollover_band": "low",
        "rollover_band_zh": "低",
        "top_members": ["PYPL", "GPN", "FIS", "FOUR"],
        "validated": False,
        "reco_why_en": "LONG THEME EXPLANATION THAT MUST NEVER REACH THE HOVER CARD",
        "reco_why_zh": "冗长主题说明",
    }


def _render() -> str:
    vm = _base_vm()
    vm["action_board"] = {
        "buy_now": [_sector()],
        "buy_soon": [_theme()],
        "on_the_run": [],
        "take_profits": [],
        "hold": [],
        "avoid": [],
        "notable": [],
        "buy": [],
        "more": {},
    }
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _row_payload(html: str, href: str) -> str:
    start = html.index(f'href="{href}"')
    return html[start:html.index("</a>", start)]


def test_sector_hover_card_is_short_and_decision_focused():
    payload = _row_payload(_render(), "basket/us_sector_health.html")
    assert '<div class="rp-src row-pop-decision" hidden>' in payload
    assert "Sector pulse" in payload and "Early turn" in payload
    assert "+13.5%" in payload and "▲ +56" in payload and "14/20" in payload
    assert "RSI" in payload and "STO" in payload
    assert "What matters" in payload
    assert "LONG ENTRY EXPLANATION" not in payload
    assert "LONG MODEL COMMENTARY" not in payload
    assert "Fwd 63d base rate" not in payload
    assert "Seasonality" not in payload


def test_theme_hover_card_prioritizes_score_breadth_risk_and_leaders():
    payload = _row_payload(_render(), "basket/payments_fintech.html")
    assert "Theme basket" in payload and "Broad and leading" in payload
    assert "row-pop-score-ring up" in payload and "--score:62" in payload
    assert "+4.2%" in payload and "75%" in payload and ">Low<" in payload
    assert "PYPL · GPN · FIS" in payload
    assert "LONG THEME EXPLANATION" not in payload
    assert "Flip distance" not in payload
    assert "RS percentile" not in payload


def test_decision_card_shell_is_viewport_safe_and_uses_dedicated_variant():
    """The card shell now lives in the shared partial, not page-local on the US board.

    Before 2026-08-02 this CSS sat inline in dashboard.html.j2 and China / HK
    rendered an unrelated label:value grid; Canada rendered no hover at all. The
    shell moved to templates/_decision_card.html.j2 so all four boards render one
    component — so this test pins the partial AND its four consumers, which a
    dashboard-only assertion could never catch drifting apart.
    """
    css = (ROOT / "templates" / "_decision_card.html.j2").read_text(encoding="utf-8")
    assert '<style id="decision-card-css">' in css
    assert ".row-pop:has(> .row-pop-decision){" in css
    assert "max-height:calc(100dvh - 20px)" in css
    assert "grid-template-columns:repeat(auto-fit,minmax(82px,1fr))" in css
    assert "z-index:2147483001" in css
    for page in ("dashboard.html.j2", "china.html.j2", "hk.html.j2", "canada.html.j2"):
        src = (ROOT / "templates" / page).read_text(encoding="utf-8")
        assert '{% import "_decision_card.html.j2" as dc %}' in src, f"{page} does not import the shared card"
        assert "dc.dc_css()" in src, f"{page} never emits the shared card CSS"
        assert "dc.dc_card(" in src, f"{page} never renders the shared card"


def test_score_caption_sits_outside_the_ring():
    """The score caption must not live inside the conic disc.

    A 7.5px label centred in the 62px disc rendered fine at the authored size and
    ran straight through the ring stroke for any reader whose browser enforces a
    minimum font size (12-16px is a common accessibility setting) — the label's
    width is set by the clamped font, not by the design. Keeping the caption a
    SIBLING of the disc makes the collision impossible at any font size.
    """
    css = (ROOT / "templates" / "_decision_card.html.j2").read_text(encoding="utf-8")
    ring = css[css.index(".row-pop-score-ring{"):css.index(".row-pop-trust{")]
    assert "row-pop-score-cap" in css, "score caption class missing"
    assert ".row-pop-score-ring small" not in ring, (
        "caption is back inside the ring — a clamped font size will cross the stroke"
    )
    assert ".row-pop-score{" in css, "ring/caption wrapper missing"
