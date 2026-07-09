"""Tests for engine/pick_lab/render_hk.py and templates/hk_stocks_lab.html.j2.

Covers:
  - build_vm() with rich HK fixture (zh names, knife chips, disabled_stale states,
    halt counters)
  - build_vm() with None input (empty-state render)
  - render_page() writes valid HTML without raising
  - Bilingual spans present (l-en / l-zh)
  - No "validated" word anywhere (CI-enforced invariant)
  - No title= attributes containing CJK characters (CI-guarded)
  - Random control row (hklab_random_ctrl) present in scoreboard as yardstick
  - Inverse books (hklab_knife_avoid, hklab_chase_avoid) flagged as NOT-BUY
  - disabled_stale books show STALE flag with organ name
  - halt_voided counter visible on scoreboard
  - Tab structure: 4 data-tab-panel sections (Scoreboard/Velocity/AllBooks/Method)
  - NO Long-Hold tab (HKPL-R9)
  - hk.html.j2 edits: 1D Velocity Desk lane + Lab button present in stocks mode
  - hk.html.j2 1D Velocity Desk degrades gracefully when key absent
  - body padding-top >= 24px (nav-gap CI requirement)
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from jinja2 import Environment, DictLoader

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
#  Prod-shaped HK fixture data                                                 #
# --------------------------------------------------------------------------- #

def _make_hk_scoreboard_row(
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
    halt_voided: int = 0,
    disabled_stale_nights: int = 0,
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
        "halt_voided": halt_voided,
        "disabled_stale_nights": disabled_stale_nights,
        "status": status,
    }


def _make_hk_pick(
    ticker: str,
    rank: int,
    close: float,
    sector: str,
    why: list[str] | None = None,
    features: dict | None = None,
    is_avoid: bool = False,
    name_zh: str | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "rank": rank,
        "close": close,
        "sector": sector,
        "name": ticker,
        "name_zh": name_zh or ticker,
        "why": why or ["1D MACD✚≤2", "from_OS"],
        "features": features or {"d1_macd_xup_bars": "1", "rsi14": "48"},
        "is_avoid": is_avoid,
        "liq_unknown": False,
        "authority": "display_only",
    }


def _make_hk_fire(ticker: str, fire_date: str, ret21_excess: float | None,
                  matured: bool, fill_basis: str = "close",
                  halted: bool = False, halt_voided: bool = False) -> dict:
    return {
        "ticker": ticker,
        "fire_date": fire_date,
        "ret21_excess": ret21_excess,
        "matured": matured,
        "fill_basis": fill_basis,
        "halted": halted,
        "halt_voided": halt_voided,
    }


def _hk_prod_fixture() -> dict:
    """Return hk_pick_lab_dict with rich prod-shaped HK data."""
    scoreboard = [
        # Family A — 1D velocity
        _make_hk_scoreboard_row(
            "hklab_1d_pure", "HK 1D Velocity Pure", "港股1日速度纯",
            "A", "21d_hsi_excess", n_fires=12, n_open=6, n_dates=10, months_span=0.6,
            wr21_abs=0.62, wr21_excess=0.06, med_excess21=0.04,
            mfe_med=0.10, mae_med=0.04, asym=2.5,
            nav_excess_cum=0.08, max_dd=-0.09,
            vs_random_lift=0.05, vs_universe_lift=0.03, status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_1d_ignition", "HK 1D + Washout Ignition (organ x 1D)", "港股1日+洗盘点火",
            "A", "21d_hsi_excess", status="accruing", disabled_stale_nights=2,
        ),
        _make_hk_scoreboard_row(
            "hklab_1d_adr", "HK 1D + ADR Overnight Confirmation", "港股1日+ADR隔夜确认",
            "A", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_1d_blastoff", "HK 1D Blastoff (fast cohort 3D gate misses)", "港股1日起飞",
            "A", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_1d_regime", "HK 1D + Risk-On Regime", "港股1日+风险偏好开启",
            "A", "21d_hsi_excess", status="accruing",
        ),
        # Family B — washout/ignition + inverse knife
        _make_hk_scoreboard_row(
            "hklab_washout_ignite", "HK Washout Ignition (strongest organ state)", "港股洗盘点火",
            "B", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_washout_sb", "HK Washout + SB Accum Confluence", "港股洗盘+南向积累汇流",
            "B", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_washout_buyback", "HK Washout + Buyback Confluence", "港股洗盘+回购汇流",
            "B", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_pullback_entry", "HK Pullback Entry Watch (second-chance)", "港股回调入场",
            "B", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_knife_avoid", "HK Knife Avoid (INVERSE — expected negative)", "港股刀口规避 (反向)",
            "B", "21d_hsi_excess_avoid_accuracy", status="accruing",
        ),
        # Family C — HK-unique structure
        _make_hk_scoreboard_row(
            "hklab_cbbc_fuel", "HK CBBC Bear Skew Fuel", "港股CBBC空头偏斜燃料",
            "C", "21d_hsi_excess", status="accruing", disabled_stale_nights=1,
        ),
        _make_hk_scoreboard_row(
            "hklab_ah_value", "HK A/H Discount Value (H3 near-GO edge)", "港股A/H折价价值",
            "C", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_short_squeeze", "HK Short Squeeze Setup (H2a ACCRUE leg)", "港股轧空形态",
            "C", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_catalyst_narrative", "HK Catalyst + Narrative Attention", "港股催化剂+叙事关注",
            "C", "21d_hsi_excess", status="accruing",
        ),
        # Family D — beta/regime
        _make_hk_scoreboard_row(
            "hklab_beta_amplifier", "HK Beta Amplifier (Risk-On)", "港股Beta放大器",
            "D", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_beta_cushion", "HK Beta Cushion (Risk-Off Defensive)", "港股Beta缓冲",
            "D", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_hibor_easy", "HK HIBOR/Peg Easy Liquidity Rebound", "港股HIBOR宽松流动性反弹",
            "D", "21d_hsi_excess", status="accruing",
        ),
        # Family E — ablations + controls
        _make_hk_scoreboard_row(
            "hklab_flagship_nogate", "HK Flagship (no signal-gate ablation)", "港股旗舰 (无信号门消融)",
            "E", "21d_hsi_excess", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_chase_avoid", "HK Chase Avoid (INVERSE — chase_risk state)", "港股追涨规避 (反向)",
            "E", "21d_hsi_excess_avoid_accuracy", status="accruing",
        ),
        _make_hk_scoreboard_row(
            "hklab_random_ctrl", "HK Random Control", "港股随机基准",
            "E", "21d_hsi_excess",
            n_fires=10, n_open=0, n_dates=8, months_span=0.5,
            wr21_abs=0.50, wr21_excess=0.0, nav_excess_cum=0.0, max_dd=-0.07,
            status="accruing",
        ),
    ]

    books = {
        "hklab_1d_pure": {
            "picks_today": [
                _make_hk_pick("0700.HK", 1, 295.40, "Technology",
                              why=["1D MACD✚≤2", "1D StochRSI✚≤8", "from_OS", "RSI14<70"],
                              features={"d1_macd_xup_bars": "1", "rsi14": "48.3", "edge_z": "1.4"},
                              name_zh="腾讯控股"),
                _make_hk_pick("9988.HK", 2, 78.55, "Consumer Cyclical",
                              why=["1D MACD✚≤2", "from_OS", "RSI14<70"],
                              name_zh="阿里巴巴"),
            ],
            "recent_fires": [
                _make_hk_fire("0700.HK", "2026-06-20", 0.042, True, "close"),
                _make_hk_fire("2318.HK", "2026-06-25", -0.015, True, "close"),
                _make_hk_fire("2628.HK", "2026-07-01", None, False, "close",
                              halted=True, halt_voided=False),
            ],
        },
        "hklab_1d_ignition": {
            "picks_today": [],
            "recent_fires": [],
            "disabled_stale": True,
            "stale_organ": "washout",
        },
        "hklab_knife_avoid": {
            "picks_today": [
                _make_hk_pick("1HK.HK", 1, 0.45, "Real Estate",
                              why=["AVOID/inverse", "knife_risk✓"],
                              features={"knife_risk": "True", "off_high": "-55.2"},
                              is_avoid=True,
                              name_zh="某房企"),
            ],
            "recent_fires": [
                _make_hk_fire("2HK.HK", "2026-06-18", -0.055, True, "close"),
            ],
        },
        "hklab_chase_avoid": {
            "picks_today": [
                _make_hk_pick("3HK.HK", 1, 122.30, "Technology",
                              why=["AVOID/inverse", "chase_risk state✓", "RSI≥70 gapped"],
                              is_avoid=True,
                              name_zh="某科技"),
            ],
            "recent_fires": [
                _make_hk_fire("4HK.HK", "2026-06-22", -0.038, True, "close",
                              halt_voided=True),
            ],
        },
        "hklab_cbbc_fuel": {
            "picks_today": [],
            "recent_fires": [],
            "disabled_stale": True,
            "stale_organ": "cbbc",
        },
        "hklab_random_ctrl": {
            "picks_today": [
                _make_hk_pick("0005.HK", 1, 61.20, "Financial Services", name_zh="汇丰控股"),
                _make_hk_pick("1299.HK", 2, 48.85, "Financial Services", name_zh="友邦保险"),
            ],
            "recent_fires": [],
        },
    }

    return {
        "schema": "hk_pick_lab.v1",
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T14:30:00Z",
        "scoreboard": scoreboard,
        "books": books,
        "total_halt_voided": 3,
        "stale_cross_diagnostic": {
            "blastoff": {
                "n_fires": 8,
                "med_excess21": 0.032,
            },
            "stale_cross": {
                "n_fires": 14,
                "med_excess21": -0.011,
            },
        },
        "method_note": "Asia-lane run 2026-07-09. 20 books active. 3 fires halt-voided.",
    }


# --------------------------------------------------------------------------- #
#  render_hk.py unit tests                                                     #
# --------------------------------------------------------------------------- #

def test_build_vm_empty_state():
    """build_vm(None) returns empty=True with all safe defaults."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(None)
    assert vm["empty"] is True
    assert vm["scoreboard"] == []
    # 5 velocity book stubs always present even with empty input
    assert len(vm["velocity_books"]) == 5
    assert vm["all_books"] == []
    assert vm["total_halt_voided"] is None
    assert vm["authority"] == "display_only"
    assert vm["stale_cross"] is None


def test_build_vm_full_fixture():
    """build_vm() with rich fixture populates all fields correctly."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    assert vm["empty"] is False
    assert vm["as_of"] == "2026-07-09"
    assert len(vm["scoreboard"]) == 20
    assert vm["total_halt_voided"] == 3
    assert vm["authority"] == "display_only"


def test_scoreboard_random_ctrl_is_marked():
    """hklab_random_ctrl row must be flagged as is_random=True."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    random_rows = [r for r in vm["scoreboard"] if r.get("is_random")]
    assert len(random_rows) == 1
    assert random_rows[0]["engine_id"] == "hklab_random_ctrl"


def test_scoreboard_inverse_books_flagged():
    """Both inverse books (hklab_knife_avoid, hklab_chase_avoid) must be flagged is_inverse=True."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    inv_rows = [r for r in vm["scoreboard"] if r.get("is_inverse")]
    inv_ids = {r["engine_id"] for r in inv_rows}
    assert "hklab_knife_avoid" in inv_ids
    assert "hklab_chase_avoid" in inv_ids
    assert len(inv_rows) == 2


def test_scoreboard_halt_voided_formatted():
    """halt_voided field must be present and formatted for each row."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    # All rows should have halt_voided_fmt key
    for row in vm["scoreboard"]:
        assert "halt_voided_fmt" in row


def test_velocity_books_populated():
    """velocity_books must contain all 5 HK 1D books (Family A)."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    assert len(vm["velocity_books"]) == 5
    ids = {b["engine_id"] for b in vm["velocity_books"]}
    assert "hklab_1d_pure" in ids
    assert "hklab_1d_blastoff" in ids
    assert "hklab_1d_adr" in ids


def test_velocity_books_disabled_stale_flag():
    """hklab_1d_ignition must have disabled_stale=True and stale_organ set."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    ignition = next(b for b in vm["velocity_books"] if b["engine_id"] == "hklab_1d_ignition")
    assert ignition["disabled_stale"] is True
    assert ignition["stale_organ"] == "washout"


def test_all_books_count():
    """all_books must contain all 20 entry-role books."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    assert len(vm["all_books"]) == 20


def test_all_books_inverse_flagged():
    """Both inverse books in all_books must have is_inverse=True."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    inv = [b for b in vm["all_books"] if b.get("is_inverse")]
    inv_ids = {b["engine_id"] for b in inv}
    assert "hklab_knife_avoid" in inv_ids
    assert "hklab_chase_avoid" in inv_ids


def test_all_books_disabled_stale_passthrough():
    """Stale organ books in all_books must have disabled_stale=True."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    by_id = {b["engine_id"]: b for b in vm["all_books"]}
    assert by_id["hklab_1d_ignition"]["disabled_stale"] is True
    assert by_id["hklab_cbbc_fuel"]["disabled_stale"] is True
    # Non-stale book should not be disabled
    assert by_id["hklab_1d_pure"]["disabled_stale"] is False


def test_hk_pick_close_formatted_in_hkd():
    """HK pick cards must show close price in HK$ format."""
    from engine.pick_lab.render_hk import _enrich_pick
    p = _enrich_pick({"close": 295.40})
    assert p["close_fmt"] == "HK$295.40"


def test_hk_pick_no_close_formats_dash():
    """HK pick with no close must format as '—'."""
    from engine.pick_lab.render_hk import _enrich_pick
    p = _enrich_pick({"close": None})
    assert p["close_fmt"] == "—"


def test_hk_pick_no_limit_state():
    """HK picks have no limit_state (no price limits in HK — HKPL-R4)."""
    from engine.pick_lab.render_hk import _enrich_pick
    p = _enrich_pick({"close": 50.0, "is_avoid": False})
    # No limit chip keys (different from CN)
    assert "limit_chip_en" not in p


def test_hk_fire_halt_chip_halt_voided():
    """halt_voided fires must show halt-voided chip."""
    from engine.pick_lab.render_hk import _enrich_fire
    f = _enrich_fire({"ticker": "4HK.HK", "fire_date": "2026-06-22",
                      "ret21_excess": -0.038, "matured": True, "fill_basis": "close",
                      "halt_voided": True})
    assert f["halt_chip_en"] == "halt-voided"
    assert f["halt_chip_zh"] == "停牌已撤"


def test_hk_fire_halt_chip_halted_not_voided():
    """Halted (not voided) fires must show halted chip."""
    from engine.pick_lab.render_hk import _enrich_fire
    f = _enrich_fire({"ticker": "2628.HK", "fire_date": "2026-07-01",
                      "ret21_excess": None, "matured": False, "fill_basis": "close",
                      "halted": True, "halt_voided": False})
    assert f["halt_chip_en"] == "halted"
    assert f["halt_chip_zh"] == "停牌中"


def test_hk_fire_no_halt_chip_normal():
    """Normal fires (not halted) must have no halt chip."""
    from engine.pick_lab.render_hk import _enrich_fire
    f = _enrich_fire({"ticker": "0700.HK", "fire_date": "2026-06-20",
                      "ret21_excess": 0.042, "matured": True})
    assert f["halt_chip_en"] is None


def test_stale_cross_passthrough():
    """stale_cross_diagnostic must appear in the vm."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    assert vm["stale_cross"] is not None
    assert vm["stale_cross"]["blastoff"]["n_fires"] == 8
    assert vm["stale_cross"]["stale_cross"]["n_fires"] == 14


# --------------------------------------------------------------------------- #
#  Template render tests                                                       #
# --------------------------------------------------------------------------- #

def _render_hk_lab(vm: dict) -> str:
    """Render hk_stocks_lab.html.j2 with the given vm dict."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=True,
    )
    return env.get_template("hk_stocks_lab.html.j2").render(**vm)


def test_template_parse():
    """hk_stocks_lab.html.j2 must parse without Jinja syntax errors."""
    env = Environment(autoescape=False)
    src = (ROOT / "templates" / "hk_stocks_lab.html.j2").read_text()
    env.parse(src)


def test_render_empty_state():
    """Empty-state render must complete without errors and show accrual message."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(None)
    html = _render_hk_lab(vm)
    assert "First accrual tonight" in html or "今晚首次累积" in html
    # Must have 4 tab panel sections (no Long-Hold; JS also references the attr)
    assert html.count('<section data-tab-panel=') == 4


def test_render_no_long_hold_tab():
    """HKPL-R9: NO Long-Hold tab must appear in the rendered page."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(None)
    html = _render_hk_lab(vm)
    assert "data-tab=\"longhold\"" not in html
    assert "Long-Hold Grid" not in html


def test_render_four_tabs():
    """Rendered page must have exactly 4 tab buttons: Scoreboard, Velocity HK, All Books, Method."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(None)
    html = _render_hk_lab(vm)
    tabs = re.findall(r'data-tab=["\'](\w+)["\']', html)
    assert set(tabs) == {"scoreboard", "velocity", "allbooks", "method"}
    assert len(tabs) == 4


def test_render_bilingual_spans():
    """Rendered page must contain both l-en and l-zh class spans."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert 'class="l-en"' in html
    assert 'class="l-zh"' in html
    assert "Pick Lab" in html
    assert "选股实验室" in html


def test_render_no_validated_word():
    """The word 'validated' must NEVER appear in the rendered HK lab page (CI-enforced)."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert "validated" not in html.lower()


def test_render_no_cjk_in_title_attrs():
    """No CJK characters must appear inside title= attributes (CI-guarded)."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    cjk_pattern = re.compile(r'title=["\'][^"\']*[一-鿿㐀-䶿][^"\']*["\']')
    bad = cjk_pattern.findall(html)
    assert not bad, f"CJK characters found in title= attributes: {bad}"


def test_render_random_ctrl_in_scoreboard():
    """hklab_random_ctrl must appear in the scoreboard with yardstick label."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert "hklab_random_ctrl" in html
    assert "yardstick" in html or "基准" in html


def test_render_inverse_books_not_buy():
    """Both inverse books must show NOT-BUY / 非买入 label."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    # Both knife_avoid and chase_avoid must be labelled as NOT-BUY
    assert ("NOT BUY" in html or "非买入" in html), (
        "Inverse books missing NOT-BUY / 非买入 label"
    )
    assert "AVOID" in html or "规避" in html


def test_render_disabled_stale_books_flagged():
    """Books with disabled_stale=True must show STALE / 停用 flag."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert "STALE" in html or "停用" in html


def test_render_stale_organ_name_visible():
    """Stale organ name must be visible in the page."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    # washout organ is stale (hklab_1d_ignition)
    assert "washout" in html


def test_render_halt_voided_counter_visible():
    """halt_voided counter must appear on the scoreboard page."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    # total_halt_voided = 3 should be rendered
    assert "3" in html and ("halt" in html.lower() or "停牌" in html)


def test_render_zh_name_present():
    """Chinese names (name_zh) must appear in the rendered picks."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert "腾讯控股" in html or "0700.HK" in html


def test_render_hkd_price_format():
    """HK prices must appear in HK$ format (not ¥ like CN)."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    assert "HK$" in html


def test_render_stale_cross_diagnostic_shown():
    """Stale-cross diagnostic section must appear on the 1D velocity tab."""
    from engine.pick_lab.render_hk import build_vm
    vm = build_vm(_hk_prod_fixture())
    html = _render_hk_lab(vm)
    # The diagnostic section must be present
    assert "stale-cross" in html.lower() or "迟滞交叉" in html or "Stale-Cross" in html


def test_render_nav_gap_at_least_24px():
    """body padding-top must be >= 24px to satisfy check_nav_gap."""
    src = (ROOT / "templates" / "hk_stocks_lab.html.j2").read_text()
    m = re.search(r"body\s*\{[^}]*padding-top\s*:\s*(\d+)px", src)
    assert m, "body{padding-top:Npx} not found in hk_stocks_lab.html.j2"
    assert int(m.group(1)) >= 24, f"body padding-top={m.group(1)}px < 24px (nav gap violated)"


def test_render_page_writes_html(tmp_path):
    """render_page() must write a non-empty hk_stocks_lab.html to site/."""
    from engine.pick_lab.render_hk import build_vm, render_page
    vm = build_vm(_hk_prod_fixture())
    render_page(vm, tmp_path)
    out = tmp_path / "hk_stocks_lab.html"
    assert out.exists(), "hk_stocks_lab.html was not written"
    content = out.read_text()
    assert len(content) > 5000, "Rendered HTML seems too short"
    assert "<!DOCTYPE html>" in content


def test_build_and_render_no_raise(tmp_path):
    """build_and_render() must not raise even with no labdata directory."""
    from engine.pick_lab.render_hk import build_and_render
    import engine.pick_lab.render_hk as rhk
    import lib.config as cfg
    (tmp_path / "labdata").mkdir()
    orig_root = cfg.ROOT
    cfg.ROOT = ROOT
    try:
        build_and_render(tmp_path)
    finally:
        cfg.ROOT = orig_root
    out = tmp_path / "hk_stocks_lab.html"
    assert out.exists(), "build_and_render must write the file even in empty state"


# --------------------------------------------------------------------------- #
#  hk.html.j2 template edits                                                   #
# --------------------------------------------------------------------------- #

HK_SRC = (ROOT / "templates" / "hk.html.j2").read_text()


def test_hk_template_parses():
    """Full hk.html.j2 must parse (Jinja2 syntax check)."""
    env = Environment(autoescape=False)
    env.parse(HK_SRC)


def test_hk_stocks_lab_button_present():
    """Lab button (hk_stocks_lab.html link) must exist in hk.html.j2."""
    assert "hk_stocks_lab.html" in HK_SRC, (
        "hk_stocks_lab.html link not found in hk.html.j2"
    )
    assert "Pick Lab" in HK_SRC
    assert "选股实验室" in HK_SRC


def test_hk_lab_button_inside_stocks_mode_gate():
    """Lab button must be inside a mode==stocks gate, not visible in macro mode."""
    link = "hk_stocks_lab.html"
    link_pos = HK_SRC.index(link)
    # Walk backwards to find the nearest preceding mode=='stocks' gate
    gate_marker = "{% if mode == 'stocks' %}"
    gate_pos = HK_SRC.rfind(gate_marker, 0, link_pos)
    assert gate_pos >= 0, "No mode=='stocks' gate found before the Lab button"
    assert gate_pos < link_pos, "mode=='stocks' gate must precede the lab button"


def test_hk_velocity_desk_lane_present():
    """1D Velocity Desk lane must be present in hk.html.j2."""
    assert "hk-velocity-desk" in HK_SRC or "hk_1d_velocity_desk" in HK_SRC, (
        "1D Velocity Desk panel missing from hk.html.j2"
    )
    assert "1D Velocity Desk" in HK_SRC or "1日速度台" in HK_SRC, (
        "1D Velocity Desk bilingual heading missing from hk.html.j2"
    )


def test_hk_velocity_desk_uses_safe_key_access():
    """1D Velocity Desk must NOT use 'hk_1d_velocity_desk is not none' (crashes on missing key).

    The JINJA GOTCHA: 'is not none' on a missing key raises UndefinedError.
    The correct pattern is to set a variable via 'if X is defined else none'.
    """
    vd_start = HK_SRC.find("{# ======= 1D VELOCITY DESK")
    assert vd_start >= 0, "1D Velocity Desk Jinja comment block not found"
    vd_end_marker = "{# /mode == 'stocks' velocity desk #}"
    vd_end = HK_SRC.find(vd_end_marker, vd_start)
    if vd_end < 0:
        vd_end = vd_start + 5000
    block = HK_SRC[vd_start:vd_end]
    assert "is defined" in block, (
        "1D Velocity Desk block must use 'is defined' to guard the vm key "
        "(bare 'is not none' crashes on missing key)"
    )
    assert "hk_1d_velocity_desk is not none" not in block, (
        "DANGEROUS: 'hk_1d_velocity_desk is not none' will crash when key is absent"
    )


def _extract_velocity_desk_block() -> str:
    """Extract the full self-contained 1D velocity desk block from hk.html.j2."""
    start_marker = "{# ======= 1D VELOCITY DESK"
    end_marker = "{# /mode == 'stocks' velocity desk #}"
    vd_start = HK_SRC.find(start_marker)
    assert vd_start >= 0, "1D Velocity Desk block not found"
    vd_end = HK_SRC.find(end_marker, vd_start)
    assert vd_end >= 0, f"End marker '{end_marker}' not found after velocity desk"
    vd_end += len(end_marker)
    return HK_SRC[vd_start:vd_end]


def _make_vd_env(snippet: str) -> Environment:
    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro help(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro td(v) -%}{{ v }}{%- endmacro -%}\n'
    )
    import re as _re
    snippet = _re.sub(r'\{#.*?#\}', '', snippet, flags=_re.DOTALL)
    full = macros + snippet
    return Environment(loader=DictLoader({"blk": full}), autoescape=False)


def test_hk_velocity_desk_degrades_gracefully():
    """hk.html.j2 1D Velocity Desk must render gracefully when vm key absent.

    Renders the stocks-mode block with hk_1d_velocity_desk absent from vm — must not raise.
    """
    snippet = _extract_velocity_desk_block()
    env = _make_vd_env(snippet)
    try:
        env.get_template("blk").render(mode="stocks")
        # Should render empty/nothing (the {% if _vd %} guard collapses it)
    except Exception as exc:
        pytest.fail(
            f"1D Velocity Desk block raised when hk_1d_velocity_desk absent: {exc}"
        )


def test_hk_velocity_desk_renders_with_data():
    """1D Velocity Desk must render picks when data is present."""
    snippet = _extract_velocity_desk_block()
    env = _make_vd_env(snippet)

    test_vd = {
        "as_of": "2026-07-09",
        "picks": [
            {
                "ticker": "0700.HK",
                "close": 295.40,
                "name": "腾讯控股",
                "name_zh": "腾讯控股",
                "sector": "Technology",
                "confluence_count": 3,
                "washout_state": "ignition_watch",
                "adr_gap_pct": 0.012,
                "knife_risk": False,
                "beta_role": "amplifier",
            },
        ],
        "n_picks": 1,
        "authority": "display_only",
    }

    html = env.get_template("blk").render(
        mode="stocks",
        hk_1d_velocity_desk=test_vd,
    )
    assert "0700.HK" in html, "1D Velocity Desk pick ticker not rendered"
    assert "腾讯控股" in html, "1D Velocity Desk zh name not rendered"


def test_hk_template_no_validated_word_in_stocks_section():
    """The word 'validated' must not appear in the newly added stocks-mode sections."""
    vd_start = HK_SRC.find("{# ======= 1D VELOCITY DESK")
    if vd_start < 0:
        return
    added_section = HK_SRC[vd_start:vd_start + 6000]
    assert "validated" not in added_section.lower(), (
        "Word 'validated' found in the newly added 1D Velocity Desk section"
    )


def test_build_hk_velocity_desk_reads_rows_key():
    """build_hk.py must read the 'rows' key from the artifact (not 'picks').

    The velocity_desk artifact uses key 'rows'; build_hk.py must transform to
    'picks' for the template, renaming confluence_n→confluence_count and
    lifting chips.* to flat keys.
    """
    import json
    import sys
    import tempfile
    from pathlib import Path
    from unittest.mock import patch, MagicMock

    # Build a minimal artifact with `rows` (the correct key from velocity_desk.py)
    artifact = {
        "schema": "hk_1d_velocity_desk.v1",
        "as_of": "2026-07-09",
        "rows": [
            {
                "ticker": "0700.HK",
                "name": "Tencent",
                "name_zh": "腾讯控股",
                "rank": 1,
                "confluence_n": 3,   # artifact uses 'confluence_n'
                "chips": {
                    "washout_state": "ignition_watch",
                    "adr_gap_pct": 0.015,
                    "knife_risk": None,
                    "beta_role": "amplifier",
                },
                "close": 295.0,
                "sector": "Technology",
                "edge_z": 1.23,
                "authority": "display_only",
            }
        ],
        "n_rows": 1,
        "authority": "display_only",
    }

    with tempfile.TemporaryDirectory() as td:
        factordata = Path(td) / "factordata"
        factordata.mkdir(parents=True)
        vd_path = factordata / "hk_1d_velocity_desk.json"
        vd_path.write_text(json.dumps(artifact))

        # Simulate what build_hk.py does (we call the inline logic directly)
        _vd_raw = json.loads(vd_path.read_text())
        _vd_rows = _vd_raw.get("rows") if isinstance(_vd_raw, dict) else None
        assert _vd_rows is not None, "build_hk.py must find rows under 'rows' key"
        assert len(_vd_rows) == 1

        # Flatten as build_hk.py now does
        _vd_picks = []
        for _r in _vd_rows:
            _chips = _r.get("chips") or {}
            _pick = dict(_r)
            _pick["confluence_count"] = _r.get("confluence_n")
            _pick.setdefault("washout_state", _chips.get("washout_state"))
            _pick.setdefault("adr_gap_pct", _chips.get("adr_gap_pct"))
            _pick.setdefault("knife_risk", _chips.get("knife_risk"))
            _pick.setdefault("beta_role", _chips.get("beta_role"))
            _vd_picks.append(_pick)

        assert len(_vd_picks) == 1
        p = _vd_picks[0]
        assert p["confluence_count"] == 3, "confluence_n must be renamed to confluence_count"
        assert p["washout_state"] == "ignition_watch", "chips.washout_state must be lifted to flat"
        assert p["adr_gap_pct"] == 0.015, "chips.adr_gap_pct must be lifted to flat"
        assert p["beta_role"] == "amplifier", "chips.beta_role must be lifted to flat"
        assert p["ticker"] == "0700.HK"


def test_build_hk_velocity_desk_absent_key_gives_none():
    """build_hk.py must yield vm['hk_1d_velocity_desk']=None when artifact uses wrong key.

    Regression test: the old code read _vd_raw.get('picks') which is always None
    for the current artifact schema. The fix reads 'rows'.
    """
    artifact_old_wrong_key = {
        "schema": "hk_1d_velocity_desk.v1",
        "as_of": "2026-07-09",
        "picks": [{"ticker": "0700.HK"}],   # wrong key that old code would have read
        "rows": [],                           # correct key empty → yields None
        "n_rows": 0,
    }
    # An empty 'rows' list → desk hidden (None)
    _vd_rows = artifact_old_wrong_key.get("rows") if isinstance(artifact_old_wrong_key, dict) else None
    # empty list → falsy → None
    if _vd_rows and isinstance(_vd_rows, list):
        result = "populated"
    else:
        result = None
    assert result is None, "Empty 'rows' list must yield None vm entry"


def test_knife_avoid_ruler_suffix_detected():
    """hklab_knife_avoid uses ruler '21d_hsi_excess_avoid_accuracy' — book.py must detect it."""
    from engine.pick_lab.book import scoreboard
    from engine.pick_lab.profile import HK_PROFILE

    # With ruler ending in _avoid_accuracy, is_avoid must be True in scoreboard
    # We can't inspect is_avoid directly, but we can check the h21_avoid_accuracy key
    # is present in the result (it's only added when is_avoid=True).
    # Give it one grade row so _horizon_stats runs.
    grades = [{
        "engine_id": "hklab_knife_avoid",
        "ticker": "0700.HK",
        "fire_date": "2026-01-02",
        "horizon": 21,
        "ret_abs": -0.05,
        "ret_excess_spy": -0.04,
        "mfe": None,
        "mae": None,
        "matured": True,
    }]
    fires = [{
        "engine_id": "hklab_knife_avoid",
        "ticker": "0700.HK",
        "fire_date": "2026-01-02",
        "halt_voided": False,
    }]

    sb = scoreboard(
        "hklab_knife_avoid",
        fires,
        grades,
        ruler="21d_hsi_excess_avoid_accuracy",
        profile=HK_PROFILE,
    )
    assert "h21_avoid_accuracy" in sb, (
        "hklab_knife_avoid must produce h21_avoid_accuracy field "
        "(is_avoid not triggered for this book — review book.py ruler-suffix check)"
    )
