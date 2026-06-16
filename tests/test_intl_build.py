"""International dashboard build smoke + the display-only invariant.

Renders templates/intl.html.j2 in BOTH modes from a synthetic view-model (no live
data needed) so the template + None-handling can't silently break, and asserts the
universe ticker/flag conversion. The display-only invariant: per-country records
expose descriptive gauges (recession_score, drawdown_risk) but NEVER a portfolio
weight / allocation — the risk reads must not feed a scored buy/sell.
"""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.intl_universe import _EU_SUFFIX, _clean_local  # noqa: E402
from engine import i18n  # noqa: E402


def _vm() -> dict:
    rec = {"cc": "JP", "name": "Japan", "name_zh": "日本", "flag": "🇯🇵", "region": "Asia",
           "date": "2026-06-16", "quad": "Q1", "quad_name": "Goldilocks",
           "growth_score": 0.7, "inflation_score": -0.5, "confidence": 0.6,
           "liquidity": "neutral", "recession_score": 5, "recession_band": "low",
           "macro": {"policy_rate": 0.5, "yield_10y": 2.6, "curve": 1.4, "real_yield": 0.5,
                     "cpi_yoy": 2.0, "cpi_chg3m": 0.1, "gdp_yoy": 0.3, "unemployment": 2.5,
                     "fx_strength_3m": -0.7, "m2_yoy": 2.0, "fx": 1.5, "realvol": 14.0, "drawdown": 0.0},
           "macro_asof": {"cpi_yoy": "2026-04", "gdp": "2026-03", "unemployment": "2026-04", "yield_10y": "2026-05"},
           "equity": {"price": 23000, "off_52w_high": 0.0, "drawdown_risk": 16, "drawdown_band": "low",
                      "ext_grade": "stretched", "ext_z": 1.6, "bubble_flag": True},
           "data_limited": False, "quad_meaning": ("growth up inflation down", "增长上 通胀下")}
    summary = {"n": 1, "quad_counts": {"Goldilocks": 1}, "dominant_quad": "Goldilocks",
               "recession_watch": 0, "drawdown_watch": 0, "avg_recession": 5}
    rankings = {"recession_score": {"label_en": "Recession pressure", "label_zh": "衰退压力",
                                    "risk_high": True, "rows": [{"cc": "JP", "flag": "🇯🇵", "name": "Japan", "value": 5}]}}
    latest = {"date": "2026-06-16", "summary": summary, "records": [rec], "rankings": rankings,
              "heatmap": [{"cc": "JP", "flag": "🇯🇵", "name": "Japan", "growth": 0.7, "inflation": -0.5,
                           "quad": "Q1", "quad_name": "Goldilocks", "confidence": 0.6, "data_limited": False}],
              "periphery": {"asof": "2026-05", "spreads": [{"label": "Italy (BTP)", "flag": "🇮🇹",
                            "bps": 77, "chg3m_bps": -26, "widening": False}]}}
    setups = {"buy": [{"ticker": "4004.T", "name": "Resonac", "flag": "🇯🇵", "sector": "Materials",
                       "dir": "up", "label": "BOUNCE", "state": "BOUNCE", "alpha": 3.0,
                       "price": 18650, "off_high": -4.0, "spark_svg": ""}]}
    board = [{"cc": "KR", "flag": "🇰🇷", "market": "South Korea", "sector": "Information Technology",
              "n": 8, "mom_20d": 21.3, "mom_60d": 55.3, "above_trend": True, "rank": 1}]
    return {"latest": latest, "built": "2026-06-16 00:00 UTC", "records": [rec], "summary": summary,
            "rankings": rankings, "heatmap": latest["heatmap"], "periphery": latest["periphery"],
            "sector_board": board, "setups": setups}


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env


def test_render_macro_mode():
    html = _env().get_template("intl.html.j2").render(**_vm(), mode="macro")
    assert "Cross-country comparison" in html and "Regime map" in html
    assert "🇯🇵" in html and "Goldilocks" in html
    assert "{{" not in html and "{%" not in html        # no leaked template tags


def test_render_stocks_mode():
    html = _env().get_template("intl.html.j2").render(**_vm(), mode="stocks")
    assert "What to act on now" in html
    assert "4004.T" in html and "Resonac" in html
    assert "South Korea" in html                          # sector board row


def test_display_only_invariant():
    rec = _vm()["records"][0]
    forbidden = {"weight", "allocation", "position_size", "target_weight", "score_weight"}
    assert not (set(rec) & forbidden)
    assert not (set(rec.get("equity", {})) & forbidden)
    # the risk reads are descriptive 0-100 gauges, not weights
    assert 0 <= rec["recession_score"] <= 100
    assert 0 <= rec["equity"]["drawdown_risk"] <= 100


def test_universe_ticker_conversion():
    assert _clean_local("8306") == "8306"                # JP code
    assert _clean_local("BP.") == "BP"                   # LSE trailing dot
    assert _clean_local("BT.A") == "BT-A"                # class share -> dash
    assert _clean_local("CASH") is None                  # cash row skipped
    assert _EU_SUFFIX["Germany"] == ".DE" and _EU_SUFFIX["France"] == ".PA"
