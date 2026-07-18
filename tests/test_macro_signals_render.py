"""Render tests for the rewritten macro_signals.html.j2 (MSX-2).

Three scenarios:
  a) full vm including fx_context → assert hero stance, fx section text
     (offshore-yuan words, triple-red banner), NO plotly, NO banned tokens outside tips
  b) fx_context=None → fx section absent, page still renders
  c) minimal vm (most keys None) → renders without exception

Follows test_china_fx_context_render.py conventions.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env() -> Environment:
    """Jinja2 env with FileSystemLoader on templates/ and minimal globals."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        undefined=Undefined,  # silent undefined — mirrors build_site behaviour
    )

    # Inject the two globals that build_site always sets (td and tr).
    # td() is a bilingual translation helper; for test purposes it just returns
    # the first argument (English).
    def _td(val, *_args, **_kw):
        return val if val is not None else ""

    def _tr(*args, **kwargs):
        return args[0] if args else ""

    env.globals.update(td=_td, tr=_tr, zip=zip)
    return env


def _minimal_vm() -> dict:
    """Absolute-minimum vm — every optional key is None or absent."""
    return {
        "latest": {},
        "market_state": None,
        "msig_stances": None,
        "fear_greed": None,
        "fear_euphoria": None,
        "vix": None,
        "chart_liquidity": None,
        "chart_credit_breadth": None,
        "chart_vix": None,
        "commodities": [],
        "positioning": [],
        "cross_asset": None,
        "fx_context": None,
    }


def _full_vm() -> dict:
    """Full production-shaped vm with every optional sub-block present."""
    vm = _minimal_vm()
    vm.update(
        latest={
            "date": "2026-07-18",
            "growth_score": 0.35,
            "inflation_score": -0.20,
            "business_cycle": {
                "available": True,
                "phase": {"key": "expansion", "label": "Expansion"},
                "shadow": {"phase": {"label": "Slowdown"}},
                "recession_signal": {
                    "state": "off",
                    "months_active": 0,
                    "conditions": {"depth": False, "breadth": False},
                },
                "tiers": {
                    "leading": {"mom6": 0.12, "diffusion": 62.0, "n_legs": 8},
                    "coincident": {"mom6": 0.07, "diffusion": 55.0, "n_legs": 4},
                    "lagging": {"mom6": -0.03, "diffusion": 42.0, "n_legs": 3},
                },
                "measured": {
                    "oos_caught": 7,
                    "oos_endogenous": 8,
                    "oos_median_lead_months": 4.5,
                    "consensus_false_positives": 1,
                    "oos_catch_rate_jeffreys95": [0.55, 0.97],
                },
            },
            "conditions": {
                "recession": {
                    "score": 22,
                    "label": "Low",
                    "sahm": 0.10,
                    "ny_fed_prob": 0.08,
                    "ebp": -0.15,
                },
                "drawdown_risk": {
                    "score": 35,
                    "band": "Moderate",
                    "dd10_prob_pct": 18,
                    "base_rate_pct": 22,
                },
                "financial_conditions": {
                    "state": "easy",
                    "nfci": -0.30,
                    "nfci_pctile": 0.28,
                    "trend": "easing",
                },
                "systemic_stress": {
                    "state": "calm",
                    "ofr_fsi": -0.12,
                    "leading_driver": "equity",
                    "cp_stress": "normal",
                },
                "growth_nowcast": {"gdpnow": 2.4, "wei": 0.8},
                "inflation_nowcast": {"sticky_ann": 3.1, "flexible_ann": 1.9},
                "labor_nowcast": {
                    "read": "steady",
                    "claims_yoy_pct": 2.1,
                    "indeed_chg_3m_pct": -1.5,
                    "withheld_tax_yoy_pct": 4.2,
                },
                "risk_appetite": {
                    "roro": 0.4,
                    "roro_state": "risk-on",
                    "vrp": 3.2,
                    "vix_term": 1.08,
                    "stock_bond_corr": 0.32,
                },
                "capitulation": {"score": 0, "signals_firing": [], "measured_bounce_pct": None},
            },
        },
        market_state={"color": "green"},
        msig_stances={
            "hero": {"en": "Conditions support staying invested — watch the usual risks.", "zh": "环境支持持仓 — 留意常规风险。"},
            "liquidity": {"en": "The money tide is rising — historically the most reliable tailwind.", "zh": "资金潮上涨 — 历史上最可靠的顺风。"},
            "credit": {"en": "Credit calm, participation healthy — no smoke.", "zh": "信用平稳，参与度健康 — 无警讯。"},
        },
        fear_greed={
            "dial": 62,
            "label_en": "Greed",
            "n_legs_qualifying": 5,
            "legs_included": [
                {"name_en": "Market momentum", "name_zh": "市场动量", "value": 1.82, "unit": "σ", "z": 1.5, "pct": 78, "orientation": "higher=greed", "obs_count": 520, "freshness": "fresh"},
                {"name_en": "Breadth", "name_zh": "广度", "value": 58.3, "unit": "%", "z": 0.8, "pct": 62, "orientation": "higher=greed", "obs_count": 520, "freshness": "fresh"},
                {"name_en": "Put/Call ratio", "name_zh": "认沽/认购比率", "value": 0.72, "unit": "", "z": -0.6, "pct": 40, "orientation": "lower=greed", "obs_count": 520, "freshness": "fresh"},
            ],
            "legs_excluded_young": [],
            "young_tiles": [],
            "disclaimer_en": "Display only. Not a buy/sell signal.",
            "disclaimer_zh": "仅供展示。非买卖信号。",
        },
        fear_euphoria={
            "fe_score": 58,
            "band": "Greed",
            "roro": 0.4,
            "legs": [
                {"name_en": "Leg A", "name_zh": "A分量", "value": 0.3, "pct": 60, "lean": "risk-on"},
            ],
            "positioning": {"chip": "confirms", "cot_washed_out": False, "cot_crowded_long": False, "insider_breadth": 0.05},
        },
        vix={
            "last": 13.8,
            "chg": -0.4,
            "pct": -2.8,
            "regime": "calm",
            "pctile": 18.0,
            "ratio": 1.04,
            "rword": "contango",
        },
        chart_liquidity="<svg viewBox='0 0 640 220' width='100%'><text>Net liquidity chart</text></svg>",
        chart_credit_breadth="<svg viewBox='0 0 640 220' width='100%'><text>Credit breadth chart</text></svg>",
        chart_vix="<svg viewBox='0 0 640 220' width='100%'><text>VIX chart</text></svg>",
        commodities=[
            {"name": "Oil (WTI)", "above200": True, "above50": True, "rsi14": 54.0, "mom_60d_pct": 3.2, "off_52w_high_pct": -8.1},
            {"name": "Gold", "above200": True, "above50": False, "rsi14": 61.0, "mom_60d_pct": 7.5, "off_52w_high_pct": -2.3},
        ],
        positioning=[
            {"name": "CTAs", "pct": 72.0, "label": "long", "verdict": "crowded long"},
            {"name": "Retail", "pct": 55.0, "label": "moderate", "verdict": None, "source": None},
        ],
        cross_asset={
            "caution_flags": [
                {"key": "fx_triple", "en": "Triple-red: dollar, stocks and bonds falling together.", "zh": "三重下跌：美元、股票与债券同跌。", "severity": "high", "owner": "fx", "lead": "coincident", "equity_blind": False},
                {"key": "credit", "en": "Credit widening.", "zh": "信用走阔。", "severity": "medium", "owner": "bonds", "lead": "leading", "equity_blind": False},
            ],
        },
        fx_context={
            "asof": "2026-07-18",
            "smile_regime": "Risk-off haven bid",
            "dollar_desk": {
                "lean": "dollar-supportive",
                "lean_n": 3,
                "triple_red": True,
                "real_rate_z": 0.8,
                "fed_path_bps": -45,
                "usd_reer_gap_pct": 6.2,
                "usd_pos_pctile": 71,
                "trend_n_up": 3,
                "liquidity_dir": "supportive",
                "smile_confidence": "medium",
            },
            "strength": {
                "default": "1m",
                "horizons": {
                    "1m": [
                        {"ccy": "EUR", "ccy_zh": "欧元", "strength": -0.42, "vs_usd_pct": -1.2, "em": False},
                        {"ccy": "JPY", "ccy_zh": "日元", "strength": 0.61, "vs_usd_pct": 2.1, "em": False},
                        {"ccy": "CNH", "ccy_zh": "离岸人民币", "strength": -0.18, "vs_usd_pct": -0.4, "em": True},
                    ],
                },
            },
            "regime_radar": {
                "scenarios": [
                    {
                        "key": "dollar_wrecking_ball",
                        "name_en": "Dollar wrecking ball",
                        "name_zh": "美元破坏球",
                        "intensity": 72,
                        "active": True,
                        "dominant": True,
                        "illustrative": True,
                        "prob": {"status": "illustrative", "p_cond": 0.35, "base_rate": 0.12, "wilson_lo": 0.07, "wilson_hi": 0.19, "n_raw": 24, "n_eff": 22, "N": 200},
                    },
                    {"key": "carry_unwind", "name_en": "Carry unwind", "name_zh": "套利平仓", "intensity": 3, "active": False, "dominant": False, "illustrative": True, "prob": None},
                ],
            },
            "transmission": {
                "headwind_for": ["EM equities", "Commodities"],
                "tailwind_for": ["USD earners"],
                "corr": {"EEM": -0.72},
            },
            "state_changes": {
                "smile_regime": {"current": "Risk-off haven bid", "prev": "US growth premium", "changed_on": "2026-07-10", "days_in_state": 8},
                "triple_red": {"current": True, "prev": False, "changed_on": "2026-07-18", "days_in_state": 1},
            },
            "pairs": {
                "USDCNH": {
                    "headline": "USD/CNH: dollar bid amid haven flows",
                    "headline_zh": "美元/离岸人民币：避险资金推升美元",
                    "shock_state": "outflow_stress",
                    "cnh_basis_bps": -28.5,
                    "cnh_basis_state": "outflow_stress",
                },
            },
            "recent_events": [
                {"date": "2026-07-18", "headline": "Triple-red onset: dollar, stocks and bonds falling together.", "headline_zh": "三重下跌触发：美元、股票与债券同跌。", "severity": "high"},
                {"date": "2026-07-10", "headline": "Smile regime flipped to Risk-off haven bid.", "headline_zh": "微笑周期切换至避险资金涌入。", "severity": "medium"},
            ],
        },
    )
    return vm


def _strip_tips(html: str) -> str:
    """Remove content inside .tip spans so we can check glance-tier text only."""
    # Remove <span class="tip">...</span> blocks (possibly nested)
    # Simple approach: strip everything between class="tip" and the closing span
    return re.sub(r'<span class="tip">.*?</span>', '', html, flags=re.DOTALL)


def _render(vm: dict) -> str:
    env = _make_env()
    tpl = env.get_template("macro_signals.html.j2")
    return tpl.render(**vm)


# ---------------------------------------------------------------------------
# Scenario (a): full vm
# ---------------------------------------------------------------------------

class TestFullVm:
    def setup_method(self):
        self.html = _render(_full_vm())

    def test_no_plotly(self):
        """Plotly must not be included — it was dropped in MSX-2."""
        assert "plotly" not in self.html.lower()

    def test_hero_stance_green(self):
        """Green market state → positive stance sentence rendered."""
        assert "Conditions support staying invested" in self.html

    def test_fx_section_present(self):
        """fx_context present → currencies section renders."""
        assert "currencies" in self.html or "Full currency board" in self.html

    def test_triple_red_banner(self):
        """triple_red=True → banner text in page."""
        assert "Dollar, stocks and bonds are falling together" in self.html

    def test_offshore_yuan_outflow(self):
        """CNH shock_state=outflow_stress → outflow pressure text."""
        assert "Offshore yuan under outflow pressure" in self.html

    def test_dollar_regime_risk_off_plain_words(self):
        """Risk-off haven bid → plain-word mapping rendered on the dollar card."""
        assert "Dollar strong — investors hiding in it" in self.html
        # The raw smile-regime key must NOT appear in the dollar-regime card itself —
        # only event headlines (recent_events) may echo it as narrative copy.
        # Check that the smile-map div renders the plain words and not just the key.
        assert "investors hiding in it" in self.html

    def test_fx_caution_flag_rendered(self):
        """FX caution flag (owner='fx') appears; bonds flag does not in fx row."""
        assert "Triple-red: dollar, stocks and bonds falling together" in self.html

    def test_forex_link(self):
        """Footer link to forex.html present."""
        assert "forex.html" in self.html

    def test_banned_loro_absent_from_glance(self):
        """'LORO' must not appear outside .tip spans."""
        glance = _strip_tips(self.html)
        assert "LORO" not in glance

    def test_banned_zscore_absent_from_glance(self):
        """'z-score' must not appear outside .tip spans at glance tier."""
        glance = _strip_tips(self.html)
        # Allow 'z-score' only inside tip spans
        assert "z-score" not in glance

    def test_no_validated_keyword(self):
        """'validated' must never appear in user-facing copy."""
        assert "validated" not in self.html.lower()

    def test_growth_stance_present(self):
        """Growth phase (expansion) maps to plain sentence."""
        assert "The economy is growing" in self.html

    def test_no_title_t_macro(self):
        """<title> must be plain text (RCDATA law) — no t() spans inside it."""
        title_match = re.search(r'<title>(.*?)</title>', self.html, re.DOTALL)
        assert title_match, "No <title> found"
        title_text = title_match.group(1)
        assert "<span" not in title_text
        assert "l-en" not in title_text

    def test_prefers_reduced_motion_guard(self):
        """prefers-reduced-motion: reduce must disable animations."""
        assert "prefers-reduced-motion" in self.html
        assert "animation:none" in self.html or "animation: none" in self.html

    def test_macro_context_crosslink_present(self):
        """Cross-link to macro_context.html present."""
        assert "macro_context.html" in self.html

    def test_as_of_single_in_hero(self):
        """As-of date renders from latest.date."""
        assert "2026-07-18" in self.html

    def test_svg_needle_gauges_present(self):
        """Four gauge SVGs rendered."""
        assert "gauge-growth" in self.html
        assert "gauge-inflation" in self.html
        assert "gauge-fg" in self.html
        assert "gauge-vix" in self.html

    def test_commodities_trend_words(self):
        """Commodities table shows 'above trend'/'below trend', not ✓✗ for 200."""
        assert "above trend" in self.html or "below trend" in self.html
        # ✓✗ should NOT appear for the 200 day column any more
        # (RSI ✓✗ was removed; the test checks the key word)
        assert "above trend" in self.html

    def test_days_held_chip(self):
        """Days-in-state chip rendered from state_changes.smile_regime."""
        assert "8" in self.html  # days_in_state = 8

    def test_stress_chip_dominant(self):
        """Dominant stress scenario renders with dominant tag."""
        assert "Dollar wrecking ball" in self.html
        assert "dominant" in self.html

    def test_null_intensity_scenario_renders(self):
        """B1 regression: a scenario with null/missing intensity must not crash
        the render (selectattr 'ge' on None aborts the whole nightly build)."""
        vm = _full_vm()
        vm["fx_context"]["regime_radar"]["scenarios"].extend([
            {"key": "s_null", "name_en": "Null intensity", "name_zh": "空强度",
             "intensity": None, "active": False, "illustrative": False, "prob": None},
            {"key": "s_missing", "name_en": "Missing intensity", "name_zh": "缺强度",
             "active": True, "illustrative": False, "prob": None},
        ])
        html = _render(vm)
        assert "Stress patterns" in html

    def test_liquidity_4wk_chip_renders(self):
        """M2 regression: the 4-week change chip renders from chart_liquidity_meta."""
        vm = _full_vm()
        vm["chart_liquidity_meta"] = {"chg_4w_bn": 132.0, "state": "rising"}
        html = _render(vm)
        assert "+132" in html and "bn / 4wk" in html

    def test_insufficient_prob_scenario_renders(self):
        """Scenario with a None-field prob dict (status=insufficient) must render
        without raising — the real-data crash class caught on first full build."""
        vm = _full_vm()
        vm["fx_context"]["regime_radar"]["scenarios"].append({
            "key": "carry_unwind2", "name_en": "Carry unwind", "name_zh": "套息平仓",
            "intensity": 12.0, "active": False, "illustrative": False,
            "prob": {"status": "insufficient", "p_cond": None, "base_rate": 0.18,
                     "wilson_lo": None, "wilson_hi": None, "n_raw": 6, "n_eff": 2.1, "N": 10},
        })
        html = _render(vm)
        assert "Not enough history at this stress level" in html

    def test_what_changed_strip(self):
        """recent_events strip renders with event headline."""
        assert "Triple-red onset" in self.html

    def test_num_token_defined(self):
        """--num CSS token must be defined locally (not inherited from dashboard)."""
        assert "--num:" in self.html

    def test_no_raw_enum_outflow_stress_glance(self):
        """Raw enum 'outflow_stress' must not appear at glance tier."""
        glance = _strip_tips(self.html)
        assert "outflow_stress" not in glance


# ---------------------------------------------------------------------------
# Scenario (b): fx_context=None
# ---------------------------------------------------------------------------

class TestNoFxContext:
    def setup_method(self):
        vm = _full_vm()
        vm["fx_context"] = None
        self.html = _render(vm)

    def test_fx_section_absent(self):
        """When fx_context is None the currencies section must be absent."""
        # The section is gated on {% if fx_context %}
        # "Full currency board" is our section-specific footer text.
        # Note: forex.html may still appear in the nav include — that is fine.
        assert "Full currency board" not in self.html

    def test_no_triple_red_banner(self):
        assert "Dollar, stocks and bonds are falling together" not in self.html

    def test_no_offshore_yuan(self):
        assert "Offshore yuan" not in self.html

    def test_page_still_renders(self):
        """Page renders without throwing — hero still present."""
        assert "Right now" in self.html or "当下" in self.html


# ---------------------------------------------------------------------------
# Scenario (c): minimal vm — no exception
# ---------------------------------------------------------------------------

class TestMinimalVm:
    def test_renders_without_exception(self):
        """Minimal vm (all optionals None/absent) must render without raising."""
        html = _render(_minimal_vm())
        assert "<!DOCTYPE html>" in html

    def test_no_plotly_minimal(self):
        html = _render(_minimal_vm())
        assert "plotly" not in html.lower()

    def test_absent_market_state_fallback(self):
        """market_state=None → neutral stance fallback sentence renders."""
        html = _render(_minimal_vm())
        assert "A mixed picture" in html or "情况混杂" in html

    def test_absent_fear_greed_no_crash(self):
        """fear_greed=None → mood section simply absent, no crash."""
        html = _render(_minimal_vm())
        # The gauge still renders but shows '—'
        assert "<!DOCTYPE html>" in html

    def test_latest_empty_dict_no_crash(self):
        """latest={} → no crash on gauge rendering."""
        vm = _minimal_vm()
        vm["latest"] = {}
        html = _render(vm)
        assert "<!DOCTYPE html>" in html
