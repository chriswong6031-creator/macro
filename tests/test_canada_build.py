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
                    "take_profits": [], "hold": [], "avoid": []},
        # Branch-B ripe-list row (the fields scripts/build_canada_library._branch_b_order stamps):
        # group, board_pos (rank pill), lead_en/lead_zh, oil_tailwind. Composite is suppressed.
        "setups": {"branch": "B", "rank_basis": "momentum_screen_accruing",
                   "tailwind_suppressed": False, "tailwind_stale_days": 1,
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
    assert len(html) > 8000
