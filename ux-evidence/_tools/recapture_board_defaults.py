#!/usr/bin/env python3
"""Recapture Prophet board default viewports only. Does not wipe detail."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys

sys.path.insert(0, str(Path(__file__).parent))
from paths import evidence_root  # noqa
from pw_lib import (  # noqa
    annotate, assert_and_shot, capture_segments, dump_json,
    extract, goto, launch_browser, load_aionui_cookies, new_page,
)

BOARD = evidence_root() / "pages" / "us-stocks-prophet-board"
URL = "https://www.mastermind-x.com/us_stocks.html"
VIEWS = [("1440x1000",1440,1000),("1280x900",1280,900),("1024x800",1024,800),("768x900",768,900),("390x844",390,844)]
CATALOG = [
    {"id":"E.board.root","selector":"#us-standouts","section":"board"},
    {"id":"E.board.title","selector":"#us-standouts h2","section":"board"},
    {"id":"E.board.view.grid","selector":"#us-st-btn-grid","section":"board-tools"},
    {"id":"E.board.view.table","selector":"#us-st-btn-table","section":"board-tools"},
    {"id":"E.board.sub","selector":"#us-board-sub","section":"board"},
    {"id":"E.board.note","selector":"#us-standouts .pbs-note","section":"board"},
    {"id":"E.stage.all","selector":"#us-stage-filter [data-stagepick=all]","section":"filters"},
    {"id":"E.stage.live","selector":"#us-stage-filter [data-stagepick=live]","section":"filters"},
    {"id":"E.stage.setting_up","selector":"#us-stage-filter [data-stagepick=setting_up]","section":"filters"},
    {"id":"E.stage.ran","selector":"#us-stage-filter [data-stagepick=ran]","section":"filters"},
    {"id":"E.stage.basing","selector":"#us-stage-filter [data-stagepick=basing]","section":"filters"},
    {"id":"E.stage.blocked","selector":"#us-stage-filter [data-stagepick=blocked]","section":"filters"},
    {"id":"E.card.ONTO","selector":"a.pvcard[data-ticker=ONTO]","section":"cards"},
    {"id":"E.card.ONTO.verb","selector":"a.pvcard[data-ticker=ONTO] .pv-chip","section":"cards"},
    {"id":"E.card.ONTO.trigger","selector":"a.pvcard[data-ticker=ONTO] .pv-trg","section":"cards"},
    {"id":"E.card.ONTO.priority","selector":"a.pvcard[data-ticker=ONTO] .pv-edn","section":"cards"},
    {"id":"E.board.track.btn","selector":"#trd-btn","section":"track"},
]

def main():
    cookies = load_aionui_cookies()
    print("cookies", len(cookies))
    shots = BOARD / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    fid = []
    with sync_playwright() as p:
        browser = launch_browser(p)
        for name,w,h in VIEWS:
            ctx, page = new_page(browser, w, h, cookies)
            goto(page, URL)
            if page.locator("#us-standouts").count():
                page.locator("#us-standouts").scroll_into_view_if_needed()
                page.wait_for_timeout(250)
            ext = extract(page, CATALOG)
            dump_json(BOARD / f"extract-{name}.json", ext)
            path = shots / f"board_default_{name}.png"
            rec = assert_and_shot(page, path, w, h)
            fid.append(rec)
            annotate(path, shots / f"board_default_{name}_annotated.png", ext.get("elements") or [])
            if name in ("1440x1000","390x844"):
                try:
                    fid.append(assert_and_shot(page, shots / f"board_default_{name}_full.png", w, h, full=True))
                except Exception as e:
                    print("native full skip", e)
                segs = capture_segments(page, shots / f"board_full_segments_{name}", "board", w, h)
                fid.extend(segs)
            print("ok", name, path.stat().st_size)
            ctx.close()
        browser.close()
    dump_json(BOARD / "capture-fidelity.json", fid)
    print("done", len(fid), "records")

if __name__ == "__main__":
    main()
