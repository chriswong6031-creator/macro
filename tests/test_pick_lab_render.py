"""Tests for engine/pick_lab/render.py and templates/us_stocks_lab.html.j2.

Covers:
  - build_vm() with full prod-shaped fixture (realistic tickers, mixed
    matured/accruing, some nulls, zh strings)
  - build_vm() with empty / None inputs (empty-state render)
  - render_page() writes valid HTML without raising
  - Bilingual spans present (l-en / l-zh)
  - No "validated" word anywhere (CI-enforced invariant)
  - No title= attributes containing CJK characters (CI-guarded)
  - Random control row is present in scoreboard
  - ACCRUING badge rendered for ACCRUING books
  - Tab structure: 5 data-tab-panel sections present
  - Template renders with empty dicts for all 5 tabs
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
#  Prod-shaped fixture data                                                    #
# --------------------------------------------------------------------------- #

def _make_scoreboard_row(
    engine_id: str,
    name_en: str,
    name_zh: str,
    family: str,
    ruler: str,
    n_fires: int = 0,
    n_open: int = 0,
    n_dates: int = 0,
    months_span: float | None = None,
    wr21_abs: float | None = None,
    wr21_excess: float | None = None,
    med_excess21: float | None = None,
    mfe_med: float | None = None,
    mae_med: float | None = None,
    asym: float | None = None,
    nav_excess_cum: float | None = None,
    max_dd: float | None = None,
    vs_random_lift: float | None = None,
    vs_universe_lift: float | None = None,
    status: str = "accruing",
    horizon_role: str = "entry",
) -> dict:
    return {
        "engine_id": engine_id,
        "name_en": name_en,
        "name_zh": name_zh,
        "family": family,
        "ruler": ruler,
        "horizon_role": horizon_role,
        "n_fires": n_fires,
        "n_open": n_open,
        "n_dates": n_dates,
        "months_span": months_span,
        "wr21_abs": wr21_abs,
        "wr21_excess": wr21_excess,
        "med_excess21": med_excess21,
        "mfe_med": mfe_med,
        "mae_med": mae_med,
        "asym": asym,
        "nav_excess_cum": nav_excess_cum,
        "max_dd": max_dd,
        "vs_random_lift": vs_random_lift,
        "vs_universe_lift": vs_universe_lift,
        "status": status,
    }


def _make_pick(ticker: str, rank: int, close: float, sector: str,
               why: list[str] | None = None,
               features: dict | None = None) -> dict:
    return {
        "ticker": ticker,
        "rank": rank,
        "close": close,
        "sector": sector,
        "why": why or ["1D✚ MACD×K/D", "deep<20"],
        "features": features or {"rsi14": "54.2", "calm": "0.72"},
    }


def _make_fire(ticker: str, fire_date: str, ret21_excess: float | None,
               matured: bool) -> dict:
    return {
        "ticker": ticker,
        "fire_date": fire_date,
        "ret21_excess": ret21_excess,
        "matured": matured,
    }


def _prod_fixture() -> tuple[dict, dict]:
    """Return (pick_lab_dict, longhold_dict) with realistic prod-shaped data."""
    # ---- scoreboard: 20 entry books ----
    scoreboard = [
        _make_scoreboard_row(
            "plab_1d_pure", "1D Pure (velocity gate)", "1日纯速 (动能门)", "A",
            "21d_spy_excess", n_fires=12, n_open=7, n_dates=9, months_span=0.6,
            wr21_abs=0.58, wr21_excess=0.04, med_excess21=0.02,
            mfe_med=0.08, mae_med=0.03, asym=2.1,
            nav_excess_cum=0.06, max_dd=-0.12,
            vs_random_lift=0.03, vs_universe_lift=0.01, status="accruing",
        ),
        _make_scoreboard_row(
            "plab_1d_regime", "1D Regime-filtered", "1日制度过滤", "A",
            "21d_spy_excess", n_fires=8, n_open=5, n_dates=6, months_span=0.4,
            wr21_abs=None, wr21_excess=None, status="accruing",
        ),
        _make_scoreboard_row(
            "plab_1d_sectorheat", "1D Sector-heat", "1日板块热度", "A",
            "21d_spy_excess", n_fires=5, n_open=3, status="accruing",
        ),
        _make_scoreboard_row(
            "plab_1d_blastoff", "1D Blastoff (3D gate miss)", "1日起飞 (3日门遗漏)", "A",
            "21d_spy_excess", n_fires=3, status="accruing",
        ),
        _make_scoreboard_row(
            "plab_breakout_vol", "Breakout + Volume", "突破+量能", "B",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_resid_mom", "Residual Momentum (no gate)", "残差动能 (无门控)", "B",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_otr_pullback", "On-the-Run Pullback", "热门板块回调", "B",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_hi_base", "High Base / Squeeze", "高位基建/盘整", "B",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_washout_deep", "Deep Washout + Structure", "深度洗盘+结构", "C",
            "21d_abs_reversion_capture_mfe_mae", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_sector_trough", "Sector Trough / Recovery", "板块底部/复苏", "C",
            "21d_abs_reversion_capture_mfe_mae", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_washout_clean", "Clean Washout (quality screen)", "优质洗盘", "C",
            "21d_abs_reversion_capture_mfe_mae", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_edge_pure", "EDGE Pure (no gate)", "纯EDGE (无门控)", "D",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_edge_1d", "EDGE x 1D Grid", "EDGE×1日网格", "D",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_quality_pullback", "Quality Pullback", "优质回调", "D",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_beta_squeeze", "Beta Squeeze", "Beta压缩", "E",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_revision_accel", "Revision Acceleration", "预测加速上修", "E",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_flagship_nogate", "Flagship (no oscillator gate)", "旗舰 (无振荡器门控)", "F",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_flagship_t3t4", "Flagship T3/T4 (early tiers)", "旗舰T3/T4 (早期档位)", "F",
            "21d_spy_excess", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_topping_avoid", "Topping Avoid (INVERSE)", "顶部规避 (反向)", "F",
            "21d_spy_excess_avoid_accuracy", status="accruing",
        ),
        _make_scoreboard_row(
            "plab_random_ctrl", "Random Control", "随机基准", "F",
            "21d_spy_excess",
            n_fires=12, n_open=0, n_dates=10, months_span=0.5,
            wr21_abs=0.50, wr21_excess=0.0, med_excess21=0.0,
            nav_excess_cum=0.0, max_dd=-0.08, status="accruing",
        ),
    ]

    # ---- books: per-book pick + fire data ----
    books = {
        "plab_1d_pure": {
            "picks_today": [
                _make_pick("NVDA", 1, 128.45, "Information Technology",
                           why=["1D✚ MACD×K/D", "deep<20", "EDGE q1"],
                           features={"rsi14": "54.2", "calm": "0.80", "edge_alpha": "1.23"}),
                _make_pick("MSFT", 2, 445.30, "Information Technology",
                           why=["1D✚ MACD×K/D", "deep<20"],
                           features={"rsi14": "52.1", "calm": "0.75"}),
                _make_pick("META", 3, 588.10, "Communication Services",
                           why=["1D✚ MACD×K/D", "sector heating"],
                           features={"rsi14": "59.3", "calm": "0.70"}),
            ],
            "recent_fires": [
                _make_fire("AMZN", "2026-06-15", 0.028, True),
                _make_fire("GOOGL", "2026-06-18", -0.012, True),
                _make_fire("TSLA", "2026-06-22", None, False),  # null ret (open)
            ],
        },
        "plab_1d_regime": {
            "picks_today": [
                _make_pick("AAPL", 1, 210.50, "Information Technology",
                           why=["1D MACD✚", "calm≥0.5", "EDGE q2"]),
            ],
            "recent_fires": [],
        },
        "plab_1d_sectorheat": {
            "picks_today": [],
            "recent_fires": [],
        },
        "plab_1d_blastoff": {
            "picks_today": [
                _make_pick("AMD", 1, 155.20, "Information Technology",
                           why=["1D blastoff", "3D not yet crossed", "above 200MA"],
                           features={"ext_grade": "none"}),
            ],
            "recent_fires": [],
        },
        "plab_random_ctrl": {
            "picks_today": [
                _make_pick("XYZ1", 1, 42.10, "Industrials"),
                _make_pick("XYZ2", 2, 88.30, "Health Care"),
            ],
            "recent_fires": [],
        },
        "plab_topping_avoid": {
            "picks_today": [
                _make_pick("SPG", 1, 155.50, "Real Estate",
                           why=["TOP WATCH", "rsi>70", "take-profits sector"]),
            ],
            "recent_fires": [],
        },
    }

    # ---- lanes ----
    lanes = {
        "on_the_run_stocks": [
            _make_pick("NVDA", 1, 128.45, "Information Technology",
                       why=["on_the_run sector", "above 200MA", "pullback"]),
            _make_pick("SMCI", 2, 44.20, "Information Technology",
                       why=["on_the_run sector"]),
        ],
        "take_profits_stocks": [
            _make_pick("SPG", 1, 155.50, "Real Estate",
                       why=["TOP WATCH", "rsi>70"]),
        ],
    }

    pick_lab = {
        "schema": "pick_lab.v1",
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T22:30:00Z",
        "regime": {"calm": 0.72, "stress": 0.18, "liquidity": "neutral"},
        "scoreboard": scoreboard,
        "books": books,
        "lanes": lanes,
        "method_note": "Snapshot from 2026-07-09 nightly run. 20 entry books active.",
    }

    longhold = {
        "schema": "pick_lab_longhold.v1",
        "as_of": "2026-07-09",
        "books": {
            "plab_lh_compounder": {
                "picks_today": [
                    _make_pick("MSFT", 1, 445.30, "Information Technology",
                               why=["axis_quality top-decile", "compounder archetype", "no dilution"]),
                    _make_pick("AAPL", 2, 210.50, "Information Technology",
                               why=["axis_quality top-decile", "secular_growth"]),
                ],
                "recent_fires": [
                    _make_fire("GOOG", "2026-06-01", None, False),  # open, no grade yet
                ],
            },
            "plab_lh_edge_durability": {
                "picks_today": [
                    _make_pick("V", 1, 290.10, "Financials",
                               why=["EDGE top-decile", "quality above median"]),
                ],
                "recent_fires": [],
            },
            "plab_lh_washout_survivor": {
                "picks_today": [],
                "recent_fires": [],
            },
        },
        "first_maturation_eta": "~2027-01",
    }

    return pick_lab, longhold


# --------------------------------------------------------------------------- #
#  Jinja env mirroring render.py's setup                                      #
# --------------------------------------------------------------------------- #

def _env():
    from jinja2 import Environment, FileSystemLoader
    return Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=True,
    )


# --------------------------------------------------------------------------- #
#  build_vm tests                                                              #
# --------------------------------------------------------------------------- #

class TestBuildVm:
    def test_empty_state_does_not_raise(self):
        from engine.pick_lab.render import build_vm
        vm = build_vm(None, None)
        assert vm["empty"] is True
        assert vm["scoreboard"] == []
        assert vm["velocity_books"] == [] or all(
            b["picks_today"] == [] for b in vm["velocity_books"]
        )

    def test_full_fixture_populated(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        assert vm["empty"] is False
        assert vm["as_of"] == "2026-07-09"
        assert len(vm["scoreboard"]) == 20

    def test_scoreboard_enriched(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        # first row is 1d_pure with some data
        row = next(r for r in vm["scoreboard"] if r["engine_id"] == "plab_1d_pure")
        assert row["wr21_abs_fmt"] == "58.0%"
        assert row["wr21_excess_fmt"] == "+4.0%"
        assert row["n_fires_fmt"] == "12"
        assert row["status_badge"]["css"] == "badge-accruing"

    def test_random_control_flagged(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        rand_row = next(r for r in vm["scoreboard"] if r["engine_id"] == "plab_random_ctrl")
        assert rand_row["is_random"] is True
        # all other rows are not random
        others = [r for r in vm["scoreboard"] if r["engine_id"] != "plab_random_ctrl"]
        assert all(not r["is_random"] for r in others)

    def test_inverse_book_flagged(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        inv_row = next(r for r in vm["scoreboard"] if r["engine_id"] == "plab_topping_avoid")
        assert inv_row["is_inverse"] is True

    def test_velocity_books_have_picks(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        # plab_1d_pure has 3 picks in fixture
        pure = next(b for b in vm["velocity_books"] if b["engine_id"] == "plab_1d_pure")
        assert len(pure["picks_today"]) == 3
        assert pure["picks_today"][0]["close_fmt"] == "$128.45"

    def test_otr_and_tp_lanes(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        assert len(vm["otr_stocks"]) == 2
        assert len(vm["tp_stocks"]) == 1
        assert vm["tp_stocks"][0]["ticker"] == "SPG"

    def test_longhold_books_populated(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        assert len(vm["lh_books"]) == 3
        comp = next(b for b in vm["lh_books"] if b["engine_id"] == "plab_lh_compounder")
        assert len(comp["picks_today"]) == 2

    def test_first_maturation_eta_propagated(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        assert vm["first_maturation_eta"] == "~2027-01"

    def test_eta_fallback_when_longhold_none(self):
        from engine.pick_lab.render import build_vm
        pl, _ = _prod_fixture()
        vm = build_vm(pl, None)
        assert vm["first_maturation_eta"] == "~2027-01"

    def test_null_metrics_format_as_dash(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        # plab_1d_regime has wr21_abs=None in the fixture
        row = next(r for r in vm["scoreboard"] if r["engine_id"] == "plab_1d_regime")
        assert row["wr21_abs_fmt"] == "—"
        assert row["wr21_excess_fmt"] == "—"

    def test_authority_is_display_only(self):
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        assert vm["authority"] == "display_only"


# --------------------------------------------------------------------------- #
#  Template render tests                                                       #
# --------------------------------------------------------------------------- #

class TestTemplateRender:
    def _render_full(self) -> str:
        from engine.pick_lab.render import build_vm
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        return _env().get_template("us_stocks_lab.html.j2").render(**vm)

    def _render_empty(self) -> str:
        from engine.pick_lab.render import build_vm
        vm = build_vm(None, None)
        return _env().get_template("us_stocks_lab.html.j2").render(**vm)

    def test_full_render_does_not_raise(self):
        html = self._render_full()
        assert len(html) > 5000

    def test_empty_render_does_not_raise(self):
        html = self._render_empty()
        assert len(html) > 1000

    def test_no_validated_word(self):
        """CI-enforced invariant: the word 'validated' must never appear."""
        html = self._render_full()
        # case-insensitive search
        assert "validated" not in html.lower(), (
            "Found forbidden word 'validated' in rendered HTML"
        )

    def test_no_validated_word_empty(self):
        html = self._render_empty()
        assert "validated" not in html.lower()

    def test_five_tab_panels_present(self):
        """Exactly 7 data-tab-panel section elements (scoreboard/velocity/allbooks/beta/longhold/accountability/method).
        SA-W5 added the Accountability tab. We count only <section ...> tags, not JS querySelector strings."""
        html = self._render_full()
        # match only <section ...> opening tags that carry data-tab-panel
        panels = re.findall(r'<section[^>]+data-tab-panel="[^"]+"', html)
        assert len(panels) == 7, f"Expected 7 tab panels, got {len(panels)}"

    def test_five_tab_buttons(self):
        html = self._render_full()
        btns = re.findall(r'data-tab="[^"]+"', html)
        assert len(btns) == 7  # SA-W5: +1 for Accountability tab

    def test_bilingual_spans_present(self):
        html = self._render_full()
        assert 'class="l-en"' in html
        assert 'class="l-zh"' in html

    def test_accruing_badge_present(self):
        html = self._render_full()
        assert "ACCRUING" in html
        assert "累积中" in html

    def test_random_control_yardstick_marked(self):
        html = self._render_full()
        assert "yardstick" in html or "基准" in html

    def test_scoreboard_table_contains_family_badges(self):
        html = self._render_full()
        # family-badge class is rendered in the scoreboard table
        assert "family-badge" in html
        # All family letters present
        for fam in ("A", "B", "C", "D", "E", "F"):
            assert f">{fam}<" in html or f">{fam} " in html or f' class="family-badge">{fam}<' in html

    def test_nvda_pick_appears(self):
        html = self._render_full()
        assert "NVDA" in html

    def test_take_profits_not_buys_warning(self):
        html = self._render_full()
        assert "NOT" in html  # the "NOT buys" warning label

    def test_lh_firewall_note_present(self):
        html = self._render_full()
        assert "PL-R6" in html

    def test_first_maturation_eta_rendered(self):
        html = self._render_full()
        assert "2027-01" in html

    def test_empty_state_hero_rendered(self):
        html = self._render_empty()
        # all 5 tabs show "first accrual tonight" (l-en version)
        count = html.count("First accrual tonight")
        assert count >= 1, "Empty state hero not found"

    def test_no_title_cjk_attributes(self):
        """CI guard: no CJK characters in title= attributes."""
        html = self._render_full()
        # find all title="..." values
        title_attrs = re.findall(r'title="([^"]*)"', html)
        cjk_range = re.compile(r'[一-鿿㐀-䶿]')
        violations = [v for v in title_attrs if cjk_range.search(v)]
        assert not violations, (
            f"Found CJK in title= attributes: {violations[:3]}"
        )

    def test_theme_js_at_end_of_body(self):
        html = self._render_full()
        body_close = html.rfind("</body>")
        theme_js_pos = html.rfind("theme.js")
        assert theme_js_pos != -1, "theme.js not found"
        assert theme_js_pos < body_close, "theme.js must be before </body>"
        # also must be in the bottom half of the page (after main content)
        half = len(html) // 2
        assert theme_js_pos > half, "theme.js should be at end of body, not head"

    def test_site_nav_included(self):
        html = self._render_full()
        assert "site-nav" in html

    def test_inline_js_has_tab_switch_logic(self):
        html = self._render_full()
        assert "data-tab-panel" in html
        assert "classList.remove('on')" in html or "classList.remove" in html


# --------------------------------------------------------------------------- #
#  render_page() integration test                                              #
# --------------------------------------------------------------------------- #

class TestRenderPage:
    def test_render_page_writes_file(self, tmp_path):
        from engine.pick_lab.render import build_vm, render_page
        pl, lh = _prod_fixture()
        vm = build_vm(pl, lh)
        render_page(vm, site=tmp_path)
        out = tmp_path / "us_stocks_lab.html"
        assert out.exists()
        html = out.read_text()
        assert len(html) > 5000
        assert "NVDA" in html

    def test_render_page_empty_state(self, tmp_path):
        from engine.pick_lab.render import build_vm, render_page
        vm = build_vm(None, None)
        render_page(vm, site=tmp_path)
        out = tmp_path / "us_stocks_lab.html"
        assert out.exists()
        html = out.read_text()
        assert "First accrual tonight" in html

    def test_render_page_injects_data_base_shim(self, tmp_path):
        """write_page() must inject the data-base shim per lib/pages.py contract."""
        from engine.pick_lab.render import build_vm, render_page
        vm = build_vm(None, None)
        render_page(vm, site=tmp_path)
        html = (tmp_path / "us_stocks_lab.html").read_text()
        assert "data-dbase" in html, "data_base.js shim not injected"


# --------------------------------------------------------------------------- #
#  Dashboard template regression: Lab button present                           #
# --------------------------------------------------------------------------- #

class TestDashboardLabButton:
    def test_lab_link_in_stocks_header(self):
        """The Lab button must appear in the stocks-header panel region."""
        template_path = ROOT / "templates" / "dashboard.html.j2"
        src = template_path.read_text()
        # The stocks-header div must contain the lab link.
        # Find the <div id="stocks-header"> block and check the region until </div>.
        hd_start = src.find('id="stocks-header"')
        assert hd_start != -1, "stocks-header panel not found"
        # The lab link is inside the paragraph at the end of this panel.
        # Find the closing of this panel block (  </div>\n  {% endif %})
        panel_close = src.find("  {% endif %}", hd_start)
        block = src[hd_start:panel_close]
        assert "us_stocks_lab.html" in block, (
            "Lab link not found in the stocks-header panel block\n" + block[:500]
        )
        assert "Pick Lab" in block or "选股实验室" in block

    def test_lab_link_uses_emoji(self):
        src = (ROOT / "templates" / "dashboard.html.j2").read_text()
        assert "🧪" in src, "Lab emoji not found in dashboard template"


# --------------------------------------------------------------------------- #
#  Dashboard render smoke: both modes must still render after edit             #
# --------------------------------------------------------------------------- #

class TestDashboardRenderSmoke:
    """Mirrors the critical subset of test_dashboard_template_render.py so we
    know our dashboard.html.j2 edit (Lab button) did not break either mode."""

    def _board_row(self, **overrides) -> dict:
        row = {
            "ticker": "ACME", "name": "Acme Corp",
            "sector": "Information Technology", "lane": "bottoming",
            "signal": None, "signal_date": "2026-07-01",
            "conviction": None, "alpha": 0.42, "alpha_z": 0.42,
            "alpha_entry": None, "alpha_sector_rank": 3, "alpha_sector_n": 25,
            "sector_rank": 3, "sector_n": 25, "price": 42.5,
            "off_high": -18.0, "ext_z": 0.1, "demand": None, "sue_z": None,
            "insider_buyers": None, "insider_net_mn": None, "insider_bps": None,
            "news_burst": None, "gex_confirm": None, "confluence_plus": None,
            "altdata": None, "smartmoney_chip": None, "eq_grade": None,
            "eq_grade_zh": None, "eq_dir": None, "eq_badge": None,
            "stop_guidance": None, "spark_svg": None,
            "sector_capitulating": None, "hold": None, "dir": None,
            "days": None, "count": None, "age_short": None, "age_short_zh": None,
            "align_tier": None, "urgency": None, "risk_sizing": None,
            "label": None, "entry_signal": None, "above_trend": None,
            "dossier": {
                "action": {"verb": "WAIT", "verb_zh": "等待", "tone": "wait"},
                "why_now": "Weekly cross fresh; daily reset underway.",
                "no_buy_reasons": ["freshness_expired", "risk_veto"],
                "stale_flags": ["insider stale 45d"],
                "authority_level": {"tier": "T2 calibrated", "css": "trust-t2"},
            },
        }
        row.update(overrides)
        return row

    def _base_vm(self) -> dict:
        return dict(
            latest={
                "date": "2026-07-09", "quad": "Q2", "quad_name": "Reflation",
                "label": "Q2 — Reflation", "confidence": 0.72,
                "fed_stance": None, "dislocation": None, "turning_point": None,
                "risk_radar": None, "rate_inflation_transmission": None,
                "cross_asset_confirm": None, "transition_state": "stable",
                "liquidity_overlay": "neutral", "conditions": None,
                "risk_state": None, "cycle_tag": "mid",
            },
            mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
            prediction_markets=None, narrative_regime=None, ndi=None,
            macro_news=None, macro_brief=None,
            macro_news_disclaimer="", macro_news_disclaimer_zh="",
            alerts=[], pb=None, month_name="July",
            commodities=[], sector_timing={},
            action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
            top_setups=[],
            us_standouts={
                "buy": [
                    self._board_row(),
                    self._board_row(ticker="ZEUS", name="Zeus Industries", lane=None, dossier=None),
                ],
                "eligible": 2,
            },
            us_board_outcomes=None, market_gamma=None,
            components_confirming=[], components_contradicting=[],
            flip_plain=None, internals=[], size_style=[],
            breadth_div=None, breadth_panel=None, adv_breadth=None,
            sector_setups=None, generated_utc="2026-07-09 06:00",
            chart_liquidity=None, chart_credit_breadth=None,
            market_tiles=[], vix=None, chart_vix=None,
            positioning=[], holdings_changes=[], holdings_threshold=5.0,
            accumulation=[], flows_html="", health=[], factor_leadership=None,
            nowcast_hist=None, stance=None, index_health=[], alloc_card=None,
            risk_model=None, chart_risk_model=None, chart_curve=None,
            chart_vix_term=None, cross_asset=None, fear_euphoria=None,
            regime_snap=None, market_state=None, signal_stack=None,
            vol_shock=None, froth_fragility=None, fear_greed=None,
            sector_heat=None, dispersion_regime=None,
        )

    def _dash_env(self):
        import jinja2
        from engine import i18n
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))
        env.filters["min"] = lambda seq: min(seq)
        env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
        return env

    def test_stocks_mode_renders_after_lab_edit(self):
        html = self._dash_env().get_template("dashboard.html.j2").render(
            **self._base_vm(), mode="stocks"
        )
        assert len(html) > 50_000
        assert "ACME" in html

    def test_macro_mode_renders_after_lab_edit(self):
        html = self._dash_env().get_template("dashboard.html.j2").render(
            **self._base_vm(), mode="macro"
        )
        assert len(html) > 50_000

    def test_lab_link_rendered_in_stocks_mode(self):
        html = self._dash_env().get_template("dashboard.html.j2").render(
            **self._base_vm(), mode="stocks"
        )
        assert "us_stocks_lab.html" in html

    def test_lab_link_absent_in_macro_mode(self):
        """Lab button is inside {% if mode == 'stocks' %} so it must NOT appear in macro mode."""
        html = self._dash_env().get_template("dashboard.html.j2").render(
            **self._base_vm(), mode="macro"
        )
        assert "us_stocks_lab.html" not in html
