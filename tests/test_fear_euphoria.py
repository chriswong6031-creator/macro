"""Tests for the DISPLAY-ONLY Fear<->Euphoria synthesis panel
(scripts/build_site.py helpers + templates/dashboard.html.j2 section +
engine/i18n.py LEX). The load-bearing invariant: the synthesis is a conditioning
lens, NEVER a scored leg — nothing in axes / regime / macro_risk reads it. See
research/FEAR_EUPHORIA_PANEL_SPEC.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import i18n  # noqa: E402
from engine.conditions import conditions_frame  # noqa: E402
from scripts import build_site as bs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
RORO_LEG_KEYS = {"vix", "hy_oas", "skew", "vix_term", "nfci", "copper_gold", "dxy"}


def _frame(n: int = 1500) -> pd.DataFrame:
    """A long, fully-populated feature frame so the rolling-5y windows warm up
    and all 7 RORO legs are present. Sin-varying so z-scores have nonzero std."""
    idx = pd.bdate_range("2017-01-02", periods=n)
    r = np.arange(n, dtype=float)
    f = pd.DataFrame(index=idx)
    f["SPY"] = 400 + np.cumsum(np.sin(r / 9) * 0.4)
    f["vix"] = 16 + 3 * np.sin(r / 30)
    f["vix3m"] = 18 + 2 * np.sin(r / 30)
    f["skew"] = 130 + 8 * np.sin(r / 40)
    f["hy_oas"] = 3.5 + 0.4 * np.sin(r / 45)
    f["nfci"] = -0.4 + 0.1 * np.sin(r / 25)
    f["copper_gold"] = 0.18 + 0.01 * np.sin(r / 35)
    f["dxy"] = 103 + 2 * np.sin(r / 60)
    f["us10y"] = 4.0 + 0.3 * np.sin(r / 50)
    return f


# ---- 1. mapping monotonicity -------------------------------------------------
def test_fe_map_monotonic():
    assert bs._fe_map(0.0) == 0
    assert bs._fe_map(0.5) == 50
    assert bs._fe_map(1.0) == 100
    seq = [bs._fe_map(p) for p in np.linspace(0, 1, 21)]
    assert seq == sorted(seq)               # increasing pct -> non-decreasing fe


# ---- 2. NaN / short-history guard --------------------------------------------
def test_short_history_returns_none():
    latest = {"conditions": {"risk_appetite": {"roro": 0.1, "roro_state": "neutral"}},
              "dislocation": {"inputs": {"primary_trend": "up"}}}
    assert bs.fear_euphoria_synthesis(latest, _frame(80)) is None   # < min_periods


# ---- 3. clamp ----------------------------------------------------------------
def test_fe_map_clamps():
    assert bs._fe_map(1.4) == 100
    assert bs._fe_map(-0.3) == 0


# ---- 4. band cutoffs (half-open) ---------------------------------------------
@pytest.mark.parametrize("fe,band", [
    (0, "Panic"), (9, "Panic"), (10, "Fear"), (34, "Fear"), (35, "Neutral"),
    (64, "Neutral"), (65, "Greed"), (89, "Greed"), (90, "Euphoria"), (100, "Euphoria"),
])
def test_fe_band_cutoffs(fe, band):
    assert bs._fe_band(fe) == band


# ---- 5. leg shape ------------------------------------------------------------
def test_legs_shape():
    legs = bs._fe_legs(conditions_frame(_frame()))
    assert len(legs) == 7
    assert {leg["key"] for leg in legs} == RORO_LEG_KEYS
    for leg in legs:
        assert set(leg) == {"key", "name_en", "name_zh", "value", "pct", "lean"}
        assert 0 <= leg["pct"] <= 100
        assert leg["lean"] in {"risk-on", "risk-off"}     # hyphenated -> LEX


# ---- 6. lean sign ------------------------------------------------------------
def test_lean_sign():
    f = _frame()
    f.iloc[-40:, f.columns.get_loc("vix")] = 70.0          # VIX spike -> risk-off
    f.iloc[-40:, f.columns.get_loc("copper_gold")] = 0.30  # copper/gold up -> risk-on
    legs = {leg["key"]: leg for leg in bs._fe_legs(conditions_frame(f))}
    assert legs["vix"]["value"] < 0 and legs["vix"]["lean"] == "risk-off"
    assert legs["copper_gold"]["value"] > 0 and legs["copper_gold"]["lean"] == "risk-on"


# ---- 7. insider breadth ------------------------------------------------------
def test_insider_breadth():
    sig = {"A": {"bps": 5.0}, "B": {"bps": -2.0}, "C": {"bps": -1.0},
           "D": {"bps": None}, "E": {"bps": float("nan")}, "F": {}}
    # valid = A(+), B(-), C(-) -> (1 buyer - 2 sellers) / 3
    assert bs._fe_insider_breadth(sig) == pytest.approx((1 - 2) / 3)
    assert bs._fe_insider_breadth({"X": {"bps": None}, "Y": {}}) == 0.0
    assert bs._fe_insider_breadth({}) == 0.0


# ---- 8. divergence truth table -----------------------------------------------
@pytest.mark.parametrize("wash,crowd,buy,sell,up,chip,lean", [
    (True,  False, False, False, False, "diverges", "bullish"),
    (True,  False, False, False, True,  "confirms", "bullish"),
    (False, True,  False, True,  True,  "diverges", "bearish"),
    (False, True,  False, True,  False, "confirms", "bearish"),
    (True,  True,  False, False, True,  "mixed",    "mixed"),
    (False, False, True,  True,  True,  "mixed",    "mixed"),
])
def test_fe_chip(wash, crowd, buy, sell, up, chip, lean):
    assert bs._fe_chip(wash, crowd, buy, sell, up) == (chip, lean)


# ---- 9. display-only invariant (load-bearing) --------------------------------
@pytest.fixture(scope="module")
def real_f():
    from engine.inputs import build_features
    return build_features()


def test_not_scored_in_classify(real_f):
    from engine import regime
    cols = list(regime.classify(real_f).columns)
    assert "fear_euphoria" not in cols and "fe_score" not in cols
    assert not any("fear" in c or "fe_score" in c for c in cols)


def test_not_in_axes_scoring(real_f):
    from engine import axes
    for ax in ("growth", "inflation"):
        cols = list(axes.score_axis(real_f, ax).columns)
        assert "fear_euphoria" not in cols and "fe_score" not in cols
        assert not any("fear" in c for c in cols)


def test_synthesis_absent_from_scoring_sources():
    axes_src = (ROOT / "engine" / "axes.py").read_text()
    regime_src = (ROOT / "engine" / "regime.py").read_text()
    cond_src = (ROOT / "engine" / "conditions.py").read_text()
    mrs_region = cond_src[cond_src.index("def _macro_risk_legs"):]   # the MRS surface
    for src in (axes_src, regime_src, mrs_region):
        assert "fear_euphoria" not in src
        assert "fe_score" not in src
    # the synthesis helper is consumed by the site builder ONLY, never the engine
    for p in (ROOT / "engine").glob("*.py"):
        assert "fear_euphoria_synthesis" not in p.read_text(), p.name
    assert hasattr(bs, "fear_euphoria_synthesis")


# ---- 10/11. template render smoke + neutrality -------------------------------
def _render_fe(latest, fear_euphoria):
    from jinja2 import Environment, FileSystemLoader
    src = (TEMPLATES / "dashboard.html.j2").read_text()
    macros = src[: src.index("{# coloured")]            # the help() + t() macros
    start = src.index("<!-- ===== FEAR <-> EUPHORIA SYNTHESIS")
    end = src.index("<!-- ======================= ACTION BOARD")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env.from_string(macros + src[start:end]).render(
        latest=latest, fear_euphoria=fear_euphoria)


_LATEST_MIN = {
    "dislocation": {"verdict": "calm", "fed_put": True, "put_state": "put-present",
                    "capitulation_caveat": None,
                    "inputs": {"primary_trend": "up", "spy_drawdown_pct": -2.3}},
    "conditions": {"capitulation": {"score": 1, "signals_firing": [],
                                    "measured_bounce_pct": 4.5, "measured_hit_pct": 75}},
    "cross_asset": None,
}
_FE_MIN = {"fe_score": 12, "band": "Fear", "roro": 0.42, "roro_state": "risk-on",
           "legs": [{"key": "vix", "name_en": "VIX", "name_zh": "波动率 VIX",
                     "value": -0.5, "pct": 30, "lean": "risk-off"}],
           "positioning": {"chip": "mixed", "smart_money_lean": "mixed",
                           "cot_washed_out": False, "cot_crowded_long": False,
                           "insider_breadth": -0.64, "price_up": True}}


def test_render_smoke():
    html = _render_fe(_LATEST_MIN, _FE_MIN)
    assert 'id="fear-euphoria"' in html
    assert "Fear ↔ Euphoria: regime synthesis" in html      # title EN
    assert "恐惧 ↔ 欣喜：周期综合" in html                    # title ZH
    for en, zh in [("Panic", "恐慌"), ("Fear", "恐惧"), ("Neutral", "中性"),
                   ("Greed", "贪婪"), ("Euphoria", "欣喜")]:   # all 5 bands, both langs
        assert en in html and zh in html, en
    assert "positioning mixed" in html and "持仓信号混杂" in html   # chip, both langs


def test_render_building_when_none():
    html = _render_fe(_LATEST_MIN, None)
    assert 'id="fear-euphoria"' in html
    assert "Building…" in html and "构建中…" in html


def test_neutral_no_pos_neg():
    html = _render_fe(_LATEST_MIN, _FE_MIN)
    assert 'class="pos"' not in html       # euphoria is not "good", fear not "bad"
    assert 'class="neg"' not in html


# ---- 12. LEX completeness ----------------------------------------------------
def test_lex_completeness():
    for key in ["stand_aside", "buyable_washout", "put-present", "put-absent",
                "calm", "diversified", "converging", "concentrated",
                "risk-on", "risk-off", "unknown"]:
        zh = i18n.tr(key)
        assert zh != key, key                                   # not English fallback
        assert any("一" <= ch <= "鿿" for ch in zh), key  # contains Han
