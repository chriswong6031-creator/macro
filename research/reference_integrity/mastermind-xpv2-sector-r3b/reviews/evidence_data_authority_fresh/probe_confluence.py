import json
from playwright.sync_api import sync_playwright
BASE="file:///Users/chriswong/Documents/Cluade/Macro%20Dashboard/.claude/worktrees/xpv2-sc-r3b-critic-data-8151af/mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
out={}
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1440,"height":1000})
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE+"#confluence", wait_until="load"); pg.wait_for_timeout(3000)
    def txt(sel):
        try: return pg.eval_on_selector(sel,"e=>e.innerText.replace(/\\s+/g,' ').trim()")
        except Exception as e: return f"<none:{sel}>"
    out["cf_tabs"]=pg.eval_on_selector_all("[role='tab']","els=>els.map(e=>({t:e.innerText.replace(/\\s+/g,' ').trim(),sel:e.getAttribute('aria-selected'),id:e.id}))")
    out["cf_foot_sp"]=txt("#cf-foot")
    # switch tabs and capture foot + row counts
    for ds,label in [("subsectors","S&P"),("nasdaq","Nasdaq"),("russell","Russell"),("baskets","Baskets")]:
        try:
            pg.evaluate("d=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.id&&x.id.indexOf(d)>=0); if(b) b.click();}", ds)
            pg.wait_for_timeout(700)
            out[f"foot_{ds}"]=txt("#cf-foot")
            out[f"rows_{ds}"]=pg.eval_on_selector_all(".r3-cf-row, #cf-rows tr, #sc-app .r3-row","els=>els.length")
        except Exception as e: out[f"foot_{ds}"]=f"ERR {e}"
    out["errs"]=errs[:10]
    b.close()
print(json.dumps(out,ensure_ascii=False,indent=1)[:5000])
