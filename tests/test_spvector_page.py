"""Render-smoke + structure tests for the split market pages.

 - spvector.html.j2 (US allocation deep-dive) renders, carries the mandated
   honesty caveats, and has no double-escaped entities.
 - dashboard.html.j2 compiles (the macro/stocks mode-conditional if/endif balance)
   and carries the split markers; same for the nav-edited china/gex/hk templates.
 - the landing hub (AURORA globe flight deck) emits the d3-geo regime globe + the
   two-split Macro/Stock market cards + vector grid, and absorbs the intl/ipo/spr
   kwargs build_landing still passes.

Every pin is a plain ``assert`` so pytest can actually go red on it (the file's
original ``check()`` helper only printed and tallied — under pytest a FAIL was
decorative, and for months the only thing that could red this suite was an
exception).

Run as a script (no pytest needed): python -m tests.test_spvector_page
"""
from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent


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
    assert len(html) > 2000, f"spvector rendered suspiciously small: len={len(html)}"
    assert "&amp;amp;" not in html, "double-escaped entities in spvector"
    for s in ["Allocation Strategy", "drawdown / Sharpe engine", "Taxable-account",
              "Macro-stress drawdown gauge", "rule-book", "permutation null", "after-tax"]:
        assert s.lower() in html.lower(), f"spvector missing mandated copy: {s!r}"


def test_suite_has_no_decorative_soft_check_helper():
    """Keep #5076's useful diagnosis without restoring its stale page markers.

    The stronger #5062 repair replaced the old print-and-tally ``check()`` helper
    with direct assertions. A later copy/paste of that helper would make failures
    decorative under pytest again, so guard the shape through the Python AST while
    leaving the current dashboard, China, and HK successor markers authoritative.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    soft_defs = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "check"
    ]
    soft_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "check"
    ]
    assert not soft_defs and not soft_calls, (
        "test_spvector_page.py reintroduced decorative check() gates: "
        f"definitions={soft_defs}, calls={soft_calls}"
    )


def test_dashboard_compiles_and_splits():
    env = _env()
    for tpl in ("dashboard.html.j2", "china.html.j2", "gex.html.j2", "hk.html.j2", "spvector.html.j2"):
        env.get_template(tpl)               # compiles -> raises on if/endif imbalance
    src = (ROOT / "templates" / "dashboard.html.j2").read_text()
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="index-health"', 'id="stocks-header"', "us_stocks.html",
              "Index risk model", "rm-bar", "chart_risk_model"):  # integrated risk model
        assert m in src, f"dashboard lost split marker: {m!r}"
    # China + HK mirror the same macro/stocks mode split (rendered twice by their
    # builders -> <market>.html + <market>_stocks.html). Their index-health boards
    # were demoted from always-on panels into the glance-tier markets dialogs
    # (china: mx5 redesign #2589; hk: copy simplification #1337) — the pin follows
    # the successor container plus the index_health data contract it consumes.
    cn = (ROOT / "templates" / "china.html.j2").read_text()
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="cnx-dlg-markets"', "index_health", 'id="stocks-header"',
              'id="standouts"', "china_stocks.html"):
        assert m in cn, f"china lost split marker: {m!r}"
    hk = (ROOT / "templates" / "hk.html.j2").read_text()
    # "mostly risk exposures" is the surviving honest-stance line of the screener
    # (successor of the long "no idiosyncratic stock-selection edge" caveat, which
    # #1337 rewrote to glance-tier plain words — the disclosure itself must stay).
    for m in ("mode == 'stocks'", "mode != 'stocks'", "mode != 'macro'",
              'id="hkx-dlg-markets"', "index_health", 'id="stocks-header"',
              'id="hk-screener"', "hk_stocks.html", "mostly risk exposures"):
        assert m in hk, f"hk lost split marker: {m!r}"


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
    assert 'class="globe-deck' in html, "hub lost the globe deck"
    assert 'class="gd-canvas' in html, "hub lost the globe canvas"
    assert 'id="globe-data"' in html, "hub lost the globe-data blob"
    assert html.count('class="gd-leg') >= 9, "hub server-rendered legend twin under 9 entries"
    assert nb >= 8, f"hub two-split market buttons: splitbtns={nb} < 8"
    assert 'class="nav vc' in html, "hub lost the vector grid"
    for s in ("United States", "macro.html", "us_stocks.html", "china_stocks.html"):
        assert s in html, f"hub missing: {s!r}"
    assert "&amp;amp;" not in html, "double-escaped entities in hub"
    # Markup+str / markup-in-attribute regressions ESCAPE the bilingual spans -> the
    # tell-tale is a literal escaped "&lt;span" anywhere in the rendered hub.
    assert "&lt;span" not in html, "escaped-markup leak in hub"
    # build_landing passes intl/ipo/spr -> the hub MUST absorb them (else daily crash).
    assert bv._hub_html(vm, macro, [], intl={}, ipo={}, spr={}), \
        "hub did not absorb intl/ipo/spr kwargs"
    # graceful: China/HK didn't build -> still renders, US hero present
    html2 = bv._hub_html(
        vm, macro, [], china={"present": False}, hk={"present": False},
        us_stocks={"present": False}, commodities={"present": False}, forex={"present": False},
        bonds={"present": False}, etf={"present": False}, watchlist={"present": False})
    assert "United States" in html2, "hub not graceful without China/HK (US hero gone)"


def main() -> int:
    tests = (
        test_spvector_renders,
        test_suite_has_no_decorative_soft_check_helper,
        test_dashboard_compiles_and_splits,
        test_hub_split_cards,
    )
    failed = 0
    for fn in tests:
        print(f"\n{fn.__name__}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — CLI mirror of a pytest failure
            failed += 1
            print(f"  FAIL  {type(e).__name__}: {e}")
        else:
            print("  PASS")
    print(f"\n{'=' * 40}\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
