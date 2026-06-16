"""Render-guards + math guards for the Strategy Scorecards feature.

Mirrors tests/test_canada_build.py: render each new template with a synthetic
view-model (the i18n globals the builder wires in, autoescape=True like the builder)
so Jinja breakage is caught before CI. Plus a no-network guard on the total-return
reconstruction (it reads the parquets already on disk; skipped if absent) and a
structural check on the strategy registry.
"""
from __future__ import annotations

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from lib import config, store

# minimal C palette the templates interpolate into :root
_C = {"blue": "#285fff", "indigo": "#5b6bff", "r2": "#9aa4b2", "r3": "#cfd4dc",
      "ink": "#101828", "text": "#344054", "muted": "#667085", "faint": "#98a2b3",
      "red": "#e5484d", "amber": "#e0a106", "grid": "#e6e9ef", "card": "#ffffff",
      "bg": "#f7f8fa"}


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


def _cards() -> list[dict]:
    return [
        {"key": "spvector", "icon": "📈", "href": "spvector.html",
         "name_en": "S&P / Macro Vector", "name_zh": "标普宏观向量",
         "thesis_en": "Stay-in / step-out.", "thesis_zh": "进出场。", "experimental": False,
         "cagr": 12.6, "hodl_cagr": 10.9, "sharpe": 0.88, "hodl_sharpe": 0.65,
         "maxdd": -36.5, "hodl_maxdd": -55.2, "income": 1.3, "years": 33.4,
         "stance_en": "100% S&P 500 · 0% T-bills", "stance_zh": "100% 标普500 · 0% 短债"},
        {"key": "credit_carry", "icon": "💳", "href": "strategy_credit_carry.html",
         "name_en": "Credit Carry", "name_zh": "信用套息",
         "thesis_en": "Harvest the high-yield carry.", "thesis_zh": "收割票息。", "experimental": True,
         "cagr": 4.3, "hodl_cagr": 4.95, "sharpe": 0.75, "hodl_sharpe": 0.5,
         "maxdd": -14.7, "hodl_maxdd": -34.2, "income": 6.0, "years": 19.2,
         "stance_en": "66% HY credit · 34% Treasuries", "stance_zh": "66% 高收益债 · 34% 国债"},
    ]


def _detail_vm() -> dict:
    return {
        "s": {"key": "credit_carry", "icon": "💳", "name_en": "Credit Carry", "name_zh": "信用套息",
              "thesis_en": "Harvest the high-yield carry.", "thesis_zh": "收割票息。",
              "bench_en": "High-yield credit (TR)", "bench_zh": "高收益信用债",
              "cash_en": "Treasuries", "cash_zh": "国债",
              "risk_word_en": "Credit stress", "risk_word_zh": "信用压力", "experimental": True,
              "caveat_en": "Experimental — under validation.", "caveat_zh": "实验性 — 验证中。"},
        "as_of": "Jun 15, 2026", "built": "2026-06-15 03:00 UTC", "income_now": 6.0,
        "risk_w": 66, "cash_w": 34, "score": 38, "band_label": "Watch — trim",
        "band_label_zh": "关注 — 减仓", "band_color": "#e0a106",
        "last_switch": {"date": "2026-05-01", "frm": 100, "to": 66},
        "legs": [{"label": "Credit stress (HY-OAS widening)", "label_zh": "信用压力", "value": 42.0,
                  "weight": 1.0, "lag": 3, "points": 18.0, "active": True, "color": "#e5484d"}],
        "sc": {"years": 19.2, "cagr": 4.3, "hodl_cagr": 4.95, "sharpe": 0.75, "hodl_sharpe": 0.5,
               "maxdd": -14.7, "hodl_maxdd": -34.2, "time_in_market": 99.3, "turnover_annual": 2.55,
               "sortino": 1.1, "hodl_sortino": 0.7},
        "at": {"after_tax_cagr": 3.1, "hodl_cagr": 4.0, "cumulative_tax_paid_x": 0.3},
        "dsr": {"dsr": 0.91, "n_trials": 8},
        "bands": [{"label": "Calm — fully invested", "label_zh": "平静", "rng": "< 25", "weight": 100, "cur": False},
                  {"label": "Watch — trim", "label_zh": "关注", "rng": "25–50", "weight": 66, "cur": True}],
        "episodes": [{"peak": "2008-05-01", "trough": "2008-12-01", "drawdown_pct": -34.2}],
        "charts": {"strategy": "<div id='chartA'>STRATCHART</div>",
                   "growth": "<div>GROWTHCHART</div>", "dd": "<div>DDCHART</div>"},
    }


def test_strategies_hub_renders():
    html = _env().get_template("strategies.html.j2").render(cards=_cards(), built="2026-06-15 03:00 UTC", C=_C)
    assert "Strategy Scorecards" in html
    assert "Credit Carry" in html and "Macro Vector" in html  # ('S&P' is autoescaped to 'S&amp;P')
    assert "strategy_credit_carry.html" in html          # card link wired
    assert "Experimental" in html                          # experimental chip on the new card
    assert "href=\"strategies.html\"" in html              # self nav entry present
    assert len(html) > 5000


def test_strategy_detail_renders():
    html = _env().get_template("strategy_detail.html.j2").render(**_detail_vm(), C=_C)
    assert "Credit Carry" in html
    assert "Backtest scorecard" in html
    assert "STRATCHART" in html and "GROWTHCHART" in html  # chart HTML passes |safe unescaped
    assert "Experimental" in html and "under validation" in html
    assert "Credit stress (HY-OAS widening)" in html       # leg breakdown row
    assert len(html) > 6000


def test_total_return_reconstruction():
    """No-network guard on the reconstruction (reads on-disk parquets; skip if absent).
    Each TR builder must be a positive, sorted index that starts at 100 (or, when the
    authoritative TR parquet lands, just a positive sorted series)."""
    if store.read("yahoo", "HYG") is None:
        pytest.skip("HYG parquet absent (data cache not populated)")
    from engine import total_return as tr
    for s in (tr.hy_tr(), tr.long_treasury_tr(), tr.treasury_tr()):
        assert isinstance(s, pd.Series) and len(s) > 200
        assert (s > 0).all()                                   # a valid total-return level
        assert s.index.is_monotonic_increasing and not s.index.has_duplicates
    # hy_tr / long_treasury_tr are the dividend/coupon-adjusted close (already total return,
    # NOT rebased); only the pure synthetic CMT index is rebased to 100.
    assert abs(float(tr.treasury_tr().iloc[0]) - 100.0) < 1e-6
    # the HY proxy plausibly compounds ~3-9%/yr (sanity, not double-counted carry)
    hy = tr.hy_tr(); cagr = (hy.iloc[-1] / hy.iloc[0]) ** (252 / len(hy)) - 1
    assert 0.0 < cagr < 0.12


def test_strategy_registry_structure():
    from engine import strategies as S
    keys = [s.key for s in S.STRATEGIES]
    # the original three lead the registry; the broader suite follows
    assert keys[:3] == ["spvector", "credit_carry", "duration_timing"]
    assert len(keys) == len(set(keys)), "strategy keys must be unique"
    assert len(S.STRATEGIES) >= 27, "the tactical suite should expose 24 additional strategies"
    for spec in S.STRATEGIES:
        assert callable(spec.benchmark) and callable(spec.alloc) and callable(spec.cash_yield)
        assert callable(spec.risk_yield) and callable(spec.score)
        assert spec.name_en and spec.name_zh and spec.thesis_en and spec.thesis_zh
        assert spec.bench_en and spec.cash_en and spec.risk_word_en
        assert len(spec.bands) == 3
    # only the validated vector is non-experimental; everything else is under validation
    assert S.by_key("spvector").experimental is False
    assert S.by_key("credit_carry").experimental is True
    assert S.by_key("duration_timing").own_page is None   # uses the generic detail page
    assert S.by_key("spvector").own_page == "spvector.html"
    # the suite keys are all experimental and use the generic detail page
    for k in ("nasdaq_trend", "btc_trend", "credit_gate_equity", "ig_carry"):
        assert S.by_key(k).experimental is True
        assert S.by_key(k).own_page is None
