#!/usr/bin/env python3
"""Independent recapture of verified board interaction screenshots."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from pw_lib import assert_and_shot, goto, launch_browser, load_aionui_cookies, new_page

SHOTS = Path("/Users/chriswong/Documents/Cluade/macro-main/ux-evidence/pages/us-stocks-prophet-board/screenshots")
URL = "https://www.mastermind-x.com/us_stocks.html"
W, H = 1440, 1000


def shot(page, name):
    rec = assert_and_shot(page, SHOTS / name, W, H)
    print("ok", name, rec["screenshot_px"])


def main():
    cookies = load_aionui_cookies()
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = launch_browser(p)

        ctx, page = new_page(b, W, H, cookies)
        goto(page, URL)
        page.locator("#us-st-btn-table").click()
        page.wait_for_timeout(400)
        assert page.locator("#us-st-btn-table").get_attribute("aria-selected") == "true"
        shot(page, "board_table_view_1440x1000.png")
        ctx.close()

        ctx, page = new_page(b, W, H, cookies)
        goto(page, URL)
        page.locator("#trd-btn").click()
        page.wait_for_timeout(400)
        assert page.locator("#trd-btn").get_attribute("aria-expanded") == "true"
        shot(page, "board_track_record_open_1440x1000.png")
        ctx.close()

        for stage in ("live", "setting_up", "ran", "basing", "blocked", "all"):
            ctx, page = new_page(b, W, H, cookies)
            goto(page, URL)
            page.locator(f"#us-stage-filter [data-stagepick={stage}]").click()
            page.wait_for_timeout(350)
            assert page.locator(f"#us-stage-filter [data-stagepick={stage}]").get_attribute("aria-pressed") == "true"
            shot(page, f"board_stage_{stage}_1440x1000.png")
            ctx.close()

        ctx, page = new_page(b, W, H, cookies)
        goto(page, URL)
        page.locator("button", has_text="Show 15 more").first.click()
        page.wait_for_timeout(400)
        shot(page, "board_show_more_1440x1000.png")
        ctx.close()

        ctx, page = new_page(b, W, H, cookies)
        goto(page, URL)
        page.locator("a.pvcard[data-ticker=ONTO]").hover()
        page.wait_for_timeout(250)
        shot(page, "board_card_hover_1440x1000.png")
        ctx.close()

        ctx, page = new_page(b, W, H, cookies)
        goto(page, URL)
        btn = page.locator("a.pvcard[data-ticker=ONTO] .pv-cau-btn")
        btn.hover(); btn.focus(); page.wait_for_timeout(300)
        shot(page, "board_onto_caution_1440x1000.png")
        ctx.close()

        b.close()
    print("interactions recaptured")


if __name__ == "__main__":
    main()
