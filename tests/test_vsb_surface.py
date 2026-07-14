"""VSB W3/W4/W5 surface tests: vol_weather + breadth_split on Market Sentiment card/dialog.

Four scenario groups:
  (i)  Both payloads present -> strip rows, AI section, stance text, card caveat appear.
  (ii) vol_weather=None/breadth_split=None -> sections absent, no raise.
  (iii) spread_50=8 (below 15 threshold) -> no card caveat rendered.
  (iv) Chip with pctile=None -> 'Still collecting' copy shown, no history phrase.

Also asserts no '<< NaN' artifacts in rendered output.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Jinja2 environment helpers
# ---------------------------------------------------------------------------

def _env():
    """Minimal Jinja2 env that mirrors build_site.py's dashboard render env."""
    import jinja2
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
        undefined=jinja2.ChainableUndefined,
    )
    # td/tr/zip globals (subset used by template)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    except Exception:  # noqa: BLE001
        env.globals.update(
            td=lambda en, zh=None: en,
            tr=lambda en: en,
            zip=zip,
        )
    env.filters["min"] = lambda seq: min(seq)
    return env


def _base_ctx() -> dict:
    """Minimal context dict that keeps the template from crashing on unrelated keys.

    Only provides the keys exercised by the sections under test. All other
    references inside dashboard.html.j2 degrade via ChainableUndefined.
    """
    return {
        # fear_greed: needed by the dialog preamble we share the block with
        "fear_greed": {
            "dial": 50,
            "label_en": "Neutral",
            "label_zh": "中性",
            "legs_included": [],
            "legs_excluded_young": [],
            "disclaimer_en": "Test disclaimer.",
            "disclaimer_zh": "测试免责声明。",
            "as_of": "2026-07-13",
        },
        # defaults for other often-accessed keys
        "latest": {},
        "generated": "2026-07-13 00:00",
        # These should be None/falsy by default; individual tests override
        "vol_weather": None,
        "breadth_split": None,
    }


def _full_vol_weather() -> dict:
    """Fixture: vol_weather payload with all 8 chips, some young, some with pctile."""
    return {
        "as_of": "2026-07-13",
        "n_young": 1,
        "disclaimer_en": "Vol weather disclaimer.",
        "disclaimer_zh": "波动率天气免责声明。",
        "chips": [
            {
                "key": "vix_level",
                "name_en": "VIX level",
                "name_zh": "VIX 水平",
                "value": 18.5,
                "pctile": 42,
                "band": "normal",
                "state": "calm",
                "plain_en": "Volatility is calm",
                "plain_zh": "波动率平静",
                "freshness": "ok",
                "obs_count": 500,
                "last_date": "2026-07-13",
                "spark": [17, 18, 19, 18.5],
            },
            {
                "key": "vix_velocity",
                "name_en": "VIX velocity",
                "name_zh": "VIX 变动速度",
                "value": 0.3,
                "pctile": 55,
                "band": "normal",
                "state": "steady",
                "plain_en": "Rising slowly",
                "plain_zh": "缓慢上升",
                "freshness": "ok",
                "obs_count": 500,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "term_slope",
                "name_en": "VIX term slope",
                "name_zh": "VIX 期限结构斜率",
                "value": 2.1,
                "pctile": 60,
                "band": "normal",
                "state": "contango",
                "plain_en": "Curve in contango — near-term calm",
                "plain_zh": "期货溢价，短期平静",
                "freshness": "ok",
                "obs_count": 500,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "vvix_vix",
                "name_en": "VVIX / VIX",
                "name_zh": "VVIX / VIX",
                "value": 5.8,
                "pctile": 72,
                "band": "elevated",
                "state": "hedging",
                "plain_en": "Options on options elevated vs VIX",
                "plain_zh": "期权隐含波动率高于 VIX",
                "freshness": "ok",
                "obs_count": 500,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "vix1d",
                "name_en": "VIX1D (overnight VIX)",
                "name_zh": "VIX1D（隔夜波动率）",
                "value": None,
                "pctile": None,
                "band": None,
                "state": "young",
                "plain_en": None,
                "plain_zh": None,
                "freshness": "young",
                "obs_count": 10,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "cor1m",
                "name_en": "1-month implied correlation",
                "name_zh": "1个月隐含相关性",
                "value": 0.38,
                "pctile": 33,
                "band": "low",
                "state": "dispersed",
                "plain_en": "Stocks moving independently — dispersion high",
                "plain_zh": "个股走势分散，相关性低",
                "freshness": "ok",
                "obs_count": 400,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "cor3m",
                "name_en": "3-month implied correlation",
                "name_zh": "3个月隐含相关性",
                "value": 0.41,
                "pctile": 38,
                "band": "low",
                "state": "dispersed",
                "plain_en": "Stocks moving independently",
                "plain_zh": "个股走势分散",
                "freshness": "ok",
                "obs_count": 400,
                "last_date": "2026-07-13",
                "spark": [],
            },
            {
                "key": "dspx",
                "name_en": "DSPX dispersion index",
                "name_zh": "DSPX 离散度指数",
                "value": 12.3,
                "pctile": 65,
                "band": "elevated",
                "state": "high",
                "plain_en": "Dispersion elevated — stock-picking matters",
                "plain_zh": "离散度偏高，选股更重要",
                "freshness": "ok",
                "obs_count": 300,
                "last_date": "2026-07-13",
                "spark": [],
            },
        ],
    }


def _full_breadth_split(spread: float = 25.0) -> dict:
    """Fixture: breadth_split payload."""
    return {
        "as_of": "2026-07-13",
        "cohort_sizes": {
            "ai_core": 80,
            "ai_infra_power": 20,
            "ai_total": 100,
            "non_ai": 300,
            "universe": 400,
            "ai_core_tagged": 85,
            "ai_infra_power_tagged": 22,
        },
        "latest": {
            "ai_pct50": 72.0,
            "nonai_pct50": 72.0 - spread,
            "spread_50": spread,
            "ai_pct200": 65.0,
            "nonai_pct200": 60.0,
            "spread_200": 5.0,
            "ai_adv_share": 55.0,
            "nonai_adv_share": 50.0,
            "spread_adv": 5.0,
        },
        "spark": {"spread_50": [20, 22, 25, 24, 25]},
        "young": False,
        "stance_en": "AI names leading — watch, don't chase",
        "stance_zh": "AI 相关股领涨，观察而非追高",
        "disclaimer_en": "Display-only. Not investment advice.",
        "disclaimer_zh": "仅供展示，非投资建议。",
    }


def _render(ctx: dict) -> str:
    """Render dashboard.html.j2 with the given context; returns HTML string."""
    env = _env()
    tmpl = env.get_template("dashboard.html.j2")
    return tmpl.render(**ctx)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVSBSurfaceBothPayloads:
    """Scenario (i): both vol_weather and breadth_split present."""

    def test_vol_weather_section_present(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert 'id="vsb-vol-weather-section"' in html, (
            "Vol weather section header should render when payload present"
        )

    def test_vol_weather_chip_rows_present(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split()
        html = _render(ctx)
        # At least some chip keys should appear as data-vsb-chip attributes
        assert 'data-vsb-chip="vix_level"' in html
        assert 'data-vsb-chip="vix_velocity"' in html
        assert 'data-vsb-chip="cor1m"' in html
        assert 'data-vsb-chip="dspx"' in html

    def test_vol_weather_plain_text_and_pctile_phrase(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        html = _render(ctx)
        # plain_en text for vix_level chip should appear
        assert "Volatility is calm" in html
        # pctile=42 (<50) -> renders the low-side phrasing "lower than 58% of days"
        assert "lower than 58% of days" in html
        # a high-side chip (pctile >= 50) renders "higher than N% of days"
        assert "higher than" in html

    def test_breadth_split_section_present(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert 'id="vsb-breadth-split-section"' in html, (
            "AI vs rest section header should render when payload present"
        )

    def test_breadth_split_stance_text(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert "AI names leading" in html
        assert "AI 相关股领涨" in html

    def test_breadth_split_receipt_lines(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert 'data-vsb-bs="ai"' in html
        assert 'data-vsb-bs="nonai"' in html
        assert "AI-linked names above their 50-day trend" in html
        assert "Everyone else" in html

    def test_card_caveat_renders_when_spread_large(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert 'id="vsb-sentiment-caveat"' in html, (
            "Card caveat should render when |spread_50| >= 15"
        )
        # Stance text should appear in the caveat
        assert "AI names leading" in html

    def test_circularity_watch_note(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        assert "recycles capital" in html, (
            "Static circularity-watch note should appear in dialog"
        )

    def test_cohort_size_note(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        # 100 AI-linked names out of 400 tracked
        assert "100" in html
        assert "400" in html

    def test_no_nan_artifacts(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=25.0)
        html = _render(ctx)
        # The brief check: no Jinja undefined-variable render artifacts
        assert "<< NaN" not in html, "No << NaN artifacts should appear"
        # Spot-check our added sections specifically: extract the vol/breadth block
        # by looking between our sentinel ids; neither should contain rendering NaNs
        if 'id="vsb-vol-weather-section"' in html:
            start = html.index('id="vsb-vol-weather-section"')
            snippet = html[start:start + 4000]
            assert "<< NaN" not in snippet


class TestVSBSurfaceAbsent:
    """Scenario (ii): vol_weather=None, breadth_split=None -> sections absent, no raise."""

    def test_renders_without_exception_when_both_none(self):
        ctx = _base_ctx()
        # Already defaults to None; just confirm render doesn't raise
        html = _render(ctx)
        assert html  # non-empty

    def test_vol_weather_section_absent_when_none(self):
        ctx = _base_ctx()
        html = _render(ctx)
        assert 'id="vsb-vol-weather-section"' not in html

    def test_breadth_split_section_absent_when_none(self):
        ctx = _base_ctx()
        html = _render(ctx)
        assert 'id="vsb-breadth-split-section"' not in html

    def test_card_caveat_absent_when_breadth_none(self):
        ctx = _base_ctx()
        html = _render(ctx)
        assert 'id="vsb-sentiment-caveat"' not in html

    def test_no_nan_artifacts_absent_case(self):
        ctx = _base_ctx()
        html = _render(ctx)
        # No Jinja undefined render artifacts
        assert "<< NaN" not in html


class TestVSBSurfaceSmallSpread:
    """Scenario (iii): spread_50=8 (below 15 threshold) -> no card caveat."""

    def test_card_caveat_absent_when_spread_small(self):
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=8.0)
        html = _render(ctx)
        assert 'id="vsb-sentiment-caveat"' not in html, (
            "Card caveat must not render when |spread_50| < 15"
        )

    def test_dialog_sections_still_render_when_spread_small(self):
        """Small spread should not suppress the dialog sections."""
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()
        ctx["breadth_split"] = _full_breadth_split(spread=8.0)
        html = _render(ctx)
        assert 'id="vsb-breadth-split-section"' in html

    def test_negative_spread_also_suppressed(self):
        """Negative spread of -8 is below absolute threshold — no caveat."""
        bs = _full_breadth_split(spread=-8.0)
        bs["latest"]["spread_50"] = -8.0
        bs["latest"]["nonai_pct50"] = 80.0
        ctx = _base_ctx()
        ctx["breadth_split"] = bs
        html = _render(ctx)
        assert 'id="vsb-sentiment-caveat"' not in html


class TestVSBSurfaceYoungChip:
    """Scenario (iv): chip with pctile=None renders 'still collecting' copy, no history phrase."""

    def test_young_chip_shows_collecting_copy(self):
        """vix1d chip has freshness='young' and pctile=None -> 'Still collecting' shown."""
        ctx = _base_ctx()
        ctx["vol_weather"] = _full_vol_weather()  # includes vix1d with freshness='young'
        html = _render(ctx)
        assert "Still collecting" in html, (
            "Young chip should show 'Still collecting — check back soon'"
        )

    def test_young_chip_no_history_phrase(self):
        """A young chip must NOT show 'higher than X% of days'."""
        ctx = _base_ctx()
        # Isolate: only vix1d (young, pctile=None) in vol_weather
        vw = {
            "as_of": "2026-07-13",
            "n_young": 1,
            "chips": [
                {
                    "key": "vix1d",
                    "name_en": "VIX1D",
                    "name_zh": "VIX1D",
                    "value": None,
                    "pctile": None,
                    "band": None,
                    "state": "young",
                    "plain_en": None,
                    "plain_zh": None,
                    "freshness": "young",
                    "obs_count": 5,
                    "last_date": "2026-07-13",
                    "spark": [],
                }
            ],
        }
        ctx["vol_weather"] = vw
        html = _render(ctx)
        assert "higher than" not in html, (
            "Young chip with pctile=None must not show 'higher than X% of days'"
        )
        assert "Still collecting" in html

    def test_ok_chip_with_pctile_shows_history_phrase(self):
        """A non-young chip with pctile=99 should show 'higher than 99% of days'."""
        ctx = _base_ctx()
        vw = {
            "as_of": "2026-07-13",
            "n_young": 0,
            "chips": [
                {
                    "key": "vix_level",
                    "name_en": "VIX level",
                    "name_zh": "VIX 水平",
                    "value": 45.0,
                    "pctile": 99,
                    "band": "extreme",
                    "state": "panic",
                    "plain_en": "Extreme fear — volatility spiked",
                    "plain_zh": "极度恐慌，波动率飙升",
                    "freshness": "ok",
                    "obs_count": 500,
                    "last_date": "2026-07-13",
                    "spark": [],
                }
            ],
        }
        ctx["vol_weather"] = vw
        html = _render(ctx)
        assert "higher than 99% of days" in html

    def test_ok_chip_no_pctile_no_history_phrase(self):
        """A chip with pctile=None but freshness='ok' should not show history phrase."""
        ctx = _base_ctx()
        vw = {
            "as_of": "2026-07-13",
            "n_young": 0,
            "chips": [
                {
                    "key": "vix_level",
                    "name_en": "VIX level",
                    "name_zh": "VIX 水平",
                    "value": 18.0,
                    "pctile": None,
                    "band": "normal",
                    "state": "calm",
                    "plain_en": "Calm",
                    "plain_zh": "平静",
                    "freshness": "ok",
                    "obs_count": 500,
                    "last_date": "2026-07-13",
                    "spark": [],
                }
            ],
        }
        ctx["vol_weather"] = vw
        html = _render(ctx)
        assert "higher than" not in html
        # plain text should still appear
        assert "Calm" in html
