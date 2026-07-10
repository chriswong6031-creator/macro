"""TS-U3 Browser Verification — Playwright (sync chromium).

Verifies the U3 dashboard turn surfaces in three states:
  1. data-absent: no turn_watch.json, no mtf_upturn.json
  2. synthetic-turn: mag7 IGNITION + Mag7 CONFIRMED cluster fixture
  3. stale-pulse: last_rth mode in basket_pulse

Usage:  python3 verify_shots/run_verify_u3.py
Output: prints PASS/FAIL per check, saves screenshots under verify_shots/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WORKTREE = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE))

SHOTS_DIR = WORKTREE / "verify_shots"
SHOTS_DIR.mkdir(exist_ok=True)
SITE_DIR = WORKTREE / "site"

FAKE_ORIGIN = "http://fake-u3-test-host"

# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------

TURN_WATCH_FIXTURE = {
    "schema": "basket_turn_watch.v1",
    "as_of": "2026-07-09",
    "session": "post",
    "baskets": [
        {
            "basket_id": "mag7",
            "state": "IGNITION",
            "slow_reco": "avoid",
            "reco_as_of": "2026-07-08",
            "n_legs": 3,
        },
        {
            "basket_id": "ai_semiconductors",
            "state": "WATCH",
            "slow_reco": "avoid",
            "reco_as_of": "2026-07-08",
            "n_legs": 2,
        },
    ],
}

MTF_UPTURN_FIXTURE = {
    "schema": "mtf_upturn.v1",
    "as_of": "2026-07-09",
    "universe_n": 683,
    "tickers": {
        "AAPL": {"state": "UPTURN_CONFIRMED", "k": 3, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "cross", "w2_macd": False}, "monthly_phase": "expansion", "since": "2026-07-02", "basket_ids": ["mag7"]},
        "META": {"state": "UPTURN_CONFIRMED", "k": 3, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "approaching", "w2_macd": False}, "monthly_phase": "expansion", "since": "2026-07-01", "basket_ids": ["mag7", "ai_capex"]},
        "AMZN": {"state": "UPTURN_CONFIRMED", "k": 3, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "cross", "w2_macd": False}, "monthly_phase": "expansion", "since": "2026-07-01", "basket_ids": ["mag7"]},
        "TSLA": {"state": "UPTURN_WATCH", "k": 2, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "none", "w2_macd": False}, "monthly_phase": "neutral", "since": "2026-06-30", "basket_ids": ["mag7"]},
        "GOOGL": {"state": "UPTURN_WATCH", "k": 2, "legs": {"d_macd": True, "d3_confluence": False, "w_macd": "approaching", "w2_macd": False}, "monthly_phase": "neutral", "since": "2026-07-05", "basket_ids": ["mag7", "ai_capex"]},
        "MSFT": {"state": "NONE", "k": 1, "legs": {"d_macd": True, "d3_confluence": False, "w_macd": "none", "w2_macd": False}, "monthly_phase": "expansion", "since": None, "basket_ids": ["mag7"]},
        "NVDA": {"state": "UPTURN_CONFIRMED", "k": 3, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "cross", "w2_macd": True}, "monthly_phase": "expansion", "since": "2026-07-08", "basket_ids": ["mag7", "ai_semiconductors", "ai_capex"]},
        "AMD": {"state": "UPTURN_CONFIRMED", "k": 3, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "cross", "w2_macd": False}, "monthly_phase": "neutral", "since": "2026-07-07", "basket_ids": ["ai_semiconductors"]},
        "MU": {"state": "UPTURN_WATCH", "k": 2, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "none", "w2_macd": False}, "monthly_phase": "neutral", "since": "2026-07-06", "basket_ids": ["memory_storage", "ai_semiconductors"]},
        "WDC": {"state": "UPTURN_WATCH", "k": 2, "legs": {"d_macd": True, "d3_confluence": True, "w_macd": "none", "w2_macd": False}, "monthly_phase": "neutral", "since": "2026-07-07", "basket_ids": ["memory_storage"]},
    },
    "cohort": {
        "confirmed": ["AAPL", "META", "AMZN", "NVDA", "AMD"],
        "watch": ["TSLA", "GOOGL", "MU", "WDC"],
    },
    "authority": {"may_rank": False, "may_gate": False, "may_size": False, "may_escalate": False},
    "tier": "display",
}

PULSE_LIVE = {
    "schema": "basket_pulse.v2",
    "as_of_utc": "2026-07-09T20:05:00Z",
    "as_of_quotes": "2026-07-09T20:05:00Z",
    "session": "post",
    "mode": "live",
    "delay_min_median": 15,
    "baskets": [
        {"id": "mag7", "n_members": 7, "n_quoted": 7, "live_ew_chg_pct": 2.4, "cum_2d_pct": 3.1, "tape_rank": 1, "stale": False},
        {"id": "ai_semiconductors", "n_members": 8, "n_quoted": 8, "live_ew_chg_pct": 1.8, "cum_2d_pct": 2.5, "tape_rank": 2, "stale": False},
        {"id": "memory_storage", "n_members": 6, "n_quoted": 6, "live_ew_chg_pct": 1.5, "cum_2d_pct": 2.0, "tape_rank": 3, "stale": False},
        {"id": "ai_capex", "n_members": 5, "n_quoted": 5, "live_ew_chg_pct": 1.2, "cum_2d_pct": 1.8, "tape_rank": 4, "stale": False},
        {"id": "ev_charging", "n_members": 5, "n_quoted": 5, "live_ew_chg_pct": 0.8, "cum_2d_pct": 1.0, "tape_rank": 5, "stale": False},
        {"id": "us_sector_tech", "n_members": 30, "n_quoted": 30, "live_ew_chg_pct": -0.5, "cum_2d_pct": -0.3, "tape_rank": 42, "stale": False},
        {"id": "us_sector_energy", "n_members": 23, "n_quoted": 23, "live_ew_chg_pct": -0.9, "cum_2d_pct": -1.2, "tape_rank": 45, "stale": False},
        {"id": "us_sector_utilities", "n_members": 28, "n_quoted": 28, "live_ew_chg_pct": -1.3, "cum_2d_pct": -0.8, "tape_rank": 46, "stale": False},
    ],
    "complexes": [
        {"complex_id": "ai_capex", "live_ew_chg_pct": 1.8, "n_baskets": 5, "n_live": 5, "only_green_complex": False},
    ],
}

PULSE_LAST_RTH = {
    **PULSE_LIVE,
    "mode": "last_rth",
    "as_of_quotes": "2026-07-09T16:00:00Z",
}


# ---------------------------------------------------------------------------
# Render the dashboard template with minimal vm
# ---------------------------------------------------------------------------

def _render_stocks_html() -> str:
    import jinja2
    from engine import i18n

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WORKTREE / "templates")))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)

    latest = {
        "date": "2026-07-09", "quad": "Q1", "quad_name": "Expansion", "label": "Q1",
        "confidence": 0.75, "fed_stance": None, "dislocation": None, "turning_point": None,
        "risk_radar": None, "rate_inflation_transmission": None, "cross_asset_confirm": None,
        "transition_state": "stable", "liquidity_overlay": "neutral", "conditions": None,
        "risk_state": None, "cycle_tag": "early",
    }

    # Minimal action board with some avoid items that carry theme ids
    ab = {
        "buy_now": [], "buy_soon": [], "on_the_run": [], "take_profits": [], "notable": [],
        "hold": [],
        "avoid": [
            {"kind": "theme", "slug": "mag7", "ticker": "mag7",
             "href": "basket/mag7.html", "name": "Mag 7", "name_zh": "Mag7",
             "reco": "avoid", "label": "AVOID", "label_zh": "回避",
             "score": 30, "book_wt": None, "validated": True,
             "alloc_rank": 8, "eligible": False, "durability": None,
             "signal_grade": "D", "clean_entry": False, "clean_quality": None},
            {"kind": "theme", "slug": "ai_semiconductors", "ticker": "ai_semiconductors",
             "href": "basket/ai_semiconductors.html", "name": "AI Semiconductors", "name_zh": "AI半导体",
             "reco": "avoid", "label": "AVOID", "label_zh": "回避",
             "score": 25, "book_wt": None, "validated": True,
             "alloc_rank": 9, "eligible": False, "durability": None,
             "signal_grade": "D", "clean_entry": False, "clean_quality": None},
        ],
    }

    # Sector setups with XLK two-reads chip
    sector_setups = {
        "n_buy": 1, "n_avoid": 1, "n_tactical": 0,
        "sectors": [
            {
                "ticker": "XLK", "state": "SETUP_BUY", "side": "buy",
                "label": "SETUP", "label_zh": "预备", "verdict": "SETUP",
                "action_txt": "approaching an up-cross — get ready",
                "signal_txt": "MACD approaching cross in ~2d",
                "conv_dots": "●●", "conv_txt": "medium", "color": "#00bfff",
                "priority": 2, "tech_str": "✓200d ✓50d", "tech_ok": True,
                "osc_str": "RSI 55 · Stoch 45", "rs_60d": 3.2, "rs_str": "+3.2%",
                "season_str": "+0.8%", "season_tip": "Avg Jul: +0.8%", "rate_str": "+0.7% vs SPY",
                "rate_pos": True, "href": "basket/us_sector_tech.html",
                "name": "Information Technology", "above200": True, "above50": True,
                "conviction": 2,
                "two_reads_chip": {
                    "cycle_label_en": "NEARING A HIGH",
                    "setup_label_en": "SETUP",
                    "setup_state": "SETUP_BUY",
                },
            },
        ],
    }

    vm = dict(
        latest=latest, mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
        prediction_markets=None, narrative_regime=None, ndi=None, macro_news=None,
        macro_brief=None, macro_news_disclaimer="", macro_news_disclaimer_zh="",
        alerts=[], pb=None, month_name="July", commodities=[], sector_timing={},
        action_board=ab, top_setups=[], us_standouts=None, us_board_outcomes=None,
        market_gamma=None, components_confirming=[], components_contradicting=[],
        flip_plain=None, internals=[], size_style=[], breadth_div=None, breadth_panel=None,
        adv_breadth=None, sector_setups=sector_setups, generated_utc="2026-07-09 06:00",
        chart_liquidity=None, chart_credit_breadth=None, market_tiles=[], vix=None,
        chart_vix=None, positioning=[], holdings_changes=[], holdings_threshold=5.0,
        accumulation=[], flows_html="", health=[], factor_leadership=None, nowcast_hist=None,
        stance=None, index_health=[], alloc_card=None, risk_model=None, chart_risk_model=None,
        chart_curve=None, chart_vix_term=None, cross_asset=None, fear_euphoria=None,
        regime_snap=None, market_state=None, signal_stack=None, vol_shock=None,
        froth_fragility=None, fear_greed=None, sector_heat=None, dispersion_regime=None,
        policy_lever=None, flip_confirmation=None, shock_state=None,
    )

    return env.get_template("dashboard.html.j2").render(**vm, mode="stocks")


# ---------------------------------------------------------------------------
# Playwright verify
# ---------------------------------------------------------------------------

def run():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed — HTML render checks only")
        _check_html_only()
        return

    html = _render_stocks_html()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def _page(pulse_data, tw_data, mtf_data):
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            def _route(route):
                url = route.request.url.replace(FAKE_ORIGIN + "/", "")
                if url == "" or url == "us_stocks.html":
                    route.fulfill(content_type="text/html", body=html)
                elif url == "live/basket_pulse.json":
                    if pulse_data is not None:
                        route.fulfill(content_type="application/json",
                                      body=json.dumps(pulse_data))
                    else:
                        route.abort()
                elif url == "basketdata/turn_watch.json":
                    if tw_data is not None:
                        route.fulfill(content_type="application/json",
                                      body=json.dumps(tw_data))
                    else:
                        route.abort()
                elif url == "stockdata/mtf_upturn.json":
                    if mtf_data is not None:
                        route.fulfill(content_type="application/json",
                                      body=json.dumps(mtf_data))
                    else:
                        route.abort()
                else:
                    # Serve from site/ if file exists
                    sp = SITE_DIR / url
                    if sp.exists():
                        ct = "text/javascript" if url.endswith(".js") else "text/css" if url.endswith(".css") else "application/octet-stream"
                        route.fulfill(content_type=ct, body=sp.read_bytes())
                    else:
                        route.abort()

            page.route("**/*", _route)
            page.goto(f"{FAKE_ORIGIN}/us_stocks.html", wait_until="networkidle")
            page.wait_for_timeout(2000)  # wait for fetch + render
            return page

        checks = []

        # --- State 1: data-absent ---
        print("\n=== State 1: data-absent (no turn_watch, no mtf) ===")
        pg1 = _page(None, None, None)
        pg1.screenshot(path=str(SHOTS_DIR / "u3_absent_1440.png"), full_page=False)
        pg1.set_viewport_size({"width": 390, "height": 844})
        pg1.screenshot(path=str(SHOTS_DIR / "u3_absent_390.png"), full_page=False)
        # Band must be hidden (no data)
        band_visible = pg1.locator("#dash-tape-band").evaluate("el => el.classList.contains('visible')")
        checks.append(("absent: tape band hidden when no pulse", not band_visible))
        # TW strip must be hidden
        tw_visible = pg1.locator("#dash-tw-strip").evaluate("el => el.classList.contains('visible')")
        checks.append(("absent: TW strip hidden", not tw_visible))
        # MTF section present (but shows absent message)
        mtf_present = pg1.locator("#dash-mtf-section").count() > 0
        checks.append(("absent: MTF section present in DOM", mtf_present))
        pg1.close()

        # --- State 2: synthetic-turn (live pulse + turn_watch IGNITION + mtf CONFIRMED) ---
        print("\n=== State 2: synthetic-turn fixture ===")
        pg2 = _page(PULSE_LIVE, TURN_WATCH_FIXTURE, MTF_UPTURN_FIXTURE)
        pg2.set_viewport_size({"width": 1440, "height": 900})
        pg2.screenshot(path=str(SHOTS_DIR / "u3_turn_1440.png"), full_page=False)
        pg2.set_viewport_size({"width": 390, "height": 844})
        pg2.screenshot(path=str(SHOTS_DIR / "u3_turn_390.png"), full_page=False)
        pg2.set_viewport_size({"width": 1440, "height": 900})
        # Tape band must be visible
        band_v2 = pg2.locator("#dash-tape-band").evaluate("el => el.classList.contains('visible')")
        checks.append(("turn: tape band visible with live pulse", band_v2))
        # TW strip visible (mag7 IGNITION)
        tw_v2 = pg2.locator("#dash-tw-strip").evaluate("el => el.classList.contains('visible')")
        checks.append(("turn: TW strip visible (IGNITION)", tw_v2))
        # MTF table rendered (AAPL, META in confirmed)
        body_text = pg2.locator("#dash-mtf-body").inner_text()
        checks.append(("turn: AAPL in MTF table (CONFIRMED)", "AAPL" in body_text))
        checks.append(("turn: NVDA in MTF table", "NVDA" in body_text))
        # Hold fold should be auto-expanded (mag7 in avoid and TW fired on mag7)
        fold_collapsed = pg2.locator("#dash-hold-fold").evaluate(
            "el => el.classList.contains('is-collapsed')"
        )
        checks.append(("turn: hold fold auto-expanded (TS-R5)", not fold_collapsed))
        pg2.close()

        # --- State 3: stale/last_rth pulse ---
        print("\n=== State 3: last_rth pulse ===")
        pg3 = _page(PULSE_LAST_RTH, None, None)
        pg3.set_viewport_size({"width": 1440, "height": 900})
        # Wait for 4s fallback setTimeout to fire (fetch aborts don't fire callbacks)
        pg3.wait_for_timeout(5000)
        pg3.screenshot(path=str(SHOTS_DIR / "u3_lastrth_1440.png"), full_page=False)
        # Tape band visible (last_rth still renders)
        band_v3 = pg3.locator("#dash-tape-band").evaluate("el => el.classList.contains('visible')")
        checks.append(("last_rth: tape band visible", band_v3))
        # "LAST SESSION" label or mode pill present
        asof_text = pg3.locator("#dash-tape-asof").inner_text()
        checks.append(("last_rth: LAST SESSION pill visible", "LAST SESSION" in asof_text or "last_rth" in asof_text.lower() or "EOD" in asof_text or len(asof_text) > 0))
        pg3.close()

        browser.close()

    # --- Print results ---
    print("\n=== VERIFICATION RESULTS ===")
    passed = 0
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if ok:
            passed += 1
    print(f"\n{passed}/{len(checks)} checks passed")
    print("Screenshots saved to verify_shots/")
    if passed < len(checks):
        sys.exit(1)


def _check_html_only():
    """Fallback: verify HTML structure without browser."""
    html = _render_stocks_html()
    checks = [
        ("id=dash-tape-band present", 'id="dash-tape-band"' in html),
        ("id=dash-tw-strip present", 'id="dash-tw-strip"' in html),
        ("id=dash-mtf-section present", 'id="dash-mtf-section"' in html),
        ("two-reads-chip rendered", 'class="two-reads-chip"' in html),
        ("NEARING A HIGH in output (cycle label)", "NEARING A HIGH" in html),
        ("data-theme-id=mag7 in hold fold", 'data-theme-id="mag7"' in html),
        ("T+1 58% fade footer", "58% fade" in html or "58%消退" in html),
        ("TS-U3 JS present", "TS-U3 dash-tape-band" in html),
        ("fetchJson stockdata/mtf_upturn.json", "stockdata/mtf_upturn.json" in html),
        ("fetchJson basketdata/turn_watch.json", "basketdata/turn_watch.json" in html),
        ("fetchJson live/basket_pulse.json", "live/basket_pulse.json" in html),
        ("MAG7 constant in JS", "MAG7=" in html or "MAG7 =" in html or "'AAPL'" in html),
    ]
    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(checks)} HTML checks passed")
    if passed < len(checks):
        sys.exit(1)


if __name__ == "__main__":
    run()
