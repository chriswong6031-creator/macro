"""take_down_state_screenshot.py — capture Mag 7 panel in down + rolling_over states.

Renders templates/_mag7_panel.html.j2 with negative run.cw_ret and run.spy_ret,
then screenshots with Playwright to prove the state line renders '-6%' not '+-6%'.

Run: python verify_shots/take_down_state_screenshot.py
"""
from __future__ import annotations
import json
import pathlib
import sys
import socket

WORKTREE = pathlib.Path(__file__).parent.parent
TMPL_DIR = WORKTREE / "templates"
SHOTS_DIR = WORKTREE / "verify_shots"

BASE_FIXTURE = {
    "as_of": "2026-07-10",
    "weights_basis": "polygon_mktcap",
    "structure": {"dd_from_252d_high": -0.082, "chip": "recovering"},
    "k7": {"trend": 2, "rs": 3},
    "cw": {"r2": -0.011, "r5": -0.032, "r10": -0.061, "r20": -0.038, "rel20": -0.016},
    "ew": {"r10": -0.042, "r20": -0.020},
    "members": [
        {"sym": "AAPL", "w": 0.184, "r5": -0.083, "r10": -0.065, "r20": -0.088,
         "rs20": -0.061, "above50": False, "above200": False, "contrib10": -0.31,
         "mtf": "DOWN"},
        {"sym": "MSFT", "w": 0.132, "r5": -0.020, "r10": -0.031, "r20": -0.047,
         "rs20": -0.063, "above50": False, "above200": False, "contrib10": -0.08,
         "mtf": "DOWN"},
        {"sym": "NVDA", "w": 0.128, "r5": -0.044, "r10": -0.012, "r20": -0.026,
         "rs20": -0.042, "above50": False, "above200": False, "contrib10": -0.01,
         "mtf": "DOWN"},
        {"sym": "AMZN", "w": 0.110, "r5": -0.021, "r10": -0.038, "r20": -0.047,
         "rs20": -0.031, "above50": False, "above200": False, "contrib10": -0.04,
         "mtf": "DOWN"},
        {"sym": "GOOGL", "w": 0.102, "r5": -0.008, "r10": -0.009, "r20": -0.015,
         "rs20": -0.031, "above50": False, "above200": False, "contrib10": -0.01,
         "mtf": "DOWN"},
        {"sym": "META", "w": 0.098, "r5": -0.062, "r10": -0.071, "r20": -0.081,
         "rs20": -0.065, "above50": False, "above200": False, "contrib10": -0.07,
         "mtf": "DOWN"},
        {"sym": "TSLA", "w": 0.070, "r5": -0.033, "r10": -0.054, "r20": -0.063,
         "rs20": -0.079, "above50": False, "above200": False, "contrib10": -0.04,
         "mtf": "DOWN"},
    ],
    "generals": {"now": [], "joining": [], "coverage": 0.0},
    "spread20": {"max": -0.015, "min": -0.088, "range": 0.073},
    "mags": {"px": 55.40, "asof": "2026-07-02", "since_run": -0.057},
    "tech_legs": [
        {"id": "mag7", "en": "Mag 7", "zh": "七巨头", "r10_rel": -0.061,
         "r20_rel": -0.016, "word": "falling hard"},
        {"id": "ai_semiconductors", "en": "AI chips", "zh": "AI芯片",
         "r10_rel": -0.021, "r20_rel": -0.012, "word": "falling"},
        {"id": "memory_storage", "en": "Memory", "zh": "存储",
         "r10_rel": -0.14, "r20_rel": -0.023, "word": "falling hard"},
        {"id": "ai_software", "en": "Software", "zh": "软件",
         "r10_rel": -0.008, "r20_rel": -0.007, "word": "flat"},
    ],
}

DOWN_FIXTURE = dict(BASE_FIXTURE,
    trend_state="down",
    run={"start": "2026-05-14", "sessions": 42, "cw_ret": -0.063, "spy_ret": -0.024})

ROLLING_FIXTURE = dict(BASE_FIXTURE,
    trend_state="rolling_over",
    run={"start": "2026-06-05", "sessions": 6, "cw_ret": -0.031, "spy_ret": -0.021})


def render_panel(fixture: dict) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    tmpl = env.from_string(
        "{% from '_mag7_panel.html.j2' import mag7_panel %}{{ mag7_panel(d) }}"
    )
    panel_html = tmpl.render(d=fixture)

    # Wrap in a minimal page with the site's CSS variables to render properly
    site_css = (WORKTREE / "site" / "style.css")
    css_link = f'<link rel="stylesheet" href="style.css">' if site_css.exists() else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{css_link}
<style>
:root {{
  --c-bg: #0a0e14;
  --c-surface: #131920;
  --c-surface2: #1a2230;
  --c-border: #1e2a38;
  --c-text: #c9d1d9;
  --c-text2: #8b949e;
  --c-accent: #58a6ff;
  --c-green: #3fb950;
  --c-red: #f85149;
  --c-amber: #d29922;
  --c-yellow: #e3b341;
  --ff-mono: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  --ff-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
body {{
  background: var(--c-bg);
  color: var(--c-text);
  font-family: var(--ff-sans);
  font-size: 14px;
  margin: 0;
  padding: 16px;
  box-sizing: border-box;
}}
.l-zh {{ display: none; }}
/* Mag 7 panel styles (minimal preview) */
.m7p {{ background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 8px; padding: 16px; max-width: 700px; }}
.m7p-hd {{ margin-bottom: 12px; }}
.m7p-meta {{ flex: 1; }}
.m7p-title-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.m7p-h2 {{ margin: 0; font-size: 16px; font-weight: 600; }}
.m7p-badge {{ background: #1a2230; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: var(--c-text2); }}
.m7p-help {{ cursor: help; color: var(--c-text2); font-size: 11px; border: 1px solid var(--c-border); border-radius: 50%; width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center; }}
.m7p-state {{ font-size: 13px; color: var(--c-text); margin-bottom: 4px; }}
.m7p-stance {{ font-size: 13px; font-weight: 500; color: var(--c-red); margin-bottom: 12px; }}
.m7p-down .m7p-stance, .m7p-rolling_over .m7p-stance {{ color: var(--c-red); }}
.m7p-dots {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
.m7p-dot-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: default; }}
.m7p-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.m7p-dot-green {{ background: var(--c-green); }}
.m7p-dot-amber {{ background: var(--c-amber); }}
.m7p-dot-grey {{ background: var(--c-text2); }}
.m7p-dot-lbl {{ font-size: 10px; color: var(--c-text2); }}
.m7p-generals {{ font-size: 12px; color: var(--c-text2); margin-bottom: 10px; }}
.m7p-struct {{ display: inline-block; background: #1a2230; border-radius: 4px; padding: 2px 8px; font-size: 12px; margin-bottom: 10px; }}
.m7p-legs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
.m7p-leg {{ display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #1a2230; cursor: default; }}
.m7p-leg.up2, .m7p-leg.up {{ color: var(--c-green); }}
.m7p-leg.dn2, .m7p-leg.dn {{ color: var(--c-red); }}
.m7p-leg-name {{ font-weight: 500; }}
.m7p-leg-word {{ color: inherit; }}
.m7p-foot {{ font-size: 11px; color: var(--c-text2); border-top: 1px solid var(--c-border); padding-top: 8px; }}
.m7p-asof {{ display: block; margin-top: 4px; font-size: 10px; opacity: 0.7; }}
h3 {{ color: var(--c-text2); font-size: 13px; margin: 20px 0 8px; }}
</style>
</head>
<body>
<h3>State: {fixture['trend_state']} — run.cw_ret={fixture['run']['cw_ret']}, run.spy_ret={fixture['run']['spy_ret']}</h3>
{panel_html}
</body>
</html>"""


def screenshot_state(fixture: dict, name: str, playwright_ctx):
    html = render_panel(fixture)
    # Verify the sign in the raw HTML before screenshotting
    assert "+-" not in html, f"BROKEN: '+-' found in rendered HTML for state={fixture['trend_state']}"
    state = fixture["trend_state"]
    cw = round(fixture["run"]["cw_ret"] * 100)
    spy = round(fixture["run"]["spy_ret"] * 100)
    assert f"{cw}%" in html, f"Expected '{cw}%' in HTML for state={state}"

    out_path = SHOTS_DIR / name
    page = playwright_ctx.new_page()
    page.set_content(html, wait_until="networkidle")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.screenshot(path=str(out_path))
    page.close()
    print(f"  Screenshot saved: {out_path}")
    return out_path


def main():
    from playwright.sync_api import sync_playwright

    print("Verifying sign correctness in rendered HTML...")
    # Quick Jinja verification before Playwright
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    for state, fixture in [("down", DOWN_FIXTURE), ("rolling_over", ROLLING_FIXTURE)]:
        tmpl = env.from_string(
            "{% from '_mag7_panel.html.j2' import mag7_panel %}{{ mag7_panel(d) }}"
        )
        html = tmpl.render(d=fixture)
        assert "+-" not in html, f"FAIL: '+-' in rendered HTML for state={state}"
        print(f"  [PASS] state={state}: no '+-' found in HTML")
        cw = round(fixture["run"]["cw_ret"] * 100)
        assert f"{cw}%" in html, f"FAIL: '{cw}%' not in HTML for state={state}"
        print(f"  [PASS] state={state}: '{cw}%' found in HTML")

    print("\nCapturing Playwright screenshots...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})

        shot1 = screenshot_state(DOWN_FIXTURE, "mag7_down_state_1280.png", ctx)
        shot2 = screenshot_state(ROLLING_FIXTURE, "mag7_rolling_over_state_1280.png", ctx)

        ctx.close()
        browser.close()

    print(f"\nScreenshots committed:")
    print(f"  {shot1}")
    print(f"  {shot2}")
    print("\nVERIFICATION PASSED — sign handling is correct for down + rolling_over states.")


if __name__ == "__main__":
    main()
