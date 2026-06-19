"""China Mastermind GTAA flagship engine + pinned-hero render guards.

Mirrors tests/test_china_commodity_strategies.py. The engine tests run on the real china
price store when present (degrade-skip otherwise); the render test uses a synthetic
mastermind-card view-model so the pinned hero on china_strategies.html is Jinja-guarded,
and also asserts the two nav links were removed. DISPLAY-ONLY / experimental — priors-based
knobs, never a scored china axis.
"""
from __future__ import annotations

import pytest
from jinja2 import Environment, FileSystemLoader

from lib import config

_C = {"blue": "#285fff", "indigo": "#5b6bff", "ink": "#101828", "text": "#344054",
      "muted": "#667085", "faint": "#98a2b3", "red": "#e5484d", "amber": "#e0a106",
      "grid": "#e6e9ef", "card": "#ffffff", "bg": "#f7f8fa"}


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


def _scard():
    return {"key": "cn_credit_vol", "icon": "🪙", "href": "strategy_cn_credit_vol.html",
            "name_en": "X", "name_zh": "X", "thesis_en": "t", "thesis_zh": "t",
            "experimental": True, "cagr": 8.0, "hodl_cagr": 7.0, "sharpe": 0.7,
            "hodl_sharpe": 0.6, "maxdd": -20.0, "hodl_maxdd": -40.0, "income": 0.0,
            "years": 12, "stance_en": "a", "stance_zh": "a"}


def _mm_card(pk, accent, pos):
    return {"key": f"cnmm_{pk}", "href": f"strategy_cnmm_{pk}.html", "icon": "⚖️",
            "name_en": f"China Mastermind — {pk}", "name_zh": "中国操盘大师",
            "profile_en": pk.title(), "profile_zh": "均衡", "accent": accent, "riskpos": pos,
            "thesis_en": "t", "thesis_zh": "测", "cagr": 10.1, "hodl_cagr": 8.0,
            "sharpe": 1.16, "hodl_sharpe": 0.47, "maxdd": -11.6, "hodl_maxdd": -45.5,
            "sharpe_mult": 2.5, "bench_en": "CSI 300", "bench_zh": "沪深300",
            "gross_now": 0.68, "years": 12.9}


def test_pinned_hero_renders_and_nav_cleaned():
    cards = [_scard()]
    mm = [_mm_card("conservative", "#1FA971", 0.16), _mm_card("moderate", "#285fff", 0.5),
          _mm_card("aggressive", "#a855f7", 0.9)]
    html = _env().get_template("china_strategies.html.j2").render(
        cards=cards, masterminds=mm, built="now", C=_C)
    assert "China Mastermind Flagships" in html
    assert 'class="mm-hero"' in html and html.count('class="mm-card"') == 3
    for pk in ("conservative", "moderate", "aggressive"):
        assert f"strategy_cnmm_{pk}.html" in html
    # additive guard: no masterminds -> the hero markup is omitted (CSS stays)
    html0 = _env().get_template("china_strategies.html.j2").render(
        cards=cards, masterminds=[], built="now", C=_C)
    assert 'class="mm-hero"' not in html0
    # nav cleanup: the two removed submenu links must not reappear
    assert 'href="spvector.html">📐' not in html
    assert 'href="china_allocation.html">◎' not in html


def test_engine_three_profiles_long_only_and_levcap():
    from engine import china_masterminds as M
    P = M._prices()
    if P.empty:
        pytest.skip("china price store not present")
    for pk in ("conservative", "moderate", "aggressive"):
        res = M.backtest(pk, P)
        assert not res.get("error")
        W = res["weights"]
        assert (W.values >= -1e-9).all()                              # long-only
        assert float(W.abs().sum(axis=1).max()) <= M.PROFILES[pk]["max_lev"] + 0.05  # gross <= leverage cap
        assert res["gross_now"] <= M.PROFILES[pk]["max_lev"] + 0.05
        sc = res["scorecard"]
        assert sc.get("cagr") is not None and sc.get("sharpe") is not None
        assert sc.get("hodl_cagr") is not None                        # CSI 300 (or 40/60) benchmark spliced
    # risk ladder: vol target + leverage rise with risk
    assert (M.PROFILES["aggressive"]["target_vol"] > M.PROFILES["moderate"]["target_vol"]
            > M.PROFILES["conservative"]["target_vol"])
    assert M.PROFILES["conservative"]["max_lev"] == 1.0               # conservative is unlevered


def test_card_contract():
    from scripts.build_china_masterminds import china_mastermind_cards
    cards = china_mastermind_cards()
    if not cards:
        pytest.skip("china price store not present")
    assert len(cards) == 3
    req = {"key", "href", "icon", "name_en", "name_zh", "profile_en", "profile_zh", "accent",
           "riskpos", "thesis_en", "thesis_zh", "cagr", "hodl_cagr", "sharpe", "hodl_sharpe",
           "maxdd", "hodl_maxdd", "sharpe_mult", "bench_en", "bench_zh", "gross_now", "years"}
    for c in cards:
        assert req <= set(c), f"missing {req - set(c)}"
        assert c["href"].startswith("strategy_cnmm_")


def test_derisk_score_unit_range():
    from engine import china_masterminds as M
    P = M._prices()
    if P.empty:
        pytest.skip("china price store not present")
    d = M._derisk_score(P.index)
    if d is not None:
        dd = d.dropna()
        assert ((dd >= 0) & (dd <= 1)).all()


def test_detail_metadata_shapes():
    """The "how it works" explainer metadata that the flagship detail pages render."""
    from engine import china_masterminds as M
    # four conviction factors, weights match the engine's W_* and sum to 1
    assert len(M.FACTORS) == 4
    assert abs(sum(f["weight"] for f in M.FACTORS) - 1.0) < 1e-9
    keys = {f["key"]: f["weight"] for f in M.FACTORS}
    assert keys == {"regime": M.W_REGIME, "trend": M.W_TREND, "carry": M.W_CARRY, "xmom": M.W_XMOM}
    assert keys["regime"] == max(keys.values())          # regime is the largest weight in China
    for f in M.FACTORS:
        assert {"icon", "name_en", "name_zh", "tag_en", "tag_zh", "desc_en", "desc_zh",
                "src_en", "src_zh"} <= set(f)
    # six-asset Mainland universe
    assert sum(len(c["rows"]) for c in M.UNIVERSE) == 6
    for c in M.UNIVERSE:
        assert {"cls_en", "cls_zh", "icon", "rows"} <= set(c)
    # sizing pipeline + per-profile blurb/goal (bilingual)
    assert len(M.PIPELINE) == 6 and all({"icon", "en", "zh"} <= set(p) for p in M.PIPELINE)
    for pk in ("conservative", "moderate", "aggressive"):
        p = M.PROFILES[pk]
        assert {"blurb_en", "blurb_zh", "goal_en", "goal_zh"} <= set(p)


def test_regime_state_contract():
    """The live credit/vol/margin regime layer exposed to the detail page."""
    from engine import china_masterminds as M
    P = M._prices()
    if P.empty:
        pytest.skip("china price store not present")
    rs = M.regime_state(P)
    if rs is None:
        pytest.skip("no de-risk leg resolved locally")
    assert {"blended", "tilt", "pct", "state_en", "state_zh", "tone", "legs", "asof"} <= set(rs)
    assert 0.0 <= rs["blended"] <= 1.0 and 0 <= rs["pct"] <= 100
    assert -1.0 <= rs["tilt"] <= 1.0 and rs["tone"] in ("off", "mixed", "on")
    for lg in rs["legs"]:
        assert lg["key"] in M._DERISK_W and 0.0 <= lg["value"] <= 1.0
        assert lg["weight"] == M._DERISK_W[lg["key"]]
        assert {"name_en", "name_zh", "src_en", "src_zh", "desc_en", "desc_zh"} <= set(lg)


def test_detail_page_renders_rich_sections():
    """The cnmm detail page now renders the rich mastermind template (hero + explainer +
    live regime panel), bilingual, not the lean active_detail page."""
    from engine import china_masterminds as M
    from scripts import build_china_masterminds as B
    P = M._prices()
    if P.empty:
        pytest.skip("china price store not present")
    res = M.backtest("moderate", P)
    regime = M.regime_state(P)
    html = _env().get_template("mastermind_detail.html.j2").render(
        **B._detail_vm("moderate", res, "now", regime), C=_C)
    for needle in ("mm-stage", "How this strategy works", "four conviction factors",
                   "The investable universe", "From conviction to position", "risk dials"):
        assert needle in html, f"missing section: {needle}"
    # China-tailored explainer copy (not the US "nine assets" text)
    assert "Mainland-investible assets" in html and "nine assets across five classes" not in html
    assert "regime-led four-factor conviction" in html
    # bilingual: both language spans present for the China-specific copy
    assert "体制主导" in html and "境内可投" in html
    if regime:                                            # live regime panel when a leg resolves
        assert "Live regime layer" in html and 'class="rg-leg"' in html
        assert "Credit impulse" in html and "信用脉冲" in html
