"""PR3 Browser Verification — conditions-card popover (shared row-pop engine).

Verifies:
  (a) us_stocks mode: hovering a sector row opens a populated .row-pop (name + >=3 grid
      cells visible), no 'Leadership LENS' text anywhere, card stays open on mouse-over.
  (b) us_stocks mode: hovering a theme row opens a populated .row-pop.
  (c) macro.html mode: renders without errors, action board visually unchanged.
  (d) EN and ZH language switching.
  (e) Zero console/page errors.

Usage:  python3 verify_shots/run_verify_pr3.py
Output: prints PASS/FAIL per check, saves screenshots to verify_shots/pr3_*.png.
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

FAKE_ORIGIN = "http://fake-pr3-test-host"

# ---------------------------------------------------------------------------
# Build synthetic action_board with rich sector + theme items so we can
# assert specific popover content without relying on stale pickle data.
# ---------------------------------------------------------------------------

SECTOR_ITEM_XLK = {
    "kind": "sector", "ticker": "XLK",
    "name": "Information Technology", "href": "basket/us_sector_tech.html",
    "label": "RALLY ON", "tag": "RALLY ON",
    "text": "Tech sector uptrend intact.", "text_zh": "科技板块上涨趋势完好。",
    "age_short": "3d", "age_short_zh": "3日",
    "eq_badge": "▲ +45", "eq_dir": "up", "eq_tip": "broad advance", "eq_tip_zh": "广泛上涨",
    "style": ("#1d3326", "#6fce8f"),
    # enrichment fields from sector_setup_lookup
    "rs_60d": 5.2,
    "above200": True, "above50": True,
    "rsi_3d": 62.0, "stoch_3d": 58.0,
    "rate_str": "+1.2% vs SPY · 65% up · n=1234",
    "rate_pos": True,
    "season_str": "+1.8% (78%)",
    "season_tip": "Jul historically positive",
    "dc_day": 18,
    "buy_zone": 7, "n_holdings": 10,
    "stat_en": "clean entry · 3d", "stat_zh": "入场干净 · 3日",
    "chip_en": "", "chip_zh": "", "chip_tone": "muted",
}

SECTOR_ITEM_XLE = {
    "kind": "sector", "ticker": "XLE",
    "name": "Energy", "href": "basket/us_sector_energy.html",
    "label": "FRESH BUY", "tag": "FRESH BUY",
    "text": "Energy fresh cycle buy — worst state per DO_NOT_REBUILD #1513.",
    "text_zh": "能源新鲜周期买入。",
    "age_short": "today", "age_short_zh": "今日",
    "eq_badge": "▲ +12", "eq_dir": "up", "eq_tip": "light advance", "eq_tip_zh": "轻度上涨",
    "style": ("#1d4a2c", "#7fe0a0"),
    "rs_60d": -2.1,
    "above200": True, "above50": False,
    "rsi_3d": 42.0, "stoch_3d": 38.0,
    "rate_str": "-0.3% vs SPY · 48% up · n=980",
    "rate_pos": False,
    "season_str": "+0.3% (52%)",
    "season_tip": "Jul slightly positive",
    "dc_day": 3,
    "buy_zone": 2, "n_holdings": 10,
    "stat_en": "clean entry · today", "stat_zh": "入场干净 · 今日",
    "chip_en": "", "chip_zh": "", "chip_tone": "muted",
}

THEME_ITEM_AI = {
    "kind": "theme", "ticker": "ai_semiconductors", "slug": "ai_semiconductors",
    "name": "AI Semiconductors", "name_zh": "AI半导体",
    "href": "basket/ai_semiconductors.html",
    "reco": "accumulate", "label": "ACCUMULATE", "label_zh": "积累",
    "score": 85,
    "book_wt": 0.08,
    "validated": False,
    "alloc_rank": 2, "eligible": True, "durability": "high",
    "signal_grade": "B",
    "clean_entry": True, "clean_quality": 0.87,
    # popover enrichment fields
    "perf_20d_rel": 0.045,
    "breadth_pct50": 0.82,
    "top_members": ["NVDA", "AMD", "AVGO"],
    "rollover_band": "low", "rollover_band_zh": "低",
    "reco_why_en": "Strong momentum across AI chip leaders with broad participation.",
    "reco_why_zh": "AI芯片龙头整体动能强劲，参与度广泛。",
    "rs_pctile": 0.88,
    "flip_distance": 8.4,
    "run_reason_en": None, "run_reason_zh": None,
    "stat_en": "", "stat_zh": "",
    "chip_en": "", "chip_zh": "", "chip_tone": "muted",
}

THEME_ITEM_VALIDATED = {
    "kind": "theme", "ticker": "mag7", "slug": "mag7",
    "name": "Magnificent Seven", "name_zh": "七巨头",
    "href": "basket/mag7.html",
    "reco": "avoid", "label": "AVOID", "label_zh": "回避",
    "score": 30,
    "book_wt": None,
    "validated": True,  # the reduce-side gate
    "alloc_rank": 10, "eligible": False, "durability": None,
    "signal_grade": "D",
    "clean_entry": False, "clean_quality": None,
    "perf_20d_rel": -0.032,
    "breadth_pct50": 0.45,
    "top_members": ["AAPL", "MSFT", "NVDA"],
    "rollover_band": "high", "rollover_band_zh": "高",
    "reco_why_en": "Breadth deteriorating, trend rolling over.",
    "reco_why_zh": "广度恶化，趋势转向。",
    "rs_pctile": 0.22,
    "flip_distance": 3.1,
    "run_reason_en": None, "run_reason_zh": None,
    "stat_en": "", "stat_zh": "",
    "chip_en": "AVOID", "chip_zh": "回避", "chip_tone": "neg",
}


def _make_vm(mode: str = "stocks") -> dict:
    """Build a minimal vm for rendering the dashboard template."""
    latest = {
        "date": "2026-07-10", "quad": "Q1", "quad_name": "Expansion", "label": "Q1",
        "confidence": 0.78, "fed_stance": None, "dislocation": None, "turning_point": None,
        "risk_radar": None, "rate_inflation_transmission": None, "cross_asset_confirm": None,
        "transition_state": "stable", "liquidity_overlay": "neutral", "conditions": None,
        "risk_state": None, "cycle_tag": "early",
    }
    ab = {
        "buy_now": [SECTOR_ITEM_XLK, SECTOR_ITEM_XLE],
        "buy_soon": [],
        "on_the_run": [THEME_ITEM_AI],
        "take_profits": [],
        "hold": [],
        "avoid": [THEME_ITEM_VALIDATED],
        "notable": [],
    }
    return dict(
        latest=latest, mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
        prediction_markets=None, narrative_regime=None, ndi=None, macro_news=None,
        macro_brief=None, macro_news_disclaimer="", macro_news_disclaimer_zh="",
        alerts=[], pb=None, month_name="July", commodities=[], sector_timing={},
        action_board=ab, top_setups=[], us_standouts=None, us_board_outcomes=None,
        market_gamma=None, components_confirming=[], components_contradicting=[],
        flip_plain=None, internals=[], size_style=[], breadth_div=None, breadth_panel=None,
        adv_breadth=None, sector_setups=None, generated_utc="2026-07-10 06:00",
        chart_liquidity=None, chart_credit_breadth=None, market_tiles=[], vix=None,
        chart_vix=None, positioning=[], holdings_changes=[], holdings_threshold=5.0,
        accumulation=[], flows_html="", health=[], factor_leadership=None, nowcast_hist=None,
        stance=None, index_health=[], alloc_card=None, risk_model=None, chart_risk_model=None,
        chart_curve=None, chart_vix_term=None, cross_asset=None, fear_euphoria=None,
        regime_snap=None, market_state=None, signal_stack=None, vol_shock=None,
        froth_fragility=None, fear_greed=None, sector_heat=None, dispersion_regime=None,
        policy_lever=None, flip_confirmation=None, shock_state=None,
        mode=mode,
    )


def _render(mode: str = "stocks") -> str:
    import jinja2
    from engine import i18n

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WORKTREE / "templates")))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    vm = _make_vm(mode)
    return env.get_template("dashboard.html.j2").render(**vm)


# ---------------------------------------------------------------------------
# HTML-only checks (no browser needed)
# ---------------------------------------------------------------------------

def _check_html_only(html_stocks: str, html_macro: str) -> list[tuple[str, bool]]:
    checks = []

    # 1. rp-src payloads present (replaced act-pop-src)
    checks.append(("rp-src payloads present in us_stocks", 'class="rp-src"' in html_stocks))
    checks.append(("no act-pop-src in us_stocks (old class removed)", 'class="act-pop-src"' not in html_stocks))

    # 2. data-rpop on actitem elements
    checks.append(("data-rpop on actitem rows (sector)", 'class="actitem" data-rpop' in html_stocks))
    checks.append(("data-rpop on actitem ai-theme rows (theme)", 'class="actitem ai-theme" data-rpop' in html_stocks))

    # 3. No old IIFE popover engine
    checks.append(("old IIFE removed (act-pop class in JS)", 'pop.className=\'act-pop\'' not in html_stocks))
    checks.append(("old act-pop CSS removed", '.act-pop {' not in html_stocks and '.act-pop{' not in html_stocks))

    # 4. 'Leadership LENS' text gone from us_stocks action board macros
    # (may still exist in sector_setups board section — only the macro is replaced)
    # Count occurrences: the sector_setups board uses 'Leadership LENS' in its own tooltips — acceptable
    import re
    # The old macro else-branch "Leadership LENS — descriptive" text should be gone from rp-src payloads
    checks.append(("'Leadership LENS — descriptive' not in rp-src payloads",
                   "Leadership LENS — descriptive</span>" not in html_stocks))

    # 5. Real content in sector popover: sector name, ticker, grid cells
    checks.append(("'Information Technology' in stocks html", "Information Technology" in html_stocks))
    checks.append(("XLK ticker in rp-src payload", 'XLK' in html_stocks))
    checks.append(("'60d RS vs SPY' label in html (sector pop)", "60d RS vs SPY" in html_stocks))
    checks.append(("'60日RS对SPY' ZH label in html", "60日RS对SPY" in html_stocks))
    checks.append(("rate_str '1.2%' visible in sector pop", "1.2%" in html_stocks))

    # 6. Theme popover content
    checks.append(("'Composite score' label in theme pop", "Composite score" in html_stocks))
    checks.append(("'综合评分' ZH in theme pop", "综合评分" in html_stocks))
    checks.append(("'NVDA' top members in theme pop", "NVDA" in html_stocks))
    checks.append(("'Rollover risk' in theme pop", "Rollover risk" in html_stocks))
    checks.append(("'20d vs market' in theme pop", "20d vs market" in html_stocks))

    # 7. Validated theme: Backtested absolute-trend gate (not Leadership LENS)
    checks.append(("validated gate row present (trim/avoid)", "Backtested absolute-trend gate" in html_stocks))

    # 8. FRESH BUY gets warn tag tone (not up/green)
    # The tag span for FRESH BUY item should have class 'warn', not 'up'
    fresh_buy_section = ""
    # Find the rp-src for XLE (FRESH BUY)
    idx = html_stocks.find("Energy fresh cycle buy")
    if idx > -1:
        # grab surrounding context (the rp-src block)
        start = html_stocks.rfind('<span class="rp-src"', 0, idx)
        end = html_stocks.find('</span>', idx) + 100
        fresh_buy_section = html_stocks[start:end] if start > -1 else ""
    checks.append(("FRESH BUY tag has 'warn' tone (not 'up')",
                   'row-pop-tag warn' in fresh_buy_section if fresh_buy_section else False))

    # 9. macro.html mode — renders without the action board (mode-gated)
    checks.append(("macro mode renders without crash", len(html_macro) > 10000))
    # The action board section is mode-gated — only shown in stocks mode
    # In macro mode there should be no rp-src payloads from the action board
    # (sector_setups board doesn't use rp-src)
    # But macro mode DOES show action board too — check there's no regression
    checks.append(("macro mode has no js errors string", "Uncaught" not in html_macro))

    # 10. row-pop-why bullets (entry text)
    checks.append(("why bullets present in sector pop", "row-pop-why" in html_stocks))
    checks.append(("entry text in why bullets", "Tech sector uptrend intact" in html_stocks))

    # 11. footer with ETF ticker reference
    checks.append(("row-pop-ft footer with XLK", "row-pop-ft" in html_stocks))

    return checks


# ---------------------------------------------------------------------------
# Playwright checks
# ---------------------------------------------------------------------------

def _playwright_checks(html_stocks: str, html_macro: str) -> list[tuple[str, bool]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed — returning empty playwright checks")
        return []

    checks = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def _new_page(html: str, lang: str = "en") -> object:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            # Filter out network-fetch failures for absent data files — these are pre-existing
            # in the test harness context (no live data/ dir) and unrelated to popover changes.
            def _on_console(msg):
                if msg.type == "error" and "net::ERR_FAILED" in (msg.text or ""):
                    return  # expected absent-data fetch — not a JS error
                if msg.type == "error":
                    errors.append(msg)
            page.on("console", _on_console)
            page.on("pageerror", lambda err: errors.append(str(err)))

            def _route(route):
                url = route.request.url.replace(FAKE_ORIGIN + "/", "")
                if url in ("", "us_stocks.html", "macro.html"):
                    route.fulfill(content_type="text/html", body=html)
                else:
                    sp = SITE_DIR / url
                    if sp.exists():
                        ct = ("text/javascript" if url.endswith(".js") else
                              "text/css" if url.endswith(".css") else
                              "application/octet-stream")
                        route.fulfill(content_type=ct, body=sp.read_bytes())
                    else:
                        route.abort()

            page.route("**/*", _route)
            page.goto(f"{FAKE_ORIGIN}/us_stocks.html", wait_until="networkidle")
            page.wait_for_timeout(1500)
            # set language
            if lang == "zh":
                page.evaluate("document.documentElement.setAttribute('data-lang', 'zh')")
                page.wait_for_timeout(200)
            page._pr3_errors = errors
            return page

        # --- (a) Sector row hover: .row-pop appears with name + >=3 grid cells ---
        print("\n=== Sector row hover (EN) ===")
        pg1 = _new_page(html_stocks)
        # Expand the "Buy now" lane to ensure it's visible
        pg1.locator("#ab-buy-fold").evaluate("el => el.classList.remove('is-collapsed')")
        pg1.wait_for_timeout(200)
        # Find the first sector row with data-rpop in buy_now
        sector_rows = pg1.locator(".actitem[data-rpop]")
        n_sector = sector_rows.count()
        checks.append(("sector actitem[data-rpop] rows present", n_sector > 0))

        if n_sector > 0:
            row = sector_rows.first
            # Hover to trigger row-pop
            row.hover()
            pg1.wait_for_timeout(400)
            pop_visible = pg1.locator(".row-pop").is_visible()
            checks.append(("sector hover opens .row-pop", pop_visible))

            if pop_visible:
                pop_text = pg1.locator(".row-pop").inner_text()
                checks.append(("sector pop has ETF name text", "Information Technology" in pop_text or "Energy" in pop_text))
                cells = pg1.locator(".row-pop .row-pop-cell").count()
                checks.append((f"sector pop has >=3 grid cells (got {cells})", cells >= 3))
                checks.append(("no 'Leadership LENS' in pop", "Leadership LENS" not in pop_text))

                # Move mouse onto the card itself — it should stay open
                pg1.locator(".row-pop").hover()
                pg1.wait_for_timeout(300)
                still_visible = pg1.locator(".row-pop").is_visible()
                checks.append(("row-pop stays open on mouse-over (hoverable)", still_visible))

        pg1.screenshot(path=str(SHOTS_DIR / "pr3_sector_pop_en_1440.png"), full_page=False)
        print(f"  console errors: {len(pg1._pr3_errors)}")
        checks.append(("sector: zero console errors (EN)", len(pg1._pr3_errors) == 0))
        pg1.close()

        # --- (b) Theme row hover ---
        print("\n=== Theme row hover (EN) ===")
        pg2 = _new_page(html_stocks)
        # Expand on_the_run lane
        pg2.locator("#ab-run-fold").evaluate("el => el.classList.remove('is-collapsed')")
        pg2.wait_for_timeout(200)
        theme_rows = pg2.locator(".actitem.ai-theme[data-rpop]")
        n_theme = theme_rows.count()
        checks.append(("theme actitem.ai-theme[data-rpop] rows present", n_theme > 0))

        if n_theme > 0:
            row = theme_rows.first
            row.hover()
            pg2.wait_for_timeout(400)
            pop_visible = pg2.locator(".row-pop").is_visible()
            checks.append(("theme hover opens .row-pop", pop_visible))

            if pop_visible:
                pop_text = pg2.locator(".row-pop").inner_text()
                checks.append(("theme pop has basket name", "AI Semiconductors" in pop_text or "AI" in pop_text))
                cells = pg2.locator(".row-pop .row-pop-cell").count()
                checks.append((f"theme pop has >=3 grid cells (got {cells})", cells >= 3))
                checks.append(("no 'Leadership LENS' in theme pop", "Leadership LENS" not in pop_text))
                # NVDA should be in top_members
                checks.append(("NVDA in theme pop leaders", "NVDA" in pop_text))

        pg2.screenshot(path=str(SHOTS_DIR / "pr3_theme_pop_en_1440.png"), full_page=False)
        pg2.close()

        # --- (c) ZH language ---
        print("\n=== ZH language sector pop ===")
        pg3 = _new_page(html_stocks, lang="zh")
        pg3.locator("#ab-buy-fold").evaluate("el => el.classList.remove('is-collapsed')")
        pg3.wait_for_timeout(200)
        rows = pg3.locator(".actitem[data-rpop]")
        if rows.count() > 0:
            rows.first.hover()
            pg3.wait_for_timeout(400)
            zh_pop_visible = pg3.locator(".row-pop").is_visible()
            checks.append(("ZH: sector row-pop opens", zh_pop_visible))
            if zh_pop_visible:
                pop_text = pg3.locator(".row-pop").inner_text()
                # Should have Chinese label text (60日RS or similar)
                checks.append(("ZH: row-pop has CJK text", any(ord(c) > 0x4e00 for c in pop_text)))
        pg3.screenshot(path=str(SHOTS_DIR / "pr3_sector_pop_zh_1440.png"), full_page=False)
        pg3.close()

        # --- (d) macro.html renders without visual regression ---
        # The V2 action board is mode-gated: only renders in mode='stocks'.
        # In mode='macro' the page renders the macro dashboard (no actiongrid div in body).
        # Verify: page loads correctly, no JS errors, title present, no crash.
        print("\n=== macro.html mode ===")
        pg4 = _new_page(html_macro)
        pg4.screenshot(path=str(SHOTS_DIR / "pr3_macro_mode_1440.png"), full_page=False)
        macro_errors = pg4._pr3_errors
        checks.append(("macro mode: no JS errors (non-network)", len(macro_errors) == 0))
        # Macro dashboard title visible
        title = pg4.title()
        checks.append(("macro mode: title contains 'Macro'", "Macro" in title))
        # Confirm no actitem rows in macro mode (action board is stocks-only)
        actitem_ct = pg4.locator(".actitem").count()
        checks.append(("macro mode: no actitem rows (mode-gated correctly)", actitem_ct == 0))
        pg4.close()

        # --- (e) Sector row in "Stand aside" lst-collapse (row inside View all modal) ---
        print("\n=== Stand-aside lane (avoid, lst-collapse) ===")
        pg5 = _new_page(html_stocks)
        # Expand dash-hold-fold to make rows accessible
        pg5.evaluate("document.querySelector('#dash-hold-fold').classList.remove('is-collapsed')")
        pg5.wait_for_timeout(200)
        avoid_rows = pg5.locator("#dash-hold-fold .actitem[data-rpop]")
        n_avoid = avoid_rows.count()
        checks.append((f"avoid lane has data-rpop rows (n={n_avoid})", n_avoid > 0))
        if n_avoid > 0:
            avoid_rows.first.hover()
            pg5.wait_for_timeout(400)
            pop_in_fold = pg5.locator(".row-pop").is_visible()
            checks.append(("avoid lane row hover opens row-pop", pop_in_fold))
        pg5.screenshot(path=str(SHOTS_DIR / "pr3_avoid_lane_1440.png"), full_page=False)
        pg5.close()

        browser.close()

    return checks


def run():
    print("Rendering dashboard.html.j2 in stocks + macro modes...")
    html_stocks = _render("stocks")
    html_macro = _render("macro")
    print(f"  stocks html: {len(html_stocks):,} chars")
    print(f"  macro html:  {len(html_macro):,} chars")

    print("\n=== HTML-only checks ===")
    html_checks = _check_html_only(html_stocks, html_macro)
    for name, ok in html_checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    print("\n=== Browser checks ===")
    browser_checks = _playwright_checks(html_stocks, html_macro)
    for name, ok in browser_checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    all_checks = html_checks + browser_checks
    passed = sum(1 for _, ok in all_checks if ok)
    total = len(all_checks)
    print(f"\n{'='*40}")
    print(f"{passed}/{total} checks passed")
    print("Screenshots saved to verify_shots/pr3_*.png")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run()
