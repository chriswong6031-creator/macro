"""tests/test_leadership_board.py — MLC-W1 Leadership Board render tests.

Covers:
  - Full payload render: key strings present, no crash.
  - All-null payload: panel absent (fail-open silently).
  - No banned Tier-1 jargon (raw lifecycle enum slugs, "validated").
  - Lifecycle states translate to plain-word labels (never raw enum on Tier 1).
  - Earnings chip renders when within 14d, absent when over 14d or stale.
  - Sector RS strip renders with lead words (not raw "mid-pack" or enum slugs).
  - Cohort strip: generals line, run day count, cw-vs-ew word.
  - Bilingual parity: EN and ZH strings both present.
  - build_site._leadership_board_view: None when m7 absent; valid when present.
  - both macro and stocks modes render without exception (dashboard.html.j2 smoke test).
"""
from __future__ import annotations

import json
import pathlib
import sys
import re

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA_OK = True
except ImportError:
    _JINJA_OK = False

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"
ROOT = pathlib.Path(__file__).parent.parent


def _env() -> "Environment":
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    return env


# ── full fixture ──────────────────────────────────────────────────────────────

FULL_PAYLOAD: dict = {
    "as_of": "2026-07-14",
    "trend_state": "turning_up",
    "run": {"start": "2026-07-01", "sessions": 8, "cw_ret": 0.0236, "spy_ret": 0.0046},
    "generals": {"now": ["AAPL", "META", "NVDA"], "joining": ["MSFT", "AMZN"], "coverage": 0.67},
    "k7": {"trend": 2, "rs": 5},
    "cw": {"r2": 0.001, "r5": 0.010, "r10": 0.077, "r20": 0.026, "rel20": 0.008},
    "ew": {"r10": 0.083, "r20": 0.035},
    "members": [
        {"sym": "AAPL", "w": 0.19, "r5": 0.02, "r10": 0.05, "r20": 0.08,
         "rs20": 0.04, "above50": True, "above200": True, "contrib10": 0.3,
         "lifecycle": "QUIET_ACCUMULATION", "earnings": None},
        {"sym": "MSFT", "w": 0.14, "r5": -0.01, "r10": 0.03, "r20": 0.04,
         "rs20": -0.02, "above50": False, "above200": True, "contrib10": 0.1,
         "lifecycle": "BREAKAWAY", "earnings": {"next_date": "2026-07-29", "days_until": 15}},
        {"sym": "NVDA", "w": 0.13, "r5": 0.06, "r10": 0.09, "r20": 0.07,
         "rs20": 0.05, "above50": True, "above200": True, "contrib10": 0.2,
         "lifecycle": "LEADERSHIP", "earnings": {"next_date": "2026-07-20", "days_until": 6}},
        {"sym": "AMZN", "w": 0.11, "r5": 0.01, "r10": 0.02, "r20": 0.03,
         "rs20": 0.01, "above50": False, "above200": False, "contrib10": 0.05,
         "lifecycle": "NONE", "earnings": None},
        {"sym": "GOOGL", "w": 0.10, "r5": -0.02, "r10": -0.01, "r20": -0.02,
         "rs20": -0.03, "above50": False, "above200": False, "contrib10": -0.01,
         "lifecycle": "FAILED", "earnings": None},
        {"sym": "META", "w": 0.10, "r5": 0.04, "r10": 0.06, "r20": 0.07,
         "rs20": 0.05, "above50": True, "above200": True, "contrib10": 0.15,
         "lifecycle": "CROWDED", "earnings": None},
        {"sym": "TSLA", "w": 0.07, "r5": -0.04, "r10": -0.06, "r20": -0.07,
         "rs20": -0.08, "above50": False, "above200": False, "contrib10": -0.05,
         "lifecycle": "SUPPRESSED", "earnings": None},
    ],
    "sector_rs": [
        {"ticker": "XLK", "name": "Technology", "name_zh": "科技",
         "rs_rank": 1, "lead": "leading", "conviction_en": "Cautious", "conviction_zh": "谨慎"},
        {"ticker": "XLF", "name": "Financials", "name_zh": "金融",
         "rs_rank": 2, "lead": "leading", "conviction_en": "Cautious", "conviction_zh": "谨慎"},
        {"ticker": "XLV", "name": "Health Care", "name_zh": "医疗保健",
         "rs_rank": 3, "lead": "leading", "conviction_en": "Reduce", "conviction_zh": "减仓"},
        {"ticker": "XLI", "name": "Industrials", "name_zh": "工业",
         "rs_rank": 4, "lead": "mid-pack", "conviction_en": "Neutral", "conviction_zh": "中性"},
        {"ticker": "XLV", "name": "Real Estate", "name_zh": "房地产",
         "rs_rank": 5, "lead": "mid-pack", "conviction_en": "Reduce", "conviction_zh": "减仓"},
        {"ticker": "XLU", "name": "Utilities", "name_zh": "公用事业",
         "rs_rank": 11, "lead": "lagging", "conviction_en": "Accumulate", "conviction_zh": "积极配置"},
    ],
}

RENDER_TMPL = (
    "{% from '_leadership_board.html.j2' import leadership_board as lboard %}"
    "{{ lboard(d) }}"
)
GUARD_TMPL = (
    "{% from '_leadership_board.html.j2' import leadership_board as lboard %}"
    "{% if d %}{{ lboard(d) }}{% endif %}"
)


# ── main render tests ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_renders_full_payload_without_exception():
    """Full fixture must render without raising; panel class present."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "ldb" in html
    assert len(html) > 500


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_key_tier1_strings_present():
    """Title, cohort badge, stance words, and company names on Tier 1."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # panel title bilingual
    assert "Leadership Board" in html
    assert "领涨面板" in html
    # cohort badge (turning_up)
    assert "Turning up" in html
    assert "拐头向上" in html
    # stance
    assert "Get ready" in html
    assert "准备就绪" in html
    # company names (Tier 1 display names, not raw tickers)
    assert "Apple" in html
    assert "苹果" in html
    assert "Nvidia" in html
    assert "英伟达" in html
    # generals line
    assert "Led by" in html
    assert "领涨" in html
    # run day count
    assert "day 8" in html
    assert "第8日" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_lifecycle_states_plain_word_on_tier1():
    """Raw lifecycle enum slugs must NOT appear in user-visible copy.
    Plain-word translations must be present for all states."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    stripped = re.sub(r'\s+class="[^"]*"', '', html)
    stripped = re.sub(r'\s+data-tip-[a-z]+="[^"]*"', '', stripped)
    stripped = re.sub(r'\s+style="[^"]*"', '', stripped)
    # raw enum slugs must not be in user-visible copy (CSS class names are stripped above)
    BANNED_RAW = [
        "QUIET_ACCUMULATION", "BREAKAWAY", "LEADERSHIP", "CROWDED",
        "SUPPRESSED", "FAILED", "CATALYST_WINDOW",
    ]
    for term in BANNED_RAW:
        assert term not in stripped, f"Raw enum '{term}' leaked to user-visible copy"
    # plain-word translations must be present
    assert "quietly building" in html  # QUIET_ACCUMULATION
    assert "breaking out" in html       # BREAKAWAY
    assert "leading the market" in html # LEADERSHIP
    assert "crowded" in html            # CROWDED
    assert "held back" in html          # SUPPRESSED
    assert "trend failed" in html       # FAILED
    assert "no trend read" in html      # NONE


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_sowhat_stances_present():
    """Every megacap tile shows a 'so what do I do' stance (MLC-R9)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # LEADERSHIP → "In favour"; BREAKAWAY → "Get ready"; SUPPRESSED → "Stand aside"
    assert "In favour" in html
    assert "Stand aside" in html
    assert "Watch" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_earnings_chip_renders_when_within_14d():
    """Earnings chip appears only for members with earnings.days_until ≤ 14."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # NVDA has 6d → chip should appear
    assert "reports in 6d" in html
    assert "6日后发布财报" in html
    # MSFT has 15d (>14) → no chip (earnings field not present for 15d)
    # AAPL has None → no chip


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_sector_rs_strip_renders_with_plain_words():
    """Sector RS strip shows rank numbers and plain-word lead labels."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # Tier 1 lead words
    assert "leading" in html
    assert "lagging" in html
    # Sector names
    assert "Technology" in html
    assert "Utilities" in html
    # Chinese sector names
    assert "科技" in html
    assert "公用事业" in html
    # Rank numbers
    assert "#1" in html
    assert "#11" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_banned_tier1_vocabulary():
    """Design doctrine: banned Tier-1 jargon must not appear in user-visible copy.
    Strips class attrs, data-tip attrs, style attrs, and <style>...</style> blocks
    before checking — these are not visible to the user."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # strip CSS blocks (not user-visible)
    stripped = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    # strip class attributes (CSS identifiers are not user copy)
    stripped = re.sub(r'\s+class="[^"]*"', '', stripped)
    # strip data-tip (Tier 2 hover — not always-visible Tier 1)
    stripped = re.sub(r'\s+data-tip-[a-z]+="[^"]*"', '', stripped)
    # strip inline style attributes
    stripped = re.sub(r'\s+style="[^"]*"', '', stripped)
    BANNED = [
        "organ", "lobe", "display-tier", "display-only", "confluence",
        "k-of-n", "K-of-N", "percentile", "z-score", "t-stat",
        "Leader Radar",     # internal program name — banned from Tier 1
        "LRV",              # internal acronym
        "M7C",              # internal acronym
        "MLC",              # internal program name
    ]
    for term in BANNED:
        assert term not in stripped, f"Banned Tier-1 term '{term}' found in user-visible HTML"


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_validated_word():
    """CI law: 'validated' must never appear in user-facing output."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "validated" not in html.lower()


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_none_payload():
    """Panel renders nothing when payload is None."""
    env = _env()
    html = env.from_string(GUARD_TMPL).render(d=None)
    assert "ldb" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_empty_dict():
    """Panel renders nothing when payload is empty dict (falsy in Jinja2)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d={})
    assert "ldb" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_all_null_members_no_crash():
    """All-null member fields must render without crashing — no blank tile, no exception."""
    env = _env()
    null_payload = {
        "as_of": "2026-07-14",
        "trend_state": "cooling",
        "run": {},
        "generals": {},
        "k7": {},
        "cw": {},
        "ew": {},
        "members": [
            {"sym": "AAPL", "lifecycle": None, "earnings": None},
            {"sym": "NVDA", "lifecycle": "NONE", "earnings": None},
        ],
        "sector_rs": [],
    }
    html = env.from_string(RENDER_TMPL).render(d=null_payload)
    assert "ldb" in html
    assert "no trend read" in html  # null lifecycle renders plain-word null
    assert "暂无趋势判断" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_sector_rs_no_crash():
    """Empty sector_rs list must render without crashing (RS strip body simply absent)."""
    env = _env()
    payload = dict(FULL_PAYLOAD, sector_rs=[])
    html = env.from_string(RENDER_TMPL).render(d=payload)
    assert "ldb" in html
    # RS strip HTML div should be absent (the CSS class name is still in <style>,
    # but the actual <div class="ldb-rs-rows"> HTML element should not exist).
    # Strip the <style> block first to avoid false positives from CSS rules.
    body_html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    assert 'class="ldb-rs-rows"' not in body_html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_bilingual_parity():
    """Both EN and ZH strings must appear throughout the panel."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # English
    assert "Leadership Board" in html
    assert "Turning up" in html
    assert "Sector momentum rank" in html
    # Chinese
    assert "领涨面板" in html
    assert "拐头向上" in html
    assert "板块动量排名" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_cohort_strip_cw_ew_word():
    """cw vs ew word line renders when both r10 fields present."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # FULL_PAYLOAD has cw.r10 = 0.077, ew.r10 = 0.083 → ew > cw
    assert "equal-weight leading" in html or "cap-weight" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_footnote_present():
    """Footnote 'heads-up, not a buy signal' must be present."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "heads-up, not a buy signal" in html
    assert "仅供参考，非买入信号" in html


# ── dashboard.html.j2 smoke tests ────────────────────────────────────────────

def _full_env():
    """Mirror scripts/build_site.py Jinja env (same as test_dashboard_template_render)."""
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _base_vm_with_lb() -> dict:
    """Base vm from test_dashboard_template_render extended with leadership_board key."""
    # Minimal vm that passes the existing dashboard render suite
    return dict(
        latest={
            "date": "2026-07-14",
            "quad": "Q2",
            "quad_name": "Reflation",
            "label": "Q2 — Reflation",
            "confidence": 0.72,
            "fed_stance": None,
            "dislocation": None,
            "turning_point": None,
            "risk_radar": None,
            "rate_inflation_transmission": None,
            "cross_asset_confirm": None,
            "transition_state": "stable",
            "liquidity_overlay": "neutral",
            "conditions": None,
            "risk_state": None,
            "cycle_tag": "mid",
        },
        mtf=None,
        macro_catalysts=[],
        event_strip=[],
        event_risk=None,
        prediction_markets=None,
        narrative_regime=None,
        ndi=None,
        macro_news=None,
        macro_brief=None,
        macro_news_disclaimer="",
        macro_news_disclaimer_zh="",
        alerts=[],
        pb=None,
        month_name="July",
        commodities=[],
        sector_timing={},
        action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
        top_setups=[],
        us_standouts=None,
        us_board_outcomes=None,
        market_gamma=None,
        components_confirming=[],
        components_contradicting=[],
        flip_plain=None,
        internals=[],
        size_style=[],
        breadth_div=None,
        breadth_panel=None,
        adv_breadth=None,
        sector_setups=None,
        generated_utc="2026-07-14 06:00",
        chart_liquidity=None,
        chart_credit_breadth=None,
        market_tiles=[],
        vix=None,
        chart_vix=None,
        positioning=[],
        holdings_changes=[],
        holdings_threshold=5.0,
        accumulation=[],
        flows_html="",
        health=[],
        factor_leadership=None,
        nowcast_hist=None,
        stance=None,
        index_health=[],
        alloc_card=None,
        risk_model=None,
        chart_risk_model=None,
        chart_curve=None,
        chart_vix_term=None,
        cross_asset=None,
        fear_euphoria=None,
        regime_snap=None,
        market_state=None,
        signal_stack=None,
        vol_shock=None,
        froth_fragility=None,
        fear_greed=None,
        sector_heat=None,
        dispersion_regime=None,
        policy_lever=None,
        flip_confirmation=None,
        shock_state=None,
        # MLC-W1 new key
        leadership_board=FULL_PAYLOAD,
    )


def test_dashboard_macro_mode_with_leadership_board():
    """dashboard.html.j2 macro mode renders without exception when leadership_board present."""
    env = _full_env()
    html = env.get_template("dashboard.html.j2").render(**_base_vm_with_lb(), mode="macro")
    assert len(html) > 50_000
    assert "Leadership Board" in html
    assert "领涨面板" in html


def test_dashboard_stocks_mode_with_leadership_board():
    """dashboard.html.j2 stocks mode renders without exception when leadership_board present."""
    env = _full_env()
    html = env.get_template("dashboard.html.j2").render(**_base_vm_with_lb(), mode="stocks")
    assert len(html) > 50_000
    assert "Leadership Board" in html


def test_dashboard_macro_mode_null_leadership_board():
    """dashboard.html.j2 renders cleanly when leadership_board is None (panel absent)."""
    env = _full_env()
    vm = _base_vm_with_lb()
    vm["leadership_board"] = None
    html = env.get_template("dashboard.html.j2").render(**vm, mode="macro")
    assert len(html) > 50_000
    assert "Leadership Board" not in html


def test_dashboard_stocks_mode_null_leadership_board():
    """dashboard.html.j2 renders cleanly when leadership_board is None (panel absent)."""
    env = _full_env()
    vm = _base_vm_with_lb()
    vm["leadership_board"] = None
    html = env.get_template("dashboard.html.j2").render(**vm, mode="stocks")
    assert len(html) > 50_000
    assert "Leadership Board" not in html


# ── build_site._leadership_board_view unit tests ──────────────────────────────

def test_leadership_board_view_missing_m7(tmp_path, monkeypatch):
    """_leadership_board_view returns None when mag7_regime/latest.json is absent."""
    import types
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is None


def test_leadership_board_view_valid_m7_only(tmp_path, monkeypatch):
    """_leadership_board_view returns a dict with trend_state when m7 present."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL", "r5": 0.01, "r10": 0.02, "r20": 0.03,
                       "rs20": 0.01, "above50": True, "above200": True, "contrib10": 0.1}],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "sectordata").mkdir(parents=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    assert result["trend_state"] == "turning_up"
    assert "members" in result
    assert "sector_rs" in result


def test_leadership_board_view_no_trend_state(tmp_path, monkeypatch):
    """_leadership_board_view returns None when trend_state is missing."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps({"as_of": "2026-07-14"}))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is None


def test_leadership_board_view_sector_rs_enrichment(tmp_path, monkeypatch):
    """_leadership_board_view enriches sector_rs from sector_central.json."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up", "members": [],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    sc_dir = tmp_path / "site" / "sectordata"
    sc_dir.mkdir(parents=True)
    sc_doc = {
        "as_of": "2026-07-14",
        "sectors": [
            {"ticker": "XLK", "name": "Technology", "name_zh": "科技",
             "momentum": {"rs_rank": 1, "lead": "leading"},
             "conviction": {"label_en": "Cautious", "label_zh": "谨慎"}},
            {"ticker": "XLU", "name": "Utilities", "name_zh": "公用事业",
             "momentum": {"rs_rank": 11, "lead": "lagging"},
             "conviction": {"label_en": "Accumulate", "label_zh": "积极配置"}},
        ],
    }
    (sc_dir / "sector_central.json").write_text(json.dumps(sc_doc))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    assert len(result["sector_rs"]) == 2
    assert result["sector_rs"][0]["ticker"] == "XLK"
    assert result["sector_rs"][0]["rs_rank"] == 1
    assert result["sector_rs"][0]["lead"] == "leading"
    assert result["sector_rs"][1]["ticker"] == "XLU"
    assert result["sector_rs"][1]["rs_rank"] == 11


def test_leadership_board_view_earnings_stale_omitted(tmp_path, monkeypatch):
    """Earnings chip is omitted when as_of is stale (>7d old)."""
    import types
    import datetime
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL"}], "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    # Write stale earnings parquet
    try:
        import pandas as pd
        (tmp_path / "earnings").mkdir()
        stale_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        edf = pd.DataFrame({
            "next_date": ["2026-07-20"],
            "next_time": ["PMC"],
            "as_of": [stale_date + "T00:00:00+00:00"],
        }, index=pd.Index(["AAPL"], name="ticker"))
        edf.to_parquet(tmp_path / "earnings" / "earnings.parquet")
    except Exception:
        pytest.skip("pandas/pyarrow not available")
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / "sectordata").mkdir(parents=True, exist_ok=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    # earnings chip must be absent (stale as_of)
    aapl_member = next((m for m in result["members"] if m.get("sym") == "AAPL"), None)
    assert aapl_member is not None
    assert aapl_member.get("earnings") is None


# ── LRV lifecycle from radar.json (frozen-store fix, 2026-07-16) ──────────────
# The board's per-tile lifecycle used to read data/leader_radar/state_history
# .parquet, which sat frozen at its 2026-07-11 seed with no freshness gate.
# It now reads site/leaderradar/radar.json rows[].state behind an as_of gate.

def _radar_view(tmp_path, monkeypatch, radar_doc):
    """m7 fixture + optional radar.json; returns _leadership_board_view()."""
    import types
    (tmp_path / "mag7_regime").mkdir(exist_ok=True)
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL", "above50": True},
                      {"sym": "NVDA", "above50": False}],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir(exist_ok=True)
    if radar_doc is not None:
        rr_dir = tmp_path / "site" / "leaderradar"
        rr_dir.mkdir(parents=True, exist_ok=True)
        (rr_dir / "radar.json").write_text(json.dumps(radar_doc))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    return bs._leadership_board_view()


def _fresh_asof() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def test_view_lifecycle_from_fresh_radar(tmp_path, monkeypatch):
    """Fresh radar.json → rows[].state mapped onto members; not stale."""
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": _fresh_asof(), "stale": False,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"},
                 {"ticker": "NVDA", "state": "NONE"},
                 {"ticker": "ZZZZ", "state": "BREAKAWAY"}],  # non-M7: ignored
    })
    assert result is not None
    assert result["lifecycle_stale"] is False
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] == "QUIET_ACCUMULATION"
    assert by_sym["NVDA"]["lifecycle"] == "NONE"


def test_view_lifecycle_stale_radar_gated(tmp_path, monkeypatch):
    """as_of older than 7 calendar days → no lifecycle reads, stale disclosed."""
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": old, "stale": False,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"}],
    })
    assert result is not None
    assert result["lifecycle_stale"] is True
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] is None


def test_view_lifecycle_radar_absent(tmp_path, monkeypatch):
    """No radar.json at all → fail-open, stale disclosed, members lifecycle None."""
    result = _radar_view(tmp_path, monkeypatch, None)
    assert result is not None
    assert result["lifecycle_stale"] is True
    assert all(m["lifecycle"] is None for m in result["members"])


def test_view_lifecycle_radar_self_reported_stale(tmp_path, monkeypatch):
    """radar.json stale:true → gated even when as_of is fresh."""
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": _fresh_asof(), "stale": True,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"}],
    })
    assert result is not None
    assert result["lifecycle_stale"] is True
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] is None


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_footnote_stale_disclosure_renders():
    """lifecycle_stale → bilingual plain-word disclosure in the footnote."""
    env = _env()
    payload = dict(FULL_PAYLOAD)
    payload["lifecycle_stale"] = True
    html = env.from_string(RENDER_TMPL).render(d=payload)
    assert "Per-stock trend reads unavailable" in html
    assert "个股趋势读数暂不可用" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_footnote_no_disclosure_when_fresh_or_missing_key():
    """No stale line when lifecycle_stale is False — or absent (old payloads)."""
    env = _env()
    fresh = dict(FULL_PAYLOAD)
    fresh["lifecycle_stale"] = False
    html = env.from_string(RENDER_TMPL).render(d=fresh)
    assert "Per-stock trend reads unavailable" not in html
    # missing key entirely (pre-fix payload) must render safely without the line
    html2 = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "Per-stock trend reads unavailable" not in html2
