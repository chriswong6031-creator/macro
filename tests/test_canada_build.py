"""Canada macro template render-guard (templates/canada.html.j2).

Renders the page with a synthetic view-model + the i18n globals the build wires in,
exactly as scripts/build_canada does. Catches Jinja breakage (missing-key crashes,
bad string escapes) before it reaches CI — the kind of bug a pure-Python test misses."""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import i18n  # noqa: E402


def _vm() -> dict:
    mtf = "{}"
    return {
        "latest": {"date": "2026-06-12", "quad": "Q1", "quad_name": "Goldilocks",
                   "growth_score": 0.73, "inflation_score": -1.0, "confidence": 0.87,
                   "liquidity_overlay": "neutral", "cycle_tag": "mid",
                   "confirming": ["a", "b"], "contradicting": []},
        "built": "2026-06-12 22:00 UTC",
        "quad_meaning": ("growth up inflation down", "增长上 通胀下"),
        "overlay": {"state": "Risk-off", "score": -0.37, "terms_of_trade": "deteriorating",
                    "factors": [{"key": "oil", "label": "WTI crude oil", "z": -1.2, "sign": 1.0, "risk": "off", "level": 60.0},
                                {"key": "gold", "label": "Gold", "z": 1.1, "sign": 1.0, "risk": "on", "level": 4200.0}]},
        "coupling": {"boc_rate": 2.25, "goc_curve_2s10s": 0.64, "goc_2y": 2.77, "goc_10y": 3.41,
                     "us_2y": None, "us_10y": None, "goc_minus_ust_2y": None, "goc_minus_ust_10y": None},
        "curve_chart": "", "axes_chart": "",
        "sectors": [{"rank": 1, "ticker": "XEG.TO", "name": "Energy", "tv": "", "dir": "up",
                     "label": "UPTREND", "state": "UPTREND", "mom20": 2.1, "mom60": 5.4,
                     "pctile": 80.0, "above200": True, "mtf_json": mtf, "entry": {"urgency": "now", "tag": "BUY NOW"}}],
        "actions": {"buy_now": [{"name": "Energy", "ticker": "XEG.TO"}], "buy_soon": [],
                    "on_the_run": [{"name": "Financials", "ticker": "XFN.TO"}],
                    "take_profits": [], "hold": [], "avoid": []},
        # Branch-B ripe-list row (the fields scripts/build_canada_library._branch_b_order stamps):
        # group, board_pos (rank pill), lead_en/lead_zh, oil_tailwind. Composite is suppressed.
        "setups": {"branch": "B", "rank_basis": "momentum_screen_accruing",
                   "tailwind_suppressed": False, "tailwind_stale_days": 1,
                   # CA2: confluence stat (zero-cross tape visible) + sector-concentration banner
                   "confluence": {"crosses": 0, "board": 1},
                   "sector_concentration": {"sector": "Materials", "n": 10, "total": 14,
                                            "counts": {"Materials": 10, "Energy": 2,
                                                       "Industrials": 1, "Utilities": 1}},
                   # W6 track-record panel (accruing state) + watch/laggard parity strips.
                   "board_track": {"market": "CA", "status": "accruing",
                                   "note": "no board calls logged yet",
                                   "first_read_est": "2026-08-24"},
                   "watch": [{"ticker": "CLS.TO", "name": "CELESTICA INC", "alpha": 2.38,
                              "watch_reason": "knife", "block_reason": "weekly still falling",
                              "block_reason_zh": "周线仍下行",
                              "conviction": {"score": 61, "verdict": "Strong screen, no base",
                                             "verdict_zh": "筛选强，尚未筑底"}}],
                   "laggards": [{"ticker": "WSP.TO", "name": "WSP GLOBAL", "alpha": -2.52}],
                   "buy": [{"ticker": "TD.TO", "name": "TD Bank", "alpha": 1.8, "label": "UPTREND",
                            "dir": "up", "sector_rank": 1, "sector_n": 9, "sector": "Financials",
                            "off_high": -3.0, "spark_svg": "<svg></svg>",
                            "group": "setting_up", "board_pos": 1, "oil_tailwind": False,
                            "insider": {"lean": "buying", "n_buys": 3, "n_sells": 0, "window_days": 180},
                            "earnings": {"next_date": "2026-07-10", "days_to": 7},
                            "lead_en": "Main driver: Financials sector · wait for the weekly turn",
                            "lead_zh": "主要驱动：Financials 板块 · 等待周线转向",
                            # CA2: confluence gate verdict (RAN, no fresh cross → 'no confluence' badge)
                            "signal": {"eligible": False, "tier": None, "sub": None,
                                       "reason": "flat: cut", "tier_cascade": None},
                            # CA2 port: hold basing-state note (close-only) + pullback zone
                            "hold": {"state": "intact", "anchor": "2026-05-01", "anchor_src": "take",
                                     "days_basing": 12, "invalidation": 38.4, "provisional": False},
                            "pullback_zone": {"stance": "accumulate", "price": 44.0,
                                              "levels": [{"label_en": "rising 50-day average",
                                                          "label_zh": "上升50日均线",
                                                          "price": 42.5, "pull_pct": -3.4}],
                                              "headline_en": "Don't chase — accumulate on a pullback.",
                                              "headline_zh": "勿追 — 回调时分批建仓。"},
                            "entry_signal": {"status": "wait_pullback", "buy_zone": {}}}]},
        "stocks_health": [], "board_health": [],
        "breadth": {"pct_above_50": 62.0, "pct_above_200": 71.0, "nh": 8, "nl": 2,
                    "net_nh": 6, "adv": 130, "dec": 80, "ad_trend": "up",
                    "pct50_chg20": 3.1, "n_members": 220, "state": "broad",
                    "tone": "pos", "full": True},
        "benchmark": {"name": "S&P/TSX Composite", "ticker": "^GSPTSE", "price": 34937.0,
                      "chg": 0.4, "dc_day": 12, "label": "UPTREND", "state": "UPTREND", "mtf_json": mtf},
        "housing": {"level": 142.3, "yoy": 1.2, "off_peak": -4.5, "asof": "2025-12-31"},
        "health": [{"en": "Prices / sectors", "zh": "价格", "status": "ok", "rows": 90000, "last": "2026-06-12"}],
        "pair": {}, "pref": {}, "lifespan_rows": [],
    }


def _env():
    env = Environment(loader=FileSystemLoader(
        str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env


def test_canada_macro_template_renders():
    # macro mode = the regime story; the standout names now live on the Stock Dashboard
    html = _env().get_template("canada.html.j2").render(**_vm(), mode="macro")
    assert "Canada — S&P/TSX Regime" in html
    assert "Goldilocks" in html
    assert "Risk-off" in html
    assert "Commodity / CAD" in html
    assert "XEG.TO" in html                            # sector rotation stays on macro
    assert "ON THE RUN" in html and "XFN.TO" in html   # #1513 lane split ported (violet lane)
    assert "TD Bank" not in html                       # standouts moved to the stock dashboard
    assert "canada_stocks.html" in html                # cross-link to the stock dashboard
    # nav search moved into the shared multi-market lib (theme.js) — assert the page
    # loads it and the lib itself still wires the Canada index
    assert "theme.js" in html
    assert "canadastockdata/index.json" in (
        Path(__file__).resolve().parent.parent / "templates" / "theme.js").read_text()
    assert len(html) > 8000


def test_canada_stocks_template_renders():
    # stocks mode = the new TSX Stock Dashboard: standout cards + show-more, no regime hero
    html = _env().get_template("canada.html.j2").render(**_vm(), mode="stocks")
    assert "TSX Stock Dashboard" in html
    assert "ripe-list screen" in html                   # Branch-B board header (C7 verdict)
    assert "TD Bank" in html                            # the standout setup renders here
    # Branch B: composite 0-100 chip SUPPRESSED, rank pill + accruing screen badge present
    assert "rankpill" in html and ">#1<" in html
    assert "momentum screen · unproven" in html         # W6 why-now evidence-tag chip (plain-language label)
    assert 'class="nb-cscore' not in html               # composite score chip is gone
    assert 'data-showmore-rows=' in html                # the progressive reveal is wired (#888 row-capped)
    assert "Commodity / CAD" not in html                # overlay hero is macro-only
    assert "Housing & household-debt" not in html       # housing is macro-only
    # ── W6 UX overhaul (§7): consolidated desk-header + accruing track-record panel +
    #    watch/laggard parity strips + why-now evidence chips + entry-window card accent ──
    assert 'class="desk-hdr"' in html                   # ONE "what this desk is / isn't" block
    assert "Not a guaranteed buy list" in html
    assert 'class="trk"' in html and "ACCRUING" in html  # track-record centerpiece (accruing)
    assert "2026-08-24" in html                          # honest first-stable-read date on the panel
    assert 'class="watch-strip"' in html and "CLS.TO" in html   # strong-but-blocked watch strip
    assert "Weakest screen (laggards)" in html and "WSP.TO" in html  # laggard/avoid strip
    assert "ev-insider" in html                          # insider why-now chip
    assert "ev-earn" in html and "reports in" in html    # earnings-catalyst chip (days_to present)
    assert "ent-pullback" in html                        # entry-window card accent
    assert "Read the Canada AI brief" not in html        # AI-brief doorway presence-guarded (no CA brief)
    # ── CA2 fix: gate-tier visibility + confluence stat + sector banner + close-only ports ──
    assert "Confluence:" in html                          # desk-header confluence stat
    assert "no fresh entry trigger" in html               # zero-cross tape reads honestly (0 of N)
    assert "gate-none" in html and "no confluence cross" in html  # tier badge honest RAN-no-cross state
    assert "sec-conc" in html and "picks are" in html     # sector-concentration banner (>60%)
    assert "Materials" in html                            # the concentrated sector is named
    assert "basing" in html                               # HOLD port chip (basing-state note)
    assert "nbe-pull" in html                             # pullback-zone range enriches the entry window
    assert len(html) > 8000


def test_canada_stocks_shows_real_tier_badge_when_cross_fires():
    """When a board name has a FRESH confluence cross, the card must render its T1..T4 tier
    badge (not the 'no confluence' state) — the gate-tier passthrough the CA2 fix restores."""
    vm = _vm()
    vm["setups"]["buy"][0]["signal"] = {"eligible": True, "tier": "T2", "sub": "master",
                                        "reason": "held take", "tier_cascade": "T2"}
    vm["setups"]["confluence"] = {"crosses": 1, "board": 1}
    html = _env().get_template("canada.html.j2").render(**vm, mode="stocks")
    assert "gate-tier" in html and ">🎯 T2" in html       # real tier badge on the card
    assert "no confluence cross" not in html              # not the RAN-no-cross state
    assert "buyable cross" in html                        # confluence stat present


# ── W8-G: CA table-view port tests ────────────────────────────────────────────

def _w8g_vm():
    """Synthetic VM with 3 board rows (2 entry_open, 1 setting_up) to test
    serialization completeness, system-order preservation, and field coverage."""
    import copy
    vm = _vm()
    # extend buy list with two more rows to cover both groups + multiple entries
    vm["setups"]["buy"] = [
        {"ticker": "BIR.TO", "name": "BIRCHCLIFF ENERGY LTD.", "alpha": -1.51,
         "label": "BOTTOMING", "dir": "flat", "sector": "Energy",
         "off_high": -21.0, "price": 4.82, "group": "entry_open", "board_pos": 1,
         "oil_tailwind": True, "days_since_signal": 1,
         "signal": {"eligible": False, "tier": None, "sub": None,
                    "reason": "flat: cut", "tier_cascade": None},
         "conviction": {"score": None, "verdict": "—", "verdict_zh": "—",
                        "alignment": None,
                        "axes": {"selection": {"pct": 60}, "entry": {"pct": 55},
                                 "tailwind": {"pct": None}, "quality": {"pct": 40}},
                        "cautions": [], "cautions_zh": []},
         "entry_signal": {"status": "partial", "buy_zone": {}, "headline": "Partial entry",
                          "headline_zh": "部分入场", "action": "buy", "act_level": 3},
         "lead_en": "Energy sector tailwind.", "lead_zh": "能源顺风。",
         "spark_svg": "<svg></svg>"},
        {"ticker": "DPM.TO", "name": "DPM METALS INC", "alpha": 1.10,
         "label": "UPTREND", "dir": "up", "sector": "Materials",
         "off_high": -16.0, "price": 12.75, "group": "entry_open", "board_pos": 2,
         "oil_tailwind": False, "days_since_signal": 5,
         "signal": {"eligible": True, "tier": "T1", "sub": "master",
                    "reason": "full", "tier_cascade": "T1"},
         "conviction": {"score": None, "verdict": "—", "verdict_zh": "—",
                        "alignment": None,
                        "axes": {"selection": {"pct": 70}, "entry": {"pct": 80},
                                 "tailwind": {"pct": None}, "quality": {"pct": 65}},
                        "cautions": [], "cautions_zh": []},
         "entry_signal": {"status": "buy_now", "buy_zone": {}, "headline": "Buy now",
                          "headline_zh": "立即买入", "action": "buy", "act_level": 3},
         "lead_en": "Materials breakout.", "lead_zh": "材料突破。",
         "spark_svg": "<svg></svg>"},
        {"ticker": "TD.TO", "name": "TD Bank", "alpha": 1.8,
         "label": "UPTREND", "dir": "up", "sector": "Financials",
         "off_high": -3.0, "price": 88.50, "group": "setting_up", "board_pos": 3,
         "oil_tailwind": False, "days_since_signal": None,
         "signal": {"eligible": False, "tier": None, "sub": None,
                    "reason": "flat: cut", "tier_cascade": None},
         "conviction": {"score": None, "verdict": "—", "verdict_zh": "—",
                        "alignment": None,
                        "axes": {"selection": {"pct": 50}, "entry": {"pct": 30},
                                 "tailwind": {"pct": None}, "quality": {"pct": 55}},
                        "cautions": [], "cautions_zh": []},
         "entry_signal": {"status": "wait_pullback", "buy_zone": {}, "headline": "Wait",
                          "headline_zh": "等待", "action": "wait", "act_level": 1},
         "lead_en": "Financials leader.", "lead_zh": "金融龙头。",
         "spark_svg": "<svg></svg>"},
    ]
    vm["setups"]["confluence"] = {"crosses": 1, "board": 3}
    vm["setups"]["sector_concentration"] = None
    return vm


# Configured columns for the CA table (must match what the template configures for JS)
_CA_TABLE_COLS = [
    "ticker", "name", "tier", "sector", "price",
    "off_high", "alpha", "entry_status", "days_since_signal", "conviction",
]


def test_w8g_ca_stocktable_data_block_present():
    """stocks mode must emit a <script type=application/json id=stocktable-data> block."""
    import json
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="stocks")
    assert 'id="stocktable-data"' in html, "stocktable-data block missing"
    # extract JSON
    import re
    m = re.search(r'id="stocktable-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert m, "Could not find stocktable-data script block"
    payload = json.loads(m.group(1))
    rows = payload["rows"]
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"


def test_w8g_ca_serialization_completeness():
    """Every configured column key must be present-or-None on every serialized row.
    Catches schema/field-name drift between template serialization and JS column config."""
    import json, re
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="stocks")
    m = re.search(r'id="stocktable-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    payload = json.loads(m.group(1))
    rows = payload["rows"]
    # Each configured column key must exist as a key on every row (None is OK)
    for row in rows:
        for col_key in _CA_TABLE_COLS:
            assert col_key in row, (
                f"Column key '{col_key}' missing from serialized row for {row.get('ticker')}; "
                f"keys present: {sorted(row.keys())}"
            )


def test_w8g_ca_no_ordering_mutation():
    """System (board) order must be preserved verbatim in serialization — tickers in
    the same sequence as setups.buy, no re-sort."""
    import json, re
    vm = _w8g_vm()
    expected_order = [r["ticker"] for r in vm["setups"]["buy"]]
    html = _env().get_template("canada.html.j2").render(**vm, mode="stocks")
    m = re.search(r'id="stocktable-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    payload = json.loads(m.group(1))
    actual_order = [r["ticker"] for r in payload["rows"]]
    assert actual_order == expected_order, (
        f"Serialization mutated system order. Expected {expected_order}, got {actual_order}"
    )


def test_w8g_ca_stage_mapping():
    """entry_open group maps to stage=ENTRY; setting_up maps to stage=RIPENING."""
    import json, re
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="stocks")
    m = re.search(r'id="stocktable-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    payload = json.loads(m.group(1))
    rows = payload["rows"]
    for row in rows:
        if row.get("group") == "entry_open":
            assert row["stage"] == "ENTRY", f"{row['ticker']} entry_open should map to ENTRY"
            assert row["_stage"] == "ENTRY"
        elif row.get("group") == "setting_up":
            assert row["stage"] == "RIPENING", f"{row['ticker']} setting_up should map to RIPENING"
            assert row["_stage"] == "RIPENING"


def test_w8g_ca_view_toggle_present():
    """stocks mode must include the grid/table view toggle and mount point."""
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="stocks")
    assert 'id="st-view-toggle"' in html, "view toggle missing"
    assert 'id="st-btn-grid"' in html
    assert 'id="st-btn-table"' in html
    assert 'id="stocktable-wrap"' in html, "table mount point missing"
    assert 'id="st-count-chips"' in html, "count chips missing"
    assert 'class="nb-grid-section"' in html, "nb-grid-section wrapper missing"


def test_w8g_ca_stocktable_js_include():
    """stocks mode must include stocktable.js and the StockTable.init call."""
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="stocks")
    assert 'src="stocktable.js"' in html, "stocktable.js include missing"
    assert "StockTable.init" in html, "StockTable.init missing"
    assert "mdx_stocktable_ca_view" in html, "CA localStorage key missing"
    assert "canada_stock.html#{ticker}" in html, "CA link pattern missing"


def test_w8g_ca_table_not_in_macro_mode():
    """macro mode must NOT include the stocktable data block or JS init."""
    html = _env().get_template("canada.html.j2").render(**_w8g_vm(), mode="macro")
    assert 'id="stocktable-data"' not in html, "stocktable-data must not appear in macro mode"
    assert "StockTable.init" not in html, "StockTable.init must not appear in macro mode"
