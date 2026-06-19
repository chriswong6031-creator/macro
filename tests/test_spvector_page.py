"""Render-smoke + structure tests for the split market pages.

 - spvector.html.j2 (US allocation deep-dive) renders, carries the mandated
   honesty caveats, and has no double-escaped entities.
 - dashboard.html.j2 compiles (the macro/stocks mode-conditional if/endif balance)
   and carries the split markers; same for the nav-edited china/gex/hk templates.
 - the landing hub (AURORA globe flight deck) emits the d3-geo regime globe + the
   two-split Macro/Stock market cards + vector grid, and absorbs the intl/ipo/spr
   kwargs build_landing still passes.

Run as a script (no pytest needed): python -m tests.test_spvector_page
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001 — i18n absent -> identity, still renders
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


def _spvector_vm() -> dict:
    legs = [
        {"key": "drawdown", "label": "Macro-stress drawdown gauge", "label_zh": "x",
         "value": 15.0, "points": 4.3, "weight": 1.0, "lag": 10, "active": True, "color": "#D30B0B"},
        {"key": "recession", "label": "Recession risk", "label_zh": "x",
         "value": 4.0, "points": 1.1, "weight": 1.0, "lag": 22, "active": True, "color": "#F5AD42"},
        {"key": "liquidity", "label": "Net-liquidity contracting", "label_zh": "x",
         "value": 0.0, "points": 0.0, "weight": 0.5, "lag": 0, "active": True, "color": "#8FA5F6"},
    ]
    sc = {"cagr": 12.56, "cagr_nocarry": 10.5, "carry_pp": 2.0, "hodl_cagr": 10.82,
          "sharpe": 0.9, "hodl_sharpe": 0.65, "sortino": 1.2, "hodl_sortino": 0.8,
          "maxdd": -36.5, "hodl_maxdd": -55.2, "time_in_market": 98.0, "turnover_annual": 1.5,
          "years": 33.4, "bootstrap": {"sharpe_ci": [0.6, 0.9, 1.2]},
          "boot_sharpe_lo": 0.6, "boot_sharpe_hi": 1.2}
    at = {"after_tax_cagr": 8.0, "hodl_cagr": 10.8, "cumulative_tax_paid_x": 1.5, "st_rate": 0.35}
    bands = [
        {"label": "Low", "label_zh": "低", "rng": "< 25", "weight": 100, "cur": True},
        {"label": "Elevated", "label_zh": "偏高", "rng": "25–50", "weight": 66, "cur": False},
        {"label": "High", "label_zh": "高", "rng": "50–75", "weight": 33, "cur": False},
        {"label": "Extreme", "label_zh": "极端", "rng": "≥ 75", "weight": 0, "cur": False},
    ]
    return dict(
        as_of="Jun 12, 2026", built="2026-06-14", price=741.75, score=9,
        band_label="LOW — fully invested", band_label_zh="低", band_key="low", band_color="#1FA971",
        equity_w=100, cash_w=0, last_switch={"date": "2026-05-22", "frm": 66, "to": 100},
        next_note="next note", next_note_zh="x", legs=legs,
        disloc={"verdict": "calm", "verdict_zh": "平静", "put_absent": False, "capitulation": 1},
        sc=sc, at=at, bands=bands,
        episodes=[{"peak": "2007-10-09", "trough": "2009-03-09", "drawdown_pct": -55.2}],
        charts={"strategy": "<div>c</div>", "growth": "<div>c</div>", "dd": "<div>c</div>"})


def test_spvector_renders():
    from scripts.build_vector import C
    html = _env().get_template("spvector.html.j2").render(**_spvector_vm(), C=C)
    check("spvector renders non-empty", len(html) > 2000, f"len={len(html)}")
    check("no double-escaped entities", "&amp;amp;" not in html)
    for s in ["Allocation Strategy", "drawdown / Sharpe engine", "Taxable-account",
              "Macro-stress drawdown gauge", "rule-book", "permutation null", "after-tax"]:
        check(f"spvector contains: {s}", s.lower() in html.lower(), "missing")


def test_dashboard_compiles_and_splits():
    env = _env()
    for tpl in ("dashboard.html.j2", "china.html.j2", "gex.html.j2", "hk.html.j2", "spvector.html.j2"):
        try:
            env.get_template(tpl)               # compiles -> catches if/endif imbalance
            check(f"{tpl} compiles", True)
        except Exception as e:                  # noqa: BLE001
            check(f"{tpl} compiles", False, str(e))
    src = (ROOT / "templates" / "dashboard.html.j2").read_text()
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="index-health"', 'id="stocks-header"', "Regime-approved sectors",
              "Index risk model", "rm-bar", "chart_risk_model"):  # integrated risk model
        check(f"dashboard has split marker: {m}", m in src, "missing")
    # China + HK mirror the same macro/stocks mode split (rendered twice by their
    # builders -> <market>.html + <market>_stocks.html).
    cn = (ROOT / "templates" / "china.html.j2").read_text()
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="index-health"', 'id="stocks-header"', 'id="standouts"',
              "china_stocks.html"):
        check(f"china has split marker: {m}", m in cn, "missing")
    hk = (ROOT / "templates" / "hk.html.j2").read_text()
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="index-health"', 'id="stocks-header"', 'id="hk-screener"',
              "hk_stocks.html", "stock-selection edge"):
        check(f"hk has split marker: {m}", m in hk, "missing")


def test_hub_split_cards():
    from scripts import build_vector as bv
    vm = {"risk_on": False, "risk_word": "OFF", "risk_index": 39, "momentum": -0.8, "built": "2026-06-14"}
    macro = {"label": "Goldilocks", "date": "2026-06-12"}
    html = bv._hub_html(
        vm, macro, [], china={"label": "Stagflation", "present": True},
        hk={"label": "Stagflation", "risk": "Neutral", "present": True},
        us_stocks={"label": "12 standout setups", "n_setups": 12, "present": True},
        commodities={"present": False}, forex={"present": False}, bonds={"present": False},
        etf={"present": False}, watchlist={"present": False})
    # AURORA globe flight deck: an unbounded d3-geo regime globe + market-clock
    # sidebar, then two-split Macro/Stock market cards + the vector grid + alerts.
    nb = html.count("splitbtn")
    check("hub has globe deck", 'class="globe-deck' in html)
    check("hub has globe canvas", 'class="gd-canvas' in html)
    check("hub has globe-data blob", 'id="globe-data"' in html)
    check("hub has server-rendered legend twin (>=9)", html.count('class="gd-leg') >= 9)
    check("hub has two-split markets (>=8 buttons)", nb >= 8, f"splitbtns={nb}")
    check("hub has vector grid", 'class="nav vc' in html)
    for s in ("United States", "macro.html", "us_stocks.html", "china_stocks.html"):
        check(f"hub contains: {s}", s in html, "missing")
    check("no double-escaped entities in hub", "&amp;amp;" not in html)
    # Markup+str / markup-in-attribute regressions ESCAPE the bilingual spans -> the
    # tell-tale is a literal escaped "&lt;span" anywhere in the rendered hub.
    check("no escaped-markup leak in hub", "&lt;span" not in html)
    # build_landing passes intl/ipo/spr -> the hub MUST absorb them (else daily crash).
    check("hub absorbs intl/ipo/spr kwargs",
          bool(bv._hub_html(vm, macro, [], intl={}, ipo={}, spr={})))
    # graceful: China/HK didn't build -> still renders, US hero present
    html2 = bv._hub_html(
        vm, macro, [], china={"present": False}, hk={"present": False},
        us_stocks={"present": False}, commodities={"present": False}, forex={"present": False},
        bonds={"present": False}, etf={"present": False}, watchlist={"present": False})
    check("hub graceful without China/HK (US still present)", "United States" in html2)


def main() -> int:
    for fn in (test_spvector_renders, test_dashboard_compiles_and_splits, test_hub_split_cards):
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n{'=' * 40}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
