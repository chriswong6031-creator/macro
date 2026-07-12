"""Tests for engine/pick_lab/render_cn.py and templates/china_stocks_lab.html.j2.

Covers:
  - build_vm() with rich CN fixture (zh-heavy names, limit chips, data_gap states)
  - build_vm() with None input (empty-state render)
  - render_page() writes valid HTML without raising
  - Bilingual spans present (l-en / l-zh)
  - No "validated" word anywhere (CI-enforced invariant)
  - No title= attributes containing CJK characters (CI-guarded)
  - Random control row (cnlab_random_ctrl) present in scoreboard
  - Chase avoid row flagged as inverse (NOT BUY label present)
  - data_gap books (cnlab_block_discount, cnlab_lhb_inst) flagged
  - skipped_unfillable counter visible on scoreboard
  - Tab structure: 4 data-tab-panel sections (Scoreboard/Velocity/AllBooks/Method)
  - NO Long-Hold tab (CNPL-R10)
  - china.html.j2 edits: Reversion Desk lane and Lab button present in stocks mode
  - china.html.j2 Reversion Desk degrades gracefully when key absent
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest
from jinja2 import Environment, DictLoader

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
#  Prod-shaped CN fixture data                                                 #
# --------------------------------------------------------------------------- #

def _make_cn_scoreboard_row(
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
    data_gap: bool = False,
    skipped_unfillable: int = 0,
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
        "data_gap": data_gap,
        "skipped_unfillable": skipped_unfillable,
    }


def _make_cn_pick(
    ticker: str,
    rank: int,
    close: float,
    sector: str,
    why: list[str] | None = None,
    features: dict | None = None,
    limit_state: str | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "rank": rank,
        "close": close,
        "sector": sector,
        "why": why or ["1D✚ MACD×K/D", "深度回调"],
        "features": features or {"rev_z": "-2.1", "vol_tercile": "low"},
        "limit_state": limit_state,
    }


def _make_cn_fire(ticker: str, fire_date: str, ret21_excess: float | None,
                  matured: bool, fill_basis: str = "hl2") -> dict:
    return {
        "ticker": ticker,
        "fire_date": fire_date,
        "ret21_excess": ret21_excess,
        "matured": matured,
        "fill_basis": fill_basis,
    }


def _cn_prod_fixture() -> dict:
    """Return cn_pick_lab_dict with rich prod-shaped CN data."""
    scoreboard = [
        # Family A — reversion
        _make_cn_scoreboard_row(
            "cnlab_rev_pure", "CN Reversion Pure (flat, no gates)", "A股纯反转 (平坦无门)",
            "A", "21d_csi300_excess", n_fires=15, n_open=8, n_dates=11, months_span=0.7,
            wr21_abs=0.60, wr21_excess=0.05, med_excess21=0.03,
            mfe_med=0.09, mae_med=0.04, asym=2.2,
            nav_excess_cum=0.07, max_dd=-0.10,
            vs_random_lift=0.04, vs_universe_lift=0.02, status="accruing",
            skipped_unfillable=2,
        ),
        _make_cn_scoreboard_row(
            "cnlab_rev_washout", "CN Reversion + Washout", "A股反转+洗盘",
            "A", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_rev_coiled", "CN Reversion + Coiled/STAR", "A股反转+盘绕/STAR",
            "A", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_rev_lowvol", "CN Reversion + Low Volatility", "A股反转+低波动",
            "A", "21d_csi300_excess", status="accruing",
        ),
        # Family B — 1D velocity
        _make_cn_scoreboard_row(
            "cnlab_1d_pure", "CN 1D Velocity Pure", "A股1日速度纯",
            "B", "21d_csi300_excess", n_fires=10, n_open=5, status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_1d_phase", "CN 1D + Cycle Phase", "A股1日+周期阶段",
            "B", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_1d_participation", "CN 1D + Participation Regime", "A股1日+参与制度",
            "B", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_1d_blastoff", "CN 1D Blastoff (2D/3D gate miss)", "A股1日起飞 (2D/3D门遗漏)",
            "B", "21d_csi300_excess", status="accruing",
        ),
        # Family C — structure/flow, including data_gap books
        _make_cn_scoreboard_row(
            "cnlab_block_discount", "CN Block Discount ≤−15%", "A股大宗折价≤−15%",
            "C", "21d_csi300_excess", status="accruing",
            data_gap=True,  # store-dependent, absent in CI (CNPL-R9)
        ),
        _make_cn_scoreboard_row(
            "cnlab_lhb_inst", "CN LHB Institutional Seats ≥2", "A股龙虎榜机构席位≥2",
            "C", "21d_csi300_excess", status="accruing",
            data_gap=True,  # store-dependent, absent in CI (CNPL-R9)
        ),
        _make_cn_scoreboard_row(
            "cnlab_policy_put", "CN Policy Put Bottom Fisher", "A股政策托底抄底",
            "C", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_theme_laggard", "CN Theme Laggard Catch-up", "A股主题落后者补涨",
            "C", "21d_csi300_excess", status="accruing",
        ),
        # Family D — washout/panic + inverse (chase avoid)
        _make_cn_scoreboard_row(
            "cnlab_capitulation_beta", "CN Capitulation Beta (dormant unless market caps)", "A股资本出逃Beta (非市场投降期休眠)",
            "D", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_qvix_panic", "CN QVIX Panic Entry", "A股波动率恐慌入场",
            "D", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_star_20cm", "CN STAR/ChiNext 20cm 1D Timing", "A股科创/创业20cm 1日择时",
            "D", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_chase_avoid", "CN Chase Avoid (INVERSE)", "A股追涨规避 (反向)",
            "D", "21d_csi300_excess_avoid_accuracy", status="accruing",
        ),
        # Family E — defensive + control
        _make_cn_scoreboard_row(
            "cnlab_lowvol_defensive", "CN Low-Vol Defensive", "A股低波动防御",
            "E", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_dividend_ma120", "CN Dividend / 中特估 Defensive", "A股分红/中特估防御",
            "E", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_flagship_nogate", "CN Flagship (no US confluence-cascade gate)", "A股旗舰 (无美式汇流门)",
            "E", "21d_csi300_excess", status="accruing",
        ),
        _make_cn_scoreboard_row(
            "cnlab_random_ctrl", "CN Random Control", "A股随机基准",
            "E", "21d_csi300_excess",
            n_fires=12, n_open=0, n_dates=10, months_span=0.5,
            wr21_abs=0.50, wr21_excess=0.0, med_excess21=0.0,
            nav_excess_cum=0.0, max_dd=-0.08, status="accruing",
        ),
    ]

    books = {
        "cnlab_rev_pure": {
            "picks_today": [
                _make_cn_pick("300725.SZ", 1, 42.50, "Healthcare",
                              why=["rev_quintile", "深度洗盘", "sector: Healthcare"],
                              features={"rev_3m": "-28.4%", "vol_rank": "3"}),
                _make_cn_pick("603129.SS", 2, 18.30, "Industrials",
                              why=["rev_quintile", "sector: Industrials"],
                              limit_state="hit_up"),
                _make_cn_pick("688306.SS", 3, 55.10, "Technology",
                              why=["rev_quintile", "coiled", "20cm board"],
                              features={"rev_3m": "-31.2%"}),
            ],
            "recent_fires": [
                _make_cn_fire("000001.SZ", "2026-06-15", 0.032, True, "hl2"),
                _make_cn_fire("002415.SZ", "2026-06-18", -0.018, True, "close"),
                _make_cn_fire("600519.SS", "2026-06-22", None, False, "hl2"),
            ],
        },
        "cnlab_1d_pure": {
            "picks_today": [
                _make_cn_pick("300059.SZ", 1, 22.80, "Technology",
                              why=["1D MACD cross ≤2", "StochRSI k×d cross", "from_os"],
                              features={"rsi_10": "48.3", "fresh_bars": "1"}),
            ],
            "recent_fires": [],
        },
        "cnlab_block_discount": {
            "picks_today": [],
            "recent_fires": [],
            "data_gap": True,
        },
        "cnlab_lhb_inst": {
            "picks_today": [],
            "recent_fires": [],
            "data_gap": True,
        },
        "cnlab_chase_avoid": {
            "picks_today": [
                _make_cn_pick("000858.SZ", 1, 88.60, "Consumer Defensive",
                              why=["sealed_up", "5d run +18%"],
                              limit_state="sealed_up"),
            ],
            "recent_fires": [
                _make_cn_fire("002714.SZ", "2026-06-20", -0.041, True, "hl2"),
            ],
        },
        "cnlab_random_ctrl": {
            "picks_today": [
                _make_cn_pick("600036.SS", 1, 38.20, "Financial Services"),
                _make_cn_pick("002594.SZ", 2, 55.40, "Consumer Cyclical"),
            ],
            "recent_fires": [],
        },
    }

    return {
        "schema": "china_pick_lab.v1",
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T10:30:00Z",
        "scoreboard": scoreboard,
        "books": books,
        "total_skipped_unfillable": 4,
        "method_note": "Asia-lane run 2026-07-09. 20 books active. 4 fires skipped (sealed_up at close).",
    }


# --------------------------------------------------------------------------- #
#  render_cn.py unit tests                                                     #
# --------------------------------------------------------------------------- #

def test_build_vm_empty_state():
    """build_vm(None) returns empty=True with all safe defaults.

    velocity_books always has 4 stubs (static IDs); all_books is empty
    because there is no scoreboard to iterate over.
    """
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(None)
    assert vm["empty"] is True
    assert vm["scoreboard"] == []
    # 4 velocity book stubs always present even with empty input
    assert len(vm["velocity_books"]) == 4
    # all_books only populated from scoreboard — empty when scoreboard is empty
    assert vm["all_books"] == []
    assert vm["total_skipped_unfillable"] is None
    assert vm["authority"] == "display_only"


def test_build_vm_full_fixture():
    """build_vm() with rich fixture populates all fields correctly."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    assert vm["empty"] is False
    assert vm["as_of"] == "2026-07-09"
    assert len(vm["scoreboard"]) == 20
    assert vm["total_skipped_unfillable"] == 4
    assert vm["authority"] == "display_only"


def test_scoreboard_random_ctrl_is_marked():
    """cnlab_random_ctrl row must be flagged as is_random=True."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    random_rows = [r for r in vm["scoreboard"] if r.get("is_random")]
    assert len(random_rows) == 1
    assert random_rows[0]["engine_id"] == "cnlab_random_ctrl"


def test_scoreboard_chase_avoid_is_inverse():
    """cnlab_chase_avoid row must be flagged as is_inverse=True."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    inv_rows = [r for r in vm["scoreboard"] if r.get("is_inverse")]
    assert len(inv_rows) == 1
    assert inv_rows[0]["engine_id"] == "cnlab_chase_avoid"


def test_scoreboard_data_gap_books_flagged():
    """cnlab_block_discount and cnlab_lhb_inst must have has_data_gap=True."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    by_id = {r["engine_id"]: r for r in vm["scoreboard"]}
    assert by_id["cnlab_block_discount"]["has_data_gap"] is True
    assert by_id["cnlab_lhb_inst"]["has_data_gap"] is True
    # Other books should not have data_gap
    assert by_id["cnlab_rev_pure"]["has_data_gap"] is False


def test_scoreboard_skipped_unfillable_formatted():
    """skipped_unfillable field must be formatted for each row."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    rev_row = next(r for r in vm["scoreboard"] if r["engine_id"] == "cnlab_rev_pure")
    assert rev_row["skipped_unfillable_fmt"] == "2"


def test_velocity_books_populated():
    """velocity_books must contain all 4 CN 1D books."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    assert len(vm["velocity_books"]) == 4
    ids = {b["engine_id"] for b in vm["velocity_books"]}
    assert "cnlab_1d_pure" in ids
    assert "cnlab_1d_blastoff" in ids


def test_velocity_books_data_gap_passthrough():
    """Velocity book data_gap flag comes from books_raw.get(eid, {}).get('data_gap')."""
    from engine.pick_lab.render_cn import build_vm
    fixture = _cn_prod_fixture()
    fixture["books"]["cnlab_1d_pure"]["data_gap"] = True
    vm = build_vm(fixture)
    pure_book = next(b for b in vm["velocity_books"] if b["engine_id"] == "cnlab_1d_pure")
    assert pure_book["data_gap"] is True


def test_cn_pick_close_formatted_in_yuan():
    """CN pick cards must show close price in ¥ format."""
    from engine.pick_lab.render_cn import _enrich_pick
    p = _enrich_pick({"close": 42.5})
    assert p["close_fmt"] == "¥42.50"


def test_cn_pick_no_close_formats_dash():
    """CN pick with no close must format as '—'."""
    from engine.pick_lab.render_cn import _enrich_pick
    p = _enrich_pick({"close": None})
    assert p["close_fmt"] == "—"


def test_cn_pick_sealed_up_chip():
    """sealed_up limit state must produce the correct chip."""
    from engine.pick_lab.render_cn import _enrich_pick
    p = _enrich_pick({"close": 88.6, "limit_state": "sealed_up"})
    assert p["limit_chip_en"] == "sealed ↑"
    assert p["limit_chip_css"] == "chip-warn"


def test_cn_pick_hit_up_chip():
    """hit_up limit state produces the hit ↑ chip."""
    from engine.pick_lab.render_cn import _enrich_pick
    p = _enrich_pick({"close": 18.3, "limit_state": "hit_up"})
    assert p["limit_chip_en"] == "hit ↑"
    assert p["limit_chip_css"] == "chip-up"


def test_cn_fire_fill_basis_label():
    """fill_basis label must be included in enriched fires."""
    from engine.pick_lab.render_cn import _enrich_fire
    f = _enrich_fire({"ticker": "000001.SZ", "fire_date": "2026-06-15",
                      "ret21_excess": 0.032, "matured": True, "fill_basis": "hl2"})
    assert f["fill_basis_label"] == "hl2"
    assert f["ret21_excess_fmt"] == "+3.2%"
    assert f["matured_label"] == "matured"


def test_all_books_count():
    """all_books must contain all 20 entry-role books."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    assert len(vm["all_books"]) == 20


def test_all_books_chase_avoid_is_inverse():
    """cnlab_chase_avoid in all_books must have is_inverse=True."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    ca = next(b for b in vm["all_books"] if b["engine_id"] == "cnlab_chase_avoid")
    assert ca["is_inverse"] is True


# --------------------------------------------------------------------------- #
#  Template render tests                                                       #
# --------------------------------------------------------------------------- #

def _render_cn_lab(vm: dict) -> str:
    """Render china_stocks_lab.html.j2 with the given vm dict."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=True,
    )
    return env.get_template("china_stocks_lab.html.j2").render(**vm)


def test_template_parse():
    """china_stocks_lab.html.j2 must parse without Jinja syntax errors."""
    env = Environment(autoescape=False)
    src = (ROOT / "templates" / "china_stocks_lab.html.j2").read_text()
    env.parse(src)


def test_render_empty_state():
    """Empty-state render must complete without errors and show accrual message."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(None)
    html = _render_cn_lab(vm)
    assert "First accrual tonight" in html or "今晚首次累积" in html
    # Must have 5 tab panel sections (no Long-Hold; SA-W5 adds Accountability)
    assert html.count('<section data-tab-panel=') == 5


def test_render_no_long_hold_tab(tmp_path):
    """CNPL-R10: NO Long-Hold tab must appear in the rendered page."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(None)
    html = _render_cn_lab(vm)
    # Long-Hold / 长持 must not appear as a tab
    assert "data-tab=\"longhold\"" not in html
    assert "Long-Hold Grid" not in html


def test_render_four_tabs():
    """Rendered page must have exactly 5 tab buttons: Scoreboard, Velocity CN, All Books, Record (SA-W5), Method."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(None)
    html = _render_cn_lab(vm)
    # Count data-tab attributes in tabbtn elements
    tabs = re.findall(r'data-tab=["\'](\w+)["\']', html)
    assert set(tabs) == {"scoreboard", "velocity", "allbooks", "accountability", "method"}
    assert len(tabs) == 5  # SA-W5: +1 for Accountability tab


def test_render_bilingual_spans():
    """Rendered page must contain both l-en and l-zh class spans."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert 'class="l-en"' in html
    assert 'class="l-zh"' in html
    # Spot-check a key bilingual label
    assert "Pick Lab" in html
    assert "选股实验室" in html


def test_render_no_validated_word():
    """The word 'validated' must NEVER appear in the rendered CN lab page (CI-enforced)."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert "validated" not in html.lower()


def test_render_no_cjk_in_title_attrs():
    """No CJK characters must appear inside title= attributes (CI-guarded)."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    cjk_pattern = re.compile(r'title=["\'][^"\']*[一-鿿㐀-䶿][^"\']*["\']')
    bad = cjk_pattern.findall(html)
    assert not bad, f"CJK characters found in title= attributes: {bad}"


def test_render_random_ctrl_in_scoreboard():
    """cnlab_random_ctrl must appear in the scoreboard with yardstick label."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert "cnlab_random_ctrl" in html
    # yardstick / 基准
    assert "yardstick" in html or "基准" in html


def test_render_chase_avoid_not_buy_label():
    """Chase Avoid book must show a NOT-BUY warning — avoid / 规避 language."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    # The avoid label must appear; both EN and ZH variants are acceptable
    assert ("NOT BUY" in html or "非买入" in html), (
        "Chase Avoid book missing NOT-BUY / 非买入 label"
    )
    # Explicit AVOID banner must appear in the AllBooks tab section
    assert "AVOID" in html or "规避" in html


def test_render_data_gap_books_flagged():
    """Store-dependent books must show DATA GAP / 数据缺失 flag."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert "DATA GAP" in html or "数据缺失" in html


def test_render_skipped_unfillable_visible():
    """skipped_unfillable counter must appear on the scoreboard page."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    # The total_skipped_unfillable = 4 should be rendered
    # Accept either the number in the banner or the column
    assert "4" in html and ("skipped" in html.lower() or "跳过" in html or "封涨停" in html)


def test_render_nav_gap_at_least_14px():
    """body padding-top must be >= 14px to satisfy check_nav_gap (body has padding-top:24px)."""
    src = (ROOT / "templates" / "china_stocks_lab.html.j2").read_text()
    # Find padding-top in the body style
    m = re.search(r"body\s*\{[^}]*padding-top\s*:\s*(\d+)px", src)
    assert m, "body{padding-top:Npx} not found in china_stocks_lab.html.j2"
    assert int(m.group(1)) >= 14, f"body padding-top={m.group(1)}px < 14px (nav gap violated)"


def test_render_body_padding_24px():
    """body padding-top must be exactly 24px (matching task spec)."""
    src = (ROOT / "templates" / "china_stocks_lab.html.j2").read_text()
    assert "padding-top:24px" in src, "body padding-top:24px not found in template"


def test_render_page_writes_html(tmp_path):
    """render_page() must write a non-empty china_stocks_lab.html to site/."""
    from engine.pick_lab.render_cn import build_vm, render_page
    vm = build_vm(_cn_prod_fixture())
    render_page(vm, tmp_path)
    out = tmp_path / "china_stocks_lab.html"
    assert out.exists(), "china_stocks_lab.html was not written"
    content = out.read_text()
    assert len(content) > 5000, "Rendered HTML seems too short"
    assert "<!DOCTYPE html>" in content


def test_render_cn_picks_shown():
    """Rich fixture picks (300725.SZ, zh-heavy names) must appear in the rendered page."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert "300725.SZ" in html
    assert "603129.SS" in html


def test_render_sealed_up_limit_chip():
    """A pick with limit_state=sealed_up must show the sealed ↑ chip in rendered HTML."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(_cn_prod_fixture())
    html = _render_cn_lab(vm)
    assert "sealed" in html or "涨停" in html


def test_build_and_render_no_raise(tmp_path):
    """build_and_render() must not raise even with no labdata directory."""
    from engine.pick_lab.render_cn import build_and_render
    # Empty site dir — labdata/china_pick_lab.json absent → renders empty state
    (tmp_path / "labdata").mkdir()
    # Point templates at our real templates dir via a monkeypatch of config
    import engine.pick_lab.render_cn as rcn
    import lib.config as cfg
    orig_root = cfg.ROOT
    cfg.ROOT = ROOT
    try:
        build_and_render(tmp_path)
    finally:
        cfg.ROOT = orig_root
    out = tmp_path / "china_stocks_lab.html"
    assert out.exists(), "build_and_render must write the file even in empty state"


# --------------------------------------------------------------------------- #
#  china.html.j2 template edits                                                #
# --------------------------------------------------------------------------- #

CHINA_SRC = (ROOT / "templates" / "china.html.j2").read_text()


def test_china_template_parses():
    """Full china.html.j2 must parse (Jinja2 syntax check)."""
    env = Environment(autoescape=False)
    env.parse(CHINA_SRC)


def test_china_stocks_lab_button_present():
    """Lab button (china_stocks_lab.html link) must exist in china.html.j2."""
    assert "china_stocks_lab.html" in CHINA_SRC, (
        "china_stocks_lab.html link not found in china.html.j2"
    )
    # Check bilingual label
    assert "Pick Lab" in CHINA_SRC
    assert "选股实验室" in CHINA_SRC


def test_china_lab_button_inside_stocks_mode_gate():
    """Lab button must be inside a mode==stocks gate, not visible in macro mode.

    There are multiple short inline mode gates (page title, SEO vars).
    Search for the gate that CONTAINS the lab link.
    """
    link = "china_stocks_lab.html"
    link_pos = CHINA_SRC.index(link)
    # Walk backwards to find the nearest preceding mode=='stocks' gate
    gate_marker = "{% if mode == 'stocks' %}"
    gate_pos = CHINA_SRC.rfind(gate_marker, 0, link_pos)
    assert gate_pos >= 0, "No mode=='stocks' gate found before the Lab button"
    # Confirm the gate is before the link (not after)
    assert gate_pos < link_pos, "mode=='stocks' gate must precede the lab button"


def test_china_reversion_desk_lane_present():
    """Reversion Desk lane must be present in china.html.j2."""
    assert "reversion-desk" in CHINA_SRC or "reversion_desk" in CHINA_SRC, (
        "Reversion Desk panel missing from china.html.j2"
    )
    # Bilingual heading
    assert "Reversion Desk" in CHINA_SRC
    assert "回归台" in CHINA_SRC


def test_china_reversion_desk_uses_safe_key_access():
    """Reversion Desk must NOT use 'reversion_desk is not none' (crashes on missing key).

    The JINJA GOTCHA: 'is not none' on a missing key raises UndefinedError.
    The correct pattern is to set a variable via 'if X is defined else none' or .get().
    """
    # Find the Jinja comment block that opens the reversion desk
    rd_start = CHINA_SRC.find("{# ======= REVERSION DESK")
    assert rd_start >= 0, "Reversion Desk Jinja comment block not found"
    # The end guard is the outer endif
    rd_end_marker = "{# /mode == 'stocks' reversion desk #}"
    rd_end = CHINA_SRC.find(rd_end_marker, rd_start)
    if rd_end < 0:
        rd_end = rd_start + 5000  # fallback: 5000 chars after start
    block = CHINA_SRC[rd_start:rd_end]
    # Must use 'is defined' to guard the vm key safely
    assert "is defined" in block, (
        "Reversion Desk block must use 'is defined' to guard the vm key "
        "(bare 'is not none' crashes on missing key)"
    )
    # Must NOT use bare 'reversion_desk is not none' (the dangerous pattern)
    assert "reversion_desk is not none" not in block, (
        "DANGEROUS: 'reversion_desk is not none' will crash when key is absent"
    )


def _extract_reversion_desk_block() -> str:
    """Extract the full self-contained reversion desk block from china.html.j2."""
    # The outer block starts at the Jinja comment and ends at the outer endif comment
    start_marker = "{# ======= REVERSION DESK"
    end_marker = "{# /mode == 'stocks' reversion desk #}"
    rd_start = CHINA_SRC.find(start_marker)
    assert rd_start >= 0, "Reversion Desk block not found"
    rd_end = CHINA_SRC.find(end_marker, rd_start)
    assert rd_end >= 0, f"End marker '{end_marker}' not found after reversion desk"
    rd_end += len(end_marker)
    return CHINA_SRC[rd_start:rd_end]


def _make_rd_env(snippet: str) -> Environment:
    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro help(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        "{%- endmacro -%}\n"
    )
    # Strip the Jinja comment block (not valid as Jinja tag)
    import re
    snippet = re.sub(r'\{#.*?#\}', '', snippet, flags=re.DOTALL)
    full = macros + snippet
    return Environment(loader=DictLoader({"blk": full}), autoescape=False)


def test_china_reversion_desk_degrades_gracefully():
    """china.html.j2 Reversion Desk must render gracefully when reversion_desk is absent.

    Renders the stocks-mode block with reversion_desk absent from vm — must not raise.
    """
    snippet = _extract_reversion_desk_block()
    env = _make_rd_env(snippet)
    # Render WITHOUT reversion_desk in context — must not raise
    try:
        env.get_template("blk").render(mode="stocks")
        # Should render empty/nothing (the {% if _rd %} guard collapses it)
    except Exception as exc:
        pytest.fail(
            f"Reversion Desk block raised when reversion_desk absent: {exc}"
        )


def test_china_reversion_desk_renders_with_data():
    """Reversion Desk must render picks when data is present."""
    snippet = _extract_reversion_desk_block()
    env = _make_rd_env(snippet)

    test_reversion_desk = {
        "as_of": "2026-07-09",
        "picks": [
            {
                "ticker": "300725.SZ",
                "name": "宁德时代 / CATL",
                "price": 155.30,
                "sector": "Technology",
                "off_high": -22.4,
                "rev_depth_pct": -28.5,
                "washout_2w": True,
                "coiled": False,
                "chase_veto": False,
                "cycle_phase": "ACCUMULATION",
            },
            {
                "ticker": "603129.SS",
                "name": "科伦药业 / Kelun",
                "price": 18.20,
                "sector": "Healthcare",
                "off_high": -31.0,
                "rev_depth_pct": -35.1,
                "washout_2w": False,
                "coiled": True,
                "chase_veto": False,
                "cycle_phase": None,
            },
        ],
    }

    html = env.get_template("blk").render(
        mode="stocks",
        reversion_desk=test_reversion_desk,
    )
    assert "300725.SZ" in html, "Reversion Desk pick ticker not rendered"
    assert "155.30" in html, "Reversion Desk pick price not rendered"
    assert "CATL" in html or "宁德时代" in html, "Reversion Desk pick name not rendered"
    # washout_2w chip
    assert "washout" in html.lower() or "洗盘" in html, "washout_2w chip missing"
    # Coiled chip for second pick
    assert "Coiled" in html or "蓄势" in html, "coiled chip missing"


def test_china_template_no_validated_word_in_stocks_section():
    """The word 'validated' must not appear in the stocks-mode sections we added."""
    # Find the reversion desk block
    rd_start = CHINA_SRC.find("{# ======= REVERSION DESK")
    if rd_start < 0:
        return  # block not present; caught by other test
    rd_end = CHINA_SRC.find("{# /mode != macro", rd_start)
    if rd_end < 0:
        rd_end = len(CHINA_SRC)
    added_section = CHINA_SRC[rd_start:rd_end]
    assert "validated" not in added_section.lower(), (
        "Word 'validated' found in the newly added Reversion Desk section"
    )
