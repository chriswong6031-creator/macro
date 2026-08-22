import json, sys
from playwright.sync_api import sync_playwright
C="file:///Users/chriswong/Documents/Cluade/Macro%20Dashboard/.claude/worktrees/xpv2-sc-r3b-critic-data-8151af/mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
out={}
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_page(viewport={"width":1440,"height":1000})
    errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console:"+m.type+":"+m.text) if m.type=="error" else None)
    pg.goto(C+"#overview", wait_until="load")
    pg.wait_for_timeout(2500)
    out["page_errors"]=errs[:20]
    out["title"]=pg.title()
    # views present
    out["views"]=pg.eval_on_selector_all("[data-view]", "els=>[...new Set(els.map(e=>e.getAttribute('data-view')))]")
    # Overview lane tabs + counts
    out["ov_tabs"]=pg.eval_on_selector_all("#ov-ledge .r3-ledge-cell",
      "els=>els.map(e=>({lane:e.dataset.lane, name:e.querySelector('.r3-ledge-name .l-en')?.textContent, count:e.querySelector('.r3-ledge-count')?.textContent, sel:e.getAttribute('aria-selected')}))")
    out["ov_foot"]=pg.eval_on_selector("#ov-foot","e=>e.innerText.replace(/\\s+/g,' ').trim()")
    # rows in the visible lane
    out["ov_rows_buy"]=pg.eval_on_selector_all("#ab-buy-fold > a",
      "els=>els.map(e=>({name:e.querySelector('.r3-name .l-en')?.textContent, sub:e.querySelector('.r3-sub')?.innerText.replace(/\\s+/g,' '), fig:e.querySelector('.r3-fig')?.textContent, why:e.querySelector('.r3-why .l-en')?.textContent, href:e.getAttribute('href')}))")
    out["ov_disclosures"]=pg.eval_on_selector_all("#actnow .pg-more, #actnow .pg-plus","els=>els.map(e=>e.innerText.replace(/\\s+/g,' ').trim())")
    out["ov_hero"]=pg.eval_on_selector("#ov-ctx-body","e=>e.innerText.replace(/\\s+/g,' ').trim()")
    out["ov_watch"]=pg.eval_on_selector_all(".r3-watch-cell","els=>els.map(e=>e.innerText.replace(/\\s+/g,' ').trim())")
    out["ov_watch_foot"]=pg.eval_on_selector("#ov-watch-foot","e=>e.innerText.replace(/\\s+/g,' ').trim()")
    b.close()
print(json.dumps(out,ensure_ascii=False,indent=1)[:6000])
