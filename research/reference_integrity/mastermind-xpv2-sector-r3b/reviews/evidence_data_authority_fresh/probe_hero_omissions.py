import json
from playwright.sync_api import sync_playwright
BASE="file:///Users/chriswong/Documents/Cluade/Macro%20Dashboard/.claude/worktrees/xpv2-sc-r3b-critic-data-8151af/mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
out={}
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1440,"height":1200})
    pg.goto(BASE+"#overview", wait_until="load"); pg.wait_for_timeout(3000)
    # DAC-104: every destination the RENDERED overview offers
    out["overview_hrefs"]=sorted(set(pg.eval_on_selector_all(
      "[data-view='overview'] a[href]", "els=>els.map(e=>e.getAttribute('href'))")))
    # DAC-101/102: full rendered text of the hero band
    out["hero_full_text"]=pg.eval_on_selector("[data-view='overview'] .r3-band, [data-view='overview']",
      "e=>e.innerText.replace(/\\s+/g,' ').trim().slice(0,700)")
    # every receipt/tooltip button in the overview and what caveat each carries
    out["overview_receipts"]=pg.eval_on_selector_all("[data-view='overview'] .r3-rcpt",
      "els=>els.map(e=>({en:(e.getAttribute('data-tip-en')||'').slice(0,150)}))")
    # DAC-101 explicit: is ANY sizing string rendered anywhere in the document?
    out["sizing_in_rendered_text"]=pg.evaluate(
      "()=>{const t=document.body.innerText; return ['positions sized','仓位缩','sized to','gross'].map(s=>[s,t.includes(s)])}")
    out["forecast_caveat_in_rendered_text"]=pg.evaluate(
      "()=>{const t=document.body.innerText; return ['not a forecast','How this works','Trailing-momentum','Open the playbook','allocation'].map(s=>[s,t.includes(s)])}")
    b.close()
print(json.dumps(out,ensure_ascii=False,indent=1)[:4000])
